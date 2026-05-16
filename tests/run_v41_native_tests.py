from __future__ import annotations

from pathlib import Path
import math
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from keim.compiler import compile_kernel_abi
from keim.native_vm import NativeNumericVm, default_native_library, NativeVmError
from keim.parser import parse_source


def assert_close(xs, ys, eps=1e-6):
    assert len(xs) == len(ys), (xs, ys)
    for a, b in zip(xs, ys):
        assert abs(a - b) <= eps, (a, b, xs, ys)


def py_clamp(v: float) -> float:
    return max(0.0, min(1.0, v))


# Build native library if it does not exist yet.
lib = default_native_library()
if not lib.exists():
    subprocess.check_call([sys.executable, str(ROOT / "scripts" / "build_native_vm.py")], cwd=ROOT)

vm = NativeNumericVm(lib)
assert vm.info().version >= 410

# Numeric bytecode dispatcher determinism.
fields, memories, masks = vm.run_numeric_program(
    fields=[[0.1, 0.8, 0.95]],
    memories=[0.2],
    masks=[[False, False, False]],
    ops=[
        (NativeNumericVm.OP_FIELD_ADD_CLAMP, 0, 0, 0.1),
        (NativeNumericVm.OP_MASK_GT, 0, 0, 0.85),
        (NativeNumericVm.OP_APPLY_MASKED_ADD_CLAMP, 0, 0, -0.2),
        (NativeNumericVm.OP_MEMORY_ADD_CLAMP, 0, 0, 0.9),
    ],
)
assert_close(fields[0], [0.2, 0.7, 0.8])
assert_close(memories, [1.0])
assert masks[0] == [False, True, True]

# SoA agent dispatcher determinism.
with vm.agent_store(8, 5, 4) as agents:
    agents.import_state([0, 4, 2], [0, 3, 1], [0.2, 0.95, 0.5], [True, True, False])
    agents.run([
        (NativeNumericVm.OP_AGENT_X_ADD_WRAP, 2, 0, 0.0),
        (NativeNumericVm.OP_AGENT_Y_ADD_WRAP, 1, 1, 0.0),
        (NativeNumericVm.OP_AGENT_ENERGY_ADD_CLAMP, 0, 0, 0.1),
        (NativeNumericVm.OP_AGENT_ALIVE_MASK_GT, 0, 0, 0.9),
        (NativeNumericVm.OP_AGENT_APPLY_MASK_ENERGY, 0, 0, -0.5),
    ])
    st = agents.export_state(3)
    assert st["x"] == [2, 1, 2]
    assert st["y"] == [3, 2, 1]
    assert_close(st["energy"], [0.3, 0.5, 0.5])
    assert st["alive"] == [True, True, False]

# sim.mathe native battery.
noise = vm.noise2_array([0.0, 1.25, 2.5], [0.0, 3.5, 4.5], seed=42)
assert len(noise) == 3 and all(0.0 <= v <= 1.0 for v in noise)
vx, vy = vm.vec2_add([1, 2], [3, 4], [10, 20], [30, 40])
assert_close(vx, [11.0, 22.0])
assert_close(vy, [33.0, 44.0])
path = vm.astar_grid(4, 4, (0, 0), (3, 3), [0.0] * 16)
assert path[0] == (0, 0) and path[-1] == (3, 3)

# JIT hook determinism.
with vm.jit_affine2(0.5, 0.25, 0.1) as plan:
    out = plan.execute([0.0, 1.0], [1.0, 1.0])
assert_close(out, [0.35, 0.85])

# ABI v1.2 markers.
src = """
welt nativecheck mit 16 agenten groesse 8 8
feld energie startet bei 0.5
spur futter startet bei 0.0 quellen 1 diffundiert 0.1 zerfaellt 0.01
jede runde:
    energie waechst 0.1
    wenn energie > 0.5: energie sinkt 0.05
    spur futter breitet sich aus
"""
program = parse_source(src)
abi = compile_kernel_abi(program)
assert abi["format"] == "keim-kernel-abi-v1"
assert abi["format_version"] == "1.2"
assert abi["layout"]["agents"]["kind"] == "SoA"
assert any(bundle["parallel"] for bundle in abi["kernel_bundles_v12"])
assert "keim_jit_compile_affine2" in abi["jit"]["entrypoints"]

print("[Keim] v4.1 native bridge tests OK")
