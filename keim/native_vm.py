from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import ctypes as C
import platform
import struct


class NativeVmError(RuntimeError):
    pass


@dataclass(slots=True, frozen=True)
class NativeVmInfo:
    path: Path
    version: int
    loaded: bool


class _Status(C.Structure):
    _fields_ = [
        ("ok", C.c_uint32),
        ("pc", C.c_uint32),
        ("message", C.c_char * 128),
    ]


class NativeNumericVm:
    """ctypes-Brücke zur C++ Native VM.

    v4.1 hebt den früheren Hotspot-Prototyp auf eine belastbare ABI:
    - flache numerische Register-VM
    - VRAM-ready Agent-SoA
    - native sim.mathe-Kerne
    - JIT-Handle für spezialisierte Ausdruckskerne
    - optionaler Loader für den externen GPU-C-Treiber
    """

    OP_FIELD_ADD_CLAMP = 1
    OP_MEMORY_ADD_CLAMP = 2
    OP_MASK_GT = 3
    OP_MASK_LT = 4
    OP_APPLY_MASKED_ADD_CLAMP = 5
    OP_AGENT_X_ADD_WRAP = 16
    OP_AGENT_Y_ADD_WRAP = 17
    OP_AGENT_ENERGY_ADD_CLAMP = 18
    OP_AGENT_ALIVE_MASK_GT = 19
    OP_AGENT_APPLY_MASK_ENERGY = 20
    OP_HALT = 255

    def __init__(self, library: str | Path) -> None:
        self.path = Path(library)
        if not self.path.exists():
            raise NativeVmError(f"Native-VM-Bibliothek nicht gefunden: {self.path}")
        self.lib = C.CDLL(str(self.path))
        self._bind()

    def _bind(self) -> None:
        L = self.lib
        L.keim_native_version.argtypes = []
        L.keim_native_version.restype = C.c_uint32

        L.keim_field_add_clamp.argtypes = [C.POINTER(C.c_float), C.c_uint32, C.c_float]
        L.keim_field_add_clamp.restype = C.c_uint32
        L.keim_field_add_clamp_masked.argtypes = [C.POINTER(C.c_float), C.POINTER(C.c_uint8), C.c_uint32, C.c_float]
        L.keim_field_add_clamp_masked.restype = C.c_uint32
        L.keim_int_field_add.argtypes = [C.POINTER(C.c_int32), C.c_uint32, C.c_int32, C.c_int32, C.c_int32]
        L.keim_int_field_add.restype = C.c_uint32
        L.keim_affine2_clamp.argtypes = [C.POINTER(C.c_float), C.POINTER(C.c_float), C.POINTER(C.c_float), C.c_uint32, C.c_float, C.c_float, C.c_float]
        L.keim_affine2_clamp.restype = C.c_uint32

        L.keim_run_numeric_program.argtypes = [
            C.POINTER(C.c_uint32), C.c_uint32,
            C.POINTER(C.POINTER(C.c_float)), C.POINTER(C.c_uint32), C.c_uint32,
            C.POINTER(C.c_float), C.c_uint32,
            C.POINTER(C.POINTER(C.c_uint8)), C.c_uint32,
            C.POINTER(_Status),
        ]
        L.keim_run_numeric_program.restype = C.c_uint32

        L.keim_agent_soa_create.argtypes = [C.c_uint32, C.c_int32, C.c_int32]
        L.keim_agent_soa_create.restype = C.c_void_p
        L.keim_agent_soa_destroy.argtypes = [C.c_void_p]
        L.keim_agent_soa_destroy.restype = None
        L.keim_agent_soa_resize.argtypes = [C.c_void_p, C.c_uint32]
        L.keim_agent_soa_resize.restype = C.c_uint32
        L.keim_agent_soa_import.argtypes = [
            C.c_void_p, C.POINTER(C.c_int32), C.POINTER(C.c_int32),
            C.POINTER(C.c_float), C.POINTER(C.c_uint8), C.c_uint32
        ]
        L.keim_agent_soa_import.restype = C.c_uint32
        L.keim_agent_soa_export.argtypes = [
            C.c_void_p, C.POINTER(C.c_int32), C.POINTER(C.c_int32),
            C.POINTER(C.c_float), C.POINTER(C.c_uint8), C.c_uint32
        ]
        L.keim_agent_soa_export.restype = C.c_uint32
        L.keim_run_agent_program.argtypes = [C.c_void_p, C.POINTER(C.c_uint32), C.c_uint32, C.POINTER(_Status)]
        L.keim_run_agent_program.restype = C.c_uint32

        L.keim_noise2.argtypes = [C.c_float, C.c_float, C.c_uint32]
        L.keim_noise2.restype = C.c_float
        L.keim_noise2_array.argtypes = [C.POINTER(C.c_float), C.POINTER(C.c_float), C.POINTER(C.c_float), C.c_uint32, C.c_uint32]
        L.keim_noise2_array.restype = C.c_uint32
        L.keim_vec2_add.argtypes = [
            C.POINTER(C.c_float), C.POINTER(C.c_float), C.POINTER(C.c_float), C.POINTER(C.c_float),
            C.POINTER(C.c_float), C.POINTER(C.c_float), C.c_uint32
        ]
        L.keim_vec2_add.restype = C.c_uint32
        L.keim_astar_grid.argtypes = [
            C.c_int32, C.c_int32, C.c_int32, C.c_int32, C.c_int32, C.c_int32,
            C.POINTER(C.c_float), C.POINTER(C.c_int32), C.POINTER(C.c_int32), C.c_uint32
        ]
        L.keim_astar_grid.restype = C.c_uint32

        L.keim_jit_compile_affine2.argtypes = [C.c_float, C.c_float, C.c_float]
        L.keim_jit_compile_affine2.restype = C.c_void_p
        L.keim_jit_destroy.argtypes = [C.c_void_p]
        L.keim_jit_destroy.restype = None
        L.keim_jit_execute_affine2.argtypes = [C.c_void_p, C.POINTER(C.c_float), C.POINTER(C.c_float), C.POINTER(C.c_float), C.c_uint32]
        L.keim_jit_execute_affine2.restype = C.c_uint32

        L.keim_gpu_driver_load.argtypes = [C.c_char_p]
        L.keim_gpu_driver_load.restype = C.c_void_p
        L.keim_gpu_driver_unload.argtypes = [C.c_void_p]
        L.keim_gpu_driver_unload.restype = None
        L.keim_gpu_driver_ready.argtypes = [C.c_void_p]
        L.keim_gpu_driver_ready.restype = C.c_uint32
        L.keim_gpu_shadow_init.argtypes = [C.c_void_p, C.c_int, C.c_int, C.c_int, C.c_int, C.c_int, C.c_int]
        L.keim_gpu_shadow_init.restype = C.c_uint32
        L.keim_gpu_shadow_cycle.argtypes = [C.c_void_p, C.c_int, C.c_int, C.c_int]
        L.keim_gpu_shadow_cycle.restype = C.c_uint32

    def info(self) -> NativeVmInfo:
        return NativeVmInfo(path=self.path, version=int(self.lib.keim_native_version()), loaded=True)

    @staticmethod
    def _float_bits(v: float) -> int:
        return struct.unpack("<I", struct.pack("<f", float(v)))[0]

    def field_add_clamp(self, values: list[float], delta: float) -> list[float]:
        arr = (C.c_float * len(values))(*[float(v) for v in values])
        ok = self.lib.keim_field_add_clamp(arr, C.c_uint32(len(values)), C.c_float(delta))
        if not ok:
            raise NativeVmError("keim_field_add_clamp fehlgeschlagen")
        return [float(v) for v in arr]

    def field_add_clamp_masked(self, values: list[float], mask: list[bool], delta: float) -> list[float]:
        if len(values) != len(mask):
            raise NativeVmError("values und mask haben unterschiedliche Länge")
        arr = (C.c_float * len(values))(*[float(v) for v in values])
        mask_arr = (C.c_uint8 * len(mask))(*[1 if v else 0 for v in mask])
        ok = self.lib.keim_field_add_clamp_masked(arr, mask_arr, C.c_uint32(len(values)), C.c_float(delta))
        if not ok:
            raise NativeVmError("keim_field_add_clamp_masked fehlgeschlagen")
        return [float(v) for v in arr]

    def int_field_add(self, values: list[int], delta: int, min_value: int = -2_147_483_648, max_value: int = 2_147_483_647) -> list[int]:
        arr = (C.c_int32 * len(values))(*[int(v) for v in values])
        ok = self.lib.keim_int_field_add(arr, C.c_uint32(len(values)), C.c_int32(delta), C.c_int32(min_value), C.c_int32(max_value))
        if not ok:
            raise NativeVmError("keim_int_field_add fehlgeschlagen")
        return [int(v) for v in arr]

    def affine2_clamp(self, x: list[float], y: list[float], a: float, b: float, c: float) -> list[float]:
        if len(x) != len(y):
            raise NativeVmError("x und y haben unterschiedliche Länge")
        xa = (C.c_float * len(x))(*[float(v) for v in x])
        ya = (C.c_float * len(y))(*[float(v) for v in y])
        out = (C.c_float * len(x))()
        ok = self.lib.keim_affine2_clamp(xa, ya, out, C.c_uint32(len(x)), C.c_float(a), C.c_float(b), C.c_float(c))
        if not ok:
            raise NativeVmError("keim_affine2_clamp fehlgeschlagen")
        return [float(v) for v in out]

    def run_numeric_program(self, fields: list[list[float]], ops: list[tuple[int, int, int, float]], memories: list[float] | None = None, masks: list[list[bool]] | None = None) -> tuple[list[list[float]], list[float], list[list[bool]]]:
        memories = list(memories or [])
        masks = [list(m) for m in (masks or [])]
        field_arrays = [(C.c_float * len(v))(*[float(x) for x in v]) for v in fields]
        field_ptrs = (C.POINTER(C.c_float) * len(field_arrays))(*[C.cast(a, C.POINTER(C.c_float)) for a in field_arrays])
        field_lengths = (C.c_uint32 * len(field_arrays))(*[len(v) for v in fields])
        mem_arr = (C.c_float * len(memories))(*[float(x) for x in memories]) if memories else None
        mask_arrays = [(C.c_uint8 * len(m))(*[1 if x else 0 for x in m]) for m in masks]
        mask_ptrs = (C.POINTER(C.c_uint8) * len(mask_arrays))(*[C.cast(a, C.POINTER(C.c_uint8)) for a in mask_arrays]) if mask_arrays else None
        words: list[int] = []
        for op, a, b, imm in ops:
            words += [int(op), int(a), int(b), self._float_bits(float(imm))]
        prog = (C.c_uint32 * len(words))(*words)
        st = _Status()
        ok = self.lib.keim_run_numeric_program(
            prog, C.c_uint32(len(ops)), field_ptrs, field_lengths, C.c_uint32(len(fields)),
            mem_arr, C.c_uint32(len(memories)), mask_ptrs, C.c_uint32(len(masks)), C.byref(st)
        )
        if not ok:
            raise NativeVmError(f"numeric program pc={st.pc}: {bytes(st.message).split(b'\0',1)[0].decode(errors='replace')}")
        out_fields = [[float(arr[i]) for i in range(len(fields[j]))] for j, arr in enumerate(field_arrays)]
        out_mems = [float(mem_arr[i]) for i in range(len(memories))] if mem_arr is not None else []
        out_masks = [[bool(arr[i]) for i in range(len(masks[j]))] for j, arr in enumerate(mask_arrays)]
        return out_fields, out_mems, out_masks

    def agent_store(self, capacity: int, width: int, height: int) -> "NativeAgentStore":
        return NativeAgentStore(self, capacity, width, height)

    def noise2(self, x: float, y: float, seed: int = 0) -> float:
        return float(self.lib.keim_noise2(C.c_float(x), C.c_float(y), C.c_uint32(seed)))

    def noise2_array(self, x: list[float], y: list[float], seed: int = 0) -> list[float]:
        if len(x) != len(y):
            raise NativeVmError("x und y haben unterschiedliche Länge")
        xa = (C.c_float * len(x))(*[float(v) for v in x])
        ya = (C.c_float * len(y))(*[float(v) for v in y])
        out = (C.c_float * len(x))()
        ok = self.lib.keim_noise2_array(xa, ya, out, C.c_uint32(len(x)), C.c_uint32(seed))
        if not ok:
            raise NativeVmError("noise2_array fehlgeschlagen")
        return [float(v) for v in out]

    def vec2_add(self, ax: list[float], ay: list[float], bx: list[float], by: list[float]) -> tuple[list[float], list[float]]:
        n = len(ax)
        if not (len(ay) == len(bx) == len(by) == n):
            raise NativeVmError("Vektorlisten haben unterschiedliche Länge")
        cax = (C.c_float * n)(*[float(v) for v in ax]); cay = (C.c_float * n)(*[float(v) for v in ay])
        cbx = (C.c_float * n)(*[float(v) for v in bx]); cby = (C.c_float * n)(*[float(v) for v in by])
        ox = (C.c_float * n)(); oy = (C.c_float * n)()
        ok = self.lib.keim_vec2_add(cax, cay, cbx, cby, ox, oy, C.c_uint32(n))
        if not ok:
            raise NativeVmError("vec2_add fehlgeschlagen")
        return [float(v) for v in ox], [float(v) for v in oy]

    def astar_grid(self, width: int, height: int, start: tuple[int, int], goal: tuple[int, int], cost: list[float] | None = None) -> list[tuple[int, int]]:
        max_path = max(1, width * height)
        cost_arr = (C.c_float * len(cost))(*[float(v) for v in cost]) if cost is not None else None
        ox = (C.c_int32 * max_path)(); oy = (C.c_int32 * max_path)()
        n = self.lib.keim_astar_grid(width, height, start[0], start[1], goal[0], goal[1], cost_arr, ox, oy, max_path)
        return [(int(ox[i]), int(oy[i])) for i in range(n)]

    def jit_affine2(self, a: float, b: float, c: float) -> "NativeJitAffine2":
        handle = self.lib.keim_jit_compile_affine2(C.c_float(a), C.c_float(b), C.c_float(c))
        if not handle:
            raise NativeVmError("JIT-Plan konnte nicht erzeugt werden")
        return NativeJitAffine2(self, handle)

    def load_gpu_driver(self, path: str | Path) -> "NativeGpuDriver":
        handle = self.lib.keim_gpu_driver_load(str(path).encode("utf-8"))
        if not handle:
            raise NativeVmError(f"GPU-Treiber konnte nicht geladen werden: {path}")
        return NativeGpuDriver(self, handle)


class NativeAgentStore:
    def __init__(self, vm: NativeNumericVm, capacity: int, width: int, height: int) -> None:
        self.vm = vm
        self.handle = vm.lib.keim_agent_soa_create(C.c_uint32(capacity), C.c_int32(width), C.c_int32(height))
        self.capacity = capacity
        if not self.handle:
            raise NativeVmError("Agent-SoA konnte nicht erzeugt werden")

    def close(self) -> None:
        if self.handle:
            self.vm.lib.keim_agent_soa_destroy(self.handle)
            self.handle = None

    def __enter__(self) -> "NativeAgentStore":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def resize(self, count: int) -> None:
        if not self.vm.lib.keim_agent_soa_resize(self.handle, C.c_uint32(count)):
            raise NativeVmError("Agent-SoA resize fehlgeschlagen")

    def import_state(self, x: list[int], y: list[int], energy: list[float], alive: list[bool] | None = None) -> None:
        n = len(x)
        if len(y) != n or len(energy) != n:
            raise NativeVmError("Agent-State-Arrays haben unterschiedliche Länge")
        alive = alive if alive is not None else [True] * n
        if len(alive) != n:
            raise NativeVmError("alive hat falsche Länge")
        xa = (C.c_int32 * n)(*[int(v) for v in x])
        ya = (C.c_int32 * n)(*[int(v) for v in y])
        ea = (C.c_float * n)(*[float(v) for v in energy])
        aa = (C.c_uint8 * n)(*[1 if v else 0 for v in alive])
        ok = self.vm.lib.keim_agent_soa_import(self.handle, xa, ya, ea, aa, C.c_uint32(n))
        if not ok:
            raise NativeVmError("Agent-SoA import fehlgeschlagen")

    def export_state(self, count: int | None = None) -> dict[str, list[int] | list[float] | list[bool]]:
        n = int(count or self.capacity)
        xa = (C.c_int32 * n)(); ya = (C.c_int32 * n)(); ea = (C.c_float * n)(); aa = (C.c_uint8 * n)()
        got = self.vm.lib.keim_agent_soa_export(self.handle, xa, ya, ea, aa, C.c_uint32(n))
        return {
            "x": [int(xa[i]) for i in range(got)],
            "y": [int(ya[i]) for i in range(got)],
            "energy": [float(ea[i]) for i in range(got)],
            "alive": [bool(aa[i]) for i in range(got)],
        }

    def run(self, ops: list[tuple[int, int, int, float]]) -> None:
        words: list[int] = []
        for op, a, b, imm in ops:
            words += [int(op), int(a), int(b), NativeNumericVm._float_bits(float(imm))]
        prog = (C.c_uint32 * len(words))(*words)
        st = _Status()
        ok = self.vm.lib.keim_run_agent_program(self.handle, prog, C.c_uint32(len(ops)), C.byref(st))
        if not ok:
            raise NativeVmError(f"agent program pc={st.pc}: {bytes(st.message).split(b'\0',1)[0].decode(errors='replace')}")


class NativeJitAffine2:
    def __init__(self, vm: NativeNumericVm, handle: int) -> None:
        self.vm = vm
        self.handle = handle

    def close(self) -> None:
        if self.handle:
            self.vm.lib.keim_jit_destroy(self.handle)
            self.handle = None

    def __enter__(self) -> "NativeJitAffine2":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def execute(self, x: list[float], y: list[float]) -> list[float]:
        if len(x) != len(y):
            raise NativeVmError("x und y haben unterschiedliche Länge")
        n = len(x)
        xa = (C.c_float * n)(*[float(v) for v in x])
        ya = (C.c_float * n)(*[float(v) for v in y])
        out = (C.c_float * n)()
        ok = self.vm.lib.keim_jit_execute_affine2(self.handle, xa, ya, out, C.c_uint32(n))
        if not ok:
            raise NativeVmError("JIT execute fehlgeschlagen")
        return [float(v) for v in out]


class NativeGpuDriver:
    def __init__(self, vm: NativeNumericVm, handle: int) -> None:
        self.vm = vm
        self.handle = handle

    def close(self) -> None:
        if self.handle:
            self.vm.lib.keim_gpu_driver_unload(self.handle)
            self.handle = None

    def __enter__(self) -> "NativeGpuDriver":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def ready(self) -> bool:
        return bool(self.vm.lib.keim_gpu_driver_ready(self.handle))

    def shadow_init(self, gpu_index: int, cells: int, channels: int, neighbors: int = 4, dreams: int = 1, action_vector_len: int = 0) -> bool:
        return bool(self.vm.lib.keim_gpu_shadow_init(self.handle, gpu_index, cells, channels, neighbors, dreams, action_vector_len))

    def shadow_cycle(self, gpu_index: int, cycles: int, mode: int = 0) -> bool:
        return bool(self.vm.lib.keim_gpu_shadow_cycle(self.handle, gpu_index, cycles, mode))


def default_native_library() -> Path:
    root = Path(__file__).resolve().parents[1]
    system = platform.system().lower()
    if system == "windows":
        return root / "build" / "native" / "keim_vm_native.dll"
    if system == "darwin":
        return root / "build" / "native" / "libkeim_vm_native.dylib"
    return root / "build" / "native" / "libkeim_vm_native.so"
