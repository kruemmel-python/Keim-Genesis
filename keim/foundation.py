
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from collections import deque
import ast as pyast
import hashlib
import json
import operator
import re
import time
import tomllib


class FoundationError(Exception):
    """Fehler des Foundation/Independent-Kerns."""


@dataclass(frozen=True, slots=True)
class TypeRef:
    name: str
    args: tuple["TypeRef", ...] = ()

    def __str__(self) -> str:
        if not self.args:
            return self.name
        return f"{self.name}<" + ", ".join(map(str, self.args)) + ">"

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "args": [a.as_dict() for a in self.args]}


def parse_type_ref(text: str | None) -> TypeRef:
    text = (text or "").strip()
    if not text:
        return TypeRef("beliebig")
    lt = text.find("<")
    if lt < 0:
        return TypeRef(text)
    if not text.endswith(">"):
        raise FoundationError(f"Ungültige generische Typnotation: {text}")
    name = text[:lt].strip()
    inner = text[lt + 1:-1].strip()
    return TypeRef(name, tuple(parse_type_ref(p) for p in _split_commas(inner) if p))


@dataclass(slots=True)
class FieldDef:
    name: str
    typ: TypeRef


@dataclass(slots=True)
class TypeDef:
    name: str
    fields: list[FieldDef]
    union: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Param:
    name: str
    typ: TypeRef


@dataclass(slots=True)
class Step:
    op: str
    args: tuple[Any, ...]
    line: int
    text: str = ""


@dataclass(slots=True)
class FunctionDef:
    name: str
    params: list[Param]
    returns: TypeRef
    steps: list[Step]
    exported: bool = False
    line: int = 0


@dataclass(slots=True)
class TestDef:
    name: str
    steps: list[Step]
    line: int = 0


@dataclass(slots=True)
class ImportDef:
    module: str
    alias: str | None
    line: int


@dataclass(slots=True)
class ActorHandler:
    message: str
    returns: TypeRef
    steps: list[Step]
    line: int


@dataclass(slots=True)
class ActorDef:
    name: str
    fields: list[Step] = field(default_factory=list)
    handlers: dict[str, ActorHandler] = field(default_factory=dict)
    line: int = 0


@dataclass(slots=True)
class ModuleDef:
    name: str
    path: Path
    imports: list[ImportDef] = field(default_factory=list)
    exports: set[str] = field(default_factory=set)
    types: dict[str, TypeDef] = field(default_factory=dict)
    functions: dict[str, FunctionDef] = field(default_factory=dict)
    tests: list[TestDef] = field(default_factory=list)
    actors: dict[str, ActorDef] = field(default_factory=dict)
    permissions: set[str] = field(default_factory=set)


@dataclass(slots=True)
class Diagnostic:
    severity: str
    message: str
    line: int = 0
    module: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"severity": self.severity, "message": self.message, "line": self.line, "module": self.module}


@dataclass(slots=True)
class CheckReport:
    ok: bool
    modules: list[str]
    diagnostics: list[Diagnostic]

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "modules": self.modules, "diagnostics": [d.as_dict() for d in self.diagnostics]}

    def format(self, *_, **__) -> str:
        lines = ["[Keim Foundation] Check " + ("OK" if self.ok else "FEHLER")]
        lines.append("  Module: " + (", ".join(self.modules) if self.modules else "-"))
        for d in self.diagnostics:
            loc = f"{d.module}:" if d.module else ""
            lines.append(f"  {d.severity.upper()} {loc}Zeile {d.line}: {d.message}")
        return "\n".join(lines)


class Parser:
    def __init__(self, path: Path, source: str):
        self.path = Path(path)
        self.lines = source.splitlines()
        self.i = 0
        self.module = ModuleDef(self.path.stem, self.path)

    def parse(self) -> ModuleDef:
        while self.i < len(self.lines):
            raw = self.lines[self.i]
            line = _clean(raw)
            if not line:
                self.i += 1
                continue
            if _indent(raw) != 0:
                raise FoundationError(f"{self.path}:{self.i+1}: Top-Level darf nicht eingerückt sein")
            if line.startswith("modul "):
                self.module.name = line.removeprefix("modul ").strip()
                self.i += 1
            elif line.startswith("berechtigung "):
                self.module.permissions.add(line.removeprefix("berechtigung ").strip().replace("system.", ""))
                self.i += 1
            elif line.startswith("verwende "):
                self.module.imports.append(self._parse_import(line, self.i + 1))
                self.i += 1
            elif line.startswith("exportiere "):
                self.module.exports.add(line.removeprefix("exportiere ").strip().split()[-1])
                self.i += 1
            elif line.startswith("typ "):
                self._parse_type()
            elif line.startswith("akteur "):
                self._parse_actor()
            elif line.startswith("funktion "):
                fn = self._parse_function()
                fn.exported = fn.name in self.module.exports
                self.module.functions[fn.name] = fn
            elif line.startswith("test "):
                self.module.tests.append(self._parse_test())
            else:
                raise FoundationError(f"{self.path}:{self.i+1}: Unbekannte Top-Level-Form: {line}")
        return self.module

    def _parse_import(self, line: str, line_no: int) -> ImportDef:
        rest = line.removeprefix("verwende ").strip()
        if " als " in rest:
            mod, alias = rest.split(" als ", 1)
            return ImportDef(mod.strip().strip('"'), alias.strip(), line_no)
        return ImportDef(rest.strip().strip('"'), None, line_no)

    def _parse_type(self) -> None:
        line = _clean(self.lines[self.i])
        line_no = self.i + 1
        if " ist " in line and not line.endswith(":"):
            m = re.match(r"typ\s+(\w+)\s+ist\s+(.+)$", line)
            if not m:
                raise FoundationError(f"{self.path}:{line_no}: Ungültige Union-Typdefinition")
            self.module.types[m.group(1)] = TypeDef(m.group(1), [], [p.strip() for p in m.group(2).split("|")])
            self.i += 1
            return
        m = re.match(r"typ\s+(\w+)\s*:$", line)
        if not m:
            raise FoundationError(f"{self.path}:{line_no}: Typdefinition braucht 'typ Name:'")
        name = m.group(1)
        self.i += 1
        fields: list[FieldDef] = []
        while self.i < len(self.lines):
            raw = self.lines[self.i]
            line2 = _clean(raw)
            if not line2:
                self.i += 1
                continue
            if _indent(raw) < 4:
                break
            if _indent(raw) != 4:
                raise FoundationError(f"{self.path}:{self.i+1}: Typfelder brauchen genau vier Leerzeichen")
            m2 = re.match(r"(\w+)\s+ist\s+(.+)$", line2)
            if not m2:
                raise FoundationError(f"{self.path}:{self.i+1}: Ungültiges Typfeld")
            fields.append(FieldDef(m2.group(1), parse_type_ref(m2.group(2))))
            self.i += 1
        self.module.types[name] = TypeDef(name, fields)

    def _parse_actor(self) -> None:
        line = _clean(self.lines[self.i])
        line_no = self.i + 1
        m = re.match(r"akteur\s+(\w+)\s*:$", line)
        if not m:
            raise FoundationError(f"{self.path}:{line_no}: Akteur braucht 'akteur Name:'")
        actor = ActorDef(m.group(1), line=line_no)
        self.i += 1
        while self.i < len(self.lines):
            raw = self.lines[self.i]
            line2 = _clean(raw)
            if not line2:
                self.i += 1
                continue
            if _indent(raw) < 4:
                break
            if _indent(raw) != 4:
                raise FoundationError(f"{self.path}:{self.i+1}: Akteur-Block braucht vier Leerzeichen")
            if line2.startswith("speicher "):
                st = self._parse_single_step(line2, self.i + 1)
                if st.op != "let":
                    raise FoundationError(f"{self.path}:{self.i+1}: Akteur-Feld braucht typisierten Speicher")
                actor.fields.append(st)
                self.i += 1
            elif line2.startswith("bei "):
                mh = re.match(r'bei\s+"([^"]+)"(?:\s+antwortet\s+(.+?))?\s*:$', line2)
                if not mh:
                    raise FoundationError(f"{self.path}:{self.i+1}: Handler braucht bei \"msg\":")
                msg = mh.group(1)
                ret = parse_type_ref(mh.group(2) or "nichts")
                self.i += 1
                actor.handlers[msg] = ActorHandler(msg, ret, self._parse_steps(8), self.i + 1)
            else:
                raise FoundationError(f"{self.path}:{self.i+1}: Unbekannte Akteur-Form: {line2}")
        self.module.actors[actor.name] = actor

    def _parse_function(self) -> FunctionDef:
        line = _clean(self.lines[self.i])
        line_no = self.i + 1
        m = re.match(r"funktion\s+(\w+)\((.*?)\)\s+gibt\s+(.+):$", line)
        if not m:
            raise FoundationError(f"{self.path}:{line_no}: Funktion braucht 'funktion name(params) gibt Typ:'")
        params: list[Param] = []
        for part in _split_commas(m.group(2)):
            if not part:
                continue
            mm = re.match(r"(\w+)\s+ist\s+(.+)$", part)
            if not mm:
                raise FoundationError(f"{self.path}:{line_no}: Parameter braucht 'name ist Typ'")
            params.append(Param(mm.group(1), parse_type_ref(mm.group(2))))
        self.i += 1
        return FunctionDef(m.group(1), params, parse_type_ref(m.group(3)), self._parse_steps(4), line=line_no)

    def _parse_test(self) -> TestDef:
        line = _clean(self.lines[self.i])
        line_no = self.i + 1
        m = re.match(r'test\s+"([^"]+)"\s*:$', line)
        if not m:
            raise FoundationError(f"{self.path}:{line_no}: Test braucht test \"Name\":")
        self.i += 1
        return TestDef(m.group(1), self._parse_steps(4), line_no)

    def _parse_steps(self, base: int) -> list[Step]:
        steps: list[Step] = []
        while self.i < len(self.lines):
            raw = self.lines[self.i]
            line = _clean(raw)
            if not line:
                self.i += 1
                continue
            ind = _indent(raw)
            if ind < base:
                break
            if ind != base:
                raise FoundationError(f"{self.path}:{self.i+1}: Unerwartete Einrückung")
            line_no = self.i + 1
            if line.startswith("wenn ") and line.endswith(":"):
                expr = line[5:-1].strip()
                self.i += 1
                then_steps = self._parse_steps(base + 4)
                else_steps: list[Step] = []
                if self.i < len(self.lines) and _indent(self.lines[self.i]) == base and _clean(self.lines[self.i]) == "sonst:":
                    self.i += 1
                    else_steps = self._parse_steps(base + 4)
                steps.append(Step("if", (expr, then_steps, else_steps), line_no, line))
                continue
            if line.startswith("solange ") and line.endswith(":"):
                expr = line[len("solange "):-1].strip()
                self.i += 1
                body = self._parse_steps(base + 4)
                steps.append(Step("while", (expr, body), line_no, line))
                continue
            if line in {"abbruch", "break"}:
                steps.append(Step("break", (), line_no, line))
                self.i += 1
                continue
            if line in {"weiter", "continue"}:
                steps.append(Step("continue", (), line_no, line))
                self.i += 1
                continue
            if line.startswith("erwarte fehler:"):
                self.i += 1
                steps.append(Step("expect_error", (self._parse_steps(base + 4),), line_no, line))
                continue
            if line.startswith("match ") and line.endswith(":"):
                expr = line[len("match "):-1].strip()
                self.i += 1
                cases: list[tuple[str, str | None, list[Step], int]] = []
                while self.i < len(self.lines):
                    raw_case = self.lines[self.i]
                    case_line = _clean(raw_case)
                    if not case_line:
                        self.i += 1
                        continue
                    ind_case = _indent(raw_case)
                    if ind_case < base + 4:
                        break
                    if ind_case != base + 4:
                        raise FoundationError(f"{self.path}:{self.i+1}: match-Fälle brauchen {base+4} Leerzeichen")
                    if not case_line.startswith("fall ") or not case_line.endswith(":"):
                        raise FoundationError(f"{self.path}:{self.i+1}: match erwartet 'fall ...:'")
                    pat = case_line[len("fall "):-1].strip()
                    case_no = self.i + 1
                    kind = pat
                    bind: str | None = None
                    m_ok = re.match(r"ok\((\w+)\)$", pat)
                    m_err = re.match(r"fehler\((\w+)\)$", pat)
                    if m_ok:
                        kind, bind = "ok", m_ok.group(1)
                    elif m_err:
                        kind, bind = "fehler", m_err.group(1)
                    elif pat in {"_", "sonst"}:
                        kind, bind = "_", None
                    self.i += 1
                    body = self._parse_steps(base + 8)
                    cases.append((kind, bind, body, case_no))
                if not cases:
                    raise FoundationError(f"{self.path}:{line_no}: match braucht mindestens einen fall")
                steps.append(Step("match", (expr, cases), line_no, line))
                continue
            steps.append(self._parse_single_step(line, line_no))
            self.i += 1
        return steps

    def _parse_single_step(self, line: str, line_no: int) -> Step:
        if line.startswith("speicher "):
            rest = line.removeprefix("speicher ").strip()
            m = re.match(r"(\w+)\s+ist\s+(.+?)\s+setzt\s+(.+)$", rest)
            if m:
                return Step("let", (m.group(1), parse_type_ref(m.group(2)), m.group(3)), line_no, line)
            m = re.match(r"(\w+)\s+setzt\s+(.+)$", rest)
            if m:
                return Step("set", (m.group(1), m.group(2)), line_no, line)
            raise FoundationError(f"{self.path}:{line_no}: Ungültige Speicher-Anweisung")
        m = re.match(r"^(\w+)\s+setzt\s+(.+)$", line)
        if m:
            return Step("set", (m.group(1), m.group(2)), line_no, line)
        if line.startswith("rueckgabe "):
            return Step("return", (line.removeprefix("rueckgabe ").strip(),), line_no, line)
        if line.startswith("ausgabe "):
            return Step("print", (line.removeprefix("ausgabe ").strip(),), line_no, line)
        if line.startswith("pruefe "):
            return Step("assert", (line.removeprefix("pruefe ").strip(),), line_no, line)
        if line.startswith("snapshot speichere "):
            return Step("snapshot_save", (line.removeprefix("snapshot speichere ").strip().strip('"'),), line_no, line)
        if line.startswith("snapshot lade "):
            return Step("snapshot_load", (line.removeprefix("snapshot lade ").strip().strip('"'),), line_no, line)
        if line.startswith("replay marke "):
            return Step("replay_mark", (line.removeprefix("replay marke ").strip().strip('"'),), line_no, line)
        if line.startswith("sende "):
            rest = line.removeprefix("sende ").strip()
            parts = _split_ws_expr(rest)
            if len(parts) < 2:
                raise FoundationError(f"{self.path}:{line_no}: sende braucht Ziel und Ausdruck")
            return Step("send", (parts[0], " ".join(parts[1:])), line_no, line)
        if re.match(r"^\w+(\.\w+)?\(.*\)$", line):
            return Step("expr", (line,), line_no, line)
        raise FoundationError(f"{self.path}:{line_no}: Unbekannte Anweisung: {line}")


def _clean(raw: str) -> str:
    out: list[str] = []
    in_s = in_d = False
    esc = False
    for ch in raw:
        if ch == "\\" and not esc:
            esc = True
            out.append(ch)
            continue
        if ch == "'" and not in_d and not esc:
            in_s = not in_s
        elif ch == '"' and not in_s and not esc:
            in_d = not in_d
        elif ch == "#" and not in_s and not in_d:
            break
        out.append(ch)
        esc = False
    return "".join(out).strip()


def _indent(raw: str) -> int:
    return len(raw) - len(raw.lstrip(" "))


def _split_commas(text: str) -> list[str]:
    parts: list[str] = []
    start = depth = 0
    in_s = in_d = False
    for i, ch in enumerate(text + ","):
        if ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "'" and not in_d:
            in_s = not in_s
        elif not in_s and not in_d:
            if ch in "(<[{":
                depth += 1
            elif ch in ")>]}":
                depth -= 1
            elif ch == "," and depth == 0:
                parts.append(text[start:i].strip())
                start = i + 1
    return parts


def _split_ws_expr(text: str) -> list[str]:
    parts: list[str] = []
    cur: list[str] = []
    depth = 0
    in_s = in_d = False
    for ch in text:
        if ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "'" and not in_d:
            in_s = not in_s
        if ch == " " and not in_s and not in_d and depth == 0:
            if cur:
                parts.append("".join(cur))
                cur = []
            continue
        if not in_s and not in_d:
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth -= 1
        cur.append(ch)
    if cur:
        parts.append("".join(cur))
    return parts


class ModuleGraph:
    def __init__(self, entry: Path):
        self.entry = Path(entry).resolve()
        self.modules: dict[str, ModuleDef] = {}
        self.by_path: dict[Path, ModuleDef] = {}

    def load(self) -> "ModuleGraph":
        self._load_path(self.entry, [])
        return self

    def _load_path(self, path: Path, stack: list[Path]) -> ModuleDef:
        path = Path(path).resolve()
        if path in self.by_path:
            return self.by_path[path]
        if path in stack:
            raise FoundationError("Importzyklus: " + " -> ".join(p.name for p in stack + [path]))
        if not path.exists():
            raise FoundationError(f"Moduldatei nicht gefunden: {path}")
        mod = Parser(path, path.read_text(encoding="utf-8")).parse()
        self.by_path[path] = mod
        self.modules[mod.name] = mod
        for imp in mod.imports:
            ipath = self._resolve_import(path.parent, imp.module)
            if ipath:
                child = self._load_path(ipath, stack + [path])
                imp.module = child.name
        return mod

    def _resolve_import(self, base: Path, name: str) -> Path | None:
        candidates = []
        if name.endswith(".keim") or "/" in name or "\\" in name:
            candidates.append((base / name).resolve())
        candidates.append((base / (name.replace(".", "/") + ".keim")).resolve())
        candidates.append((base / (name.split(".")[-1] + ".keim")).resolve())
        for c in candidates:
            if c.exists():
                return c
        for c in self.entry.parent.rglob(name.split(".")[-1] + ".keim"):
            if c.exists():
                return c.resolve()
        return None

    def entry_module(self) -> ModuleDef:
        return self.by_path[self.entry]


@dataclass(slots=True)
class Instruction:
    op: str
    args: tuple[Any, ...]
    line: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {"op": self.op, "args": [_jsonify(a) for a in self.args], "line": self.line}


@dataclass(slots=True)
class ScopeLayout:
    names: dict[str, int] = field(default_factory=dict)
    types: dict[int, TypeRef] = field(default_factory=dict)

    def add(self, name: str, typ: TypeRef) -> int:
        if name in self.names:
            return self.names[name]
        slot = len(self.names)
        self.names[name] = slot
        self.types[slot] = typ
        return slot


@dataclass(slots=True)
class FunctionIR:
    module: str
    name: str
    params: list[dict[str, Any]]
    returns: dict[str, Any]
    slots: dict[str, int]
    slot_types: dict[str, str]
    code: list[Instruction]
    exported: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "module": self.module,
            "name": self.name,
            "params": self.params,
            "returns": self.returns,
            "slots": self.slots,
            "slot_types": self.slot_types,
            "exported": self.exported,
            "code": [i.as_dict() for i in self.code],
        }


@dataclass(slots=True)
class BytecodeProgram:
    format: str
    version: int
    entry: str
    modules: dict[str, dict[str, Any]]
    functions: dict[str, FunctionIR]
    actors: dict[str, dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "version": self.version,
            "entry": self.entry,
            "modules": self.modules,
            "functions": {k: v.as_dict() for k, v in self.functions.items()},
            "actors": self.actors,
        }


@dataclass(slots=True)
class CompileContext:
    graph: ModuleGraph
    module: ModuleDef
    scope: ScopeLayout


def compile_graph(graph: ModuleGraph) -> BytecodeProgram:
    functions: dict[str, FunctionIR] = {}
    actors: dict[str, dict[str, Any]] = {}
    modules_payload: dict[str, dict[str, Any]] = {}
    for mod in graph.modules.values():
        modules_payload[mod.name] = {
            "path": str(mod.path),
            "exports": sorted(mod.exports),
            "permissions": sorted(mod.permissions),
            "types": {n: {"fields": [{"name": f.name, "type": str(f.typ)} for f in td.fields], "union": td.union} for n, td in mod.types.items()},
            "imports": [{"module": i.module, "alias": i.alias} for i in mod.imports],
            "tests": [t.name for t in mod.tests],
            "actors": sorted(mod.actors),
        }
        for fn in mod.functions.values():
            functions[f"{mod.name}.{fn.name}"] = _compile_function(graph, mod, fn)
        for actor in mod.actors.values():
            actors[f"{mod.name}.{actor.name}"] = _compile_actor(graph, mod, actor)
    return BytecodeProgram("keim-independent-bytecode", 610, graph.entry_module().name, modules_payload, functions, actors)


def _compile_function(graph: ModuleGraph, mod: ModuleDef, fn: FunctionDef, seed: ScopeLayout | None = None) -> FunctionIR:
    scope = seed or ScopeLayout()
    for p in fn.params:
        scope.add(p.name, p.typ)
    ctx = CompileContext(graph, mod, scope)
    code = _compile_steps(ctx, fn.steps)
    return FunctionIR(
        mod.name, fn.name,
        [{"name": p.name, "type": str(p.typ), "slot": scope.names[p.name]} for p in fn.params],
        fn.returns.as_dict(),
        dict(scope.names),
        {str(k): str(v) for k, v in scope.types.items()},
        code,
        fn.exported,
    )


def _compile_actor(graph: ModuleGraph, mod: ModuleDef, actor: ActorDef) -> dict[str, Any]:
    fields = []
    for st in actor.fields:
        name, typ, expr = st.args
        fields.append({"name": name, "type": str(typ), "expr": [i.as_dict() for i in compile_expr(CompileContext(graph, mod, ScopeLayout()), expr, st.line)]})
    handlers = {}
    for msg, h in actor.handlers.items():
        scope = ScopeLayout()
        for st in actor.fields:
            n, t, _ = st.args
            scope.add(n, t)
        fake = FunctionDef(f"actor_{actor.name}_{msg}", [], h.returns, h.steps, False, h.line)
        handlers[msg] = _compile_function(graph, mod, fake, scope).as_dict()
    return {"module": mod.name, "name": actor.name, "fields": fields, "handlers": handlers}


def _compile_steps(ctx: CompileContext, steps: list[Step]) -> list[Instruction]:
    code: list[Instruction] = []
    for st in steps:
        match st.op:
            case "let":
                name, typ, expr = st.args
                slot = ctx.scope.add(name, typ)
                code.append(Instruction("DECLARE_SLOT", (slot, name, str(typ), [i.as_dict() for i in compile_expr(ctx, expr, st.line)]), st.line))
            case "set":
                name, expr = st.args
                if name not in ctx.scope.names:
                    ctx.scope.add(name, TypeRef("beliebig"))
                code.append(Instruction("STORE_SLOT", (ctx.scope.names[name], name, [i.as_dict() for i in compile_expr(ctx, expr, st.line)]), st.line))
            case "return":
                code.append(Instruction("RETURN", ([i.as_dict() for i in compile_expr(ctx, st.args[0], st.line)],), st.line))
            case "print":
                code.append(Instruction("PRINT", ([i.as_dict() for i in compile_expr(ctx, st.args[0], st.line)],), st.line))
            case "assert":
                code.append(Instruction("ASSERT", ([i.as_dict() for i in compile_expr(ctx, st.args[0], st.line)], st.args[0]), st.line))
            case "expr":
                code.append(Instruction("POP", ([i.as_dict() for i in compile_expr(ctx, st.args[0], st.line)],), st.line))
            case "send":
                target, expr = st.args
                if target not in ctx.scope.names:
                    raise FoundationError(f"Zeile {st.line}: sende-Ziel unbekannt: {target}")
                code.append(Instruction("CHANNEL_SEND", (ctx.scope.names[target], [i.as_dict() for i in compile_expr(ctx, expr, st.line)]), st.line))
            case "if":
                expr, a, b = st.args
                code.append(Instruction("IF", (
                    [i.as_dict() for i in compile_expr(ctx, expr, st.line)],
                    [i.as_dict() for i in _compile_steps(ctx, a)],
                    [i.as_dict() for i in _compile_steps(ctx, b)],
                ), st.line))
            case "expect_error":
                code.append(Instruction("EXPECT_ERROR", ([i.as_dict() for i in _compile_steps(ctx, st.args[0])],), st.line))
            case "snapshot_save":
                code.append(Instruction("SNAPSHOT_SAVE", st.args, st.line))
            case "snapshot_load":
                code.append(Instruction("SNAPSHOT_LOAD", st.args, st.line))
            case "replay_mark":
                code.append(Instruction("REPLAY_MARK", st.args, st.line))
    return code


def compile_expr(ctx: CompileContext, expr: str, line: int = 0) -> list[Instruction]:
    node = pyast.parse(_keim_expr_to_py(expr), mode="eval").body
    code: list[Instruction] = []
    _compile_node(ctx, node, code, line)
    return code


def _compile_node(ctx: CompileContext, node: pyast.AST, code: list[Instruction], line: int) -> None:
    match node:
        case pyast.Constant(value=v):
            code.append(Instruction("CONST", (v,), line))
        case pyast.Name(id=name):
            name = _py_name_to_keim(name)
            if name in ctx.scope.names:
                code.append(Instruction("LOAD_SLOT", (ctx.scope.names[name], name), line))
            elif name in {"wahr", "true"}:
                code.append(Instruction("CONST", (True,), line))
            elif name in {"falsch", "false"}:
                code.append(Instruction("CONST", (False,), line))
            elif name in {"nichts", "none"}:
                code.append(Instruction("CONST", (None,), line))
            else:
                code.append(Instruction("LOAD_NAME", (name,), line))
        case pyast.BinOp(left=l, op=op, right=r):
            _compile_node(ctx, l, code, line); _compile_node(ctx, r, code, line)
            code.append(Instruction(_BIN_OPCODE[type(op)], (), line))
        case pyast.UnaryOp(op=pyast.USub(), operand=o):
            _compile_node(ctx, o, code, line); code.append(Instruction("NEG", (), line))
        case pyast.BoolOp(op=pyast.And(), values=vals):
            for v in vals: _compile_node(ctx, v, code, line)
            code.append(Instruction("AND", (len(vals),), line))
        case pyast.BoolOp(op=pyast.Or(), values=vals):
            for v in vals: _compile_node(ctx, v, code, line)
            code.append(Instruction("OR", (len(vals),), line))
        case pyast.Compare(left=l, ops=ops, comparators=comps):
            _compile_node(ctx, l, code, line)
            for op, comp in zip(ops, comps):
                _compile_node(ctx, comp, code, line)
                code.append(Instruction(_CMP_OPCODE[type(op)], (), line))
        case pyast.List(elts=elts):
            for e in elts: _compile_node(ctx, e, code, line)
            code.append(Instruction("MAKE_LIST", (len(elts),), line))
        case pyast.Dict(keys=keys, values=vals):
            for k, v in zip(keys, vals):
                _compile_node(ctx, k, code, line); _compile_node(ctx, v, code, line)
            code.append(Instruction("MAKE_MAP", (len(keys),), line))
        case pyast.Subscript(value=v, slice=s):
            _compile_node(ctx, v, code, line); _compile_node(ctx, s, code, line)
            code.append(Instruction("GET_ITEM", (), line))
        case pyast.Attribute(value=v, attr=a):
            _compile_node(ctx, v, code, line)
            code.append(Instruction("GET_ATTR", (a,), line))
        case pyast.Call(func=func, args=args):
            for a in args: _compile_node(ctx, a, code, line)
            if isinstance(func, pyast.Name):
                name = _py_name_to_keim(func.id)
                if name in {"ok", "fehler", "kanal", "empfange", "starte", "frage"}:
                    code.append(Instruction("CALL_BUILTIN", (name, len(args)), line))
                elif name in ctx.module.types:
                    code.append(Instruction("MAKE_RECORD", (name, len(args)), line))
                else:
                    code.append(Instruction("CALL_LOCAL", (name, len(args)), line))
            elif isinstance(func, pyast.Attribute) and isinstance(func.value, pyast.Name):
                code.append(Instruction("CALL_IMPORTED", (_py_name_to_keim(func.value.id), func.attr, len(args)), line))
            else:
                raise FoundationError(f"Zeile {line}: Nicht unterstützter Call")
        case _:
            raise FoundationError(f"Zeile {line}: Nicht unterstützter Ausdruck: {pyast.dump(node)}")


_BIN_OPCODE = {pyast.Add: "ADD", pyast.Sub: "SUB", pyast.Mult: "MUL", pyast.Div: "DIV", pyast.FloorDiv: "FLOORDIV", pyast.Mod: "MOD"}
_CMP_OPCODE = {pyast.Eq: "EQ", pyast.NotEq: "NE", pyast.Lt: "LT", pyast.LtE: "LE", pyast.Gt: "GT", pyast.GtE: "GE"}


def analyze_graph(graph: ModuleGraph) -> CheckReport:
    diagnostics: list[Diagnostic] = []
    for mod in graph.modules.values():
        aliases = _aliases_for(graph, mod)
        for imp in mod.imports:
            if imp.module not in graph.modules:
                diagnostics.append(Diagnostic("error", f"Import nicht auflösbar: {imp.module}", imp.line, mod.name))
        for name in mod.exports:
            if name not in mod.functions and name not in mod.types:
                diagnostics.append(Diagnostic("error", f"Export unbekannt: {name}", 0, mod.name))
        for fn in mod.functions.values():
            seen: set[str] = set()
            for p in fn.params:
                if p.name in seen:
                    diagnostics.append(Diagnostic("error", f"Doppelter Parameter {p.name}", fn.line, mod.name))
                seen.add(p.name)
            if fn.returns.name not in {"nichts", "void"} and not _has_return(fn.steps):
                diagnostics.append(Diagnostic("error", f"Funktion {fn.name} gibt nicht auf allen einfachen Pfaden zurück", fn.line, mod.name))
    try:
        diagnostics.extend(verify_bytecode(compile_graph(graph).as_dict()))
    except Exception as exc:
        diagnostics.append(Diagnostic("error", str(exc), 0, ""))
    return CheckReport(not any(d.severity == "error" for d in diagnostics), sorted(graph.modules), diagnostics)


def _has_return(steps: list[Step]) -> bool:
    for st in steps:
        if st.op == "return":
            return True
        if st.op == "if":
            _, a, b = st.args
            if a and b and _has_return(a) and _has_return(b):
                return True
    return False


def verify_bytecode(payload: dict[str, Any]) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    if payload.get("format") != "keim-independent-bytecode":
        diags.append(Diagnostic("error", "Unbekanntes Bytecode-Format"))
    if payload.get("version", 0) < 610:
        diags.append(Diagnostic("warning", "Bytecode-Version älter als 610"))
    for fid, fn in payload.get("functions", {}).items():
        for instr in _walk_instr_dicts(fn.get("code", [])):
            if instr.get("op") == "EVAL":
                diags.append(Diagnostic("error", f"{fid}: verbotene Instruktion EVAL", instr.get("line", 0)))
    return diags


def _walk_instr_dicts(code: list[dict[str, Any]]):
    for instr in code:
        yield instr
        for arg in instr.get("args", []):
            if isinstance(arg, list) and all(isinstance(x, dict) for x in arg):
                yield from _walk_instr_dicts(arg)


def _names_in_steps(steps: list[Step]) -> tuple[set[str], set[str]]:
    used: set[str] = set(); declared: set[str] = set()
    for st in steps:
        if st.op == "let":
            n, _, e = st.args; declared.add(n); used |= _expr_names(e)
        elif st.op == "set":
            n, e = st.args; used.add(n); used |= _expr_names(e)
        elif st.op in {"return", "print", "assert", "expr"}:
            used |= _expr_names(st.args[0])
        elif st.op == "send":
            used.add(st.args[0]); used |= _expr_names(st.args[1])
        elif st.op == "if":
            e, a, b = st.args; used |= _expr_names(e)
            ua, da = _names_in_steps(a); ub, db = _names_in_steps(b)
            used |= ua | ub; declared |= da | db
    return used, declared


def _expr_names(expr: str) -> set[str]:
    try:
        node = pyast.parse(_keim_expr_to_py(expr), mode="eval")
    except Exception:
        return set()
    return {_py_name_to_keim(n.id) for n in pyast.walk(node) if isinstance(n, pyast.Name)}


def lint_graph(graph: ModuleGraph) -> CheckReport:
    report = analyze_graph(graph)
    diagnostics = list(report.diagnostics)
    for mod in graph.modules.values():
        for fn in mod.functions.values():
            used, declared = _names_in_steps(fn.steps)
            for n in sorted(declared - used):
                diagnostics.append(Diagnostic("warning", f"Variable '{n}' wird nie gelesen", fn.line, mod.name))
            if fn.name not in mod.exports and fn.name != "main" and not fn.name.startswith("_"):
                diagnostics.append(Diagnostic("info", f"Funktion '{fn.name}' ist privat/nicht exportiert", fn.line, mod.name))
    return CheckReport(not any(d.severity == "error" for d in diagnostics), sorted(graph.modules), diagnostics)


class ReturnSignal(Exception):
    def __init__(self, value: Any):
        self.value = value


@dataclass(slots=True)
class Frame:
    module: str
    function: str
    slots: list[Any]
    slot_names: dict[int, str]
    slot_types: dict[int, TypeRef]


@dataclass(slots=True)
class Channel:
    queue: deque[Any] = field(default_factory=deque)


@dataclass(slots=True)
class ActorInstance:
    id: int
    module: str
    type_name: str
    state: dict[str, Any]


@dataclass(slots=True)
class VmResult:
    ok: bool
    value: Any = None
    output: list[str] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "value": _snapshot_value(self.value), "output": self.output, "events": self.events}


class IndependentVM:
    def __init__(self, graph: ModuleGraph, *, deterministic: bool = False, seed: int = 0, record_path: Path | None = None):
        self.graph = graph
        self.bytecode = compile_graph(graph)
        self.output: list[str] = []
        self.events: list[dict[str, Any]] = []
        self.deterministic = deterministic
        self.seed = seed
        self.record_path = record_path
        self.frames: list[Frame] = []
        self.functions = self.bytecode.functions
        self.aliases = {m.name: _aliases_for(graph, m) for m in graph.modules.values()}
        self.actors: dict[int, ActorInstance] = {}
        self.next_actor_id = 1

    def run_main(self) -> VmResult:
        entry = self.graph.entry_module()
        result = self.call(entry.name, "main", [])
        self._flush_replay()
        return VmResult(True, result, self.output, self.events)

    def run_tests(self) -> dict[str, Any]:
        tests = []; ok = True
        for mod in self.graph.modules.values():
            for t in mod.tests:
                started = time.perf_counter()
                scope = ScopeLayout(); ctx = CompileContext(self.graph, mod, scope)
                code = _compile_steps(ctx, t.steps)
                frame = Frame(mod.name, f"test:{t.name}", [None] * (max(scope.names.values(), default=-1) + 1), {v: k for k, v in scope.names.items()}, scope.types)
                self.frames.append(frame)
                try:
                    self._exec_code(code, frame)
                    tests.append({"module": mod.name, "name": t.name, "ok": True, "seconds": time.perf_counter() - started})
                except Exception as exc:
                    ok = False
                    tests.append({"module": mod.name, "name": t.name, "ok": False, "error": str(exc), "seconds": time.perf_counter() - started})
                finally:
                    self.frames.pop()
        self._flush_replay()
        return {"ok": ok, "tests": tests, "count": len(tests)}

    def call(self, module: str, name: str, args: list[Any]) -> Any:
        fid = f"{module}.{name}"
        fn = self.functions.get(fid)
        if fn is None:
            raise FoundationError(f"Funktion nicht gefunden: {fid}")
        if len(args) != len(fn.params):
            raise FoundationError(f"{fid} erwartet {len(fn.params)} Argumente, bekam {len(args)}")
        slots = [None] * (max(fn.slots.values(), default=-1) + 1)
        mod = self.graph.modules[module]
        for p, val in zip(fn.params, args):
            typ = parse_type_ref(p["type"])
            if not value_matches_type(val, typ, mod.types):
                raise FoundationError(f"Parameter {p['name']} erwartet {typ}, bekam {val!r}")
            slots[p["slot"]] = val
        frame = Frame(module, name, slots, {v: k for k, v in fn.slots.items()}, {int(k): parse_type_ref(v) for k, v in fn.slot_types.items()})
        self.frames.append(frame)
        try:
            try:
                self._exec_code(fn.code, frame)
                result = None
            except ReturnSignal as ret:
                result = ret.value
            ret_typ = _typeref_from_dict(fn.returns)
            if not value_matches_type(result, ret_typ, mod.types):
                raise FoundationError(f"Rückgabe von {fid} erwartet {ret_typ}, bekam {result!r}")
            return result
        finally:
            self.frames.pop()

    def _exec_code(self, code: list[Instruction | dict[str, Any]], frame: Frame) -> None:
        for raw in code:
            instr = _instr_from_any(raw)
            match instr.op:
                case "DECLARE_SLOT":
                    slot, name, typ_s, expr_code = instr.args
                    value = self._eval_code(expr_code, frame)
                    typ = parse_type_ref(typ_s)
                    if not value_matches_type(value, typ, self.graph.modules[frame.module].types):
                        raise FoundationError(f"Zeile {instr.line}: {name} erwartet {typ}, bekam {value!r}")
                    self._ensure_slot(frame, slot); frame.slots[slot] = value; frame.slot_names[slot] = name; frame.slot_types[slot] = typ
                    self._event("declare", line=instr.line, name=name, value=value)
                case "STORE_SLOT":
                    slot, name, expr_code = instr.args
                    value = self._eval_code(expr_code, frame)
                    typ = frame.slot_types.get(slot, TypeRef("beliebig"))
                    if not value_matches_type(value, typ, self.graph.modules[frame.module].types):
                        raise FoundationError(f"Zeile {instr.line}: {name} erwartet {typ}, bekam {value!r}")
                    self._ensure_slot(frame, slot); frame.slots[slot] = value
                    self._event("store", line=instr.line, name=name, value=value)
                case "RETURN":
                    raise ReturnSignal(self._eval_code(instr.args[0], frame))
                case "PRINT":
                    val = self._eval_code(instr.args[0], frame); self.output.append(str(val)); print(val)
                case "ASSERT":
                    if not bool(self._eval_code(instr.args[0], frame)):
                        raise FoundationError(f"Zeile {instr.line}: Prüfung fehlgeschlagen: {instr.args[1]}")
                case "POP":
                    self._eval_code(instr.args[0], frame)
                case "IF":
                    cond, then_code, else_code = instr.args
                    self._exec_code(then_code if self._eval_code(cond, frame) else else_code, frame)
                case "EXPECT_ERROR":
                    try:
                        self._exec_code(instr.args[0], frame)
                    except Exception:
                        self._event("expected_error", line=instr.line)
                    else:
                        raise FoundationError(f"Zeile {instr.line}: erwarteter Fehler trat nicht ein")
                case "CHANNEL_SEND":
                    slot, expr_code = instr.args
                    ch = frame.slots[slot]
                    if not isinstance(ch, Channel):
                        raise FoundationError(f"Zeile {instr.line}: sende-Ziel ist kein Kanal")
                    ch.queue.append(self._eval_code(expr_code, frame))
                    self._event("channel_send", line=instr.line, size=len(ch.queue))
                case "SNAPSHOT_SAVE":
                    self.save_snapshot(Path(instr.args[0])); self._event("snapshot_save", path=instr.args[0], line=instr.line)
                case "SNAPSHOT_LOAD":
                    self.load_snapshot(Path(instr.args[0])); self._event("snapshot_load", path=instr.args[0], line=instr.line)
                case "REPLAY_MARK":
                    self._event("replay_mark", mark=instr.args[0], line=instr.line)
                case _:
                    raise FoundationError(f"Unbekannte VM-Instruktion: {instr.op}")

    def _eval_code(self, code: list[Instruction | dict[str, Any]], frame: Frame) -> Any:
        stack: list[Any] = []
        for raw in code:
            instr = _instr_from_any(raw); op = instr.op
            if op == "CONST":
                stack.append(instr.args[0])
            elif op == "LOAD_SLOT":
                slot, _ = instr.args; self._ensure_slot(frame, slot); stack.append(frame.slots[slot])
            elif op == "LOAD_NAME":
                raise FoundationError(f"Unbekannter Name: {instr.args[0]}")
            elif op in _OPS:
                b = stack.pop(); a = stack.pop(); stack.append(_OPS[op](a, b))
            elif op == "NEG":
                stack.append(-stack.pop())
            elif op in {"AND", "OR"}:
                n = instr.args[0]; vals = stack[-n:] if n else []
                if n: del stack[-n:]
                stack.append(all(vals) if op == "AND" else any(vals))
            elif op == "MAKE_LIST":
                n = instr.args[0]; vals = stack[-n:] if n else []
                if n: del stack[-n:]
                stack.append(list(vals))
            elif op == "MAKE_MAP":
                n = instr.args[0]; vals = stack[-2*n:] if n else []
                if n: del stack[-2*n:]
                it = iter(vals); stack.append({k: v for k, v in zip(it, it)})
            elif op == "GET_ITEM":
                key = stack.pop(); base = stack.pop(); stack.append(base[key])
            elif op == "GET_ATTR":
                attr = instr.args[0]; base = stack.pop()
                stack.append(base[attr] if isinstance(base, dict) else getattr(base, attr))
            elif op == "CALL_LOCAL":
                name, argc = instr.args
                args = stack[-argc:] if argc else []
                if argc: del stack[-argc:]
                stack.append(self.call(frame.module, name, list(args)))
            elif op == "CALL_IMPORTED":
                alias, name, argc = instr.args
                args = stack[-argc:] if argc else []
                if argc: del stack[-argc:]
                mod_name = self.aliases.get(frame.module, {}).get(alias, alias)
                stack.append(self.call(mod_name, name, list(args)))
            elif op == "CALL_BUILTIN":
                name, argc = instr.args
                args = stack[-argc:] if argc else []
                if argc: del stack[-argc:]
                stack.append(self._call_builtin(frame, name, list(args)))
            elif op == "MAKE_RECORD":
                name, argc = instr.args
                args = stack[-argc:] if argc else []
                if argc: del stack[-argc:]
                td = self.graph.modules[frame.module].types.get(name)
                if not td or len(args) != len(td.fields):
                    raise FoundationError(f"{name} erwartet passende Felder")
                stack.append({"__typ__": name, **{f.name: v for f, v in zip(td.fields, args)}})
            else:
                raise FoundationError(f"Unbekannte Ausdrucksinstruktion: {op}")
        return stack[-1] if stack else None

    def _call_builtin(self, frame: Frame, name: str, args: list[Any]) -> Any:
        if name == "ok":
            return {"ok": True, "wert": args[0] if args else None}
        if name == "fehler":
            return {"ok": False, "fehler": args[0] if args else None}
        if name == "kanal":
            return Channel()
        if name == "empfange":
            if not args or not isinstance(args[0], Channel):
                raise FoundationError("empfange erwartet kanal")
            if not args[0].queue:
                raise FoundationError("Kanal ist leer")
            val = args[0].queue.popleft(); self._event("channel_receive", value=val); return val
        if name == "starte":
            if not args or not isinstance(args[0], str):
                raise FoundationError("starte erwartet Akteur-Namen als text")
            return self._start_actor(frame.module, args[0])
        if name == "frage":
            if len(args) < 2:
                raise FoundationError("frage erwartet actor, nachricht")
            return self._ask_actor(args[0], str(args[1]), args[2] if len(args) > 2 else None)
        raise FoundationError(f"Unbekanntes Builtin: {name}")

    def _start_actor(self, module: str, actor_name: str) -> ActorInstance:
        bc = self.bytecode.actors.get(f"{module}.{actor_name}")
        if bc is None:
            raise FoundationError(f"Akteur nicht gefunden: {module}.{actor_name}")
        fake = Frame(module, f"actor:{actor_name}", [], {}, {})
        state = {f["name"]: self._eval_code(f["expr"], fake) for f in bc["fields"]}
        inst = ActorInstance(self.next_actor_id, module, actor_name, state)
        self.actors[inst.id] = inst; self.next_actor_id += 1
        self._event("actor_start", actor=actor_name, id=inst.id)
        return inst

    def _ask_actor(self, actor: ActorInstance, msg: str, payload: Any = None) -> Any:
        if not isinstance(actor, ActorInstance):
            raise FoundationError("frage erwartet Akteur")
        h = self.bytecode.actors[f"{actor.module}.{actor.type_name}"]["handlers"].get(msg)
        if not h:
            raise FoundationError(f"Akteur {actor.type_name} kennt Nachricht {msg} nicht")
        fn = FunctionIR(h["module"], h["name"], h["params"], h["returns"], h["slots"], h["slot_types"], [_instr_from_any(i) for i in h["code"]], False)
        slots = [None] * (max(fn.slots.values(), default=-1) + 1)
        for name, val in actor.state.items():
            if name in fn.slots:
                slots[fn.slots[name]] = val
        frame = Frame(actor.module, f"actor:{actor.type_name}.{msg}", slots, {v: k for k, v in fn.slots.items()}, {int(k): parse_type_ref(v) for k, v in fn.slot_types.items()})
        self.frames.append(frame)
        try:
            try:
                self._exec_code(fn.code, frame)
                result = None
            except ReturnSignal as ret:
                result = ret.value
            for idx, name in frame.slot_names.items():
                if name in actor.state:
                    actor.state[name] = frame.slots[idx]
            self._event("actor_message", actor=actor.type_name, message=msg)
            return result
        finally:
            self.frames.pop()

    def _ensure_slot(self, frame: Frame, slot: int) -> None:
        if slot >= len(frame.slots):
            frame.slots.extend([None] * (slot + 1 - len(frame.slots)))

    def _event(self, typ: str, **payload: Any) -> None:
        payload = {k: _snapshot_value(v) for k, v in payload.items()}
        payload["type"] = typ
        payload.setdefault("time", len(self.events) if self.deterministic else time.time())
        self.events.append(payload)

    def save_snapshot(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"format": "keim-snapshot-v1", "events": self.events, "actors": {str(i): _snapshot_value(a) for i, a in self.actors.items()}}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_snapshot(self, path: Path) -> None:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload.get("format") != "keim-snapshot-v1":
            raise FoundationError("Unbekanntes Snapshot-Format")
        self.events = payload.get("events", [])

    def _flush_replay(self) -> None:
        if self.record_path:
            self.record_path.parent.mkdir(parents=True, exist_ok=True)
            self.record_path.write_text(json.dumps({"format": "keim-replay-v1", "events": self.events}, ensure_ascii=False, indent=2), encoding="utf-8")


_OPS = {
    "ADD": operator.add, "SUB": operator.sub, "MUL": operator.mul, "DIV": operator.truediv,
    "FLOORDIV": operator.floordiv, "MOD": operator.mod, "EQ": operator.eq, "NE": operator.ne,
    "LT": operator.lt, "LE": operator.le, "GT": operator.gt, "GE": operator.ge,
}


def _snapshot_value(v: Any) -> Any:
    if isinstance(v, Channel):
        return {"__channel__": list(v.queue)}
    if isinstance(v, ActorInstance):
        return {"__actor__": v.id, "module": v.module, "type": v.type_name, "state": _snapshot_value(v.state)}
    if isinstance(v, dict):
        return {str(k): _snapshot_value(val) for k, val in v.items()}
    if isinstance(v, list):
        return [_snapshot_value(x) for x in v]
    return v


def replay_file(path: Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("format") not in {"keim-replay-v1", "keim-snapshot-v1"}:
        raise FoundationError("Unbekanntes Replay-/Snapshot-Format")
    return {"ok": True, "event_count": len(payload.get("events", [])), "events": payload.get("events", [])}


def core_run(path: Path, *, record: Path | None = None) -> VmResult:
    graph = ModuleGraph(path).load()
    report = analyze_graph(graph)
    if not report.ok:
        raise FoundationError(report.format())
    return IndependentVM(graph, record_path=record).run_main()


def core_test(path: Path) -> dict[str, Any]:
    graph = ModuleGraph(path).load()
    report = analyze_graph(graph)
    if not report.ok:
        raise FoundationError(report.format())
    return IndependentVM(graph).run_tests()


def core_bytecode(path: Path) -> dict[str, Any]:
    graph = ModuleGraph(path).load()
    report = analyze_graph(graph)
    if not report.ok:
        raise FoundationError(report.format())
    return compile_graph(graph).as_dict()


def load_project(entry: Path | None = None, cwd: Path | None = None) -> tuple[Path, dict[str, Any]]:
    cwd = Path(cwd or Path.cwd())
    if entry is not None:
        return Path(entry), {}
    toml_path = cwd / "keim.toml"
    if not toml_path.exists():
        raise FoundationError("Keine Eingabedatei und keine keim.toml gefunden")
    data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    main = data.get("build", {}).get("main") or data.get("projekt", {}).get("main") or "src/main.keim"
    return cwd / main, data


def build_lock(cwd: Path) -> dict[str, Any]:
    cwd = Path(cwd)
    data = tomllib.loads((cwd / "keim.toml").read_text(encoding="utf-8")) if (cwd / "keim.toml").exists() else {}
    deps = data.get("abhängigkeiten", {}) or data.get("abhaengigkeiten", {})

    def _walk(prefix: str, value: Any) -> list[tuple[str, Any]]:
        if isinstance(value, dict):
            out: list[tuple[str, Any]] = []
            for k, v in value.items():
                out.extend(_walk(f"{prefix}.{k}" if prefix else str(k), v))
            return out
        return [(prefix, value)]

    packages = []
    for name, version in sorted(_walk("", deps)):
        packages.append({"name": name, "version": str(version), "sha256": hashlib.sha256(f"{name}@{version}".encode()).hexdigest(), "permissions": []})
    sources = [{"path": str(p.relative_to(cwd)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(cwd.rglob("*.keim"))]
    lock = {"format": "keim-lock-v2", "packages": packages, "sources": sources}
    (cwd / "keim.lock").write_text(json.dumps(lock, ensure_ascii=False, indent=2), encoding="utf-8")
    return lock


def export_independent_bundle(path: Path, out: Path) -> None:
    graph = ModuleGraph(path).load()
    bc = compile_graph(graph).as_dict()
    out.mkdir(parents=True, exist_ok=True)
    (out / "app.kbc.json").write_text(json.dumps(bc, ensure_ascii=False, indent=2), encoding="utf-8")
    import shutil
    runtime_dir = out / "runtime"
    dst_pkg = runtime_dir / "keim"
    if dst_pkg.exists():
        shutil.rmtree(dst_pkg)
    runtime_dir.mkdir(exist_ok=True)
    shutil.copytree(Path(__file__).resolve().parent, dst_pkg, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "build"))
    sources = {str(m.path): m.path.read_text(encoding="utf-8") for m in graph.modules.values()}
    entry = str(graph.entry)
    (out / "keim_app.py").write_text(
        "from pathlib import Path\nimport tempfile, sys\nROOT=Path(__file__).resolve().parent\nsys.path.insert(0,str(ROOT/'runtime'))\nfrom keim.foundation import ModuleGraph, IndependentVM\n"
        f"SOURCES={sources!r}\nENTRY={entry!r}\nTMP=Path(tempfile.mkdtemp(prefix='keim_bundle_'))\nentry=None\n"
        "for p,t in SOURCES.items():\n    d=TMP/Path(p).name; d.write_text(t,encoding='utf-8')\n    if p==ENTRY: entry=d\nIndependentVM(ModuleGraph(entry or next(TMP.glob('*.keim'))).load()).run_main()\n",
        encoding="utf-8",
    )
    (out / "README_RUN.txt").write_text("Keim Genesis v6.2 Independent-Core Bundle\n\nStart:\n  python keim_app.py\n\nBytecode-Version 610 ohne EVAL-Instruktion.\n", encoding="utf-8")


def format_source(source: str) -> str:
    out: list[str] = []
    for raw in source.splitlines():
        line = _clean(raw)
        if not line:
            out.append("")
            continue
        ind = _indent(raw)
        line = re.sub(r"\s+", " ", line)
        line = re.sub(r"\s*([+\-*/%<>=!]=?|==)\s*", r" \1 ", line)
        line = re.sub(r",\s*", ", ", line)
        line = re.sub(r"\s+:", ":", line)
        out.append(" " * ind + line.strip())
    return "\n".join(out).rstrip() + "\n"


def format_path(path: Path, *, write: bool = False) -> str:
    p = Path(path)
    if p.is_dir():
        files = sorted(p.rglob("*.keim"))
        for f in files:
            new = format_source(f.read_text(encoding="utf-8"))
            if write:
                f.write_text(new, encoding="utf-8")
        return "\n".join(str(f) for f in files)
    new = format_source(p.read_text(encoding="utf-8"))
    if write:
        p.write_text(new, encoding="utf-8")
    return new


def _aliases_for(graph: ModuleGraph, mod: ModuleDef) -> dict[str, str]:
    return {imp.alias or imp.module.split(".")[-1]: imp.module for imp in mod.imports}


def _keim_expr_to_py(expr: str) -> str:
    expr = re.sub(r"\bwahr\b", "True", expr)
    expr = re.sub(r"\bfalsch\b", "False", expr)
    expr = re.sub(r"\bnichts\b", "None", expr)
    expr = re.sub(r"\bund\b", "and", expr)
    expr = re.sub(r"\boder\b", "or", expr)
    expr = re.sub(r"\bnicht\b", "not", expr)
    return expr


def _py_name_to_keim(name: str) -> str:
    return {"True": "wahr", "False": "falsch", "None": "nichts"}.get(name, name)


def _typeref_from_dict(d: dict[str, Any]) -> TypeRef:
    return TypeRef(d.get("name", "beliebig"), tuple(_typeref_from_dict(a) for a in d.get("args", [])))


def value_matches_type(value: Any, typ: TypeRef, local_types: dict[str, TypeDef]) -> bool:
    name = typ.name
    if name in {"beliebig", "any"}:
        return True
    if name in {"nichts", "void"}:
        return value is None
    if name == "ganzzahl":
        return isinstance(value, int) and not isinstance(value, bool)
    if name in {"kommazahl", "zahl"}:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if name == "text":
        return isinstance(value, str)
    if name == "bool":
        return isinstance(value, bool)
    if name == "kanal":
        return isinstance(value, Channel)
    if name == "akteur":
        return isinstance(value, ActorInstance)
    if name == "liste":
        return isinstance(value, list) and (not typ.args or all(value_matches_type(v, typ.args[0], local_types) for v in value))
    if name == "karte":
        return isinstance(value, dict)
    if name == "ergebnis":
        return isinstance(value, dict) and "ok" in value
    if name in local_types:
        return isinstance(value, dict) and value.get("__typ__") == name
    return True


def _instr_from_any(x: Instruction | dict[str, Any]) -> Instruction:
    if isinstance(x, Instruction):
        return x
    return Instruction(x["op"], tuple(x.get("args", [])), x.get("line", 0))


def _jsonify(value: Any) -> Any:
    if isinstance(value, TypeRef):
        return str(value)
    if isinstance(value, Instruction):
        return value.as_dict()
    if isinstance(value, list):
        return [_jsonify(v) for v in value]
    if isinstance(value, tuple):
        return [_jsonify(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonify(v) for k, v in value.items()}
    return _snapshot_value(value)
