from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = [sys.executable, "-S"]


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(PY + ["-m", "keim", *args], cwd=ROOT, text=True, capture_output=True, check=True)


def test_status_reports_self_bootstrap() -> None:
    payload = json.loads(run("exe-status", "--json").stdout)
    assert payload["version"] >= 782
    assert "self_bootstrapping_runtime_launcher" in payload["features"]
    assert payload["external_compiler_required"] is False


def test_launcher_executes_runtime_on_host() -> None:
    out = ROOT / "build" / "v782_self_bootstrap"
    run("exe-pack", "examples/exe_runtime_packager_v78/main.keim", "--out", str(out), "--name", "keim_v782_self", "--no-gpu")
    verify = json.loads(run("exe-verify", str(out), "--json").stdout)
    assert verify["ok"] is True
    assert verify["self_bootstrap_launcher"]["ok"] is True

    launcher = out / "bin" / ("keim_v782_self_launcher.exe" if os.name == "nt" else "keim_v782_self_launcher")
    assert launcher.exists(), launcher
    if os.name != "nt":
        res = subprocess.run([str(launcher)], cwd=ROOT, text=True, capture_output=True, check=True)
        assert "42" in res.stdout


def test_windows_launcher_artifact_is_pe() -> None:
    out = ROOT / "build" / "v782_self_bootstrap_win"
    run(
        "exe-pack",
        "examples/exe_runtime_packager_v78/main.keim",
        "--out",
        str(out),
        "--name",
        "keim_v782_win",
        "--target",
        "pe64-windows-x86_64",
        "--no-gpu",
    )
    launcher = out / "bin" / "keim_v782_win_launcher.exe"
    assert launcher.exists()
    assert launcher.read_bytes().startswith(b"MZ")
    verify = json.loads(run("exe-verify", str(out), "--json").stdout)
    assert verify["self_bootstrap_launcher"]["ok"] is True
    assert (out / "bin" / "keim_v782_win_launcher.cmd").exists()


def main() -> int:
    test_status_reports_self_bootstrap()
    test_launcher_executes_runtime_on_host()
    test_windows_launcher_artifact_is_pe()
    print("[Keim v7.8.3] Self-Bootstrapping Launcher Tests OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
