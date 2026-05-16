# Changelog v7.1

## Added

- `keim/compiler71.py`
- `.kbc71b` Binary Container mit `COMPACT`- und `REGION`-Sektionen
- selektiv kompaktierender WASM-GC
- Forwarding Pointer im Objekt-Header
- Root-/Edge-Rewrite-Metadaten
- Region-Allocator für kurzlebige temporäre Werte
- Region Escape Policy
- neue CLI-Kommandos `v71-*`
- neues Beispiel `examples/sprache_v71_compacting_region_gc.keim`
- neue Tests `tests/run_v71_compacting_region_gc_tests.py`

## Guarantees

- kein `EVAL` im v7.1-Bytecode
- WAT-Lowering ohne `unreachable`-Fallback
- Rückwärtskompatible Python-VM-Ausführung über bestehenden VM66/VM70-Pfad

## Known design choice

Der kompaktierende Collector ist selektiv: gepinnte und host-sichtbare Objekte bleiben stabil. Das ist für WASM-/Host-Interop sicherer als ein vollständig bewegender Collector ohne Pinning-Protokoll.
