# Keim Genesis v6.8 WASM Heap Runtime

v6.8 behebt die bisherige Grenze des WASM-Backends: dynamische Heap-Operationen wie Records, Maps, Listen, Text und Result werden nicht mehr defensiv auf `unreachable` gesenkt.

## Technischer Kern

Keim-WASM nutzt eine Tagged-Value-ABI:

```text
carrier: i64
low 3 bits: tag
payload: integer, bool payload oder heap pointer
```

Tags:

```text
0 = int
1 = bool
2 = null
3 = heap ref
```

Heap-Objekte liegen im linearen WASM-Speicher:

```text
u32 kind
u32 size
u32 aux
u32 reserved
payload...
```

Kinds:

```text
1 = text
2 = list
3 = map
4 = record
5 = result_ok
6 = result_error
```

## Runtime-Intrinsics

Das WAT-Backend erzeugt jetzt Intrinsics wie:

```text
$keim_text_new
$keim_list_new
$keim_list_push
$keim_list_get
$keim_map_new
$keim_map_set
$keim_map_get
$keim_record_new
$keim_record_set
$keim_record_get
$keim_result_ok
$keim_result_error
$keim_result_is_ok
$keim_result_payload
```

## Lowering

Bytecode-Opcodes werden auf Runtime-Aufrufe gesenkt:

```text
MAKE_LIST   -> keim_list_new + keim_list_push
GET_ITEM    -> keim_list_get / keim_map_get
MAKE_MAP    -> keim_map_new + keim_map_set
MAKE_RECORD -> keim_record_new + keim_record_set
GET_ATTR    -> keim_record_get / keim_map_get / result helpers
CALL_BUILTIN ok/fehler/ist_ok -> result helpers
```

## Speicherverwaltung

v6.8 nutzt bewusst einen Bump-Allocator. Das ist kein GC, aber eine robuste erste Runtime-Grundlage. GC, Refcount oder Regionenverwaltung bleiben spätere Ausbaustufen.

## Neue CLI

```bash
python -m keim v68-check examples/sprache_v68_wasm_heap_runtime.keim
python -m keim v68-bytecode examples/sprache_v68_wasm_heap_runtime.keim --out build/v68/app.kbc68.json --binary-out build/v68/app.kbc68b
python -m keim v68-wasm build/v68/app.kbc68b --out build/v68/app_heap_runtime.wat
python -m keim v68-test examples/sprache_v68_wasm_heap_runtime.keim --json
```

## Ehrliche Grenze

Das WAT ist jetzt semantisch vollständig für Text/List/Map/Record/Result-Lowering vorbereitet und enthält keine `unreachable`-Platzhalter für Heap-Opcodes. Es ist noch kein optimiertes GC-WASM und Map nutzt zunächst lineare Suche statt Hash-Tabelle.
