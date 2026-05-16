# Keim Genesis v6.9 WASM GC/Hashmap Runtime

v6.9 ersetzt den v6.8 Bump-Allocator/Linear-Map-Kern durch einen professionelleren WASM-Runtime-Kern.

## Runtime-Kern

- Tagged `i64` Value ABI bleibt stabil.
- Heap-Header wird auf GC-Metadaten erweitert.
- Nicht-verschiebender Mark/Sweep-GC.
- Free-List-Allocator mit Bump-Fallback.
- Allocation-Threshold löst GC aus.
- Graph-Tracing für Listen, Records, Result und Maps.
- Maps nutzen Open Addressing mit linear probing statt linearer Entry-Liste.
- `.kbc69b` enthält eigene `GC`- und `HASHMAP`-Sektionen.

## Objekt-Header

```text
kind      u32 @ 0
size      u32 @ 4
aux       u32 @ 8
flags     u32 @ 12  # mark/pinned/generation
next_free u32 @ 16
payload       @ 24
```

## Hashmap Entry

```text
key   i64 @ 0
value i64 @ 8
state u32 @ 16  # empty/occupied/tombstone
hash  u32 @ 20
```

## CLI

```bash
python -m keim v69-bytecode examples/sprache_v69_gc_hashmap_runtime.keim --out build/v69/app.kbc69.json --binary-out build/v69/app.kbc69b
python -m keim v69-wasm build/v69/app.kbc69b --out build/v69/app_gc_hashmap_runtime.wat
python -m keim v69-test examples/sprache_v69_gc_hashmap_runtime.keim --json
```

## Ehrliche Grenze

Der GC ist nicht verschiebend und damit bewusst einfacher als ein kompaktierender GC. Das ist für WASM und Pointer-Stabilität korrekt. Eine spätere v7 kann generationsbasierte oder kompaktierende Strategien einführen.
