from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from keim.parser import parse_file
from keim.runtime import RunOptions, run_program


def main() -> int:
    program = parse_file(ROOT / "examples" / "sprache_v29.keim")
    run_program(program, RunOptions(rounds=60, show_every=10, backend="segmented"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
