from __future__ import annotations

from pathlib import Path
import platform
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "native" / "keim_vm_native.cpp"


def main() -> int:
    out_dir = ROOT / "build" / "native"
    out_dir.mkdir(parents=True, exist_ok=True)
    system = platform.system().lower()
    if system == "windows":
        cl = shutil.which("cl")
        if not cl:
            print("MSVC cl.exe nicht gefunden.")
            return 2
        out = out_dir / "keim_vm_native.dll"
        cmd = ["cl", "/O2", "/std:c++20", "/LD", str(SRC), f"/Fe:{out}"]
    else:
        cxx = shutil.which("c++") or shutil.which("g++") or shutil.which("clang++")
        if not cxx:
            print("Kein C++ Compiler gefunden.")
            return 2
        suffix = ".dylib" if system == "darwin" else ".so"
        out = out_dir / f"libkeim_vm_native{suffix}"
        cmd = [cxx, "-O3", "-std=c++20", "-shared", "-fPIC", str(SRC), "-o", str(out)]
    print(" ".join(cmd))
    subprocess.check_call(cmd, cwd=ROOT)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
