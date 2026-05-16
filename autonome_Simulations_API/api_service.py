from __future__ import annotations

from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import argparse
import json
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urlparse

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from autonome_Simulations_API.sim_engine import SimulationEngine, load_config
else:
    from .sim_engine import SimulationEngine, load_config


@dataclass(slots=True)
class ApiServerHandle:
    httpd: ThreadingHTTPServer
    engine: SimulationEngine

    @property
    def port(self) -> int:
        return int(self.httpd.server_address[1])

    def serve_forever(self) -> None:
        self.engine.start_background()
        try:
            self.httpd.serve_forever()
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.engine.close()


def _json_bytes(data: Any, status: int = 200) -> tuple[int, bytes]:
    return status, json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def make_handler(engine: SimulationEngine) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "KeimAutonomeSimAPI/4.2"

        def log_message(self, fmt: str, *args: Any) -> None:
            # Daemon-freundlich: kein Request-Spam auf stdout.
            return

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length <= 0:
                return {}
            raw = self.rfile.read(length).decode("utf-8")
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"ungültiges JSON: {exc}") from exc
            if not isinstance(obj, dict):
                raise ValueError("JSON-Body muss ein Objekt sein")
            return obj

        def _send(self, status: int, data: Any) -> None:
            code, payload = _json_bytes(data, status)
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _safe(self, fn: Any) -> None:
            try:
                status, data = fn()
            except Exception as exc:
                self._send(400, {"ok": False, "error": str(exc)})
                return
            self._send(status, data)

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            def route() -> tuple[int, Any]:
                match path:
                    case "/health":
                        return 200, {"ok": True, "service": "autonome_Simulations_API", "round": engine.round}
                    case "/snapshot":
                        return 200, {"ok": True, "snapshot": engine.snapshot()}
                    case "/metrics":
                        return 200, {"ok": True, "metrics": engine.metrics()}
                    case "/control":
                        return 200, {"ok": True, "control": engine.control_state()}
                    case _:
                        return 404, {"ok": False, "error": f"unbekannter Endpunkt: {path}"}
            self._safe(route)

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            def route() -> tuple[int, Any]:
                body = self._read_json()
                match path:
                    case "/control":
                        return 200, {"ok": True, "control": engine.apply_control(body)}
                    case "/step":
                        rounds = int(body.get("rounds", 1))
                        return 200, {"ok": True, "snapshot": engine.step(rounds)}
                    case "/reset":
                        return 200, {"ok": True, "snapshot": engine.reset(body)}
                    case "/command":
                        kind = str(body.get("kind", "control"))
                        payload = body.get("payload", {})
                        if not isinstance(payload, dict):
                            raise ValueError("payload muss ein Objekt sein")
                        return 202, {"ok": True, "queue": engine.enqueue(kind, payload)}
                    case "/gc":
                        engine.enqueue("gc", {})
                        engine.drain_commands()
                        return 200, {"ok": True, "metrics": engine.metrics()}
                    case _:
                        return 404, {"ok": False, "error": f"unbekannter Endpunkt: {path}"}
            self._safe(route)

    return Handler


def create_server(host: str = "127.0.0.1", port: int = 8080, config_path: str | Path | None = None) -> ApiServerHandle:
    cfg = load_config(config_path) if config_path else load_config(Path(__file__).with_name("config.json"))
    engine = SimulationEngine(cfg)
    httpd = ThreadingHTTPServer((host, port), make_handler(engine))
    return ApiServerHandle(httpd=httpd, engine=engine)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Autonome Keim-v4.2-Simulations-API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--config", default=str(Path(__file__).with_name("config.json")))
    args = parser.parse_args(argv)

    srv = create_server(args.host, args.port, args.config)
    print(f"Keim autonome_Simulations_API lauscht auf http://{args.host}:{srv.port}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
