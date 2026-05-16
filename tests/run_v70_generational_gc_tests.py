from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = [sys.executable, "-S"]


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(PY + ["-m", "keim", *args], cwd=ROOT, text=True, capture_output=True, check=True)


def json_from_stdout(text: str) -> dict:
    start = text.find("{")
    assert start >= 0, text
    return json.loads(text[start:])


def test_status_check_bytecode_binary() -> None:
    status = json.loads(run("v70-status", "--json").stdout)
    assert status["version"] == 700
    assert "write_barrier" in status["features"]
    out = ROOT / "build" / "v70" / "app.kbc70.json"
    bout = ROOT / "build" / "v70" / "app.kbc70b"
    run("v70-bytecode", "examples/sprache_v70_generational_gc.keim", "--out", str(out), "--binary-out", str(bout), "--json")
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["version"] == 700
    assert payload["wasm_runtime"]["gc"]["algorithm"] == "non-moving-generational-mark-sweep"
    assert {"nursery", "old"}.issubset(payload["heap_layouts"]["spaces"].keys())
    assert bout.read_bytes().startswith(b"KBC70GEN")
    assert "EVAL" not in out.read_text(encoding="utf-8")


def test_wat_generational_gc() -> None:
    bout = ROOT / "build" / "v70" / "app.kbc70b"
    wat = ROOT / "build" / "v70" / "app_generational_gc.wat"
    run("v70-bytecode", "examples/sprache_v70_generational_gc.keim", "--binary-out", str(bout))
    run("v70-wasm", str(bout), "--out", str(wat))
    text = wat.read_text(encoding="utf-8")
    required = [
        "$gc_minor_collect",
        "$gc_major_collect",
        "$keim_write_barrier",
        "$gc_remember_old_object",
        "$gc_remembered_head",
        "$alloc_young",
        "$gc_nursery_ptr",
        "$gc_stats_minor",
        "$gc_stats_major",
    ]
    for item in required:
        assert item in text, item
    assert "unreachable" not in text


def test_run_bin_build_and_test() -> None:
    bout = ROOT / "build" / "v70" / "run.kbc70b"
    run("v70-bytecode", "examples/sprache_v70_generational_gc.keim", "--binary-out", str(bout))
    run("v70-run-bin", str(bout))
    test_payload = json.loads(run("v70-test", "examples/sprache_v70_generational_gc.keim", "--json").stdout)
    assert test_payload["ok"]
    checks = test_payload["coverage"]["v70_generational_gc_runtime"]
    assert all(checks.values()), checks
    build_payload = json_from_stdout(run("v70-build", "--cwd", ".", "--out", "build/v70_project").stdout)
    assert build_payload["ok"]
    assert (ROOT / "build" / "v70_project" / "app_generational_gc_runtime.wat").exists()


def main() -> int:
    test_status_check_bytecode_binary()
    test_wat_generational_gc()
    test_run_bin_build_and_test()
    print("[Keim v7.0] Generational GC Runtime Tests OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
