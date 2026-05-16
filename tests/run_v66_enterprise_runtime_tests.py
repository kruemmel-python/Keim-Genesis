from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = [sys.executable, "-S"]
EX = "examples/sprache_v66_enterprise_full.keim"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(PY + ["-m", "keim", *args], cwd=ROOT, text=True, capture_output=True, check=True)


def test_check_run_binary() -> None:
    run("v66-check", EX)
    out_json = ROOT / "build" / "v66_test" / "app.kbc66.json"
    out_bin = ROOT / "build" / "v66_test" / "app.kbc66b"
    run("v66-bytecode", EX, "--out", str(out_json), "--binary-out", str(out_bin))
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["version"] >= 660
    assert payload["const_pool"], "Constant Pool fehlt"
    assert "PROGRAM" in out_bin.read_bytes().decode("latin1", errors="ignore"), "PROGRAM-Sektion fehlt"
    assert "EVAL" not in out_json.read_text(encoding="utf-8")
    run("v66-run-bin", str(out_bin))


def test_tests_junit_lock_status() -> None:
    junit = ROOT / "build" / "v66_test" / "junit.xml"
    res = run("v66-test", EX, "--json", "--junit", str(junit))
    payload = json.loads(res.stdout)
    assert payload["ok"], payload
    assert payload["coverage"]["instruction_count"] > 0
    assert junit.exists()
    lock = ROOT / "build" / "v66_test" / "keim.lock"
    run("v66-lock", "--cwd", ".", "--out", str(lock))
    assert json.loads(lock.read_text(encoding="utf-8"))["format"] == "keim-lock-v5"
    status = json.loads(run("v66-status", "--json").stdout)
    assert status["implemented"]["constant_pool_sectioned_binary_kbc66b"]


def test_native_differential() -> None:
    out_json = ROOT / "build" / "v66_test" / "native_app.kbc66.json"
    run("v66-bytecode", EX, "--out", str(out_json))
    cpp = ROOT / "build" / "v66_test" / "keimvm66.cpp"
    exe = ROOT / "build" / "v66_test" / "keimvm66"
    run("v66-native", str(out_json), "--out", str(cpp))
    compiler = shutil.which("g++") or shutil.which("c++")
    assert compiler, "C++ compiler fehlt"
    subprocess.run([compiler, "-std=c++20", str(cpp), "-o", str(exe)], cwd=ROOT, text=True, capture_output=True, check=True)
    native = subprocess.run([str(exe)], cwd=ROOT, text=True, capture_output=True, check=True)
    assert native.stdout.strip().endswith("62"), native.stdout


def main() -> int:
    test_check_run_binary()
    test_tests_junit_lock_status()
    test_native_differential()
    print("[Keim v6.6] Enterprise Runtime Completion Tests OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
