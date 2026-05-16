from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import socket
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from keim.analyzer import analyze_program
from keim.bytecode import compile_bytecode
from keim.debugbus import DebugBus
from keim.errors import KeimRuntimeError
from keim.parser import parse_source
from keim.runtime import RunOptions, run_program
from keim.sandbox import SandboxPolicy


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def assert_true(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def test_generics_analyzer_runtime() -> None:
    ok_src = """
welt test mit 1 agenten groesse 4 4
speicher zahlen ist liste<ganzzahl>
speicher index ist karte<text, ganzzahl>

jede runde:
    liste zahlen fuegt 1 hinzu
    karte index setzt "ok" auf 200
"""
    program = parse_source(ok_src, source_name="<v50-generics>")
    report = analyze_program(program)
    assert_true(report.ok, report.format())
    run = run_program(program, RunOptions(rounds=1, show_every=0, quiet=True))
    assert_true(run.cpu.memory["zahlen"] == [1], "Generische Liste speichert keine Ganzzahl")
    assert_true(run.cpu.memory["index"]["ok"] == 200, "Generische Karte speichert keinen Ganzzahlwert")

    bad_src = ok_src.replace("liste zahlen fuegt 1 hinzu", 'liste zahlen fuegt "falsch" hinzu')
    bad_report = analyze_program(parse_source(bad_src, source_name="<v50-bad>"))
    assert_true(not bad_report.ok, "Generics-Typverstoß muss statisch auffallen")


def test_debugbus_events_state() -> None:
    src = """
welt test mit 1 agenten groesse 4 4
speicher running bool startet bei wahr
speicher count ist liste<ganzzahl>

jede runde:
    debug beobachtet speicher running
    debug beobachtet speicher count
    liste count fuegt 7 hinzu
    debug sendet "runde"
"""
    bus = DebugBus(maxlen=32)
    program = parse_source(src, source_name="<v50-debug>")
    run_program(program, RunOptions(rounds=1, show_every=0, quiet=True, debug_bus=bus))
    events = bus.snapshot_events()
    state = bus.snapshot_state()
    assert_true(any(e.get("kind") == "mark" and e.get("label") == "runde" for e in events), "Debug-Marke fehlt")
    assert_true(state["running"] is True, "Debug-State beobachtet Speicher nicht")
    assert_true(state["count"] == [7], "Debug-State aktualisiert Listen nicht")


def test_sandbox_denial_and_allow() -> None:
    port = _free_port()
    src = f"""
welt netz mit 1 agenten groesse 4 4
speicher antwort text startet bei "ok"
server api bei {port} parallel 1:
    route GET "/health" antwortet speicher antwort:
        speicher antwort setzt "ok"

jede runde:
    agent ruht
"""
    program = parse_source(src, source_name="<v50-sandbox>")
    try:
        run_program(program, RunOptions(rounds=1, show_every=0, quiet=True, sandbox=SandboxPolicy.from_cli("strict", [])))
    except KeimRuntimeError as exc:
        assert_true("Sandbox verweigert" in str(exc), "Sandbox-Fehlertext unerwartet")
    else:
        raise AssertionError("Strict-Sandbox muss HTTP-Dienst ohne --allow netz verweigern")

    ok = run_program(program, RunOptions(rounds=1, show_every=0, quiet=True, sandbox=SandboxPolicy.from_cli("strict", ["netz"])))
    assert_true(ok.cpu.memory["antwort"] == "ok", "Sandbox-Allow netz verhindert Dienst")


def test_grafik_audio_bytecode_runtime() -> None:
    src = """
verwende system.grafik
verwende system.audio
welt kit mit 1 agenten groesse 4 4
speicher muted bool startet bei falsch

jede runde:
    grafik farbe 20 30 40
    grafik rechteck 1 2 3 4
    audio stumm wahr
    audio signal "ok"
"""
    program = parse_source(src, source_name="<v50-kit>")
    ops = [op.opcode.value for op in compile_bytecode(program).ops]
    assert_true("GRAFIK_COMMAND" in ops and "AUDIO_COMMAND" in ops, "Kit-Bytecode fehlt")
    report = run_program(program, RunOptions(rounds=1, show_every=0, quiet=True))
    metric = report.cpu.metrics[-1]
    assert_true(metric.get("grafik:commands", 0) >= 2, "Grafik-Kommandos wurden nicht gezählt")
    assert_true(metric.get("audio:events", 0) >= 2, "Audio-Events wurden nicht gezählt")


def test_export_bin_asset_bundle() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "app.keim"
        asset = root / "config.json"
        out = root / "dist"
        src.write_text("""
welt export mit 1 agenten groesse 4 4
speicher x ganzzahl startet bei 1
jede runde:
    speicher x setzt 2
""", encoding="utf-8")
        asset.write_text(json.dumps({"ok": True}), encoding="utf-8")
        subprocess.run([sys.executable, "-m", "keim", "export-bin", str(src), "--out", str(out), "--asset", str(asset)], cwd=ROOT, check=True)
        assert_true((out / "keim_app.py").exists(), "keim_app.py fehlt")
        assert_true((out / "app.kbc.json").exists(), "app.kbc.json fehlt")
        manifest = json.loads((out / "bundle_manifest.json").read_text(encoding="utf-8"))
        assert_true(manifest["assets"][0]["path"] == "assets/config.json", "Asset-Manifest falsch")
        run = subprocess.run([sys.executable, str(out / "keim_app.py")], cwd=ROOT, text=True, capture_output=True)
        assert_true(run.returncode == 0, run.stderr + run.stdout)


if __name__ == "__main__":
    test_generics_analyzer_runtime()
    test_debugbus_events_state()
    test_sandbox_denial_and_allow()
    test_grafik_audio_bytecode_runtime()
    test_export_bin_asset_bundle()
    print("[Keim] v5.0 Sovereign Edition tests OK")
