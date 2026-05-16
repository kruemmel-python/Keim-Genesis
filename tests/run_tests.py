from __future__ import annotations

from pathlib import Path
import json
import sqlite3
import sys
import tempfile
import os

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from keim.analyzer import analyze_program
from keim.bytecode import compile_bytecode
from keim.compiler import compile_kernel_abi
from keim.gpu_validation import validate_gpu_mapping
from keim.observe import observe_program
from keim.optimizer import analyze_optimization
from keim.parser import parse_source
from keim.preprocessor import expand_macros
from keim.runtime import RunOptions, run_program
from keim.sweep import run_sweep
from keim.source_loader import load_source_file
from keim.project import build_project, new_project
from keim.trace import compare_final, read_trace, trace_final, write_trace
from keim.contracts import run_contracts, run_contracts_from_file


def assert_true(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sample_source() -> str:
    return """
welt test mit 80 agenten groesse 24 12
feld hunger startet bei 0.2
feld energie startet bei 0.8
feld fokus startet bei 0.1
spur futter startet bei 0.0 quellen 2 diffundiert 0.2 zerfaellt 0.01
spur gefahr startet bei 0.0 quellen 1 diffundiert 0.1 zerfaellt 0.02

baustein leben($h, $e):
    agent bekommt hunger $h
    agent verliert energie $e

baustein koppeln($feld, $spur, $art):
    feld $feld $art spur $spur mit 0.01

jede runde:
    agent wandert 0.10
    nutze leben(0.01, 0.005)
    nutze koppeln(fokus, gefahr, meidet)
    feld energie schreibt spur futter mit 0.005
    wenn agent riecht spur gefahr > 0.4: agent meidet spur gefahr
    wenn hunger > 0.4: agent folgt spur futter
    wenn energie < 0.2: agent ruht
    wenn agent findet futter: hunger sinkt 0.2
    wenn agent findet futter: spur futter wird staerker 0.5
    spur futter breitet sich aus
    zeige test

alle 3 runden:
    spur gefahr breitet sich aus
"""


def test_macro_expansion() -> None:
    exp = expand_macros(sample_source())
    assert_true("nutze leben" not in exp.source, "Parametrischer Baustein wurde nicht expandiert")
    assert_true("agent bekommt hunger 0.01" in exp.source, "Parameterersetzung fehlt")
    assert_true("leben" in exp.parameterized_macros, "Parametrischer Baustein nicht gemeldet")


def test_analyze_bytecode_optimizer() -> None:
    program = parse_source(sample_source())
    report = analyze_program(program)
    assert_true(report.ok, report.format())
    bytecode = compile_bytecode(program)
    stats = bytecode.stats()
    assert_true(stats["op_count"] > 15, "Bytecode hat zu wenige Ops")
    assert_true(stats["gpu_candidate_ops"] > 0, "GPU-Kandidaten fehlen")
    opt = analyze_optimization(program)
    assert_true(opt.estimated_gpu_launches_bundled <= opt.estimated_gpu_launches_naive, "Bündelung darf nicht mehr Launches erzeugen")


def test_backends_match() -> None:
    program = parse_source(sample_source())
    reports = {
        backend: run_program(program, RunOptions(rounds=6, show_every=0, quiet=True, backend=backend))
        for backend in ("cpu", "vm", "fused", "circuit", "segmented")
    }
    base = reports["cpu"].cpu.as_dict()
    for backend, report in reports.items():
        cmp = compare_final(base, report.cpu.as_dict())
        assert_true(cmp["ok"], f"{backend} weicht ab: {cmp}")


def test_trace_observe_gpu_abi() -> None:
    src = sample_source()
    program = parse_source(src, source_name="<test>")
    report = run_program(program, RunOptions(rounds=4, show_every=0, quiet=True, backend="segmented"))
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        p = Path(td) / "run.jsonl"
        write_trace(p, source_text=src, source_name="<test>", seed=7, backend=report.backend, report=report.cpu)
        final = trace_final(read_trace(p))
        assert_true(compare_final(final, report.cpu.as_dict())["ok"], "Trace final stimmt nicht")
    obs = observe_program(program, rounds=4, every=2, backend="segmented")
    assert_true(len(obs.rows) >= 2, "Observe liefert zu wenige Zeilen")
    gpu = validate_gpu_mapping(program)
    assert_true(gpu.scatter_ops >= 1, "GPU-Validierung erkennt Scatter nicht")
    abi = compile_kernel_abi(program)
    assert_true(abi["format"] == "keim-kernel-abi-v1", "ABI-Format falsch")
    assert_true("scatter_accum" in abi["buffers"], "ABI enthält keinen Scatter-Akkumulator")


def test_sweep() -> None:
    src = sample_source()
    report = run_sweep(
        src,
        source_name="<sweep-test>",
        variations=["field:hunger=0.1,0.2", "trail:futter.diffuse=0.15,0.2"],
        rounds=2,
        backend="segmented",
        limit=8,
    )
    assert_true(len(report.points) == 4, "Sweep erzeugt falsche Punktzahl")
    data = report.as_dict()
    assert_true(data["best"] is not None, "Sweep meldet keinen besten Punkt")


def test_values_imports_and_build() -> None:
    program_file = ROOT / "examples" / "sprache_v15.keim"
    loaded = load_source_file(program_file)
    assert_true("std_wander" in loaded.values, "Importierter Wert fehlt")
    assert_true("stoffwechsel" in loaded.macros, "Importierter Baustein fehlt")
    assert_true("nutze " not in loaded.source, "Bausteinaufrufe wurden nicht vollständig expandiert")
    program = parse_source(loaded.source, source_name=str(program_file))
    assert_true(analyze_program(program).ok, "v1.5-Beispiel ist nicht analysierbar")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        build = build_project(program_file, Path(td) / "build", default_rounds=2)
        assert_true((Path(build.out_dir) / "runner.py").exists(), "Build-Runner fehlt")
        files = new_project(Path(td) / "new", name="testwelt")
        assert_true("main.keim" in files, "new_project erzeugt kein main.keim")


def test_v16_control_blocks_and_v17_contracts() -> None:
    src = """
welt kontroll mit 50 agenten groesse 20 10
feld hunger startet bei 0.2
feld energie startet bei 0.5
spur futter startet bei 0.0 quellen 2 diffundiert 0.1 zerfaellt 0.01
spur gefahr startet bei 0.0 quellen 1 diffundiert 0.1 zerfaellt 0.01

jede runde:
    wiederhole 2 mal:
        agent wandert 0.01
    wenn hunger > 0.1:
        agent folgt spur futter
        energie sinkt 0.01
    sonst:
        energie waechst 0.01
    spur futter breitet sich aus
    zeige kontroll

erwarte feld hunger zwischen 0 und 1
erwarte feld energie zwischen 0 und 1
erwarte treffer >= 0
"""
    exp = expand_macros(src)
    assert_true(exp.control_expansions >= 4, "Kontrollblöcke wurden nicht expandiert")
    assert_true("wiederhole" not in exp.source, "Wiederholung blieb im Parserquelltext")
    assert_true("wenn hunger > 0.1: agent folgt spur futter" in exp.source, "Wenn-Block wurde nicht entblockt")
    program = parse_source(src)
    assert_true(analyze_program(program).ok, "Kontrollblock-Programm ist nicht analysierbar")
    report = run_contracts(src, rounds=2)
    assert_true(report.ok, report.format())


def test_v20_condition_memory_expression() -> None:
    src = """
welt sprache20 mit 60 agenten groesse 24 12
feld hunger startet bei 0.22
feld energie startet bei 0.78
feld risiko startet bei 0.0
speicher alarm startet bei 0.0
spur futter startet bei 0.0 quellen 3 diffundiert 0.12 zerfaellt 0.01
spur gefahr startet bei 0.0 quellen 2 diffundiert 0.10 zerfaellt 0.01

jede runde:
    feld risiko wird hunger * 0.65 + spur gefahr * 0.30 + speicher alarm * 0.20 - energie * 0.05
    wenn risiko > 0.10 und nicht speicher alarm > 0.95: speicher alarm waechst 0.25
    wenn speicher alarm > 0.05 oder agent riecht spur gefahr > 0.18: agent meidet spur gefahr
    wenn hunger > 0.10 und energie > 0.20: agent folgt spur futter
    wenn agent findet futter oder speicher alarm > 0.80: hunger sinkt 0.10
    speicher alarm sinkt 0.03
    spur futter breitet sich aus

erwarte feld risiko zwischen 0 und 1
erwarte speicher alarm zwischen 0 und 1
erwarte treffer >= 0
"""
    program = parse_source(src)
    analysis = analyze_program(program)
    assert_true(analysis.ok, analysis.format())
    assert_true(analysis.expression_count == 1, "v2.0 Ausdrucksfeld wurde nicht gezählt")
    assert_true(analysis.boolean_condition_count >= 3, "v2.0 Bool-Bedingungen wurden nicht gezählt")
    bytecode = compile_bytecode(program)
    stats = bytecode.stats()
    assert_true(stats.get("op:FIELD_COMPUTE", 0) == 1, "FIELD_COMPUTE fehlt im Bytecode")
    assert_true(stats.get("op:ALLOC_MEMORY", 0) == 1, "ALLOC_MEMORY fehlt im Bytecode")
    reports = {
        backend: run_program(program, RunOptions(rounds=5, show_every=0, quiet=True, backend=backend))
        for backend in ("cpu", "vm", "fused", "circuit", "segmented")
    }
    base = reports["cpu"].cpu.as_dict()
    for backend, report in reports.items():
        cmp = compare_final(base, report.cpu.as_dict())
        assert_true(cmp["ok"], f"v2.0 {backend} weicht ab: {cmp}")
    contract_report = run_contracts(src, rounds=5)
    assert_true(contract_report.ok, contract_report.format())


def test_v23_rules_blocks_expression_functions() -> None:
    src = """
welt sprache23 mit 70 agenten groesse 28 12
feld hunger startet bei 0.24
feld energie startet bei 0.72
feld risiko startet bei 0.0
speicher alarm startet bei 0.0
spur futter startet bei 0.0 quellen 3 diffundiert 0.12 zerfaellt 0.01
spur gefahr startet bei 0.0 quellen 2 diffundiert 0.10 zerfaellt 0.02

regel stoffwechsel:
    feld risiko wird clamp(mix(hunger, spur gefahr, 0.35) + speicher alarm * 0.20 - energie * 0.04)
    wenn risiko > 0.18:
        speicher alarm waechst 0.22
        agent meidet spur gefahr
    sonst:
        speicher alarm sinkt 0.02
        energie waechst 0.002

regel suche:
    wiederhole 2 mal:
        agent wandert 0.06
    wenn hunger > 0.12 und energie > 0.18:
        agent folgt spur futter

jede runde:
    rufe stoffwechsel
    rufe suche
    wenn agent findet futter:
        hunger sinkt 0.12
        energie waechst 0.04
    spur futter breitet sich aus

alle 4 runden:
    spur gefahr breitet sich aus

erwarte feld risiko zwischen 0 und 1
erwarte speicher alarm zwischen 0 und 1
erwarte treffer >= 0
"""
    program = parse_source(src)
    analysis = analyze_program(program)
    assert_true(analysis.ok, analysis.format())
    assert_true(analysis.rule_count == 2, "v2.3 Regeln wurden nicht gezählt")
    assert_true(analysis.structured_block_count >= 3, "v2.3 Strukturblöcke wurden nicht gezählt")
    bytecode = compile_bytecode(program)
    stats = bytecode.stats()
    assert_true(stats.get("op:BEGIN_RULE", 0) == 2, "BEGIN_RULE fehlt im Bytecode")
    assert_true(stats.get("op:CALL_RULE", 0) == 2, "CALL_RULE fehlt im Bytecode")
    assert_true(stats.get("op:BEGIN_IF", 0) >= 3, "BEGIN_IF fehlt im Bytecode")
    assert_true(stats.get("op:BEGIN_REPEAT", 0) == 1, "BEGIN_REPEAT fehlt im Bytecode")
    reports = {
        backend: run_program(program, RunOptions(rounds=5, show_every=0, quiet=True, backend=backend))
        for backend in ("cpu", "vm", "fused", "circuit", "segmented")
    }
    base = reports["cpu"].cpu.as_dict()
    for backend, report in reports.items():
        cmp = compare_final(base, report.cpu.as_dict())
        assert_true(cmp["ok"], f"v2.3 {backend} weicht ab: {cmp}")
    contract_report = run_contracts(src, rounds=5)
    assert_true(contract_report.ok, contract_report.format())


def test_v26_functions_aggregates_events() -> None:
    src = """
funktion risikoformel(h, g, alarm, e) = clamp(mix(h, g, 0.35) + alarm * 0.20 - e * 0.04)
funktion suchdruck(h, futter, gefahr) = clamp(h + max(futter - gefahr, 0) * 0.25)

welt sprache26 mit 80 agenten groesse 28 12
feld hunger startet bei 0.24
feld energie startet bei 0.74
feld risiko startet bei 0.0
feld druck startet bei 0.0
speicher alarm startet bei 0.0
speicher hunger_mittel startet bei 0.0
speicher risiko_max startet bei 0.0
spur futter startet bei 0.0 quellen 4 diffundiert 0.12 zerfaellt 0.01
spur gefahr startet bei 0.0 quellen 2 diffundiert 0.09 zerfaellt 0.02

regel messen:
    speicher hunger_mittel liest mittel feld hunger
    speicher risiko_max liest max feld risiko

regel denken:
    feld risiko wird risikoformel(hunger, spur gefahr, speicher alarm, energie)
    feld druck wird suchdruck(hunger, spur futter, spur gefahr)

ereignis alarmstart wenn speicher risiko_max > 0.20:
    speicher alarm setzt 1.0
    agent meidet spur gefahr

jede runde:
    rufe messen
    rufe denken
    wenn druck > 0.10:
        agent folgt spur futter
    sonst:
        agent wandert 0.04
    wenn agent findet futter:
        hunger sinkt 0.12
        energie waechst 0.04
    hunger waechst 0.006
    speicher alarm sinkt 0.03
    spur futter breitet sich aus

alle 4 runden:
    spur gefahr breitet sich aus

erwarte feld risiko zwischen 0 und 1
erwarte feld druck zwischen 0 und 1
erwarte speicher alarm zwischen 0 und 1
erwarte speicher hunger_mittel zwischen 0 und 1
erwarte speicher risiko_max zwischen 0 und 1
"""
    program = parse_source(src)
    analysis = analyze_program(program)
    assert_true(analysis.ok, analysis.format())
    assert_true(analysis.function_count == 2, "v2.6 Funktionen wurden nicht gezählt")
    assert_true(analysis.aggregate_count >= 2, "v2.6 Aggregate wurden nicht gezählt")
    assert_true(analysis.event_count == 1, "v2.6 Ereignisse wurden nicht gezählt")
    bytecode = compile_bytecode(program)
    stats = bytecode.stats()
    assert_true(stats.get("op:DEFINE_FUNCTION", 0) == 2, "DEFINE_FUNCTION fehlt im Bytecode")
    assert_true(stats.get("op:MEMORY_AGGREGATE", 0) >= 2, "MEMORY_AGGREGATE fehlt im Bytecode")
    assert_true(stats.get("op:BEGIN_EVENT", 0) == 1, "BEGIN_EVENT fehlt im Bytecode")
    reports = {
        backend: run_program(program, RunOptions(rounds=5, show_every=0, quiet=True, backend=backend))
        for backend in ("cpu", "vm", "fused", "circuit", "segmented")
    }
    base = reports["cpu"].cpu.as_dict()
    for backend, report in reports.items():
        cmp = compare_final(base, report.cpu.as_dict())
        assert_true(cmp["ok"], f"v2.6 {backend} weicht ab: {cmp}")
    contract_report = run_contracts(src, rounds=5)
    assert_true(contract_report.ok, contract_report.format())


def test_v29_tables_database_objects() -> None:
    # ignore_cleanup_errors=True hilft bei Windows-Race-Conditions
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db_path = Path(td) / "keim_v29.sqlite"
        src = f"""
welt datenraum mit 40 agenten groesse 20 10
feld hunger startet bei 0.30
feld risiko startet bei 0.0
feld energie startet bei 0.8
speicher risiko_max startet bei 0.0
speicher alarm startet bei 0.0
spur gefahr startet bei 0.0 quellen 1 diffundiert 0.05 zerfaellt 0.01

funktion score(h, g, e) = clamp(h * 0.7 + g * 0.4 - e * 0.1)

tabelle messungen mit tick zahl, risiko zahl, alarm zahl, modus text
datenbank log bei "{db_path}"

klasse waechter:
    eigenschaft schwelle = 0.05
    methode pruefe:
        wenn speicher risiko_max > selbst.schwelle:
            speicher alarm setzt 1.0
            agent meidet spur gefahr

objekt alarmwache ist waechter mit schwelle=0.04

regel messen:
    feld risiko wird score(hunger, spur gefahr, energie)
    speicher risiko_max liest max feld risiko
    tabelle messungen fuegt tick=zeit risiko=speicher.risiko_max alarm=speicher.alarm modus=aktiv ein

jede runde:
    rufe messen
    objekt alarmwache ruft pruefe
    datenbank log speichert tabelle messungen
    hunger waechst 0.01
    spur gefahr breitet sich aus
"""
        program = parse_source(src)
        analysis = analyze_program(program)
        assert_true(analysis.ok, analysis.format())
        assert_true(analysis.table_count == 1, "v2.9 Tabelle wurde nicht gezählt")
        assert_true(analysis.database_count == 1, "v2.9 Datenbank wurde nicht gezählt")
        assert_true(analysis.class_count == 1, "v2.9 Klasse wurde nicht gezählt")
        assert_true(analysis.object_count == 1, "v2.9 Objekt wurde nicht gezählt")
        
        bytecode = compile_bytecode(program)
        stats = bytecode.stats()
        assert_true(stats.get("op:ALLOC_TABLE", 0) == 1, "ALLOC_TABLE fehlt im Bytecode")
        assert_true(stats.get("op:TABLE_INSERT", 0) == 1, "TABLE_INSERT fehlt im Bytecode")
        assert_true(stats.get("op:ALLOC_DATABASE", 0) == 1, "ALLOC_DATABASE fehlt im Bytecode")
        assert_true(stats.get("op:DATABASE_SAVE", 0) == 1, "DATABASE_SAVE fehlt im Bytecode")
        assert_true(stats.get("op:DEFINE_CLASS", 0) == 1, "DEFINE_CLASS fehlt im Bytecode")
        assert_true(stats.get("op:ALLOC_OBJECT", 0) == 1, "ALLOC_OBJECT fehlt im Bytecode")
        assert_true(stats.get("op:CALL_METHOD", 0) == 1, "CALL_METHOD fehlt im Bytecode")
        
        report = run_program(program, RunOptions(rounds=4, show_every=0, quiet=True, backend="cpu"))
        assert_true(report.cpu.memory["alarm"] >= 0.0, "Objektmethode hat keinen gültigen Speicherzustand erzeugt")
        assert_true(db_path.exists(), "SQLite-Datenbank wurde nicht erzeugt")
        
        # Geändertes Handling der SQLite Verbindung zur Vermeidung von Sperren
        con = sqlite3.connect(db_path)
        try:
            cursor = con.execute("select count(*) from messungen")
            rows = cursor.fetchone()[0]
        finally:
            con.close() # Explizite Freigabe vor Ende des Context-Managers
            
        assert_true(rows == 4, f"SQLite-Export sollte 4 Zeilen enthalten, nicht {rows}")



def test_v30_types_inheritance_dynamic_native() -> None:
    src = """
welt genesis mit 3 agenten groesse 10 6
feld aktiv bool startet bei wahr
feld alter ganzzahl startet bei 1
feld hunger zahl startet bei 0.20
speicher alarm bool startet bei falsch
speicher zaehler ganzzahl startet bei 0
spur futter startet bei 0.0 quellen 1 diffundiert 0.05 zerfaellt 0.01

klasse waechter:
    eigenschaft schwelle zahl = 0.5
    methode pruefe:
        wenn hunger > selbst.schwelle:
            speicher alarm setzt wahr

klasse spezial_waechter ist waechter:
    eigenschaft name text = alpha
    methode pruefe:
        wenn alter >= 1:
            speicher alarm setzt wahr

objekt w ist spezial_waechter

jede runde:
    erzeuge 2 agenten
    rufe w.pruefe
    wenn speicher alarm == wahr:
        loesche 1 agenten
    alter waechst 1
    hunger waechst 0.05
    spur futter breitet sich aus
"""
    program = parse_source(src)
    analysis = analyze_program(program)
    assert_true(analysis.ok, analysis.format())
    bytecode = compile_bytecode(program)
    stats = bytecode.stats()
    assert_true(stats.get("op:SPAWN_AGENTS", 0) == 1, "SPAWN_AGENTS fehlt im Bytecode")
    assert_true(stats.get("op:KILL_AGENTS", 0) == 1, "KILL_AGENTS fehlt im Bytecode")
    report = run_program(program, RunOptions(rounds=3, show_every=0, quiet=True, backend="native"))
    assert_true(report.backend == "native", "Native-Backend wurde nicht ausgewählt")
    assert_true(report.cpu.agents == 6, f"Dynamische Agentenzahl falsch: {report.cpu.agents}")
    assert_true(report.cpu.memory["alarm"] is True, "Bool-Speicher wurde nicht typisiert gesetzt")



def test_v40_batteries_native_bridge() -> None:
    src = """
welt v40 mit 8 agenten groesse 8 6
feld energie ganzzahl startet bei 1
feld signal startet bei 0.1
speicher treffer liste mit ganzzahl startet bei []
speicher letzter ganzzahl startet bei 0
speicher popped ganzzahl startet bei 0
spur futter startet bei 0.0 quellen 1 diffundiert 0.1 zerfaellt 0.01
tabelle messungen mit tick ganzzahl, energie zahl, tag text
index messungen auf tick
tabelle route mit schritt ganzzahl, x ganzzahl, y ganzzahl, kosten zahl
klasse waechter:
    eigenschaft schwelle zahl = 0.2
    methode pruefe:
        wenn signal > selbst.schwelle:
            speicher letzter setzt 1
klasse spezial_waechter ist waechter:
    eigenschaft name text = "beta"
    methode pruefe:
        wenn signal > selbst.schwelle:
            speicher letzter setzt 2
jede runde:
    feld signal wird clamp(signal + perlin(energie, signal, 4) * 0.02)
    liste treffer haengt 1 an
    liste treffer nimmt letztes in speicher popped
    tabelle messungen fuegt tick=zeit energie=feld.energie tag="x" ein
    tabelle messungen sucht tick == 1 in speicher treffer
    neu spezial_waechter als dyn_alarm mit schwelle=0.05
    objekt dyn_alarm ruft pruefe
    pfad von 0 0 nach 2 2 mit spur futter in tabelle route
    bild schreibt png "__TMP__/frame.png" aus spur futter
    dashboard startet bei "__TMP__/dash.html"
    loesche objekt dyn_alarm
    sammle muell
    spur futter breitet sich aus
"""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        src = src.replace("__TMP__", td.replace("\\", "/"))
        program = parse_source(src)
        analysis = analyze_program(program)
        assert_true(analysis.ok, analysis.format())
        bytecode = compile_bytecode(program)
        stats = bytecode.stats()
        assert_true(stats.get("op:ALLOC_TABLE_INDEX", 0) == 1, "ALLOC_TABLE_INDEX fehlt")
        assert_true(stats.get("op:TABLE_QUERY", 0) == 1, "TABLE_QUERY fehlt")
        assert_true(stats.get("op:EXPORT_IMAGE", 0) == 1, "EXPORT_IMAGE fehlt")
        report = run_program(program, RunOptions(rounds=2, show_every=0, quiet=True))
        assert_true(report.cpu.memory["letzter"] == 2, "Vererbte Methode/Override griff nicht")
        assert_true(Path(td, "frame.png").exists(), "PNG-Export fehlt")
        assert_true(Path(td, "dash.html").exists(), "Dashboard fehlt")


def test_v41_kernel_abi_markers() -> None:
    src = """
welt nativecheck mit 16 agenten groesse 8 8
feld energie startet bei 0.5
spur futter startet bei 0.0 quellen 1 diffundiert 0.1 zerfaellt 0.01
jede runde:
    energie waechst 0.1
    wenn energie > 0.5: energie sinkt 0.05
    spur futter breitet sich aus
"""
    program = parse_source(src)
    abi = compile_kernel_abi(program)
    assert_true(abi["format_version"] == "1.2", "Kernel-ABI v1.2 fehlt")
    assert_true(abi["layout"]["agents"]["kind"] == "SoA", "SoA-Layout fehlt")
    assert_true(any(b["parallel"] for b in abi["kernel_bundles_v12"]), "Kernel-Bundles markieren keine Parallelität")
    assert_true("keim_jit_compile_affine2" in abi["jit"]["entrypoints"], "JIT-Haken fehlen")



def test_v42_gpl_core_features() -> None:
    src = """
welt app mit 1 agenten groesse 4 4
speicher raw text startet bei '{"name":"Ada","n":3}'
speicher obj karte startet bei {}
speicher out text startet bei ""
speicher err text startet bei ""
speicher wert text startet bei ""
speicher digest text startet bei ""
speicher jetzt text startet bei ""
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
    program = parse_source(src, source_name="v42_core.keim")
    analysis = analyze_program(program)
    assert_true(analysis.ok, analysis.format())
    ops = [op.opcode.value for op in compile_bytecode(program).ops]
    for op in ("MAP_GET", "MAP_SET", "JSON_PARSE", "CRYPTO_HASH", "TIME_NOW", "TRY_BEGIN", "CATCH_BEGIN"):
        assert_true(op in ops, f"v4.2 Opcode fehlt: {op}")
    report = run_program(program, RunOptions(rounds=1, show_every=0, quiet=True))
    memory = report.cpu.as_dict()["memory"]
    assert_true(memory["wert"] == "Ada", "Karte/JSON-Lesezugriff fehlgeschlagen")
    assert_true(len(memory["digest"]) == 64, "SHA256-Hash fehlt")
    assert_true("Unbekanntes Objekt" in memory["err"], "versuche/fange hat Fehler nicht gefangen")
    assert_true("T" in memory["jetzt"], "system.zeit hat keinen ISO-Zeitwert geschrieben")


def test_autonome_simulations_api_programm() -> None:
    from autonome_Simulations_API.sim_engine import SimulationConfig, SimulationEngine

    program = load_source_file(ROOT / "autonome_Simulations_API" / "keim_sources" / "autonome_api.keim")
    parsed = parse_source(program.source, source_name=program.source_name, preprocess=False)
    report = analyze_program(parsed)
    assert_true(report.ok, report.format())

    engine = SimulationEngine(SimulationConfig(agent_count=32, width=12, height=8, native_enabled=False, running=False))
    before = engine.snapshot()["round"]
    engine.step(2)
    after = engine.snapshot()["round"]
    assert_true(after == before + 2, "Autonome API Engine steppt nicht deterministisch")
    control = engine.apply_control({"wind_x": 2, "energy_delta": -0.002})
    assert_true(control["wind_x"] == 2, "Autonome API Control-Update fehlgeschlagen")
    engine.close()


def test_v43_internal_http_router() -> None:
    import subprocess
    subprocess.run([sys.executable, str(ROOT / "tests" / "run_v43_http_tests.py")], cwd=ROOT, check=True)


def test_v44_gpl_gui_ffi_foundation() -> None:
    import subprocess
    subprocess.run([sys.executable, str(ROOT / "tests" / "run_v44_gpl_gui_ffi_tests.py")], cwd=ROOT, check=True)

def test_v50_sovereign_edition() -> None:
    import subprocess
    subprocess.run([sys.executable, str(ROOT / "tests" / "run_v50_sovereign_tests.py")], cwd=ROOT, check=True)


def test_v60_independent_core() -> None:
    import subprocess
    subprocess.run([sys.executable, str(ROOT / "tests" / "run_v60_independent_core_tests.py")], cwd=ROOT, check=True)

def test_v67_enterprise_complete() -> None:
    import subprocess
    subprocess.run([sys.executable, "-S", str(ROOT / "tests" / "run_v67_enterprise_complete_tests.py")], cwd=ROOT, check=True)

def test_v64_professional_core() -> None:
    import subprocess
    subprocess.run([sys.executable, "-S", str(ROOT / "tests" / "run_v64_professional_tests.py")], cwd=ROOT, check=True)


def test_v61_compiler_runtime_core() -> None:
    import subprocess
    subprocess.run([sys.executable, "-S", str(ROOT / "tests" / "run_v61_compiler_runtime_tests.py")], cwd=ROOT, check=True)


def test_v63_enterprise_infrastructure() -> None:
    import subprocess
    subprocess.run([sys.executable, str(ROOT / "tests" / "run_v63_enterprise_tests.py")], cwd=ROOT, check=True)



def test_v65_native_generics_binary() -> None:
    import os
    import subprocess
    env = os.environ.copy()
    # Full repository test runs must be reproducible and must not inherit a
    # previous shell's strict native-toolchain probe. Users can still request
    # a hard native test explicitly through KEIM_NATIVE_STRICT_SUITE=1.
    if env.get("KEIM_NATIVE_STRICT_SUITE") == "1":
        env["KEIM_NATIVE_STRICT"] = "1"
    else:
        env["KEIM_NATIVE_STRICT"] = "0"
    subprocess.run([sys.executable, "-S", str(ROOT / "tests" / "run_v65_native_generics_binary_tests.py")], cwd=ROOT, check=True, env=env)


def test_v68_wasm_heap_runtime() -> None:
    import subprocess
    subprocess.run([sys.executable, "-S", str(ROOT / "tests" / "run_v68_wasm_heap_runtime_tests.py")], cwd=ROOT, check=True)


def test_v72_training_impossible() -> None:
    import subprocess
    subprocess.run([sys.executable, "-S", str(ROOT / "tests" / "run_v72_training_impossible_tests.py")], cwd=ROOT, check=True)


def test_v76_gpu_driver_execution() -> None:
    import subprocess
    subprocess.run([sys.executable, str(ROOT / "tests" / "run_v76_gpu_driver_execution_tests.py")], cwd=ROOT, check=True)


def test_v764_linux_gpu_driver_support() -> None:
    import subprocess
    subprocess.run([sys.executable, "-S", str(ROOT / "tests" / "run_v764_linux_gpu_driver_tests.py")], cwd=ROOT, check=True)



def test_v77_internal_native_linker() -> None:
    import subprocess
    subprocess.run([sys.executable, "-S", str(ROOT / "tests" / "run_v77_internal_linker_tests.py")], cwd=ROOT, check=True)


def test_v78_full_exe_packager() -> None:
    import subprocess
    subprocess.run([sys.executable, "-S", str(ROOT / "tests" / "run_v78_full_exe_packager_tests.py")], cwd=ROOT, check=True)


def test_v781_gpu_aware_exe_packager() -> None:
    import subprocess
    subprocess.run([sys.executable, "-S", str(ROOT / "tests" / "run_v781_gpu_aware_exe_packager_tests.py")], cwd=ROOT, check=True)


def test_v782_self_bootstrap_launcher() -> None:
    import subprocess
    subprocess.run([sys.executable, "-S", str(ROOT / "tests" / "run_v782_self_bootstrap_launcher_tests.py")], cwd=ROOT, check=True)


def test_v783_real_self_bootstrap_launcher() -> None:
    import subprocess
    subprocess.run([sys.executable, "-S", str(ROOT / "tests" / "run_v783_real_self_bootstrap_launcher_tests.py")], cwd=ROOT, check=True)


def test_v784_project_web_overlay() -> None:
    import subprocess
    subprocess.run([sys.executable, "-S", str(ROOT / "tests" / "run_v784_project_web_overlay_tests.py")], cwd=ROOT, check=True)

def main() -> int:
    test_macro_expansion()
    test_analyze_bytecode_optimizer()
    test_backends_match()
    test_trace_observe_gpu_abi()
    test_sweep()
    test_values_imports_and_build()
    test_v16_control_blocks_and_v17_contracts()
    test_v20_condition_memory_expression()
    test_v23_rules_blocks_expression_functions()
    test_v26_functions_aggregates_events()
    test_v29_tables_database_objects()
    test_v30_types_inheritance_dynamic_native()
    test_v40_batteries_native_bridge()
    test_v41_kernel_abi_markers()
    test_v42_gpl_core_features()
    test_autonome_simulations_api_programm()
    test_v43_internal_http_router()
    test_v44_gpl_gui_ffi_foundation()
    test_v50_sovereign_edition()
    test_v60_independent_core()
    test_v72_training_impossible()
    test_v68_wasm_heap_runtime()
    test_v65_native_generics_binary()
    test_v63_enterprise_infrastructure()
    test_v61_compiler_runtime_core()
    test_v76_gpu_driver_execution()
    test_v764_linux_gpu_driver_support()
    test_v77_internal_native_linker()
    test_v78_full_exe_packager()
    test_v781_gpu_aware_exe_packager()
    test_v782_self_bootstrap_launcher()
    test_v783_real_self_bootstrap_launcher()
    print("[Keim] Tests OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
