from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .ast_nodes import Program, WorldDecl, FieldDecl, MemoryDecl, TrailDecl
from .bytecode import compile_bytecode
from .optimizer import analyze_optimization


@dataclass(slots=True, frozen=True)
class PlanOp:
    name: str
    args: tuple[str, ...]
    note: str


@dataclass(slots=True, frozen=True)
class Plan:
    ops: tuple[PlanOp, ...]


def compile_plan(program: Program) -> Plan:
    bp = compile_bytecode(program)
    return Plan(tuple(PlanOp(op.opcode.value.lower(), tuple(str(a) for a in op.args), op.note) for op in bp.ops))


def compile_kernel_plan(program: Program) -> dict[str, Any]:
    bytecode = compile_bytecode(program)
    opt = analyze_optimization(bytecode)
    return {
        "source": program.source_name,
        "ops": [op.as_dict() for op in bytecode.ops],
        "stats": bytecode.stats(),
        "bundles": [b.as_dict() for b in opt.bundles],
        "driver_strategy": [
            "Welt/Felder im VRAM halten",
            "FIELD_CHANGE und FIELD_TRAIL_COUPLE als elementwise/gather-Batch bündeln",
            "FIELD_TRAIL_EMIT und STRENGTHEN_TRAIL als segmented scatter vorbereiten",
            "DIFFUSE_TRAIL als fused diffusion pro Spur",
            "FOLLOW/AVOID_TRAIL als Migrationskernel",
            "SHOW nur gezielt lesen, um Host-Device-Kopien zu reduzieren",
        ],
    }


def _kernel_mapping_for_opcode(opcode: str) -> dict[str, Any]:
    elementwise = {
        "FIELD_CHANGE", "FIELD_COMPUTE", "MEMORY_CHANGE",
        "FOLLOW_TRAIL", "AVOID_TRAIL", "WANDER", "REST",
    }
    scatter = {"FIELD_TRAIL_EMIT", "STRENGTHEN_TRAIL"}
    grid = {"DIFFUSE_TRAIL"}
    io = {"FILE_TABLE_IO", "WEB_REQUEST", "EXPORT_IMAGE", "START_DASHBOARD"}

    if opcode in elementwise:
        return {
            "parallel": True,
            "class": "agent_elementwise",
            "target": "native_soa_or_gpu_kernel",
            "hazard": "none_or_read_only",
            "jit": opcode == "FIELD_COMPUTE",
        }
    if opcode in scatter:
        return {
            "parallel": True,
            "class": "segmented_scatter",
            "target": "gpu_atomic_or_sort_reduce",
            "hazard": "many_agents_same_cell",
            "resolution": "segmented_sum_or_atomic_add_then_clamp",
            "jit": False,
        }
    if opcode in grid:
        return {
            "parallel": True,
            "class": "grid_stencil",
            "target": "gpu_shared_memory_tile",
            "hazard": "neighbor_reads",
            "resolution": "double_buffer_or_pingpong",
            "jit": False,
        }
    if opcode in io:
        return {
            "parallel": False,
            "class": "host_io_boundary",
            "target": "system_module",
            "hazard": "side_effect_order",
            "resolution": "execute_on_host_between_kernel_bundles",
            "jit": False,
        }
    return {
        "parallel": False,
        "class": "control_or_dynamic_state",
        "target": "host_vm_until_lowered",
        "hazard": "semantic_ordering",
        "resolution": "barrier",
        "jit": False,
    }


def compile_kernel_abi(program: Program) -> dict[str, Any]:
    """v1.2: stabiler JSON-Kontrakt für native C++-/GPU-Kernel.

    v1 bleibt als Kompatibilitätsfeld erhalten. v1.2 ergänzt:
    - SoA-Agentenlayout
    - Kernel-Bundles mit Parallelisierbarkeitsmarkern
    - JIT-Haken für mathematische Feld-Ausdrücke
    - externe GPU-Treiber-ABI ohne Einbettung des Treibers
    """

    bp = compile_bytecode(program)
    opt = analyze_optimization(bp)
    world = next((decl for decl in program.declarations if isinstance(decl, WorldDecl)), None)
    fields = [decl for decl in program.declarations if isinstance(decl, FieldDecl)]
    memory = [decl for decl in program.declarations if isinstance(decl, MemoryDecl)]
    trails = [decl.name for decl in program.declarations if isinstance(decl, TrailDecl)]

    agents = world.agents if world else 0
    width = world.width if world else 0
    height = world.height if world else 0
    cells = width * height

    hazards = []
    mapped_ops = []
    for op in bp.ops:
        opcode = op.opcode.value
        mapping = _kernel_mapping_for_opcode(opcode)
        mapped_ops.append({
            **op.as_dict(),
            "kernel_mapping": mapping,
            "abi_block": "host" if not mapping["parallel"] else mapping["class"],
        })
        if opcode in {"FIELD_TRAIL_EMIT", "STRENGTHEN_TRAIL"}:
            hazards.append({
                "pc": op.pc,
                "opcode": opcode,
                "hazard": "many_agents_same_cell",
                "resolution": "segmented_sum_or_atomic_add_then_clamp",
                "determinism": "CPU-equivalent for nonnegative additions",
            })

    kernel_bundles = []
    current: dict[str, Any] | None = None
    for mop in mapped_ops:
        km = mop["kernel_mapping"]
        if km["parallel"]:
            key = (km["class"], km["target"], km.get("hazard"))
            if current and current["key"] == key:
                current["ops"].append(mop["pc"])
            else:
                if current:
                    kernel_bundles.append(current)
                current = {
                    "key": key,
                    "class": km["class"],
                    "target": km["target"],
                    "parallel": True,
                    "ops": [mop["pc"]],
                    "barrier_after": km["class"] in {"segmented_scatter", "grid_stencil"},
                }
        else:
            if current:
                kernel_bundles.append(current)
                current = None
            kernel_bundles.append({
                "key": ("host", mop["pc"]),
                "class": km["class"],
                "target": km["target"],
                "parallel": False,
                "ops": [mop["pc"]],
                "barrier_after": True,
            })
    if current:
        kernel_bundles.append(current)
    for i, bundle in enumerate(kernel_bundles):
        bundle["id"] = f"k{i:03d}"
        bundle.pop("key", None)

    return {
        "format": "keim-kernel-abi-v1",
        "format_version": "1.2",
        "source": program.source_name,
        "world": {
            "agents": agents,
            "width": width,
            "height": height,
            "cells": cells,
            "agent_density": (agents / cells) if cells else 0.0,
        },
        "layout": {
            "agents": {
                "kind": "SoA",
                "vram_ready": True,
                "buffers": {
                    "agent_x": {"dtype": "int32", "shape": ["N"], "mutability": "rw"},
                    "agent_y": {"dtype": "int32", "shape": ["N"], "mutability": "rw"},
                    "agent_energy": {"dtype": "float32", "shape": ["N"], "mutability": "rw"},
                    "agent_class_id": {"dtype": "uint32", "shape": ["N"], "mutability": "rw"},
                    "agent_alive": {"dtype": "uint8", "shape": ["N"], "mutability": "rw"},
                },
            },
            "driver": {
                "external": True,
                "required_symbols_any": [
                    "shadow_init/shadow_cycle",
                    "subqg_set_multifield_state",
                ],
                "embedding": "runtime_dlopen_or_LoadLibrary",
            },
        },
        "buffers": {
            "agent_x": {"dtype": "int32", "shape": ["N"], "mutability": "rw"},
            "agent_y": {"dtype": "int32", "shape": ["N"], "mutability": "rw"},
            "fields": {decl.name: {"dtype": "float32" if decl.kind == "zahl" else decl.kind, "shape": ["N"], "mutability": "rw"} for decl in fields},
            "trails": {name: {"dtype": "float32", "shape": ["W*H"], "mutability": "rw"} for name in trails},
            "trail_sources": {name: {"dtype": "float32", "shape": ["W*H"], "mutability": "ro"} for name in trails},
            "memory": {decl.name: {"dtype": "float32" if decl.kind == "zahl" else decl.kind, "shape": [], "mutability": "rw"} for decl in memory},
            "mask": {"dtype": "uint8", "shape": ["N"], "mutability": "scratch"},
            "scatter_accum": {"dtype": "float32", "shape": ["W*H"], "mutability": "scratch"},
        },
        "launch_groups": [bundle.as_dict() for bundle in opt.bundles],
        "kernel_bundles_v12": kernel_bundles,
        "jit": {
            "abi": "keim-jit-abi-v1",
            "entrypoints": [
                "keim_jit_compile_affine2",
                "keim_jit_execute_affine2",
                "keim_jit_destroy",
            ],
            "current_lowering": "affine2_clamp",
            "future_lowering": "llvm_or_platform_codegen",
        },
        "hazards": hazards,
        "validation": {
            "reference_backend": "segmented",
            "native_hotspot_backend": "keim_run_agent_program + keim_run_numeric_program",
            "float_tolerance": 1e-6,
            "food_hits_exact": True,
            "rng_policy": "movement remains host-deterministic until GPU RNG stream is specified",
            "expression_policy": "FIELD_COMPUTE expressions are marked jit=true when scalar-safe",
            "determinism_check": "tests compare Python clamp/mask/agent kernels against C++ SoA kernels",
        },
        "ops": mapped_ops,
    }
