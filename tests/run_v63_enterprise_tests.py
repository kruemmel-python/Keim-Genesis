from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = [sys.executable, "-S"]


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(PY + ["-m", "keim", *args], cwd=ROOT, text=True, capture_output=True, check=True)


def test_enterprise_check_status() -> None:
    status = run("enterprise-status", "--json")
    matrix = json.loads(status.stdout)
    assert len(matrix) == 10
    assert all(row["status"] == "implementiert" for row in matrix)

    check = run("enterprise-check", "examples/sprache_v61_compiler_runtime.keim", "--json")
    payload = json.loads(check.stdout)
    assert payload["ok"], payload


def test_project_build_test_reports_and_seeds() -> None:
    out = ROOT / "build" / "v63_enterprise_test"
    if out.exists():
        import shutil
        shutil.rmtree(out)

    run("enterprise-build", "--cwd", ".", "--out", str(out))
    assert (out / "app.kbc.json").exists()
    assert (out / "keim.lock").exists()
    assert json.loads((out / "keim.lock").read_text(encoding="utf-8"))["format"] == "keim-lock-v3"

    run(
        "enterprise-test",
        "examples/sprache_v61_compiler_runtime.keim",
        "--coverage",
        "--json-out", str(out / "tests.json"),
        "--junit-out", str(out / "tests.xml"),
    )
    assert json.loads((out / "tests.json").read_text(encoding="utf-8"))["ok"]
    assert "<testsuite" in (out / "tests.xml").read_text(encoding="utf-8")

    run("enterprise-native", str(out / "app.kbc.json"), "--out", str(out / "keimvm_seed.cpp"))
    run("enterprise-wasm", str(out / "app.kbc.json"), "--out", str(out / "app_seed.wat"))
    assert "keim_native_version" in (out / "keimvm_seed.cpp").read_text(encoding="utf-8")
    assert "keim_version" in (out / "app_seed.wat").read_text(encoding="utf-8")


def test_enterprise_lint_fmt_replay() -> None:
    lint = run("enterprise-lint", "examples/sprache_v61_compiler_runtime.keim", "--json")
    assert json.loads(lint.stdout)["ok"]

    fmt = run("enterprise-fmt", "examples/sprache_v61_compiler_runtime.keim")
    assert "modul demo.v61" in fmt.stdout

    replay = ROOT / "build" / "v63_replay.json"
    run("core-run", "examples/sprache_v61_compiler_runtime.keim", "--record", str(replay))
    out = run("enterprise-replay", str(replay), "--json")
    payload = json.loads(out.stdout)
    assert payload["ok"]
    assert payload["event_count"] > 0


def main() -> int:
    test_enterprise_check_status()
    test_project_build_test_reports_and_seeds()
    test_enterprise_lint_fmt_replay()
    print("[Keim v6.3 Enterprise] Tests OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
