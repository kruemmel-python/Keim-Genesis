# Keim Genesis v6.4 Professional Core

v6.4 implementiert den harten Souveränitätsschritt, der nach v6.3 noch offen war: Keim-Ausdrücke werden nicht mehr über Python-AST geparst, sondern durch einen eigenen Keim-Tokenizer und Pratt-Parser in eine Keim-Expression-AST überführt.

## Enthalten

- eigener Keim-Expression-Tokenizer
- eigener Keim-Expression-Parser ohne `ast`/Python-AST
- Expression-AST mit Positionen
- statische Typinferenz für Literale, Listen, Karten, Records, Index, Attribute, lokale/importierte Funktionsaufrufe
- lineares Bytecodeformat `keim-linear-bytecode` Version `640`
- `JUMP`/`JUMP_IF_FALSE` statt verschachtelter Blocklisten
- Slot-Frames mit `LOAD_SLOT`/`STORE_SLOT`
- Bytecode-Verifier mit harter `EVAL`-Ablehnung
- VM64 Interpreter
- `keim-lock-v4`
- JUnit/JSON-Testreport
- Native-C++-Seed und WASM-WAT-Seed

## Neue CLI

```bash
python -m keim v64-expr "a * b + 4" --json
python -m keim v64-check examples/sprache_v64_professional_core.keim
python -m keim v64-bytecode examples/sprache_v64_professional_core.keim --out build/v64/app.kbc64.json
python -m keim v64-run examples/sprache_v64_professional_core.keim --record build/v64/run.kreplay
python -m keim v64-test examples/sprache_v64_professional_core.keim --coverage --junit build/v64/junit.xml
python -m keim v64-build --cwd . --out build/v64_project
python -m keim v64-native build/v64/app.kbc64.json --out build/v64/keimvm64_seed.cpp
python -m keim v64-wasm build/v64/app.kbc64.json --out build/v64/app_seed.wat
```

## Architektur

```text
Keim Source
  -> foundation Parser für Top-Level/Statements
  -> v64 Expression Tokenizer
  -> v64 Expression AST
  -> v64 TypeEnv / ScopeLayout
  -> linear bytecode
  -> verifier
  -> VM64 / native seed / wasm seed
```

## Nicht mehr erlaubt

`EVAL` ist im v6.4-Bytecode verboten. Legacy-Bytecode bleibt in älteren Kompatibilitätsschichten ausführbar, aber der professionelle v6.4-Pfad akzeptiert nur `keim-linear-bytecode`.

## Ehrliche Grenze

Der native C++-Seed validiert und kapselt Bytecode, ist aber noch nicht die finale optimierende native Heap-/String-/Listen-/Map-VM. Der entscheidende Vertrag ist jetzt stabiler: Parser, Typed AST und lineares Bytecodeformat sind nicht mehr Python-AST-abhängig.
