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


def test_windows_pe_launcher_is_real_waiting_runtime_launcher() -> None:
    out = ROOT / "build" / "v783_real_win_launcher"
    run(
        "exe-pack",
        "examples/exe_runtime_packager_v78/main.keim",
        "--out",
        str(out),
        "--name",
        "keim_v783_real",
        "--target",
        "pe64-windows-x86_64",
        "--no-gpu",
    )
    launcher = out / "bin" / "keim_v783_real_launcher.exe"
    assert launcher.exists(), launcher
    data = launcher.read_bytes()
    assert data.startswith(b"MZ")
    assert b"msvcrt.dll" in data, "PE launcher must import msvcrt"
    assert b"system" in data, "PE launcher must wait through system()"
    assert b"cmd.exe" in data
    assert b"run.bat" in data
    assert b"WinExec" not in data, "WinExec returns immediately and is not acceptable for v7.8.3"
    assert b"Dieses Native-Artefakt" not in data, "Launcher must not be a hint stub"

    verify = json.loads(run("exe-verify", str(out), "--json").stdout)
    sb = verify["self_bootstrap_launcher"]
    assert sb["ok"] is True
    assert sb["real_runtime_launcher"] is True
    assert sb["native_checks"][0]["real_runtime_launcher"] is True
    assert sb["native_checks"][0]["hint_stub_detected"] is False


def test_linux_elf_launcher_executes_runtime() -> None:
    out = ROOT / "build" / "v783_real_elf_launcher"
    run(
        "exe-pack",
        "examples/exe_runtime_packager_v78/main.keim",
        "--out",
        str(out),
        "--name",
        "keim_v783_real_elf",
        "--target",
        "elf64-linux-x86_64",
        "--no-gpu",
    )
    launcher = out / "bin" / "keim_v783_real_elf_launcher"
    assert launcher.exists(), launcher
    assert launcher.read_bytes().startswith(b"\x7fELF")
    if os.name != "nt":
        res = subprocess.run([str(launcher)], cwd=ROOT, text=True, capture_output=True, check=True)
        assert "42" in res.stdout, res.stdout + res.stderr

    verify = json.loads(run("exe-verify", str(out), "--json").stdout)
    assert verify["self_bootstrap_launcher"]["ok"] is True
    assert verify["self_bootstrap_launcher"]["real_runtime_launcher"] is True


def main() -> int:
    test_windows_pe_launcher_is_real_waiting_runtime_launcher()
    test_linux_elf_launcher_executes_runtime()
    print("[Keim v7.8.3] Real Self-Bootstrapping Launcher Tests OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
