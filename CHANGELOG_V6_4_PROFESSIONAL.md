# Changelog v6.4 Professional

## Compiler

- eigener Keim-Expression-Tokenizer
- eigener Keim-Expression-Parser ohne Python-AST
- Expression-AST mit Positionen
- statische Typinferenz für Kernsyntax
- Record-Konstruktoren mit benannten Feldern
- strenge Import-/Exportprüfung bei importierten Funktionsaufrufen

## Bytecode

- neues Format `keim-linear-bytecode`
- Version `640`
- lineare Instruktionsliste mit Sprungadressen
- `JUMP` und `JUMP_IF_FALSE`
- `LOAD_SLOT` und `STORE_SLOT`
- `MAKE_RECORD`, `MAKE_LIST`, `MAKE_MAP`, `CALL`, `CALL_BUILTIN`
- `EVAL` wird vom Verifier abgelehnt

## Runtime

- VM64 Interpreter
- deterministische Events
- Snapshot v64
- Replay-Eventlog v64
- Kanal-Builtins für `kanal`, `sende`, `empfange`

## Tooling

- `v64-status`
- `v64-expr`
- `v64-check`
- `v64-bytecode`
- `v64-run`
- `v64-build`
- `v64-test`
- `v64-lint`
- `v64-fmt`
- `v64-native`
- `v64-wasm`

## Tests

- `tests/run_v64_professional_tests.py`
- C++ syntax check für generierten Native-Seed
- Regression gegen v6.3, v6.1/v6.2 und v6.0

## Projektmodell

- `keim.toml`
- `keim-lock-v4`
- Dateihashes für `.keim`-Quellen
