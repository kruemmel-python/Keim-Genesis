# Keim Genesis v6.5 Native / Generics / Result / Match / Binary Bytecode

v6.5 erweitert den v6.4 Professional Core um vier harte Produktionsbausteine:

1. generische Funktionssignaturen über Typvariablen
2. `ergebnis<T, E>` mit `ok(...)`, `fehler(...)`, `ist_ok(...)`
3. `match` mit Exhaustiveness-Prüfung für `ok`/`fehler`
4. binäres `.kbc65b`-Bytecodeformat mit Magic, Version, Größe und SHA-256-Prüfung
5. native C++ `keimvm65`-MVP-Generierung für ein echtes ausführbares Integer/Bool-Opcode-Subset

## Generics

Generische Funktionen nutzen Typvariablen als Typnamen:

```keim
funktion ident(x ist T) gibt T:
    rueckgabe x
```

Der v6.5-Typechecker unifiziert `T` an der Call-Site:

```keim
speicher a ist ganzzahl setzt ident(21)
```

## Result

```keim
funktion teile(a ist ganzzahl, b ist ganzzahl) gibt ergebnis<ganzzahl, text>:
    wenn b == 0:
        rueckgabe fehler("division durch null")
    sonst:
        rueckgabe ok(a // b)
```

## Match

```keim
funktion entpacke(r ist ergebnis<ganzzahl, text>) gibt ganzzahl:
    match r:
        fall ok(wert):
            rueckgabe wert
        fall fehler(meldung):
            rueckgabe 0
```

Der Compiler verlangt bei `ergebnis<T,E>` entweder beide Fälle `ok` und `fehler` oder einen `_`/`sonst`-Fall.

## Binary Bytecode

```bash
python -m keim v65-bytecode app.keim --out build/app.kbc65.json --binary-out build/app.kbc65b
python -m keim v65-run-bin build/app.kbc65b
```

Das Format `KBC65B` enthält:

- Magic `KBC65B\0\1`
- Version `650`
- Payload-Länge
- SHA-256 über JSON-Payload
- canonical JSON-Bytecode-Payload

## Native keimvm65 MVP

```bash
python -m keim v65-native build/native_subset.kbc65.json --out build/keimvm65.cpp
g++ -std=c++20 build/keimvm65.cpp -o build/keimvm65
./build/keimvm65
```

Der native MVP führt ein echtes VM-Subset aus:

- `CONST_INT`
- `CONST_BOOL`
- `LOAD_SLOT`
- `STORE_SLOT`
- `ADD`
- `SUB`
- `MUL`
- `EQ`
- `JUMP`
- `JUMP_IF_FALSE`
- `PRINT`
- `RETURN`

Grenze: der native MVP ist absichtlich klein. Heap, Strings, Listen, Maps, Records, Calls und Result-Match im Native-Backend sind nächste Ausbaustufe.
