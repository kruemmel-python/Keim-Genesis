from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import json
from typing import Any, Literal

from .errors import KeimSyntaxError
from .parser import parse_source
from .preprocessor import expand_macros
from .runtime import RunOptions, run_program
from .source_loader import load_raw_with_imports


@dataclass(slots=True, frozen=True)
class Contract:
    kind: Literal["field_range", "trail_range", "memory_range", "hits_compare"]
    name: str
    op: str
    a: float
    b: float | None = None
    source: str = ""


@dataclass(slots=True, frozen=True)
class ContractResult:
    contract: Contract
    value: float
    ok: bool
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract": asdict(self.contract),
            "value": self.value,
            "ok": self.ok,
            "message": self.message,
        }


@dataclass(slots=True, frozen=True)
class ContractReport:
    source_name: str
    rounds: int
    backend: str
    ok: bool
    results: tuple[ContractResult, ...]
    stats: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source_name,
            "rounds": self.rounds,
            "backend": self.backend,
            "ok": self.ok,
            "results": [r.as_dict() for r in self.results],
            "stats": self.stats,
        }

    def format(self) -> str:
        lines = [
            "[Keim] Sprachtests/Kontrakte v2.0",
            f"  Quelle:  {self.source_name}",
            f"  Backend: {self.backend}",
            f"  Runden:  {self.rounds}",
            f"  Status:  {'OK' if self.ok else 'FEHLER'}",
            "",
        ]
        if not self.results:
            lines.append("  Keine erwarte-Zeilen gefunden.")
            return "\n".join(lines)
        for result in self.results:
            marker = "OK" if result.ok else "FAIL"
            lines.append(f"  {marker:4} {result.message}")
        return "\n".join(lines)


def run_contracts_from_file(path: Path, *, rounds: int = 30, seed: int = 7, backend: str = "segmented") -> ContractReport:
    source, _imports = load_raw_with_imports(path)
    return run_contracts(source, source_name=str(path), rounds=rounds, seed=seed, backend=backend)


def run_contracts(source: str, *, source_name: str = "<string>", rounds: int = 30, seed: int = 7, backend: str = "segmented") -> ContractReport:
    expansion = expand_macros(source)
    contracts = tuple(parse_contract(line) for line in expansion.contracts)
    program = parse_source(expansion.source, source_name=source_name)
    report = run_program(program, RunOptions(rounds=rounds, seed=seed, show_every=0, quiet=True, backend=backend))
    stats = report.cpu.as_dict()
    results = tuple(_eval_contract(contract, stats) for contract in contracts)
    ok = all(result.ok for result in results)
    return ContractReport(source_name=source_name, rounds=rounds, backend=report.backend, ok=ok, results=results, stats=stats)


def parse_contract(line: str) -> Contract:
    words = line.split()
    if not words or words[0] != "erwarte":
        raise KeimSyntaxError("Kontrakt muss mit 'erwarte' beginnen.", 0, line)

    match words:
        case ["erwarte", "feld", name, "zwischen", lo, "und", hi]:
            return Contract(kind="field_range", name=name, op="between", a=_num(lo, line), b=_num(hi, line), source=line)
        case ["erwarte", "spur", name, "zwischen", lo, "und", hi]:
            return Contract(kind="trail_range", name=name, op="between", a=_num(lo, line), b=_num(hi, line), source=line)
        case ["erwarte", "speicher", name, "zwischen", lo, "und", hi]:
            return Contract(kind="memory_range", name=name, op="between", a=_num(lo, line), b=_num(hi, line), source=line)
        case ["erwarte", "treffer", op, value] if op in {">", ">=", "<", "<=", "==", "!="}:
            return Contract(kind="hits_compare", name="treffer", op=op, a=_num(value, line), b=None, source=line)
        case _:
            raise KeimSyntaxError(
                "Unbekannter Kontrakt. Beispiele: 'erwarte feld hunger zwischen 0 und 1', 'erwarte speicher alarm zwischen 0 und 1' oder 'erwarte treffer >= 1'.",
                0,
                line,
            )


def _eval_contract(contract: Contract, stats: dict[str, Any]) -> ContractResult:
    if contract.kind == "field_range":
        means = stats.get("field_means", {})
        value = float(means.get(contract.name, float("nan")))
        ok = _between(value, contract.a, contract.b)
        return ContractResult(contract, value, ok, f"feld {contract.name} mittel={value:.6g} zwischen {contract.a:g} und {contract.b:g}")
    if contract.kind == "trail_range":
        means = stats.get("trail_means", {})
        value = float(means.get(contract.name, float("nan")))
        ok = _between(value, contract.a, contract.b)
        return ContractResult(contract, value, ok, f"spur {contract.name} mittel={value:.6g} zwischen {contract.a:g} und {contract.b:g}")
    if contract.kind == "memory_range":
        mem = stats.get("memory", {})
        value = float(mem.get(contract.name, float("nan")))
        ok = _between(value, contract.a, contract.b)
        return ContractResult(contract, value, ok, f"speicher {contract.name}={value:.6g} zwischen {contract.a:g} und {contract.b:g}")
    if contract.kind == "hits_compare":
        value = float(stats.get("food_hits_total", 0))
        ok = _cmp(value, contract.op, contract.a)
        return ContractResult(contract, value, ok, f"treffer {value:.0f} {contract.op} {contract.a:g}")
    raise AssertionError(contract.kind)


def _between(value: float, lo: float, hi: float | None) -> bool:
    return hi is not None and lo <= value <= hi


def _cmp(left: float, op: str, right: float) -> bool:
    if op == ">":
        return left > right
    if op == ">=":
        return left >= right
    if op == "<":
        return left < right
    if op == "<=":
        return left <= right
    if op == "==":
        return abs(left - right) < 1e-9
    if op == "!=":
        return abs(left - right) >= 1e-9
    return False


def _num(token: str, line: str) -> float:
    try:
        return float(token.replace(",", "."))
    except ValueError as exc:
        raise KeimSyntaxError(f"Kontrakt erwartet Zahl, nicht {token!r}.", 0, line) from exc
