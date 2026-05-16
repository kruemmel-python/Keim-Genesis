
from __future__ import annotations

import json
import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from keim.parser import parse_source
from keim.bytecode import compile_bytecode
from keim.runtime import RunOptions, run_program
from keim.package_manager import KeimPackageManager


def test_v44_parse_bytecode_and_async() -> None:
    src = """
welt app mit 2 agenten groesse 8 4
speicher status text startet bei "bereit"
speicher task_ok bool startet bei falsch

hintergrund vorbereiten:
    speicher status setzt "fertig"

jede runde:
    erwarte vorbereiten in speicher task_ok
"""
    program = parse_source(src, source_name="<v44>")
    bytecode = compile_bytecode(program)
    ops = [op.opcode.value for op in bytecode.ops]
    assert "ASYNC_TASK" in ops
    assert "AWAIT_TASK" in ops
    report = run_program(program, RunOptions(rounds=1, show_every=0, quiet=True, backend="cpu"))
    assert report.cpu.memory["task_ok"] is True
    assert report.cpu.memory["status"] == "fertig"


def test_v44_package_manager() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        pkg = root / "pkg"
        pkg.mkdir()
        (pkg / "keim_package.json").write_text(json.dumps({"name": "demo", "version": "1.2.3"}), encoding="utf-8")
        (pkg / "modul.keim").write_text("# demo", encoding="utf-8")
        mgr = KeimPackageManager(root)
        info = mgr.install(str(pkg))
        assert info.name == "demo"
        assert mgr.list()[0].version == "1.2.3"


if __name__ == "__main__":
    test_v44_parse_bytecode_and_async()
    test_v44_package_manager()
    print("[Keim] v4.4 GPL/WebGUI/FFI foundation tests OK")
