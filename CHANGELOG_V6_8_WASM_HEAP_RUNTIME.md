# Changelog v6.8 WASM Heap Runtime

## Neu

- `keim/compiler68.py`
- Tagged `i64` Value ABI für WASM
- Linear Memory Heap mit Bump-Allocator
- Text-Runtime
- List-Runtime
- Map-Runtime mit linearen Entries
- Record-Runtime mit Layout-Tabelle
- Result-Runtime
- `.kbc68b` mit `HEAP`- und `WASMRT`-Sektionen
- WAT-Lowering für `MAKE_LIST`, `MAKE_MAP`, `MAKE_RECORD`, `GET_ITEM`, `GET_ATTR`, `ok`, `fehler`, `ist_ok`
- neues Beispiel `examples/sprache_v68_wasm_heap_runtime.keim`
- neue Tests `tests/run_v68_wasm_heap_runtime_tests.py`

## CLI

- `v68-status`
- `v68-check`
- `v68-bytecode`
- `v68-run`
- `v68-run-bin`
- `v68-build`
- `v68-test`
- `v68-wasm`

## Behobene Grenze

Dynamische Heap-Opcodes werden im WASM-Backend nicht mehr auf `unreachable` gesetzt.
