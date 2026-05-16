from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from keim.foundation import ModuleGraph, IndependentVM, analyze_graph, core_bytecode, core_run, core_test, export_independent_bundle, build_lock, FoundationError


def main() -> int:
    entry = ROOT / "examples" / "sprache_v60_independent_core.keim"
    math = ROOT / "examples" / "sprache_v51_foundation_runtime.keim"
    assert entry.exists()
    assert math.exists()

    graph = ModuleGraph(entry).load()
    report = analyze_graph(graph)
    assert report.ok, report.format()
    assert "demo.main" in report.modules
    assert "demo.math" in report.modules

    bc = core_bytecode(entry)
    assert bc["format"] == "keim-independent-bytecode"
    assert bc["version"] >= 600
    assert "demo.main.main" in bc["functions"]

    result = core_run(entry)
    assert result.ok is True
    assert "Hallo Keim" in result.output
    assert result.value == 3

    tests = core_test(entry)
    assert tests["ok"] is True
    assert tests["count"] >= 2

    bad = ROOT / "build" / "v60_bad_type.keim"
    bad.parent.mkdir(exist_ok=True)
    bad.write_text("""
modul bad

funktion main() gibt ganzzahl:
    speicher zahlen ist liste<ganzzahl> setzt [1, "falsch"]
    rueckgabe 1
""".strip() + "\n", encoding="utf-8")
    try:
        core_run(bad)
    except FoundationError as exc:
        assert "liste<ganzzahl>" in str(exc)
    else:
        raise AssertionError("Typfehler wurde nicht ausgelöst")

    out = ROOT / "build" / "export_v60_core"
    if out.exists():
        shutil.rmtree(out)
    export_independent_bundle(entry, out)
    assert (out / "app.kbc.json").exists()
    assert (out / "keim_app.py").exists()
    exported = json.loads((out / "app.kbc.json").read_text(encoding="utf-8"))
    assert exported["entry"] == "demo.main"

    proj = ROOT / "build" / "v60_project"
    proj.mkdir(parents=True, exist_ok=True)
    (proj / "keim.toml").write_text("""
[projekt]
name = "v60_demo"
main = "src/main.keim"

[abhaengigkeiten]
keim.math = "1.2.0"
""".strip() + "\n", encoding="utf-8")
    lock = build_lock(proj)
    assert (proj / "keim.lock").exists()
    assert lock["packages"][0]["name"] == "keim.math"

    print("[Keim v6] Independent-Core Tests OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
