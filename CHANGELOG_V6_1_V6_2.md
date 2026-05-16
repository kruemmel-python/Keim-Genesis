# Changelog v6.1/v6.2

## v6.1 Compiler Core

- Expression-Opcodes statt `EVAL`
- Slot-basierte VM-Frames
- Bytecode-Version `610`
- Bytecode-Verifier
- `keim lint`
- `keim fmt`

## v6.2 Runtime Systems

- `core-run --record`
- `core-replay`
- Snapshot speichern/laden
- `kanal<T>`, `sende`, `empfange`
- minimales Actor-Modell
- neues Beispiel `examples/sprache_v61_compiler_runtime.keim`
- neue Tests `tests/run_v61_compiler_runtime_tests.py`

## Kompatibilität

Die ältere v6.0 Foundation-Syntax bleibt für vorhandene Beispiele lauffähig. Native Vollständigkeit ist vorbereitet, aber nicht abgeschlossen.
