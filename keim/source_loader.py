from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .errors import KeimSyntaxError
from .preprocessor import expand_macros


_IMPORT_RE = re.compile(
    r'^\s*(?:verwende|importiere)\s+"(?P<path>[^"]+)"\s*$|^\s*nutze\s+datei\s+"(?P<path2>[^"]+)"\s*$'
)


@dataclass(slots=True, frozen=True)
class LoadedSource:
    source_name: str
    source: str
    imports: tuple[str, ...]
    values: dict[str, float]
    macros: tuple[str, ...]
    parameterized_macros: tuple[str, ...]
    expansion_count: int
    contracts: tuple[str, ...] = ()
    control_expansions: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "source_name": self.source_name,
            "imports": list(self.imports),
            "values": self.values,
            "macros": list(self.macros),
            "parameterized_macros": list(self.parameterized_macros),
            "expansion_count": self.expansion_count,
            "contracts": list(self.contracts),
            "control_expansions": self.control_expansions,
            "source": self.source,
        }


def load_source_file(path: str | Path) -> LoadedSource:
    path = Path(path)
    combined, imports = _load_with_imports(path.resolve(), stack=())
    expansion = expand_macros(combined)
    return LoadedSource(
        source_name=str(path),
        source=expansion.source,
        imports=tuple(imports),
        values=expansion.values,
        macros=expansion.macros,
        parameterized_macros=expansion.parameterized_macros,
        expansion_count=expansion.expansion_count,
        contracts=expansion.contracts,
        control_expansions=expansion.control_expansions,
    )


def load_raw_with_imports(path: str | Path) -> tuple[str, tuple[str, ...]]:
    text, imports = _load_with_imports(Path(path).resolve(), stack=())
    return text, tuple(imports)


def _load_with_imports(path: Path, stack: tuple[Path, ...]) -> tuple[str, list[str]]:
    if path in stack:
        cycle = " -> ".join(p.name for p in (*stack, path))
        raise KeimSyntaxError(f"Zyklischer Modulimport: {cycle}", 0, str(path))
    if not path.exists():
        raise KeimSyntaxError(f"Keim-Datei nicht gefunden: {path}", 0, str(path))

    raw_text = path.read_text(encoding="utf-8")
    lines = raw_text.splitlines()
    out: list[str] = []
    imports: list[str] = []

    for line_no, line in enumerate(lines, start=1):
        match = _IMPORT_RE.match(line.split("#", 1)[0].rstrip())
        if not match:
            out.append(line)
            continue

        spec = match.group("path") or match.group("path2") or ""
        target = _resolve_import(spec, base=path.parent)
        imported, nested = _load_with_imports(target, (*stack, path))
        imports.append(str(target))
        imports.extend(nested)
        out.append(f"# -- import {spec} begin --")
        out.append(imported)
        out.append(f"# -- import {spec} end --")

    return "\n".join(out) + ("\n" if raw_text.endswith("\n") else ""), imports


def _resolve_import(spec: str, *, base: Path) -> Path:
    candidates: list[Path] = []
    raw = Path(spec)
    if raw.suffix == "":
        raw = raw.with_suffix(".keim")

    if raw.is_absolute():
        candidates.append(raw)
    else:
        candidates.append(base / raw)
        candidates.append(base / "stdlib" / raw)
        package_root = Path(__file__).resolve().parents[1]
        candidates.append(package_root / "stdlib" / raw)
        candidates.append(Path(__file__).resolve().parent / "stdlib" / raw)

    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    tried = "\n".join(f"  - {c}" for c in candidates)
    raise KeimSyntaxError(f"Import {spec!r} nicht gefunden. Versucht:\n{tried}", 0, spec)
