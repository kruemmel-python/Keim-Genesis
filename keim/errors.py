from __future__ import annotations


class KeimError(Exception):
    """Basisklasse für Keim-Fehler."""


class KeimSyntaxError(KeimError):
    def __init__(self, message: str, line: int = 0, text: str = "") -> None:
        self.message = message
        self.line = line
        self.text = text
        where = f"Zeile {line}: " if line else ""
        detail = f"\n    {text}" if text else ""
        super().__init__(f"{where}{message}{detail}")


class KeimRuntimeError(KeimError):
    pass
