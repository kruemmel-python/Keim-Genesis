from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .ast_nodes import Program
from .runtime import RunOptions, run_program


@dataclass(slots=True, frozen=True)
class ObservationReport:
    source: str
    rounds: int
    seed: int
    backend: str
    every: int
    rows: tuple[dict[str, Any], ...]
    final: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {"source": self.source, "rounds": self.rounds, "seed": self.seed, "backend": self.backend, "every": self.every, "rows": list(self.rows), "final": self.final}

    def format(self) -> str:
        lines = ["[Keim] Beobachtung v1.2", f"  Quelle:  {self.source}", f"  Backend: {self.backend}", f"  Runden:  {self.rounds}", f"  Schritt: {self.every}", ""]
        if not self.rows:
            lines.append("  Keine Messpunkte.")
            return "\n".join(lines)
        interesting = sorted(k for k in self.rows[-1] if k == "food_hits" or k.startswith("field_mean:") or k.startswith("trail_mean:") or k.startswith("segmented:"))
        header = ["tick", *interesting]
        lines.append("  " + " | ".join(f"{h:>18}" for h in header))
        lines.append("  " + "-+-".join("-" * 18 for _ in header))
        for row in self.rows:
            parts = [f"{int(row.get('tick', 0)):18d}"]
            for key in interesting:
                value = row.get(key, 0.0)
                if isinstance(value, int):
                    parts.append(f"{value:18d}")
                else:
                    parts.append(f"{float(value):18.6f}")
            lines.append("  " + " | ".join(parts))
        lines.append("")
        lines.append("  Mini-Trend:")
        for key in interesting:
            if key == "food_hits" or key.startswith("segmented:"):
                continue
            series = [float(row.get(key, 0.0)) for row in self.rows]
            lines.append(f"    {key:<28} {_sparkline(series)}")
        return "\n".join(lines)


def observe_program(program: Program, *, rounds: int, seed: int = 7, backend: str = "segmented", every: int = 10) -> ObservationReport:
    every = max(1, every)
    report = run_program(program, RunOptions(rounds=rounds, show_every=0, seed=seed, quiet=True, backend=backend, collect_metrics=True))
    rows = tuple(row for row in report.cpu.metrics if int(row.get("tick", 0)) % every == 0 or int(row.get("tick", 0)) == rounds)
    return ObservationReport(source=program.source_name, rounds=rounds, seed=seed, backend=report.backend, every=every, rows=rows, final=report.cpu.as_dict())


def _sparkline(values: list[float]) -> str:
    if not values:
        return ""
    blocks = "▁▂▃▄▅▆▇█"
    lo = min(values)
    hi = max(values)
    if hi <= lo + 1e-12:
        return blocks[0] * len(values)
    return "".join(blocks[max(0, min(len(blocks) - 1, int((v - lo) / (hi - lo) * (len(blocks) - 1))))] for v in values)
