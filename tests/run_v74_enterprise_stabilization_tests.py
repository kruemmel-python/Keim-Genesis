from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = [sys.executable, "-S"]
EX = "examples/sprache_v74_enterprise_stabilization.keim"


def run(*args: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(PY + ["-m", "keim", *args], cwd=ROOT, text=True, input=input_text, capture_output=True, check=True)


def test_status_spec_build_verify() -> None:
    out = ROOT / "build" / "v74_test"
    run("v74-status", "--json")
    spec = run("v74-spec", "--json")
    assert json.loads(spec.stdout)["format"] == "keim-kbc-stable-1"
    check = run("v74-check", EX, "--json")
    assert json.loads(check.stdout)["ok"] is True
    build = run("v74-build", EX, "--out", str(out), "--json")
    payload = json.loads(build.stdout)
    assert payload["ok"] is True
    assert (out / "app.kbcstable").exists()
    verify = run("v74-verify", str(out / "app.kbcstable"), "--json")
    assert json.loads(verify.stdout)["ok"] is True


def test_security_sbom_parity_benchmark_compat() -> None:
    out = ROOT / "build" / "v74_test_tools"
    sec = run("v74-security", EX, "--json")
    assert json.loads(sec.stdout)["ok"] is True
    sbom = run("v74-sbom", "--cwd", ".", "--out", str(out / "sbom"), "--json")
    assert json.loads(sbom.stdout)["format"] == "keim-sbom-v1"
    parity = run("v74-parity", EX, "--out", str(out / "parity"), "--json")
    assert json.loads(parity.stdout)["source"].endswith(EX)
    bench = run("v74-benchmark", EX, "--out", str(out / "bench"), "--iterations", "1", "--json")
    assert json.loads(bench.stdout)["format"] == "keim-benchmark-v1"
    compat = run("v74-compat", "--cwd", ".", "--out", str(out / "compat"), "--json")
    assert json.loads(compat.stdout)["format"] == "keim-compatibility-matrix-v1"


def test_lsp_bundle_and_stdio() -> None:
    out = ROOT / "build" / "v74_lsp"
    bundle = run("v74-lsp-bundle", "--out", str(out), "--json")
    assert json.loads(bundle.stdout)["ok"] is True
    request = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}) + "\n"
    proc = run("v74-lsp", input_text=request)
    response = json.loads(proc.stdout.splitlines()[0])
    assert response["result"]["serverInfo"]["name"] == "keim-lsp"


def test_whitepaper() -> None:
    out = ROOT / "build" / "v74_whitepaper.md"
    wp = run("v74-whitepaper", "--out", str(out), "--json")
    assert json.loads(wp.stdout)["ok"] is True
    assert "Enterprise Stabilization" in out.read_text(encoding="utf-8")


def main() -> int:
    test_status_spec_build_verify()
    test_security_sbom_parity_benchmark_compat()
    test_lsp_bundle_and_stdio()
    test_whitepaper()
    print("[Keim v7.4] Enterprise Stabilization Tests OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
