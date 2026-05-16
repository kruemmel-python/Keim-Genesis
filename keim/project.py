from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import shutil
from typing import Any

from .source_loader import load_source_file


@dataclass(slots=True, frozen=True)
class BuildReport:
    out_dir: str
    files: tuple[str, ...]
    manifest: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {"out_dir": self.out_dir, "files": list(self.files), "manifest": self.manifest}

    def format(self) -> str:
        lines = [
            "[Keim] Build v2.6",
            f"  Ziel:   {self.out_dir}",
            f"  Name:   {self.manifest['name']}",
            f"  Quelle: {self.manifest['source']}",
            "  Dateien:",
        ]
        for f in self.files:
            lines.append(f"    - {f}")
        return "\n".join(lines)


def build_project(source_file: str | Path, out_dir: str | Path, *, name: str | None = None, default_rounds: int = 80) -> BuildReport:
    source_file = Path(source_file)
    out_dir = Path(out_dir)
    loaded = load_source_file(source_file)

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    project_name = name or source_file.stem
    (out_dir / "expanded.keim").write_text(loaded.source, encoding="utf-8")
    (out_dir / "runner.py").write_text(_runner_source(project_name, default_rounds), encoding="utf-8")
    manifest = {
        "format": "keim-build-v1",
        "name": project_name,
        "source": str(source_file),
        "default_rounds": default_rounds,
        "imports": list(loaded.imports),
        "values": loaded.values,
        "macros": list(loaded.macros),
        "parameterized_macros": list(loaded.parameterized_macros),
    }
    (out_dir / "keim_build.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "README.txt").write_text(
        "Ausführen:\n  python runner.py --rounds 80 --backend segmented\n\n"
        "Die Datei expanded.keim ist eine vollständig expandierte Keim-Quelle ohne Imports und ohne Bausteinaufrufe.\n",
        encoding="utf-8",
    )
    return BuildReport(
        out_dir=str(out_dir),
        files=("expanded.keim", "runner.py", "keim_build.json", "README.txt"),
        manifest=manifest,
    )


def new_project(out_dir: str | Path, *, name: str = "mein_keim") -> tuple[str, ...]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    src = out_dir / "main.keim"
    if not src.exists():
        src.write_text(_starter_source(name), encoding="utf-8")
    (out_dir / "run.bat").write_text("python -m keim run main.keim --backend segmented --rounds 80 --show-every 20\n", encoding="utf-8")
    (out_dir / "README.md").write_text(
        f"# {name}\n\nKeim-Projekt.\n\n```powershell\npython -m keim run main.keim --backend segmented\n```\n",
        encoding="utf-8",
    )
    return ("main.keim", "run.bat", "README.md")


def _runner_source(name: str, default_rounds: int) -> str:
    return f'''from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
for _candidate in (ROOT, ROOT.parent, ROOT.parent.parent, ROOT.parent.parent.parent):
    if (_candidate / "keim").exists():
        sys.path.insert(0, str(_candidate))
        break

from keim.parser import parse_file
from keim.runtime import RunOptions, run_program


def main() -> int:
    parser = argparse.ArgumentParser(prog="{name}")
    parser.add_argument("--rounds", type=int, default={default_rounds})
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--backend", default="segmented", choices=["cpu", "vm", "fused", "circuit", "segmented"])
    parser.add_argument("--show-every", type=int, default=20)
    args = parser.parse_args()
    program = parse_file(ROOT / "expanded.keim")
    run_program(program, RunOptions(rounds=args.rounds, seed=args.seed, backend=args.backend, show_every=args.show_every))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def _starter_source(name: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name).strip("_") or "welt"
    return f'''# {name}: Keim-Starterprojekt

verwende "basis"

wert agenten = 500
wert breite = 80
wert hoehe = 25
wert hunger_start = 0.20
wert energie_start = 0.90

welt {safe} mit $agenten agenten groesse $breite $hoehe
feld hunger startet bei $hunger_start
feld energie startet bei $energie_start
spur futter startet bei 0.0 quellen 12 diffundiert 0.16 zerfaellt 0.012
spur ruhe startet bei 0.0 quellen 4 diffundiert 0.12 zerfaellt 0.01

jede runde:
    agent wandert 0.08
    nutze stoffwechsel(0.006, 0.004)
    nutze suche(hunger, futter, 0.50)
    wenn agent findet futter: hunger sinkt 0.35
    wenn agent findet futter: energie waechst 0.20
    feld energie schreibt spur ruhe mit 0.004
    spur futter breitet sich aus
    zeige {safe}
'''
