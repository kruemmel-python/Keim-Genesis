from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ast_nodes import Program, WorldDecl
from .bytecode import OpCode, compile_bytecode
from .compiler import compile_kernel_abi
from .backends.driver import DriverLoadError, DriverProbe


@dataclass(slots=True, frozen=True)
class GpuValidationReport:
    source: str
    agents: int
    cells: int
    scatter_ops: int
    gather_ops: int
    motion_ops: int
    diffusion_ops: int
    estimated_atomic_contention: float
    required_symbols: tuple[str, ...]
    present_symbols: tuple[str, ...]
    missing_symbols: tuple[str, ...]
    smoke_ok: bool | None
    abi: dict[str, Any]
    notes: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.missing_symbols and self.smoke_ok is not False

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "ok": self.ok,
            "agents": self.agents,
            "cells": self.cells,
            "scatter_ops": self.scatter_ops,
            "gather_ops": self.gather_ops,
            "motion_ops": self.motion_ops,
            "diffusion_ops": self.diffusion_ops,
            "estimated_atomic_contention": self.estimated_atomic_contention,
            "required_symbols": list(self.required_symbols),
            "present_symbols": list(self.present_symbols),
            "missing_symbols": list(self.missing_symbols),
            "smoke_ok": self.smoke_ok,
            "abi_format": self.abi.get("format"),
            "notes": list(self.notes),
        }

    def format(self) -> str:
        lines = [
            "[Keim] GPU-Validierungsplan v1.2",
            f"  Quelle:      {self.source}",
            f"  Status:      {'OK' if self.ok else 'VORBEREITET/UNVOLLSTÄNDIG'}",
            f"  Agenten:     {self.agents}",
            f"  Zellen:      {self.cells}",
            f"  Scatter-Ops: {self.scatter_ops}",
            f"  Gather-Ops:  {self.gather_ops}",
            f"  Motion-Ops:  {self.motion_ops}",
            f"  Diffusion:   {self.diffusion_ops}",
            f"  Atomikdruck: {self.estimated_atomic_contention:.4f} Agenten/Zelle",
            f"  ABI:         {self.abi.get('format')}",
            "",
            "  Benötigte Treibersymbole:",
        ]
        for name in self.required_symbols:
            marker = "+" if name in self.present_symbols else "-"
            lines.append(f"    {marker} {name}")
        if self.smoke_ok is not None:
            lines.append(f"  Smoke-Test:  {'OK' if self.smoke_ok else 'FEHLER'}")
        lines.append("")
        lines.append("  Hinweise:")
        for note in self.notes:
            lines.append(f"    - {note}")
        return "\n".join(lines)


def validate_gpu_mapping(program: Program, *, dll: Path | None = None, gpu_index: int = 0, smoke: bool = False) -> GpuValidationReport:
    bp = compile_bytecode(program)
    abi = compile_kernel_abi(program)
    world = next((d for d in program.declarations if isinstance(d, WorldDecl)), None)
    agents = world.agents if world else 0
    cells = world.width * world.height if world else 0

    scatter_ops = sum(1 for op in bp.ops if op.opcode in {OpCode.FIELD_TRAIL_EMIT, OpCode.STRENGTHEN_TRAIL})
    gather_ops = sum(1 for op in bp.ops if op.opcode is OpCode.FIELD_TRAIL_COUPLE)
    motion_ops = sum(1 for op in bp.ops if op.opcode in {OpCode.FOLLOW_TRAIL, OpCode.AVOID_TRAIL})
    diffusion_ops = sum(1 for op in bp.ops if op.opcode is OpCode.DIFFUSE_TRAIL)

    required = [
        "initialize_gpu",
        "finish_gpu",
        "shutdown_gpu",
        "allocate_gpu_memory",
        "free_gpu_memory",
        "write_host_to_gpu_blocking",
        "read_gpu_to_host_blocking",
    ]
    if diffusion_ops:
        required.append("execute_fused_diffusion_on_gpu")
    if motion_ops or gather_ops:
        required.append("execute_resonant_field_step_gpu")
    if scatter_ops:
        required.append("execute_energy_gated_scheduler_gpu")

    present: tuple[str, ...] = ()
    smoke_ok: bool | None = None
    if dll is not None:
        try:
            probe = DriverProbe(dll, gpu_index=gpu_index).inspect(smoke=smoke)
            available = set(probe.available)
            present = tuple(name for name in required if name in available)
            smoke_ok = probe.smoke_ok
        except DriverLoadError:
            present = ()
            smoke_ok = False if smoke else None

    missing = tuple(name for name in required if name not in set(present))
    contention = agents / cells if cells else 0.0
    notes = [
        "FIELD_TRAIL_EMIT ist als segmented scatter oder atomarer Add geplant.",
        "Der neue segmented-Backend ist die deterministische CPU-Referenz für GPU-Scatter.",
        "Kernel-ABI kann mit `keim kernel-abi DATEI --out out/abi.json` exportiert werden.",
        "Dieser Befehl führt keine Kernel-Injection aus und lädt optional nur eine explizit angegebene lokale DLL.",
    ]
    if dll is None:
        notes.insert(0, "Keine DLL angegeben; es wurde nur die Keim-IR und ABI-Struktur validiert.")
    if scatter_ops and contention > 0.25:
        notes.append("Atomikdruck ist relevant: segmented reduction dürfte stabiler sein als naive atomics.")

    return GpuValidationReport(
        source=program.source_name,
        agents=agents,
        cells=cells,
        scatter_ops=scatter_ops,
        gather_ops=gather_ops,
        motion_ops=motion_ops,
        diffusion_ops=diffusion_ops,
        estimated_atomic_contention=contention,
        required_symbols=tuple(required),
        present_symbols=present,
        missing_symbols=missing,
        smoke_ok=smoke_ok,
        abi=abi,
        notes=tuple(notes),
    )
