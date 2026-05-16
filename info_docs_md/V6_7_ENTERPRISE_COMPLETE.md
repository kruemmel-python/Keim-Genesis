# Keim Genesis v6.7 Enterprise Complete

v6.7 schließt die in v6.6 ausdrücklich offen gebliebenen Ausbaustufen:

1. Lokaler Registry-Server
2. Paket-Publish/Resolve/Install mit SemVer und SHA-256-Signaturen
3. Vollständige Call-Site-Monomorphisierung beobachteter generischer Instanzen
4. Sectioned Binary Bytecode `.kbc67b` mit GENERIC-Sektion
5. Production-orientiertes WAT/WASM-Lowering für das numerische VM-Subset
6. Grafischer Time-Travel-Debugger als eigenständige HTML-Datei
7. `keim-lock-v6` mit Registry-/Cache-/Signatur-Metadaten

## Registry

```bash
python -m keim v67-registry init --registry .keim/registry
python -m keim v67-registry publish --registry .keim/registry --cwd . --name meine.app --version 1.0.0
python -m keim v67-registry resolve --registry .keim/registry --name meine.app --requirement ^1.0.0
python -m keim v67-registry install --registry .keim/registry --name meine.app --requirement >=1.0.0
python -m keim v67-registry serve --registry .keim/registry --port 8767
```

HTTP-Endpunkte:

- `GET /v1/packages`
- `GET /v1/packages/<name>`
- `GET /v1/packages/<name>/<version>`
- `GET /v1/packages/<name>/<version>/download`
- `GET /v1/resolve/<name>/<requirement>`

## Generische Monomorphisierung

Generische Funktionen wie:

```keim
funktion ident(x ist T) gibt T:
    rueckgabe x
```

werden für beobachtete konkrete Call-Sites in Bytecode-Clones abgesenkt:

```text
demo.v67.ident__T_ganzzahl
```

Die Call-Site wird auf den Clone umgeschrieben. Das macht Native/WASM-Backends einfacher, weil konkrete Instanzen eine konkrete Signatur besitzen.

## Binary Bytecode

`.kbc67b` enthält:

- `META`
- `CONST`
- `TYPE`
- `SYMBOL`
- `GENERIC`
- `FUNC`
- `CODE`
- `DEBUG`
- `PROGRAM`

Die Datei startet mit `KBC67HASH`, enthält einen SHA-256-Hash über den Payload und prüft Section-Längen beim Laden.

## WASM/WAT

`v67-wasm` erzeugt ein WAT-Modul mit Host-Imports:

```wat
(import "keim_host" "print_i64" (func $host_print_i64 (param i64)))
(import "keim_host" "panic" (func $host_panic (param i32)))
```

Das Backend senkt das numerische/control-flow VM-Subset ab. Dynamische Heap-Operationen werden bewusst mit `unreachable` markiert, damit keine falschen WASM-Programme entstehen.

## Time Travel Debugger

`v67-replay --html-out debug.html` erzeugt eine eigenständige HTML-Oberfläche mit:

- Eventliste
- Frame-Navigation
- Play/Pause
- Filter
- Event-JSON
- Diff pro Schritt
- Replay-SHA256

## Grenzen

v6.7 ist deutlich produktionsnäher, aber zwei Grenzen bleiben bewusst transparent:

- WASM-Heapobjekte wie Records/Maps/Lists benötigen ein GC-/Reference-Types-Backend.
- Monomorphisierung erfolgt für beobachtete Call-Sites; exportierte, aber unbenutzte generische APIs bleiben als generische Vorlage erhalten.
