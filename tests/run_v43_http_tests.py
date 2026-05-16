from __future__ import annotations

from pathlib import Path
import json
import socket
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from autonome_Simulations_API.keim_daemon import create_daemon
from keim.analyzer import analyze_program
from keim.backends.cpu import CpuBackend, CpuConfig
from keim.bytecode import compile_bytecode
from keim.parser import parse_file, parse_source


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _read_json(url: str, method: str = "GET", body: dict | None = None) -> tuple[int, dict]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=5) as response:
            return int(response.status), json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return int(exc.code), json.loads(exc.read().decode("utf-8"))


def test_internal_http_router_core() -> None:
    port = _free_port()
    source = f"""
welt test mit 1 agenten groesse 4 4
speicher eingang_json text startet bei "{{}}"
speicher antwort text startet bei "{{}}"
speicher status karte startet bei {{}}
speicher status_code ganzzahl startet bei 200
speicher fehler text startet bei ""

server api bei {port} parallel 4:
    route GET "/health" antwortet speicher antwort:
        karte status setzt "ok" auf wahr
        json schreibt speicher status in speicher antwort
    route POST "/echo" liest speicher eingang_json antwortet speicher antwort status speicher status_code:
        versuche:
            json liest speicher eingang_json in speicher status
            wenn karte status enthaelt "a":
                karte status setzt "has_a" auf wahr
            karte status setzt "echo" auf speicher.eingang_json
            speicher status_code setzt 201
        fange fehler in speicher fehler:
            karte status setzt "ok" auf falsch
            karte status setzt "error" auf speicher.fehler
            speicher status_code setzt 400
        json schreibt speicher status in speicher antwort

jede runde:
    sammle muell
"""
    program = parse_source(source)
    report = analyze_program(program)
    assert report.ok, report.format()
    bytecode = compile_bytecode(program)
    stats = bytecode.stats()
    assert stats["op:HTTP_SERVICE_START"] == 1
    assert stats["op:HTTP_ROUTE"] == 2
    assert stats["op:MAP_SET"] >= 1

    backend = CpuBackend(CpuConfig(quiet=True))
    backend.load(program)
    try:
        status, health = _read_json(f"http://127.0.0.1:{port}/health")
        assert status == 200 and health["ok"] is True, health

        status, echo = _read_json(f"http://127.0.0.1:{port}/echo", "POST", {"a": 1})
        assert status == 201 and echo["a"] == 1 and echo["has_a"] is True and "echo" in echo, echo

        status, missing = _read_json(f"http://127.0.0.1:{port}/missing")
        assert status == 404 and missing["ok"] is False, missing
    finally:
        backend.shutdown_http()


def test_autonome_api_v43_daemon() -> None:
    source = ROOT / "autonome_Simulations_API" / "keim_sources" / "autonome_api_v43.keim"
    program = parse_file(source)
    report = analyze_program(program)
    assert report.ok, report.format()

    daemon = create_daemon(source, tick_hz=60.0)
    daemon.start_background()
    try:
        time.sleep(0.15)
        base = "http://127.0.0.1:18080"
        status, health = _read_json(base + "/health")
        assert status == 200 and health["ok"] is True, health

        status, control = _read_json(base + "/control", "POST", {"running": True, "wind_signal": 0.02, "energy_loss": 0.002})
        assert status == 200 and control["ok"] is True and abs(control["wind_signal"] - 0.02) < 1e-9, control

        status, paused = _read_json(base + "/control", "POST", {"running": False})
        assert status == 200 and paused["running"] is False and abs(paused["wind_signal"] - 0.02) < 1e-9 and abs(paused["energy_loss"] - 0.002) < 1e-9, paused

        status, resumed = _read_json(base + "/control", "POST", {"running": True})
        assert status == 200 and resumed["running"] is True and abs(resumed["wind_signal"] - 0.02) < 1e-9 and abs(resumed["energy_loss"] - 0.002) < 1e-9, resumed

        status, snapshot = _read_json(base + "/snapshot")
        assert status == 200 and snapshot["ok"] is True and "energy_mean" in snapshot, snapshot

        status, metrics = _read_json(base + "/metrics")
        assert status == 200 and metrics["ok"] is True and metrics["agents"] == 256 and "energy_loss" in metrics, metrics

        status, routes = _read_json(base + "/routes")
        assert status == 200 and routes["ok"] is True and "/metrics" in routes["routes"] and "/config" in routes["routes"], routes

        status, config = _read_json(base + "/config")
        assert status == 200 and config["ok"] is True and config["agents"] == 256, config

        status, saved = _read_json(base + "/save", "POST", {})
        assert status == 200 and saved["ok"] is True and "energy_mean" in saved, saved
    finally:
        daemon.close()


def main() -> None:
    test_internal_http_router_core()
    test_autonome_api_v43_daemon()
    print("[Keim] v4.3 internal HTTP router tests OK")


if __name__ == "__main__":
    main()
