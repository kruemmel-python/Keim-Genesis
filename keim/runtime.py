from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .ast_nodes import Program
from .backends.cpu import CpuBackend, CpuConfig, CpuReport
from .backends.vm import BytecodeBackend, CircuitBytecodeBackend, FusedBytecodeBackend, SegmentedScatterBackend, NativeBytecodeBackend, GpuDriverBackend
from .backends.driver import DriverLoadError, DriverProbe
from .debugbus import DebugBus
from .sandbox import SandboxPolicy


BackendName = Literal["cpu", "vm", "fused", "circuit", "segmented", "native", "gpu", "hybrid", "auto"]


@dataclass(slots=True)
class RunOptions:
    rounds: int = 60
    show_every: int = 10
    seed: int = 7
    quiet: bool = False
    backend: BackendName = "cpu"
    dll: Path | None = None
    gpu_index: int = 0
    driver_smoke: bool = False
    collect_metrics: bool = True
    debug_bus: DebugBus | None = None
    sandbox: SandboxPolicy | None = None


@dataclass(slots=True)
class RunReport:
    backend: str
    cpu: CpuReport
    driver: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"backend": self.backend, "driver": self.driver, **self.cpu.as_dict()}


def run_program(program: Program, options: RunOptions) -> RunReport:
    driver_status: dict[str, Any] | None = None
    selected = options.backend

    if options.backend in {"gpu", "hybrid", "auto"}:
        driver_status = _probe_driver(options)
        if options.backend == "gpu":
            selected = "gpu"
            if not options.quiet:
                print("[Keim] GPU-Modus: CC_OpenCl Driver Execution Backend aktiv; nutzt echten Treiber wo verfügbar und deterministische Referenz sonst.")
        elif driver_status.get("loaded") or driver_status.get("ready_for_planned_dispatch"):
            selected = "gpu"
            if not options.quiet:
                print("[Keim] Hybrid-Modus: Treiber/Dispatchplan erkannt; GPU Driver Execution Backend aktiv.")
        elif options.backend == "hybrid":
            if not options.quiet:
                print("[Keim] Hybrid-Modus: Treiber nicht nutzbar; CPU-Referenzbackend wird verwendet.")
            selected = "cpu"
        else:
            selected = "segmented"

    config = CpuConfig(seed=options.seed, show_every=options.show_every, quiet=options.quiet, collect_metrics=options.collect_metrics, debug_bus=options.debug_bus, sandbox=options.sandbox)
    if selected == "vm":
        backend = BytecodeBackend(config)
    elif selected == "fused":
        backend = FusedBytecodeBackend(config)
    elif selected == "circuit":
        backend = CircuitBytecodeBackend(config)
    elif selected == "segmented":
        backend = SegmentedScatterBackend(config)
    elif selected == "native":
        backend = NativeBytecodeBackend(config)
    elif selected == "gpu":
        backend = GpuDriverBackend(config)
    else:
        backend = CpuBackend(config)

    backend.load(program)
    for tick in range(1, options.rounds + 1):
        backend.step(tick)

    return RunReport(backend=backend.backend_tag, cpu=backend.summary(options.rounds), driver=driver_status)


def _probe_driver(options: RunOptions) -> dict[str, Any]:
    try:
        from .gpu_driver_execution import inspect_driver, default_driver_path
        dll = options.dll or default_driver_path()
        report = inspect_driver(dll, load=True, gpu_index=options.gpu_index).as_dict()
        if options.driver_smoke and options.dll is not None:
            legacy = DriverProbe(options.dll, gpu_index=options.gpu_index).inspect(smoke=True).as_dict()
            report["legacy_smoke"] = legacy
        return report
    except Exception as exc:
        return {"loaded": False, "smoke_ok": False if options.driver_smoke else None, "detail": str(exc)}
