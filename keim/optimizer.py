from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .ast_nodes import Program
from .bytecode import ByteOp, ByteProgram, OpCode, compile_bytecode


GPU_EXEC_OPS = {
    OpCode.FIELD_CHANGE,
    OpCode.FIELD_COMPUTE,
    OpCode.FIELD_TRAIL_COUPLE,
    OpCode.MEMORY_AGGREGATE,
    OpCode.FIELD_TRAIL_EMIT,
    OpCode.FOLLOW_TRAIL,
    OpCode.AVOID_TRAIL,
    OpCode.DIFFUSE_TRAIL,
    OpCode.STRENGTHEN_TRAIL,
    OpCode.SHOW,
}


@dataclass(slots=True, frozen=True)
class OpBundle:
    kind: str
    start_pc: int
    end_pc: int
    mask_depth: int
    opcodes: tuple[str, ...]
    reason: str
    gpu_hint: str | None = None
    regime: str = "unknown"

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "start_pc": self.start_pc,
            "end_pc": self.end_pc,
            "mask_depth": self.mask_depth,
            "opcodes": list(self.opcodes),
            "reason": self.reason,
            "gpu_hint": self.gpu_hint,
            "regime": self.regime,
        }


@dataclass(slots=True, frozen=True)
class OptimizationReport:
    source: str
    original_ops: int
    gpu_candidate_ops: int
    estimated_gpu_launches_naive: int
    estimated_gpu_launches_bundled: int
    bundles: tuple[OpBundle, ...]

    @property
    def estimated_launch_reduction(self) -> int:
        return self.estimated_gpu_launches_naive - self.estimated_gpu_launches_bundled

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "original_ops": self.original_ops,
            "gpu_candidate_ops": self.gpu_candidate_ops,
            "estimated_gpu_launches_naive": self.estimated_gpu_launches_naive,
            "estimated_gpu_launches_bundled": self.estimated_gpu_launches_bundled,
            "estimated_launch_reduction": self.estimated_launch_reduction,
            "bundles": [b.as_dict() for b in self.bundles],
        }

    def format(self) -> str:
        lines = [
            "[Keim] Optimierungsplan v1.2",
            f"  Quelle: {self.source}",
            f"  Bytecode-Ops: {self.original_ops}",
            f"  GPU-Kandidaten: {self.gpu_candidate_ops}",
            f"  naive GPU-Launches: {self.estimated_gpu_launches_naive}",
            f"  gebündelte GPU-Launches: {self.estimated_gpu_launches_bundled}",
            f"  geschätzte Launch-Reduktion: {self.estimated_launch_reduction}",
            "",
            "  Bündel:",
        ]
        if not self.bundles:
            lines.append("    - keine")
            return "\n".join(lines)
        for b in self.bundles:
            marker = "GPU" if b.kind == "gpu-bundle" else "CPU"
            lines.append(f"    - {marker} pc {b.start_pc:03d}..{b.end_pc:03d} depth={b.mask_depth} regime={b.regime} ops={', '.join(b.opcodes)}")
            lines.append(f"      {b.reason}")
            if b.gpu_hint:
                lines.append(f"      {b.gpu_hint}")
        return "\n".join(lines)


def analyze_optimization(program: Program | ByteProgram) -> OptimizationReport:
    bp = compile_bytecode(program) if not isinstance(program, ByteProgram) else program
    bundles: list[OpBundle] = []
    current: list[ByteOp] = []
    current_depth: int | None = None
    current_regime: str | None = None
    mask_depth = 0
    gpu_candidate_ops = 0

    def flush(reason: str = "Barriere/CPU-Op trennt Batch") -> None:
        nonlocal current, current_depth, current_regime
        if not current:
            return
        hints = sorted({op.gpu_hint for op in current if op.gpu_hint})
        bundles.append(OpBundle(
            kind="gpu-bundle",
            start_pc=current[0].pc,
            end_pc=current[-1].pc,
            mask_depth=current_depth or 0,
            opcodes=tuple(op.opcode.value for op in current),
            reason=reason,
            gpu_hint="; ".join(hints) if hints else None,
            regime=current_regime or "unknown",
        ))
        current = []
        current_depth = None
        current_regime = None

    compatible = {
        "elementwise": {"elementwise", "gather"},
        "gather": {"elementwise", "gather"},
        "scatter": {"scatter"},
        "diffusion": {"diffusion"},
        "motion": {"motion"},
        "render": {"render"},
    }

    for op in bp.ops:
        if op.opcode == OpCode.MASK_END:
            flush("Maskenende")
            mask_depth = max(0, mask_depth - 1)
            continue
        if op.opcode in {OpCode.MASK_FIELD, OpCode.MASK_TRAIL, OpCode.MASK_MEMORY, OpCode.MASK_FOOD, OpCode.MASK_EXPR}:
            flush("Maskenbeginn")
            mask_depth += 1
            continue

        if op.gpu_hint and op.opcode in GPU_EXEC_OPS:
            gpu_candidate_ops += 1
            if current and (current_depth != mask_depth or op.regime not in compatible.get(current_regime or "", set())):
                flush("anderes Masken-/Kernel-Regime")
            current.append(op)
            current_depth = mask_depth
            current_regime = current_regime or op.regime
        else:
            flush()
    flush("Programmende")

    return OptimizationReport(
        source=bp.source_name,
        original_ops=len(bp.ops),
        gpu_candidate_ops=gpu_candidate_ops,
        estimated_gpu_launches_naive=gpu_candidate_ops,
        estimated_gpu_launches_bundled=len(bundles),
        bundles=tuple(bundles),
    )
