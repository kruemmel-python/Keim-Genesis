from __future__ import annotations

from pathlib import Path
from keim.training_impossible import run_training_demo

if __name__ == "__main__":
    report = run_training_demo(steps=120, out=Path("build/training_impossible_project"))
    print(report.as_dict())
