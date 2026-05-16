from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

from .ast_nodes import (
    Action,
    AgentAvoidTrail,
    AgentFieldChange,
    AgentFindsFoodCondition,
    AgentFollowTrail,
    CallRule,
    CompositeCondition,
    ConditionBinary,
    ConditionExpr,
    ConditionNot,
    EventDecl,
    FieldCompute,
    FieldCondition,
    FieldDecl,
    FieldPredicate,
    FieldTrailCoupling,
    FieldTrailEmission,
    FoodPredicate,
    FunctionDecl,
    IfBlock,
    MemoryAggregate,
    MemoryChange,
    MemoryCondition,
    MemoryDecl,
    MemoryPredicate,
    MapHasPredicate,
    PeriodicBlock,
    Program,
    RepeatBlock,
    RoundBlock,
    RuleDecl,
    ShowWorld,
    SpawnAgents,
    KillAgents,
    SpawnObject,
    SourceDecl,
    SourceLocation,
    Step,
    TrailCondition,
    TrailDecl,
    TrailDiffuse,
    TrailPredicate,
    TrailStrengthen,
    ClassDecl,
    DatabaseDecl,
    DatabaseSave,
    ObjectCall,
    ObjectDecl,
    SelfPropertyRef,
    TableDecl,
    TableInsert,
    CollectGarbage,
    DeleteObject,
    StartDashboard,
    ExportImage,
    PathFind,
    WebRequest,
    FileTableIO,
    ListPop,
    ListAppend,
    TableQuery,
    TableIndexDecl,
    MapSet,
    MapGet,
    MapDelete,
    MapHas,
    JsonParse,
    JsonStringify,
    HttpServerStart,
    ForeignLibraryDecl,
    FfiCall,
    WebGuiDecl,
    PermissionDecl,
    UseDecl,
    GrafikCommand,
    AudioCommand,
    DebugWatch,
    DebugSend,
    AsyncTaskDecl,
    AwaitTask,
    HttpRouteDecl,
    HttpServiceDecl,
    TimeNow,
    CryptoHash,
    ProcessRun,
    TryCatchBlock,
    WorldDecl,
)
from .expressions import expression_function_calls, expression_references
from .typesys import element_type, map_types, type_accepts


Severity = Literal["error", "warning", "info"]


@dataclass(slots=True, frozen=True)
class Diagnostic:
    severity: Severity
    message: str
    line: int
    text: str
    code: str

    def as_dict(self) -> dict[str, object]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "line": self.line,
            "text": self.text,
        }


@dataclass(slots=True, frozen=True)
class AnalysisReport:
    diagnostics: tuple[Diagnostic, ...]
    fields: tuple[str, ...]
    trails: tuple[str, ...]
    memory: tuple[str, ...]
    worlds: tuple[str, ...]
    step_count: int
    periodic_blocks: int
    expression_count: int = 0
    boolean_condition_count: int = 0
    rule_count: int = 0
    structured_block_count: int = 0
    function_count: int = 0
    event_count: int = 0
    aggregate_count: int = 0
    table_count: int = 0
    database_count: int = 0
    class_count: int = 0
    object_count: int = 0
    parameterized_macro_ready: bool = True

    @property
    def ok(self) -> bool:
        return not any(d.severity == "error" for d in self.diagnostics)

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "fields": list(self.fields),
            "trails": list(self.trails),
            "memory": list(self.memory),
            "worlds": list(self.worlds),
            "step_count": self.step_count,
            "periodic_blocks": self.periodic_blocks,
            "expression_count": self.expression_count,
            "boolean_condition_count": self.boolean_condition_count,
            "rule_count": self.rule_count,
            "structured_block_count": self.structured_block_count,
            "function_count": self.function_count,
            "event_count": self.event_count,
            "aggregate_count": self.aggregate_count,
            "table_count": self.table_count,
            "database_count": self.database_count,
            "class_count": self.class_count,
            "object_count": self.object_count,
            "parameterized_macro_ready": self.parameterized_macro_ready,
            "diagnostics": [d.as_dict() for d in self.diagnostics],
        }

    def format(self) -> str:
        lines = ["[Keim] Analyse", f"  Status: {'OK' if self.ok else 'FEHLER'}"]
        lines.append(f"  Welten: {', '.join(self.worlds) if self.worlds else '-'}")
        lines.append(f"  Felder: {', '.join(self.fields) if self.fields else '-'}")
        lines.append(f"  Spuren: {', '.join(self.trails) if self.trails else '-'}")
        lines.append(f"  Speicher: {', '.join(self.memory) if self.memory else '-'}")
        lines.append(f"  Schritte: {self.step_count}")
        lines.append(f"  Ausdrucksfelder: {self.expression_count}")
        lines.append(f"  Bool-Bedingungen: {self.boolean_condition_count}")
        lines.append(f"  Strukturblöcke: {self.structured_block_count}")
        lines.append(f"  Funktionen: {self.function_count}")
        lines.append(f"  Ereignisse: {self.event_count}")
        lines.append(f"  Aggregate: {self.aggregate_count}")
        lines.append(f"  Tabellen: {self.table_count}")
        lines.append(f"  Datenbanken: {self.database_count}")
        lines.append(f"  Klassen: {self.class_count}")
        lines.append(f"  Objekte: {self.object_count}")
        lines.append(f"  Regeln: {self.rule_count}")
        lines.append(f"  Periodische Blöcke: {self.periodic_blocks}")
        lines.append("  Parametrische Bausteine: vorbereitet")
        if self.diagnostics:
            lines.append("")
            for d in self.diagnostics:
                lines.append(f"  {d.severity.upper()} {d.code} Zeile {d.line}: {d.message}")
                if d.text:
                    lines.append(f"    {d.text}")
        else:
            lines.append("  Keine Diagnosen.")
        return "\n".join(lines)


def analyze_program(program: Program) -> AnalysisReport:
    diagnostics: list[Diagnostic] = []
    worlds: dict[str, WorldDecl] = {}
    fields: dict[str, FieldDecl] = {}
    trails: dict[str, TrailDecl] = {}
    memory: dict[str, MemoryDecl] = {}
    source_decls: list[SourceDecl] = []
    round_blocks: list[RoundBlock] = []
    periodic_blocks: list[PeriodicBlock] = []
    rules: dict[str, RuleDecl] = {}
    functions: dict[str, FunctionDecl] = {}
    events: dict[str, EventDecl] = {}
    tables: dict[str, TableDecl] = {}
    databases: dict[str, DatabaseDecl] = {}
    classes: dict[str, ClassDecl] = {}
    objects: dict[str, ObjectDecl] = {}

    for decl in program.declarations:
        match decl:
            case WorldDecl(name=name):
                if name in worlds:
                    _diag(diagnostics, "error", "DUP_WORLD", f"Welt {name!r} wurde mehrfach deklariert.", decl.loc)
                worlds[name] = decl
            case FieldDecl(name=name):
                if name in fields:
                    _diag(diagnostics, "error", "DUP_FIELD", f"Feld {name!r} wurde mehrfach deklariert.", decl.loc)
                fields[name] = decl
            case MemoryDecl(name=name):
                if name in memory:
                    _diag(diagnostics, "error", "DUP_MEMORY", f"Speicher {name!r} wurde mehrfach deklariert.", decl.loc)
                memory[name] = decl
            case TrailDecl(name=name):
                if name in trails:
                    _diag(diagnostics, "error", "DUP_TRAIL", f"Spur {name!r} wurde mehrfach deklariert.", decl.loc)
                trails[name] = decl
            case SourceDecl():
                source_decls.append(decl)
            case TableDecl(name=name):
                if name in tables:
                    _diag(diagnostics, "error", "DUP_TABLE", f"Tabelle {name!r} wurde mehrfach deklariert.", decl.loc)
                tables[name] = decl
            case TableIndexDecl(table=table, column=column):
                if table not in tables:
                    _diag(diagnostics, "error", "UNKNOWN_TABLE", f"Index verweist auf unbekannte Tabelle {table!r}.", decl.loc)
                elif column not in {col.name for col in tables[table].columns}:
                    _diag(diagnostics, "error", "UNKNOWN_COLUMN", f"Index verweist auf unbekannte Spalte {column!r}.", decl.loc)
            case DatabaseDecl(name=name):
                if name in databases:
                    _diag(diagnostics, "error", "DUP_DATABASE", f"Datenbank {name!r} wurde mehrfach deklariert.", decl.loc)
                databases[name] = decl
            case ClassDecl(name=name):
                if name in classes:
                    _diag(diagnostics, "error", "DUP_CLASS", f"Klasse {name!r} wurde mehrfach deklariert.", decl.loc)
                classes[name] = decl
            case ObjectDecl(name=name):
                if name in objects:
                    _diag(diagnostics, "error", "DUP_OBJECT", f"Objekt {name!r} wurde mehrfach deklariert.", decl.loc)
                objects[name] = decl
            case RoundBlock():
                round_blocks.append(decl)
            case PeriodicBlock():
                periodic_blocks.append(decl)
            case FunctionDecl(name=name):
                if name in functions:
                    _diag(diagnostics, "error", "DUP_FUNCTION", f"Funktion {name!r} wurde mehrfach deklariert.", decl.loc)
                functions[name] = decl
            case EventDecl(name=name):
                if name in events:
                    _diag(diagnostics, "error", "DUP_EVENT", f"Ereignis {name!r} wurde mehrfach deklariert.", decl.loc)
                events[name] = decl
            case HttpServiceDecl(name=name, port=port, routes=routes):
                seen_routes: set[tuple[str, str]] = set()
                if not 0 < port < 65536:
                    _diag(diagnostics, "error", "HTTP_PORT", f"HTTP-Dienst {name!r} nutzt ungültigen Port {port}.", decl.loc)
                for route in routes:
                    key = (route.method, route.path)
                    if key in seen_routes:
                        _diag(diagnostics, "error", "HTTP_DUP_ROUTE", f"Doppelte Route {route.method} {route.path}.", route.loc)
                    seen_routes.add(key)
            case ForeignLibraryDecl() | WebGuiDecl() | AsyncTaskDecl() | PermissionDecl() | UseDecl():
                pass
            case RuleDecl(name=name):
                if name in rules:
                    _diag(diagnostics, "error", "DUP_RULE", f"Regel {name!r} wurde mehrfach deklariert.", decl.loc)
                rules[name] = decl

    if not worlds:
        _diag(diagnostics, "error", "NO_WORLD", "Programm enthält keine Welt.", SourceLocation(0, ""))
    elif len(worlds) > 1:
        first = next(iter(worlds.values()))
        _diag(diagnostics, "warning", "MULTI_WORLD", "Mehrere Welten sind syntaktisch möglich, Runtime unterstützt aktuell eine.", first.loc)

    if not round_blocks:
        _diag(diagnostics, "error", "NO_ROUND_BLOCK", "Programm enthält keinen 'jede runde:'-Block.", SourceLocation(0, ""))
    elif len(round_blocks) > 1:
        _diag(diagnostics, "error", "MULTI_ROUND_BLOCK", "Mehrere 'jede runde:'-Blöcke sind nicht erlaubt.", round_blocks[1].loc)

    world = next(iter(worlds.values()), None)

    def class_props(name: str, seen: set[str] | None = None) -> set[str]:
        seen = seen or set()
        if name in seen:
            return set()
        seen.add(name)
        klass = classes.get(name)
        if klass is None:
            return set()
        props = set()
        if klass.parent:
            props |= class_props(klass.parent, seen)
        props |= {prop.name for prop in klass.properties}
        return props

    def class_methods(name: str, seen: set[str] | None = None) -> set[str]:
        seen = seen or set()
        if name in seen:
            return set()
        seen.add(name)
        klass = classes.get(name)
        if klass is None:
            return set()
        methods = set()
        if klass.parent:
            methods |= class_methods(klass.parent, seen)
        methods |= {method.name for method in klass.methods}
        return methods

    for klass in classes.values():
        if klass.parent is not None:
            if klass.parent not in classes:
                _diag(diagnostics, "error", "UNKNOWN_PARENT_CLASS", f"Klasse {klass.name!r} erbt von unbekannter Klasse {klass.parent!r}.", klass.loc)
            elif klass.parent == klass.name:
                _diag(diagnostics, "error", "CLASS_INHERITANCE_CYCLE", f"Klasse {klass.name!r} darf nicht von sich selbst erben.", klass.loc)

    for obj in objects.values():
        klass = classes.get(obj.class_name)
        if klass is None:
            _diag(diagnostics, "error", "UNKNOWN_CLASS", f"Objekt {obj.name!r} nutzt unbekannte Klasse {obj.class_name!r}.", obj.loc)
            continue
        known_props = class_props(obj.class_name)
        for prop, _value in obj.overrides:
            if prop not in known_props:
                _diag(diagnostics, "error", "UNKNOWN_PROPERTY", f"Objekt {obj.name!r} überschreibt unbekannte Eigenschaft {prop!r}.", obj.loc)

    for src in source_decls:
        if src.trail not in trails:
            _diag(diagnostics, "error", "UNKNOWN_TRAIL", f"Quelle verweist auf unbekannte Spur {src.trail!r}.", src.loc)
        if world is not None and (src.x >= world.width or src.y >= world.height):
            _diag(diagnostics, "error", "SOURCE_OUT_OF_BOUNDS", f"Quelle ({src.x}, {src.y}) liegt außerhalb von {world.width}x{world.height}.", src.loc)

    used_fields: set[str] = set()
    used_trails: set[str] = set()
    used_memory: set[str] = set()
    step_count = 0
    expression_count = 0
    bool_count = 0
    structured_count = 0
    aggregate_count = 0
    function_arities = {name: len(fn.params) for name, fn in functions.items()}
    call_edges: dict[str, set[str]] = {name: set() for name in rules}
    function_edges: dict[str, set[str]] = {name: set() for name in functions}

    def analyze_steps(steps: tuple[Step, ...], *, owner_rule: str | None = None) -> None:
        nonlocal step_count, expression_count, bool_count, structured_count, aggregate_count
        for step in steps:
            step_count += 1
            expression_count += int(isinstance(step, FieldCompute))
            aggregate_count += int(isinstance(step, MemoryAggregate))
            bool_count += int(isinstance(step, CompositeCondition))
            if isinstance(step, IfBlock):
                bool_count += _condition_bool_weight(step.condition)
            structured_count += int(isinstance(step, (IfBlock, RepeatBlock, TryCatchBlock)))
            _check_step(step, diagnostics, fields, trails, memory, rules, used_fields, used_trails, used_memory, function_arities, owner_rule, call_edges)
            match step:
                case IfBlock(steps=then_steps, else_steps=else_steps):
                    _check_condition_expr(step.condition, diagnostics, fields, trails, memory, used_fields, used_trails, used_memory, step.loc)
                    analyze_steps(then_steps, owner_rule=owner_rule)
                    analyze_steps(else_steps, owner_rule=owner_rule)
                case RepeatBlock(steps=child_steps):
                    analyze_steps(child_steps, owner_rule=owner_rule)
                case TryCatchBlock(try_steps=try_steps, error_memory=error_memory, catch_steps=catch_steps):
                    used_memory.add(error_memory)
                    if error_memory not in memory:
                        _diag(diagnostics, "error", "UNKNOWN_MEMORY", f"Fange-Block schreibt in unbekannten Speicher {error_memory!r}.", step.loc)
                    analyze_steps(try_steps, owner_rule=owner_rule)
                    analyze_steps(catch_steps, owner_rule=owner_rule)

    for block in [*round_blocks, *periodic_blocks]:
        if isinstance(block, PeriodicBlock) and block.interval <= 0:
            _diag(diagnostics, "error", "BAD_INTERVAL", "Periodischer Block braucht ein positives Intervall.", block.loc)
        analyze_steps(block.steps)

    for name, rule in rules.items():
        analyze_steps(rule.steps, owner_rule=name)

    for name, event in events.items():
        _check_condition_expr(event.condition, diagnostics, fields, trails, memory, used_fields, used_trails, used_memory, event.loc)
        analyze_steps(event.steps)

    for service in (decl for decl in program.declarations if isinstance(decl, HttpServiceDecl)):
        for route in service.routes:
            for mem_name, role in ((route.request_memory, "Request"), (route.response_memory, "Response"), (route.status_memory, "Status")):
                if mem_name is not None:
                    used_memory.add(mem_name)
                    if mem_name not in memory:
                        _diag(diagnostics, "error", "UNKNOWN_MEMORY", f"HTTP-{role}-Speicher {mem_name!r} existiert nicht.", route.loc)
            analyze_steps(route.steps)

    for klass in classes.values():
        for method in klass.methods:
            analyze_steps(method.steps)

    for name, fn in functions.items():
        try:
            calls = expression_function_calls(fn.expression, line=fn.loc.line, text=fn.loc.text, function_arities=function_arities, parameters=fn.params)
        except Exception as exc:
            _diag(diagnostics, "error", "BAD_FUNCTION_EXPR", f"Funktion {name!r} ist nicht auswertbar: {exc}", fn.loc)
            calls = ()
        function_edges[name] = set(calls)

    for cycle in _find_rule_cycles(function_edges):
        loc = functions[cycle[0]].loc if cycle and cycle[0] in functions else SourceLocation(0, "")
        _diag(diagnostics, "error", "FUNCTION_RECURSION", "Rekursive Ausdrucksfunktionen sind nicht erlaubt: " + " -> ".join(cycle), loc)

    for cycle in _find_rule_cycles(call_edges):
        loc = rules[cycle[0]].loc if cycle and cycle[0] in rules else SourceLocation(0, "")
        _diag(diagnostics, "error", "RULE_RECURSION", "Rekursive Regelaufrufe sind nicht erlaubt: " + " -> ".join(cycle), loc)

    for name, field in fields.items():
        if name not in used_fields:
            _diag(diagnostics, "info", "UNUSED_FIELD", f"Feld {name!r} wird nicht in Regeln verwendet.", field.loc)
        if isinstance(field.initial, (int, float)) and not 0.0 <= float(field.initial) <= 1.0:
            _diag(diagnostics, "warning", "FIELD_CLAMP", f"Initialwert von Feld {name!r} wird zur Laufzeit auf [0,1] geklemmt.", field.loc)

    for name, mem in memory.items():
        if name not in used_memory:
            _diag(diagnostics, "info", "UNUSED_MEMORY", f"Speicher {name!r} wird nicht in Regeln verwendet.", mem.loc)
        if isinstance(mem.initial, (int, float)) and not 0.0 <= float(mem.initial) <= 1.0:
            _diag(diagnostics, "warning", "MEMORY_CLAMP", f"Initialwert von Speicher {name!r} wird zur Laufzeit auf [0,1] geklemmt.", mem.loc)

    for name, trail in trails.items():
        if name not in used_trails:
            _diag(diagnostics, "info", "UNUSED_TRAIL", f"Spur {name!r} wird nicht in Regeln verwendet.", trail.loc)
        if trail.diffuse > 0.55:
            _diag(diagnostics, "warning", "HIGH_DIFFUSION", f"Spur {name!r} diffundiert sehr stark; Muster können schnell verwaschen.", trail.loc)
        if not 0.0 <= trail.initial <= 1.0:
            _diag(diagnostics, "warning", "TRAIL_CLAMP", f"Initialwert von Spur {name!r} wird zur Laufzeit auf [0,1] geklemmt.", trail.loc)

    if "futter" not in trails and any(_contains_food_condition(block.steps) for block in round_blocks):
        _diag(diagnostics, "warning", "IMPLICIT_FOOD_TRAIL", "'agent findet futter' nutzt ohne Spur 'futter' die erste vorhandene Spur.", round_blocks[0].loc if round_blocks else SourceLocation(0, ""))

    return AnalysisReport(
        diagnostics=tuple(diagnostics),
        fields=tuple(sorted(fields)),
        trails=tuple(sorted(trails)),
        memory=tuple(sorted(memory)),
        worlds=tuple(sorted(worlds)),
        step_count=step_count,
        periodic_blocks=len(periodic_blocks),
        expression_count=expression_count,
        boolean_condition_count=bool_count,
        rule_count=len(rules),
        structured_block_count=structured_count,
        function_count=len(functions),
        event_count=len(events),
        aggregate_count=aggregate_count,
        table_count=len(tables),
        database_count=len(databases),
        class_count=len(classes),
        object_count=len(objects),
    )


def _check_step(
    step: Step | Action,
    diagnostics: list[Diagnostic],
    fields: dict[str, FieldDecl],
    trails: dict[str, TrailDecl],
    memory: dict[str, MemoryDecl],
    rules: dict[str, RuleDecl],
    used_fields: set[str],
    used_trails: set[str],
    used_memory: set[str],
    function_arities: dict[str, int] | None = None,
    owner_rule: str | None = None,
    call_edges: dict[str, set[str]] | None = None,
) -> None:
    match step:
        case AgentFieldChange(field=field):
            used_fields.add(field)
            if field not in fields:
                _diag(diagnostics, "error", "UNKNOWN_FIELD", f"Unbekanntes Feld {field!r}.", step.loc)
        case FieldCompute(field=field, expression=expression):
            used_fields.add(field)
            if field not in fields:
                _diag(diagnostics, "error", "UNKNOWN_FIELD", f"Ausdruck schreibt in unbekanntes Feld {field!r}.", step.loc)
            refs = expression_references(expression, line=step.loc.line, text=step.loc.text, function_arities=function_arities or {})
            for ref in refs.fields:
                used_fields.add(ref)
                if ref not in fields:
                    _diag(diagnostics, "error", "UNKNOWN_FIELD", f"Ausdruck nutzt unbekanntes Feld {ref!r}.", step.loc)
            for ref in refs.trails:
                used_trails.add(ref)
                if ref not in trails:
                    _diag(diagnostics, "error", "UNKNOWN_TRAIL", f"Ausdruck nutzt unbekannte Spur {ref!r}.", step.loc)
            for ref in refs.memory:
                used_memory.add(ref)
                if ref not in memory:
                    _diag(diagnostics, "error", "UNKNOWN_MEMORY", f"Ausdruck nutzt unbekannten Speicher {ref!r}.", step.loc)
        case MemoryChange(memory=mem):
            used_memory.add(mem)
            if mem not in memory:
                _diag(diagnostics, "error", "UNKNOWN_MEMORY", f"Unbekannter Speicher {mem!r}.", step.loc)
        case MemoryAggregate(memory=mem, source_kind=source_kind, source=source):
            used_memory.add(mem)
            if mem not in memory:
                _diag(diagnostics, "error", "UNKNOWN_MEMORY", f"Aggregat schreibt in unbekannten Speicher {mem!r}.", step.loc)
            if source_kind == "feld":
                used_fields.add(source)
                if source not in fields:
                    _diag(diagnostics, "error", "UNKNOWN_FIELD", f"Aggregat nutzt unbekanntes Feld {source!r}.", step.loc)
            elif source_kind == "spur":
                used_trails.add(source)
                if source not in trails:
                    _diag(diagnostics, "error", "UNKNOWN_TRAIL", f"Aggregat nutzt unbekannte Spur {source!r}.", step.loc)
        case TableInsert(table=table):
            # Spaltenwerte werden zur Laufzeit aufgelöst, Schemafehler meldet Runtime.
            pass
        case TableQuery(table=table, target_memory=mem):
            used_memory.add(mem)
            if mem not in memory:
                _diag(diagnostics, "error", "UNKNOWN_MEMORY", f"Tabellensuche schreibt in unbekannten Speicher {mem!r}.", step.loc)
        case MapSet(memory=mem, key=key, value=value):
            used_memory.add(mem)
            if mem not in memory:
                _diag(diagnostics, "error", "UNKNOWN_MEMORY", f"Kartenaktion nutzt unbekannten Speicher {mem!r}.", step.loc)
            else:
                kt, vt = map_types(memory[mem].kind)
                if kt is not None and not type_accepts(key, kt):
                    _diag(diagnostics, "error", "GENERIC_TYPE", f"Karte {mem!r} erwartet Schlüsseltyp {kt}, erhalten {key!r}.", step.loc)
                if vt is not None and not type_accepts(value, vt):
                    _diag(diagnostics, "error", "GENERIC_TYPE", f"Karte {mem!r} erwartet Werttyp {vt}, erhalten {value!r}.", step.loc)
        case MapGet(memory=mem) | MapDelete(memory=mem) | MapHas(memory=mem):
            used_memory.add(mem)
            if mem not in memory:
                _diag(diagnostics, "error", "UNKNOWN_MEMORY", f"Kartenaktion nutzt unbekannten Speicher {mem!r}.", step.loc)
            if isinstance(step, (MapGet, MapHas)):
                used_memory.add(step.target_memory)
                if step.target_memory not in memory:
                    _diag(diagnostics, "error", "UNKNOWN_MEMORY", f"Kartenaktion schreibt in unbekannten Speicher {step.target_memory!r}.", step.loc)
        case JsonParse(source_memory=src, target_memory=dst) | JsonStringify(source_memory=src, target_memory=dst):
            used_memory.update({src, dst})
            for mem in (src, dst):
                if mem not in memory:
                    _diag(diagnostics, "error", "UNKNOWN_MEMORY", f"JSON-Aktion nutzt unbekannten Speicher {mem!r}.", step.loc)
        case HttpServerStart(response_memory=mem) | TimeNow(target_memory=mem) | ProcessRun(target_memory=mem):
            used_memory.add(mem)
            if mem not in memory:
                _diag(diagnostics, "error", "UNKNOWN_MEMORY", f"Systemaktion nutzt unbekannten Speicher {mem!r}.", step.loc)
        case CryptoHash(source_memory=src, target_memory=dst):
            used_memory.update({src, dst})
            for mem in (src, dst):
                if mem not in memory:
                    _diag(diagnostics, "error", "UNKNOWN_MEMORY", f"Krypto-Aktion nutzt unbekannten Speicher {mem!r}.", step.loc)
        case ListAppend(memory=mem, value=value):
            used_memory.add(mem)
            if mem not in memory:
                _diag(diagnostics, "error", "UNKNOWN_MEMORY", f"Listenaktion nutzt unbekannten Speicher {mem!r}.", step.loc)
            else:
                elem = element_type(memory[mem].kind)
                if elem is not None and not type_accepts(value, elem):
                    _diag(diagnostics, "error", "GENERIC_TYPE", f"Liste {mem!r} erwartet Elemente vom Typ {elem}, erhalten {value!r}.", step.loc)
        case ListPop(memory=mem):
            used_memory.add(mem)
            if mem not in memory:
                _diag(diagnostics, "error", "UNKNOWN_MEMORY", f"Listenaktion nutzt unbekannten Speicher {mem!r}.", step.loc)
        case DebugWatch(memory=mem):
            used_memory.add(mem)
            if mem not in memory:
                _diag(diagnostics, "error", "UNKNOWN_MEMORY", f"Debug beobachtet unbekannten Speicher {mem!r}.", step.loc)
        case GrafikCommand() | AudioCommand() | DebugSend():
            pass
        case FileTableIO():
            pass
        case WebRequest(target_memory=mem):
            used_memory.add(mem)
            if mem not in memory:
                _diag(diagnostics, "error", "UNKNOWN_MEMORY", f"Anfrage schreibt in unbekannten Speicher {mem!r}.", step.loc)
        case PathFind(cost_trail=trail):
            if trail is not None:
                used_trails.add(trail)
                if trail not in trails:
                    _diag(diagnostics, "error", "UNKNOWN_TRAIL", f"Pfadfindung nutzt unbekannte Kostenspur {trail!r}.", step.loc)
        case ExportImage(source_kind="spur", source=trail):
            used_trails.add(trail)
            if trail not in trails:
                _diag(diagnostics, "error", "UNKNOWN_TRAIL", f"Bildexport nutzt unbekannte Spur {trail!r}.", step.loc)
        case ExportImage(source_kind="feld", source=field):
            used_fields.add(field)
            if field not in fields:
                _diag(diagnostics, "error", "UNKNOWN_FIELD", f"Bildexport nutzt unbekanntes Feld {field!r}.", step.loc)
        case StartDashboard() | DeleteObject() | CollectGarbage():
            pass
        case DatabaseSave():
            pass
        case ObjectCall():
            pass
        case AgentFollowTrail(trail=trail) | AgentAvoidTrail(trail=trail) | TrailDiffuse(trail=trail) | TrailStrengthen(trail=trail):
            used_trails.add(trail)
            if trail not in trails:
                _diag(diagnostics, "error", "UNKNOWN_TRAIL", f"Unbekannte Spur {trail!r}.", step.loc)
        case FieldTrailCoupling(field=field, trail=trail) | FieldTrailEmission(field=field, trail=trail):
            used_fields.add(field)
            used_trails.add(trail)
            if field not in fields:
                _diag(diagnostics, "error", "UNKNOWN_FIELD", f"Kopplung/Emission nutzt unbekanntes Feld {field!r}.", step.loc)
            if trail not in trails:
                _diag(diagnostics, "error", "UNKNOWN_TRAIL", f"Kopplung/Emission nutzt unbekannte Spur {trail!r}.", step.loc)
        case FieldCondition(field=field, action=action):
            used_fields.add(field)
            if field not in fields:
                _diag(diagnostics, "error", "UNKNOWN_FIELD", f"Bedingung nutzt unbekanntes Feld {field!r}.", step.loc)
            _check_step(action, diagnostics, fields, trails, memory, rules, used_fields, used_trails, used_memory, function_arities, owner_rule, call_edges)
        case TrailCondition(trail=trail, action=action):
            used_trails.add(trail)
            if trail not in trails:
                _diag(diagnostics, "error", "UNKNOWN_TRAIL", f"Bedingung nutzt unbekannte Spur {trail!r}.", step.loc)
            _check_step(action, diagnostics, fields, trails, memory, rules, used_fields, used_trails, used_memory, function_arities, owner_rule, call_edges)
        case MemoryCondition(memory=mem, action=action):
            used_memory.add(mem)
            if mem not in memory:
                _diag(diagnostics, "error", "UNKNOWN_MEMORY", f"Bedingung nutzt unbekannten Speicher {mem!r}.", step.loc)
            _check_step(action, diagnostics, fields, trails, memory, rules, used_fields, used_trails, used_memory, function_arities, owner_rule, call_edges)
        case CompositeCondition(condition=condition, action=action):
            _check_condition_expr(condition, diagnostics, fields, trails, memory, used_fields, used_trails, used_memory, step.loc)
            _check_step(action, diagnostics, fields, trails, memory, rules, used_fields, used_trails, used_memory, function_arities, owner_rule, call_edges)
        case AgentFindsFoodCondition(action=action):
            used_trails.add("futter")
            _check_step(action, diagnostics, fields, trails, memory, rules, used_fields, used_trails, used_memory, function_arities, owner_rule, call_edges)
        case CallRule(name=name):
            if name not in rules:
                _diag(diagnostics, "error", "UNKNOWN_RULE", f"Unbekannte Regel {name!r}.", step.loc)
            if owner_rule is not None and call_edges is not None:
                call_edges.setdefault(owner_rule, set()).add(name)
        case IfBlock():
            # Inhalt wird von analyze_steps rekursiv geprüft; hier bleibt der Match-Zweig explizit.
            pass
        case RepeatBlock(count=count):
            if count <= 0:
                _diag(diagnostics, "error", "BAD_REPEAT", "Wiederholung braucht eine positive Anzahl.", step.loc)
        case ShowWorld():
            pass
        case _:
            pass


def _check_condition_expr(
    expr: ConditionExpr,
    diagnostics: list[Diagnostic],
    fields: dict[str, FieldDecl],
    trails: dict[str, TrailDecl],
    memory: dict[str, MemoryDecl],
    used_fields: set[str],
    used_trails: set[str],
    used_memory: set[str],
    loc: SourceLocation,
) -> None:
    match expr:
        case FieldPredicate(field=field):
            used_fields.add(field)
            if field not in fields:
                _diag(diagnostics, "error", "UNKNOWN_FIELD", f"Bedingung nutzt unbekanntes Feld {field!r}.", loc)
        case TrailPredicate(trail=trail):
            used_trails.add(trail)
            if trail not in trails:
                _diag(diagnostics, "error", "UNKNOWN_TRAIL", f"Bedingung nutzt unbekannte Spur {trail!r}.", loc)
        case MemoryPredicate(memory=mem):
            used_memory.add(mem)
            if mem not in memory:
                _diag(diagnostics, "error", "UNKNOWN_MEMORY", f"Bedingung nutzt unbekannten Speicher {mem!r}.", loc)
        case MapHasPredicate(memory=mem):
            used_memory.add(mem)
            if mem not in memory:
                _diag(diagnostics, "error", "UNKNOWN_MEMORY", f"Kartenbedingung nutzt unbekannten Speicher {mem!r}.", loc)
        case FoodPredicate():
            used_trails.add("futter")
        case ConditionNot(expr=inner):
            _check_condition_expr(inner, diagnostics, fields, trails, memory, used_fields, used_trails, used_memory, loc)
        case ConditionBinary(left=left, right=right):
            _check_condition_expr(left, diagnostics, fields, trails, memory, used_fields, used_trails, used_memory, loc)
            _check_condition_expr(right, diagnostics, fields, trails, memory, used_fields, used_trails, used_memory, loc)


def _contains_food_condition(steps: Iterable[Step]) -> bool:
    return any(_step_contains_food(step) for step in steps)


def _step_contains_food(step: Step) -> bool:
    match step:
        case AgentFindsFoodCondition():
            return True
        case CompositeCondition(condition=condition):
            return _condition_contains_food(condition)
        case IfBlock(condition=condition, steps=steps, else_steps=else_steps):
            return _condition_contains_food(condition) or _contains_food_condition(steps) or _contains_food_condition(else_steps)
        case RepeatBlock(steps=steps):
            return _contains_food_condition(steps)
        case TryCatchBlock(try_steps=try_steps, catch_steps=catch_steps):
            return _contains_food_condition(try_steps) or _contains_food_condition(catch_steps)
        case _:
            return False


def _condition_contains_food(condition: ConditionExpr) -> bool:
    match condition:
        case FoodPredicate():
            return True
        case ConditionNot(expr=expr):
            return _condition_contains_food(expr)
        case ConditionBinary(left=left, right=right):
            return _condition_contains_food(left) or _condition_contains_food(right)
        case _:
            return False




def _condition_bool_weight(condition: ConditionExpr) -> int:
    match condition:
        case ConditionBinary(left=left, right=right):
            return 1 + _condition_bool_weight(left) + _condition_bool_weight(right)
        case ConditionNot(expr=expr):
            return 1 + _condition_bool_weight(expr)
        case _:
            return 0

def _find_rule_cycles(edges: dict[str, set[str]]) -> list[list[str]]:
    cycles: list[list[str]] = []
    visiting: list[str] = []
    visited: set[str] = set()

    def dfs(node: str) -> None:
        if node in visiting:
            start = visiting.index(node)
            cycles.append([*visiting[start:], node])
            return
        if node in visited:
            return
        visiting.append(node)
        for target in sorted(edges.get(node, ())):
            if target in edges:
                dfs(target)
        visiting.pop()
        visited.add(node)

    for name in sorted(edges):
        dfs(name)
    return cycles

def _diag(diagnostics: list[Diagnostic], severity: Severity, code: str, message: str, loc: SourceLocation) -> None:
    diagnostics.append(Diagnostic(severity=severity, code=code, message=message, line=loc.line, text=loc.text))
