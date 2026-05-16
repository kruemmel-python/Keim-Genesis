from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .ast_nodes import (
    AgentAvoidTrail,
    AgentFieldChange,
    AgentFindsFoodCondition,
    AgentFollowTrail,
    AgentRest,
    AgentWander,
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
    RuleDecl,
    RoundBlock,
    ShowWorld,
    SpawnAgents,
    KillAgents,
    SpawnObject,
    SourceDecl,
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
    HttpServiceDecl,
    HttpRouteDecl,
    TimeNow,
    CryptoHash,
    ProcessRun,
    TryCatchBlock,
    WorldDecl,
)
from .expressions import expression_references


class OpCode(StrEnum):
    ALLOC_WORLD = "ALLOC_WORLD"
    ALLOC_FIELD = "ALLOC_FIELD"
    ALLOC_MEMORY = "ALLOC_MEMORY"
    ALLOC_TRAIL = "ALLOC_TRAIL"
    PLACE_SOURCE = "PLACE_SOURCE"
    ALLOC_TABLE = "ALLOC_TABLE"
    ALLOC_TABLE_INDEX = "ALLOC_TABLE_INDEX"
    ALLOC_DATABASE = "ALLOC_DATABASE"
    DEFINE_CLASS = "DEFINE_CLASS"
    ALLOC_OBJECT = "ALLOC_OBJECT"
    SPAWN_AGENTS = "SPAWN_AGENTS"
    KILL_AGENTS = "KILL_AGENTS"
    SPAWN_OBJECT = "SPAWN_OBJECT"
    DELETE_OBJECT = "DELETE_OBJECT"
    COLLECT_GARBAGE = "COLLECT_GARBAGE"
    DEFINE_FUNCTION = "DEFINE_FUNCTION"
    BEGIN_ROUND = "BEGIN_ROUND"
    BEGIN_PERIODIC = "BEGIN_PERIODIC"
    BEGIN_RULE = "BEGIN_RULE"
    BEGIN_EVENT = "BEGIN_EVENT"
    BEGIN_IF = "BEGIN_IF"
    BEGIN_ELSE = "BEGIN_ELSE"
    BEGIN_REPEAT = "BEGIN_REPEAT"
    CALL_RULE = "CALL_RULE"
    CALL_METHOD = "CALL_METHOD"
    END_BLOCK = "END_BLOCK"
    FIELD_CHANGE = "FIELD_CHANGE"
    FIELD_COMPUTE = "FIELD_COMPUTE"
    MEMORY_CHANGE = "MEMORY_CHANGE"
    MEMORY_AGGREGATE = "MEMORY_AGGREGATE"
    TABLE_INSERT = "TABLE_INSERT"
    TABLE_QUERY = "TABLE_QUERY"
    MAP_SET = "MAP_SET"
    MAP_GET = "MAP_GET"
    MAP_DELETE = "MAP_DELETE"
    MAP_HAS = "MAP_HAS"
    JSON_PARSE = "JSON_PARSE"
    JSON_STRINGIFY = "JSON_STRINGIFY"
    HTTP_SERVER_START = "HTTP_SERVER_START"
    FFI_LOAD = "FFI_LOAD"
    FFI_CALL = "FFI_CALL"
    WEBGUI_START = "WEBGUI_START"
    GRAFIK_COMMAND = "GRAFIK_COMMAND"
    AUDIO_COMMAND = "AUDIO_COMMAND"
    DEBUG_WATCH = "DEBUG_WATCH"
    DEBUG_SEND = "DEBUG_SEND"
    PERMISSION = "PERMISSION"
    ASYNC_TASK = "ASYNC_TASK"
    AWAIT_TASK = "AWAIT_TASK"
    HTTP_SERVICE_START = "HTTP_SERVICE_START"
    HTTP_ROUTE = "HTTP_ROUTE"
    TIME_NOW = "TIME_NOW"
    CRYPTO_HASH = "CRYPTO_HASH"
    PROCESS_RUN = "PROCESS_RUN"
    TRY_BEGIN = "TRY_BEGIN"
    CATCH_BEGIN = "CATCH_BEGIN"
    LIST_APPEND = "LIST_APPEND"
    LIST_POP = "LIST_POP"
    FILE_TABLE_IO = "FILE_TABLE_IO"
    WEB_REQUEST = "WEB_REQUEST"
    PATH_FIND = "PATH_FIND"
    EXPORT_IMAGE = "EXPORT_IMAGE"
    START_DASHBOARD = "START_DASHBOARD"
    DATABASE_SAVE = "DATABASE_SAVE"
    FIELD_TRAIL_COUPLE = "FIELD_TRAIL_COUPLE"
    FIELD_TRAIL_EMIT = "FIELD_TRAIL_EMIT"
    FOLLOW_TRAIL = "FOLLOW_TRAIL"
    AVOID_TRAIL = "AVOID_TRAIL"
    WANDER = "WANDER"
    REST = "REST"
    DIFFUSE_TRAIL = "DIFFUSE_TRAIL"
    STRENGTHEN_TRAIL = "STRENGTHEN_TRAIL"
    SHOW = "SHOW"
    MASK_FIELD = "MASK_FIELD"
    MASK_TRAIL = "MASK_TRAIL"
    MASK_MEMORY = "MASK_MEMORY"
    MASK_FOOD = "MASK_FOOD"
    MASK_EXPR = "MASK_EXPR"
    MASK_END = "MASK_END"


@dataclass(slots=True, frozen=True)
class ByteOp:
    pc: int
    opcode: OpCode
    args: tuple[Any, ...]
    source_line: int
    source_text: str
    note: str
    gpu_hint: str | None = None
    regime: str = "cpu"

    def as_dict(self) -> dict[str, Any]:
        return {
            "pc": self.pc,
            "opcode": self.opcode.value,
            "args": list(self.args),
            "source_line": self.source_line,
            "source_text": self.source_text,
            "note": self.note,
            "gpu_hint": self.gpu_hint,
            "regime": self.regime,
        }


@dataclass(slots=True, frozen=True)
class ByteProgram:
    source_name: str
    ops: tuple[ByteOp, ...]

    def as_dict(self) -> dict[str, Any]:
        return {"source": self.source_name, "ops": [op.as_dict() for op in self.ops], "stats": self.stats()}

    def stats(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        gpu_candidates = 0
        for op in self.ops:
            counts[op.opcode.value] = counts.get(op.opcode.value, 0) + 1
            if op.gpu_hint:
                gpu_candidates += 1
        return {"op_count": len(self.ops), "gpu_candidate_ops": gpu_candidates, **{f"op:{k}": v for k, v in sorted(counts.items())}}


class BytecodeBuilder:
    def __init__(self, source_name: str) -> None:
        self.source_name = source_name
        self.ops: list[ByteOp] = []

    def emit(self, opcode: OpCode, args: tuple[Any, ...], source_line: int, source_text: str, note: str, gpu_hint: str | None = None, regime: str = "cpu") -> None:
        self.ops.append(ByteOp(pc=len(self.ops), opcode=opcode, args=args, source_line=source_line, source_text=source_text, note=note, gpu_hint=gpu_hint, regime=regime))

    def finish(self) -> ByteProgram:
        return ByteProgram(source_name=self.source_name, ops=tuple(self.ops))


def compile_bytecode(program: Program) -> ByteProgram:
    b = BytecodeBuilder(program.source_name)
    function_arities = {decl.name: len(decl.params) for decl in program.declarations if isinstance(decl, FunctionDecl)}
    for decl in program.declarations:
        loc = getattr(decl, "loc", None)
        line = loc.line if loc else 0
        text = loc.text if loc else ""
        match decl:
            case WorldDecl(name=name, agents=agents, width=width, height=height):
                b.emit(OpCode.ALLOC_WORLD, (name, agents, width, height), line, text, "Weltzustand und Agenten-SoA anlegen")
            case FieldDecl(name=name, initial=initial, kind=kind):
                b.emit(OpCode.ALLOC_FIELD, (name, initial, kind), line, text, f"Agentenfeld {kind}[N] anlegen", "GPU buffer: typed[N]", "alloc")
            case MemoryDecl(name=name, initial=initial, kind=kind):
                b.emit(OpCode.ALLOC_MEMORY, (name, initial, kind), line, text, f"Skalaren Zeitspeicher {kind} anlegen", "scalar uniform buffer candidate", "scalar")
            case TrailDecl(name=name, initial=initial, sources=sources, diffuse=diffuse, decay=decay):
                b.emit(OpCode.ALLOC_TRAIL, (name, initial, sources, diffuse, decay), line, text, "Gitterspur float32[W*H] anlegen", "GPU buffer: float32[W*H]", "alloc")
            case SourceDecl(trail=trail, x=x, y=y, strength=strength):
                b.emit(OpCode.PLACE_SOURCE, (trail, x, y, strength), line, text, "Quelle in einer Spur setzen")
            case TableDecl(name=name, columns=columns):
                b.emit(OpCode.ALLOC_TABLE, (name, [(c.name, c.kind) for c in columns]), line, text, "Tabellenschema für relationale Laufzeitdaten anlegen")
            case TableIndexDecl(table=table, column=column):
                b.emit(OpCode.ALLOC_TABLE_INDEX, (table, column), line, text, "Hash-Index für Tabellenspalte anlegen", "host/device index sidecar candidate", "data")
            case DatabaseDecl(name=name, path=path):
                b.emit(OpCode.ALLOC_DATABASE, (name, path), line, text, "SQLite-Ziel für Tabellenexport registrieren")
            case ClassDecl(name=name, properties=properties, methods=methods, parent=parent):
                b.emit(OpCode.DEFINE_CLASS, (name, parent, {p.name: (p.initial, p.kind) for p in properties}, [m.name for m in methods]), line, text, "Klasse mit Vererbung, Eigenschaften und Methoden deklarieren")
            case ObjectDecl(name=name, class_name=class_name, overrides=overrides):
                b.emit(OpCode.ALLOC_OBJECT, (name, class_name, dict(overrides)), line, text, "Objektinstanz aus Klasse anlegen")
            case FunctionDecl(name=name, params=params, expression=expression):
                b.emit(OpCode.DEFINE_FUNCTION, (name, list(params), expression), line, text, "Reine Ausdrucksfunktion deklarieren")
            case HttpServiceDecl(name=name, port=port, workers=workers, routes=routes):
                b.emit(OpCode.HTTP_SERVICE_START, (name, port, workers, len(routes)), line, text, "HTTP-Dienst mit interner Handler-Registry starten", None, "host_parallel_io")
                for route in routes:
                    b.emit(OpCode.HTTP_ROUTE, (route.method, route.path, route.request_memory, route.response_memory, route.status_memory), route.loc.line, route.loc.text, "HTTP-Route registrieren", None, "host_parallel_io")
                    for rstep in route.steps:
                        _emit_step(b, rstep, function_arities)
            case ForeignLibraryDecl(name=name, path=path):
                b.emit(OpCode.FFI_LOAD, (name, path), line, text, "Dynamische C-Bibliothek über FFI laden", None, "host_ffi")
            case WebGuiDecl(name=name, port=port, title=title, api_base=api_base):
                b.emit(OpCode.WEBGUI_START, (name, port, title, api_base), line, text, "Lokale Web-GUI starten", None, "host_gui")
            case PermissionDecl(permission=permission):
                b.emit(OpCode.PERMISSION, (permission,), line, text, "Sandbox-Berechtigung deklarieren")
            case UseDecl(module=module):
                b.emit(OpCode.PERMISSION, ("use:" + module,), line, text, "Standardbibliothek verwenden")
            case AsyncTaskDecl(name=name, steps=steps):
                b.emit(OpCode.ASYNC_TASK, (name,), line, text, "Hintergrund-Task starten", None, "host_async")
                for astep in steps:
                    _emit_step(b, astep, function_arities)
            case RoundBlock(steps=steps):
                b.emit(OpCode.BEGIN_ROUND, (), line, text, "Regelblock läuft jede Runde")
                for step in steps:
                    _emit_step(b, step, function_arities)
                b.emit(OpCode.END_BLOCK, (), line, text, "Ende jede-runde-Block")
            case PeriodicBlock(interval=interval, steps=steps):
                b.emit(OpCode.BEGIN_PERIODIC, (interval,), line, text, f"Regelblock läuft alle {interval} Runden")
                for step in steps:
                    _emit_step(b, step, function_arities)
                b.emit(OpCode.END_BLOCK, (), line, text, "Ende periodischer Block")
            case RuleDecl(name=name, steps=steps):
                b.emit(OpCode.BEGIN_RULE, (name,), line, text, "Benannte Laufzeitregel deklarieren")
                for step in steps:
                    _emit_step(b, step, function_arities)
                b.emit(OpCode.END_BLOCK, (), line, text, "Ende benannte Regel")
            case EventDecl(name=name, condition=condition, steps=steps):
                b.emit(OpCode.BEGIN_EVENT, (name, _condition_as_dict(condition)), line, text, "Rising-Edge-Ereignis deklarieren")
                for step in steps:
                    _emit_step(b, step, function_arities)
                b.emit(OpCode.END_BLOCK, (), line, text, "Ende Ereignisblock")
            case _:
                raise TypeError(f"Unbekannter Top-Level-Knoten: {decl!r}")
    return b.finish()


def _emit_step(b: BytecodeBuilder, step: Step, function_arities: dict[str, int]) -> None:
    loc = getattr(step, "loc", None)
    line = loc.line if loc else 0
    text = loc.text if loc else ""
    match step:
        case FieldCondition(field=field, op=op, value=value, action=action):
            b.emit(OpCode.MASK_FIELD, (field, op, value), line, text, "Agentenmaske aus Feldbedingung")
            _emit_step(b, action, function_arities)
            b.emit(OpCode.MASK_END, (), line, text, "Feldmaske verlassen")
        case TrailCondition(trail=trail, op=op, value=value, action=action):
            b.emit(OpCode.MASK_TRAIL, (trail, op, value), line, text, "Agentenmaske aus Spurwert")
            _emit_step(b, action, function_arities)
            b.emit(OpCode.MASK_END, (), line, text, "Spurmaske verlassen")
        case MemoryCondition(memory=memory, op=op, value=value, action=action):
            b.emit(OpCode.MASK_MEMORY, (memory, op, value), line, text, "Skalaren Speicher als Broadcast-Maske testen")
            _emit_step(b, action, function_arities)
            b.emit(OpCode.MASK_END, (), line, text, "Speichermaske verlassen")
        case CompositeCondition(condition=condition, action=action):
            b.emit(OpCode.MASK_EXPR, (_condition_as_dict(condition),), line, text, "Bedingungsalgebra zu einer Agentenmaske auswerten", "fused boolean mask kernel candidate", "mask")
            _emit_step(b, action, function_arities)
            b.emit(OpCode.MASK_END, (), line, text, "Ausdrucksmaske verlassen")
        case AgentFindsFoodCondition(action=action):
            b.emit(OpCode.MASK_FOOD, (), line, text, "Ereignismaske: Agent findet Futter")
            _emit_step(b, action, function_arities)
            b.emit(OpCode.MASK_END, (), line, text, "Ereignismaske verlassen")
        case IfBlock(condition=condition, steps=steps, else_steps=else_steps):
            b.emit(OpCode.BEGIN_IF, (_condition_as_dict(condition),), line, text, "Strukturierter Wenn-Block mit Maskenweitergabe", "structured mask control", "control")
            for child in steps:
                _emit_step(b, child, function_arities)
            if else_steps:
                b.emit(OpCode.BEGIN_ELSE, (), line, text, "Sonst-Zweig der invertierten Maske")
                for child in else_steps:
                    _emit_step(b, child, function_arities)
            b.emit(OpCode.END_BLOCK, (), line, text, "Ende Wenn-Block")
        case TryCatchBlock(try_steps=try_steps, error_memory=error_memory, catch_steps=catch_steps):
            b.emit(OpCode.TRY_BEGIN, (error_memory,), line, text, "Interne Fehlergrenze: KeimRuntimeError wird im Programm gefangen")
            for child in try_steps:
                _emit_step(b, child, function_arities)
            b.emit(OpCode.CATCH_BEGIN, (error_memory,), line, text, "Fange-Zweig erhält Fehlermeldung im Speicher")
            for child in catch_steps:
                _emit_step(b, child, function_arities)
            b.emit(OpCode.END_BLOCK, (), line, text, "Ende Versuche/Fange")
        case RepeatBlock(count=count, steps=steps):
            b.emit(OpCode.BEGIN_REPEAT, (count,), line, text, f"Strukturierte Wiederholung {count}x")
            for child in steps:
                _emit_step(b, child, function_arities)
            b.emit(OpCode.END_BLOCK, (), line, text, "Ende Wiederholung")
        case CallRule(name=name):
            b.emit(OpCode.CALL_RULE, (name,), line, text, "Benannte Laufzeitregel aufrufen")
        case AgentFieldChange(field=field, kind=kind, amount=amount):
            b.emit(OpCode.FIELD_CHANGE, (field, kind, amount), line, text, "Batch-Update auf Agentenfeld", "elementwise field kernel", "elementwise")
        case FieldCompute(field=field, expression=expression):
            refs = expression_references(expression, line=line, text=text, function_arities=function_arities).as_dict()
            b.emit(OpCode.FIELD_COMPUTE, (field, expression, refs), line, text, "Agentenlokalen Ausdruck in Feld schreiben", "fused expression/gather kernel", "elementwise")
        case MemoryChange(memory=memory, kind=kind, amount=amount):
            b.emit(OpCode.MEMORY_CHANGE, (memory, kind, amount), line, text, "Skalaren Zeitspeicher aktualisieren")
        case MemoryAggregate(memory=memory, aggregate=aggregate, source_kind=source_kind, source=source):
            b.emit(OpCode.MEMORY_AGGREGATE, (memory, aggregate, source_kind, source), line, text, "Reduktion aus Feld/Spur in Speicher", "parallel reduction kernel candidate", "reduction")
        case TableInsert(table=table, values=values):
            b.emit(OpCode.TABLE_INSERT, (table, dict(values)), line, text, "Strukturierten Datensatz in Runtime-Tabelle einfügen")
        case DatabaseSave(database=database, table=table):
            b.emit(OpCode.DATABASE_SAVE, (database, table), line, text, "Neue Tabellenzeilen nach SQLite persistieren")
        case TableQuery(table=table, column=column, op=op, value=value, target_memory=target_memory):
            b.emit(OpCode.TABLE_QUERY, (table, column, op, value, target_memory), line, text, "Tabellensuche mit optionalem Index")
        case MapSet(memory=memory, key=key, value=value):
            b.emit(OpCode.MAP_SET, (memory, key, value), line, text, "HashMap-Schreibzugriff auf karte-Speicher")
        case MapGet(memory=memory, key=key, target_memory=target_memory):
            b.emit(OpCode.MAP_GET, (memory, key, target_memory), line, text, "HashMap-Lesezugriff aus karte-Speicher")
        case MapDelete(memory=memory, key=key):
            b.emit(OpCode.MAP_DELETE, (memory, key), line, text, "HashMap-Eintrag freigeben")
        case MapHas(memory=memory, key=key, target_memory=target_memory):
            b.emit(OpCode.MAP_HAS, (memory, key, target_memory), line, text, "HashMap-Präsenztest in bool-Speicher schreiben")
        case JsonParse(source_memory=source_memory, target_memory=target_memory):
            b.emit(OpCode.JSON_PARSE, (source_memory, target_memory), line, text, "JSON-Text in karte/liste-Wert parsen")
        case JsonStringify(source_memory=source_memory, target_memory=target_memory):
            b.emit(OpCode.JSON_STRINGIFY, (source_memory, target_memory), line, text, "Keim-Wert nach JSON-Text serialisieren")
        case HttpServerStart(port=port, response_memory=response_memory):
            b.emit(OpCode.HTTP_SERVER_START, (port, response_memory), line, text, "Minimalen HTTP-Server als system.netz-Batterie starten")
        case FfiCall(library=library, function=function, args=args, target_memory=target_memory, result_kind=result_kind):
            b.emit(OpCode.FFI_CALL, (library, function, list(args), target_memory, result_kind), line, text, "C-FFI-Funktion aufrufen", None, "host_ffi")
        case GrafikCommand(kind=kind, args=args):
            b.emit(OpCode.GRAFIK_COMMAND, (kind, list(args)), line, text, "system.grafik: Canvas-/Host-Kommando", None, "host_gui")
        case AudioCommand(kind=kind, args=args):
            b.emit(OpCode.AUDIO_COMMAND, (kind, list(args)), line, text, "system.audio: Audio-Event", None, "host_audio")
        case DebugWatch(memory=memory):
            b.emit(OpCode.DEBUG_WATCH, (memory,), line, text, "DebugBus beobachtet Speicher")
        case DebugSend(label=label):
            b.emit(OpCode.DEBUG_SEND, (label,), line, text, "DebugBus sendet Marke")
        case AwaitTask(name=name, target_memory=target_memory):
            b.emit(OpCode.AWAIT_TASK, (name, target_memory), line, text, "Hintergrund-Task abwarten", None, "host_async")
        case TimeNow(target_memory=target_memory):
            b.emit(OpCode.TIME_NOW, (target_memory,), line, text, "system.zeit: aktuelle UTC-Zeit schreiben")
        case CryptoHash(algorithm=algorithm, source_memory=source_memory, target_memory=target_memory):
            b.emit(OpCode.CRYPTO_HASH, (algorithm, source_memory, target_memory), line, text, "system.krypto: Hash über Speicherwert")
        case ProcessRun(command=command, target_memory=target_memory):
            b.emit(OpCode.PROCESS_RUN, (command, target_memory), line, text, "system.prozess: externen Prozess starten")
        case ListAppend(memory=memory, value=value):
            b.emit(OpCode.LIST_APPEND, (memory, value), line, text, "Dynamisches Listenwachstum im Speicherslot")
        case ListPop(memory=memory, target_memory=target_memory):
            b.emit(OpCode.LIST_POP, (memory, target_memory), line, text, "Dynamisches Listen-Pop mit optionaler Rückgabe")
        case FileTableIO(mode=mode, fmt=fmt, path=path, table=table):
            b.emit(OpCode.FILE_TABLE_IO, (mode, fmt, path, table), line, text, "datei-Batterie für CSV/JSON")
        case WebRequest(method=method, url=url, target_memory=target_memory):
            b.emit(OpCode.WEB_REQUEST, (method, url, target_memory), line, text, "anfrage-Batterie für Web-APIs", None, "io")
        case PathFind(start_x=start_x, start_y=start_y, goal_x=goal_x, goal_y=goal_y, cost_trail=cost_trail, target_table=target_table):
            b.emit(OpCode.PATH_FIND, (start_x, start_y, goal_x, goal_y, cost_trail, target_table), line, text, "A*-Pfadfindung in Tabelle schreiben", "frontier expansion kernel candidate", "graph")
        case ExportImage(fmt=fmt, path=path, source_kind=source_kind, source=source):
            b.emit(OpCode.EXPORT_IMAGE, (fmt, path, source_kind, source), line, text, "PNG/BMP-Visualisierung aus Feld/Spur", "render kernel candidate", "render")
        case StartDashboard(path=path):
            b.emit(OpCode.START_DASHBOARD, (path,), line, text, "Web-Dashboard-Snapshot erzeugen")
        case ObjectCall(object_name=object_name, method=method):
            b.emit(OpCode.CALL_METHOD, (object_name, method), line, text, "Objektmethode mit selbst-Kontext ausführen")
        case SpawnAgents(count=count):
            b.emit(OpCode.SPAWN_AGENTS, (count,), line, text, "Dynamische Agentenallokation zur Laufzeit")
        case KillAgents(count=count):
            b.emit(OpCode.KILL_AGENTS, (count,), line, text, "Dynamische Agentenfreigabe aus aktiver Maske")
        case SpawnObject(name=name, class_name=class_name, overrides=overrides):
            b.emit(OpCode.SPAWN_OBJECT, (name, class_name, dict(overrides)), line, text, "Dynamische Objektinstanz erzeugen")
        case DeleteObject(name=name):
            b.emit(OpCode.DELETE_OBJECT, (name,), line, text, "Objekt-Referenz freigeben")
        case CollectGarbage():
            b.emit(OpCode.COLLECT_GARBAGE, (), line, text, "Nicht referenzierte dynamische Objekte sammeln")
        case AgentFollowTrail(trail=trail):
            b.emit(OpCode.FOLLOW_TRAIL, (trail,), line, text, "Agenten bewegen sich entlang eines Spurgradienten", "subqg_migrate_agents_autonomous_kernel", "motion")
        case AgentAvoidTrail(trail=trail):
            b.emit(OpCode.AVOID_TRAIL, (trail,), line, text, "Agenten bewegen sich gegen einen Spurgradienten", "subqg_migrate_agents_autonomous_kernel inverted", "motion")
        case AgentWander(chance=chance):
            b.emit(OpCode.WANDER, (chance,), line, text, "Zufallsbewegung")
        case AgentRest():
            b.emit(OpCode.REST, (), line, text, "Agent ruht")
        case FieldTrailCoupling(field=field, trail=trail, kind=kind, amount=amount):
            b.emit(OpCode.FIELD_TRAIL_COUPLE, (field, trail, kind, amount), line, text, "Spur->Feld-Gather", "gather trail[x,y] -> field[i]", "gather")
        case FieldTrailEmission(field=field, trail=trail, amount=amount):
            b.emit(OpCode.FIELD_TRAIL_EMIT, (field, trail, amount), line, text, "Feld->Spur-Scatter", "segmented or atomic scatter field[i] -> trail[x,y]", "scatter")
        case TrailDiffuse(trail=trail):
            b.emit(OpCode.DIFFUSE_TRAIL, (trail,), line, text, "Diffusion/Decay", "execute_fused_diffusion_on_gpu or mycel_diffuse_decay", "diffusion")
        case TrailStrengthen(trail=trail, amount=amount):
            b.emit(OpCode.STRENGTHEN_TRAIL, (trail, amount), line, text, "Agenten verstärken Spur", "segmented or atomic scatter constant -> trail[x,y]", "scatter")
        case ShowWorld(target=target):
            b.emit(OpCode.SHOW, (target,), line, text, "ASCII/Renderausgabe", "render_frame_buf candidate", "render")
        case _:
            raise TypeError(f"Unbekannter Step-Knoten: {step!r}")


def _condition_value_as_data(value: Any) -> Any:
    if isinstance(value, SelfPropertyRef):
        return {"kind": "self", "property": value.name}
    return value


def _condition_as_dict(condition: ConditionExpr) -> dict[str, Any]:
    match condition:
        case FieldPredicate(field=field, op=op, value=value):
            return {"kind": "field", "field": field, "op": op, "value": _condition_value_as_data(value)}
        case TrailPredicate(trail=trail, op=op, value=value):
            return {"kind": "trail", "trail": trail, "op": op, "value": _condition_value_as_data(value)}
        case MemoryPredicate(memory=memory, op=op, value=value):
            return {"kind": "memory", "memory": memory, "op": op, "value": _condition_value_as_data(value)}
        case MapHasPredicate(memory=memory, key=key):
            return {"kind": "map_has", "memory": memory, "key": _condition_value_as_data(key)}
        case FoodPredicate():
            return {"kind": "food"}
        case ConditionNot(expr=expr):
            return {"kind": "not", "expr": _condition_as_dict(expr)}
        case ConditionBinary(op=op, left=left, right=right):
            return {"kind": op, "left": _condition_as_dict(left), "right": _condition_as_dict(right)}
        case _:
            raise TypeError(f"Unbekannte Bedingung: {condition!r}")
