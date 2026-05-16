from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = [sys.executable, "-S"]


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(PY + ["-m", "keim", *args], cwd=ROOT, text=True, capture_output=True, check=True)


def test_bytecode_binary_monomorphization() -> None:
    out = ROOT / "build" / "v67_tests" / "app.kbc67.json"
    bin_out = ROOT / "build" / "v67_tests" / "app.kbc67b"
    res = run("v67-bytecode", "examples/sprache_v67_full_enterprise.keim", "--out", str(out), "--binary-out", str(bin_out), "--json")
    payload = json.loads(res.stdout)
    assert payload["version"] == 670
    assert payload["generic_monomorphization"]["clone_count"] >= 1
    assert "GENERIC" in payload["sections"] or "GENERIC" in payload.get("binary_sections", ["GENERIC"])
    assert "EVAL" not in res.stdout
    assert bin_out.exists() and bin_out.read_bytes().startswith(b"KBC67HASH")


def test_run_bin_wasm_and_replay_debugger() -> None:
    out_dir = ROOT / "build" / "v67_tests"
    bin_out = out_dir / "app.kbc67b"
    if not bin_out.exists():
        run("v67-bytecode", "examples/sprache_v67_full_enterprise.keim", "--binary-out", str(bin_out))
    run("v67-run-bin", str(bin_out))
    replay = out_dir / "run.kreplay"
    html = out_dir / "time_travel.html"
    run("v67-run", "examples/sprache_v67_full_enterprise.keim", "--record", str(replay))
    res = run("v67-replay", str(replay), "--html-out", str(html), "--json")
    payload = json.loads(res.stdout)
    assert payload["ok"] is True
    assert html.exists()
    assert "Keim Time Travel Debugger v6.7" in html.read_text(encoding="utf-8")
    wat = out_dir / "app.wat"
    run("v67-wasm", str(bin_out), "--out", str(wat))
    text = wat.read_text(encoding="utf-8")
    assert "(module" in text and "keim_host" in text


def test_registry_publish_resolve_install() -> None:
    registry = ROOT / "build" / "v67_tests" / "registry"
    cache = ROOT / "build" / "v67_tests" / "cache"
    run("v67-registry", "init", "--registry", str(registry), "--json")
    pub = json.loads(run("v67-registry", "publish", "--registry", str(registry), "--cwd", ".", "--name", "demo.v67pkg", "--version", "1.2.3", "--json").stdout)
    assert pub["sha256"] and pub["signature"].startswith("sha256:")
    resolved = json.loads(run("v67-registry", "resolve", "--registry", str(registry), "--name", "demo.v67pkg", "--requirement", "^1.0.0", "--json").stdout)
    assert resolved["version"] == "1.2.3"
    installed = json.loads(run("v67-registry", "install", "--registry", str(registry), "--name", "demo.v67pkg", "--requirement", ">=1.0.0", "--cache", str(cache), "--json").stdout)
    assert Path(installed["cached_archive"]).exists()


def test_embedded_registry_http_server() -> None:
    # In-process server smoke test; validates /v1/packages route without leaving a process behind.
    import importlib
    sys.path.insert(0, str(ROOT))
    from keim.compiler67 import start_registry_server67

    registry = ROOT / "build" / "v67_tests" / "registry"
    handle = start_registry_server67(registry, port=0)
    try:
        raw = urllib.request.urlopen(handle.url + "/v1/packages", timeout=5).read().decode()
        assert "keim-registry-v1" in raw
    finally:
        handle.shutdown()


def main() -> int:
    test_bytecode_binary_monomorphization()
    test_run_bin_wasm_and_replay_debugger()
    test_registry_publish_resolve_install()
    test_embedded_registry_http_server()
    print("[Keim v6.7] Enterprise Complete Tests OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
