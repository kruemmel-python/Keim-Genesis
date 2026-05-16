from __future__ import annotations

from dataclasses import dataclass, field
import sys
from typing import Any

@dataclass(slots=True)
class GrafikRuntime:
    commands: list[dict[str, Any]] = field(default_factory=list)

    def command(self, kind: str, *args: Any) -> dict[str, Any]:
        item = {"kind": kind, "args": list(args)}
        self.commands.append(item)
        return item

@dataclass(slots=True)
class AudioRuntime:
    muted: bool = False
    events: list[dict[str, Any]] = field(default_factory=list)

    def tone(self, freq: int, duration_ms: int) -> dict[str, Any]:
        event = {"kind": "tone", "freq": int(freq), "duration_ms": int(duration_ms), "muted": self.muted}
        self.events.append(event)
        if not self.muted and sys.platform.startswith("win"):
            try:
                import winsound
                winsound.Beep(int(freq), int(duration_ms))
            except Exception:
                pass
        return event

    def signal(self, name: str) -> dict[str, Any]:
        tones = {"ok": (880, 120), "warnung": (440, 200), "fehler": (220, 250)}
        if name in tones:
            self.tone(*tones[name])
        event = {"kind": "signal", "name": name, "muted": self.muted}
        self.events.append(event)
        return event
