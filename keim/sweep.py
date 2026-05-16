from __future__ import annotations

from dataclasses import dataclass
from itertools import product
import re
from typing import Any

from .parser import parse_source
from .runtime import RunOptions, run_program


@dataclass(slots=True, frozen=True)
class SweepPoint:
    params: dict[str, str]
    final: dict[str, Any]

    def score(self) -> float:
        # Einfache Default-Zielgröße: viele Futtertreffer, aber nicht blind.
        fields = self.final.get("field_means", {}) or {}
        return float(self.final.get("food_hits_total", 0)) + float(fields.get("energie", 0.0)) * 100.0 - float(fields.get("hunger", 0.0)) * 50.0

    def as_dict(self) -> dict[str, Any]:
        return {"params": self.params, "score": self.score(), "final": self.final}


@dataclass(slots=True, frozen=True)
class SweepReport:
    source_name: str
    rounds: int
    backend: str
    points: tuple[SweepPoint, ...]

    def as_dict(self) -> dict[str, Any]:
        ordered = sorted(self.points, key=lambda p: p.score(), reverse=True)
        return {
            "source": self.source_name,
            "rounds": self.rounds,
            "backend": self.backend,
            "points": [p.as_dict() for p in self.points],
            "best": ordered[0].as_dict() if ordered else None,
        }

    def format(self, *, top: int = 8) -> str:
        lines = [
            "[Keim] Sweep v1.2",
            f"  Quelle:  {self.source_name}",
            f"  Backend: {self.backend}",
            f"  Runden:  {self.rounds}",
            f"  Punkte:  {len(self.points)}",
            "",
            "  Top-Punkte:",
        ]
        ordered = sorted(self.points, key=lambda p: p.score(), reverse=True)
        if not ordered:
            lines.append("    - keine")
            return "\n".join(lines)
        for rank, point in enumerate(ordered[:top], start=1):
            params = ", ".join(f"{k}={v}" for k, v in point.params.items())
            final = point.final
            lines.append(
                f"    {rank:02d}. score={point.score():.3f} hits={final.get('food_hits_total')} "
                f"ms={final.get('ms_per_round', 0.0):.3f} | {params}"
            )
        return "\n".join(lines)


def run_sweep(source_text: str, *, source_name: str, variations: list[str], rounds: int, seed: int = 7, backend: str = "segmented", limit: int = 64) -> SweepReport:
    parsed = [_parse_variation(v) for v in variations]
    keys = [key for key, _values in parsed]
    values = [vals for _key, vals in parsed]
    points: list[SweepPoint] = []
    combos = list(product(*values)) if values else [()]
    if len(combos) > limit:
        combos = combos[:limit]

    for combo in combos:
        params = {key: value for key, value in zip(keys, combo)}
        mutated = source_text
        for key, value in params.items():
            mutated = _apply_variation(mutated, key, value)
        program = parse_source(mutated, source_name=f"{source_name}<sweep>")
        report = run_program(program, RunOptions(rounds=rounds, show_every=0, seed=seed, quiet=True, backend=backend, collect_metrics=False))
        points.append(SweepPoint(params=params, final=report.cpu.as_dict()))

    return SweepReport(source_name=source_name, rounds=rounds, backend=backend, points=tuple(points))


def _parse_variation(text: str) -> tuple[str, list[str]]:
    if "=" not in text:
        raise ValueError(f"Variation braucht '=': {text}")
    key, raw_values = text.split("=", 1)
    vals = [part.strip() for part in raw_values.split(",") if part.strip()]
    if not vals:
        raise ValueError(f"Variation enthält keine Werte: {text}")
    return key.strip(), vals


def _apply_variation(source: str, key: str, value: str) -> str:
    # Unterstützte Pfade:
    #   field:hunger=0.1,0.2
    #   trail:futter.diffuse=0.12,0.18
    #   trail:futter.decay=0.01,0.02
    #   world.agents=900,1200
    if key.startswith("field:"):
        name = re.escape(key.split(":", 1)[1])
        pattern = rf"(feld\s+{name}\s+startet\s+bei\s+)([-+]?[0-9]*[.,]?[0-9]+)"
        return _sub_once(source, pattern, rf"\g<1>{value}", key)
    if key.startswith("trail:"):
        rest = key.split(":", 1)[1]
        if "." not in rest:
            raise ValueError(f"Trail-Variation braucht .diffuse oder .decay: {key}")
        trail_name, attr = rest.split(".", 1)
        trail = re.escape(trail_name)
        if attr == "diffuse":
            pattern = rf"(spur\s+{trail}\s+startet\s+bei\s+[-+]?[0-9]*[.,]?[0-9]+\s+quellen\s+\d+\s+diffundiert\s+)([-+]?[0-9]*[.,]?[0-9]+)"
            return _sub_once(source, pattern, rf"\g<1>{value}", key)
        if attr == "decay":
            pattern = rf"(spur\s+{trail}\s+startet\s+bei\s+[-+]?[0-9]*[.,]?[0-9]+\s+quellen\s+\d+\s+diffundiert\s+[-+]?[0-9]*[.,]?[0-9]+\s+zerfaellt\s+)([-+]?[0-9]*[.,]?[0-9]+)"
            return _sub_once(source, pattern, rf"\g<1>{value}", key)
        raise ValueError(f"Unbekanntes Trail-Attribut: {attr}")
    if key == "world.agents":
        pattern = r"(welt\s+\S+\s+mit\s+)(\d+)(\s+agenten)"
        return _sub_once(source, pattern, rf"\g<1>{value}\g<3>", key)
    raise ValueError(f"Unbekannter Variationstyp: {key}")


def _sub_once(source: str, pattern: str, replacement: str, key: str) -> str:
    new, count = re.subn(pattern, replacement, source, count=1)
    if count != 1:
        raise ValueError(f"Variation {key!r} konnte im Quelltext nicht angewendet werden.")
    return new
