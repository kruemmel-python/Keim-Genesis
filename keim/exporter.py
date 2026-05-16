from __future__ import annotations

from pathlib import Path
import textwrap

from .source_loader import load_source_file


def write_standalone_runner(source_file: Path, output_file: Path, *, default_rounds: int = 80, default_seed: int = 7) -> None:
    source_text = load_source_file(source_file).source
    output_file.parent.mkdir(parents=True, exist_ok=True)
    code_template = """
from __future__ import annotations

# Automatisch erzeugt von Keim Genesis v1.5.
# Ausführen:
#   python {output_name} --rounds {default_rounds}

import argparse
from pathlib import Path
import sys

_HERE = Path(__file__).resolve().parent
for _candidate in (_HERE, _HERE.parent):
    if (_candidate / "keim").exists():
        sys.path.insert(0, str(_candidate))
        break

from keim.parser import parse_source
from keim.runtime import RunOptions, run_program

KEIM_SOURCE = {source_repr}


def main() -> int:
    parser = argparse.ArgumentParser(description="Exportiertes Keim-Programm")
    parser.add_argument("--rounds", type=int, default={default_rounds})
    parser.add_argument("--show-every", type=int, default=10)
    parser.add_argument("--seed", type=int, default={default_seed})
    parser.add_argument("--backend", choices=["cpu", "vm", "fused", "circuit", "segmented"], default="segmented")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    program = parse_source(KEIM_SOURCE, source_name="<exported-keim>")
    run_program(program, RunOptions(rounds=args.rounds, show_every=args.show_every, seed=args.seed, quiet=args.quiet, backend=args.backend))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""
    output_file.write_text(textwrap.dedent(code_template.format(output_name=output_file.name, default_rounds=default_rounds, default_seed=default_seed, source_repr=repr(source_text))).lstrip(), encoding="utf-8")
