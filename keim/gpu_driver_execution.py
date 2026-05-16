
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Iterable
import ctypes as C
import hashlib
import json
import math
import os
import platform
import re
import struct


class GpuExecutionError(RuntimeError):
    """Fehler der Keim v7.6 GPU Driver Execution Schicht."""


@dataclass(slots=True, frozen=True)
class KernelSpec:
    name: str
    symbol: str
    category: str
    arg_kinds: tuple[str, ...]
    description: str
    deterministic: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "symbol": self.symbol,
            "category": self.category,
            "arg_kinds": list(self.arg_kinds),
            "description": self.description,
            "deterministic": self.deterministic,
        }


KERNEL_SPECS: tuple[KernelSpec, ...] = (
    KernelSpec(
        "fused_diffusion",
        "execute_fused_diffusion_on_gpu",
        "field",
        ("buffer", "buffer", "buffer", "int", "int", "int", "float", "float"),
        "Fused diffusion/weighted aggregation kernel for BxNxD tensors.",
    ),
    KernelSpec(
        "energy_gated_scheduler",
        "execute_energy_gated_scheduler_gpu",
        "scheduler",
        ("buffer", "buffer", "buffer", "buffer", "buffer", "int", "float", "float", "float"),
        "Selects active indices from energy/nutrient fields.",
    ),
    KernelSpec(
        "resonant_field_step",
        "execute_resonant_field_step_gpu",
        "field",
        ("buffer", "buffer", "buffer", "buffer", "buffer", "buffer", "int", "int", "float", "float", "float", "float", "float"),
        "Resonant state/velocity field update with neighbor coupling.",
    ),
    KernelSpec(
        "morphogenetic_rule_step",
        "execute_morphogenetic_rule_step_gpu",
        "cellular",
        ("buffer", "buffer", "buffer", "buffer", "buffer", "buffer", "buffer", "buffer", "buffer", "int", "int", "float"),
        "Rule-driven morphogenetic cell type and potential update.",
    ),
    KernelSpec(
        "proto_segmented_sum",
        "execute_proto_segmented_sum_gpu",
        "prototype",
        ("buffer", "buffer", "buffer", "buffer", "int", "int", "int"),
        "Segmented sums for prototype learning.",
    ),
    KernelSpec(
        "proto_update",
        "execute_proto_update_step_gpu",
        "prototype",
        ("buffer", "buffer", "buffer", "float", "int", "int"),
        "Prototype update step from sums/counts.",
    ),
    KernelSpec(
        "subqg_host_fields",
        "subqg_simulation_step_host_fields",
        "subqg",
        ("int", "host_float", "host_float", "host_float", "host_float", "host_float", "host_float", "host_float", "host_float", "float", "float", "float"),
        "Host-visible SubQG multifield step.",
    ),
    KernelSpec(
        "subqg_native_fields",
        "subqg_simulation_step_native_fields",
        "subqg",
        ("float", "float", "float"),
        "GPU-resident SubQG step without readback.",
    ),
)

REQUIRED_CORE_SYMBOLS = (
    "initialize_gpu",
    "finish_gpu",
    "shutdown_gpu",
    "allocate_gpu_memory",
    "free_gpu_memory",
    "write_host_to_gpu_blocking",
    "read_gpu_to_host_blocking",
)

OPTIONAL_UTILITY_SYMBOLS = (
    "cc_get_version",
    "cc_get_last_error",
    "simulated_get_compute_unit_count",
    "subqg_initialize_state",
    "subqg_initialize_state_batched",
    "subqg_set_multifield_state",
    "subqg_set_deterministic_mode",
    "shadow_init",
    "shadow_cycle",
)


def default_driver_path(cwd: Path | None = None) -> Path:
    """Return the best platform-appropriate CipherCore/OpenCL driver artifact.

    v7.6 originally preferred the Windows DLL.  v7.6.4 adds first-class Linux
    support for driver/build/libCC_OpenCL.so while keeping Windows paths intact.
    """
    base = Path(cwd or Path.cwd())
    repo = Path(__file__).resolve().parents[1]
    system = platform.system().lower()
    if system == "windows":
        candidates = [
            base / "driver" / "build" / "CC_OpenCl.dll",
            base / "driver" / "build" / "CC_OpenCL.dll",
            base / "driver" / "CL" / "gpu_driver.dll",
            repo / "driver" / "build" / "CC_OpenCl.dll",
            repo / "driver" / "build" / "CC_OpenCL.dll",
        ]
    elif system == "linux":
        candidates = [
            base / "driver" / "build" / "libCC_OpenCL.so",
            base / "driver" / "build" / "libCC_OpenCl.so",
            repo / "driver" / "build" / "libCC_OpenCL.so",
            repo / "driver" / "build" / "libCC_OpenCl.so",
            base / "driver" / "build" / "CC_OpenCl.dll",
            repo / "driver" / "build" / "CC_OpenCl.dll",
        ]
    elif system == "darwin":
        candidates = [
            base / "driver" / "build" / "libCC_OpenCL.dylib",
            repo / "driver" / "build" / "libCC_OpenCL.dylib",
            base / "driver" / "build" / "libCC_OpenCL.so",
            repo / "driver" / "build" / "libCC_OpenCL.so",
        ]
    else:
        candidates = [
            base / "driver" / "build" / "libCC_OpenCL.so",
            base / "driver" / "build" / "CC_OpenCl.dll",
            repo / "driver" / "build" / "libCC_OpenCL.so",
            repo / "driver" / "build" / "CC_OpenCl.dll",
        ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


def _scan_ascii_symbols(path: Path) -> set[str]:
    if not path.exists() or not path.is_file():
        return set()
    data = path.read_bytes()
    found: set[str] = set()
    for sym in list(REQUIRED_CORE_SYMBOLS) + list(OPTIONAL_UTILITY_SYMBOLS) + [s.symbol for s in KERNEL_SPECS]:
        if sym.encode("ascii", errors="ignore") in data:
            found.add(sym)
    return found


def _sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(slots=True)
class DriverCapabilityReport:
    dll: str
    exists: bool
    platform: str
    can_load: bool
    loaded: bool
    mode: str
    sha256: str | None
    version: str | None
    core_available: list[str]
    core_missing: list[str]
    kernels_available: list[str]
    kernels_missing: list[str]
    utility_available: list[str]
    utility_missing: list[str]
    notes: list[str] = field(default_factory=list)

    @property
    def ready_for_real_dispatch(self) -> bool:
        return self.exists and self.loaded and not self.core_missing and bool(self.kernels_available)

    @property
    def ready_for_planned_dispatch(self) -> bool:
        return self.exists and not self.core_missing and bool(self.kernels_available)

    def as_dict(self) -> dict[str, Any]:
        return {
            "dll": self.dll,
            "exists": self.exists,
            "platform": self.platform,
            "can_load": self.can_load,
            "loaded": self.loaded,
            "mode": self.mode,
            "sha256": self.sha256,
            "version": self.version,
            "core_available": self.core_available,
            "core_missing": self.core_missing,
            "kernels_available": self.kernels_available,
            "kernels_missing": self.kernels_missing,
            "utility_available": self.utility_available,
            "utility_missing": self.utility_missing,
            "ready_for_real_dispatch": self.ready_for_real_dispatch,
            "ready_for_planned_dispatch": self.ready_for_planned_dispatch,
            "notes": self.notes,
            "kernel_specs": [s.as_dict() for s in KERNEL_SPECS],
        }

    def format(self) -> str:
        lines = [
            "[Keim v7.6] GPU Driver Execution",
            f"  DLL:          {self.dll}",
            f"  Existiert:    {self.exists}",
            f"  Plattform:    {self.platform}",
            f"  Modus:        {self.mode}",
            f"  Geladen:      {self.loaded}",
            f"  Real Dispatch:{self.ready_for_real_dispatch}",
            f"  Plan Dispatch:{self.ready_for_planned_dispatch}",
        ]
        if self.version:
            lines.append(f"  Version:      {self.version}")
        if self.sha256:
            lines.append(f"  SHA-256:      {self.sha256}")
        lines.append(f"  Core:         {len(self.core_available)}/{len(REQUIRED_CORE_SYMBOLS)}")
        lines.append(f"  Kernels:      {len(self.kernels_available)}/{len(KERNEL_SPECS)}")
        if self.core_missing:
            lines.append("  Fehlende Core-Symbole: " + ", ".join(self.core_missing))
        if self.kernels_available:
            lines.append("  Dispatchfähige Kernel:")
            for k in self.kernels_available:
                lines.append(f"    + {k}")
        if self.notes:
            lines.append("  Hinweise:")
            for n in self.notes:
                lines.append(f"    - {n}")
        return "\n".join(lines)


def inspect_driver(dll: Path | None = None, *, load: bool = True, gpu_index: int = 0) -> DriverCapabilityReport:
    path = Path(dll) if dll else default_driver_path()
    exists = path.exists()
    sha = _sha256(path)
    symbols = _scan_ascii_symbols(path) if exists else set()
    notes: list[str] = []
    lib = None
    loaded = False
    version = None
    can_load = exists and _is_loadable_native_driver(path)
    kind = _driver_kind(path)
    mode = "real" if can_load else "portable-symbol-scan"
    if exists and load and can_load:
        try:
            lib = C.CDLL(str(path))
            loaded = True
            symbols = set(symbols)
            for sym in list(REQUIRED_CORE_SYMBOLS) + list(OPTIONAL_UTILITY_SYMBOLS) + [s.symbol for s in KERNEL_SPECS]:
                try:
                    getattr(lib, sym)
                    symbols.add(sym)
                except AttributeError:
                    pass
            version = _try_version(lib)
            notes.append(f"Native Treiberbibliothek geladen: {kind}")
        except OSError as exc:
            notes.append(f"Native Treiberbibliothek konnte nicht geladen werden ({kind}): {exc}")
    elif exists and not can_load:
        notes.append(f"Treiberartefakt existiert, ist auf dieser Plattform aber nicht direkt ladbar: {kind}; Symbolscan/CPU-Fallback bleiben aktiv.")
    elif not exists:
        notes.append("Treiberdatei nicht gefunden.")

    core_av = [s for s in REQUIRED_CORE_SYMBOLS if s in symbols]
    core_miss = [s for s in REQUIRED_CORE_SYMBOLS if s not in symbols]
    kern_av = [spec.name for spec in KERNEL_SPECS if spec.symbol in symbols]
    kern_miss = [spec.name for spec in KERNEL_SPECS if spec.symbol not in symbols]
    util_av = [s for s in OPTIONAL_UTILITY_SYMBOLS if s in symbols]
    util_miss = [s for s in OPTIONAL_UTILITY_SYMBOLS if s not in symbols]
    return DriverCapabilityReport(
        dll=str(path),
        exists=exists,
        platform=platform.platform(),
        can_load=can_load,
        loaded=loaded,
        mode=mode if loaded else ("symbol-scan" if exists else "missing"),
        sha256=sha,
        version=version,
        core_available=core_av,
        core_missing=core_miss,
        kernels_available=kern_av,
        kernels_missing=kern_miss,
        utility_available=util_av,
        utility_missing=util_miss,
        notes=notes,
    )


def _is_loadable_native_driver(path: Path) -> bool:
    suffix = path.suffix.lower()
    system = platform.system().lower()
    if system == "windows":
        return suffix == ".dll"
    if system == "linux":
        return suffix == ".so"
    if system == "darwin":
        return suffix in {".dylib", ".so"}
    return suffix in {".so", ".dylib", ".dll"}


def _driver_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".dll":
        return "windows-dll"
    if suffix == ".so":
        return "linux-elf-so"
    if suffix == ".dylib":
        return "macos-dylib"
    return "unknown"


def _try_version(lib: Any) -> str | None:
    try:
        fn = lib.cc_get_version
        fn.argtypes = []
        fn.restype = C.c_char_p
        raw = fn()
        return raw.decode("utf-8", errors="replace") if raw else None
    except Exception:
        return None


@dataclass(slots=True)
class GpuArray:
    name: str
    dtype: str
    values: list[float] | list[int]

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "dtype": self.dtype, "values": list(self.values)}


@dataclass(slots=True)
class DispatchProfile:
    kernel: str
    mode: str
    ok: bool
    upload_ms: float = 0.0
    kernel_ms: float = 0.0
    download_ms: float = 0.0
    total_ms: float = 0.0
    detail: str = ""
    cpu_reference_ms: float | None = None
    max_abs_error: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "kernel": self.kernel,
            "mode": self.mode,
            "ok": self.ok,
            "upload_ms": self.upload_ms,
            "kernel_ms": self.kernel_ms,
            "download_ms": self.download_ms,
            "total_ms": self.total_ms,
            "detail": self.detail,
            "cpu_reference_ms": self.cpu_reference_ms,
            "max_abs_error": self.max_abs_error,
        }



@dataclass(slots=True)
class DeviceBuffer:
    handle: int
    size: int
    name: str = ""

class RealGpuBufferManager:
    """Persistent GPU buffer manager for the CC_OpenCl.dll core memory ABI."""

    def __init__(self, lib: Any, gpu_index: int) -> None:
        self.lib = lib
        self.gpu_index = gpu_index
        self.buffers: list[DeviceBuffer] = []

    def alloc(self, size: int, name: str = "") -> DeviceBuffer:
        ptr = self.lib.allocate_gpu_memory(self.gpu_index, C.c_size_t(size))
        if not ptr:
            raise GpuExecutionError(f"allocate_gpu_memory failed for {size} bytes")
        buf = DeviceBuffer(int(ptr), size, name)
        self.buffers.append(buf)
        return buf

    def free(self, buf: DeviceBuffer) -> None:
        if buf.handle:
            self.lib.free_gpu_memory(self.gpu_index, C.c_void_p(buf.handle))
            buf.handle = 0

    def close(self) -> None:
        for buf in list(self.buffers):
            try:
                self.free(buf)
            except Exception:
                pass
        self.buffers.clear()

    def upload_f32(self, values: list[float], name: str = "") -> DeviceBuffer:
        arr = (C.c_float * len(values))(*[float(v) for v in values])
        buf = self.alloc(C.sizeof(arr), name=name)
        ok = self.lib.write_host_to_gpu_blocking(self.gpu_index, C.c_void_p(buf.handle), C.c_size_t(0), C.c_size_t(C.sizeof(arr)), C.byref(arr))
        if not ok:
            raise GpuExecutionError("write_host_to_gpu_blocking failed")
        return buf

    def upload_i32(self, values: list[int], name: str = "") -> DeviceBuffer:
        arr = (C.c_int * len(values))(*[int(v) for v in values])
        buf = self.alloc(C.sizeof(arr), name=name)
        ok = self.lib.write_host_to_gpu_blocking(self.gpu_index, C.c_void_p(buf.handle), C.c_size_t(0), C.c_size_t(C.sizeof(arr)), C.byref(arr))
        if not ok:
            raise GpuExecutionError("write_host_to_gpu_blocking failed")
        return buf

    def download_f32(self, buf: DeviceBuffer, count: int) -> list[float]:
        arr = (C.c_float * count)()
        ok = self.lib.read_gpu_to_host_blocking(self.gpu_index, C.c_void_p(buf.handle), C.c_size_t(0), C.c_size_t(C.sizeof(arr)), C.byref(arr))
        if not ok:
            raise GpuExecutionError("read_gpu_to_host_blocking failed")
        return [float(v) for v in arr]

    def download_i32(self, buf: DeviceBuffer, count: int) -> list[int]:
        arr = (C.c_int * count)()
        ok = self.lib.read_gpu_to_host_blocking(self.gpu_index, C.c_void_p(buf.handle), C.c_size_t(0), C.c_size_t(C.sizeof(arr)), C.byref(arr))
        if not ok:
            raise GpuExecutionError("read_gpu_to_host_blocking failed")
        return [int(v) for v in arr]

class CpuFallbackKernelPack:
    """Deterministische CPU-Referenz für die GPU-Kernel-ABI.

    Diese Klasse ist kein Ersatz für die GPU, sondern eine Enterprise-Sicherheitsleine:
    gleiche API, deterministische Referenz, Differentialtests, reproduzierbare Reports.
    """

    mode = "cpu-fallback"

    def fused_diffusion(self, x: list[float], w: list[float], *, B: int, N: int, D: int, gamma: float, sigma: float) -> list[float]:
        out = [0.0] * (B * N * D)
        if len(w) < N * N:
            # fallback: local smoothing if no full matrix supplied
            w = [1.0 if i == j else 0.0 for i in range(N) for j in range(N)]
        for b in range(B):
            for n in range(N):
                for d in range(D):
                    base_idx = (b * N + n) * D + d
                    acc = x[base_idx] * (1.0 - gamma)
                    total_w = 0.0
                    for m in range(N):
                        wm = w[n * N + m]
                        total_w += abs(wm)
                        acc += gamma * wm * x[(b * N + m) * D + d]
                    norm = max(1.0, total_w)
                    out[base_idx] = max(-sigma, min(sigma, acc / norm))
        return out

    def energy_gated_scheduler(self, energy: list[float], nutrient: list[float], *, threshold: float, sleep_decay: float, nutrient_recovery: float) -> dict[str, Any]:
        flags: list[int] = []
        indices: list[int] = []
        for i, (e, n) in enumerate(zip(energy, nutrient)):
            active = 1 if (e + n) >= threshold else 0
            flags.append(active)
            if active:
                indices.append(i)
            else:
                energy[i] = max(0.0, e * (1.0 - sleep_decay))
                nutrient[i] = min(1.0, n + nutrient_recovery)
        return {"active_flags": flags, "active_indices": indices, "active_count": len(indices), "energy": energy, "nutrient": nutrient}

    def resonant_field_step(self, state: list[float], velocity: list[float], drive: list[float], energy: list[float], neighbors: list[int], weights: list[float], *, N: int, K: int, dt: float, damping: float, coupling: float, inertia: float, clamp_abs: float) -> dict[str, list[float]]:
        next_state = state[:]
        next_velocity = velocity[:]
        for i in range(N):
            coupled = 0.0
            for k in range(K):
                j = neighbors[i * K + k]
                if 0 <= j < N:
                    coupled += weights[i * K + k] * (state[j] - state[i])
            acc = drive[i] + coupling * coupled - damping * velocity[i]
            next_velocity[i] = velocity[i] * inertia + acc * dt
            next_state[i] = max(-clamp_abs, min(clamp_abs, state[i] + next_velocity[i] * dt))
            energy[i] = min(1.0, max(0.0, energy[i] + abs(next_velocity[i]) * 0.001))
        return {"state": next_state, "velocity": next_velocity, "energy": energy}

    def morphogenetic_rule_step(self, cell_type: list[int], nutrient: list[float], energy: list[float], potential: list[float], rule_in_type: list[int], rule_min_nutrient: list[float], rule_min_energy: list[float], rule_out_type: list[int], rule_delta_potential: list[float], *, nutrient_cost: float) -> dict[str, Any]:
        R = len(rule_in_type)
        for i, t in enumerate(cell_type):
            for r in range(R):
                if t == rule_in_type[r] and nutrient[i] >= rule_min_nutrient[r] and energy[i] >= rule_min_energy[r]:
                    cell_type[i] = rule_out_type[r]
                    potential[i] += rule_delta_potential[r]
                    nutrient[i] = max(0.0, nutrient[i] - nutrient_cost)
                    break
        return {"cell_type": cell_type, "nutrient": nutrient, "energy": energy, "potential": potential}

    def proto_segmented_sum(self, activations: list[float], indices: list[int], *, E: int, T: int) -> dict[str, Any]:
        sums = [0.0] * (E * T)
        counts = [0] * T
        for e in range(E):
            for i, t in enumerate(indices):
                if 0 <= t < T:
                    sums[e * T + t] += activations[i * E + e]
                    if e == 0:
                        counts[t] += 1
        return {"proto_sums": sums, "proto_counts": counts}

    def proto_update(self, prototypes: list[float], proto_sums: list[float], proto_counts: list[int], *, learning_rate: float, E: int, T: int) -> list[float]:
        out = prototypes[:]
        for e in range(E):
            for t in range(T):
                c = max(1, proto_counts[t])
                target = proto_sums[e * T + t] / c
                idx = e * T + t
                out[idx] = out[idx] * (1.0 - learning_rate) + target * learning_rate
        return out


class CipherCoreGpuExecutor:
    """Enterprise Executor für CC_OpenCl.dll.

    Unter Windows lädt er die DLL, unter Linux libCC_OpenCL.so und bindet
    Kernels. Wenn kein nativer Treiber oder kein OpenCL-Gerät verfügbar ist,
    bleibt dieselbe Planungs-/Profilingoberfläche mit deterministischer
    CPU-Referenz aktiv.
    """

    def __init__(self, dll: Path | None = None, gpu_index: int = 0, *, force_cpu: bool = False) -> None:
        self.dll = Path(dll) if dll else default_driver_path()
        self.gpu_index = gpu_index
        self.force_cpu = force_cpu
        self.report = inspect_driver(self.dll, load=not force_cpu, gpu_index=gpu_index)
        self.cpu = CpuFallbackKernelPack()
        self.lib: Any | None = None
        if not force_cpu and self.dll.exists() and _is_loadable_native_driver(self.dll):
            try:
                self.lib = C.CDLL(str(self.dll))
                self._bind()
            except OSError as exc:
                self.report.notes.append(f"Real-Executor deaktiviert: {exc}")
                self.lib = None

    @property
    def real_enabled(self) -> bool:
        return self.lib is not None and not self.force_cpu

    def _bind(self) -> None:
        assert self.lib is not None
        # Core
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
        # Enterprise kernels
        self._bind_optional("execute_fused_diffusion_on_gpu", [C.c_int, C.c_void_p, C.c_void_p, C.c_void_p, C.c_int, C.c_int, C.c_int, C.c_float, C.c_float])
        self._bind_optional("execute_energy_gated_scheduler_gpu", [C.c_int, C.c_void_p, C.c_void_p, C.c_void_p, C.c_void_p, C.c_void_p, C.c_int, C.c_float, C.c_float, C.c_float])
        self._bind_optional("execute_resonant_field_step_gpu", [C.c_int, C.c_void_p, C.c_void_p, C.c_void_p, C.c_void_p, C.c_void_p, C.c_void_p, C.c_int, C.c_int, C.c_float, C.c_float, C.c_float, C.c_float, C.c_float])
        self._bind_optional("execute_morphogenetic_rule_step_gpu", [C.c_int, C.c_void_p, C.c_void_p, C.c_void_p, C.c_void_p, C.c_void_p, C.c_void_p, C.c_void_p, C.c_void_p, C.c_int, C.c_int, C.c_float])
        self._bind_optional("execute_proto_segmented_sum_gpu", [C.c_int, C.c_void_p, C.c_void_p, C.c_void_p, C.c_void_p, C.c_int, C.c_int, C.c_int])
        self._bind_optional("execute_proto_update_step_gpu", [C.c_int, C.c_void_p, C.c_void_p, C.c_void_p, C.c_float, C.c_int, C.c_int])
        self._bind_optional("subqg_simulation_step_host_fields", [C.c_int, C.c_int, C.POINTER(C.c_float), C.POINTER(C.c_float), C.POINTER(C.c_float), C.POINTER(C.c_float), C.POINTER(C.c_float), C.POINTER(C.c_float), C.POINTER(C.c_float), C.POINTER(C.c_float), C.c_float, C.c_float, C.c_float])
        self._bind_optional("subqg_simulation_step_native_fields", [C.c_int, C.c_float, C.c_float, C.c_float])

    def _bind_optional(self, name: str, argtypes: list[Any]) -> None:
        if self.lib is None:
            return
        try:
            fn = getattr(self.lib, name)
            fn.argtypes = argtypes
            fn.restype = C.c_int
        except AttributeError:
            pass

    def dispatch_fused_diffusion(self, x: list[float], w: list[float], *, B: int, N: int, D: int, gamma: float, sigma: float) -> tuple[list[float], DispatchProfile]:
        """Execute fused diffusion via DLL when available, otherwise CPU reference.

        This is the first real hot-path dispatch with full upload/kernel/readback
        profiling. It intentionally keeps CPU comparison available for
        differential testing.
        """
        t_total = perf_counter()
        t0 = perf_counter()
        cpu_ref = self.cpu.fused_diffusion(x[:], w[:], B=B, N=N, D=D, gamma=gamma, sigma=sigma)
        cpu_ms = (perf_counter() - t0) * 1000.0
        if not self.real_enabled or self.lib is None or not hasattr(self.lib, "execute_fused_diffusion_on_gpu"):
            total_ms = (perf_counter() - t_total) * 1000.0
            return cpu_ref, DispatchProfile("fused_diffusion", "cpu-reference", True, kernel_ms=cpu_ms, total_ms=total_ms, cpu_reference_ms=cpu_ms, detail="real DLL dispatch unavailable")
        mgr = RealGpuBufferManager(self.lib, self.gpu_index)
        try:
            try:
                init_ok = self.lib.initialize_gpu(self.gpu_index)
                if not init_ok:
                    raise GpuExecutionError("initialize_gpu failed")
                t_upload = perf_counter()
                x_buf = mgr.upload_f32(x, "x")
                w_buf = mgr.upload_f32(w, "w")
                out_buf = mgr.alloc(len(x) * C.sizeof(C.c_float), "out")
                upload_ms = (perf_counter() - t_upload) * 1000.0
                t_kernel = perf_counter()
                ok = self.lib.execute_fused_diffusion_on_gpu(self.gpu_index, C.c_void_p(x_buf.handle), C.c_void_p(w_buf.handle), C.c_void_p(out_buf.handle), C.c_int(B), C.c_int(N), C.c_int(D), C.c_float(gamma), C.c_float(sigma))
                kernel_ms = (perf_counter() - t_kernel) * 1000.0
                if not ok:
                    raise GpuExecutionError("execute_fused_diffusion_on_gpu failed")
                t_download = perf_counter()
                gpu_out = mgr.download_f32(out_buf, len(x))
                download_ms = (perf_counter() - t_download) * 1000.0
                max_err = max((abs(a - b) for a, b in zip(cpu_ref, gpu_out)), default=0.0)
                return gpu_out, DispatchProfile("fused_diffusion", "gpu-real", max_err < 1e-3, upload_ms=upload_ms, kernel_ms=kernel_ms, download_ms=download_ms, total_ms=(perf_counter() - t_total) * 1000.0, cpu_reference_ms=cpu_ms, max_abs_error=max_err, detail=f"real native dispatch via {self.dll.name}")
            except Exception as exc:
                total_ms = (perf_counter() - t_total) * 1000.0
                return cpu_ref, DispatchProfile("fused_diffusion", "cpu-fallback-after-native-error", True, kernel_ms=cpu_ms, total_ms=total_ms, cpu_reference_ms=cpu_ms, detail=f"native dispatch unavailable or failed: {exc}")
        finally:
            mgr.close()
            try:
                self.lib.finish_gpu(self.gpu_index)
                self.lib.shutdown_gpu(self.gpu_index)
            except Exception:
                pass

    def demo(self, *, size: int = 256) -> dict[str, Any]:
        profiles: list[DispatchProfile] = []
        # 1 fused diffusion
        B, N, D = 1, max(4, min(64, int(math.sqrt(size)))), 4
        total = B * N * D
        x = [((i % 17) / 17.0) for i in range(total)]
        w = [1.0 if i == j else 0.1 for i in range(N) for j in range(N)]
        out, fused_profile = self.dispatch_fused_diffusion(x, w, B=B, N=N, D=D, gamma=0.3, sigma=2.0)
        profiles.append(fused_profile.as_dict())
        # 2 scheduler
        energy = [((i * 7) % 100) / 100.0 for i in range(size)]
        nutrient = [((i * 13) % 100) / 100.0 for i in range(size)]
        t0 = perf_counter()
        sched = self.cpu.energy_gated_scheduler(energy[:], nutrient[:], threshold=0.9, sleep_decay=0.02, nutrient_recovery=0.01)
        cpu_ms = (perf_counter() - t0) * 1000
        profiles.append(DispatchProfile("energy_gated_scheduler", "cpu-reference" if not self.real_enabled else "gpu-planned", True, total_ms=cpu_ms, kernel_ms=cpu_ms, cpu_reference_ms=cpu_ms, detail=f"active={sched['active_count']}").as_dict())
        # 3 proto
        E, T, M = 8, 5, size
        acts = [((i * 3) % 31) / 31.0 for i in range(M * E)]
        idx = [i % T for i in range(M)]
        t0 = perf_counter()
        seg = self.cpu.proto_segmented_sum(acts, idx, E=E, T=T)
        cpu_ms = (perf_counter() - t0) * 1000
        profiles.append(DispatchProfile("proto_segmented_sum", "cpu-reference" if not self.real_enabled else "gpu-planned", True, total_ms=cpu_ms, kernel_ms=cpu_ms, cpu_reference_ms=cpu_ms, detail=f"counts={seg['proto_counts']}").as_dict())
        return {
            "ok": True,
            "driver": self.report.as_dict(),
            "real_enabled": self.real_enabled,
            "profiles": profiles,
            "recommendation": "Windows: --backend gpu --dll driver/build/CC_OpenCl.dll; Linux: --backend gpu --dll driver/build/libCC_OpenCL.so; ohne ladbaren OpenCL-Kontext bleibt CPU-Differentialreferenz aktiv.",
        }


def build_execution_plan(source: Path | None = None, *, dll: Path | None = None) -> dict[str, Any]:
    report = inspect_driver(dll or default_driver_path(source.parent if source else None), load=False)
    plan = {
        "format": "keim-gpu-driver-execution-plan-v1",
        "driver": report.as_dict(),
        "dispatch_rules": [],
        "fallback_policy": "cpu-reference-on-missing-driver-or-symbol",
        "profile_metrics": ["upload_ms", "kernel_ms", "download_ms", "total_ms", "speedup", "max_abs_error"],
    }
    for spec in KERNEL_SPECS:
        plan["dispatch_rules"].append({
            "keim_kernel": spec.name,
            "driver_symbol": spec.symbol,
            "available": spec.name in report.kernels_available,
            "category": spec.category,
            "deterministic": spec.deterministic,
            "arg_kinds": list(spec.arg_kinds),
        })
    return plan


def run_driver_demo(dll: Path | None = None, *, out: Path | None = None, size: int = 256, force_cpu: bool = False) -> dict[str, Any]:
    executor = CipherCoreGpuExecutor(dll=dll, force_cpu=force_cpu)
    payload = executor.demo(size=size)
    if out:
        out.mkdir(parents=True, exist_ok=True)
        (out / "gpu_driver_report.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "gpu_execution_plan.json").write_text(json.dumps(build_execution_plan(dll=Path(payload["driver"]["dll"])), ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "README_GPU_DRIVER_EXECUTION.txt").write_text(
            "Keim v7.6 GPU Driver Execution\n\n"
            "Dieses Artefakt zeigt, ob driver/build/CC_OpenCl.dll erkannt wird,\n"
            "welche Kernel dispatchfähig sind und welche CPU-Differentialreferenzen\n"
            "für CI/Entwicklung gelaufen sind.\n\n"
            "Echter GPU-Hotpath:\n"
            "  Windows: python -m keim gpu-driver-demo --dll driver/build/CC_OpenCl.dll --out build/gpu_driver --json\n"
            "  Linux:   python -m keim gpu-driver-demo --dll driver/build/libCC_OpenCL.so --out build/gpu_driver --json\n"
            "  Run:     python -m keim run examples/bench.keim --backend gpu --dll <driver-artifact> --driver-smoke\n",
            encoding="utf-8",
        )
    return payload


def status_payload(dll: Path | None = None) -> dict[str, Any]:
    report = inspect_driver(dll or default_driver_path(), load=False)
    return {
        "version": "7.6.4",
        "feature": "GPU Driver Execution",
        "driver": report.as_dict(),
        "kernels": [s.as_dict() for s in KERNEL_SPECS],
        "backend_modes": ["gpu", "hybrid", "auto"],
        "enterprise_guarantees": [
            "auto discovery driver/build/CC_OpenCl.dll and driver/build/libCC_OpenCL.so",
            "portable symbol scan",
            "real ctypes dispatch on Windows DLL and Linux .so",
            "deterministic CPU fallback and differential test surface",
            "profiling report for upload/kernel/download/total timings",
        ],
    }
