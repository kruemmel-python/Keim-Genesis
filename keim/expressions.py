from __future__ import annotations

import ast
from dataclasses import dataclass
import re
from typing import Callable, Mapping

from .errors import KeimSyntaxError


_TRAIL_REF_RE = re.compile(r"\bspur\s+([A-Za-z_][A-Za-z0-9_]*)\b")
_MEMORY_REF_RE = re.compile(r"\bspeicher\s+([A-Za-z_][A-Za-z0-9_]*)\b")
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(slots=True, frozen=True)
class ExpressionRefs:
    fields: tuple[str, ...] = ()
    trails: tuple[str, ...] = ()
    memory: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, list[str]]:
        return {"fields": list(self.fields), "trails": list(self.trails), "memory": list(self.memory)}


@dataclass(slots=True, frozen=True)
class CompiledAgentExpression:
    source: str
    normalized: str
    tree: ast.Expression
    refs: ExpressionRefs
    called_functions: tuple[str, ...] = ()

    def eval(
        self,
        resolve: Callable[[str], float],
        functions: Mapping[str, "CompiledUserFunction"] | None = None,
        local_values: Mapping[str, float] | None = None,
        *,
        _depth: int = 0,
    ) -> float:
        if _depth > 32:
            raise RuntimeError("Ausdrucksfunktionen sind zu tief verschachtelt oder rekursiv.")
        return _eval_node(self.tree.body, resolve, functions or {}, local_values or {}, _depth)


@dataclass(slots=True, frozen=True)
class CompiledUserFunction:
    name: str
    params: tuple[str, ...]
    expression: CompiledAgentExpression

    def call(
        self,
        values: list[float],
        resolve: Callable[[str], float],
        functions: Mapping[str, "CompiledUserFunction"],
        *,
        _depth: int,
    ) -> float:
        if len(values) != len(self.params):
            raise RuntimeError(f"Funktion {self.name!r} erwartet {len(self.params)} Argumente.")
        local = dict(zip(self.params, values))
        return self.expression.eval(resolve, functions, local, _depth=_depth + 1)


def builtin_function_names() -> tuple[str, ...]:
    return tuple(sorted(_ALLOWED_CALL_ARITY))


def compile_user_function(
    name: str,
    params: tuple[str, ...],
    source: str,
    *,
    function_arities: Mapping[str, int] | None = None,
    line: int = 0,
    text: str = "",
) -> CompiledUserFunction:
    if name in _ALLOWED_CALL_ARITY:
        raise KeimSyntaxError(f"Funktion {name!r} überschreibt eine eingebaute Ausdrucksfunktion.", line, text or source)
    if len(set(params)) != len(params):
        raise KeimSyntaxError(f"Funktion {name!r} hat doppelte Parameter.", line, text or source)
    for param in params:
        if not _IDENT_RE.match(param):
            raise KeimSyntaxError(f"Ungültiger Funktionsparameter {param!r}.", line, text or source)
    expr = compile_agent_expression(
        source,
        line=line,
        text=text or source,
        function_arities=function_arities,
        parameters=params,
    )
    return CompiledUserFunction(name=name, params=params, expression=expr)


def compile_agent_expression(
    source: str,
    *,
    line: int = 0,
    text: str = "",
    function_arities: Mapping[str, int] | None = None,
    parameters: tuple[str, ...] | set[str] = (),
) -> CompiledAgentExpression:
    normalized = _normalize_refs(source)
    try:
        tree = ast.parse(normalized, mode="eval")
    except SyntaxError as exc:
        raise KeimSyntaxError(f"Ungültiger Agentenausdruck {source!r}.", line, text or source) from exc
    refs, calls = _validate_and_collect(tree, source, line, text or source, function_arities or {}, set(parameters))
    return CompiledAgentExpression(source=source, normalized=normalized, tree=tree, refs=refs, called_functions=calls)


def expression_references(
    source: str,
    *,
    line: int = 0,
    text: str = "",
    function_arities: Mapping[str, int] | None = None,
    parameters: tuple[str, ...] | set[str] = (),
) -> ExpressionRefs:
    return compile_agent_expression(source, line=line, text=text, function_arities=function_arities, parameters=parameters).refs


def expression_function_calls(
    source: str,
    *,
    line: int = 0,
    text: str = "",
    function_arities: Mapping[str, int] | None = None,
    parameters: tuple[str, ...] | set[str] = (),
) -> tuple[str, ...]:
    return compile_agent_expression(source, line=line, text=text, function_arities=function_arities, parameters=parameters).called_functions


def _normalize_refs(source: str) -> str:
    def repl_trail(match: re.Match[str]) -> str:
        return f"spur__{match.group(1)}"
    def repl_memory(match: re.Match[str]) -> str:
        return f"speicher__{match.group(1)}"
    text = _TRAIL_REF_RE.sub(repl_trail, source)
    text = _MEMORY_REF_RE.sub(repl_memory, text)
    return text


_ALLOWED_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div)
_ALLOWED_UNARY = (ast.UAdd, ast.USub)
_ALLOWED_CALL_ARITY = {
    "min": (2, None),
    "max": (2, None),
    "abs": (1, 1),
    "clamp": (1, 3),
    "mix": (3, 3),
    "step": (2, 2),
    "rauschen": (2, 3),
    "perlin": (2, 3),
    "simplex": (2, 3),
    "ganz": (1, 1),
}


def _validate_and_collect(
    tree: ast.Expression,
    source: str,
    line: int,
    text: str,
    function_arities: Mapping[str, int],
    parameters: set[str],
) -> tuple[ExpressionRefs, tuple[str, ...]]:
    fields: set[str] = set()
    trails: set[str] = set()
    memory: set[str] = set()
    calls: set[str] = set()

    def visit(node: ast.AST) -> None:
        match node:
            case ast.Expression(body=body):
                visit(body)
            case ast.Constant(value=value) if isinstance(value, (int, float)):
                return
            case ast.Name(id=name):
                if name in parameters:
                    return
                if name.startswith("spur__"):
                    real = name.removeprefix("spur__")
                    if not _IDENT_RE.match(real):
                        raise KeimSyntaxError(f"Ungültiger Spurname im Ausdruck: {real!r}.", line, text)
                    trails.add(real)
                elif name.startswith("speicher__"):
                    real = name.removeprefix("speicher__")
                    if not _IDENT_RE.match(real):
                        raise KeimSyntaxError(f"Ungültiger Speichername im Ausdruck: {real!r}.", line, text)
                    memory.add(real)
                else:
                    if not _IDENT_RE.match(name):
                        raise KeimSyntaxError(f"Ungültiger Feldname im Ausdruck: {name!r}.", line, text)
                    fields.add(name)
            case ast.BinOp(left=left, op=op, right=right) if isinstance(op, _ALLOWED_BINOPS):
                visit(left)
                visit(right)
            case ast.UnaryOp(op=op, operand=operand) if isinstance(op, _ALLOWED_UNARY):
                visit(operand)
            case ast.Call(func=ast.Name(id=name), args=args, keywords=[]) if name in _ALLOWED_CALL_ARITY:
                low, high = _ALLOWED_CALL_ARITY[name]
                if len(args) < low or (high is not None and len(args) > high):
                    raise KeimSyntaxError(f"Funktion {name} hat eine falsche Argumentzahl.", line, text)
                for arg in args:
                    visit(arg)
            case ast.Call(func=ast.Name(id=name), args=args, keywords=[]) if name in function_arities:
                expected = function_arities[name]
                if len(args) != expected:
                    raise KeimSyntaxError(f"Funktion {name} erwartet {expected} Argumente, erhalten {len(args)}.", line, text)
                calls.add(name)
                for arg in args:
                    visit(arg)
            case ast.Call(func=ast.Name(id=name)):
                raise KeimSyntaxError(f"Unbekannte Ausdrucksfunktion {name!r}.", line, text)
            case _:
                raise KeimSyntaxError(
                    "Agentenausdrücke erlauben Zahlen, Feldnamen, 'spur NAME', 'speicher NAME', + - * / () "
                    "und sichere Funktionen min/max/abs/clamp/mix/step sowie deklarierte funktion-Aufrufe.",
                    line,
                    text,
                )

    visit(tree)
    return (
        ExpressionRefs(fields=tuple(sorted(fields)), trails=tuple(sorted(trails)), memory=tuple(sorted(memory))),
        tuple(sorted(calls)),
    )


def _eval_node(
    node: ast.AST,
    resolve: Callable[[str], float],
    functions: Mapping[str, CompiledUserFunction],
    local_values: Mapping[str, float],
    depth: int,
) -> float:
    match node:
        case ast.Constant(value=value) if isinstance(value, (int, float)):
            return float(value)
        case ast.Name(id=name):
            if name in local_values:
                return float(local_values[name])
            return float(resolve(name))
        case ast.BinOp(left=left, op=ast.Add(), right=right):
            return _eval_node(left, resolve, functions, local_values, depth) + _eval_node(right, resolve, functions, local_values, depth)
        case ast.BinOp(left=left, op=ast.Sub(), right=right):
            return _eval_node(left, resolve, functions, local_values, depth) - _eval_node(right, resolve, functions, local_values, depth)
        case ast.BinOp(left=left, op=ast.Mult(), right=right):
            return _eval_node(left, resolve, functions, local_values, depth) * _eval_node(right, resolve, functions, local_values, depth)
        case ast.BinOp(left=left, op=ast.Div(), right=right):
            denom = _eval_node(right, resolve, functions, local_values, depth)
            return 0.0 if abs(denom) < 1e-12 else _eval_node(left, resolve, functions, local_values, depth) / denom
        case ast.UnaryOp(op=ast.UAdd(), operand=operand):
            return +_eval_node(operand, resolve, functions, local_values, depth)
        case ast.UnaryOp(op=ast.USub(), operand=operand):
            return -_eval_node(operand, resolve, functions, local_values, depth)
        case ast.Call(func=ast.Name(id=name), args=args, keywords=[]):
            values = [_eval_node(arg, resolve, functions, local_values, depth) for arg in args]
            match name:
                case "min":
                    return min(values)
                case "max":
                    return max(values)
                case "abs":
                    return abs(values[0])
                case "clamp":
                    if len(values) == 1:
                        lo, hi = 0.0, 1.0
                    elif len(values) == 2:
                        lo, hi = 0.0, values[1]
                    else:
                        lo, hi = values[1], values[2]
                    return max(lo, min(hi, values[0]))
                case "mix":
                    a, b, t = values
                    return a * (1.0 - t) + b * t
                case "step":
                    edge, x = values
                    return 0.0 if x < edge else 1.0
                case "ganz":
                    return float(int(round(values[0])))
                case "rauschen" | "perlin" | "simplex":
                    seed = values[2] if len(values) > 2 else 0.0
                    return _value_noise(values[0], values[1], seed)
            fn = functions.get(name)
            if fn is None:
                raise RuntimeError(f"Unbekannte validierte Funktion: {name}")
            return fn.call(values, resolve, functions, _depth=depth + 1)
        case _:
            raise RuntimeError(f"Ungültiger validierter Ausdrucksknoten: {node!r}")


def _value_noise(x: float, y: float, seed: float = 0.0) -> float:
    """Deterministisches, kontinuierlich interpoliertes Value-Noise in [0,1].

    Kein exakter Perlin/Simplex-Clone, sondern eine kleine stdlib-fähige
    Rauschprimitive ohne externe Abhängigkeit. Für höhere Qualität kann dieser
    Funktionskörper später nativ ersetzt werden, die Sprachsignatur bleibt stabil.
    """
    import math
    xi, yi = math.floor(x), math.floor(y)
    xf, yf = x - xi, y - yi
    def h(ix: int, iy: int) -> float:
        n = (ix * 374761393 + iy * 668265263 + int(seed * 104729)) & 0xffffffff
        n = (n ^ (n >> 13)) * 1274126177 & 0xffffffff
        return ((n ^ (n >> 16)) & 0xffffff) / float(0xffffff)
    def smooth(t: float) -> float:
        return t * t * (3.0 - 2.0 * t)
    a, b = h(xi, yi), h(xi + 1, yi)
    c, d = h(xi, yi + 1), h(xi + 1, yi + 1)
    u, v = smooth(xf), smooth(yf)
    return (a * (1.0 - u) + b * u) * (1.0 - v) + (c * (1.0 - u) + d * u) * v
