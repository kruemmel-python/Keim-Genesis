
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import ctypes
from typing import Any

from .errors import KeimRuntimeError


@dataclass(slots=True)
class ForeignFunctionResult:
    library: str
    function: str
    value: Any


class ForeignLibrary:
    """Kleine, sichere C-FFI-Brücke für Keim.

    Unterstützt absichtlich nur primitive ABI-Typen. Komplexe Pointer-/Struct-
    Übergaben bleiben Native-Bridge-Aufgabe, damit Keim-Programme nicht aus
    Versehen Prozessspeicher beschädigen.
    """

    def __init__(self, name: str, path: str) -> None:
        self.name = name
        self.path = str(Path(path))
        try:
            self.handle = ctypes.CDLL(self.path)
        except OSError as exc:
            raise KeimRuntimeError(f"FFI-Bibliothek {name!r} konnte nicht geladen werden: {exc}") from exc

    def call(self, function: str, args: tuple[Any, ...], result_kind: str = "ganzzahl") -> Any:
        try:
            fn = getattr(self.handle, function)
        except AttributeError as exc:
            raise KeimRuntimeError(f"FFI-Funktion {function!r} existiert nicht in Bibliothek {self.name!r}.") from exc

        c_args = []
        argtypes = []
        buffers: list[Any] = []
        for value in args:
            if isinstance(value, bool):
                argtypes.append(ctypes.c_int)
                c_args.append(int(value))
            elif isinstance(value, int):
                argtypes.append(ctypes.c_longlong)
                c_args.append(int(value))
            elif isinstance(value, float):
                argtypes.append(ctypes.c_double)
                c_args.append(float(value))
            elif isinstance(value, str):
                data = value.encode("utf-8")
                buf = ctypes.create_string_buffer(data)
                buffers.append(buf)
                argtypes.append(ctypes.c_char_p)
                c_args.append(ctypes.cast(buf, ctypes.c_char_p))
            else:
                raise KeimRuntimeError(f"FFI unterstützt diesen Argumenttyp noch nicht: {type(value).__name__}")

        fn.argtypes = argtypes
        match result_kind:
            case "zahl":
                fn.restype = ctypes.c_double
            case "bool":
                fn.restype = ctypes.c_int
            case "text":
                fn.restype = ctypes.c_char_p
            case "referenz":
                fn.restype = ctypes.c_void_p
            case _:
                fn.restype = ctypes.c_longlong

        result = fn(*c_args)
        if result_kind == "bool":
            return bool(result)
        if result_kind == "text":
            return b"" if result is None else result.decode("utf-8", errors="replace")
        if result_kind == "referenz":
            return int(result or 0)
        if result_kind == "zahl":
            return float(result)
        return int(result)
