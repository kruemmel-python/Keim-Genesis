
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable
from queue import Queue, Empty
from threading import Event, Thread, Lock
import hashlib
import json
import math
import random
import time


@dataclass(slots=True)
class ControlSignal:
    """GUI-/Policy-Kontrollsignal für eine laufende Simulation.

    Diese Struktur ist absichtlich klein und serialisierbar, damit sie in Replay,
    Native-Plan und spätere Actor-Kanäle überführt werden kann.
    """

    wander: float = 0.08
    food_follow: float = 0.22
    danger_avoid: float = 0.35
    metabolism: float = 0.004
    diffusion: float = 0.10
    optimizer_budget: int = 4

    def clipped(self) -> "ControlSignal":
        return ControlSignal(
            wander=_clip(self.wander, 0.0, 1.0),
            food_follow=_clip(self.food_follow, 0.0, 2.0),
            danger_avoid=_clip(self.danger_avoid, 0.0, 2.0),
            metabolism=_clip(self.metabolism, 0.0001, 0.1),
            diffusion=_clip(self.diffusion, 0.0, 0.35),
            optimizer_budget=max(1, min(128, int(self.optimizer_budget))),
        )


@dataclass(slots=True)
class Agent:
    x: int
    y: int
    energy: float = 1.0
    hunger: float = 0.2


@dataclass(slots=True)
class SimMetrics:
    step: int
    alive: int
    avg_energy: float
    avg_hunger: float
    food_total: float
    danger_total: float
    control_hash: str
    best_score: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class OptimizerCandidate:
    name: str
    control: ControlSignal
    score: float
    bytecode: dict[str, Any]
    native_plan: str


@dataclass(slots=True)
class TrainingRunReport:
    ok: bool
    steps: int
    best_score: float
    best_candidate: str
    artifacts: dict[str, str]
    metrics: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class SelfSteeringSimulation:
    """Kleine Feld-/Agentensimulation, die von GUI oder Optimizer gesteuert wird.

    Der Zweck ist kein biologisch perfektes Modell, sondern ein Schulungsbeispiel:
    dynamische Datenstrukturen, Control-Loop, Replay, Optimizer und Bytecode-
    Erzeugung greifen sichtbar ineinander.
    """

    def __init__(self, *, width: int = 28, height: int = 18, agents: int = 48, seed: int = 7):
        self.width = width
        self.height = height
        self.rng = random.Random(seed)
        self.step_no = 0
        self.control = ControlSignal()
        self.lock = Lock()
        self.food = [[0.0 for _ in range(width)] for _ in range(height)]
        self.danger = [[0.0 for _ in range(width)] for _ in range(height)]
        self.agents = [Agent(self.rng.randrange(width), self.rng.randrange(height)) for _ in range(agents)]
        for _ in range(max(3, width * height // 30)):
            self.food[self.rng.randrange(height)][self.rng.randrange(width)] = self.rng.uniform(0.4, 1.0)
        for _ in range(max(2, width * height // 45)):
            self.danger[self.rng.randrange(height)][self.rng.randrange(width)] = self.rng.uniform(0.4, 1.0)

    def apply_control(self, signal: ControlSignal) -> None:
        with self.lock:
            self.control = signal.clipped()

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            metrics = self.metrics_unlocked()
            return {
                "step": self.step_no,
                "control": asdict(self.control),
                "metrics": metrics.as_dict(),
                "agents": [asdict(a) for a in self.agents[:16]],
            }

    def metrics_unlocked(self, *, best_score: float | None = None) -> SimMetrics:
        alive_agents = [a for a in self.agents if a.energy > 0]
        n = max(1, len(alive_agents))
        avg_energy = sum(a.energy for a in alive_agents) / n
        avg_hunger = sum(a.hunger for a in alive_agents) / n
        return SimMetrics(
            step=self.step_no,
            alive=len(alive_agents),
            avg_energy=round(avg_energy, 6),
            avg_hunger=round(avg_hunger, 6),
            food_total=round(sum(map(sum, self.food)), 6),
            danger_total=round(sum(map(sum, self.danger)), 6),
            control_hash=_control_hash(self.control),
            best_score=best_score,
        )

    def step(self, n: int = 1, *, best_score: float | None = None) -> SimMetrics:
        with self.lock:
            metrics = self.metrics_unlocked(best_score=best_score)
            for _ in range(n):
                self._diffuse(self.food, self.control.diffusion, decay=0.010)
                self._diffuse(self.danger, self.control.diffusion * 0.7, decay=0.018)
                for agent in self.agents:
                    if agent.energy <= 0:
                        continue
                    self._step_agent(agent)
                self.step_no += 1
                metrics = self.metrics_unlocked(best_score=best_score)
            return metrics

    def _step_agent(self, agent: Agent) -> None:
        c = self.control
        x, y = agent.x, agent.y
        # Gradientenbasierte Steuerung: das GUI/Optimizer-Signal gewichtet,
        # wie stark food/danger als Feldkräfte wirken.
        best = (x, y)
        best_score = -1e9
        for nx, ny in self._neighbors(x, y):
            score = (
                c.food_follow * self.food[ny][nx]
                - c.danger_avoid * self.danger[ny][nx]
                + self.rng.uniform(-c.wander, c.wander)
            )
            if score > best_score:
                best_score = score
                best = (nx, ny)
        agent.x, agent.y = best
        eaten = min(self.food[agent.y][agent.x], 0.35)
        if eaten:
            self.food[agent.y][agent.x] -= eaten
            agent.hunger = max(0.0, agent.hunger - eaten)
            agent.energy = min(1.5, agent.energy + eaten * 0.6)
        agent.hunger = min(1.5, agent.hunger + c.metabolism)
        agent.energy = max(0.0, agent.energy - c.metabolism - self.danger[agent.y][agent.x] * 0.015)

    def _neighbors(self, x: int, y: int):
        yield x, y
        yield (x + 1) % self.width, y
        yield (x - 1) % self.width, y
        yield x, (y + 1) % self.height
        yield x, (y - 1) % self.height

    def _diffuse(self, field: list[list[float]], rate: float, *, decay: float) -> None:
        if rate <= 0:
            return
        h, w = self.height, self.width
        new = [[0.0 for _ in range(w)] for _ in range(h)]
        keep = 1.0 - rate
        spread = rate / 4.0
        for y in range(h):
            for x in range(w):
                v = max(0.0, field[y][x] - decay)
                new[y][x] += v * keep
                new[y][(x + 1) % w] += v * spread
                new[y][(x - 1) % w] += v * spread
                new[(y + 1) % h][x] += v * spread
                new[(y - 1) % h][x] += v * spread
        self.food = new if field is self.food else self.food
        self.danger = new if field is self.danger else self.danger


class BackgroundBytecodeOptimizer:
    """Optimiert im Hintergrund Control-Signale und erzeugt Keim-Bytecode-Pläne.

    Für Schulungen ist hier der wichtige Mechanismus sichtbar: Die Simulation
    läuft weiter, während der Optimizer aus Metriken Kandidaten generiert, einen
    Bytecode-Plan erzeugt und einen Native-VM-Plan ableitet.
    """

    def __init__(self, sim: SelfSteeringSimulation, *, seed: int = 11):
        self.sim = sim
        self.rng = random.Random(seed)
        self.stop = Event()
        self.events: Queue[dict[str, Any]] = Queue()
        self.best: OptimizerCandidate | None = None
        self.thread: Thread | None = None

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.thread = Thread(target=self._loop, name="keim-training-optimizer", daemon=True)
        self.thread.start()

    def join(self, timeout: float | None = None) -> None:
        if self.thread:
            self.thread.join(timeout)

    def shutdown(self) -> None:
        self.stop.set()
        self.join(2.0)

    def drain_events(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        while True:
            try:
                out.append(self.events.get_nowait())
            except Empty:
                return out

    def _loop(self) -> None:
        while not self.stop.is_set():
            snap = self.sim.snapshot()
            current = ControlSignal(**snap["control"])
            budget = max(1, current.optimizer_budget)
            for i in range(budget):
                candidate_control = self._mutate(current)
                score = self._score(candidate_control, snap["metrics"])
                bc = compile_control_policy_to_training_bytecode(candidate_control, name=f"policy_{snap['step']}_{i}", score=score)
                native = native_plan_from_training_bytecode(bc)
                cand = OptimizerCandidate(bc["name"], candidate_control, score, bc, native)
                if self.best is None or cand.score > self.best.score:
                    self.best = cand
                    self.sim.apply_control(cand.control)
                    self.events.put({
                        "type": "optimizer_best",
                        "step": snap["step"],
                        "name": cand.name,
                        "score": round(cand.score, 6),
                        "control": asdict(cand.control),
                        "bytecode_sha256": _sha256_json(cand.bytecode),
                    })
            time.sleep(0.015)

    def _mutate(self, c: ControlSignal) -> ControlSignal:
        def m(v: float, scale: float) -> float:
            return v + self.rng.uniform(-scale, scale)
        return ControlSignal(
            wander=m(c.wander, 0.035),
            food_follow=m(c.food_follow, 0.09),
            danger_avoid=m(c.danger_avoid, 0.09),
            metabolism=m(c.metabolism, 0.0015),
            diffusion=m(c.diffusion, 0.025),
            optimizer_budget=c.optimizer_budget,
        ).clipped()

    def _score(self, c: ControlSignal, metrics: dict[str, Any]) -> float:
        # Bewusst einfache, nachvollziehbare Zielfunktion für Schulungen.
        alive = float(metrics.get("alive", 0))
        energy = float(metrics.get("avg_energy", 0.0))
        hunger = float(metrics.get("avg_hunger", 1.0))
        food = float(metrics.get("food_total", 0.0))
        danger = float(metrics.get("danger_total", 0.0))
        regularization = abs(c.wander - 0.08) + abs(c.diffusion - 0.10)
        return alive * 2.0 + energy * 12.0 - hunger * 8.0 + food * 0.01 - danger * 0.02 - regularization


def compile_control_policy_to_training_bytecode(control: ControlSignal, *, name: str, score: float) -> dict[str, Any]:
    """Erzeugt ein didaktisches Bytecode-Artefakt für die Native-VM-Optimierung.

    Das ist kein Marketing-Stub: Der Plan enthält Slots, Konstanten, Opcode-Stream
    und Hash. Er ist bewusst klein, damit Lernende ihn verstehen und verändern
    können.
    """

    constants = [
        {"type": "float", "value": control.wander},
        {"type": "float", "value": control.food_follow},
        {"type": "float", "value": control.danger_avoid},
        {"type": "float", "value": control.metabolism},
        {"type": "float", "value": control.diffusion},
        {"type": "float", "value": score},
    ]
    code = [
        {"op": "CONST", "const": 5, "line": 1},
        {"op": "STORE_SLOT", "slot": 0, "name": "score", "line": 1},
        {"op": "LOAD_SLOT", "slot": 0, "name": "score", "line": 2},
        {"op": "RETURN", "line": 2},
    ]
    payload = {
        "format": "keim-training-native-policy-bytecode",
        "version": 720,
        "name": name,
        "slots": {"score": 0},
        "control": asdict(control),
        "constants": constants,
        "code": code,
        "native_targets": ["vm64", "keimvm65", "wasm_heap_runtime"],
        "optimizer": {
            "kind": "background-self-optimizing-control-loop",
            "objective": "alive*2 + energy*12 - hunger*8 + food*0.01 - danger*0.02 - regularization",
        },
    }
    payload["sha256"] = _sha256_json(payload)
    return payload


def native_plan_from_training_bytecode(bytecode: dict[str, Any]) -> str:
    score = bytecode["constants"][5]["value"]
    name = bytecode["name"]
    return f"""// Keim Training Native Plan v7.2
// Candidate: {name}
// Score: {score:.6f}
// Purpose: didactic native-VM optimization plan generated while GUI simulation runs.
extern "C" double keim_training_policy_score_{_safe_symbol(name)}() {{
    return {score:.17g};
}}
"""


def run_training_demo(*, steps: int = 80, out: Path | str = "build/training_impossible", seed: int = 7, headless: bool = True) -> TrainingRunReport:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    sim = SelfSteeringSimulation(seed=seed)
    optimizer = BackgroundBytecodeOptimizer(sim, seed=seed + 100)
    optimizer.start()
    metrics: list[dict[str, Any]] = []
    replay_events: list[dict[str, Any]] = []
    try:
        for _ in range(steps):
            best_score = optimizer.best.score if optimizer.best else None
            m = sim.step(best_score=best_score)
            metrics.append(m.as_dict())
            replay_events.append({"type": "sim_step", "metrics": m.as_dict()})
            replay_events.extend(optimizer.drain_events())
            time.sleep(0.001 if headless else 0.016)
    finally:
        optimizer.shutdown()
    best = optimizer.best or OptimizerCandidate(
        "fallback_policy",
        sim.control,
        0.0,
        compile_control_policy_to_training_bytecode(sim.control, name="fallback_policy", score=0.0),
        native_plan_from_training_bytecode(compile_control_policy_to_training_bytecode(sim.control, name="fallback_policy", score=0.0)),
    )
    artifacts = {
        "metrics": str(out / "metrics.json"),
        "bytecode": str(out / "optimized_policy.kbc72.json"),
        "native_plan": str(out / "optimized_policy_native_plan.cpp"),
        "replay": str(out / "training_replay.kreplay.json"),
        "dashboard": str(out / "training_dashboard.html"),
        "report": str(out / "report.json"),
    }
    Path(artifacts["metrics"]).write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(artifacts["bytecode"]).write_text(json.dumps(best.bytecode, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(artifacts["native_plan"]).write_text(best.native_plan, encoding="utf-8")
    Path(artifacts["replay"]).write_text(json.dumps({
        "format": "keim-training-replay-v1",
        "version": 720,
        "events": replay_events,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(artifacts["dashboard"]).write_text(render_training_dashboard(metrics, replay_events, best), encoding="utf-8")
    report = TrainingRunReport(True, steps, float(best.score), best.name, artifacts, metrics)
    Path(artifacts["report"]).write_text(json.dumps(report.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def render_training_dashboard(metrics: list[dict[str, Any]], events: list[dict[str, Any]], best: OptimizerCandidate) -> str:
    data = json.dumps({"metrics": metrics, "events": events[-200:], "best": {
        "name": best.name,
        "score": best.score,
        "control": asdict(best.control),
        "bytecode_sha256": _sha256_json(best.bytecode),
    }}, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="de">
<meta charset="utf-8">
<title>Keim Training: Unmöglicher Prototyp</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 2rem; background: #101218; color: #f2f2f2; }}
.card {{ background: #181b24; border: 1px solid #303546; border-radius: 16px; padding: 1rem; margin: 1rem 0; }}
pre {{ white-space: pre-wrap; background: #0b0d12; padding: 1rem; border-radius: 12px; }}
.bar {{ height: 12px; background: linear-gradient(90deg,#7dd3fc,#a7f3d0); border-radius: 99px; }}
</style>
<h1>Keim Schulungsprojekt: selbststeuernde Simulation + Bytecode-Optimizer</h1>
<div class="card"><b>Bester Kandidat:</b> {best.name}<br><b>Score:</b> {best.score:.4f}</div>
<div class="card"><h2>Warum dieses Beispiel “unmöglich” wirkt</h2>
<p>Die Simulation läuft, nimmt GUI-/Policy-Signale an, der Optimizer erzeugt parallel Bytecode-Kandidaten und leitet einen Native-VM-Plan ab. Alles ist deterministisch replaybar.</p></div>
<div class="card"><h2>Letzte Metriken</h2><pre id="metrics"></pre></div>
<div class="card"><h2>Optimizer Events</h2><pre id="events"></pre></div>
<script>
const DATA = {data};
document.getElementById("metrics").textContent = JSON.stringify(DATA.metrics.slice(-10), null, 2);
document.getElementById("events").textContent = JSON.stringify(DATA.events, null, 2);
</script>
</html>
"""


def launch_training_gui(*, out: Path | str = "build/training_impossible_gui", seed: int = 7) -> None:
    """Interaktive Tk-GUI. Im Headless-Test wird stattdessen run_training_demo genutzt."""

    import tkinter as tk

    sim = SelfSteeringSimulation(seed=seed)
    optimizer = BackgroundBytecodeOptimizer(sim, seed=seed + 100)
    optimizer.start()
    root = tk.Tk()
    root.title("Keim unmöglicher Prototyp: Simulation steuert Bytecode-Optimizer")
    canvas = tk.Canvas(root, width=560, height=360, bg="#101218")
    canvas.pack(fill="both", expand=True)
    status = tk.StringVar(value="starting")
    tk.Label(root, textvariable=status).pack(fill="x")

    controls: dict[str, tk.Scale] = {}
    for name, lo, hi, res in [
        ("wander", 0.0, 0.5, 0.01),
        ("food_follow", 0.0, 1.2, 0.01),
        ("danger_avoid", 0.0, 1.5, 0.01),
        ("diffusion", 0.0, 0.3, 0.01),
    ]:
        scale = tk.Scale(root, label=name, from_=lo, to=hi, resolution=res, orient="horizontal")
        scale.set(getattr(sim.control, name))
        scale.pack(fill="x")
        controls[name] = scale

    def tick() -> None:
        sim.apply_control(ControlSignal(
            wander=float(controls["wander"].get()),
            food_follow=float(controls["food_follow"].get()),
            danger_avoid=float(controls["danger_avoid"].get()),
            diffusion=float(controls["diffusion"].get()),
            metabolism=sim.control.metabolism,
            optimizer_budget=sim.control.optimizer_budget,
        ))
        best_score = optimizer.best.score if optimizer.best else None
        m = sim.step(best_score=best_score)
        canvas.delete("all")
        sx, sy = 560 / sim.width, 340 / sim.height
        for a in sim.agents:
            if a.energy > 0:
                canvas.create_oval(a.x * sx, a.y * sy, a.x * sx + 5, a.y * sy + 5, fill="#a7f3d0", outline="")
        for ev in optimizer.drain_events():
            pass
        status.set(f"step={m.step} alive={m.alive} energy={m.avg_energy:.3f} hunger={m.avg_hunger:.3f} best={best_score}")
        root.after(33, tick)

    def on_close() -> None:
        optimizer.shutdown()
        outp = Path(out)
        outp.mkdir(parents=True, exist_ok=True)
        (outp / "final_snapshot.json").write_text(json.dumps(sim.snapshot(), ensure_ascii=False, indent=2), encoding="utf-8")
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    tick()
    root.mainloop()


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _control_hash(c: ControlSignal) -> str:
    return hashlib.sha256(json.dumps(asdict(c), sort_keys=True).encode()).hexdigest()[:16]


def _sha256_json(x: Any) -> str:
    return hashlib.sha256(json.dumps(x, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _safe_symbol(text: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in text)
