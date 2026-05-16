from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time
from typing import Any

@dataclass(slots=True)
class DebugBus:
    maxlen: int = 2048
    events: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=2048))
    state: dict[str, Any] = field(default_factory=dict)
    watched: set[str] = field(default_factory=set)
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def __post_init__(self) -> None:
        if self.events.maxlen != self.maxlen:
            self.events = deque(self.events, maxlen=self.maxlen)

    def watch(self, name: str, value: Any = None) -> None:
        with self._lock:
            self.watched.add(name)
            if value is not None:
                self.state[name] = value
            self.events.append({"t": time.time(), "kind": "watch", "name": name, "value": self.state.get(name)})

    def update(self, name: str, value: Any) -> None:
        with self._lock:
            if name in self.watched:
                self.state[name] = value
                self.events.append({"t": time.time(), "kind": "state", "name": name, "value": value})

    def send(self, label: str, payload: Any = None) -> None:
        with self._lock:
            self.events.append({"t": time.time(), "kind": "mark", "label": label, "payload": payload})

    def snapshot_events(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self.events)

    def snapshot_state(self) -> dict[str, Any]:
        with self._lock:
            return dict(self.state)

@dataclass(slots=True)
class DebugServer:
    bus: DebugBus
    port: int
    server: ThreadingHTTPServer
    thread: threading.Thread

    def shutdown(self) -> None:
        self.server.shutdown()
        self.server.server_close()

def start_debug_server(bus: DebugBus, port: int) -> DebugServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: object) -> None:
            return

        def _json(self, payload: object) -> None:
            data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # noqa: N802
            if self.path in {"/debug/events", "/events"}:
                self._json({"ok": True, "events": bus.snapshot_events()})
                return
            if self.path in {"/debug/state", "/state"}:
                self._json({"ok": True, "state": bus.snapshot_state()})
                return
            if self.path in {"/", "/health"}:
                self._json({"ok": True, "debug": True, "events": len(bus.snapshot_events())})
                return
            self.send_error(404)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, name=f"keim-debug-{port}", daemon=True)
    thread.start()
    return DebugServer(bus=bus, port=port, server=server, thread=thread)
