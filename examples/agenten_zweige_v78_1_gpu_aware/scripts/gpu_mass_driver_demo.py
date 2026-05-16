from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MassReference:
    count: int
    first_values: list[int]
    last_value: int
    checksum: int
    formula: str


def find_repo_root(start: Path) -> Path | None:
    """Findet den Keim-Repository-Wurzelordner robust ausgehend vom Script-Pfad."""
    for candidate in [start, *start.parents]:
        if (candidate / "keim").exists() and (candidate / "driver").exists():
            return candidate
        if (candidate / "src" / "keim").exists() and (candidate / "driver").exists():
            return candidate
    return None


def mass_reference(count: int) -> MassReference:
    """Berechnet die deterministische CPU-Referenz für alle Zweige von 1 bis count."""
    values = [(1 + branch) * (1 + branch) for branch in range(1, count + 1)]
    return MassReference(
        count=count,
        first_values=values[:16],
        last_value=values[-1] if values else 0,
        checksum=sum(values),
        formula="sum((1 + branch)^2 for branch in 1..count)",
    )


def run_command(repo_root: Path, command: list[str]) -> dict[str, Any]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    injected_candidates = [str(repo_root), str(repo_root / "src")]
    injected = os.pathsep.join(path for path in injected_candidates if Path(path).exists())
    env["PYTHONPATH"] = injected if not existing else injected + os.pathsep + existing

    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=str(repo_root),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000.0

    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()

    parsed: dict[str, Any] | None = None
    if stdout.startswith("{"):
        try:
            parsed = json.loads(stdout)
        except json.JSONDecodeError:
            parsed = None

    return {
        "command": command,
        "returncode": completed.returncode,
        "elapsed_ms": elapsed_ms,
        "stdout_json": parsed,
        "stdout": stdout if parsed is None else None,
        "stderr": stderr,
    }


def build_report(repo_root: Path | None, dll: Path, out_dir: Path, count: int) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    reference = mass_reference(count)

    report: dict[str, Any] = {
        "ok": False,
        "mode": "cpu-reference-only",
        "repo_root": str(repo_root) if repo_root else None,
        "driver_candidate": str(dll),
        "driver_exists": dll.exists(),
        "mass_reference": asdict(reference),
        "keim_gpu_driver_demo": None,
    }

    if repo_root is None:
        report["reason"] = "Keim-Repository-Wurzel konnte nicht automatisch gefunden werden."
        return report

    demo = run_command(
        repo_root,
        [
            sys.executable,
            "-m",
            "keim",
            "gpu-driver-demo",
            "--dll",
            str(dll),
            "--out",
            str(out_dir / "driver_demo"),
            "--json",
        ],
    )
    report["keim_gpu_driver_demo"] = demo

    stdout_json = demo.get("stdout_json")
    if demo["returncode"] == 0 and isinstance(stdout_json, dict):
        report["ok"] = bool(stdout_json.get("ok", False))
        report["mode"] = "gpu-driver-demo"
        report["reason"] = "Keim-v7.6/v7.8.1-Treibersmoke wurde über python -m keim gpu-driver-demo ausgeführt."
    else:
        report["reason"] = "Keim-Treibersmoke konnte nicht erfolgreich ausgeführt werden; CPU-Referenz bleibt gültig."

    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Keim v7.8.1 GPU-aware Massendemonstration mit CPU-Differentialreferenz.")
    parser.add_argument("--dll", type=Path, required=True, help="Pfad zur CC_OpenCl.dll oder libCC_OpenCL.so.")
    parser.add_argument("--out", type=Path, required=True, help="Ausgabeordner für Reports.")
    parser.add_argument("--count", type=int, default=100_000, help="Anzahl der Zweige für die Massenreferenz.")
    parser.add_argument("--repo-root", type=Path, default=None, help="Optionaler Keim-Repository-Wurzelordner.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    script_path = Path(__file__).resolve()
    repo_root = args.repo_root.resolve() if args.repo_root else find_repo_root(script_path.parent)
    dll = args.dll.resolve()
    out_dir = args.out.resolve()

    report = build_report(repo_root, dll, out_dir, args.count)

    report_path = out_dir / "gpu_mass_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
