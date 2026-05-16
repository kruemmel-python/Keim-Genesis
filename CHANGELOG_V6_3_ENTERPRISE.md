# Changelog v6.3 Enterprise

## Neu

- `keim/enterprise.py`
- `enterprise-check`
- `enterprise-build`
- `enterprise-test`
- `enterprise-fmt`
- `enterprise-lint`
- `enterprise-replay`
- `enterprise-native`
- `enterprise-wasm`
- `enterprise-status`
- `ResolvedModuleGraph`
- `ModuleResolver`
- Keim Expression AST
- statische Typinferenz für Kernexpressions
- Enterprise Bytecode Verifier
- `keim-lock-v3`
- JSON/JUnit-Testreports
- Coverage-Grunddaten
- deterministischer Actor-Scheduler
- Native C++ Seed Generator
- WASM WAT Seed Generator
- Tests: `tests/run_v63_enterprise_tests.py`

## Kompatibilität

- v6.0/v6.1/v6.2-Programme bleiben lauffähig.
- Der neue Enterprise-Pfad ist additiv und kann mit bestehenden `core-*`-Kommandos kombiniert werden.
- Bytecode muss weiterhin `keim-independent-bytecode` sein und Version `>=610` haben.

## Harte Sicherheitsregel

`EVAL` ist im Enterprise-Verifier ein Fehler.
