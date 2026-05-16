# Keim v7.0 Generational WASM GC Runtime

v7.0 ergänzt die v6.9 Mark/Sweep-WASM-Runtime um einen generationsbasierten, nicht-verschiebenden GC-Kern.

## Kernmechanik

- Nursery-Space mit Bump-Allocator
- Old-Space mit Free-List-Allocator
- Minor GC für kurzlebige Objekte
- Major GC als Full-Heap-Mark/Sweep
- Write-Barrier für old-to-young Referenzen
- Remembered-Set plus Card-Table-Metadaten
- Promotion-Policy über Survivor/Age Counter
- `.kbc70b` mit GEN2GC, SPACES, WBARRIER und REMSET-Sektionen

Der GC bleibt bewusst nicht-verschiebend, damit Tagged-Value-Referenzen, Records, Maps, Result-Objekte und Host-Interop stabil bleiben.
