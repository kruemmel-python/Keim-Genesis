
from pathlib import Path
import sys, tempfile
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from keim.parser import parse_source
from keim.runtime import RunOptions, run_program
from keim.bytecode import compile_bytecode
from keim.expressions import compile_agent_expression

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
with tempfile.TemporaryDirectory() as td:
    src = src.replace("__TMP__", td.replace("\\", "/"))
    program = parse_source(src)
    bc = compile_bytecode(program)
    stats = bc.stats()
    assert stats.get("op:ALLOC_TABLE_INDEX", 0) == 1
    assert stats.get("op:TABLE_QUERY", 0) == 1
    assert stats.get("op:EXPORT_IMAGE", 0) == 1
    report = run_program(program, RunOptions(rounds=2, show_every=0, quiet=True))
    assert report.cpu.memory["letzter"] == 2
    assert Path(td, "frame.png").exists()
    assert Path(td, "dash.html").exists()
print("[Keim] v4 Tests OK")
