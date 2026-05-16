from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import gc
import json
import random
import threading
import time
from typing import Any

try:
    from keim.native_vm import NativeAgentStore, NativeNumericVm, default_native_library
except Exception:  # pragma: no cover - erlaubt Nutzung außerhalb des Projektroots
    NativeAgentStore = None  # type: ignore[assignment]
    NativeNumericVm = None  # type: ignore[assignment]

    def default_native_library() -> Path:  # type: ignore[no-redef]
        return Path("build/native/keim_vm_native.dll")


@dataclass(slots=True)
class SimulationConfig:
    width: int = 96
    height: int = 64
    agent_count: int = 4096
    seed: int = 42
    tick_hz: float = 20.0
    steps_per_tick: int = 1
    running: bool = True
    wind_x: int = 1
    wind_y: int = 0
    energy_delta: float = -0.001
    native_enabled: bool = True
    gpu_driver_path: str | None = None
    snapshot_limit: int = 32

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "SimulationConfig":
        cfg = cls()
        cfg.apply_patch(data)
        return cfg

    def apply_patch(self, data: dict[str, Any]) -> None:
        for key, value in data.items():
            if not hasattr(self, key):
                raise ValueError(f"unbekannter Steuerparameter: {key}")
            match key:
                case "width" | "height" | "agent_count" | "seed" | "steps_per_tick" | "wind_x" | "wind_y" | "snapshot_limit":
                    value = int(value)
                case "tick_hz" | "energy_delta":
                    value = float(value)
                case "running" | "native_enabled":
                    value = bool(value)
                case "gpu_driver_path":
                    value = None if value in ("", None) else str(value)
                case _:
                    pass
            setattr(self, key, value)
        self._validate()

    def _validate(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("width und height müssen positiv sein")
        if not 0 < self.agent_count <= 5_000_000:
            raise ValueError("agent_count muss zwischen 1 und 5_000_000 liegen")
        if not 0.1 <= self.tick_hz <= 1000.0:
            raise ValueError("tick_hz muss zwischen 0.1 und 1000 liegen")
        if not 1 <= self.steps_per_tick <= 10_000:
            raise ValueError("steps_per_tick muss zwischen 1 und 10000 liegen")
        if self.snapshot_limit < 0:
            raise ValueError("snapshot_limit darf nicht negativ sein")


@dataclass(slots=True)
class ApiCommand:
    kind: str
    payload: dict[str, Any]
    created_at: float = field(default_factory=time.time)


class SimulationEngine:
    """Dauerhafte Simulationsmaschine mit Keim-v4.2-kompatibler Steuerfläche.

    Der Zustand liegt als Structure-of-Arrays vor. Wenn die native Bibliothek
    existiert, werden x/y/energy/alive in den C++-Hotspot gespiegelt. Ohne
    native Bibliothek bleibt die API identisch und nutzt den Python-Fallback.
    """

    def __init__(self, config: SimulationConfig | None = None) -> None:
        self.config = config or SimulationConfig()
        self.config._validate()
        self.lock = threading.RLock()
        self.commands: list[ApiCommand] = []
        self.round = 0
        self.started_at = time.time()
        self.last_error: str | None = None
        self.native_mode = False
        self.gpu_ready = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

        self.x: list[int] = []
        self.y: list[int] = []
        self.energy: list[float] = []
        self.alive: list[bool] = []
        self._rng = random.Random(self.config.seed)

        self._native_vm: Any = None
        self._native_store: Any = None
        self.reset({})

    def reset(self, patch: dict[str, Any] | None = None) -> dict[str, Any]:
        with self.lock:
            if patch:
                self.config.apply_patch(patch)
            self._rng = random.Random(self.config.seed)
            n = self.config.agent_count
            self.x = [self._rng.randrange(self.config.width) for _ in range(n)]
            self.y = [self._rng.randrange(self.config.height) for _ in range(n)]
            self.energy = [0.5 + self._rng.random() * 0.5 for _ in range(n)]
            self.alive = [True] * n
            self.round = 0
            self.last_error = None
            self._init_native_locked()
            return self.snapshot()

    def _init_native_locked(self) -> None:
        self.native_mode = False
        self.gpu_ready = False
        if self._native_store is not None:
            try:
                self._native_store.close()
            except Exception:
                pass
        self._native_store = None
        self._native_vm = None

        if not self.config.native_enabled or NativeNumericVm is None:
            return

        lib = default_native_library()
        if not lib.exists():
            return

        try:
            self._native_vm = NativeNumericVm(lib)
            self._native_store = NativeAgentStore(
                self._native_vm,
                self.config.agent_count,
                self.config.width,
                self.config.height,
            )
            self._native_store.import_state(self.x, self.y, self.energy, self.alive)
            self.native_mode = True

            if self.config.gpu_driver_path:
                try:
                    gpu = self._native_vm.load_gpu_driver(self.config.gpu_driver_path)
                    self.gpu_ready = gpu.ready()
                    gpu.close()
                except Exception as exc:
                    self.last_error = f"GPU-Treiber nicht bereit: {exc}"
        except Exception as exc:
            self.last_error = f"Native-Hotspot nicht aktiv: {exc}"
            self.native_mode = False
            self._native_store = None
            self._native_vm = None

    def enqueue(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            self.commands.append(ApiCommand(kind=kind, payload=dict(payload)))
            return {"queued": len(self.commands), "kind": kind}

    def apply_control(self, patch: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            structural = {"width", "height", "agent_count", "seed", "native_enabled", "gpu_driver_path"}
            needs_reset = any(k in structural for k in patch)
            self.config.apply_patch(patch)
            if needs_reset:
                self.reset({})
            return self.control_state()

    def control_state(self) -> dict[str, Any]:
        return {
            "running": self.config.running,
            "tick_hz": self.config.tick_hz,
            "steps_per_tick": self.config.steps_per_tick,
            "wind_x": self.config.wind_x,
            "wind_y": self.config.wind_y,
            "energy_delta": self.config.energy_delta,
            "agent_count": self.config.agent_count,
            "native_enabled": self.config.native_enabled,
            "native_mode": self.native_mode,
            "gpu_ready": self.gpu_ready,
        }

    def drain_commands(self) -> None:
        with self.lock:
            pending = self.commands
            self.commands = []
        for cmd in pending:
            try:
                match cmd.kind:
                    case "control":
                        self.apply_control(cmd.payload)
                    case "reset":
                        self.reset(cmd.payload)
                    case "step":
                        self.step(int(cmd.payload.get("rounds", 1)))
                    case "gc":
                        gc.collect()
                    case _:
                        raise ValueError(f"unbekannter Befehl: {cmd.kind}")
            except Exception as exc:
                with self.lock:
                    self.last_error = str(exc)

    def step(self, rounds: int = 1) -> dict[str, Any]:
        if rounds < 1:
            raise ValueError("rounds muss positiv sein")
        with self.lock:
            if self.native_mode and self._native_store is not None and NativeNumericVm is not None:
                ops: list[tuple[int, int, int, float]] = []
                if self.config.wind_x:
                    ops.append((NativeNumericVm.OP_AGENT_X_ADD_WRAP, 0, 0, float(self.config.wind_x)))
                if self.config.wind_y:
                    ops.append((NativeNumericVm.OP_AGENT_Y_ADD_WRAP, 0, 0, float(self.config.wind_y)))
                if self.config.energy_delta:
                    ops.append((NativeNumericVm.OP_AGENT_ENERGY_ADD_CLAMP, 0, 0, float(self.config.energy_delta)))
                ops.append((NativeNumericVm.OP_HALT, 0, 0, 0.0))
                for _ in range(rounds):
                    self._native_store.run(ops)
                exported = self._native_store.export_state(self.config.agent_count)
                self.x = list(exported["x"])  # type: ignore[arg-type]
                self.y = list(exported["y"])  # type: ignore[arg-type]
                self.energy = list(exported["energy"])  # type: ignore[arg-type]
                self.alive = list(exported["alive"])  # type: ignore[arg-type]
            else:
                w, h = self.config.width, self.config.height
                dx, dy, de = self.config.wind_x, self.config.wind_y, self.config.energy_delta
                for _ in range(rounds):
                    for i, ok in enumerate(self.alive):
                        if not ok:
                            continue
                        self.x[i] = (self.x[i] + dx) % w
                        self.y[i] = (self.y[i] + dy) % h
                        self.energy[i] = min(1.0, max(0.0, self.energy[i] + de))
                        if self.energy[i] <= 0.0:
                            self.alive[i] = False
            self.round += rounds
            return self.snapshot()

    def run_forever(self) -> None:
        while not self._stop.is_set():
            start = time.perf_counter()
            self.drain_commands()
            try:
                if self.config.running:
                    self.step(self.config.steps_per_tick)
            except Exception as exc:
                with self.lock:
                    self.last_error = str(exc)
            delay = max(0.0, (1.0 / max(0.1, self.config.tick_hz)) - (time.perf_counter() - start))
            self._stop.wait(delay)

    def start_background(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self.run_forever, name="keim-sim-api-loop", daemon=True)
        self._thread.start()

    def stop_background(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            alive_count = sum(1 for v in self.alive if v)
            n = max(1, len(self.energy))
            limit = min(self.config.snapshot_limit, len(self.x))
            return {
                "round": self.round,
                "world": {"width": self.config.width, "height": self.config.height},
                "agents": {
                    "count": len(self.x),
                    "alive": alive_count,
                    "mean_energy": sum(self.energy) / n,
                    "sample": [
                        {"id": i, "x": self.x[i], "y": self.y[i], "energy": self.energy[i], "alive": self.alive[i]}
                        for i in range(limit)
                    ],
                },
                "control": self.control_state(),
                "last_error": self.last_error,
                "uptime_seconds": time.time() - self.started_at,
            }

    def metrics(self) -> dict[str, Any]:
        snap = self.snapshot()
        return {
            "round": snap["round"],
            "agent_updates": snap["round"] * self.config.agent_count,
            "agent_count": self.config.agent_count,
            "native_mode": self.native_mode,
            "gpu_ready": self.gpu_ready,
            "mean_energy": snap["agents"]["mean_energy"],
            "queued_commands": len(self.commands),
            "last_error": self.last_error,
        }

    def close(self) -> None:
        self.stop_background()
        with self.lock:
            if self._native_store is not None:
                self._native_store.close()
                self._native_store = None


def load_config(path: str | Path) -> SimulationConfig:
    p = Path(path)
    if not p.exists():
        return SimulationConfig()
    return SimulationConfig.from_mapping(json.loads(p.read_text(encoding="utf-8")))
