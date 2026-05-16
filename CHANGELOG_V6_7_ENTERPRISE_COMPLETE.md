# Changelog v6.7 Enterprise Complete

## Neu

- `keim/compiler67.py`
- `examples/sprache_v67_full_enterprise.keim`
- `tests/run_v67_enterprise_complete_tests.py`
- `docs/V6_7_ENTERPRISE_COMPLETE.md`

## CLI

- `v67-status`
- `v67-check`
- `v67-bytecode`
- `v67-run`
- `v67-run-bin`
- `v67-build`
- `v67-test`
- `v67-wasm`
- `v67-lock`
- `v67-registry`
- `v67-replay`

## Features

- Lokale HTTP-Registry
- Publish/Resolve/Install
- SemVer-Ranges `*`, `>=`, `^`, `~`
- SHA-256-Paketsignaturen
- Paketcache
- `keim-lock-v6`
- Call-Site-Monomorphisierung generischer Funktionen
- `.kbc67b` mit GENERIC-Sektion
- WAT-Lowering für numerische Opcodes
- HTML-Time-Travel-Debugger

## Tests

- Bytecode/Binary/Monomorphisierung
- Run aus Source und Binary
- WAT-Erzeugung
- Registry Init/Publish/Resolve/Install
- HTTP-Registry-Smoke-Test
- Replay-to-HTML-Debugger
