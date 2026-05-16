from __future__ import annotations

from .analyzer import analyze_program
from .parser import parse_source
from .runtime import RunOptions, run_program


HELP = """Keim-REPL
Befehle:
  :help              Hilfe anzeigen
  :show              aktuellen Quelltext anzeigen
  :clear             Puffer leeren
  :analyze           statische Analyse ausführen
  :run [runden]      Programm ausführen
  :quit              beenden

Normale Zeilen werden zum Keim-Programm hinzugefügt.
"""


def repl() -> int:
    print(HELP)
    lines: list[str] = []
    while True:
        try:
            line = input("keim> ")
        except EOFError:
            print()
            return 0
        cmd = line.strip()
        if not cmd:
            continue
        if cmd == ":quit":
            return 0
        if cmd == ":help":
            print(HELP)
            continue
        if cmd == ":show":
            print("\n".join(lines))
            continue
        if cmd == ":clear":
            lines.clear()
            print("[Keim] Puffer geleert.")
            continue
        if cmd == ":analyze":
            try:
                print(analyze_program(parse_source("\n".join(lines), source_name="<repl>")).format())
            except Exception as exc:
                print(f"[Keim] Fehler: {exc}")
            continue
        if cmd.startswith(":run"):
            parts = cmd.split()
            rounds = int(parts[1]) if len(parts) > 1 else 20
            try:
                program = parse_source("\n".join(lines), source_name="<repl>")
                run_program(program, RunOptions(rounds=rounds, show_every=max(1, rounds // 2), backend="segmented"))
            except Exception as exc:
                print(f"[Keim] Fehler: {exc}")
            continue
        lines.append(line)
