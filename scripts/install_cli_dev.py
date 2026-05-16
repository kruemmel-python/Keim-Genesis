
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if sys.platform.startswith("win"):
    target = ROOT / "keim.cmd"
    target.write_text(f'@echo off\r\n"{sys.executable}" -m keim %*\r\n', encoding="utf-8")
else:
    target = ROOT / "keim"
    target.write_text(f'#!/usr/bin/env sh\n"{sys.executable}" -m keim "$@"\n', encoding="utf-8")
    target.chmod(0o755)
print(f"[Keim] CLI-Starter geschrieben: {target}")
