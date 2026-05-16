from __future__ import annotations

from pathlib import Path
import re
from typing import NoReturn

from .ast_nodes import (
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
    MethodDecl,
    ObjectCall,
    ObjectDecl,
    ObjectPropertyDecl,
    SelfPropertyRef,
    TableColumn,
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
from .errors import KeimSyntaxError
from .typesys import parse_type, parse_literal, KeimType
from .expressions import builtin_function_names, compile_agent_expression, compile_user_function
from .preprocessor import expand_macros
from .source_loader import load_raw_with_imports


_COMPARE = {">", ">=", "<", "<=", "==", "!="}
_AGGREGATES = {"mittel", "summe", "min", "max"}
_SOURCES = {"feld", "spur"}
_FUNCTION_RE = re.compile(r"^funktion\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\((?P<params>[^)]*)\)\s*=\s*(?P<expr>.+)$")


def parse_file(path: str | Path) -> Program:
    raw, _imports = load_raw_with_imports(path)
    return parse_source(raw, source_name=str(path))


def parse_source(source: str, source_name: str = "<string>", *, preprocess: bool = True) -> Program:
    # v2.4-v2.6: Makros/Werte bleiben Vorstufe, reine Funktionen,
    # Ereignisblöcke und aggregierende Speicheraktionen bleiben im AST sichtbar.
    if preprocess:
        source = expand_macros(source, expand_control=False).source

    raw_lines = source.splitlines()
    function_arities = _scan_function_arities(raw_lines)
    declarations = []
    seen_round_block = False
    i = 0

    while i < len(raw_lines):
        raw = raw_lines[i]
        cleaned = _strip_comment(raw)
        if not cleaned.strip():
            i += 1
            continue

        indent = _indent_of(cleaned)
        loc = _loc(i + 1, raw)
        if indent != 0:
            _fail("Top-Level-Deklarationen dürfen nicht eingerückt sein.", loc)

        line = cleaned.strip()
        if line == "jede runde:":
            if seen_round_block:
                _fail("Es gibt bereits einen 'jede runde:'-Block.", loc)
            steps, i = _parse_steps(raw_lines, i + 1, base_indent=4, function_arities=function_arities)
            declarations.append(RoundBlock(tuple(steps), loc))
            seen_round_block = True
            continue

        if line.startswith("ereignis "):
            event = _parse_event_header(line, loc)
            steps, i = _parse_steps(raw_lines, i + 1, base_indent=4, function_arities=function_arities)
            if not steps:
                _fail("Ereignisblock ist leer.", loc)
            declarations.append(EventDecl(name=event[0], condition=event[1], steps=tuple(steps), loc=loc))
            continue

        if line.startswith("klasse "):
            klass, i = _parse_class_block(raw_lines, i, function_arities=function_arities)
            declarations.append(klass)
            continue

        if line.startswith("hintergrund ") and line.endswith(":"):
            name = line.removeprefix("hintergrund ").removesuffix(":").strip()
            _require_ident(name, loc)
            steps, i = _parse_steps(raw_lines, i + 1, base_indent=4, function_arities=function_arities)
            if not steps:
                _fail("Hintergrund-Task ist leer.", loc)
            declarations.append(AsyncTaskDecl(name=name, steps=tuple(steps), loc=loc))
            continue

        if line.startswith("server ") and line.endswith(":"):
            service, i = _parse_http_service_block(raw_lines, i, function_arities=function_arities)
            declarations.append(service)
            continue

        words = line.split()
        match words:
            case ["alle", interval, "runden:"]:
                steps, i = _parse_steps(raw_lines, i + 1, base_indent=4, function_arities=function_arities)
                declarations.append(PeriodicBlock(interval=_positive_int(interval, loc), steps=tuple(steps), loc=loc))
                continue
            case ["alle", interval, "runden"]:
                _fail("Periodische Blöcke brauchen einen Doppelpunkt: alle N runden:", loc)
            case ["regel", name_colon] if name_colon.endswith(":"):
                name = name_colon[:-1]
                _require_ident(name, loc)
                steps, i = _parse_steps(raw_lines, i + 1, base_indent=4, function_arities=function_arities)
                declarations.append(RuleDecl(name=name, steps=tuple(steps), loc=loc))
                continue
            case ["regel", name, ":"]:
                _require_ident(name, loc)
                steps, i = _parse_steps(raw_lines, i + 1, base_indent=4, function_arities=function_arities)
                declarations.append(RuleDecl(name=name, steps=tuple(steps), loc=loc))
                continue
            case ["regel", *_]:
                _fail("Regeln werden als Block geschrieben: regel NAME:", loc)

        declarations.append(_parse_top_level(line, loc, function_arities))
        i += 1

    return Program(source_name=source_name, declarations=tuple(declarations))


def _scan_function_arities(raw_lines: list[str]) -> dict[str, int]:
    result: dict[str, int] = {}
    for line_no, raw in enumerate(raw_lines, start=1):
        cleaned = _strip_comment(raw)
        if not cleaned.strip() or _indent_of(cleaned) != 0:
            continue
        m = _FUNCTION_RE.match(cleaned.strip())
        if not m:
            continue
        loc = _loc(line_no, raw)
        name = m.group("name")
        if name in result:
            _fail(f"Funktion {name!r} wurde mehrfach deklariert.", loc)
        if name in builtin_function_names():
            _fail(f"Funktion {name!r} überschreibt eine eingebaute Ausdrucksfunktion.", loc)
        params = _parse_params(m.group("params"), loc)
        result[name] = len(params)
    return result


def _parse_steps(raw_lines: list[str], start: int, *, base_indent: int, function_arities: dict[str, int]) -> tuple[list[Step], int]:
    steps: list[Step] = []
    i = start

    while i < len(raw_lines):
        raw = raw_lines[i]
        cleaned = _strip_comment(raw)
        if not cleaned.strip():
            i += 1
            continue

        indent = _indent_of(cleaned)
        if indent < base_indent:
            break
        loc = _loc(i + 1, raw)
        if indent > base_indent:
            _fail("Unerwartete Einrückung. Blöcke müssen mit genau vier Leerzeichen pro Ebene beginnen.", loc)

        line = cleaned.strip()
        if line == "sonst:" or line.startswith("fange "):
            break

        if line == "versuche:":
            try_steps, next_i = _parse_steps(raw_lines, i + 1, base_indent=base_indent + 4, function_arities=function_arities)
            if not try_steps:
                _fail("Versuche-Block ist leer.", loc)
            j = _skip_blank(raw_lines, next_i)
            if j >= len(raw_lines):
                _fail("Versuche-Block braucht einen Fange-Block.", loc)
            catch_cleaned = _strip_comment(raw_lines[j])
            catch_line = catch_cleaned.strip()
            if _indent_of(catch_cleaned) != base_indent or not catch_line.startswith("fange "):
                _fail("Versuche-Block braucht: fange fehler in speicher NAME:", _loc(j + 1, raw_lines[j]))
            error_memory = _parse_catch_header(catch_line, _loc(j + 1, raw_lines[j]))
            catch_steps, after_catch = _parse_steps(raw_lines, j + 1, base_indent=base_indent + 4, function_arities=function_arities)
            if not catch_steps:
                _fail("Fange-Block ist leer.", _loc(j + 1, raw_lines[j]))
            steps.append(TryCatchBlock(try_steps=tuple(try_steps), error_memory=error_memory, catch_steps=tuple(catch_steps), loc=loc))
            i = after_catch
            continue

        if line.startswith("wenn ") and line.endswith(":"):
            condition_text = line.removeprefix("wenn ").removesuffix(":").strip()
            if not condition_text:
                _fail("Wenn-Block braucht eine Bedingung.", loc)
            then_steps, next_i = _parse_steps(raw_lines, i + 1, base_indent=base_indent + 4, function_arities=function_arities)
            if not then_steps:
                _fail("Wenn-Block ist leer.", loc)

            else_steps: tuple[Step, ...] = ()
            j = _skip_blank(raw_lines, next_i)
            if j < len(raw_lines):
                else_cleaned = _strip_comment(raw_lines[j])
                if else_cleaned.strip() == "sonst:" and _indent_of(else_cleaned) == base_indent:
                    parsed_else, after_else = _parse_steps(raw_lines, j + 1, base_indent=base_indent + 4, function_arities=function_arities)
                    if not parsed_else:
                        _fail("Sonst-Block ist leer.", _loc(j + 1, raw_lines[j]))
                    else_steps = tuple(parsed_else)
                    next_i = after_else

            steps.append(IfBlock(condition=_parse_condition_expr(condition_text, loc), steps=tuple(then_steps), else_steps=else_steps, loc=loc))
            i = next_i
            continue

        if line.startswith("wiederhole ") and line.endswith(":"):
            body = line.removeprefix("wiederhole ").removesuffix(":").strip()
            count = _parse_repeat_count(body, loc)
            child_steps, next_i = _parse_steps(raw_lines, i + 1, base_indent=base_indent + 4, function_arities=function_arities)
            if not child_steps:
                _fail("Wiederholungsblock ist leer.", loc)
            steps.append(RepeatBlock(count=count, steps=tuple(child_steps), loc=loc))
            i = next_i
            continue

        steps.append(_parse_step(line, loc, function_arities))
        i += 1

    return steps, i


def _parse_top_level(line: str, loc: SourceLocation, function_arities: dict[str, int]):
    words = line.split()
    if line.startswith("tabelle ") and " mit " in line:
        return _parse_table_decl(line, loc)
    if line.startswith("index "):
        return _parse_table_index_decl(line, loc)
    if line.startswith("datenbank "):
        return _parse_database_decl(line, loc)
    if line.startswith("objekt "):
        return _parse_object_decl(line, loc)
    if line.startswith("funktion "):
        m = _FUNCTION_RE.match(line)
        if not m:
            _fail("Funktionen werden geschrieben als: funktion NAME(a, b) = AUSDRUCK", loc)
        name = m.group("name")
        params = _parse_params(m.group("params"), loc)
        expr = m.group("expr").strip()
        compile_user_function(name, params, expr, function_arities=function_arities, line=loc.line, text=loc.text)
        return FunctionDecl(name=name, params=params, expression=expr, loc=loc)

    if line.startswith("berechtigung "):
        perm = line.removeprefix("berechtigung ").strip()
        return PermissionDecl(permission=perm, loc=loc)
    if line.startswith("verwende "):
        module = line.removeprefix("verwende ").strip()
        return UseDecl(module=module, loc=loc)
    m_generic = re.match(r"^(speicher|feld)\s+([A-Za-z_][A-Za-z0-9_]*)\s+ist\s+(.+)$", line)
    if m_generic:
        decl, name, type_raw = m_generic.groups()
        type_raw = type_raw.strip()
        if type_raw.startswith("liste<"):
            initial = []
        elif type_raw.startswith("karte<"):
            initial = {}
        elif type_raw in {"text", "string"}:
            initial = ""
        elif type_raw in {"bool", "boolean"}:
            initial = False
        else:
            initial = 0
        if decl == "speicher":
            return MemoryDecl(name=name, initial=initial, kind=type_raw, loc=loc)
        return FieldDecl(name=name, initial=initial, kind=type_raw, loc=loc)

    if line.startswith("bibliothek "):
        # bibliothek NAME laedt "pfad/zur/lib.dll"
        m = re.match(r'^bibliothek\s+([A-Za-z_][A-Za-z0-9_]*)\s+laedt\s+(.+)$', line)
        if not m:
            _fail('Bibliothek erwartet: bibliothek NAME laedt "PFAD"', loc)
        return ForeignLibraryDecl(name=m.group(1), path=str(_auto_literal(m.group(2).strip(), loc)), loc=loc)
    if line.startswith("webgui "):
        # webgui NAME bei 18081 titel "Keim" api "http://127.0.0.1:18080"
        m = re.match(r'^webgui\s+([A-Za-z_][A-Za-z0-9_]*)\s+bei\s+(\d+)\s+titel\s+(.+?)\s+api\s+(.+)$', line)
        if not m:
            _fail('Web-GUI erwartet: webgui NAME bei PORT titel "Titel" api "URL"', loc)
        return WebGuiDecl(name=m.group(1), port=_positive_int(m.group(2), loc), title=str(_auto_literal(m.group(3).strip(), loc)), api_base=str(_auto_literal(m.group(4).strip(), loc)), loc=loc)

    # Native Listen: speicher werte liste mit zahl startet bei [1,2,3]
    if words[:3] in (["speicher", words[1] if len(words)>1 else "", "liste"] if len(words)>1 else []):
        pass
    if len(words) >= 8 and words[0] in {"speicher", "feld"} and words[2] == "liste" and words[3] == "mit" and words[5:7] == ["startet", "bei"]:
        name = words[1]
        elem_kind = words[4]
        if elem_kind not in {"zahl", "ganzzahl", "bool", "text", "array", "karte", "referenz"}:
            _fail("Listen brauchen einen Elementtyp: liste mit zahl|ganzzahl|bool|text|array", loc)
        raw = line.split(" startet bei ", 1)[1]
        decl_kind = f"liste<{elem_kind}>"
        value = _typed_literal(raw, decl_kind, loc)
        if words[0] == "speicher":
            return MemoryDecl(name=name, initial=value, kind=decl_kind, loc=loc)
        return FieldDecl(name=name, initial=value, kind=decl_kind, loc=loc)

    match words:
        case ["welt", name, "mit", agents, "agenten", "groesse", width, height]:
            return WorldDecl(name=name, agents=_positive_int(agents, loc), width=_positive_int(width, loc), height=_positive_int(height, loc), loc=loc)
        case ["welt", name, "mit", agents, "agenten"]:
            return WorldDecl(name=name, agents=_positive_int(agents, loc), width=80, height=25, loc=loc)
        case ["feld", name, kind, "startet", "bei", initial] if kind in {"zahl", "ganzzahl", "bool", "text", "array", "karte", "referenz"}:
            return FieldDecl(name=name, initial=_typed_literal(initial, kind, loc), kind=kind, loc=loc)
        case ["feld", name, "startet", "bei", initial]:
            return FieldDecl(name=name, initial=_number(initial, loc), kind="zahl", loc=loc)
        case ["speicher", name, kind, "startet", "bei", initial] if kind in {"zahl", "ganzzahl", "bool", "text", "array", "karte", "referenz"}:
            return MemoryDecl(name=name, initial=_typed_literal(initial, kind, loc), kind=kind, loc=loc)
        case ["speicher", name, "startet", "bei", initial]:
            return MemoryDecl(name=name, initial=_number(initial, loc), kind="zahl", loc=loc)
        case ["spur", name, "startet", "bei", initial, "quellen", sources, "diffundiert", diffuse, "zerfaellt", decay]:
            return TrailDecl(name=name, initial=_number(initial, loc), sources=_int(sources, loc), diffuse=_number(diffuse, loc), decay=_number(decay, loc), loc=loc)
        case ["spur", name, "startet", "bei", initial]:
            return TrailDecl(name=name, initial=_number(initial, loc), sources=4, diffuse=0.18, decay=0.02, loc=loc)
        case ["quelle", trail, "bei", x, y, "staerke", strength]:
            return SourceDecl(trail=trail, x=_int(x, loc), y=_int(y, loc), strength=_number(strength, loc), loc=loc)
        case _:
            _fail("Keim versteht diese Deklaration noch nicht.", loc)



def _parse_http_service_block(raw_lines: list[str], start: int, *, function_arities: dict[str, int]) -> tuple[HttpServiceDecl, int]:
    """Parse a daemon-style HTTP service.

    Syntax:
        server api bei 8080 parallel 8:
            route GET "/health" antwortet speicher antwort:
                ...
            route POST "/control" liest speicher eingang_json antwortet speicher antwort status speicher code:
                ...
    """
    raw = raw_lines[start]
    line = _strip_comment(raw).strip()
    loc = _loc(start + 1, raw)
    words = line.removesuffix(":").split()
    if len(words) not in {4, 6} or words[0] != "server" or words[2] != "bei":
        _fail("HTTP-Dienst erwartet: server NAME bei PORT [parallel WORKERS]:", loc)
    name = words[1]
    _require_ident(name, loc)
    port = _positive_int(words[3], loc)
    workers = 4
    if len(words) == 6:
        if words[4] != "parallel":
            _fail("HTTP-Dienst erwartet: server NAME bei PORT parallel WORKERS:", loc)
        workers = _positive_int(words[5], loc)
    if workers > 256:
        _fail("HTTP-Dienst erlaubt höchstens 256 parallele Handler.", loc)

    routes: list[HttpRouteDecl] = []
    i = start + 1
    while i < len(raw_lines):
        cleaned = _strip_comment(raw_lines[i])
        if not cleaned.strip():
            i += 1
            continue
        indent = _indent_of(cleaned)
        if indent < 4:
            break
        rloc = _loc(i + 1, raw_lines[i])
        if indent != 4:
            _fail("Routen im server-Block müssen mit genau vier Leerzeichen eingerückt sein.", rloc)
        route_line = cleaned.strip()
        if not route_line.startswith("route ") or not route_line.endswith(":"):
            _fail("Route erwartet: route GET|POST \"/pfad\" [liest speicher BODY] antwortet speicher RESP [status speicher CODE]:", rloc)
        method, path, request_memory, response_memory, status_memory = _parse_http_route_header(route_line, rloc)
        steps, next_i = _parse_steps(raw_lines, i + 1, base_indent=8, function_arities=function_arities)
        if not steps:
            _fail("Route-Handler ist leer.", rloc)
        routes.append(HttpRouteDecl(method=method, path=path, request_memory=request_memory, response_memory=response_memory, status_memory=status_memory, steps=tuple(steps), loc=rloc))
        i = next_i
    if not routes:
        _fail("HTTP-Dienst braucht mindestens eine route.", loc)
    return HttpServiceDecl(name=name, port=port, workers=workers, routes=tuple(routes), loc=loc), i


def _parse_http_route_header(line: str, loc: SourceLocation) -> tuple[str, str, str | None, str, str | None]:
    # route POST "/control" liest speicher eingang_json antwortet speicher ausgang_json status speicher statuscode:
    body = line.removesuffix(":").strip()
    m = re.match(r'^route\s+(GET|POST|PUT|DELETE|PATCH)\s+(".*?"|\'.*?\'|\S+)(?P<rest>.*)$', body, flags=re.IGNORECASE)
    if not m:
        _fail("Route erwartet Methode und Pfad: route GET \"/pfad\" ...:", loc)
    method = m.group(1).upper()
    path_token = m.group(2)
    path = _auto_literal(path_token, loc)
    if not isinstance(path, str) or not path.startswith("/"):
        _fail("Routenpfad muss mit / beginnen.", loc)
    rest = m.group("rest").strip()
    request_memory: str | None = None
    status_memory: str | None = None
    words = rest.split()
    # optional: liest speicher BODY
    if words[:2] == ["liest", "speicher"]:
        if len(words) < 3:
            _fail("Route liest speicher NAME.", loc)
        request_memory = words[2]
        _require_ident(request_memory, loc)
        words = words[3:]
    if len(words) < 3 or words[:2] != ["antwortet", "speicher"]:
        _fail("Route braucht: antwortet speicher NAME", loc)
    response_memory = words[2]
    _require_ident(response_memory, loc)
    words = words[3:]
    if words:
        if len(words) != 3 or words[:2] != ["status", "speicher"]:
            _fail("Optionaler Status erwartet: status speicher NAME", loc)
        status_memory = words[2]
        _require_ident(status_memory, loc)
    return method, path, request_memory, response_memory, status_memory


def _parse_event_header(line: str, loc: SourceLocation) -> tuple[str, ConditionExpr]:
    # ereignis NAME wenn BEDINGUNG:
    if not line.endswith(":"):
        _fail("Ereignisse werden als Block geschrieben: ereignis NAME wenn BEDINGUNG:", loc)
    body = line.removeprefix("ereignis ").removesuffix(":").strip()
    if " wenn " not in body:
        _fail("Ereignisse brauchen eine Bedingung: ereignis NAME wenn BEDINGUNG:", loc)
    name, condition = body.split(" wenn ", 1)
    name = name.strip()
    _require_ident(name, loc)
    condition = condition.strip()
    if not condition:
        _fail("Ereignis braucht eine Bedingung.", loc)
    return name, _parse_condition_expr(condition, loc)


def _parse_step(line: str, loc: SourceLocation, function_arities: dict[str, int]) -> Step:
    if line.startswith("wenn "):
        return _parse_condition(line, loc, function_arities)
    return _parse_action(line, loc, function_arities)


def _parse_condition(line: str, loc: SourceLocation, function_arities: dict[str, int]) -> FieldCondition | TrailCondition | MemoryCondition | AgentFindsFoodCondition | CompositeCondition:
    if ":" not in line:
        _fail("Bedingungen brauchen einen Doppelpunkt: wenn ...: aktion", loc)
    condition_text, action_text = line.removeprefix("wenn ").split(":", 1)
    action_text = action_text.strip()
    if not action_text:
        _fail("Einzeilige Bedingungen brauchen nach ':' eine Aktion oder müssen als Block geschrieben werden.", loc)
    action = _parse_action(action_text, loc, function_arities)
    condition = _parse_condition_expr(condition_text.strip(), loc)

    # Alte Einzelknoten bleiben erhalten, damit Bytecode/Backends lesbar bleiben.
    match condition:
        case FoodPredicate():
            return AgentFindsFoodCondition(action=action, loc=loc)
        case FieldPredicate(field=field, op=op, value=value):
            return FieldCondition(field=field, op=op, value=value, action=action, loc=loc)
        case TrailPredicate(trail=trail, op=op, value=value):
            return TrailCondition(trail=trail, op=op, value=value, action=action, loc=loc)
        case MemoryPredicate(memory=memory, op=op, value=value):
            return MemoryCondition(memory=memory, op=op, value=value, action=action, loc=loc)
        case _:
            return CompositeCondition(condition=condition, action=action, loc=loc)


def _parse_condition_expr(text: str, loc: SourceLocation) -> ConditionExpr:
    tokens = _condition_tokens(text)
    parser = _ConditionParser(tokens, loc)
    expr = parser.parse()
    if parser.has_more:
        _fail(f"Unerwarteter Teil in Bedingung: {parser.peek()!r}.", loc)
    return expr


def _condition_tokens(text: str) -> list[str]:
    return text.replace("(", " ( ").replace(")", " ) ").split()


class _ConditionParser:
    def __init__(self, tokens: list[str], loc: SourceLocation) -> None:
        self.tokens = tokens
        self.i = 0
        self.loc = loc

    @property
    def has_more(self) -> bool:
        return self.i < len(self.tokens)

    def peek(self) -> str | None:
        return self.tokens[self.i] if self.has_more else None

    def pop(self) -> str:
        if not self.has_more:
            _fail("Unvollständige Bedingung.", self.loc)
        token = self.tokens[self.i]
        self.i += 1
        return token

    def parse(self) -> ConditionExpr:
        if not self.tokens:
            _fail("Leere Bedingung.", self.loc)
        return self._parse_or()

    def _parse_or(self) -> ConditionExpr:
        left = self._parse_and()
        while self.peek() == "oder":
            self.pop()
            right = self._parse_and()
            left = ConditionBinary(op="oder", left=left, right=right)
        return left

    def _parse_and(self) -> ConditionExpr:
        left = self._parse_unary()
        while self.peek() == "und":
            self.pop()
            right = self._parse_unary()
            left = ConditionBinary(op="und", left=left, right=right)
        return left

    def _parse_unary(self) -> ConditionExpr:
        if self.peek() == "nicht":
            self.pop()
            return ConditionNot(expr=self._parse_unary())
        return self._parse_atom()

    def _parse_atom(self) -> ConditionExpr:
        if self.peek() == "(":
            self.pop()
            expr = self._parse_or()
            if self.peek() != ")":
                _fail("Schließende Klammer in Bedingung fehlt.", self.loc)
            self.pop()
            return expr

        token = self.pop()
        if token == "agent":
            second = self.pop()
            if second == "findet":
                third = self.pop()
                if third == "futter":
                    return FoodPredicate()
            if second == "riecht":
                if self.pop() != "spur":
                    _fail("Erwartet: agent riecht spur NAME OP WERT.", self.loc)
                trail = self.pop()
                op = self.pop()
                value = self.pop()
                if op not in _COMPARE:
                    _fail(f"Unbekannter Vergleichsoperator {op!r}.", self.loc)
                return TrailPredicate(trail=trail, op=op, value=_condition_value(value, self.loc))
            _fail("Keim versteht diese Agenten-Bedingung noch nicht.", self.loc)

        if token == "karte":
            memory = self.pop()
            verb = self.pop()
            if verb not in {"enthaelt", "hat"}:
                _fail("Karten-Bedingung erwartet: karte NAME enthaelt KEY.", self.loc)
            key = self.pop()
            return MapHasPredicate(memory=memory, key=_condition_value(key, self.loc))

        if token == "speicher":
            memory = self.pop()
            op = self.pop()
            value = self.pop()
            if op not in _COMPARE:
                _fail(f"Unbekannter Vergleichsoperator {op!r}.", self.loc)
            return MemoryPredicate(memory=memory, op=op, value=_condition_value(value, self.loc))

        # Feldbedingung: hunger > 0.4
        field = token
        op = self.pop()
        value = self.pop()
        if op not in _COMPARE:
            _fail(f"Unbekannter Vergleichsoperator {op!r}.", self.loc)
        return FieldPredicate(field=field, op=op, value=_condition_value(value, self.loc))


def _parse_action(line: str, loc: SourceLocation, function_arities: dict[str, int]) -> Action | TrailDiffuse | ShowWorld:
    words = line.split()
    if line.startswith("grafik "):
        return _parse_grafik_action(line, loc)
    if line.startswith("fenster "):
        return _parse_fenster_action(line, loc)
    if line.startswith("audio "):
        return _parse_audio_action(line, loc)
    if line.startswith("debug "):
        return _parse_debug_action(line, loc)
    if line.startswith("ffi "):
        return _parse_ffi_call(line, loc)
    if line.startswith("erwarte "):
        body = line.removeprefix("erwarte ").strip()
        target = None
        if " in speicher " in body:
            name, target = body.split(" in speicher ", 1)
            name = name.strip()
            target = target.strip()
            _require_ident(target, loc)
        else:
            name = body
        _require_ident(name, loc)
        return AwaitTask(name=name, target_memory=target, loc=loc)
    if line.startswith("karte "):
        return _parse_map_action(line, loc)
    if line.startswith("json "):
        return _parse_json_action(line, loc)
    if line.startswith("server "):
        return _parse_http_server(line, loc)
    if line.startswith("zeit "):
        return _parse_time_action(line, loc)
    if line.startswith("krypto "):
        return _parse_crypto_action(line, loc)
    if line.startswith("prozess "):
        return _parse_process_action(line, loc)
    if line.startswith("neu "):
        return _parse_new_object(line, loc)
    if line.startswith("loesche objekt "):
        name = line.removeprefix("loesche objekt ").strip()
        _require_ident(name, loc)
        return DeleteObject(name=name, loc=loc)
    if line in {"sammle muell", "gc", "garbage collector"}:
        return CollectGarbage(loc=loc)
    if line.startswith("liste "):
        return _parse_list_action(line, loc)
    if line.startswith("tabelle ") and " sucht " in line:
        return _parse_table_query(line, loc)
    if line.startswith("datei "):
        return _parse_file_io(line, loc)
    if line.startswith("anfrage "):
        return _parse_web_request(line, loc)
    if line.startswith("pfad "):
        return _parse_pathfind(line, loc)
    if line.startswith("bild "):
        return _parse_image_export(line, loc)
    if line.startswith("dashboard "):
        return _parse_dashboard(line, loc)
    if line.startswith("erzeuge objekt "):
        body = line.removeprefix("erzeuge objekt ").strip()
        if " ist " not in body:
            _fail("Dynamisches Objekt erwartet: erzeuge objekt NAME ist KLASSE [mit eigenschaft=wert ...]", loc)
        name, rest = body.split(" ist ", 1)
        name = name.strip()
        _require_ident(name, loc)
        if " mit " in rest:
            class_name, override_text = rest.split(" mit ", 1)
            overrides = _parse_overrides(override_text, loc)
        else:
            class_name = rest.strip()
            overrides = ()
        _require_ident(class_name.strip(), loc)
        return SpawnObject(name=name, class_name=class_name.strip(), overrides=overrides, loc=loc)
    if line.startswith("tabelle ") and " fuegt " in line and line.endswith(" ein"):
        return _parse_table_insert(line, loc)
    if line.startswith("datenbank "):
        return _parse_database_save(line, loc)
    if line.startswith("objekt "):
        return _parse_object_action(line, loc)
    if line.startswith("rufe ") and "." in line:
        target = line.removeprefix("rufe ").strip()
        obj, method = target.split(".", 1)
        _require_ident(obj, loc)
        _require_ident(method, loc)
        return ObjectCall(object_name=obj, method=method, loc=loc)
    if line.startswith("feld ") and " wird " in line:
        left, expression = line.split(" wird ", 1)
        parts = left.split()
        if len(parts) == 2:
            field = parts[1]
            compile_agent_expression(expression, line=loc.line, text=loc.text, function_arities=function_arities)
            return FieldCompute(field=field, expression=expression.strip(), loc=loc)

    match words:
        case ["rufe", name] | ["regel", name, "ausfuehren"] | ["regel", name, "aufrufen"]:
            _require_ident(name, loc)
            return CallRule(name=name, loc=loc)
        case ["agent", kind, field, amount] if kind in {"verliert", "bekommt"}:
            return AgentFieldChange(field=field, kind=kind, amount=_number(amount, loc), loc=loc)
        case [field, kind, amount] if kind in {"sinkt", "waechst"}:
            return AgentFieldChange(field=field, kind=kind, amount=_number(amount, loc), loc=loc)
        case ["speicher", memory, kind, amount] if kind in {"setzt", "sinkt", "waechst", "verliert", "bekommt"}:
            return MemoryChange(memory=memory, kind=kind, amount=_auto_literal(amount, loc), loc=loc)
        case ["speicher", memory, verb, aggregate, source_kind, source] if verb in {"liest", "misst"} and aggregate in _AGGREGATES and source_kind in _SOURCES:
            return MemoryAggregate(memory=memory, aggregate=aggregate, source_kind=source_kind, source=source, loc=loc)
        case ["agent", "folgt", "spur", trail]:
            return AgentFollowTrail(trail=trail, loc=loc)
        case ["agent", "meidet", "spur", trail]:
            return AgentAvoidTrail(trail=trail, loc=loc)
        case ["erzeuge", count, "agenten"] | ["agenten", "erzeugen", count]:
            return SpawnAgents(count=_positive_int(count, loc), loc=loc)
        case ["erzeuge", "agent"]:
            return SpawnAgents(count=1, loc=loc)
        case ["loesche", count, "agenten"] | ["agenten", "loeschen", count]:
            return KillAgents(count=_positive_int(count, loc), loc=loc)
        case ["loesche", "agent"]:
            return KillAgents(count=1, loc=loc)
        case ["loesche", "aktive", "agenten"]:
            return KillAgents(count=None, loc=loc)
        case ["agent", "wandert", chance]:
            return AgentWander(chance=_number(chance, loc), loc=loc)
        case ["agent", "ruht"]:
            return AgentRest(loc=loc)
        case ["feld", field, "folgt", "spur", trail, "mit", amount]:
            return FieldTrailCoupling(field=field, trail=trail, kind="folgt", amount=_number(amount, loc), loc=loc)
        case ["feld", field, "meidet", "spur", trail, "mit", amount]:
            return FieldTrailCoupling(field=field, trail=trail, kind="meidet", amount=_number(amount, loc), loc=loc)
        case ["feld", field, "koppelt", "an", "spur", trail, "mit", amount]:
            return FieldTrailCoupling(field=field, trail=trail, kind="folgt", amount=_number(amount, loc), loc=loc)
        case ["feld", field, "schreibt", "spur", trail, "mit", amount] | ["feld", field, "sendet", "spur", trail, "mit", amount] | ["feld", field, "zeichnet", "spur", trail, "mit", amount]:
            return FieldTrailEmission(field=field, trail=trail, amount=_number(amount, loc), loc=loc)
        case ["spur", trail, "breitet", "sich", "aus"]:
            return TrailDiffuse(trail=trail, loc=loc)
        case ["spur", trail, "wird", "staerker", amount]:
            return TrailStrengthen(trail=trail, amount=_number(amount, loc), loc=loc)
        case ["zeige", target]:
            return ShowWorld(target=target, loc=loc)
        case _:
            _fail("Keim versteht diese Aktion noch nicht.", loc)



def _parse_ffi_call(line: str, loc: SourceLocation) -> FfiCall:
    # ffi LIB ruft "funktion" mit 1 2 "text" in speicher ziel als ganzzahl
    m = re.match(r'^ffi\s+([A-Za-z_][A-Za-z0-9_]*)\s+ruft\s+(.+?)(?:\s+mit\s+(.*?))?(?:\s+in\s+speicher\s+([A-Za-z_][A-Za-z0-9_]*))?(?:\s+als\s+(zahl|ganzzahl|bool|text|referenz))?$', line)
    if not m:
        _fail('FFI erwartet: ffi LIB ruft "FUNKTION" [mit ARG ...] [in speicher ZIEL] [als TYP]', loc)
    lib = m.group(1)
    fn = str(_auto_literal(m.group(2).strip(), loc))
    args_text = m.group(3)
    args: list[object] = []
    if args_text:
        # einfache, bewusst primitive Tokenisierung; Textargumente mit Leerzeichen können über Speicher/JSON modelliert werden.
        for token in args_text.split():
            if token == "in":
                break
            args.append(_auto_literal(token, loc))
    target = m.group(4)
    kind = m.group(5) or "ganzzahl"
    return FfiCall(library=lib, function=fn, args=tuple(args), target_memory=target, result_kind=kind, loc=loc)



def _parse_class_block(raw_lines: list[str], start: int, *, function_arities: dict[str, int]) -> tuple[ClassDecl, int]:
    raw = raw_lines[start]
    loc = _loc(start + 1, raw)
    line = _strip_comment(raw).strip()
    if not line.endswith(":"):
        _fail("Klassen werden als Block geschrieben: klasse NAME: oder klasse KIND ist BASIS:", loc)
    header = line.removeprefix("klasse ").removesuffix(":").strip()
    parent: str | None = None
    if " ist " in header:
        name, parent = [part.strip() for part in header.split(" ist ", 1)]
        _require_ident(parent, loc)
    else:
        name = header
    _require_ident(name, loc)

    properties: list[ObjectPropertyDecl] = []
    methods: list[MethodDecl] = []
    i = start + 1
    while i < len(raw_lines):
        cleaned = _strip_comment(raw_lines[i])
        if not cleaned.strip():
            i += 1
            continue
        indent = _indent_of(cleaned)
        if indent < 4:
            break
        child_loc = _loc(i + 1, raw_lines[i])
        if indent != 4:
            _fail("Klasseninhalt muss mit vier Leerzeichen eingerückt sein.", child_loc)
        child = cleaned.strip()

        if child.startswith("eigenschaft "):
            body = child.removeprefix("eigenschaft ").strip()
            if "=" not in body:
                _fail("Eigenschaften werden geschrieben als: eigenschaft NAME = WERT", child_loc)
            left, value = [part.strip() for part in body.split("=", 1)]
            parts = left.split()
            if len(parts) == 1:
                prop_name, kind = parts[0], "zahl"
            elif len(parts) == 2 and parts[1] in {"zahl", "ganzzahl", "bool", "text", "array", "karte", "referenz"}:
                prop_name, kind = parts
            else:
                _fail("Eigenschaften werden geschrieben als: eigenschaft NAME [typ] = WERT", child_loc)
            _require_ident(prop_name, child_loc)
            if any(p.name == prop_name for p in properties):
                _fail(f"Eigenschaft {prop_name!r} wurde in Klasse {name!r} mehrfach deklariert.", child_loc)
            properties.append(ObjectPropertyDecl(name=prop_name, initial=_typed_literal(value, kind, child_loc), kind=kind, loc=child_loc))
            i += 1
            continue

        if child.startswith("methode "):
            if not child.endswith(":"):
                _fail("Methoden werden als Block geschrieben: methode NAME:", child_loc)
            method_name = child.removeprefix("methode ").removesuffix(":").strip()
            _require_ident(method_name, child_loc)
            steps, next_i = _parse_steps(raw_lines, i + 1, base_indent=8, function_arities=function_arities)
            if not steps:
                _fail("Methodenblock ist leer.", child_loc)
            if any(m.name == method_name for m in methods):
                _fail(f"Methode {method_name!r} wurde in Klasse {name!r} mehrfach deklariert.", child_loc)
            methods.append(MethodDecl(name=method_name, steps=tuple(steps), loc=child_loc))
            i = next_i
            continue

        _fail("Klassen erlauben aktuell nur 'eigenschaft' und 'methode'.", child_loc)

    if not methods:
        _fail("Klasse braucht mindestens eine Methode.", loc)
    return ClassDecl(name=name, properties=tuple(properties), methods=tuple(methods), parent=parent, loc=loc), i


def _parse_table_index_decl(line: str, loc: SourceLocation) -> TableIndexDecl:
    # index messungen auf risiko  /  index risiko in messungen
    words = line.split()
    match words:
        case ["index", table, "auf", column]:
            _require_ident(table, loc); _require_ident(column, loc)
            return TableIndexDecl(table=table, column=column, loc=loc)
        case ["index", column, "in", table]:
            _require_ident(table, loc); _require_ident(column, loc)
            return TableIndexDecl(table=table, column=column, loc=loc)
        case _:
            _fail("Index erwartet: index TABELLE auf SPALTE", loc)




def _parse_time_action(line: str, loc: SourceLocation) -> TimeNow:
    # zeit jetzt in speicher NAME
    words = line.split()
    if len(words) == 5 and words[:4] == ["zeit", "jetzt", "in", "speicher"]:
        _require_ident(words[4], loc)
        return TimeNow(target_memory=words[4], loc=loc)
    _fail("Zeit-Aktion erwartet: zeit jetzt in speicher NAME", loc)


def _parse_crypto_action(line: str, loc: SourceLocation) -> CryptoHash:
    # krypto sha256 speicher quelle in speicher ziel
    words = line.split()
    if len(words) == 7 and words[0] == "krypto" and words[2] == "speicher" and words[4:6] == ["in", "speicher"]:
        algo = words[1].lower()
        if algo not in {"sha256", "sha1", "md5"}:
            _fail("Krypto unterstützt sha256, sha1 und md5.", loc)
        _require_ident(words[3], loc); _require_ident(words[6], loc)
        return CryptoHash(algorithm=algo, source_memory=words[3], target_memory=words[6], loc=loc)
    _fail("Krypto-Aktion erwartet: krypto sha256 speicher QUELLE in speicher ZIEL", loc)


def _parse_process_action(line: str, loc: SourceLocation) -> ProcessRun:
    # prozess fuehrt "echo hi" in speicher ausgabe
    if " in speicher " not in line:
        _fail("Prozess-Aktion erwartet: prozess fuehrt BEFEHL in speicher NAME", loc)
    left, target = line.rsplit(" in speicher ", 1)
    words = left.split(maxsplit=2)
    if len(words) != 3 or words[:2] != ["prozess", "fuehrt"]:
        _fail("Prozess-Aktion erwartet: prozess fuehrt BEFEHL in speicher NAME", loc)
    target = target.strip()
    _require_ident(target, loc)
    command = words[2].strip().strip('"').strip("'")
    if not command:
        _fail("Prozess-Befehl darf nicht leer sein.", loc)
    return ProcessRun(command=command, target_memory=target, loc=loc)


def _parse_catch_header(line: str, loc: SourceLocation) -> str:
    # fange fehler in speicher NAME:
    if not line.endswith(":"):
        _fail("Fange-Block erwartet: fange fehler in speicher NAME:", loc)
    words = line.removesuffix(":").split()
    if len(words) != 5 or words[:4] != ["fange", "fehler", "in", "speicher"]:
        _fail("Fange-Block erwartet: fange fehler in speicher NAME:", loc)
    _require_ident(words[4], loc)
    return words[4]


def _parse_map_action(line: str, loc: SourceLocation) -> MapSet | MapGet | MapDelete | MapHas:
    # karte daten setzt "name" auf "Ada"
    # karte daten liest "name" in speicher ziel
    # karte daten loescht "name"
    words = line.split()
    if len(words) >= 6 and words[2] == "setzt" and "auf" in words:
        at = words.index("auf")
        memory = words[1]
        key = " ".join(words[3:at])
        value = " ".join(words[at + 1:])
        _require_ident(memory, loc)
        return MapSet(memory=memory, key=_auto_literal(key, loc), value=_auto_literal(value, loc), loc=loc)
    if len(words) >= 7 and words[2] in {"liest", "holt"} and words[-3:-1] == ["in", "speicher"]:
        memory = words[1]
        key = " ".join(words[3:-3])
        target = words[-1]
        _require_ident(memory, loc); _require_ident(target, loc)
        return MapGet(memory=memory, key=_auto_literal(key, loc), target_memory=target, loc=loc)
    if len(words) >= 7 and words[2] in {"enthaelt", "hat"} and words[-3:-1] == ["in", "speicher"]:
        memory = words[1]
        key = " ".join(words[3:-3])
        target = words[-1]
        _require_ident(memory, loc); _require_ident(target, loc)
        return MapHas(memory=memory, key=_auto_literal(key, loc), target_memory=target, loc=loc)
    if len(words) >= 4 and words[2] in {"loescht", "entfernt"}:
        memory = words[1]
        key = " ".join(words[3:])
        _require_ident(memory, loc)
        return MapDelete(memory=memory, key=_auto_literal(key, loc), loc=loc)
    _fail("Kartenaktion erwartet: karte NAME setzt KEY auf WERT / liest KEY in speicher ZIEL / enthaelt KEY in speicher BOOL / loescht KEY", loc)


def _parse_json_action(line: str, loc: SourceLocation) -> JsonParse | JsonStringify:
    # json liest speicher raw in speicher obj
    # json schreibt speicher obj in speicher raw
    words = line.split()
    if len(words) == 7 and words[1] in {"liest", "parst"} and words[2] == "speicher" and words[4:6] == ["in", "speicher"]:
        _require_ident(words[3], loc); _require_ident(words[6], loc)
        return JsonParse(source_memory=words[3], target_memory=words[6], loc=loc)
    if len(words) == 7 and words[1] in {"schreibt", "serialisiert"} and words[2] == "speicher" and words[4:6] == ["in", "speicher"]:
        _require_ident(words[3], loc); _require_ident(words[6], loc)
        return JsonStringify(source_memory=words[3], target_memory=words[6], loc=loc)
    _fail("JSON-Aktion erwartet: json liest|schreibt speicher QUELLE in speicher ZIEL", loc)


def _parse_http_server(line: str, loc: SourceLocation) -> HttpServerStart:
    # server startet bei 8080 antwortet speicher antwort
    words = line.split()
    if len(words) == 7 and words[:3] == ["server", "startet", "bei"] and words[4:6] == ["antwortet", "speicher"]:
        port = _positive_int(words[3], loc)
        _require_ident(words[6], loc)
        return HttpServerStart(port=port, response_memory=words[6], loc=loc)
    _fail("HTTP-Server erwartet: server startet bei PORT antwortet speicher NAME", loc)


def _parse_new_object(line: str, loc: SourceLocation) -> SpawnObject:
    body = line.removeprefix("neu ").strip()
    if " als " in body:
        class_name, rest = body.split(" als ", 1)
        name = rest.strip()
        overrides = ()
        if " mit " in name:
            name, override_text = name.split(" mit ", 1)
            overrides = _parse_overrides(override_text, loc)
        _require_ident(class_name.strip(), loc)
        _require_ident(name.strip(), loc)
        return SpawnObject(name=name.strip(), class_name=class_name.strip(), overrides=overrides, loc=loc)
    if body.startswith("objekt "):
        body = body.removeprefix("objekt ").strip()
    if " ist " not in body:
        _fail("Neu-Objekt erwartet: neu objekt NAME ist KLASSE oder neu KLASSE als NAME", loc)
    name, rest = body.split(" ist ", 1)
    overrides = ()
    if " mit " in rest:
        class_name, override_text = rest.split(" mit ", 1)
        overrides = _parse_overrides(override_text, loc)
    else:
        class_name = rest
    _require_ident(name.strip(), loc)
    _require_ident(class_name.strip(), loc)
    return SpawnObject(name=name.strip(), class_name=class_name.strip(), overrides=overrides, loc=loc)



def _parse_grafik_action(line: str, loc: SourceLocation) -> GrafikCommand:
    words = line.split()
    if len(words) >= 2 and words[1] == "fenster":
        # grafik fenster "haupt" 800 600 "Titel"
        if len(words) < 6:
            _fail('Grafikfenster erwartet: grafik fenster "NAME" BREITE HOEHE "TITEL"', loc)
        name = _auto_literal(words[2], loc)
        width = _positive_int(words[3], loc)
        height = _positive_int(words[4], loc)
        title = _auto_literal(" ".join(words[5:]), loc)
        return GrafikCommand(kind="fenster", args=(name, width, height, title), loc=loc)
    if len(words) >= 5 and words[1] == "farbe":
        return GrafikCommand(kind="farbe", args=(_int(words[2], loc), _int(words[3], loc), _int(words[4], loc)), loc=loc)
    if len(words) >= 6 and words[1] == "rechteck":
        return GrafikCommand(kind="rechteck", args=(_int(words[2], loc), _int(words[3], loc), _int(words[4], loc), _int(words[5], loc)), loc=loc)
    if len(words) >= 5 and words[1] == "kreis":
        return GrafikCommand(kind="kreis", args=(_int(words[2], loc), _int(words[3], loc), _int(words[4], loc)), loc=loc)
    if len(words) >= 5 and words[1] == "text":
        return GrafikCommand(kind="text", args=(_int(words[2], loc), _int(words[3], loc), _auto_literal(" ".join(words[4:]), loc)), loc=loc)
    if len(words) == 2 and words[1] == "anzeigen":
        return GrafikCommand(kind="anzeigen", args=(), loc=loc)
    _fail("Grafikaktion erwartet: grafik farbe|rechteck|kreis|text|anzeigen|fenster ...", loc)


def _parse_fenster_action(line: str, loc: SourceLocation) -> GrafikCommand:
    # fenster haupt erzeugen 800 600 titel "Keim Fenster" / fenster haupt schliessen
    words = line.split()
    if len(words) >= 5 and words[2] == "erzeugen":
        title = ""
        if "titel" in words:
            at = words.index("titel")
            width, height = _positive_int(words[3], loc), _positive_int(words[4], loc)
            title = _auto_literal(" ".join(words[at + 1:]), loc)
        else:
            width, height = _positive_int(words[3], loc), _positive_int(words[4], loc)
        return GrafikCommand(kind="fenster", args=(words[1], width, height, title), loc=loc)
    if len(words) == 3 and words[2] in {"schliessen", "schließen"}:
        return GrafikCommand(kind="fenster_schliessen", args=(words[1],), loc=loc)
    _fail("Fensteraktion erwartet: fenster NAME erzeugen B H titel \"Titel\" / fenster NAME schliessen", loc)


def _parse_audio_action(line: str, loc: SourceLocation) -> AudioCommand:
    words = line.split()
    if len(words) >= 5 and words[1] == "ton" and words[3] == "dauer":
        return AudioCommand(kind="ton", args=(_int(words[2], loc), _int(words[4], loc)), loc=loc)
    if len(words) >= 3 and words[1] == "signal":
        return AudioCommand(kind="signal", args=(_auto_literal(" ".join(words[2:]), loc),), loc=loc)
    if len(words) == 3 and words[1] == "stumm":
        return AudioCommand(kind="stumm", args=(_typed_literal(words[2], "bool", loc),), loc=loc)
    _fail("Audioaktion erwartet: audio ton 440 dauer 250 / audio signal \"ok\" / audio stumm wahr", loc)


def _parse_debug_action(line: str, loc: SourceLocation) -> DebugWatch | DebugSend:
    words = line.split()
    if len(words) == 4 and words[:3] == ["debug", "beobachtet", "speicher"]:
        _require_ident(words[3], loc)
        return DebugWatch(memory=words[3], loc=loc)
    if len(words) >= 3 and words[1] in {"sendet", "marke"}:
        return DebugSend(label=str(_auto_literal(" ".join(words[2:]), loc)), loc=loc)
    _fail('Debugaktion erwartet: debug beobachtet speicher NAME / debug sendet "label"', loc)

def _parse_list_action(line: str, loc: SourceLocation) -> ListAppend | ListPop:
    # liste werte haengt 3 an  /  liste werte nimmt letztes in speicher ziel
    words = line.split()
    if len(words) >= 5 and words[2] in {"haengt", "fügt", "fuegt"} and words[-1] in {"an", "hinzu"}:
        memory = words[1]
        value = " ".join(words[3:-1])
        _require_ident(memory, loc)
        return ListAppend(memory=memory, value=_auto_literal(value, loc), loc=loc)
    if len(words) in {4, 7} and words[2] in {"nimmt", "entfernt"} and words[3] in {"letztes", "letzte"}:
        target = None
        if len(words) == 7 and words[4:6] == ["in", "speicher"]:
            target = words[6]
            _require_ident(target, loc)
        _require_ident(words[1], loc)
        return ListPop(memory=words[1], target_memory=target, loc=loc)
    _fail("Listenaktion erwartet: liste NAME haengt WERT an", loc)


def _parse_table_query(line: str, loc: SourceLocation) -> TableQuery:
    # tabelle messungen sucht risiko > 0.5 in speicher treffer
    words = line.split()
    if len(words) < 9 or words[0] != "tabelle" or words[2] != "sucht" or words[-3:-1] != ["in", "speicher"]:
        _fail("Tabellensuche erwartet: tabelle T sucht SPALTE OP WERT in speicher MEM", loc)
    table, column, op, raw_value, target = words[1], words[3], words[4], words[5], words[-1]
    if op not in _COMPARE:
        _fail("Tabellensuche braucht Vergleichsoperator > >= < <= == !=", loc)
    _require_ident(table, loc); _require_ident(column, loc); _require_ident(target, loc)
    return TableQuery(table=table, column=column, op=op, value=_auto_literal(raw_value, loc), target_memory=target, loc=loc)


def _parse_file_io(line: str, loc: SourceLocation) -> FileTableIO:
    # datei schreibt json "out.json" aus tabelle messungen
    words = line.split()
    if len(words) >= 7 and words[1] in {"schreibt", "lies", "liest"} and words[2] in {"json", "csv"}:
        mode = "write" if words[1] == "schreibt" else "read"
        path = words[3].strip('"').strip("'")
        if words[4:6] not in (["aus", "tabelle"], ["in", "tabelle"]):
            _fail("Dateiaktion erwartet: datei schreibt json PFAD aus tabelle T / datei liest json PFAD in tabelle T", loc)
        return FileTableIO(mode=mode, fmt=words[2], path=path, table=words[6], loc=loc)  # type: ignore[arg-type]
    _fail("Dateiaktion erwartet: datei schreibt|liest json|csv PFAD aus|in tabelle NAME", loc)


def _parse_web_request(line: str, loc: SourceLocation) -> WebRequest:
    # anfrage GET "https://..." in speicher antwort
    words = line.split()
    if len(words) >= 6 and words[1].upper() == "GET" and words[-3:-1] == ["in", "speicher"]:
        url = words[2].strip('"').strip("'")
        target = words[-1]
        _require_ident(target, loc)
        return WebRequest(method="GET", url=url, target_memory=target, loc=loc)
    _fail("Anfrage erwartet: anfrage GET URL in speicher NAME", loc)


def _parse_pathfind(line: str, loc: SourceLocation) -> PathFind:
    # pfad von 0 0 nach 10 10 mit spur kosten in tabelle route
    words = line.split()
    if len(words) not in {10, 13} or words[:2] != ["pfad", "von"] or words[4] != "nach":
        _fail("Pfad erwartet: pfad von X Y nach X Y [mit spur S] in tabelle T", loc)
    sx, sy, gx, gy = (_int(words[2], loc), _int(words[3], loc), _int(words[5], loc), _int(words[6], loc))
    if len(words) == 10 and words[7:9] == ["in", "tabelle"]:
        return PathFind(sx, sy, gx, gy, None, words[9], loc)
    if len(words) == 13 and words[7:9] == ["mit", "spur"] and words[10:12] == ["in", "tabelle"]:
        return PathFind(sx, sy, gx, gy, words[9], words[12], loc)
    _fail("Pfad erwartet: pfad von X Y nach X Y [mit spur S] in tabelle T", loc)


def _parse_image_export(line: str, loc: SourceLocation) -> ExportImage:
    # bild schreibt png "frame.png" aus spur futter
    words = line.split()
    if len(words) == 7 and words[1] == "schreibt" and words[2] in {"bmp", "png"} and words[4] == "aus" and words[5] in {"spur", "feld"}:
        return ExportImage(fmt=words[2], path=words[3].strip('"').strip("'"), source_kind=words[5], source=words[6], loc=loc)  # type: ignore[arg-type]
    _fail("Bildexport erwartet: bild schreibt png|bmp PFAD aus spur|feld NAME", loc)


def _parse_dashboard(line: str, loc: SourceLocation) -> StartDashboard:
    words = line.split()
    if len(words) == 4 and words[:3] == ["dashboard", "startet", "bei"]:
        return StartDashboard(path=words[3].strip('"').strip("'"), loc=loc)
    _fail("Dashboard erwartet: dashboard startet bei PFAD", loc)



def _parse_table_decl(line: str, loc: SourceLocation) -> TableDecl:
    # tabelle messungen mit rund zahl, risiko zahl, status text
    body = line.removeprefix("tabelle ").strip()
    if " mit " not in body:
        _fail("Tabellen werden geschrieben als: tabelle NAME mit SPALTE typ, ...", loc)
    name, cols_text = body.split(" mit ", 1)
    name = name.strip()
    _require_ident(name, loc)
    columns: list[TableColumn] = []
    for raw_col in cols_text.split(","):
        parts = raw_col.strip().split()
        if len(parts) != 2 or parts[1] not in {"zahl", "ganzzahl", "bool", "text", "array", "karte", "referenz"}:
            _fail("Tabellenspalten brauchen die Form: NAME zahl|ganzzahl|bool|text|array", loc)
        col_name, kind = parts
        _require_ident(col_name, loc)
        if any(c.name == col_name for c in columns):
            _fail(f"Tabellenspalte {col_name!r} wurde mehrfach deklariert.", loc)
        columns.append(TableColumn(name=col_name, kind=kind))  # type: ignore[arg-type]
    if not columns:
        _fail("Tabelle braucht mindestens eine Spalte.", loc)
    return TableDecl(name=name, columns=tuple(columns), loc=loc)


def _parse_database_decl(line: str, loc: SourceLocation) -> DatabaseDecl:
    # datenbank messdb bei "messungen.sqlite"
    parts = line.split(maxsplit=3)
    if len(parts) != 4 or parts[0] != "datenbank" or parts[2] != "bei":
        _fail("Datenbanken werden geschrieben als: datenbank NAME bei PFAD", loc)
    name = parts[1]
    _require_ident(name, loc)
    path = parts[3].strip().strip('"').strip("'")
    if not path:
        _fail("Datenbankpfad darf nicht leer sein.", loc)
    return DatabaseDecl(name=name, path=path, loc=loc)


def _parse_object_decl(line: str, loc: SourceLocation) -> ObjectDecl:
    # objekt alarm ist waechter mit schwelle=0.25
    if " ist " not in line:
        _fail("Objekte werden geschrieben als: objekt NAME ist KLASSE [mit eigenschaft=wert ...]", loc)
    body = line.removeprefix("objekt ").strip()
    name, rest = body.split(" ist ", 1)
    name = name.strip()
    _require_ident(name, loc)
    if " mit " in rest:
        class_name, override_text = rest.split(" mit ", 1)
        overrides = _parse_overrides(override_text, loc)
    else:
        class_name = rest.strip()
        overrides = ()
    _require_ident(class_name.strip(), loc)
    return ObjectDecl(name=name, class_name=class_name.strip(), overrides=overrides, loc=loc)


def _parse_overrides(text: str, loc: SourceLocation) -> tuple[tuple[str, float], ...]:
    result: list[tuple[str, float]] = []
    for token in text.replace(",", " ").split():
        if "=" not in token:
            _fail("Objekt-Overrides brauchen die Form eigenschaft=wert.", loc)
        key, raw_value = token.split("=", 1)
        _require_ident(key, loc)
        result.append((key, _auto_literal(raw_value, loc)))
    if len({key for key, _ in result}) != len(result):
        _fail("Objekt-Overrides dürfen nicht doppelt vorkommen.", loc)
    return tuple(result)


def _parse_table_insert(line: str, loc: SourceLocation) -> TableInsert:
    # tabelle messungen fuegt rund=zeit risiko=speicher.risiko_max ein
    body = line.removeprefix("tabelle ").removesuffix(" ein").strip()
    if " fuegt " not in body:
        _fail("Tabelleninsert erwartet: tabelle NAME fuegt spalte=wert ... ein", loc)
    table, values_text = body.split(" fuegt ", 1)
    table = table.strip()
    _require_ident(table, loc)
    values: list[tuple[str, str]] = []
    for token in values_text.replace(",", " ").split():
        if "=" not in token:
            _fail("Tabellenwerte brauchen die Form spalte=wert.", loc)
        key, value = token.split("=", 1)
        _require_ident(key, loc)
        if not value:
            _fail("Tabellenwert darf nicht leer sein.", loc)
        values.append((key, value.strip()))
    if not values:
        _fail("Tabelleninsert braucht mindestens einen Wert.", loc)
    return TableInsert(table=table, values=tuple(values), loc=loc)


def _parse_database_save(line: str, loc: SourceLocation) -> DatabaseSave:
    words = line.split()
    match words:
        case ["datenbank", database, "speichert", "tabelle", table]:
            _require_ident(database, loc)
            _require_ident(table, loc)
            return DatabaseSave(database=database, table=table, loc=loc)
        case _:
            _fail("Datenbankaktion erwartet: datenbank DB speichert tabelle NAME", loc)


def _parse_object_action(line: str, loc: SourceLocation) -> ObjectCall:
    words = line.split()
    match words:
        case ["objekt", obj, "ruft", method] | ["objekt", obj, "ruft", method, "auf"]:
            _require_ident(obj, loc)
            _require_ident(method, loc)
            return ObjectCall(object_name=obj, method=method, loc=loc)
        case _:
            _fail("Objektaktion erwartet: objekt NAME ruft METHODE", loc)


def _condition_value(token: str, loc: SourceLocation):
    if token.startswith("selbst."):
        name = token.removeprefix("selbst.")
        _require_ident(name, loc)
        return SelfPropertyRef(name)
    return _auto_literal(token, loc)



def _typed_literal(raw: str, kind: str, loc: SourceLocation):
    try:
        return parse_literal(raw, parse_type(kind))
    except Exception as exc:
        _fail(str(exc), loc)


def _auto_literal(raw: str, loc: SourceLocation):
    text = raw.strip()
    low = text.lower()
    if low in {"wahr", "falsch", "true", "false", "ja", "nein", "an", "aus"}:
        return _typed_literal(text, "bool", loc)
    if text.startswith("[") and text.endswith("]"):
        return _typed_literal(text, "array", loc)
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        return _typed_literal(text, "text", loc)
    try:
        value = float(text.replace(",", "."))
        return int(value) if value.is_integer() and "." not in text and "," not in text else value
    except ValueError:
        return text

def _parse_params(text: str, loc: SourceLocation) -> tuple[str, ...]:
    if not text.strip():
        return ()
    params: list[str] = []
    for part in text.split(","):
        name = part.strip()
        if name.startswith("$"):
            name = name[1:]
        _require_ident(name, loc)
        params.append(name)
    if len(params) != len(set(params)):
        _fail("Funktionsparameter dürfen nicht doppelt vorkommen.", loc)
    return tuple(params)


def _strip_comment(line: str) -> str:
    return line.split("#", 1)[0].rstrip()


def _loc(line_no: int, text: str) -> SourceLocation:
    return SourceLocation(line=line_no, text=text.strip())


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _skip_blank(raw_lines: list[str], start: int) -> int:
    i = start
    while i < len(raw_lines) and not _strip_comment(raw_lines[i]).strip():
        i += 1
    return i


def _parse_repeat_count(body: str, loc: SourceLocation) -> int:
    parts = body.split()
    if len(parts) != 2 or parts[1] != "mal":
        _fail("Wiederholung erwartet: wiederhole N mal:", loc)
    value = _positive_int(parts[0], loc)
    if value > 1024:
        _fail("Wiederholungszahl darf im AST höchstens 1024 sein.", loc)
    return value


def _require_ident(name: str, loc: SourceLocation) -> None:
    if not name or not (name[0].isalpha() or name[0] == "_") or any(not (ch.isalnum() or ch == "_") for ch in name):
        _fail(f"Ungültiger Name {name!r}.", loc)


def _number(token: str, loc: SourceLocation) -> float:
    try:
        return float(token.replace(",", "."))
    except ValueError as exc:
        raise KeimSyntaxError(f"Erwartet wurde eine Zahl, nicht {token!r}.", loc.line, loc.text) from exc


def _int(token: str, loc: SourceLocation) -> int:
    try:
        value = int(token)
    except ValueError as exc:
        raise KeimSyntaxError(f"Erwartet wurde eine ganze Zahl, nicht {token!r}.", loc.line, loc.text) from exc
    if value < 0:
        raise KeimSyntaxError("Die Zahl darf nicht negativ sein.", loc.line, loc.text)
    return value


def _positive_int(token: str, loc: SourceLocation) -> int:
    value = _int(token, loc)
    if value <= 0:
        raise KeimSyntaxError("Die Zahl muss positiv sein.", loc.line, loc.text)
    return value


def _fail(message: str, loc: SourceLocation) -> NoReturn:
    raise KeimSyntaxError(message, loc.line, loc.text)
