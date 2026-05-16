# Keim Genesis v7.7 – Internal Native Linker

v7.7 beantwortet das Windows/MinGW-Problem grundsätzlich: Keim kann für den Native-MVP-Subset ausführbare Artefakte direkt erzeugen, ohne `g++`, `clang`, `link.exe` oder ein externes Compiler-/Linker-Modul.

## Ziel

Der alte Pfad war:

```text
Keim Bytecode → C++-Quelle → externer Compiler/Linker → .exe/.elf
```

Der neue Pfad ist:

```text
Keim Bytecode → Keim Internal Native Linker → PE64/ELF64 Executable
```

## Unterstützte Ziele

- `elf64-linux-x86_64`
- `pe64-windows-x86_64`

## Unterstützter MVP-Opcode-Subset

- `CONST`
- `TYPE_ASSERT`
- `STORE_SLOT`
- `LOAD_SLOT`
- `ADD`
- `SUB`
- `MUL`
- `DIV`
- `EQ`
- `RETURN`
- `PRINT`
- `JUMP`
- `JUMP_IF_FALSE`

## CLI

```bash
python -m keim native-link-status --json

python -m keim v65-bytecode examples/sprache_v65_native_subset.keim --out build/v77/native_subset.kbc65.json

python -m keim native-link build/v77/native_subset.kbc65.json \
  --out build/v77/keimvm_internal \
  --target elf64-linux-x86_64

python -m keim native-link build/v77/native_subset.kbc65.json \
  --out build/v77/keimvm_internal.exe \
  --target pe64-windows-x86_64
```

## Technischer Kern

Der Linker erzeugt kein C++ mehr. Er schreibt direkt ausführbare Container:

- ELF64 mit Linux-`syscall` für `write`/`exit`
- PE64 mit Import Table für `KERNEL32.dll` und `WriteFile`/`ExitProcess`

Der v6.5-Native-Test nutzt den internen Linker als Fallback, wenn ein lokaler `g++` zwar gefunden wird, aber selbst bei `hello.cpp` stumm mit `returncode=1` endet.

## Grenzen

v7.7 ersetzt externe Toolchains für den kleinen Native-MVP-Subset. Für eine vollständige native Keim-VM mit Heap, Calls, GC, Maps, Records und Debugsymbolen bleibt ein größerer interner Codegen/Assembler/Linker-Ausbau nötig.
