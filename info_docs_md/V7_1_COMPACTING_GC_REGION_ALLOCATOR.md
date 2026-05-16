# Keim Genesis v7.1 Compacting GC + Region Allocator

v7.1 ergänzt den v7.0 Generational-GC um zwei produktionsorientierte Runtime-Optimierungen:

1. **selektiv kompaktierender GC**
2. **regionbasierter Allocator für kurzlebige temporäre Werte**

## Selektiv kompaktierender GC

Der Collector bleibt hybrid: host-sichtbare oder explizit gepinnte Objekte werden nicht bewegt; normale bewegliche Objekte können bei Major-Collections evakuiert und über Forwarding Pointer umgeschrieben werden.

Neue Metadaten:

- `forwarding_ptr` im Objekt-Header
- `region_id` im Objekt-Header
- `COMPACT`-Sektion in `.kbc71b`
- `compact_from` / `compact_to` Spaces

WAT-Intrinsics:

- `$gc_forwarding_ptr`
- `$gc_set_forwarding_ptr`
- `$gc_evacuate_object`
- `$gc_rewrite_value`
- `$gc_update_roots`
- `$gc_update_object_edges`
- `$gc_compact_collect`

## Region-Allocator

Kurzlebige temporäre Werte können in stack-artigen Regionen allokiert werden. Das reduziert GC-Druck für Expression-Temporaries und kurzlebige Zwischenwerte.

WAT-Intrinsics:

- `$region_begin`
- `$region_checkpoint`
- `$region_alloc`
- `$region_reset`
- `$region_end`
- `$region_escape_promote`

## Sicherheitsmodell

- Host-sichtbare Referenzen werden gepinnt.
- Entkommende Region-Werte werden über eine Escape-Policy markiert/promotet.
- Das WAT-Backend behält die `no unreachable fallback`-Eigenschaft bei.
- `.kbc71b` enthält versionierte `COMPACT`- und `REGION`-Sektionen.

## CLI

```bash
python -m keim v71-check examples/sprache_v71_compacting_region_gc.keim
python -m keim v71-bytecode examples/sprache_v71_compacting_region_gc.keim --out build/v71/app.kbc71.json --binary-out build/v71/app.kbc71b
python -m keim v71-wasm build/v71/app.kbc71b --out build/v71/app_compacting_region_gc.wat
python -m keim v71-test examples/sprache_v71_compacting_region_gc.keim --json
```
