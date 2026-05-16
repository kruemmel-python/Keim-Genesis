from __future__ import annotations

from pathlib import Path
import json
import sys
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from autonome_Simulations_API.api_service import create_server
from autonome_Simulations_API.sim_engine import SimulationConfig, SimulationEngine
from keim.analyzer import analyze_program
from keim.parser import parse_file


def _read_json(url: str, method: str = "GET", body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return json.loads(exc.read().decode("utf-8"))


def main() -> None:
    engine = SimulationEngine(SimulationConfig(agent_count=64, width=16, height=8, native_enabled=False, running=False))
    before = engine.snapshot()["round"]
    engine.step(3)
    after = engine.snapshot()["round"]
    assert after == before + 3
    assert engine.apply_control({"wind_x": 2, "energy_delta": -0.002})["wind_x"] == 2
    engine.close()

    program = parse_file(ROOT / "autonome_Simulations_API" / "keim_sources" / "autonome_api.keim")
    report = analyze_program(program)
    assert report.ok, report.format()

    srv = create_server("127.0.0.1", 0, None)
    srv.engine.apply_control({"running": False, "agent_count": 32, "native_enabled": False})
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{srv.port}"
        health = _read_json(base + "/health")
        assert health["ok"] is True, health

        control = _read_json(base + "/control", "POST", {"running": False, "wind_x": 1})
        assert control["ok"] is True, control

        stepped = _read_json(base + "/step", "POST", {"rounds": 2})
        assert stepped["snapshot"]["round"] >= 2, stepped

        metrics = _read_json(base + "/metrics")
        assert metrics["ok"] is True and metrics["metrics"]["agent_count"] == 32, metrics

        bad = _read_json(base + "/control", "POST", {"nicht_existiert": 1})
        assert bad["ok"] is False, bad
    finally:
        srv.shutdown()
        thread.join(timeout=2.0)

    print("[Keim] autonome_Simulations_API smoke test OK")


if __name__ == "__main__":
    main()
