from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = [sys.executable, "-S"]


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(PY + ["-m", "keim", *args], cwd=ROOT, text=True, capture_output=True, check=True)


def test_status() -> None:
    res = run("v75-status", "--json")
    payload = json.loads(res.stdout)
    assert payload["version"] == "7.5.0"
    assert "Differential" in payload["release"]


def test_browser_wasm_node_smoke() -> None:
    out = ROOT / "build" / "v75_test_browser"
    res = run("v75-wasm-browser", "--out", str(out), "--json")
    payload = json.loads(res.stdout)
    assert payload["ok"] is True
    assert payload["node"]["value"]["value"] == 42
    assert (out / "browser_wasm_smoke.html").exists()
    assert (out / "keim_answer42.wasm").read_bytes().startswith(b"\0asm")


def test_synthetic_matrix() -> None:
    out = ROOT / "build" / "v75_test_matrix"
    res = run("v75-matrix", "--cwd", ".", "--out", str(out), "--synthetic-only", "--max-cases", "5", "--json")
    payload = json.loads(res.stdout)
    assert payload["ok"] is True
    assert payload["case_count"] == 5
    assert (out / "differential_matrix.junit.xml").exists()
    assert (out / "differential_matrix.html").exists()


def test_hardening_build() -> None:
    out = ROOT / "build" / "v75_test_hardening"
    res = run("v75-hardening-build", "--cwd", ".", "--out", str(out), "--json")
    # Previous examples can print during runtime checks; parse the last JSON object.
    text = res.stdout
    start = text.rfind("\n{")
    payload = json.loads(text[start + 1:] if start >= 0 else text)
    assert payload["ok"] is True
    assert (out / "report.json").exists()
    assert (out / "matrix" / "differential_matrix.json").exists()


def main() -> int:
    test_status()
    test_browser_wasm_node_smoke()
    test_synthetic_matrix()
    test_hardening_build()
    print("[Keim v7.5] Enterprise Hardening Matrix Tests OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
