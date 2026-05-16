from __future__ import annotations

from dataclasses import dataclass
import argparse
from pathlib import Path
import sys
import threading
import time
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from keim.analyzer import analyze_program
from keim.backends.cpu import CpuBackend, CpuConfig
from keim.errors import KeimRuntimeError
from keim.parser import parse_file


@dataclass(slots=True)
class KeimDaemonConfig:
    source: Path
    tick_hz: float = 20.0
    seed: int = 42
    quiet: bool = True


class KeimInternalHttpDaemon:
    """Host-Hülle für Keims internes HTTP-Handler-Modell.

    Der Host macht kein URL-Routing. Er lädt das Keim-Programm; die `server`-
    und `route`-Deklarationen starten im CpuBackend eigene ThreadingHTTPServer.
    Der Host tickt nur die Simulation und beendet Ressourcen sauber.
    """

    def __init__(self, config: KeimDaemonConfig) -> None:
        self.config = config
        self.backend = CpuBackend(CpuConfig(seed=config.seed, quiet=config.quiet, collect_metrics=True))
        self.program = parse_file(config.source)
        report = analyze_program(self.program)
        if not report.ok:
            raise KeimRuntimeError(report.format())
        self.backend.load(self.program)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._tick = 0

    @property
    def tick(self) -> int:
        return self._tick

    @property
    def ports(self) -> list[int]:
        return [int(server.server_address[1]) for server in self.backend._http_servers.values()]

    def start_background(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, name="keim-internal-http-daemon", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        delay = 1.0 / max(0.1, self.config.tick_hz)
        while not self._stop.is_set():
            world = self.backend.world
            running = True
            if world is not None and "laufend" in world.memory:
                running = bool(world.memory["laufend"])
            if running:
                self._tick += 1
                # v7.7.1: Der HTTP-Router und der Daemon-Tick teilen sich den
                # Keim-Sprachzustand. Der gleiche Lock wie für Routen verhindert
                # Race Conditions beim /save-Endpoint und bei Tabellen-/JSON-IO.
                lock = getattr(self.backend, "_http_lock", None)
                if lock is None:
                    self.backend.step(self._tick)
                else:
                    with lock:
                        self.backend.step(self._tick)
            self._stop.wait(delay)

    def serve_forever(self) -> None:
        self.start_background()
        try:
            while not self._stop.is_set():
                time.sleep(0.25)
        except KeyboardInterrupt:
            pass
        finally:
            self.close()

    def close(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        self.backend.shutdown_http()


def default_source() -> Path:
    return Path(__file__).resolve().parent / "keim_sources" / "autonome_api_v43.keim"


def create_daemon(source: Path | None = None, *, tick_hz: float = 20.0, seed: int = 42) -> KeimInternalHttpDaemon:
    return KeimInternalHttpDaemon(KeimDaemonConfig(source=source or default_source(), tick_hz=tick_hz, seed=seed))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Autonome Simulations-API mit internem Keim-v4.3-HTTP-Routing")
    parser.add_argument("--source", type=Path, default=default_source())
    parser.add_argument("--tick-hz", type=float, default=20.0)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    daemon = create_daemon(args.source, tick_hz=args.tick_hz, seed=args.seed)
    ports = ", ".join(str(p) for p in daemon.ports) or "<keine>"
    print(f"[Keim] interne HTTP-Dienste aktiv auf Port(s): {ports}")
    daemon.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
