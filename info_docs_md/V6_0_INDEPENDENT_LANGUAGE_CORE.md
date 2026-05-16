# Keim Genesis v6.0 Independent Language Core

v6.0 markiert den Übergang von einer hostnahen Prototypensprache zu einer Sprache mit eigener Zwischenrepräsentation und VM-Schicht.

## Was unabhängig bedeutet

Unabhängig heißt in dieser Version:

- Keim-Source wird zu einem stabilen `.kbc`-JSON-Bytecode kompiliert.
- Der Bytecode enthält Module, Exporte, Imports, Typmetadaten, Funktionen und Instruktionen.
- Eine eigene `IndependentVM` führt Funktionen über Frames, lokale Slots und Keim-Typprüfung aus.
- Python ist aktuell noch Host/Bootstrap, aber nicht mehr die semantische Quelle der Sprache.

## Bytecodeformat

```json
{
  "format": "keim-independent-bytecode",
  "version": 600,
  "entry": "demo.main",
  "modules": {},
  "functions": {}
}
```

Instruktionen:

- `DECLARE`
- `STORE`
- `RETURN`
- `PRINT`
- `ASSERT`
- `EVAL`
- `IF`
- `SNAPSHOT_SAVE`

`EVAL` enthält in v6.0 noch sichere Ausdrucksstrings. Das ist ein bewusster Zwischenschritt: Kontrollfluss, Frames, Module und Typgrenzen sind bereits VM-eigen; die Ausdrucksabsenkung kann später in feinere Opcodes zerlegt werden.

## Projektdatei

```toml
[projekt]
name = "demo"
main = "src/main.keim"

[abhaengigkeiten]
keim.math = "1.2.0"
```

Lockfile:

```powershell
python -m keim lock --cwd .
```

erzeugt:

```json
{
  "format": "keim-lock-v1",
  "packages": [
    {
      "name": "keim.math",
      "version": "1.2.0",
      "sha256": "...",
      "permissions": []
    }
  ]
}
```

## Export

```powershell
python -m keim core-export app.keim --out dist/app
```

Erzeugt:

```text
dist/app/
├─ app.kbc.json
├─ keim_app.py
└─ README_RUN.txt
```

## Native-Ehrlichkeit

v6.0 enthält noch keine vollständige native Single-File-VM. Der entscheidende Schritt ist aber vorbereitet: `.kbc` ist jetzt ein stabiles, hostunabhängiges Artefakt, das eine spätere C++/Rust/WASM-VM direkt laden kann.
