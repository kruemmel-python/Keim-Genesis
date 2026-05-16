# Keim Genesis v5.1 Foundation Runtime

v5.1 führt einen zweiten, stabileren Sprachkern ein. Der bisherige Simulations-/Batterie-Kern bleibt kompatibel; der neue Foundation-Kern dient als Grundlage für größere Keim-Programme.

## Ziele

- Modulgraph statt Einzeldatei-Skript
- Funktionen mit Parametern, Rückgabewerten und lokalen Scopes
- Type-IR mit generischer Notation
- Testblöcke als Sprachbestandteil
- reproduzierbarer Projektzustand über `keim.toml` und `keim.lock`
- unabhängiges Bytecodeformat als späteres Ziel für native `keimvm`

## Neue CLI

```powershell
python -m keim check examples/sprache_v60_independent_core.keim
python -m keim core-run examples/sprache_v60_independent_core.keim
python -m keim core-test examples/sprache_v60_independent_core.keim
python -m keim core-bytecode examples/sprache_v60_independent_core.keim --json
python -m keim core-export examples/sprache_v60_independent_core.keim --out build/export_v60_core
python -m keim lock --cwd mein_projekt
```

## Module

```keim
modul demo.math

exportiere funktion addiere

funktion addiere(a ist ganzzahl, b ist ganzzahl) gibt ganzzahl:
    rueckgabe a + b
```

Import:

```keim
modul demo.main

verwende sprache_v51_foundation_runtime als math

funktion main() gibt ganzzahl:
    rueckgabe math.addiere(2, 3)
```

## Funktionen und Scopes

Funktionen besitzen lokale Frames. Parameter und lokale Speicherplätze werden typisiert:

```keim
funktion main() gibt ganzzahl:
    speicher zahlen ist liste<ganzzahl> setzt [1, 2, 3]
    rueckgabe zahlen[0]
```

## Typen

Records:

```keim
typ Benutzer:
    name ist text
    alter ist ganzzahl
```

Unions als Metadaten:

```keim
typ Antwort ist Erfolg | Fehler
```

## Tests

```keim
test "addition":
    pruefe addiere(2, 3) == 5
```

`core-test` führt diese Blöcke über die Foundation-VM aus.

## Grenzen

Der Foundation-Kern ist bewusst klein. Er unterstützt noch nicht die komplette alte Simulationssyntax, sondern bildet einen stabilen neuen Kern für Module, Typen, Funktionen, Tests und Bytecode. Der alte v5.0-Kern bleibt für GUI/FFI/Async/Sandbox/Simulation erhalten.
