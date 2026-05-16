from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import ctypes as C
import platform
from typing import Any


class DriverLoadError(RuntimeError):
    pass


def _is_loadable_native_driver(path: Path) -> bool:
    suffix = path.suffix.lower()
    system = platform.system().lower()
    if system == "windows":
        return suffix == ".dll"
    if system == "linux":
        return suffix == ".so"
    if system == "darwin":
        return suffix in {".dylib", ".so"}
    return suffix in {".dll", ".so", ".dylib"}



CORE_SYMBOLS = (
    "initialize_gpu",
    "finish_gpu",
    "shutdown_gpu",
    "allocate_gpu_memory",
    "free_gpu_memory",
    "write_host_to_gpu_blocking",
    "read_gpu_to_host_blocking",
)

UTILITY_SYMBOLS = (
    "cc_get_version",
    "cc_get_last_error",
    "simulated_get_compute_unit_count",
)

EXPERIMENTAL_SYMBOLS = (
    "execute_fused_diffusion_on_gpu",
    "execute_energy_gated_scheduler_gpu",
    "execute_resonant_field_step_gpu",
    "execute_morphogenetic_rule_step_gpu",
    "execute_proto_segmented_sum_gpu",
    "execute_proto_update_step_gpu",
    "subqg_simulation_step_host_fields",
    "subqg_simulation_step_native_fields",
    "subqg_set_multifield_state",
    "shadow_init",
    "shadow_cycle",
)


@dataclass(slots=True, frozen=True)
class DriverSymbolReport:
    dll: Path
    loaded: bool
    available: tuple[str, ...]
    missing: tuple[str, ...]
    version: str | None = None
    last_error: str | None = None
    smoke_ok: bool | None = None
    smoke_detail: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "dll": str(self.dll),
            "loaded": self.loaded,
            "available": list(self.available),
            "missing": list(self.missing),
            "version": self.version,
            "last_error": self.last_error,
            "smoke_ok": self.smoke_ok,
            "smoke_detail": self.smoke_detail,
        }

    def format(self) -> str:
        lines = ["[Keim] Driver-Info", f"  DLL:       {self.dll}", f"  Geladen:   {self.loaded}"]
        if self.version:
            lines.append(f"  Version:   {self.version}")
        lines.append(f"  Gefunden:  {len(self.available)} Symbole")
        lines.append(f"  Fehlend:   {len(self.missing)} Symbole")
        if self.smoke_ok is not None:
            lines.append(f"  Smoke:     {'OK' if self.smoke_ok else 'FEHLER'}")
            if self.smoke_detail:
                lines.append(f"             {self.smoke_detail}")
        if self.available:
            lines.append("  Verfügbare Symbole:")
            for name in self.available:
                lines.append(f"    + {name}")
        if self.missing:
            lines.append("  Fehlende Symbole:")
            for name in self.missing:
                lines.append(f"    - {name}")
        if self.last_error:
            lines.append(f"  Letzter Treiberstatus: {self.last_error}")
        return "\n".join(lines)


@dataclass(slots=True)
class GpuBuffer:
    handle: int
    size: int


@dataclass(slots=True, frozen=True)
class DriverSmokeResult:
    ok: bool
    detail: str
    values_written: tuple[float, ...]
    values_read: tuple[float, ...]


class DriverProbe:
    def __init__(self, dll_path: str | Path, gpu_index: int = 0) -> None:
        self.dll_path = Path(dll_path)
        self.gpu_index = gpu_index

    def inspect(self, *, smoke: bool = False) -> DriverSymbolReport:
        if not self.dll_path.exists():
            raise DriverLoadError(f"DLL nicht gefunden: {self.dll_path}")

        names = CORE_SYMBOLS + UTILITY_SYMBOLS + EXPERIMENTAL_SYMBOLS

        if not _is_loadable_native_driver(self.dll_path):
            return DriverSymbolReport(
                dll=self.dll_path,
                loaded=False,
                available=(),
                missing=names,
                smoke_ok=False if smoke else None,
                smoke_detail="Treiberartefakt ist auf dieser Plattform nicht direkt ladbar." if smoke else None,
            )

        try:
            lib = C.CDLL(str(self.dll_path))
        except OSError as exc:
            raise DriverLoadError(f"Native Treiberbibliothek konnte nicht geladen werden: {exc}") from exc

        available, missing = [], []
        for name in names:
            try:
                getattr(lib, name)
                available.append(name)
            except AttributeError:
                missing.append(name)

        version = _try_version(lib)
        last_error = _try_last_error(lib)
        smoke_ok = None
        smoke_detail = None
        if smoke:
            try:
                result = CipherCoreDriver(self.dll_path, self.gpu_index).smoke_test()
                smoke_ok = result.ok
                smoke_detail = result.detail
            except Exception as exc:
                smoke_ok = False
                smoke_detail = str(exc)

        return DriverSymbolReport(
            dll=self.dll_path,
            loaded=True,
            available=tuple(available),
            missing=tuple(missing),
            version=version,
            last_error=last_error,
            smoke_ok=smoke_ok,
            smoke_detail=smoke_detail,
        )


class CipherCoreDriver:
    def __init__(self, dll_path: str | Path, gpu_index: int = 0) -> None:
        self.dll_path = Path(dll_path)
        if not _is_loadable_native_driver(self.dll_path):
            raise DriverLoadError("Dieses Treiberartefakt ist auf dieser Plattform nicht direkt ladbar.")
        if not self.dll_path.exists():
            raise DriverLoadError(f"DLL nicht gefunden: {self.dll_path}")
        self.gpu_index = gpu_index
        self.lib = C.CDLL(str(self.dll_path))
        self._bind_core()

    def _bind_core(self) -> None:
        self.lib.initialize_gpu.argtypes = [C.c_int]
        self.lib.initialize_gpu.restype = C.c_int
        self.lib.finish_gpu.argtypes = [C.c_int]
        self.lib.finish_gpu.restype = C.c_int
        self.lib.shutdown_gpu.argtypes = [C.c_int]
        self.lib.shutdown_gpu.restype = None
        self.lib.allocate_gpu_memory.argtypes = [C.c_int, C.c_size_t]
        self.lib.allocate_gpu_memory.restype = C.c_void_p
        self.lib.free_gpu_memory.argtypes = [C.c_int, C.c_void_p]
        self.lib.free_gpu_memory.restype = None
        self.lib.write_host_to_gpu_blocking.argtypes = [C.c_int, C.c_void_p, C.c_size_t, C.c_size_t, C.c_void_p]
        self.lib.write_host_to_gpu_blocking.restype = C.c_int
        self.lib.read_gpu_to_host_blocking.argtypes = [C.c_int, C.c_void_p, C.c_size_t, C.c_size_t, C.c_void_p]
        self.lib.read_gpu_to_host_blocking.restype = C.c_int

    def initialize(self) -> None:
        ok = self.lib.initialize_gpu(self.gpu_index)
        if not ok:
            raise DriverLoadError(f"initialize_gpu meldete Fehler: {self.last_error()}")

    def finish(self) -> None:
        ok = self.lib.finish_gpu(self.gpu_index)
        if not ok:
            raise DriverLoadError(f"finish_gpu meldete Fehler: {self.last_error()}")

    def shutdown(self) -> None:
        self.lib.shutdown_gpu(self.gpu_index)

    def last_error(self) -> str | None:
        return _try_last_error(self.lib)

    def alloc(self, size: int) -> GpuBuffer:
        ptr = self.lib.allocate_gpu_memory(self.gpu_index, C.c_size_t(size))
        if not ptr:
            raise DriverLoadError(f"allocate_gpu_memory fehlgeschlagen: {size} Bytes | {self.last_error()}")
        return GpuBuffer(handle=int(ptr), size=size)

    def free(self, buffer: GpuBuffer) -> None:
        self.lib.free_gpu_memory(self.gpu_index, C.c_void_p(buffer.handle))

    def smoke_test(self) -> DriverSmokeResult:
        values = (C.c_float * 4)(0.125, 0.25, 0.5, 1.0)
        out = (C.c_float * 4)()
        buffer: GpuBuffer | None = None
        try:
            self.initialize()
            buffer = self.alloc(C.sizeof(values))
            ok_write = self.lib.write_host_to_gpu_blocking(self.gpu_index, C.c_void_p(buffer.handle), C.c_size_t(0), C.c_size_t(C.sizeof(values)), C.byref(values))
            if not ok_write:
                raise DriverLoadError(f"write_host_to_gpu_blocking fehlgeschlagen: {self.last_error()}")
            ok_read = self.lib.read_gpu_to_host_blocking(self.gpu_index, C.c_void_p(buffer.handle), C.c_size_t(0), C.c_size_t(C.sizeof(out)), C.byref(out))
            if not ok_read:
                raise DriverLoadError(f"read_gpu_to_host_blocking fehlgeschlagen: {self.last_error()}")
            written = tuple(float(v) for v in values)
            read = tuple(float(v) for v in out)
            ok = all(abs(a - b) < 1e-6 for a, b in zip(written, read))
            return DriverSmokeResult(ok=ok, detail="allocate/write/read/free Roundtrip", values_written=written, values_read=read)
        finally:
            if buffer is not None:
                self.free(buffer)
            try:
                self.finish()
            except Exception:
                pass
            try:
                self.shutdown()
            except Exception:
                pass


def _try_version(lib) -> str | None:
    try:
        func = lib.cc_get_version
        func.argtypes = []
        func.restype = C.c_char_p
        raw = func()
        return raw.decode("utf-8", errors="replace") if raw else None
    except Exception:
        return None


def _try_last_error(lib) -> str | None:
    try:
        func = lib.cc_get_last_error
        func.argtypes = []
        func.restype = C.c_char_p
        raw = func()
        return raw.decode("utf-8", errors="replace") if raw else None
    except Exception:
        return None
