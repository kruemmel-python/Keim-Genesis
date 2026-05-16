# Keim Genesis v6.1 Compiler Core

v6.1 senkt Ausdrücke im Independent Core in eigene Opcodes ab. Das neue Bytecode-Format `keim-independent-bytecode` nutzt Version `610` und verzichtet im neuen Kern auf die frühere `EVAL`-Instruktion.

## Wichtige Opcodes

- `CONST`, `LOAD_SLOT`
- `ADD`, `SUB`, `MUL`, `DIV`, `MOD`
- `CALL_LOCAL`, `CALL_IMPORTED`, `CALL_BUILTIN`
- `MAKE_LIST`, `MAKE_MAP`, `GET_ITEM`, `GET_ATTR`
- `DECLARE_SLOT`, `STORE_SLOT`, `RETURN`, `ASSERT`

## CLI

```bash
python -m keim check examples/sprache_v61_compiler_runtime.keim
python -m keim core-bytecode examples/sprache_v61_compiler_runtime.keim --json
python -m keim lint examples/sprache_v61_compiler_runtime.keim
python -m keim fmt examples/sprache_v61_compiler_runtime.keim
```

Grenze: Die VM ist weiterhin Python-gehostet. Der Bytecode ist aber näher an einer nativen VM, weil Ausdrucksstrings nicht mehr als `EVAL` ausgeführt werden.
