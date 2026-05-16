from __future__ import annotations

import ast
from dataclasses import dataclass
import operator
import re

from .errors import KeimSyntaxError


_MACRO_RE = re.compile(r"^(?P<indent>\s*)baustein\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?:\((?P<params>[^)]*)\))?\s*:\s*$")
_USE_RE = re.compile(r"^(?P<indent>\s*)nutze\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?:\((?P<args>[^)]*)\))?\s*$")
_VALUE_RE = re.compile(r"^\s*wert\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*(?:=|ist)\s*(?P<expr>.+?)\s*$")
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_CONST_REF_RE = re.compile(r"\$\{(?P<braced>[A-Za-z_][A-Za-z0-9_]*)\}|\$(?P<plain>[A-Za-z_][A-Za-z0-9_]*)")


@dataclass(slots=True, frozen=True)
class MacroDef:
    name: str
    params: tuple[str, ...]
    body: tuple[str, ...]
    line: int


@dataclass(slots=True, frozen=True)
class ValueDef:
    name: str
    expression: str
    value: float
    line: int


@dataclass(slots=True, frozen=True)
class MacroExpansion:
    source: str
    macros: tuple[str, ...]
    expansion_count: int
    parameterized_macros: tuple[str, ...]
    values: dict[str, float]
    value_expressions: dict[str, str]
    contracts: tuple[str, ...] = ()
    control_expansions: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "macros": list(self.macros),
            "parameterized_macros": list(self.parameterized_macros),
            "values": self.values,
            "value_expressions": self.value_expressions,
            "expansion_count": self.expansion_count,
            "contracts": list(self.contracts),
            "control_expansions": self.control_expansions,
        }


def expand_macros(source: str, *, max_passes: int = 16, expand_control: bool = True) -> MacroExpansion:
    """Expandiert sichere Keim-Sprachschichten.

    v1.0: parametrisierte Bausteine.
    v1.3: Werte und sichere arithmetische Ausdrücke.

        wert basis_hunger = 0.20
        wert hunger_grenze = basis_hunger + 0.30

        feld hunger startet bei $basis_hunger
        wenn hunger > $hunger_grenze: agent folgt spur futter

    Es gibt weiterhin kein eval, keine Python-Ausführung und keine Imports in
    dieser Phase. Imports werden vorher durch source_loader aufgelöst.
    """

    lines = source.splitlines()
    values, non_value_lines = _collect_values(lines)
    macros, kept = _collect_macros(non_value_lines)

    expanded = kept
    expansion_count = 0
    for _ in range(max_passes):
        changed = False
        next_lines: list[str] = []
        for raw in expanded:
            match = _USE_RE.match(_strip_comment(raw))
            if not match:
                next_lines.append(raw)
                continue

            name = match.group("name")
            macro = macros.get(name)
            if macro is None:
                raise KeimSyntaxError(f"Unbekannter Baustein {name!r}.", 0, raw.strip())

            args = _parse_args(match.group("args") or "", 0, raw)
            if len(args) != len(macro.params):
                raise KeimSyntaxError(
                    f"Baustein {name!r} erwartet {len(macro.params)} Parameter, erhalten {len(args)}.",
                    0,
                    raw.strip(),
                )

            mapping = dict(zip(macro.params, args))
            indent = match.group("indent")
            for body_line in macro.body:
                replaced = _substitute_macro_params(body_line, mapping)
                next_lines.append(indent + replaced if replaced.strip() else replaced)
            expansion_count += 1
            changed = True

        expanded = next_lines
        if not changed:
            break
    else:
        raise KeimSyntaxError("Baustein-Expansion wurde abgebrochen: mögliche Rekursion.", 0, "")

    expanded = [_substitute_values(line, values) for line in expanded]
    if expand_control:
        expanded, control_count = _expand_control_blocks(expanded)
    else:
        control_count = 0
    expanded, contracts = _strip_contract_lines(expanded)

    param_names = tuple(sorted(name for name, macro in macros.items() if macro.params))
    text = "\n".join(expanded)
    if source.endswith("\n"):
        text += "\n"
    return MacroExpansion(
        source=text,
        macros=tuple(sorted(macros)),
        parameterized_macros=param_names,
        values={name: value.value for name, value in values.items()},
        value_expressions={name: value.expression for name, value in values.items()},
        expansion_count=expansion_count,
        contracts=tuple(contracts),
        control_expansions=control_count,
    )



_CONTROL_HEAD_RE = re.compile(r"^(?P<indent>\s*)(?P<kind>wenn|wiederhole)\s+(?P<body>.+?)\s*:\s*$")
_ELSE_RE = re.compile(r"^(?P<indent>\s*)sonst\s*:\s*$")
_CONTRACT_RE = re.compile(r"^\s*erwarte\s+.+")


def _expand_control_blocks(lines: list[str]) -> tuple[list[str], int]:
    """v1.6: Block-Kontrollfluss als sichere Desugaring-Schicht.

    Unterstützt:
        wenn hunger > 0.5:
            agent folgt spur futter
            agent verliert energie 0.001

        sonst:
            ...

        wiederhole 3 mal:
            agent wandert 0.02

    Der Kernparser bleibt klein; diese Schicht erzeugt alte Einzeilen-Regeln.
    """
    expanded, count, index = _expand_control_range(lines, 0, base_indent=0)
    if index < len(lines):
        expanded.extend(lines[index:])
    return expanded, count


def _expand_control_range(lines: list[str], start: int, base_indent: int) -> tuple[list[str], int, int]:
    out: list[str] = []
    count = 0
    i = start
    while i < len(lines):
        raw = lines[i]
        if raw.strip() and _indent_of(raw) < base_indent:
            break
        head = _CONTROL_HEAD_RE.match(_strip_comment(raw))
        if not head:
            out.append(raw)
            i += 1
            continue

        indent = len(head.group("indent"))
        if indent < base_indent:
            break
        kind = head.group("kind")
        body = head.group("body").strip()

        child_start = i + 1
        child_end = _find_child_end(lines, child_start, indent)
        if child_start >= child_end:
            raise KeimSyntaxError(f"{kind!r}-Block ist leer.", i + 1, raw.strip())
        child_lines = [_dedent_to(lines[j], indent + 4) for j in range(child_start, child_end)]
        child_expanded, child_count, _ = _expand_control_range(child_lines, 0, base_indent=0)
        count += child_count

        if kind == "wiederhole":
            n = _parse_repeat_count(body, i + 1, raw)
            for _ in range(n):
                out.extend((" " * indent) + line if line.strip() else line for line in child_expanded)
            count += max(0, n * len([line for line in child_expanded if line.strip()]))
            i = child_end
            continue

        # kind == "wenn"
        condition = body
        for line in child_expanded:
            if line.strip():
                out.append((" " * indent) + f"wenn {condition}: {line.strip()}")
            else:
                out.append(line)
        count += len([line for line in child_expanded if line.strip()])

        # Optionales sonst direkt nach dem wenn-Block.
        if child_end < len(lines):
            else_match = _ELSE_RE.match(_strip_comment(lines[child_end]))
            if else_match and len(else_match.group("indent")) == indent:
                else_start = child_end + 1
                else_end = _find_child_end(lines, else_start, indent)
                else_lines = [_dedent_to(lines[j], indent + 4) for j in range(else_start, else_end)]
                else_expanded, else_count, _ = _expand_control_range(else_lines, 0, base_indent=0)
                count += else_count
                complement = _complement_condition(condition, child_end + 1, lines[child_end])
                for line in else_expanded:
                    if line.strip():
                        out.append((" " * indent) + f"wenn {complement}: {line.strip()}")
                    else:
                        out.append(line)
                count += len([line for line in else_expanded if line.strip()])
                i = else_end
            else:
                i = child_end
        else:
            i = child_end
    return out, count, i


def _find_child_end(lines: list[str], start: int, parent_indent: int) -> int:
    i = start
    while i < len(lines):
        raw = lines[i]
        if raw.strip() and _indent_of(raw) <= parent_indent:
            break
        i += 1
    return i


def _dedent_to(line: str, amount: int) -> str:
    if not line.strip():
        return line
    return line[amount:] if len(line) >= amount and line[:amount].isspace() else line.lstrip()


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _parse_repeat_count(body: str, line_no: int, raw: str) -> int:
    parts = body.split()
    if len(parts) != 2 or parts[1] != "mal":
        raise KeimSyntaxError("Wiederholung erwartet: wiederhole N mal:", line_no, raw.strip())
    try:
        value = int(parts[0])
    except ValueError as exc:
        raise KeimSyntaxError("Wiederholungszahl muss ganzzahlig sein.", line_no, raw.strip()) from exc
    if not (1 <= value <= 64):
        raise KeimSyntaxError("Wiederholungszahl muss zwischen 1 und 64 liegen.", line_no, raw.strip())
    return value


def _complement_condition(condition: str, line_no: int, raw: str) -> str:
    words = condition.split()
    if words[:3] == ["agent", "riecht", "spur"] and len(words) == 6:
        prefix = " ".join(words[:4])
        op = words[4]
        value = words[5]
        return f"{prefix} {_invert_op(op, line_no, raw)} {value}"
    if words[:2] == ["speicher"] and len(words) == 4:
        prefix = " ".join(words[:2])
        op = words[2]
        value = words[3]
        return f"{prefix} {_invert_op(op, line_no, raw)} {value}"
    if len(words) == 3 and words[1] in {">", ">=", "<", "<=", "==", "!="}:
        field, op, value = words
        return f"{field} {_invert_op(op, line_no, raw)} {value}"
    # v2.0: beliebige Bool-Algebra wird nicht algebraisch vereinfacht,
    # sondern als explizite Negation an den Kernparser weitergereicht.
    return f"nicht ({condition})"


def _invert_op(op: str, line_no: int, raw: str) -> str:
    mapping = {">": "<=", ">=": "<", "<": ">=", "<=": ">", "==": "!=", "!=": "=="}
    if op not in mapping:
        raise KeimSyntaxError("sonst unterstützt diesen Vergleichsoperator nicht.", line_no, raw.strip())
    return mapping[op]


def _strip_contract_lines(lines: list[str]) -> tuple[list[str], list[str]]:
    kept: list[str] = []
    contracts: list[str] = []
    for raw in lines:
        stripped = _strip_comment(raw).strip()
        # v4.4: "erwarte TASK [in speicher X]" ist Async/Await-Syntax.
        # Vertragszeilen bleiben erwarte-Ausdrücke mit Vergleichsoperatoren oder Metrikbezug.
        if _CONTRACT_RE.match(stripped) and " in speicher " not in stripped and not stripped.startswith("erwarte ") == False:
            contracts.append(stripped)
        else:
            kept.append(raw)
    return kept, contracts


def _collect_values(lines: list[str]) -> tuple[dict[str, ValueDef], list[str]]:
    values: dict[str, ValueDef] = {}
    kept: list[str] = []
    pending: list[tuple[str, str, int, str]] = []

    for line_no, raw in enumerate(lines, start=1):
        stripped = _strip_comment(raw)
        m = _VALUE_RE.match(stripped)
        if not m:
            kept.append(raw)
            continue
        name = m.group("name")
        if name in values or any(item[0] == name for item in pending):
            raise KeimSyntaxError(f"Wert {name!r} wurde mehrfach definiert.", line_no, raw.strip())
        pending.append((name, m.group("expr").strip(), line_no, raw))

    unresolved = pending[:]
    while unresolved:
        progress = False
        next_unresolved: list[tuple[str, str, int, str]] = []
        known = {name: value.value for name, value in values.items()}
        for name, expr, line_no, raw in unresolved:
            try:
                value = _eval_expr(expr, known, line_no, raw)
            except _UnknownName:
                next_unresolved.append((name, expr, line_no, raw))
                continue
            values[name] = ValueDef(name=name, expression=expr, value=value, line=line_no)
            progress = True
        if not progress:
            missing = ", ".join(item[0] for item in next_unresolved)
            raise KeimSyntaxError(f"Werte konnten nicht aufgelöst werden: {missing}.", next_unresolved[0][2], next_unresolved[0][3].strip())
        unresolved = next_unresolved

    return values, kept


def _collect_macros(lines: list[str]) -> tuple[dict[str, MacroDef], list[str]]:
    macros: dict[str, MacroDef] = {}
    kept: list[str] = []
    i = 0

    while i < len(lines):
        raw = lines[i]
        stripped_for_macro = _strip_comment(raw)
        match = _MACRO_RE.match(stripped_for_macro)
        if not match:
            kept.append(raw)
            i += 1
            continue

        name = match.group("name")
        if name in macros:
            raise KeimSyntaxError(f"Baustein {name!r} wurde mehrfach definiert.", i + 1, raw.strip())
        params = _parse_params(match.group("params") or "", i + 1, raw)
        base_indent = len(match.group("indent"))
        body: list[str] = []
        start_line = i + 1
        i += 1

        while i < len(lines):
            body_raw = lines[i]
            if not body_raw.strip():
                body.append("")
                i += 1
                continue
            indent = len(body_raw) - len(body_raw.lstrip(" "))
            if indent <= base_indent:
                break
            cut = base_indent + 4
            body.append(body_raw[cut:] if len(body_raw) >= cut and body_raw[:cut].isspace() else body_raw.lstrip())
            i += 1

        if not any(part.strip() for part in body):
            raise KeimSyntaxError(f"Baustein {name!r} ist leer.", start_line, raw.strip())
        macros[name] = MacroDef(name=name, params=params, body=tuple(body), line=start_line)

    return macros, kept


def _substitute_macro_params(line: str, mapping: dict[str, str]) -> str:
    for name, value in sorted(mapping.items(), key=lambda item: -len(item[0])):
        line = line.replace("$" + name, value)
    return line


def _substitute_values(line: str, values: dict[str, ValueDef]) -> str:
    def repl(match: re.Match[str]) -> str:
        name = match.group("braced") or match.group("plain")
        value = values.get(name)
        if value is None:
            raise KeimSyntaxError(f"Unbekannter Wert {name!r}.", 0, line.strip())
        return _format_number(value.value)

    return _CONST_REF_RE.sub(repl, line)


def _parse_params(text: str, line: int, raw: str) -> tuple[str, ...]:
    if not text.strip():
        return ()
    result = []
    for part in text.split(","):
        name = part.strip()
        if name.startswith("$"):
            name = name[1:]
        if not _IDENT_RE.match(name):
            raise KeimSyntaxError(f"Ungültiger Bausteinparameter {part!r}.", line, raw.strip())
        result.append(name)
    if len(set(result)) != len(result):
        raise KeimSyntaxError("Bausteinparameter dürfen nicht doppelt vorkommen.", line, raw.strip())
    return tuple(result)


def _parse_args(text: str, line: int, raw: str) -> tuple[str, ...]:
    if not text.strip():
        return ()
    return tuple(part.strip() for part in text.split(","))


def _strip_comment(line: str) -> str:
    return line.split("#", 1)[0].rstrip()


class _UnknownName(Exception):
    pass


_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}
_ALLOWED_UNARY = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _eval_expr(expr: str, names: dict[str, float], line_no: int, raw: str) -> float:
    expr = _replace_dollar_refs_for_expr(expr)
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise KeimSyntaxError(f"Ungültiger Wertausdruck {expr!r}.", line_no, raw.strip()) from exc

    def visit(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.Name):
            if node.id not in names:
                raise _UnknownName(node.id)
            return float(names[node.id])
        if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
            left = visit(node.left)
            right = visit(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 8:
                raise KeimSyntaxError("Potenz zu groß für Keim-Wertausdruck.", line_no, raw.strip())
            return float(_ALLOWED_BINOPS[type(node.op)](left, right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARY:
            return float(_ALLOWED_UNARY[type(node.op)](visit(node.operand)))
        raise KeimSyntaxError("Wertausdrücke erlauben nur Zahlen, Namen und + - * / ** ().", line_no, raw.strip())

    value = visit(tree)
    if not (-1_000_000 <= value <= 1_000_000):
        raise KeimSyntaxError("Wertausdruck liegt außerhalb des erlaubten Bereichs.", line_no, raw.strip())
    return value


def _replace_dollar_refs_for_expr(expr: str) -> str:
    return _CONST_REF_RE.sub(lambda m: m.group("braced") or m.group("plain"), expr)


def _format_number(value: float) -> str:
    if abs(value - round(value)) < 1e-12:
        return str(int(round(value)))
    return f"{value:.12g}".replace(",", ".")
