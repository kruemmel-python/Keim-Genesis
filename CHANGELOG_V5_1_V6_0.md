# Keim Genesis v5.1 Foundation Runtime + v6.0 Independent Language Core

## Neu

- Neuer Foundation-Sprachkern `keim.foundation`
- Modulgraph mit `modul`, `verwende`, `exportiere`
- Funktionen mit Parametern, Rückgabewerten und lokalen Scopes
- Type-IR: `TypeRef`, generische Typnotation, Record-Typen und Union-Metadaten
- Independent Bytecode Format `.kbc.json`
- `IndependentVM` mit Frames, lokalen Variablen, Runtime-Typprüfung und Testausführung
- Sprachtests über `test "name":`
- Projekt-Lockfile über `keim lock`
- Export via `core-export`
- Neue CLI-Befehle:
  - `check`
  - `core-run`
  - `core-test`
  - `core-bytecode`
  - `core-export`
  - `lock`

## Beispiele

- `examples/sprache_v51_foundation_runtime.keim`
- `examples/sprache_v60_independent_core.keim`

## Tests

- `tests/run_v60_independent_core_tests.py`
- `tests/run_tests.py` bindet v6-Test ein

## Bewusste Grenzen

- Der alte v5.0-Kern bleibt bestehen und ist weiterhin für Simulation/GUI/FFI/Async zuständig.
- Der neue Independent-Core unterstützt eine kleinere, sauberere Sprachbasis.
- Eine echte native `keimvm` ist vorbereitet, aber noch nicht vollständig implementiert.
- Ausdrucke werden in v6.0 noch über sichere AST-Auswertung innerhalb der VM ausgeführt; spätere Versionen können diese in feinere Opcodes absenken.
