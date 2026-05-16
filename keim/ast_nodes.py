from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


CompareOp = Literal[">", ">=", "<", "<=", "==", "!="]
FieldChangeKind = Literal["waechst", "sinkt", "verliert", "bekommt"]
MemoryChangeKind = Literal["setzt", "waechst", "sinkt", "verliert", "bekommt"]
BoolOp = Literal["und", "oder"]
AggregateKind = Literal["mittel", "summe", "min", "max"]
AggregateSourceKind = Literal["feld", "spur"]
ColumnKind = Literal["zahl", "ganzzahl", "bool", "text", "array", "karte", "referenz"]
ValueKind = ColumnKind


@dataclass(slots=True, frozen=True)
class SourceLocation:
    line: int
    text: str


@dataclass(slots=True, frozen=True)
class WorldDecl:
    name: str
    agents: int
    width: int
    height: int
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class FieldDecl:
    name: str
    initial: object
    loc: SourceLocation
    kind: ValueKind = "zahl"


@dataclass(slots=True, frozen=True)
class MemoryDecl:
    name: str
    initial: object
    loc: SourceLocation
    kind: ValueKind = "zahl"


@dataclass(slots=True, frozen=True)
class TrailDecl:
    name: str
    initial: float
    sources: int
    diffuse: float
    decay: float
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class SourceDecl:
    trail: str
    x: int
    y: int
    strength: float
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class FunctionDecl:
    name: str
    params: tuple[str, ...]
    expression: str
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class TableColumn:
    name: str
    kind: ColumnKind


@dataclass(slots=True, frozen=True)
class TableDecl:
    name: str
    columns: tuple[TableColumn, ...]
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class TableIndexDecl:
    table: str
    column: str
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class DatabaseDecl:
    name: str
    path: str
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class ObjectPropertyDecl:
    name: str
    initial: object
    loc: SourceLocation
    kind: ValueKind = "zahl"


@dataclass(slots=True, frozen=True)
class MethodDecl:
    name: str
    steps: tuple["Step", ...]
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class ClassDecl:
    name: str
    properties: tuple[ObjectPropertyDecl, ...]
    methods: tuple[MethodDecl, ...]
    loc: SourceLocation
    parent: str | None = None


@dataclass(slots=True, frozen=True)
class ObjectDecl:
    name: str
    class_name: str
    overrides: tuple[tuple[str, object], ...]
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class SelfPropertyRef:
    name: str


ConditionValue = float | SelfPropertyRef


@dataclass(slots=True, frozen=True)
class AgentFieldChange:
    field: str
    kind: FieldChangeKind
    amount: float
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class FieldCompute:
    field: str
    expression: str
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class MemoryChange:
    memory: str
    kind: MemoryChangeKind
    amount: float
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class MemoryAggregate:
    memory: str
    aggregate: AggregateKind
    source_kind: AggregateSourceKind
    source: str
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class TableInsert:
    table: str
    values: tuple[tuple[str, str], ...]
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class DatabaseSave:
    database: str
    table: str
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class TableQuery:
    table: str
    column: str
    op: CompareOp
    value: object
    target_memory: str
    loc: SourceLocation




@dataclass(slots=True, frozen=True)
class MapSet:
    memory: str
    key: object
    value: object
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class MapGet:
    memory: str
    key: object
    target_memory: str
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class MapDelete:
    memory: str
    key: object
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class MapHas:
    memory: str
    key: object
    target_memory: str
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class JsonParse:
    source_memory: str
    target_memory: str
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class JsonStringify:
    source_memory: str
    target_memory: str
    loc: SourceLocation




@dataclass(slots=True, frozen=True)
class TimeNow:
    target_memory: str
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class CryptoHash:
    algorithm: str
    source_memory: str
    target_memory: str
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class ProcessRun:
    command: str
    target_memory: str
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class HttpServerStart:
    port: int
    response_memory: str
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class ForeignLibraryDecl:
    name: str
    path: str
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class FfiCall:
    library: str
    function: str
    args: tuple[object, ...]
    target_memory: str | None
    result_kind: ValueKind
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class WebGuiDecl:
    name: str
    port: int
    title: str
    api_base: str
    loc: SourceLocation



@dataclass(slots=True, frozen=True)
class PermissionDecl:
    permission: str
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class UseDecl:
    module: str
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class GrafikCommand:
    kind: str
    args: tuple[object, ...]
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class AudioCommand:
    kind: str
    args: tuple[object, ...]
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class DebugWatch:
    memory: str
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class DebugSend:
    label: str
    loc: SourceLocation

@dataclass(slots=True, frozen=True)
class AsyncTaskDecl:
    name: str
    steps: tuple["Step", ...]
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class AwaitTask:
    name: str
    target_memory: str | None
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class ListAppend:
    memory: str
    value: object
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class ListPop:
    memory: str
    target_memory: str | None
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class FileTableIO:
    mode: Literal["read", "write"]
    fmt: Literal["json", "csv"]
    path: str
    table: str
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class WebRequest:
    method: Literal["GET"]
    url: str
    target_memory: str
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class PathFind:
    start_x: int
    start_y: int
    goal_x: int
    goal_y: int
    cost_trail: str | None
    target_table: str
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class ExportImage:
    fmt: Literal["bmp", "png"]
    path: str
    source_kind: Literal["spur", "feld"]
    source: str
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class StartDashboard:
    path: str
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class DeleteObject:
    name: str
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class CollectGarbage:
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class ObjectCall:
    object_name: str
    method: str
    loc: SourceLocation



@dataclass(slots=True, frozen=True)
class SpawnAgents:
    count: int
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class KillAgents:
    count: int | None
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class SpawnObject:
    name: str
    class_name: str
    overrides: tuple[tuple[str, object], ...]
    loc: SourceLocation

@dataclass(slots=True, frozen=True)
class AgentFollowTrail:
    trail: str
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class AgentAvoidTrail:
    trail: str
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class AgentWander:
    chance: float
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class AgentRest:
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class FieldTrailCoupling:
    field: str
    trail: str
    kind: Literal["folgt", "meidet"]
    amount: float
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class FieldTrailEmission:
    field: str
    trail: str
    amount: float
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class TrailDiffuse:
    trail: str
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class TrailStrengthen:
    trail: str
    amount: float
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class ShowWorld:
    target: str
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class CallRule:
    name: str
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class FieldPredicate:
    field: str
    op: CompareOp
    value: ConditionValue


@dataclass(slots=True, frozen=True)
class TrailPredicate:
    trail: str
    op: CompareOp
    value: ConditionValue


@dataclass(slots=True, frozen=True)
class MemoryPredicate:
    memory: str
    op: CompareOp
    value: ConditionValue


@dataclass(slots=True, frozen=True)
class MapHasPredicate:
    memory: str
    key: object


@dataclass(slots=True, frozen=True)
class FoodPredicate:
    pass


@dataclass(slots=True, frozen=True)
class ConditionNot:
    expr: "ConditionExpr"


@dataclass(slots=True, frozen=True)
class ConditionBinary:
    op: BoolOp
    left: "ConditionExpr"
    right: "ConditionExpr"


ConditionExpr = FieldPredicate | TrailPredicate | MemoryPredicate | MapHasPredicate | FoodPredicate | ConditionNot | ConditionBinary


Action = (
    FieldTrailCoupling
    | FieldTrailEmission
    | AgentFieldChange
    | FieldCompute
    | MemoryChange
    | MemoryAggregate
    | TableInsert
    | DatabaseSave
    | TableQuery
    | MapSet
    | MapGet
    | MapDelete
    | MapHas
    | JsonParse
    | JsonStringify
    | TimeNow
    | CryptoHash
    | ProcessRun
    | HttpServerStart
    | FfiCall
    | GrafikCommand
    | AudioCommand
    | DebugWatch
    | DebugSend
    | AwaitTask
    | ListAppend
    | ListPop
    | FileTableIO
    | WebRequest
    | PathFind
    | ExportImage
    | StartDashboard
    | ObjectCall
    | SpawnAgents
    | KillAgents
    | SpawnObject
    | DeleteObject
    | CollectGarbage
    | AgentFollowTrail
    | AgentAvoidTrail
    | AgentWander
    | AgentRest
    | TrailStrengthen
    | CallRule
)


@dataclass(slots=True, frozen=True)
class FieldCondition:
    field: str
    op: CompareOp
    value: ConditionValue
    action: Action
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class TrailCondition:
    trail: str
    op: CompareOp
    value: ConditionValue
    action: Action
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class MemoryCondition:
    memory: str
    op: CompareOp
    value: ConditionValue
    action: Action
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class AgentFindsFoodCondition:
    action: Action
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class CompositeCondition:
    condition: ConditionExpr
    action: Action
    loc: SourceLocation




@dataclass(slots=True, frozen=True)
class TryCatchBlock:
    try_steps: tuple["Step", ...]
    error_memory: str
    catch_steps: tuple["Step", ...]
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class IfBlock:
    condition: ConditionExpr
    steps: tuple["Step", ...]
    else_steps: tuple["Step", ...]
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class RepeatBlock:
    count: int
    steps: tuple["Step", ...]
    loc: SourceLocation


Step = (
    FieldTrailCoupling
    | FieldTrailEmission
    | AgentFieldChange
    | FieldCompute
    | MemoryChange
    | MemoryAggregate
    | TableInsert
    | DatabaseSave
    | TableQuery
    | MapSet
    | MapGet
    | MapDelete
    | MapHas
    | JsonParse
    | JsonStringify
    | TimeNow
    | CryptoHash
    | ProcessRun
    | HttpServerStart
    | FfiCall
    | GrafikCommand
    | AudioCommand
    | DebugWatch
    | DebugSend
    | AwaitTask
    | ListAppend
    | ListPop
    | FileTableIO
    | WebRequest
    | PathFind
    | ExportImage
    | StartDashboard
    | ObjectCall
    | SpawnAgents
    | KillAgents
    | SpawnObject
    | DeleteObject
    | CollectGarbage
    | AgentFollowTrail
    | AgentAvoidTrail
    | AgentWander
    | AgentRest
    | TrailDiffuse
    | TrailStrengthen
    | ShowWorld
    | CallRule
    | FieldCondition
    | TrailCondition
    | MemoryCondition
    | AgentFindsFoodCondition
    | CompositeCondition
    | IfBlock
    | RepeatBlock
    | TryCatchBlock
)




@dataclass(slots=True, frozen=True)
class HttpRouteDecl:
    method: str
    path: str
    steps: tuple["Step", ...]
    response_memory: str
    request_memory: str | None
    status_memory: str | None
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class HttpServiceDecl:
    name: str
    port: int
    routes: tuple[HttpRouteDecl, ...]
    workers: int
    loc: SourceLocation



@dataclass(slots=True, frozen=True)
class RoundBlock:
    steps: tuple[Step, ...]
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class PeriodicBlock:
    interval: int
    steps: tuple[Step, ...]
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class RuleDecl:
    name: str
    steps: tuple[Step, ...]
    loc: SourceLocation


@dataclass(slots=True, frozen=True)
class EventDecl:
    name: str
    condition: ConditionExpr
    steps: tuple[Step, ...]
    loc: SourceLocation


TopLevel = (
    WorldDecl
    | FieldDecl
    | MemoryDecl
    | TrailDecl
    | SourceDecl
    | FunctionDecl
    | TableDecl
    | TableIndexDecl
    | DatabaseDecl
    | ClassDecl
    | ObjectDecl
    | RoundBlock
    | PeriodicBlock
    | RuleDecl
    | EventDecl
    | HttpServiceDecl
    | ForeignLibraryDecl
    | WebGuiDecl
    | PermissionDecl
    | UseDecl
    | AsyncTaskDecl
)


@dataclass(slots=True, frozen=True)
class Program:
    source_name: str
    declarations: tuple[TopLevel, ...]
