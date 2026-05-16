from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = [sys.executable, "-S"]


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(PY + ["-m", "keim", *args], cwd=ROOT, text=True, capture_output=True, check=True)


def test_status_and_check() -> None:
    status = json.loads(run("v69-status", "--json").stdout)
    assert status["version"] == 690
    assert "non_moving_mark_sweep_gc" in status["features"]
    checked = json.loads(run("v69-check", "examples/sprache_v69_gc_hashmap_runtime.keim", "--json").stdout)
    assert checked["ok"], checked


def test_binary_sections_and_metadata() -> None:
    out_json = ROOT / "build" / "v69" / "app.kbc69.json"
    out_bin = ROOT / "build" / "v69" / "app.kbc69b"
    run("v69-bytecode", "examples/sprache_v69_gc_hashmap_runtime.keim", "--out", str(out_json), "--binary-out", str(out_bin))
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["version"] == 690
    assert payload["wasm_runtime"]["gc"]["algorithm"] == "non-moving-mark-sweep"
    assert payload["wasm_runtime"]["hashmap"]["strategy"] == "open-addressing"
    assert out_bin.read_bytes().startswith(b"KBC69HASH")
    result = run("v69-run-bin", str(out_bin))
    assert result.returncode == 0


def test_wasm_runtime_contains_gc_and_hashmap() -> None:
    out_bin = ROOT / "build" / "v69" / "app.kbc69b"
    wat = ROOT / "build" / "v69" / "app_gc_hashmap_runtime.wat"
    if not out_bin.exists():
        run("v69-bytecode", "examples/sprache_v69_gc_hashmap_runtime.keim", "--binary-out", str(out_bin))
    run("v69-wasm", str(out_bin), "--out", str(wat))
    text = wat.read_text(encoding="utf-8")
    assert "unreachable" not in text
    assert "$gc_collect" in text
    assert "$gc_mark_value" in text
    assert "$gc_sweep" in text
    assert "$alloc_gc" in text
    assert "$keim_hashmap_new" in text
    assert "$keim_hashmap_probe" in text
    assert "$keim_map_get" in text


def test_v69_test_command() -> None:
    payload = json.loads(run("v69-test", "examples/sprache_v69_gc_hashmap_runtime.keim", "--json").stdout)
    assert payload["ok"], payload
    checks = payload["coverage"]["v69_gc_hashmap_runtime"]
    assert all(checks.values()), checks


def main() -> int:
    test_status_and_check()
    test_binary_sections_and_metadata()
    test_wasm_runtime_contains_gc_and_hashmap()
    test_v69_test_command()
    print("[Keim v6.9] WASM GC/Hashmap Runtime Tests OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
