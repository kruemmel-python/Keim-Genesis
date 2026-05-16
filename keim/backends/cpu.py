from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from random import Random
import sqlite3
import json
import csv
import heapq
import hashlib
import shlex
import subprocess
from datetime import datetime, timezone
import math
import struct
import zlib
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen, Request
from time import perf_counter
from typing import Any
from concurrent.futures import ThreadPoolExecutor, Future

from ..ffi import ForeignLibrary
from ..webui import start_web_gui, WebGuiServer
from ..debugbus import DebugBus
from ..sandbox import SandboxPolicy
from ..kit import GrafikRuntime, AudioRuntime

from ..ast_nodes import (
    Action,
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
    MethodDecl,
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
from ..errors import KeimRuntimeError
from ..expressions import CompiledAgentExpression, CompiledUserFunction, compile_agent_expression, compile_user_function
from ..typesys import KeimType, parse_type, coerce_value, to_float, clamp01, element_type, map_types


@dataclass(slots=True)
class CpuConfig:
    seed: int = 7
    show_every: int = 10
    quiet: bool = False
    collect_metrics: bool = True
    debug_bus: DebugBus | None = None
    sandbox: SandboxPolicy | None = None


@dataclass(slots=True)
class TrailState:
    name: str
    values: list[float]
    sources: list[float]
    diffuse: float
    decay: float



@dataclass(slots=True)
class TableState:
    name: str
    columns: list[tuple[str, str]]
    rows: list[dict[str, Any]] = field(default_factory=list)
    indices: dict[str, dict[Any, list[int]]] = field(default_factory=dict)


@dataclass(slots=True)
class ClassState:
    name: str
    properties: dict[str, object]
    property_types: dict[str, KeimType]
    methods: dict[str, tuple[Step, ...]]
    parent: str | None = None


@dataclass(slots=True)
class ObjectState:
    name: str
    class_name: str
    properties: dict[str, object]
    refcount: int = 1
    dynamic: bool = False
    alive: bool = True
    marked: bool = False


@dataclass(slots=True)
class WorldState:
    name: str
    agents: int
    width: int
    height: int
    x: list[int]
    y: list[int]
    fields: dict[str, list[object]] = field(default_factory=dict)
    field_types: dict[str, KeimType] = field(default_factory=dict)
    trails: dict[str, TrailState] = field(default_factory=dict)
    memory: dict[str, object] = field(default_factory=dict)
    memory_types: dict[str, KeimType] = field(default_factory=dict)


@dataclass(slots=True)
class CpuReport:
    world: str
    rounds: int
    agents: int
    width: int
    height: int
    elapsed: float
    food_hits_total: int
    fields: dict[str, float]
    trails: dict[str, float]
    memory: dict[str, float]
    metrics: list[dict[str, Any]]

    @property
    def ms_per_round(self) -> float:
        return self.elapsed / max(1, self.rounds) * 1000.0

    @property
    def agent_rounds_per_second(self) -> float:
        return self.agents * self.rounds / max(self.elapsed, 1e-9)

    def as_dict(self) -> dict[str, Any]:
        return {
            "world": self.world,
            "rounds": self.rounds,
            "agents": self.agents,
            "width": self.width,
            "height": self.height,
            "elapsed_seconds": self.elapsed,
            "ms_per_round": self.ms_per_round,
            "agent_rounds_per_second": self.agent_rounds_per_second,
            "food_hits_total": self.food_hits_total,
            "field_means": self.fields,
            "trail_means": self.trails,
            "memory": self.memory,
            "metrics": self.metrics,
        }


class CpuBackend:
    backend_tag = "cpu"

    def __init__(self, config: CpuConfig) -> None:
        self.config = config
        self.rng = Random(config.seed)
        self.world: WorldState | None = None
        self.round_steps: tuple[Step, ...] = ()
        self.periodic_blocks: list[tuple[int, tuple[Step, ...]]] = []
        self.rules: dict[str, tuple[Step, ...]] = {}
        self.events: list[tuple[str, object, tuple[Step, ...]]] = []
        self._event_active: dict[str, bool] = {}
        self.tables: dict[str, TableState] = {}
        self.databases: dict[str, str] = {}
        self._db_exported_rows: dict[tuple[str, str], int] = {}
        self.classes: dict[str, ClassState] = {}
        self.objects: dict[str, ObjectState] = {}
        self.functions: dict[str, CompiledUserFunction] = {}
        self._function_arities: dict[str, int] = {}
        self._call_stack: list[str] = []
        self._start = perf_counter()
        self._food_hits_last = 0
        self._food_hits_total = 0
        self._resting: list[bool] = []
        self.metrics: list[dict[str, Any]] = []
        self.backend_metrics: dict[str, int] = {}
        self._expr_cache: dict[str, CompiledAgentExpression] = {}
        self._dynamic_object_serial = 0
        self._dashboard_path: str | None = None
        self._http_servers: dict[int, ThreadingHTTPServer] = {}
        self._http_lock = threading.RLock()
        self._http_routes: dict[int, dict[tuple[str, str], HttpRouteDecl]] = {}
        self._ffi_libraries: dict[str, ForeignLibrary] = {}
        self._web_guis: dict[int, WebGuiServer] = {}
        self._executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="keim-bg")
        self._async_tasks: dict[str, Future[None]] = {}
        self.debug_bus: DebugBus = config.debug_bus or DebugBus()
        self.sandbox: SandboxPolicy = config.sandbox or SandboxPolicy()
        self.requested_permissions: set[str] = set()
        self.grafik = GrafikRuntime()
        self.audio = AudioRuntime()

    def load(self, program: Program) -> None:
        self._start = perf_counter()
        function_decls = [decl for decl in program.declarations if isinstance(decl, FunctionDecl)]
        self._function_arities = {decl.name: len(decl.params) for decl in function_decls}
        for decl in function_decls:
            if decl.name in self.functions:
                raise KeimRuntimeError(f"Funktion {decl.name!r} wurde mehrfach geladen.")
            self.functions[decl.name] = compile_user_function(
                decl.name,
                decl.params,
                decl.expression,
                function_arities=self._function_arities,
                line=decl.loc.line,
                text=decl.loc.text,
            )

        self.requested_permissions = {decl.permission for decl in program.declarations if isinstance(decl, PermissionDecl)}
        self.sandbox = self.sandbox.merged(self.requested_permissions)

        for decl in program.declarations:
            match decl:
                case WorldDecl(name=name, agents=agents, width=width, height=height):
                    self._create_world(name, agents, width, height)
                case FieldDecl(name=name, initial=initial, kind=kind):
                    self._require_world()
                    self._create_field(name, initial, kind)
                case MemoryDecl(name=name, initial=initial, kind=kind):
                    self._require_world()
                    self._create_memory(name, initial, kind)
                case TrailDecl(name=name, initial=initial, sources=sources, diffuse=diffuse, decay=decay):
                    self._require_world()
                    self._create_trail(name, initial, sources, diffuse, decay)
                case SourceDecl(trail=trail, x=x, y=y, strength=strength):
                    self._require_world()
                    self._place_source(trail, x, y, strength)
                case TableDecl(name=name, columns=columns):
                    if name in self.tables:
                        raise KeimRuntimeError(f"Tabelle {name!r} wurde mehrfach geladen.")
                    self.tables[name] = TableState(name=name, columns=[(c.name, c.kind) for c in columns])
                case TableIndexDecl(table=table, column=column):
                    tbl = self.tables.get(table)
                    if tbl is None:
                        raise KeimRuntimeError(f"Index verweist auf unbekannte Tabelle {table!r}.")
                    if column not in [name for name, _ in tbl.columns]:
                        raise KeimRuntimeError(f"Index verweist auf unbekannte Spalte {column!r} in Tabelle {table!r}.")
                    tbl.indices.setdefault(column, {})
                    self._rebuild_table_index(tbl, column)
                case DatabaseDecl(name=name, path=path):
                    if name in self.databases:
                        raise KeimRuntimeError(f"Datenbank {name!r} wurde mehrfach geladen.")
                    self.databases[name] = path
                case ClassDecl(name=name, properties=properties, methods=methods, parent=parent):
                    if name in self.classes:
                        raise KeimRuntimeError(f"Klasse {name!r} wurde mehrfach geladen.")
                    base_props: dict[str, object] = {}
                    base_types: dict[str, KeimType] = {}
                    base_methods: dict[str, tuple[Step, ...]] = {}
                    if parent is not None:
                        parent_state = self.classes.get(parent)
                        if parent_state is None:
                            raise KeimRuntimeError(f"Klasse {name!r} erbt von unbekannter Klasse {parent!r}.")
                        base_props.update(parent_state.properties)
                        base_types.update(parent_state.property_types)
                        base_methods.update(parent_state.methods)
                    prop_map = dict(base_props)
                    type_map = dict(base_types)
                    for prop in properties:
                        kind = parse_type(prop.kind)
                        prop_map[prop.name] = coerce_value(prop.initial, kind)
                        type_map[prop.name] = kind
                    method_map = dict(base_methods)
                    method_map.update({method.name: method.steps for method in methods})
                    self.classes[name] = ClassState(name=name, properties=prop_map, property_types=type_map, methods=method_map, parent=parent)
                case ObjectDecl(name=name, class_name=class_name, overrides=overrides):
                    klass = self.classes.get(class_name)
                    if klass is None:
                        raise KeimRuntimeError(f"Objekt {name!r} nutzt unbekannte Klasse {class_name!r}.")
                    props = dict(klass.properties)
                    for prop, value in overrides:
                        if prop not in props:
                            raise KeimRuntimeError(f"Objekt {name!r} überschreibt unbekannte Eigenschaft {prop!r}.")
                        props[prop] = coerce_value(value, klass.property_types.get(prop, KeimType.FLOAT))
                    self.objects[name] = ObjectState(name=name, class_name=class_name, properties=props, dynamic=False)
                case RoundBlock(steps=steps):
                    self.round_steps = steps
                case PeriodicBlock(interval=interval, steps=steps):
                    self.periodic_blocks.append((interval, steps))
                case FunctionDecl():
                    pass
                case EventDecl(name=name, condition=condition, steps=steps):
                    self.events.append((name, condition, steps))
                    self._event_active[name] = False
                case HttpServiceDecl():
                    self.sandbox.require("netz", "HTTP-Dienst")
                    self._load_http_service(decl)
                case PermissionDecl() | UseDecl():
                    pass
                case ForeignLibraryDecl(name=name, path=path):
                    self.sandbox.require("ffi", "bibliothek laedt")
                    if name in self._ffi_libraries:
                        raise KeimRuntimeError(f"Bibliothek {name!r} wurde mehrfach geladen.")
                    self._ffi_libraries[name] = ForeignLibrary(name, path)
                case WebGuiDecl(name=name, port=port, title=title, api_base=api_base):
                    if port in self._web_guis:
                        raise KeimRuntimeError(f"Web-GUI-Port {port} ist bereits belegt.")
                    self._web_guis[port] = start_web_gui(name=name, port=port, title=title, api_base=api_base)
                case AsyncTaskDecl(name=name, steps=steps):
                    if name in self._async_tasks:
                        raise KeimRuntimeError(f"Hintergrund-Task {name!r} wurde mehrfach gestartet.")
                    self._async_tasks[name] = self._executor.submit(self._execute_steps, steps, 0, None)
                case RuleDecl(name=name, steps=steps):
                    if name in self.rules:
                        raise KeimRuntimeError(f"Regel {name!r} wurde mehrfach geladen.")
                    self.rules[name] = steps
                case _:
                    raise KeimRuntimeError(f"Unbekannte Deklaration: {decl!r}")

        if self.world is None:
            raise KeimRuntimeError("Programm enthält keine Welt.")
        if not self.round_steps:
            raise KeimRuntimeError("Programm enthält keinen 'jede runde:'-Block.")

    def step(self, tick: int) -> None:
        world = self._world()
        self._food_hits_last = 0
        self._resting = [False] * world.agents
        self.backend_metrics = {}

        self._execute_steps(self.round_steps, tick, None)
        for interval, steps in self.periodic_blocks:
            if interval > 0 and tick % interval == 0:
                self._execute_steps(steps, tick, None)

        self._process_events(tick)
        self._collect_garbage(auto=True)

        if self.config.collect_metrics:
            row = self._make_metrics(tick)
            row.update(self.backend_metrics)
            self.metrics.append(row)

    def shutdown_http(self) -> None:
        """Stoppt alle durch Keim gestarteten HTTP-Dienste."""
        for server in list(self._http_servers.values()):
            server.shutdown()
            server.server_close()
        self._http_servers.clear()
        self._http_routes.clear()

    def _execute_steps(self, steps: tuple[Step, ...], tick: int, mask: list[bool] | None, self_obj: ObjectState | None = None) -> None:
        for step in steps:
            match step:
                case FieldCondition(field=field, op=op, value=value, action=action):
                    self._apply_action(action, self._and_mask(mask, self._field_mask(field, op, self._condition_value(value, self_obj))), tick, self_obj)
                case TrailCondition(trail=trail, op=op, value=value, action=action):
                    self._apply_action(action, self._and_mask(mask, self._trail_mask(trail, op, self._condition_value(value, self_obj))), tick, self_obj)
                case MemoryCondition(memory=memory, op=op, value=value, action=action):
                    self._apply_action(action, self._and_mask(mask, self._memory_mask(memory, op, self._condition_value(value, self_obj))), tick, self_obj)
                case CompositeCondition(condition=condition, action=action):
                    self._apply_action(action, self._and_mask(mask, self._condition_mask(condition, self_obj)), tick, self_obj)
                case AgentFindsFoodCondition(action=action):
                    local_mask = self._finds_food_mask()
                    hits = sum(1 for value in self._and_mask(mask, local_mask) or local_mask if value)
                    self._food_hits_last += hits
                    self._food_hits_total += hits
                    self._apply_action(action, self._and_mask(mask, local_mask), tick, self_obj)
                case IfBlock(condition=condition, steps=then_steps, else_steps=else_steps):
                    condition_mask = self._condition_mask(condition, self_obj)
                    then_mask = self._and_mask(mask, condition_mask)
                    if then_mask is None or any(then_mask):
                        self._execute_steps(then_steps, tick, then_mask, self_obj)
                    if else_steps:
                        else_mask = self._and_mask(mask, [not value for value in condition_mask])
                        if else_mask is None or any(else_mask):
                            self._execute_steps(else_steps, tick, else_mask, self_obj)
                case TryCatchBlock(try_steps=try_steps, error_memory=error_memory, catch_steps=catch_steps):
                    try:
                        self._execute_steps(try_steps, tick, mask, self_obj)
                    except KeimRuntimeError as exc:
                        world = self._world()
                        if error_memory in world.memory:
                            world.memory[error_memory] = coerce_value(str(exc), world.memory_types.get(error_memory, KeimType.TEXT))
                        self.backend_metrics["errors:caught"] = self.backend_metrics.get("errors:caught", 0) + 1
                        self._execute_steps(catch_steps, tick, mask, self_obj)
                case RepeatBlock(count=count, steps=child_steps):
                    for _ in range(count):
                        self._execute_steps(child_steps, tick, mask, self_obj)
                case ShowWorld(target=target):
                    if mask is None and not self.config.quiet and self.config.show_every > 0 and tick % self.config.show_every == 0:
                        print(self.render_ascii(tick))
                case _:
                    self._apply_step(step, mask, tick, self_obj)

    def summary(self, rounds: int) -> CpuReport:
        report = self.report(rounds)
        if self.config.quiet:
            return report
        world = self._world()
        print()
        print("[Keim] Lauf beendet")
        print(f"  Welt:          {world.name}")
        print(f"  Backend:       {self.backend_tag}")
        print(f"  Runden:        {rounds}")
        print(f"  Agenten:       {world.agents}")
        print(f"  Gitter:        {world.width} x {world.height}")
        print(f"  Felder:        {', '.join(world.fields) if world.fields else '-'}")
        print(f"  Spuren:        {', '.join(world.trails) if world.trails else '-'}")
        print(f"  Speicher:      {', '.join(world.memory) if world.memory else '-'}")
        print(f"  Regeln:        {', '.join(self.rules) if self.rules else '-'}")
        print(f"  Ereignisse:    {', '.join(name for name, _, _ in self.events) if self.events else '-'}")
        print(f"  Funktionen:    {', '.join(self.functions) if self.functions else '-'}")
        print(f"  Tabellen:      {', '.join(self.tables) if self.tables else '-'}")
        print(f"  Objekte:       {', '.join(self.objects) if self.objects else '-'}")
        print(f"  Treffer ges.:  {self._food_hits_total}")
        print(f"  Zeit:          {report.elapsed:.3f}s")
        print(f"  Zeit/Runde:    {report.ms_per_round:.3f} ms")
        return report

    def report(self, rounds: int) -> CpuReport:
        world = self._world()
        elapsed = perf_counter() - self._start
        return CpuReport(
            world=world.name,
            rounds=rounds,
            agents=world.agents,
            width=world.width,
            height=world.height,
            elapsed=elapsed,
            food_hits_total=self._food_hits_total,
            fields={name: self._mean(values) for name, values in world.fields.items()},
            trails={name: self._mean(trail.values) for name, trail in world.trails.items()},
            memory=dict(world.memory),
            metrics=list(self.metrics),
        )

    def render_ascii(self, tick: int | None = None) -> str:
        world = self._world()
        chars = [" "] * (world.width * world.height)
        if world.trails:
            max_values = [0.0] * (world.width * world.height)
            max_sources = [0.0] * (world.width * world.height)
            for trail in world.trails.values():
                for i, value in enumerate(trail.values):
                    if value > max_values[i]:
                        max_values[i] = value
                    if trail.sources[i] > max_sources[i]:
                        max_sources[i] = trail.sources[i]
            for i, value in enumerate(max_values):
                if max_sources[i] > 0.0:
                    chars[i] = "*"
                elif value > 0.70:
                    chars[i] = "+"
                elif value > 0.35:
                    chars[i] = "."
                elif value > 0.10:
                    chars[i] = ","
        for i, (ax, ay) in enumerate(zip(world.x, world.y)):
            chars[self._idx(ax, ay)] = "r" if i < len(self._resting) and self._resting[i] else "a"
        lines = []
        if tick is not None:
            mem = f" | Speicher: {world.memory}" if world.memory else ""
            lines.append(f"[Keim] Runde {tick} | Treffer letzte Runde: {self._food_hits_last}{mem}")
        for y in range(world.height):
            lines.append("".join(chars[y * world.width:(y + 1) * world.width]))
        return "\n".join(lines)

    def _create_world(self, name: str, agents: int, width: int, height: int) -> None:
        if self.world is not None:
            raise KeimRuntimeError("Aktuell ist nur eine Welt pro Programm erlaubt.")
        self.world = WorldState(
            name=name,
            agents=agents,
            width=width,
            height=height,
            x=[self.rng.randrange(width) for _ in range(agents)],
            y=[self.rng.randrange(height) for _ in range(agents)],
        )
        self._resting = [False] * agents

    def _create_field(self, name: str, initial: object, kind: str = "zahl") -> None:
        world = self._world()
        if name in world.fields:
            raise KeimRuntimeError(f"Feld {name!r} existiert bereits.")
        k = parse_type(kind)
        world.field_types[name] = k
        world.fields[name] = [coerce_value(initial, k) for _ in range(world.agents)]

    def _create_memory(self, name: str, initial: object, kind: str = "zahl") -> None:
        world = self._world()
        if name in world.memory:
            raise KeimRuntimeError(f"Speicher {name!r} existiert bereits.")
        k = parse_type(kind)
        world.memory_types[name] = k
        world.memory[name] = coerce_value(initial, k)

    def _create_trail(self, name: str, initial: float, sources: int, diffuse: float, decay: float) -> None:
        world = self._world()
        if name in world.trails:
            raise KeimRuntimeError(f"Spur {name!r} existiert bereits.")
        size = world.width * world.height
        values = [self._clamp01(initial) for _ in range(size)]
        source_grid = [0.0 for _ in range(size)]
        for _ in range(sources):
            x = self.rng.randrange(max(1, world.width // 12), max(2, world.width - world.width // 12))
            y = self.rng.randrange(max(1, world.height // 8), max(2, world.height - world.height // 8))
            idx = self._idx(x, y)
            source_grid[idx] = 1.0
            values[idx] = 1.0
        world.trails[name] = TrailState(name=name, values=values, sources=source_grid, diffuse=self._clamp01(diffuse), decay=self._clamp01(decay))

    def _place_source(self, trail_name: str, x: int, y: int, strength: float) -> None:
        world = self._world()
        if x >= world.width or y >= world.height:
            raise KeimRuntimeError(f"Quelle außerhalb der Welt: ({x}, {y}) nicht in {world.width}x{world.height}")
        trail = self._trail(trail_name)
        idx = self._idx(x, y)
        value = self._clamp01(strength)
        trail.sources[idx] = max(trail.sources[idx], value)
        trail.values[idx] = max(trail.values[idx], value)

    def _apply_step(self, step: Step, mask: list[bool] | None, tick: int, self_obj: ObjectState | None = None) -> None:
        match step:
            case AgentFieldChange():
                self._change_field(step.field, step.kind, step.amount, mask)
            case FieldCompute(field=field, expression=expression):
                self._compute_field(field, expression, mask)
            case MemoryChange(memory=memory, kind=kind, amount=amount):
                self._change_memory(memory, kind, amount, mask)
            case MemoryAggregate(memory=memory, aggregate=aggregate, source_kind=source_kind, source=source):
                self._aggregate_memory(memory, aggregate, source_kind, source, mask)
            case TableInsert(table=table, values=values):
                self._insert_table_row(table, dict(values), tick)
            case DatabaseSave(database=database, table=table):
                self._save_table_to_database(database, table)
            case TableQuery(table=table, column=column, op=op, value=value, target_memory=target_memory):
                self._query_table(table, column, op, value, target_memory)
            case MapSet(memory=memory, key=key, value=value):
                self._map_set(memory, key, value)
            case MapGet(memory=memory, key=key, target_memory=target_memory):
                self._map_get(memory, key, target_memory)
            case MapDelete(memory=memory, key=key):
                self._map_delete(memory, key)
            case MapHas(memory=memory, key=key, target_memory=target_memory):
                self._map_has(memory, key, target_memory)
            case JsonParse(source_memory=source_memory, target_memory=target_memory):
                self._json_parse(source_memory, target_memory)
            case JsonStringify(source_memory=source_memory, target_memory=target_memory):
                self._json_stringify(source_memory, target_memory)
            case HttpServerStart(port=port, response_memory=response_memory):
                self.sandbox.require("netz", "server startet")
                self._http_server_start(port, response_memory)
            case FfiCall(library=library, function=function, args=args, target_memory=target_memory, result_kind=result_kind):
                self.sandbox.require("ffi", "ffi ruft")
                self._ffi_call(library, function, args, target_memory, result_kind)
            case GrafikCommand(kind=kind, args=args):
                self._grafik_command(kind, args)
            case AudioCommand(kind=kind, args=args):
                self._audio_command(kind, args)
            case DebugWatch(memory=memory):
                self._debug_watch(memory)
            case DebugSend(label=label):
                self.debug_bus.send(label)
            case AwaitTask(name=name, target_memory=target_memory):
                self._await_task(name, target_memory)
            case TimeNow(target_memory=target_memory):
                self._time_now(target_memory)
            case CryptoHash(algorithm=algorithm, source_memory=source_memory, target_memory=target_memory):
                self._crypto_hash(algorithm, source_memory, target_memory)
            case ProcessRun(command=command, target_memory=target_memory):
                self.sandbox.require("prozess", "prozess")
                self._process_run(command, target_memory)
            case ListAppend(memory=memory, value=value):
                self._list_append(memory, value)
            case ListPop(memory=memory, target_memory=target_memory):
                self._list_pop(memory, target_memory)
            case FileTableIO(mode=mode, fmt=fmt, path=path, table=table):
                self.sandbox.require("io", "datei")
                self._file_table_io(mode, fmt, path, table)
            case WebRequest(method=method, url=url, target_memory=target_memory):
                self.sandbox.require("netz", "anfrage")
                self._web_request(method, url, target_memory)
            case PathFind(start_x=start_x, start_y=start_y, goal_x=goal_x, goal_y=goal_y, cost_trail=cost_trail, target_table=target_table):
                self._path_find(start_x, start_y, goal_x, goal_y, cost_trail, target_table)
            case ExportImage(fmt=fmt, path=path, source_kind=source_kind, source=source):
                self._export_image(fmt, path, source_kind, source)
            case StartDashboard(path=path):
                self._start_dashboard(path)
            case ObjectCall(object_name=object_name, method=method):
                self._call_object_method(object_name, method, tick, mask)
            case SpawnObject(name=name, class_name=class_name, overrides=overrides):
                self._spawn_object(name, class_name, overrides)
            case DeleteObject(name=name):
                self._delete_object(name)
            case CollectGarbage():
                self._collect_garbage()
            case SpawnAgents(count=count):
                self._spawn_agents(count)
            case KillAgents(count=count):
                self._kill_agents(count, mask)
            case AgentFollowTrail(trail=trail):
                self._follow_trail(trail, mask, seek_high=True)
            case AgentAvoidTrail(trail=trail):
                self._follow_trail(trail, mask, seek_high=False)
            case AgentWander(chance=chance):
                self._wander(chance, mask)
            case AgentRest():
                self._rest(mask)
            case FieldTrailCoupling(field=field, trail=trail, kind=kind, amount=amount):
                self._couple_field_to_trail(field, trail, kind, amount, mask)
            case FieldTrailEmission(field=field, trail=trail, amount=amount):
                self._emit_field_to_trail(field, trail, amount, mask)
            case TrailDiffuse(trail=trail):
                self._diffuse_trail(trail)
            case TrailStrengthen(trail=trail, amount=amount):
                self._strengthen_trail(trail, amount, mask)
            case CallRule(name=name):
                self._call_rule(name, tick, mask)
            case ShowWorld():
                pass
            case _:
                raise KeimRuntimeError(f"Diese Step-Art kann nicht direkt ausgeführt werden: {step!r}")

    def _apply_action(self, action: Action, mask: list[bool] | None, tick: int, self_obj: ObjectState | None = None) -> None:
        self._apply_step(action, mask, tick, self_obj)


    def _ffi_call(self, library: str, function: str, args: tuple[object, ...], target_memory: str | None, result_kind: str) -> None:
        lib = self._ffi_libraries.get(library)
        if lib is None:
            raise KeimRuntimeError(f"Unbekannte FFI-Bibliothek: {library!r}")
        resolved = tuple(self._resolve_literal_or_memory(arg) for arg in args)
        result = lib.call(function, resolved, result_kind)
        self.backend_metrics["ffi:calls"] = self.backend_metrics.get("ffi:calls", 0) + 1
        if target_memory:
            world = self._world()
            if target_memory not in world.memory:
                raise KeimRuntimeError(f"FFI-Zielspeicher {target_memory!r} existiert nicht.")
            world.memory[target_memory] = coerce_value(result, world.memory_types.get(target_memory, parse_type(result_kind)))

    def _resolve_literal_or_memory(self, value: object) -> object:
        if isinstance(value, str) and value.startswith("speicher."):
            return self._memory(value.removeprefix("speicher."))
        return value

    def _await_task(self, name: str, target_memory: str | None) -> None:
        future = self._async_tasks.get(name)
        if future is None:
            raise KeimRuntimeError(f"Unbekannter Hintergrund-Task: {name!r}")
        try:
            future.result(timeout=None)
            value: object = True
        except Exception as exc:  # noqa: BLE001
            value = str(exc)
            if target_memory is None:
                raise KeimRuntimeError(f"Hintergrund-Task {name!r} ist fehlgeschlagen: {exc}") from exc
        if target_memory:
            world = self._world()
            if target_memory in world.memory:
                world.memory[target_memory] = coerce_value(value, world.memory_types.get(target_memory, KeimType.BOOL))
            else:
                raise KeimRuntimeError(f"Unbekannter Speicher für Task-Ergebnis: {target_memory!r}")


    def _call_rule(self, name: str, tick: int, mask: list[bool] | None) -> None:
        steps = self.rules.get(name)
        if steps is None:
            raise KeimRuntimeError(f"Unbekannte Regel: {name!r}")
        if name in self._call_stack:
            cycle = " -> ".join([*self._call_stack, name])
            raise KeimRuntimeError(f"Rekursiver Regelaufruf ist nicht erlaubt: {cycle}")
        if len(self._call_stack) >= 32:
            raise KeimRuntimeError("Regelaufrufe sind zu tief verschachtelt.")
        self._call_stack.append(name)
        try:
            self._execute_steps(steps, tick, mask)
        finally:
            self._call_stack.pop()



    def _call_object_method(self, object_name: str, method: str, tick: int, mask: list[bool] | None) -> None:
        obj = self.objects.get(object_name)
        if obj is None:
            raise KeimRuntimeError(f"Unbekanntes Objekt: {object_name!r}")
        klass = self.classes.get(obj.class_name)
        if klass is None:
            raise KeimRuntimeError(f"Objekt {object_name!r} hat unbekannte Klasse {obj.class_name!r}.")
        steps = klass.methods.get(method)
        if steps is None:
            raise KeimRuntimeError(f"Klasse {obj.class_name!r} hat keine Methode {method!r}.")
        self.backend_metrics["objects:method_calls"] = self.backend_metrics.get("objects:method_calls", 0) + 1
        self._execute_steps(steps, tick, mask, obj)

    def _condition_value(self, value: object, self_obj: ObjectState | None) -> float:
        if isinstance(value, SelfPropertyRef):
            if self_obj is None:
                raise KeimRuntimeError("'selbst.EIGENSCHAFT' darf nur in Objektmethoden verwendet werden.")
            try:
                return to_float(self_obj.properties[value.name])
            except KeyError as exc:
                raise KeimRuntimeError(f"Objekt {self_obj.name!r} hat keine Eigenschaft {value.name!r}.") from exc
        return to_float(value)

    def _insert_table_row(self, table_name: str, raw_values: dict[str, str], tick: int) -> None:
        table = self.tables.get(table_name)
        if table is None:
            raise KeimRuntimeError(f"Unbekannte Tabelle: {table_name!r}")
        declared = {name: kind for name, kind in table.columns}
        unknown = set(raw_values) - set(declared)
        if unknown:
            raise KeimRuntimeError(f"Tabelle {table_name!r} kennt diese Spalten nicht: {', '.join(sorted(unknown))}")
        row: dict[str, Any] = {}
        for name, kind in table.columns:
            raw = raw_values.get(name)
            if raw is None:
                row[name] = 0.0 if kind == "zahl" else ""
            elif kind == "zahl":
                row[name] = float(to_float(self._resolve_table_value(raw, tick)))
            elif kind == "ganzzahl":
                row[name] = int(round(to_float(self._resolve_table_value(raw, tick))))
            elif kind == "bool":
                row[name] = bool(self._resolve_table_value(raw, tick))
            elif kind == "array":
                value = self._resolve_table_value(raw, tick)
                row[name] = list(value) if isinstance(value, list) else [value]
            else:
                value = self._resolve_table_value(raw, tick)
                row[name] = str(value)
        table.rows.append(row)
        self._refresh_table_indices(table)
        self.backend_metrics["tables:rows_inserted"] = self.backend_metrics.get("tables:rows_inserted", 0) + 1

    def _resolve_table_value(self, raw: str, tick: int) -> Any:
        token = raw.strip().strip('"').strip("'")
        if token in {"zeit", "runde", "tick"}:
            return float(tick)
        if token.startswith("speicher."):
            return self._memory(token.removeprefix("speicher."))
        if token.startswith("feld."):
            return self._mean(self._field(token.removeprefix("feld.")))
        if token.startswith("spur."):
            return self._mean(self._trail(token.removeprefix("spur.")).values)
        if token.startswith("objekt."):
            _, obj_name, prop = token.split(".", 2)
            obj = self.objects.get(obj_name)
            if obj is None or prop not in obj.properties:
                raise KeimRuntimeError(f"Unbekannte Objekteigenschaft: {token!r}")
            return obj.properties[prop]
        try:
            return float(token.replace(",", "."))
        except ValueError:
            return token

    def _save_table_to_database(self, database_name: str, table_name: str) -> None:
        table = self.tables.get(table_name)
        if table is None:
            raise KeimRuntimeError(f"Unbekannte Tabelle: {table_name!r}")
        db_path = self.databases.get(database_name)
        if db_path is None:
            raise KeimRuntimeError(f"Unbekannte Datenbank: {database_name!r}")
        path = Path(db_path)
        if path.parent != Path("."):
            path.parent.mkdir(parents=True, exist_ok=True)
        start = self._db_exported_rows.get((database_name, table_name), 0)
        rows = table.rows[start:]
        if not rows:
            return
        col_defs = ", ".join(f'"{name}" {self._sqlite_type(kind)}' for name, kind in table.columns)
        names = [name for name, _ in table.columns]
        placeholders = ", ".join("?" for _ in names)
        quoted_names = ", ".join(f'"{name}"' for name in names)
        with sqlite3.connect(path) as con:
            con.execute(f'CREATE TABLE IF NOT EXISTS "{table.name}" ({col_defs})')
            con.executemany(
                f'INSERT INTO "{table.name}" ({quoted_names}) VALUES ({placeholders})',
                [[row.get(name) for name in names] for row in rows],
            )
            con.commit()
        self._db_exported_rows[(database_name, table_name)] = start + len(rows)
        self.backend_metrics["database:rows_saved"] = self.backend_metrics.get("database:rows_saved", 0) + len(rows)


    def _rebuild_table_index(self, table: TableState, column: str) -> None:
        idx: dict[Any, list[int]] = {}
        for i, row in enumerate(table.rows):
            idx.setdefault(row.get(column), []).append(i)
        table.indices[column] = idx

    def _refresh_table_indices(self, table: TableState) -> None:
        for column in list(table.indices):
            self._rebuild_table_index(table, column)

    def _query_table(self, table_name: str, column: str, op: str, value: object, target_memory: str) -> None:
        table = self.tables.get(table_name)
        if table is None:
            raise KeimRuntimeError(f"Unbekannte Tabelle: {table_name!r}")
        if target_memory not in self._world().memory:
            raise KeimRuntimeError(f"Tabellensuche braucht existierenden Speicher {target_memory!r}.")
        # Index-Nutzung für Gleichheit: O(k) statt O(n). Andere Vergleiche bleiben linear.
        if op == "==" and column in table.indices:
            hits = list(table.indices[column].get(value, []))
        else:
            hits = [i for i, row in enumerate(table.rows) if self._compare_value(row.get(column), op, value)]
        self._world().memory[target_memory] = coerce_value(hits, self._world().memory_types.get(target_memory, KeimType.ARRAY))
        self.backend_metrics["table:query_rows"] = self.backend_metrics.get("table:query_rows", 0) + len(table.rows)
        self.backend_metrics["table:query_hits"] = self.backend_metrics.get("table:query_hits", 0) + len(hits)

    @staticmethod
    def _compare_value(left: object, op: str, right: object) -> bool:
        if isinstance(left, (int, float, bool)) or isinstance(right, (int, float, bool)):
            return CpuBackend._compare(to_float(left), op, to_float(right))
        match op:
            case "==": return left == right
            case "!=": return left != right
            case ">": return str(left) > str(right)
            case ">=": return str(left) >= str(right)
            case "<": return str(left) < str(right)
            case "<=": return str(left) <= str(right)
            case _: raise KeimRuntimeError(f"Unbekannter Vergleich: {op}")


    def _grafik_command(self, kind: str, args: tuple[object, ...]) -> None:
        resolved = tuple(self._resolve_literal_or_memory(arg) for arg in args)
        self.grafik.command(kind, *resolved)
        self.backend_metrics["grafik:commands"] = self.backend_metrics.get("grafik:commands", 0) + 1

    def _audio_command(self, kind: str, args: tuple[object, ...]) -> None:
        resolved = tuple(self._resolve_literal_or_memory(arg) for arg in args)
        if kind == "ton":
            self.audio.tone(int(resolved[0]), int(resolved[1]))
        elif kind == "signal":
            self.audio.signal(str(resolved[0]))
        elif kind == "stumm":
            self.audio.muted = bool(resolved[0])
            self.audio.events.append({"kind": "stumm", "muted": self.audio.muted})
        else:
            raise KeimRuntimeError(f"Unbekannte Audioaktion: {kind!r}")
        self.backend_metrics["audio:events"] = self.backend_metrics.get("audio:events", 0) + 1

    def _debug_watch(self, memory_name: str) -> None:
        world = self._world()
        if memory_name not in world.memory:
            raise KeimRuntimeError(f"Debug beobachtet unbekannten Speicher: {memory_name!r}")
        self.debug_bus.watch(memory_name, world.memory[memory_name])
        self.backend_metrics["debug:watch"] = self.backend_metrics.get("debug:watch", 0) + 1

    def _list_append(self, memory_name: str, value: object) -> None:
        world = self._world()
        if memory_name not in world.memory:
            raise KeimRuntimeError(f"Unbekannte Liste/Speicher: {memory_name!r}")
        current = world.memory[memory_name]
        if not isinstance(current, list):
            raise KeimRuntimeError(f"Speicher {memory_name!r} ist keine Liste.")
        elem = element_type(world.memory_types.get(memory_name, "array"))
        resolved = self._resolve_literal(value)
        if elem is not None:
            try:
                resolved = coerce_value(resolved, elem)
            except Exception as exc:
                raise KeimRuntimeError(f"Generische Liste {memory_name!r} akzeptiert diesen Wert nicht: {value!r}") from exc
        current.append(resolved)
        self.debug_bus.update(memory_name, current)
        self.backend_metrics["list:append"] = self.backend_metrics.get("list:append", 0) + 1

    def _list_pop(self, memory_name: str, target_memory: str | None) -> None:
        world = self._world()
        current = world.memory.get(memory_name)
        if not isinstance(current, list):
            raise KeimRuntimeError(f"Speicher {memory_name!r} ist keine Liste.")
        value = current.pop() if current else None
        if target_memory is not None:
            if target_memory not in world.memory:
                raise KeimRuntimeError(f"Unbekannter Zielspeicher: {target_memory!r}")
            world.memory[target_memory] = coerce_value(value, world.memory_types.get(target_memory, KeimType.TEXT))
        self.backend_metrics["list:pop"] = self.backend_metrics.get("list:pop", 0) + 1


    def _resolve_literal(self, value: object) -> object:
        world = self._world()
        if isinstance(value, str):
            if value.startswith("speicher."):
                name = value.split(".", 1)[1]
                if name not in world.memory:
                    raise KeimRuntimeError(f"Unbekannter Speicherverweis: {value!r}")
                return world.memory[name]
            if value.startswith("objekt."):
                return value
        return value

    def _map_set(self, memory_name: str, key: object, value: object) -> None:
        world = self._world()
        current = world.memory.get(memory_name)
        if not isinstance(current, dict):
            raise KeimRuntimeError(f"Speicher {memory_name!r} ist keine karte.")
        ktype, vtype = map_types(world.memory_types.get(memory_name, "karte"))
        rkey = self._resolve_literal(key)
        rval = self._resolve_literal(value)
        if ktype is not None:
            rkey = coerce_value(rkey, ktype)
        if vtype is not None:
            try:
                rval = coerce_value(rval, vtype)
            except Exception as exc:
                raise KeimRuntimeError(f"Generische Karte {memory_name!r} akzeptiert diesen Wert nicht: {value!r}") from exc
        current[str(rkey)] = rval
        self.debug_bus.update(memory_name, current)
        self.backend_metrics["map:set"] = self.backend_metrics.get("map:set", 0) + 1

    def _map_get(self, memory_name: str, key: object, target_memory: str) -> None:
        world = self._world()
        current = world.memory.get(memory_name)
        if not isinstance(current, dict):
            raise KeimRuntimeError(f"Speicher {memory_name!r} ist keine karte.")
        if target_memory not in world.memory:
            raise KeimRuntimeError(f"Unbekannter Zielspeicher: {target_memory!r}")
        value = current.get(str(self._resolve_literal(key)))
        world.memory[target_memory] = coerce_value(value, world.memory_types.get(target_memory, KeimType.TEXT))
        self.backend_metrics["map:get"] = self.backend_metrics.get("map:get", 0) + 1

    def _map_has(self, memory_name: str, key: object, target_memory: str) -> None:
        world = self._world()
        current = world.memory.get(memory_name)
        if not isinstance(current, dict):
            raise KeimRuntimeError(f"Speicher {memory_name!r} ist keine karte.")
        if target_memory not in world.memory:
            raise KeimRuntimeError(f"Unbekannter Zielspeicher: {target_memory!r}")
        value = str(self._resolve_literal(key)) in current
        world.memory[target_memory] = coerce_value(value, world.memory_types.get(target_memory, KeimType.BOOL))
        self.backend_metrics["map:has"] = self.backend_metrics.get("map:has", 0) + 1

    def _map_delete(self, memory_name: str, key: object) -> None:
        world = self._world()
        current = world.memory.get(memory_name)
        if not isinstance(current, dict):
            raise KeimRuntimeError(f"Speicher {memory_name!r} ist keine karte.")
        current.pop(str(self._resolve_literal(key)), None)
        self.backend_metrics["map:delete"] = self.backend_metrics.get("map:delete", 0) + 1

    def _json_parse(self, source_memory: str, target_memory: str) -> None:
        world = self._world()
        if source_memory not in world.memory or target_memory not in world.memory:
            raise KeimRuntimeError("JSON braucht existierende Quell- und Zielspeicher.")
        try:
            parsed = json.loads(str(world.memory[source_memory]))
        except json.JSONDecodeError as exc:
            raise KeimRuntimeError(f"JSON-Parserfehler: {exc.msg}") from exc
        world.memory[target_memory] = coerce_value(parsed, world.memory_types.get(target_memory, KeimType.MAP))
        self.backend_metrics["json:parse"] = self.backend_metrics.get("json:parse", 0) + 1

    def _json_stringify(self, source_memory: str, target_memory: str) -> None:
        world = self._world()
        if source_memory not in world.memory or target_memory not in world.memory:
            raise KeimRuntimeError("JSON braucht existierende Quell- und Zielspeicher.")
        text = json.dumps(world.memory[source_memory], ensure_ascii=False, separators=(",", ":"))
        world.memory[target_memory] = coerce_value(text, world.memory_types.get(target_memory, KeimType.TEXT))
        self.backend_metrics["json:stringify"] = self.backend_metrics.get("json:stringify", 0) + 1


    def _time_now(self, target_memory: str) -> None:
        world = self._world()
        if target_memory not in world.memory:
            raise KeimRuntimeError(f"Zeit-Zielspeicher existiert nicht: {target_memory!r}")
        value: object
        kind = world.memory_types.get(target_memory, KeimType.TEXT)
        if kind == KeimType.INT:
            value = int(datetime.now(timezone.utc).timestamp() * 1_000_000_000)
        elif kind == KeimType.FLOAT:
            value = datetime.now(timezone.utc).timestamp()
        else:
            value = datetime.now(timezone.utc).isoformat()
        world.memory[target_memory] = coerce_value(value, kind)
        self.backend_metrics["system:time"] = self.backend_metrics.get("system:time", 0) + 1

    def _crypto_hash(self, algorithm: str, source_memory: str, target_memory: str) -> None:
        world = self._world()
        if source_memory not in world.memory or target_memory not in world.memory:
            raise KeimRuntimeError("Krypto braucht existierende Quell- und Zielspeicher.")
        data = str(world.memory[source_memory]).encode("utf-8")
        digest = hashlib.new(algorithm, data).hexdigest()
        world.memory[target_memory] = coerce_value(digest, world.memory_types.get(target_memory, KeimType.TEXT))
        self.backend_metrics["system:crypto_hash"] = self.backend_metrics.get("system:crypto_hash", 0) + 1

    def _process_run(self, command: str, target_memory: str) -> None:
        world = self._world()
        if target_memory not in world.memory:
            raise KeimRuntimeError(f"Prozess-Zielspeicher existiert nicht: {target_memory!r}")
        try:
            args = shlex.split(command)
            if not args:
                raise ValueError("leerer Befehl")
            result = subprocess.run(args, capture_output=True, text=True, timeout=5, check=False)
        except Exception as exc:
            raise KeimRuntimeError(f"Prozessfehler: {exc}") from exc
        payload = result.stdout if result.stdout else result.stderr
        if result.returncode != 0 and not payload:
            payload = f"prozess exit {result.returncode}"
        world.memory[target_memory] = coerce_value(payload.strip(), world.memory_types.get(target_memory, KeimType.TEXT))
        self.backend_metrics["system:process"] = self.backend_metrics.get("system:process", 0) + 1


    def _load_http_service(self, service: HttpServiceDecl) -> None:
        world = self._world()
        if service.port in self._http_servers:
            raise KeimRuntimeError(f"HTTP-Port {service.port} ist bereits belegt.")
        route_map: dict[tuple[str, str], HttpRouteDecl] = {}
        for route in service.routes:
            for mem in (route.request_memory, route.response_memory, route.status_memory):
                if mem is not None and mem not in world.memory:
                    raise KeimRuntimeError(f"HTTP-Route {route.method} {route.path} verweist auf unbekannten Speicher {mem!r}.")
            key = (route.method.upper(), route.path)
            if key in route_map:
                raise KeimRuntimeError(f"Doppelte HTTP-Route: {route.method} {route.path}")
            route_map[key] = route
        self._http_routes[service.port] = route_map
        self._start_routed_http_server(service.port, service.name, route_map)
        self.backend_metrics["net:service_start"] = self.backend_metrics.get("net:service_start", 0) + 1

    def _http_server_start(self, port: int, response_memory: str) -> None:
        world = self._world()
        if response_memory not in world.memory:
            raise KeimRuntimeError(f"HTTP-Server braucht existierenden Antwortspeicher: {response_memory!r}")
        route = HttpRouteDecl(method="GET", path="/", request_memory=None, response_memory=response_memory, status_memory=None, steps=(), loc=SourceLocation(0, "server startet"))
        self._start_routed_http_server(port, "legacy", {("GET", "/"): route})
        self.backend_metrics["net:server_start"] = self.backend_metrics.get("net:server_start", 0) + 1

    def _start_routed_http_server(self, port: int, service_name: str, routes: dict[tuple[str, str], HttpRouteDecl]) -> None:
        if port in self._http_servers:
            return
        backend = self

        class Handler(BaseHTTPRequestHandler):
            server_version = f"KeimHTTP/{service_name}"

            def log_message(self, format: str, *args: object) -> None:
                return

            def _dispatch(self) -> None:
                from urllib.parse import urlparse
                parsed = urlparse(self.path)
                route = routes.get((self.command.upper(), parsed.path))
                if route is None:
                    self._write_json(404, {"ok": False, "error": f"unbekannte Route: {self.command} {parsed.path}"})
                    return
                length = int(self.headers.get("Content-Length", "0") or "0")
                raw_body = self.rfile.read(length).decode("utf-8") if length else ""
                try:
                    status, payload = backend._execute_http_route(route, raw_body, dict(self.headers), parsed.query)
                except Exception as exc:  # Handler-Grenze: Fehler werden zu stabilen JSON-Antworten.
                    backend.backend_metrics["net:route_error"] = backend.backend_metrics.get("net:route_error", 0) + 1
                    self._write_json(500, {"ok": False, "error": str(exc)})
                    return
                if isinstance(payload, (dict, list)):
                    self._write_json(status, payload)
                else:
                    data = str(payload).encode("utf-8")
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json; charset=utf-8" if str(payload).strip().startswith(("{","[")) else "text/plain; charset=utf-8")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)

            def _write_json(self, status: int, obj: object) -> None:
                data = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:  # noqa: N802
                self._dispatch()

            def do_POST(self) -> None:  # noqa: N802
                self._dispatch()

            def do_PUT(self) -> None:  # noqa: N802
                self._dispatch()

            def do_DELETE(self) -> None:  # noqa: N802
                self._dispatch()

            def do_PATCH(self) -> None:  # noqa: N802
                self._dispatch()

        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        except OSError as exc:
            raise KeimRuntimeError(f"HTTP-Server konnte Port {port} nicht öffnen: {exc}") from exc
        thread = threading.Thread(target=server.serve_forever, name=f"keim-http-{port}", daemon=True)
        thread.start()
        self._http_servers[port] = server

    def _execute_http_route(self, route: HttpRouteDecl, raw_body: str, headers: dict[str, str], query: str) -> tuple[int, object]:
        # Die Handler laufen parallel auf ThreadingHTTPServer. Mutationen des Keim-
        # Zustands werden mit einem RLock serialisiert; reine Host-Netzwerkannahme
        # blockiert dadurch nicht, nur der Sprachzustand bleibt deterministisch.
        with self._http_lock:
            world = self._world()
            if route.request_memory:
                world.memory[route.request_memory] = coerce_value(raw_body, world.memory_types.get(route.request_memory, KeimType.TEXT))
            # Konventionelle Request-Metadaten, falls das Programm Speicher dafür angelegt hat.
            for name, value in {
                "anfrage_methode": route.method,
                "anfrage_pfad": route.path,
                "anfrage_query": query,
                "anfrage_header": dict(headers),
            }.items():
                if name in world.memory:
                    world.memory[name] = coerce_value(value, world.memory_types.get(name, KeimType.TEXT))
            if route.steps:
                self._execute_steps(route.steps, 0, None, None)
            status = 200
            if route.status_memory and route.status_memory in world.memory:
                try:
                    status = int(world.memory[route.status_memory])
                except Exception:
                    status = 200
            payload = world.memory.get(route.response_memory, "")
            self.backend_metrics["net:route_hit"] = self.backend_metrics.get("net:route_hit", 0) + 1
            return status, payload

    def _file_table_io(self, mode: str, fmt: str, path: str, table_name: str) -> None:
        table = self.tables.get(table_name)
        if table is None:
            raise KeimRuntimeError(f"Unbekannte Tabelle: {table_name!r}")
        target = Path(path)
        if mode == "write":
            # v7.7.1: HTTP-Daemons können Tabellen parallel zum Tick speichern.
            # Deshalb wird vor dem eigentlichen Schreiben ein stabiler Snapshot
            # erzeugt. Das verhindert unter Windows/ThreadingHTTPServer, dass ein
            # JSON-Dump eine währenddessen wachsende Tabellenliste beobachtet und
            # den Request unnötig lange blockiert.
            rows_snapshot = [dict(row) for row in table.rows]
            target.parent.mkdir(parents=True, exist_ok=True) if target.parent != Path("") else None
            tmp = target.with_name(target.name + ".tmp")
            if fmt == "json":
                tmp.write_text(json.dumps(rows_snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
            else:
                names = [name for name, _ in table.columns]
                with tmp.open("w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=names)
                    writer.writeheader()
                    writer.writerows(rows_snapshot)
            tmp.replace(target)
            self.backend_metrics["io:table_write"] = self.backend_metrics.get("io:table_write", 0) + len(rows_snapshot)
            return
        if not target.exists():
            raise KeimRuntimeError(f"Datei nicht gefunden: {path}")
        if fmt == "json":
            rows = json.loads(target.read_text(encoding="utf-8"))
            if not isinstance(rows, list):
                raise KeimRuntimeError("JSON-Tabellenimport erwartet eine Liste von Objekten.")
            table.rows.extend(dict(row) for row in rows)
        else:
            with target.open("r", newline="", encoding="utf-8") as f:
                table.rows.extend(dict(row) for row in csv.DictReader(f))
        self._refresh_table_indices(table)
        self.backend_metrics["io:table_read"] = self.backend_metrics.get("io:table_read", 0) + len(table.rows)

    def _web_request(self, method: str, url: str, target_memory: str) -> None:
        world = self._world()
        if target_memory not in world.memory:
            raise KeimRuntimeError(f"Anfrage-Zielspeicher existiert nicht: {target_memory!r}")
        if method != "GET":
            raise KeimRuntimeError("Aktuell unterstützt anfrage nur GET.")
        req = Request(url, headers={"User-Agent": "KeimGenesis/4.0"})
        with urlopen(req, timeout=5) as response:
            data = response.read(65536)
            text = data.decode(response.headers.get_content_charset() or "utf-8", errors="replace")
        world.memory[target_memory] = coerce_value(text, world.memory_types.get(target_memory, KeimType.TEXT))
        self.backend_metrics["net:get"] = self.backend_metrics.get("net:get", 0) + 1

    def _path_find(self, sx: int, sy: int, gx: int, gy: int, cost_trail: str | None, target_table: str) -> None:
        world = self._world()
        if not (0 <= sx < world.width and 0 <= gx < world.width and 0 <= sy < world.height and 0 <= gy < world.height):
            raise KeimRuntimeError("Pfadkoordinaten liegen außerhalb der Welt.")
        table = self.tables.get(target_table)
        if table is None:
            raise KeimRuntimeError(f"Pfad-Zieltabelle existiert nicht: {target_table!r}")
        trail = self._trail(cost_trail) if cost_trail else None
        start, goal = (sx, sy), (gx, gy)
        heap: list[tuple[float, tuple[int, int]]] = [(0.0, start)]
        came: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
        cost: dict[tuple[int, int], float] = {start: 0.0}
        while heap:
            _, cur = heapq.heappop(heap)
            if cur == goal:
                break
            x, y = cur
            for nx, ny in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
                if not (0 <= nx < world.width and 0 <= ny < world.height):
                    continue
                penalty = trail.values[self._idx(nx, ny)] if trail else 0.0
                new_cost = cost[cur] + 1.0 + penalty
                if (nx, ny) not in cost or new_cost < cost[(nx, ny)]:
                    cost[(nx, ny)] = new_cost
                    prio = new_cost + abs(gx - nx) + abs(gy - ny)
                    heapq.heappush(heap, (prio, (nx, ny)))
                    came[(nx, ny)] = cur
        if goal not in came:
            return
        path: list[tuple[int, int]] = []
        cur: tuple[int, int] | None = goal
        while cur is not None:
            path.append(cur); cur = came[cur]
        path.reverse()
        for step_no, (x, y) in enumerate(path):
            table.rows.append({"schritt": step_no, "x": x, "y": y, "kosten": cost.get((x, y), 0.0)})
        self._refresh_table_indices(table)
        self.backend_metrics["math:astar_nodes"] = self.backend_metrics.get("math:astar_nodes", 0) + len(cost)

    def _export_image(self, fmt: str, path: str, source_kind: str, source: str) -> None:
        world = self._world()
        if source_kind == "spur":
            values = list(self._trail(source).values)
        else:
            field_values = [to_float(v) for v in self._field(source)]
            accum = [0.0] * (world.width * world.height)
            counts = [0] * (world.width * world.height)
            for x, y, value in zip(world.x, world.y, field_values):
                idx = self._idx(x, y); accum[idx] += value; counts[idx] += 1
            values = [(accum[i] / counts[i]) if counts[i] else 0.0 for i in range(len(accum))]
        pixels = [max(0, min(255, int(to_float(v) * 255))) for v in values]
        target = Path(path)
        if target.parent != Path(""):
            target.parent.mkdir(parents=True, exist_ok=True)
        if fmt == "bmp":
            target.write_bytes(self._encode_bmp(world.width, world.height, pixels))
        else:
            target.write_bytes(self._encode_png(world.width, world.height, pixels))
        self.backend_metrics["viz:image_export"] = self.backend_metrics.get("viz:image_export", 0) + 1

    @staticmethod
    def _encode_bmp(width: int, height: int, pixels: list[int]) -> bytes:
        row_pad = (4 - (width * 3) % 4) % 4
        rows = bytearray()
        for y in range(height - 1, -1, -1):
            for x in range(width):
                v = pixels[y * width + x]
                rows.extend([v, v, v])
            rows.extend(b"\x00" * row_pad)
        size = 54 + len(rows)
        return b"BM" + struct.pack("<IHHI", size, 0, 0, 54) + struct.pack("<IiiHHIIiiII", 40, width, height, 1, 24, 0, len(rows), 2835, 2835, 0, 0) + bytes(rows)

    @staticmethod
    def _encode_png(width: int, height: int, pixels: list[int]) -> bytes:
        def chunk(kind: bytes, data: bytes) -> bytes:
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
        raw = bytearray()
        for y in range(height):
            raw.append(0)
            for x in range(width):
                v = pixels[y * width + x]
                raw.extend([v, v, v])
        return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")

    def _start_dashboard(self, path: str) -> None:
        self._dashboard_path = path
        target = Path(path)
        if target.parent != Path(""):
            target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self._dashboard_html(), encoding="utf-8")
        self.backend_metrics["viz:dashboard"] = self.backend_metrics.get("viz:dashboard", 0) + 1

    def _dashboard_html(self) -> str:
        data = json.dumps(self.metrics[-200:], ensure_ascii=False)
        return """<!doctype html><meta charset='utf-8'><title>Keim Dashboard</title>
<style>body{font-family:system-ui;margin:2rem}pre{background:#111;color:#eee;padding:1rem;border-radius:12px;overflow:auto}</style>
<h1>Keim Live Dashboard</h1><p>Statischer Snapshot der Observe-Metriken. Für Live-Betrieb diese Datei pro Runde überschreiben.</p>
<pre id='data'></pre><script>const data=""" + data + """;document.getElementById('data').textContent=JSON.stringify(data,null,2);</script>"""

    def _delete_object(self, name: str) -> None:
        obj = self.objects.get(name)
        if obj is None:
            return
        obj.refcount = max(0, obj.refcount - 1)
        obj.alive = False
        self.backend_metrics["gc:decref"] = self.backend_metrics.get("gc:decref", 0) + 1

    def _collect_garbage(self, auto: bool = False) -> None:
        # v4.2: Mark-and-Sweep über referenz-Werte in Speichern und Objektfeldern.
        # Statische Top-Level-Objekte sind Roots; dynamische Objekte überleben nur bei lebender Referenz.
        for obj in self.objects.values():
            obj.marked = False

        roots: set[str] = set()
        for name, obj in self.objects.items():
            if not obj.dynamic and obj.alive:
                roots.add(name)
        world = self._world()
        for value in world.memory.values():
            self._mark_refs_from_value(value, roots)
        for obj in self.objects.values():
            if obj.alive:
                for value in obj.properties.values():
                    self._mark_refs_from_value(value, roots)

        stack = list(roots)
        while stack:
            name = stack.pop()
            obj = self.objects.get(name)
            if obj is None or obj.marked:
                continue
            obj.marked = True
            for value in obj.properties.values():
                before = len(roots)
                self._mark_refs_from_value(value, roots)
                if len(roots) != before:
                    stack.extend(roots)

        dead = [
            name for name, obj in self.objects.items()
            if obj.dynamic and (not obj.alive or obj.refcount <= 0 or not obj.marked)
        ]
        for name in dead:
            del self.objects[name]
        key = "gc:auto_collected" if auto else "gc:collected"
        self.backend_metrics[key] = self.backend_metrics.get(key, 0) + len(dead)

    def _mark_refs_from_value(self, value: object, roots: set[str]) -> None:
        if isinstance(value, str):
            if value in self.objects:
                roots.add(value)
        elif isinstance(value, list):
            for item in value:
                self._mark_refs_from_value(item, roots)
        elif isinstance(value, dict):
            for item in value.values():
                self._mark_refs_from_value(item, roots)

    def _spawn_agents(self, count: int) -> None:
        if count <= 0:
            return
        world = self._world()
        for _ in range(count):
            world.x.append(self.rng.randrange(world.width))
            world.y.append(self.rng.randrange(world.height))
        for name, values in world.fields.items():
            fill = values[-1] if values else coerce_value(0.0, world.field_types.get(name, KeimType.FLOAT))
            values.extend(coerce_value(fill, world.field_types.get(name, KeimType.FLOAT)) for _ in range(count))
        self._resting.extend(False for _ in range(count))
        world.agents += count
        self.backend_metrics["dynamic:agents_spawned"] = self.backend_metrics.get("dynamic:agents_spawned", 0) + count

    def _kill_agents(self, count: int | None, mask: list[bool] | None) -> None:
        world = self._world()
        if world.agents <= 0:
            return
        if count is None:
            remove = [i for i in range(world.agents) if mask is None or mask[i]]
        else:
            active = [i for i in range(world.agents) if mask is None or mask[i]]
            remove = active[-count:]
        if not remove:
            return
        dead = set(remove)
        keep = [i for i in range(world.agents) if i not in dead]
        world.x = [world.x[i] for i in keep]
        world.y = [world.y[i] for i in keep]
        for name, values in list(world.fields.items()):
            world.fields[name] = [values[i] for i in keep]
        self._resting = [self._resting[i] for i in keep if i < len(self._resting)]
        killed = world.agents - len(keep)
        world.agents = len(keep)
        self.backend_metrics["dynamic:agents_killed"] = self.backend_metrics.get("dynamic:agents_killed", 0) + killed

    def _spawn_object(self, name: str, class_name: str, overrides: tuple[tuple[str, object], ...]) -> None:
        if name in self.objects:
            # Dynamische Objekt-Erzeugung ist idempotent, damit Schleifen keine Namenskollision explodieren lassen.
            return
        klass = self.classes.get(class_name)
        if klass is None:
            raise KeimRuntimeError(f"Dynamisches Objekt {name!r} nutzt unbekannte Klasse {class_name!r}.")
        props = dict(klass.properties)
        for prop, value in overrides:
            if prop not in props:
                raise KeimRuntimeError(f"Dynamisches Objekt {name!r} überschreibt unbekannte Eigenschaft {prop!r}.")
            props[prop] = coerce_value(value, klass.property_types.get(prop, KeimType.FLOAT))
        self.objects[name] = ObjectState(name=name, class_name=class_name, properties=props, dynamic=True)
        self.backend_metrics["dynamic:objects_spawned"] = self.backend_metrics.get("dynamic:objects_spawned", 0) + 1

    @staticmethod
    def _sqlite_type(kind: str) -> str:
        return {"zahl": "REAL", "ganzzahl": "INTEGER", "bool": "INTEGER", "array": "TEXT", "text": "TEXT"}.get(kind, "TEXT")


    def _process_events(self, tick: int) -> None:
        triggered = 0
        for name, condition, steps in self.events:
            mask = self._condition_mask(condition)  # type: ignore[arg-type]
            active = any(mask)
            was_active = self._event_active.get(name, False)
            if active and not was_active:
                triggered += 1
                self._execute_steps(steps, tick, mask)
            self._event_active[name] = active
        if triggered:
            self.backend_metrics["events:triggered"] = self.backend_metrics.get("events:triggered", 0) + triggered

    def _and_mask(self, outer: list[bool] | None, inner: list[bool] | None) -> list[bool] | None:
        if outer is None:
            return inner
        if inner is None:
            return outer
        return [a and b for a, b in zip(outer, inner)]

    def _change_field(self, field: str, kind: str, amount: float, mask: list[bool] | None) -> None:
        world = self._world()
        values = self._field(field)
        match kind:
            case "verliert" | "sinkt":
                signed = -amount
            case "bekommt" | "waechst":
                signed = amount
            case _:
                raise KeimRuntimeError(f"Unbekannte Feldänderung: {kind!r}")
        if mask is None:
            for i in range(world.agents):
                values[i] = coerce_value(to_float(values[i]) + signed, world.field_types.get(field, KeimType.FLOAT))
        else:
            for i, active in enumerate(mask):
                if active:
                    values[i] = coerce_value(to_float(values[i]) + signed, world.field_types.get(field, KeimType.FLOAT))

    def _compute_field(self, field_name: str, expression: str, mask: list[bool] | None) -> None:
        world = self._world()
        target = self._field(field_name)
        compiled = self._expr_cache.get(expression)
        if compiled is None:
            compiled = compile_agent_expression(expression, function_arities=self._function_arities)
            self._expr_cache[expression] = compiled

        # Unkonventionell: Ausdrucksauflösung ist agentenlokal. Feldnamen sind SoA-Lesezugriffe,
        # 'spur NAME' ist ein gather über agent_x/agent_y, 'speicher NAME' ein skalarer Broadcast.
        for i in range(world.agents):
            if mask is not None and not mask[i]:
                continue
            idx = self._idx(world.x[i], world.y[i])

            def resolve(name: str) -> float:
                if name.startswith("spur__"):
                    return self._trail(name.removeprefix("spur__")).values[idx]
                if name.startswith("speicher__"):
                    return self._memory(name.removeprefix("speicher__"))
                return self._field(name)[i]

            target[i] = coerce_value(compiled.eval(resolve, self.functions), world.field_types.get(field_name, KeimType.FLOAT))


    def _aggregate_memory(self, memory_name: str, aggregate: str, source_kind: str, source: str, mask: list[bool] | None) -> None:
        world = self._world()
        if memory_name not in world.memory:
            raise KeimRuntimeError(f"Unbekannter Speicher: {memory_name!r}")

        values: list[float]
        if source_kind == "feld":
            field = self._field(source)
            if mask is None:
                values = [to_float(v) for v in field]
            else:
                values = [to_float(value) for value, active in zip(field, mask) if active]
        elif source_kind == "spur":
            trail = self._trail(source)
            if mask is None:
                values = list(trail.values)
            else:
                values = []
                for i, active in enumerate(mask):
                    if active:
                        values.append(trail.values[self._idx(world.x[i], world.y[i])])
        else:
            raise KeimRuntimeError(f"Unbekannte Aggregatquelle: {source_kind!r}")

        if not values:
            return

        match aggregate:
            case "mittel":
                value = self._mean(values)
            case "summe":
                value = sum(values)
            case "min":
                value = min(values)
            case "max":
                value = max(values)
            case _:
                raise KeimRuntimeError(f"Unbekanntes Aggregat: {aggregate!r}")
        world.memory[memory_name] = coerce_value(value, world.memory_types.get(memory_name, KeimType.FLOAT))
        self.backend_metrics["reduction:memory_aggregate"] = self.backend_metrics.get("reduction:memory_aggregate", 0) + 1

    def _change_memory(self, memory_name: str, kind: str, amount: float, mask: list[bool] | None) -> None:
        world = self._world()
        if memory_name not in world.memory:
            raise KeimRuntimeError(f"Unbekannter Speicher: {memory_name!r}")

        if mask is None:
            factor = 1.0
            any_active = True
        else:
            active = sum(1 for value in mask if value)
            factor = active / max(1, world.agents)
            any_active = active > 0

        current = to_float(world.memory[memory_name])
        match kind:
            case "setzt":
                if any_active:
                    world.memory[memory_name] = coerce_value(amount, world.memory_types.get(memory_name, KeimType.FLOAT))
            case "verliert" | "sinkt":
                world.memory[memory_name] = coerce_value(current - to_float(amount) * factor, world.memory_types.get(memory_name, KeimType.FLOAT))
            case "bekommt" | "waechst":
                world.memory[memory_name] = coerce_value(current + to_float(amount) * factor, world.memory_types.get(memory_name, KeimType.FLOAT))
            case _:
                raise KeimRuntimeError(f"Unbekannte Speicheränderung: {kind!r}")
        self.debug_bus.update(memory_name, world.memory[memory_name])

    def _wander(self, chance: float, mask: list[bool] | None) -> None:
        world = self._world()
        p = self._clamp01(chance)
        for i in range(world.agents):
            if not self._agent_active(i, mask):
                continue
            if self.rng.random() <= p:
                world.x[i] = max(0, min(world.width - 1, world.x[i] + self.rng.choice([-1, 0, 1])))
                world.y[i] = max(0, min(world.height - 1, world.y[i] + self.rng.choice([-1, 0, 1])))

    def _rest(self, mask: list[bool] | None) -> None:
        world = self._world()
        energy = world.fields.get("energie")
        hunger = world.fields.get("hunger")
        for i in range(world.agents):
            if mask is not None and not mask[i]:
                continue
            self._resting[i] = True
            if energy is not None:
                energy[i] = coerce_value(to_float(energy[i]) + 0.012, world.field_types.get("energie", KeimType.FLOAT))
            if hunger is not None:
                hunger[i] = coerce_value(to_float(hunger[i]) + 0.001, world.field_types.get("hunger", KeimType.FLOAT))

    def _follow_trail(self, trail_name: str, mask: list[bool] | None, *, seek_high: bool) -> None:
        world = self._world()
        trail = self._trail(trail_name)
        w, h = world.width, world.height
        for i in range(world.agents):
            if not self._agent_active(i, mask):
                if mask is not None and not self._resting[i] and self.rng.random() < 0.03:
                    world.x[i] = max(0, min(w - 1, world.x[i] + self.rng.choice([-1, 0, 1])))
                    world.y[i] = max(0, min(h - 1, world.y[i] + self.rng.choice([-1, 0, 1])))
                continue
            x, y = world.x[i], world.y[i]
            best_x, best_y = x, y
            best_value = trail.values[self._idx(x, y)] + self.rng.random() * 0.015
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    nx = max(0, min(w - 1, x + dx))
                    ny = max(0, min(h - 1, y + dy))
                    value = trail.values[self._idx(nx, ny)] + self.rng.random() * 0.02
                    if seek_high and value > best_value:
                        best_value = value
                        best_x, best_y = nx, ny
                    elif not seek_high and value < best_value:
                        best_value = value
                        best_x, best_y = nx, ny
            world.x[i], world.y[i] = best_x, best_y

    def _couple_field_to_trail(self, field_name: str, trail_name: str, kind: str, amount: float, mask: list[bool] | None) -> None:
        world = self._world()
        values = self._field(field_name)
        trail = self._trail(trail_name)
        signed = -abs(amount) if kind == "meidet" else abs(amount)
        for i in range(world.agents):
            if not self._agent_active(i, mask):
                continue
            idx = self._idx(world.x[i], world.y[i])
            values[i] = coerce_value(to_float(values[i]) + trail.values[idx] * signed, world.field_types.get(field_name, KeimType.FLOAT))

    def _emit_field_to_trail(self, field_name: str, trail_name: str, amount: float, mask: list[bool] | None) -> None:
        world = self._world()
        values = self._field(field_name)
        trail = self._trail(trail_name)
        scale = max(0.0, amount)
        for i in range(world.agents):
            if not self._agent_active(i, mask):
                continue
            idx = self._idx(world.x[i], world.y[i])
            trail.values[idx] = self._clamp01(trail.values[idx] + to_float(values[i]) * scale)

    def _diffuse_trail(self, trail_name: str) -> None:
        world = self._world()
        trail = self._trail(trail_name)
        w, h = world.width, world.height
        old = trail.values
        new = [0.0] * len(old)
        d = max(0.0, min(0.95, trail.diffuse))
        decay = max(0.0, min(0.95, trail.decay))
        for y in range(h):
            row = y * w
            for x in range(w):
                idx = row + x
                total = old[idx]
                count = 1
                if x > 0:
                    total += old[idx - 1]; count += 1
                if x + 1 < w:
                    total += old[idx + 1]; count += 1
                if y > 0:
                    total += old[idx - w]; count += 1
                if y + 1 < h:
                    total += old[idx + w]; count += 1
                value = (old[idx] * (1.0 - d) + (total / count) * d) * (1.0 - decay)
                if trail.sources[idx] > 0.0:
                    value = max(value, min(1.0, 0.90 * trail.sources[idx]))
                new[idx] = self._clamp01(value)
        trail.values[:] = new

    def _strengthen_trail(self, trail_name: str, amount: float, mask: list[bool] | None) -> None:
        world = self._world()
        trail = self._trail(trail_name)
        add = max(0.0, amount)
        for i in range(world.agents):
            if mask is not None and not mask[i]:
                continue
            idx = self._idx(world.x[i], world.y[i])
            trail.values[idx] = self._clamp01(trail.values[idx] + add)

    def _condition_mask(self, condition: ConditionExpr, self_obj: ObjectState | None = None) -> list[bool]:
        world = self._world()
        match condition:
            case FieldPredicate(field=field, op=op, value=value):
                return self._field_mask(field, op, self._condition_value(value, self_obj))
            case TrailPredicate(trail=trail, op=op, value=value):
                return self._trail_mask(trail, op, self._condition_value(value, self_obj))
            case MemoryPredicate(memory=memory, op=op, value=value):
                return self._memory_mask(memory, op, self._condition_value(value, self_obj))
            case MapHasPredicate(memory=memory, key=key):
                world = self._world()
                current = world.memory.get(memory)
                active = isinstance(current, dict) and str(self._resolve_literal(key)) in current
                return [active] * world.agents
            case FoodPredicate():
                mask = self._finds_food_mask()
                hits = sum(1 for value in mask if value)
                self._food_hits_last += hits
                self._food_hits_total += hits
                return mask
            case ConditionNot(expr=expr):
                return [not v for v in self._condition_mask(expr, self_obj)]
            case ConditionBinary(op="und", left=left, right=right):
                a = self._condition_mask(left, self_obj)
                if not any(a):
                    return a
                b = self._condition_mask(right, self_obj)
                return [x and y for x, y in zip(a, b)]
            case ConditionBinary(op="oder", left=left, right=right):
                a = self._condition_mask(left, self_obj)
                if all(a):
                    return a
                b = self._condition_mask(right, self_obj)
                return [x or y for x, y in zip(a, b)]
            case _:
                raise KeimRuntimeError(f"Unbekannte Bedingung: {condition!r}")

    def _field_mask(self, field: str, op: str, value: float) -> list[bool]:
        return [self._compare(to_float(v), op, value) for v in self._field(field)]

    def _trail_mask(self, trail_name: str, op: str, value: float) -> list[bool]:
        world = self._world()
        trail = self._trail(trail_name)
        return [self._compare(trail.values[self._idx(x, y)], op, value) for x, y in zip(world.x, world.y)]

    def _memory_mask(self, memory_name: str, op: str, value: float) -> list[bool]:
        world = self._world()
        active = self._compare(to_float(self._memory(memory_name)), op, value)
        return [active] * world.agents

    def _finds_food_mask(self) -> list[bool]:
        world = self._world()
        trail = world.trails.get("futter")
        if trail is None:
            if not world.trails:
                raise KeimRuntimeError("'agent findet futter' braucht mindestens eine Spur.")
            trail = next(iter(world.trails.values()))
        return [(trail.sources[self._idx(x, y)] > 0.0 or trail.values[self._idx(x, y)] > 0.96) for x, y in zip(world.x, world.y)]

    def _make_metrics(self, tick: int) -> dict[str, Any]:
        world = self._world()
        data: dict[str, Any] = {"tick": tick, "food_hits": self._food_hits_last, "resting": sum(1 for v in self._resting if v)}
        for name, values in world.fields.items():
            data[f"field_mean:{name}"] = self._mean(values)
        for name, trail in world.trails.items():
            data[f"trail_mean:{name}"] = self._mean(trail.values)
        for name, value in world.memory.items():
            data[f"memory:{name}"] = value
        return data

    def _agent_active(self, index: int, mask: list[bool] | None) -> bool:
        return not self._resting[index] and (mask is None or mask[index])

    def _field(self, name: str) -> list[float]:
        try:
            return self._world().fields[name]
        except KeyError as exc:
            raise KeimRuntimeError(f"Unbekanntes Feld: {name!r}") from exc

    def _trail(self, name: str) -> TrailState:
        try:
            return self._world().trails[name]
        except KeyError as exc:
            raise KeimRuntimeError(f"Unbekannte Spur: {name!r}") from exc

    def _memory(self, name: str) -> float:
        try:
            return self._world().memory[name]
        except KeyError as exc:
            raise KeimRuntimeError(f"Unbekannter Speicher: {name!r}") from exc

    def _idx(self, x: int, y: int) -> int:
        return y * self._world().width + x

    def _world(self) -> WorldState:
        if self.world is None:
            raise KeimRuntimeError("Keine Welt geladen.")
        return self.world

    def _require_world(self) -> None:
        if self.world is None:
            raise KeimRuntimeError("Zuerst muss eine Welt deklariert werden.")

    @staticmethod
    def _compare(left: float, op: str, right: float) -> bool:
        match op:
            case ">": return left > right
            case ">=": return left >= right
            case "<": return left < right
            case "<=": return left <= right
            case "==": return abs(left - right) < 1e-7
            case "!=": return abs(left - right) >= 1e-7
            case _: raise KeimRuntimeError(f"Unbekannter Vergleich: {op}")

    @staticmethod
    def _clamp01(value: float) -> float:
        if value < 0.0:
            return 0.0
        if value > 1.0:
            return 1.0
        return value

    @staticmethod
    def _mean(values: list[object]) -> float:
        nums = [to_float(v) for v in values]
        return sum(nums) / len(nums) if nums else 0.0
