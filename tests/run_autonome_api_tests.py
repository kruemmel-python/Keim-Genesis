from __future__ import annotations

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

def main() -> None:
    test = ROOT / "autonome_Simulations_API" / "tests" / "test_api_smoke.py"
    subprocess.run([sys.executable, str(test)], cwd=ROOT, check=True)

if __name__ == "__main__":
    main()
