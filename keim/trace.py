from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
from typing import Any

from .backends.cpu import CpuReport


@dataclass(slots=True, frozen=True)
class TraceHeader:
    source_name: str
    source_sha256: str
    seed: int
    rounds: int
    backend: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "type": "header",
            "format": "keim-trace-v2",
            "source_name": self.source_name,
            "source_sha256": self.source_sha256,
            "seed": self.seed,
            "rounds": self.rounds,
            "backend": self.backend,
        }


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_trace(path: Path, *, source_text: str, source_name: str, seed: int, backend: str, report: CpuReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = TraceHeader(source_name=source_name, source_sha256=sha256_text(source_text), seed=seed, rounds=report.rounds, backend=backend)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(header.as_dict(), ensure_ascii=False) + "\n")
        for row in report.metrics:
            f.write(json.dumps({"type": "tick", **row}, ensure_ascii=False) + "\n")
        f.write(json.dumps({"type": "final", **report.as_dict()}, ensure_ascii=False) + "\n")


def read_trace(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Trace {path} Zeile {line_no} ist kein JSONL: {exc}") from exc
    return rows


def trace_header(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows or rows[0].get("type") != "header":
        raise ValueError("Trace enthält keinen Keim-Header.")
    return rows[0]


def trace_final(rows: list[dict[str, Any]]) -> dict[str, Any]:
    for row in reversed(rows):
        if row.get("type") == "final":
            return row
    raise ValueError("Trace enthält keinen finalen Report.")


def compare_final(expected: dict[str, Any], actual: dict[str, Any], *, tolerance: float = 1e-9) -> dict[str, Any]:
    keys = ["world", "rounds", "agents", "width", "height", "food_hits_total"]
    differences = []
    for key in keys:
        if expected.get(key) != actual.get(key):
            differences.append({"key": key, "expected": expected.get(key), "actual": actual.get(key)})

    for group in ("field_means", "trail_means"):
        exp_group = expected.get(group, {}) or {}
        act_group = actual.get(group, {}) or {}
        for name in sorted(set(exp_group) | set(act_group)):
            e = exp_group.get(name)
            a = act_group.get(name)
            if e is None or a is None or abs(float(e) - float(a)) > tolerance:
                differences.append({"key": f"{group}:{name}", "expected": e, "actual": a})


    exp_mem = expected.get("memory", {}) or {}
    act_mem = actual.get("memory", {}) or {}
    for name in sorted(set(exp_mem) | set(act_mem)):
        e = exp_mem.get(name)
        a = act_mem.get(name)
        if e is None or a is None or abs(float(e) - float(a)) > tolerance:
            differences.append({"key": f"memory:{name}", "expected": e, "actual": a})

    return {"ok": not differences, "differences": differences}
