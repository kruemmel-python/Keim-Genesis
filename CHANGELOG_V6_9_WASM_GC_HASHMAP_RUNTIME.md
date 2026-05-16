# Changelog v6.9 WASM GC/Hashmap Runtime

- Neu: `keim/compiler69.py`
- Neu: `.kbc69b` mit `GC`- und `HASHMAP`-Sektionen
- Neu: WAT-Runtime mit nicht-verschiebendem Mark/Sweep-GC
- Neu: Free-List-Allocator mit Bump-Fallback
- Neu: Open-Addressing-Hashmap mit linear probing
- Neu: GC-Tracing für Listen, Records, Result und Maps
- Neu: `examples/sprache_v69_gc_hashmap_runtime.keim`
- Neu: `tests/run_v69_wasm_gc_hashmap_tests.py`
- Neu: CLI-Befehle `v69-*`

Kompatibilität: v6.8-Programme bleiben über v6.9 kompilierbar. v6.9 fügt Runtime-Metadaten hinzu, ohne die Keim-Source-Syntax zu brechen.
