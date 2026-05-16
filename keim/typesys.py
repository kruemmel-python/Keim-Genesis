from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import json
from typing import Any


class KeimType(StrEnum):
    FLOAT = "zahl"
    INT = "ganzzahl"
    BOOL = "bool"
    TEXT = "text"
    ARRAY = "array"
    MAP = "karte"
    REFERENCE = "referenz"


@dataclass(slots=True, frozen=True)
class GenericKeimType:
    base: KeimType
    params: tuple["TypeSpec", ...] = ()

    def __str__(self) -> str:
        if not self.params:
            return self.base.value
        return f"{self.base.value}<" + ", ".join(str(p) for p in self.params) + ">"


TypeSpec = KeimType | GenericKeimType

ALIASES = {
    "zahl": KeimType.FLOAT, "float": KeimType.FLOAT, "fliesszahl": KeimType.FLOAT,
    "ganzzahl": KeimType.INT, "integer": KeimType.INT, "int": KeimType.INT,
    "bool": KeimType.BOOL, "boolean": KeimType.BOOL, "wahrheit": KeimType.BOOL,
    "text": KeimType.TEXT, "string": KeimType.TEXT,
    "array": KeimType.ARRAY, "liste": KeimType.ARRAY, "list": KeimType.ARRAY,
    "karte": KeimType.MAP, "map": KeimType.MAP, "dict": KeimType.MAP,
    "referenz": KeimType.REFERENCE, "ref": KeimType.REFERENCE,
}


@dataclass(slots=True, frozen=True)
class TypedValue:
    kind: TypeSpec
    value: Any

    def as_float(self) -> float:
        kind = self.kind.base if isinstance(self.kind, GenericKeimType) else self.kind
        match kind:
            case KeimType.FLOAT:
                return float(self.value)
            case KeimType.INT:
                return float(int(self.value))
            case KeimType.BOOL:
                return 1.0 if bool(self.value) else 0.0
            case KeimType.TEXT:
                try:
                    return float(str(self.value).replace(",", "."))
                except ValueError:
                    return 0.0
            case KeimType.ARRAY:
                vals = self.value if isinstance(self.value, list) else []
                nums = [to_float(v) for v in vals]
                return sum(nums) / len(nums) if nums else 0.0
            case KeimType.MAP:
                return float(len(self.value)) if isinstance(self.value, dict) else 0.0
            case KeimType.REFERENCE:
                return 0.0
        return 0.0


def parse_type(raw: str | None) -> TypeSpec:
    if raw is None or raw == "":
        return KeimType.FLOAT
    text = raw.strip().lower().replace(" ", "")
    if "<" in text and text.endswith(">"):
        base_raw, param_raw = text.split("<", 1)
        base = parse_type(base_raw)
        if isinstance(base, GenericKeimType):
            base = base.base
        params = tuple(parse_type(part) for part in _split_params(param_raw[:-1]))
        return GenericKeimType(base=base, params=params)
    if text not in ALIASES:
        raise ValueError(f"Unbekannter Keim-Typ: {raw!r}")
    return ALIASES[text]


def _split_params(text: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    start = 0
    for i, ch in enumerate(text):
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(text[start:i].strip())
            start = i + 1
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def parse_literal(raw: str, kind: TypeSpec | str = KeimType.FLOAT) -> Any:
    if not isinstance(kind, (KeimType, GenericKeimType)):
        kind = parse_type(str(kind))
    base = kind.base if isinstance(kind, GenericKeimType) else kind
    text = raw.strip()
    match base:
        case KeimType.FLOAT:
            return clamp01(float(text.replace(",", ".")))
        case KeimType.INT:
            return int(float(text.replace(",", ".")))
        case KeimType.BOOL:
            low = text.lower()
            if low in {"wahr", "true", "ja", "1", "an"}:
                return True
            if low in {"falsch", "false", "nein", "0", "aus"}:
                return False
            raise ValueError(f"Bool-Wert erwartet, erhalten {raw!r}")
        case KeimType.TEXT:
            return text.strip('"').strip("'")
        case KeimType.ARRAY:
            body = text
            if body.startswith("[") and body.endswith("]"):
                body = body[1:-1].strip()
            if not body:
                return []
            try:
                parsed = json.loads(text)
                vals = parsed if isinstance(parsed, list) else [parsed]
            except Exception:
                vals = [_parse_array_item(part.strip()) for part in body.split(",")]
            if isinstance(kind, GenericKeimType) and kind.params:
                return [coerce_value(v, kind.params[0]) for v in vals]
            return vals
        case KeimType.MAP:
            if not text or text == "{}":
                return {}
            try:
                parsed = json.loads(text)
            except Exception as exc:
                raise ValueError(f"Karte erwartet JSON-Objekt, erhalten {raw!r}") from exc
            if not isinstance(parsed, dict):
                raise ValueError(f"Karte erwartet JSON-Objekt, erhalten {raw!r}")
            if isinstance(kind, GenericKeimType) and len(kind.params) >= 2:
                kt, vt = kind.params[0], kind.params[1]
                return {coerce_value(k, kt): coerce_value(v, vt) for k, v in parsed.items()}
            return parsed
        case KeimType.REFERENCE:
            return text.strip('"').strip("'")


def _parse_array_item(text: str) -> Any:
    low = text.lower()
    if low in {"wahr", "true", "ja", "an"}:
        return True
    if low in {"falsch", "false", "nein", "aus"}:
        return False
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        return text[1:-1]
    try:
        value = float(text.replace(",", "."))
        return int(value) if value.is_integer() else value
    except ValueError:
        return text


def coerce_value(value: Any, kind: TypeSpec | str) -> Any:
    if not isinstance(kind, (KeimType, GenericKeimType)):
        kind = parse_type(str(kind))
    base = kind.base if isinstance(kind, GenericKeimType) else kind
    match base:
        case KeimType.FLOAT:
            return clamp01(to_float(value))
        case KeimType.INT:
            if isinstance(value, str) and not _looks_number(value):
                raise ValueError(f"ganzzahl erwartet, erhalten {value!r}")
            return int(round(to_float(value)))
        case KeimType.BOOL:
            return bool(value if not isinstance(value, str) else value.lower() in {"wahr", "true", "ja", "1", "an"})
        case KeimType.TEXT:
            return str(value)
        case KeimType.ARRAY:
            vals = list(value) if isinstance(value, (list, tuple)) else [value]
            if isinstance(kind, GenericKeimType) and kind.params:
                return [coerce_value(v, kind.params[0]) for v in vals]
            return vals
        case KeimType.MAP:
            if value is None:
                raw = {}
            elif isinstance(value, dict):
                raw = dict(value)
            elif isinstance(value, str):
                try:
                    parsed = json.loads(value)
                    raw = parsed if isinstance(parsed, dict) else {"wert": value}
                except Exception:
                    raw = {"wert": value}
            else:
                raw = {"wert": value}
            if isinstance(kind, GenericKeimType) and len(kind.params) >= 2:
                kt, vt = kind.params[0], kind.params[1]
                return {coerce_value(k, kt): coerce_value(v, vt) for k, v in raw.items()}
            return raw
        case KeimType.REFERENCE:
            return "" if value is None else str(value)


def type_accepts(value: Any, kind: TypeSpec | str) -> bool:
    try:
        coerce_value(value, kind)
        return True
    except Exception:
        return False


def element_type(kind: TypeSpec | str) -> TypeSpec | None:
    if not isinstance(kind, (KeimType, GenericKeimType)):
        kind = parse_type(str(kind))
    if isinstance(kind, GenericKeimType) and kind.base == KeimType.ARRAY and kind.params:
        return kind.params[0]
    return None


def map_types(kind: TypeSpec | str) -> tuple[TypeSpec | None, TypeSpec | None]:
    if not isinstance(kind, (KeimType, GenericKeimType)):
        kind = parse_type(str(kind))
    if isinstance(kind, GenericKeimType) and kind.base == KeimType.MAP and len(kind.params) >= 2:
        return kind.params[0], kind.params[1]
    return None, None


def _looks_number(value: str) -> bool:
    try:
        float(value.replace(",", "."))
        return True
    except Exception:
        return False


def to_float(value: Any) -> float:
    if isinstance(value, TypedValue):
        return value.as_float()
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, list):
        vals = [to_float(v) for v in value]
        return sum(vals) / len(vals) if vals else 0.0
    if isinstance(value, dict):
        return float(len(value))
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return 0.0


def clamp01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value
