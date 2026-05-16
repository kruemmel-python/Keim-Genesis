from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = [sys.executable, "-S"]


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(PY + ["-m", "keim", *args], cwd=ROOT, text=True, capture_output=True, check=True)


def test_expression_parser_no_python_ast() -> None:
    res = run("v64-expr", "a * b + 4", "--json")
    payload = json.loads(res.stdout)
    assert payload["kind"] == "binary"
    assert payload["op"] == "+"
    assert payload["left"]["op"] == "*"


def test_linear_bytecode_and_vm64() -> None:
    out = ROOT / "build" / "v64_tests"
    out.mkdir(parents=True, exist_ok=True)
    bc = out / "app.kbc64.json"
    run("v64-bytecode", "examples/sprache_v64_professional_core.keim", "--out", str(bc))
    payload = json.loads(bc.read_text(encoding="utf-8"))
    assert payload["format"] == "keim-linear-bytecode"
    assert payload["version"] == 640
    text = json.dumps(payload)
    assert "EVAL" not in text
    assert "JUMP_IF_FALSE" in text
    assert "LOAD_SLOT" in text
    run("v64-run", "examples/sprache_v64_professional_core.keim", "--record", str(out / "run.kreplay"))
    assert (out / "run.kreplay").exists()


def test_type_error_before_runtime() -> None:
    tmp = ROOT / "build" / "v64_tests" / "bad_type.keim"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(
        "modul bad\n\nfunktion main() gibt ganzzahl:\n    rueckgabe \"falsch\"\n",
        encoding="utf-8",
    )
    res = subprocess.run(PY + ["-m", "keim", "v64-check", str(tmp)], cwd=ROOT, text=True, capture_output=True)
    assert res.returncode != 0
    assert "Rückgabe erwartet ganzzahl" in res.stdout


def test_junit_lint_native_wasm() -> None:
    out = ROOT / "build" / "v64_tests"
    junit = out / "junit.xml"
    run("v64-test", "examples/sprache_v64_professional_core.keim", "--coverage", "--junit", str(junit), "--json")
    assert junit.exists()
    run("v64-lint", "examples/sprache_v64_professional_core.keim")
    bc = out / "app.kbc64.json"
    if not bc.exists():
        run("v64-bytecode", "examples/sprache_v64_professional_core.keim", "--out", str(bc))
    cpp = out / "keimvm64_seed.cpp"
    wat = out / "app_seed.wat"
    run("v64-native", str(bc), "--out", str(cpp))
    run("v64-wasm", str(bc), "--out", str(wat))
    assert cpp.exists() and wat.exists()
    compiler = shutil.which("g++") or shutil.which("c++")
    if compiler:
        subprocess.run([compiler, "-std=c++20", "-fsyntax-only", str(cpp)], cwd=ROOT, check=True)


def main() -> int:
    test_expression_parser_no_python_ast()
    test_linear_bytecode_and_vm64()
    test_type_error_before_runtime()
    test_junit_lint_native_wasm()
    print("[Keim v6.4] Professional compiler/runtime tests OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
