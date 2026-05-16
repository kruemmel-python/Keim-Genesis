from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .errors import KeimRuntimeError

PERMISSION_ALIASES = {
    "netz": "netz", "net": "netz", "network": "netz", "system.netz": "netz", "http": "netz",
    "io": "io", "datei": "io", "filesystem": "io", "system.io": "io",
    "prozess": "prozess", "process": "prozess", "system.prozess": "prozess",
    "ffi": "ffi", "system.ffi": "ffi",
    "gui": "gui", "grafik": "gui", "system.grafik": "gui",
    "audio": "audio", "system.audio": "audio",
}

@dataclass(slots=True)
class SandboxPolicy:
    mode: str = "permissive"
    allowed: set[str] = field(default_factory=set)
    requested: set[str] = field(default_factory=set)

    @classmethod
    def from_cli(cls, mode: str = "permissive", allow: Iterable[str] = ()) -> "SandboxPolicy":
        return cls(mode=mode, allowed={normalize_permission(x) for x in allow})

    def merged(self, requested: Iterable[str]) -> "SandboxPolicy":
        return SandboxPolicy(mode=self.mode, allowed=set(self.allowed), requested={normalize_permission(x) for x in requested})

    def require(self, permission: str, detail: str = "") -> None:
        perm = normalize_permission(permission)
        if self.mode != "strict":
            return
        if perm not in self.allowed:
            suffix = f" ({detail})" if detail else ""
            raise KeimRuntimeError(f"Sandbox verweigert Berechtigung {perm!r}{suffix}. Starte mit --allow {perm} oder nutze --sandbox permissive.")

def normalize_permission(raw: str) -> str:
    key = raw.strip().lower()
    if key not in PERMISSION_ALIASES:
        raise ValueError(f"Unbekannte Berechtigung: {raw!r}")
    return PERMISSION_ALIASES[key]
