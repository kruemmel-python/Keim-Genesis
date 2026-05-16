from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from keim.analyzer import analyze_program
from keim.bytecode import compile_bytecode
from keim.parser import parse_source
from keim.runtime import RunOptions, run_program


def main() -> None:
    source = """
welt app mit 1 agenten groesse 4 4
speicher raw text startet bei '{"name":"Ada","n":3}'
speicher obj karte startet bei {}
speicher out text startet bei ""
speicher err text startet bei ""
speicher wert text startet bei ""
speicher digest text startet bei ""
speicher jetzt text startet bei ""
speicher antwort text startet bei "ok"
klasse ding:
    eigenschaft name text = "x"
    methode ping:
        speicher out setzt 1
objekt statisch ist ding
jede runde:
    zeit jetzt in speicher jetzt
    json liest speicher raw in speicher obj
    karte obj liest "name" in speicher wert
    karte obj setzt "ref" auf "dyn"
    krypto sha256 speicher wert in speicher digest
    neu ding als dyn
    versuche:
        objekt fehlt ruft ping
    fange fehler in speicher err:
        speicher out setzt 2
    sammle muell
"""
    program = parse_source(source, source_name="v42_test.keim")
    report = analyze_program(program)
    assert report.ok, report.format()

    ops = [op.opcode.value for op in compile_bytecode(program).ops]
    for required in {
        "ALLOC_MEMORY", "MAP_GET", "MAP_SET", "JSON_PARSE", "CRYPTO_HASH",
        "TIME_NOW", "TRY_BEGIN", "CATCH_BEGIN", "SPAWN_OBJECT", "COLLECT_GARBAGE",
    }:
        assert required in ops, (required, ops)

    run = run_program(program, RunOptions(rounds=1, quiet=True))
    memory = run.as_dict()["memory"]
    assert memory["wert"] == "Ada", memory
    assert len(memory["digest"]) == 64, memory
    assert "Unbekanntes Objekt" in memory["err"], memory
    assert memory["out"] == "2", memory
    assert "T" in memory["jetzt"], memory

    server_source = """
welt netz mit 1 agenten groesse 2 2
speicher antwort text startet bei "pong"
jede runde:
    server startet bei 18080 antwortet speicher antwort
"""
    server_program = parse_source(server_source, source_name="v42_server_parse.keim")
    server_ops = [op.opcode.value for op in compile_bytecode(server_program).ops]
    assert "HTTP_SERVER_START" in server_ops, server_ops

    process_source = """
welt proc mit 1 agenten groesse 2 2
speicher ausgabe text startet bei ""
jede runde:
    prozess fuehrt "python --version" in speicher ausgabe
"""
    process_program = parse_source(process_source, source_name="v42_process_parse.keim")
    process_ops = [op.opcode.value for op in compile_bytecode(process_program).ops]
    assert "PROCESS_RUN" in process_ops, process_ops

    print("[Keim] v4.2 GPL tests OK")


if __name__ == "__main__":
    main()
