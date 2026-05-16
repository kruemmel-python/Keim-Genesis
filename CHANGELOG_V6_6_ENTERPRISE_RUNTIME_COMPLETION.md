# Changelog v6.6 Enterprise Runtime Completion

## Neu

- `keim/compiler66.py`
- `KBC66B` Binary Container mit sectioned layout
- Constant Pool über `CONST_POOL`
- Typ-, Symbol-, Funktions-, Code- und Debug-Sektionen
- `solange`, `weiter`, `abbruch`
- VM66 mit Constant-Pool-Ausführung
- C++ Native VM66 Generator mit Value-Modell
- Native Ausführung von Listen, Maps, Records, Results, Calls und Kontrollfluss
- `keim-lock-v5`
- Replay-Eventlog-Validator
- JUnit/JSON-Testausgabe für v6.6
- Beispiel `examples/sprache_v66_enterprise_full.keim`
- Tests `tests/run_v66_enterprise_runtime_tests.py`

## Neue CLI-Kommandos

- `v66-status`
- `v66-check`
- `v66-bytecode`
- `v66-run`
- `v66-run-bin`
- `v66-build`
- `v66-test`
- `v66-native`
- `v66-lock`
- `v66-replay`

## Kompatibilität

v6.0, v6.1/v6.2, v6.3, v6.4 und v6.5 Regressionstests laufen weiterhin.
