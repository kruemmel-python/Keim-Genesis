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


def test_internal_linker_status() -> None:
    res = run("native-link-status", "--json")
    payload = json.loads(res.stdout)
    assert payload["external_compiler_required"] is False
    assert "elf64-linux-x86_64" in payload["targets"]
    assert "pe64-windows-x86_64" in payload["targets"]


def test_internal_linker_elf_runs_on_linux() -> None:
    out_json = ROOT / "build" / "v77_tests" / "native_subset.kbc65.json"
    out_exe = ROOT / "build" / "v77_tests" / "keim_internal_linker_elf"
    run("v65-bytecode", "examples/sprache_v65_native_subset.keim", "--out", str(out_json))
    res = run("native-link", str(out_json), "--out", str(out_exe), "--target", "elf64-linux-x86_64", "--json")
    payload = json.loads(res.stdout)
    assert payload["ok"] is True
    assert out_exe.read_bytes().startswith(b"\x7fELF")
    if sys.platform.startswith("linux"):
        native = subprocess.run([str(out_exe)], cwd=ROOT, text=True, capture_output=True, check=True)
        assert native.stdout.strip() == "42"


def test_internal_linker_pe_is_emitted() -> None:
    out_json = ROOT / "build" / "v77_tests" / "native_subset.kbc65.json"
    out_exe = ROOT / "build" / "v77_tests" / "keim_internal_linker_pe.exe"
    run("v65-bytecode", "examples/sprache_v65_native_subset.keim", "--out", str(out_json))
    res = run("native-link", str(out_json), "--out", str(out_exe), "--target", "pe64-windows-x86_64", "--json")
    payload = json.loads(res.stdout)
    assert payload["ok"] is True
    assert out_exe.read_bytes().startswith(b"MZ")
    assert out_exe.stat().st_size > 1024
    if sys.platform.startswith("win"):
        native = subprocess.run([str(out_exe)], cwd=ROOT, text=True, capture_output=True, check=True)
        assert native.stdout.strip() == "42"


def main() -> int:
    test_internal_linker_status()
    test_internal_linker_elf_runs_on_linux()
    test_internal_linker_pe_is_emitted()
    print("[Keim v7.7] Internal Native Linker Tests OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
