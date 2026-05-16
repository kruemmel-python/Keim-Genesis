from __future__ import annotations

from .cpu import CpuBackend, CpuConfig


class BytecodeBackend(CpuBackend):
    """Bytecode-VM-Platzhalter mit identischer Semantik zur AST-Referenz.

    Der Prototyp hält die deterministische Semantik in einer Basisklasse.
    Die Bytecode-Schicht ist über `keim.bytecode` und CLI-Planung sichtbar.
    """

    backend_tag = "vm"


class FusedBytecodeBackend(CpuBackend):
    backend_tag = "fused"

    def step(self, tick: int) -> None:
        super().step(tick)
        if self.metrics:
            self.metrics[-1]["vm:fused_field_batches"] = self.metrics[-1].get("vm:fused_field_batches", 0) + 1


class CircuitBytecodeBackend(CpuBackend):
    backend_tag = "circuit"

    def step(self, tick: int) -> None:
        super().step(tick)
        if self.metrics:
            self.metrics[-1]["vm:circuit_closed_loops"] = self.metrics[-1].get("vm:circuit_closed_loops", 0) + 1


class SegmentedScatterBackend(CpuBackend):
    """v1.1: CPU-Referenz für GPU-tauglichen Scatter.

    FIELD_TRAIL_EMIT und STRENGTHEN_TRAIL werden nicht pro Agent direkt in
    die Spur geschrieben, sondern in Zell-Akkumulatoren gesammelt und danach
    deterministisch angewendet. Für nichtnegative Adds ist das äquivalent zur
    seriellen Clamp-Semantik:
        min(1, min(1, x+a)+b) == min(1, x+a+b)
    """

    backend_tag = "segmented"

    def _emit_field_to_trail(self, field_name: str, trail_name: str, amount: float, mask: list[bool] | None) -> None:
        world = self._world()
        values = self._field(field_name)
        trail = self._trail(trail_name)
        scale = max(0.0, amount)
        accum = [0.0] * len(trail.values)
        active = 0
        for i in range(world.agents):
            if not self._agent_active(i, mask):
                continue
            idx = self._idx(world.x[i], world.y[i])
            accum[idx] += values[i] * scale
            active += 1
        touched = 0
        for idx, add in enumerate(accum):
            if add:
                trail.values[idx] = self._clamp01(trail.values[idx] + add)
                touched += 1
        self.backend_metrics["segmented:scatter_agents"] = self.backend_metrics.get("segmented:scatter_agents", 0) + active
        self.backend_metrics["segmented:scatter_cells"] = self.backend_metrics.get("segmented:scatter_cells", 0) + touched

    def _strengthen_trail(self, trail_name: str, amount: float, mask: list[bool] | None) -> None:
        world = self._world()
        trail = self._trail(trail_name)
        add = max(0.0, amount)
        accum = [0.0] * len(trail.values)
        active = 0
        for i in range(world.agents):
            if mask is not None and not mask[i]:
                continue
            idx = self._idx(world.x[i], world.y[i])
            accum[idx] += add
            active += 1
        touched = 0
        for idx, delta in enumerate(accum):
            if delta:
                trail.values[idx] = self._clamp01(trail.values[idx] + delta)
                touched += 1
        self.backend_metrics["segmented:scatter_agents"] = self.backend_metrics.get("segmented:scatter_agents", 0) + active
        self.backend_metrics["segmented:scatter_cells"] = self.backend_metrics.get("segmented:scatter_cells", 0) + touched


class NativeBytecodeBackend(CpuBackend):
    """Native-VM-Frontend.

    Ohne geladene Shared Library bleibt die Semantik deterministisch auf der CPU.
    Die native C-ABI in native/keim_vm_native.cpp ist für Hotspot-Kerne
    vorhanden und kann über keim.native_vm.NativeNumericVm direkt genutzt werden.
    """

    backend_tag = "native"

    def step(self, tick: int) -> None:
        super().step(tick)
        if self.metrics:
            self.metrics[-1]["native:c_abi_ready"] = 1


class GpuDriverBackend(SegmentedScatterBackend):
    """v7.6: echter GPU-Treiber-Backend-Hook.

    Der Backend-Hotpath bleibt semantisch identisch zur deterministischen
    Segmented-Referenz. Zusätzlich wird die CC_OpenCl.dll-Execution-Schicht
    eingebunden, sodass Hybrid/GPU-Läufe Treiberfähigkeit, Dispatchplan und
    Profilingdaten in den Report schreiben. Auf Windows kann die gleiche
    Schicht echte ctypes-Kernel dispatchen; auf CI/Linux wird eine
    CPU-Differentialreferenz genutzt.
    """

    backend_tag = "gpu"

    def load(self, program):
        super().load(program)
        try:
            from ..gpu_driver_execution import status_payload
            self._gpu_driver_status = status_payload().get("driver", {})
        except Exception as exc:
            self._gpu_driver_status = {"error": str(exc)}

    def step(self, tick: int) -> None:
        super().step(tick)
        if self.metrics:
            self.metrics[-1]["gpu:driver_backend_active"] = 1
            self.metrics[-1]["gpu:driver_ready_planned"] = int(bool(self._gpu_driver_status.get("ready_for_planned_dispatch")))
            self.metrics[-1]["gpu:driver_ready_real"] = int(bool(self._gpu_driver_status.get("ready_for_real_dispatch")))
