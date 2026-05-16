# Keim Genesis v6.6 Enterprise Runtime Completion

v6.6 schließt die sieben offenen v6.5-Blöcke in einer produktionsorientierten Runtime-Schicht.

## 1. Native Runtime Completion

`v66-native` erzeugt eine echte C++-VM für `kbc66`-Programme. Der generierte Interpreter enthält:

- Value-Modell für `nichts`, `ganzzahl`, `kommazahl`, `bool`, `text`
- Listen, Karten, Records und Result-Werte
- Call-Stack über `run_func`
- Kontrollfluss mit `JUMP`, `JUMP_IF_FALSE`, `JUMP_IF_TRUE`
- Builtins `ok`, `fehler`, `ist_ok`
- Native Ausführung des v6.6 Enterprise-Beispiels

## 2. Constant Pool und sectioned Binary Bytecode

`kbc66b` ist ein sectioned Binary Container:

- `META`
- `CONST`
- `TYPE`
- `SYMBOL`
- `FUNC`
- `CODE`
- `DEBUG`
- `PROGRAM`

Der Container besitzt Magic, Version und SHA-256-Präambel.

## 3. Generics

Generische Signaturen aus v6.5 werden durch ein Spezialisierungsmanifest ergänzt. Dieses Manifest beschreibt konkrete Call-Sites als Monomorphisierungs-Kandidaten.

## 4. Result/Match

`ergebnis<T,E>`, `ok`, `fehler` und `match` bleiben statisch geprüft. v6.6 führt sie zusätzlich über Constant-Pool-Bytecode und native Result-Werte.

## 5. Schleifen

Neue Syntax:

```keim
solange i < n:
    ...
    weiter
    abbruch
```

Die Absenkung erfolgt auf lineare Labels und Sprünge.

## 6. Lockfile/Paketbasis

`v66-lock` erzeugt `keim-lock-v5` mit Quellhashes, Paketmanifest und Resolver-Metadaten.

## 7. Deterministisches Replay

`v66-replay` validiert Eventlogs und erzeugt reproduzierbare Event-Hashes. Externe IO-Quellen müssen für vollständiges Replay explizit aufgenommen werden.

## CLI

```bash
python -m keim v66-check examples/sprache_v66_enterprise_full.keim
python -m keim v66-bytecode examples/sprache_v66_enterprise_full.keim --out build/v66/app.kbc66.json --binary-out build/v66/app.kbc66b
python -m keim v66-run examples/sprache_v66_enterprise_full.keim
python -m keim v66-run-bin build/v66/app.kbc66b
python -m keim v66-test examples/sprache_v66_enterprise_full.keim --json --junit build/v66/junit.xml
python -m keim v66-native build/v66/app.kbc66.json --out build/v66/keimvm66.cpp
```

## Grenzen

v6.6 ist eine große Runtime-Completion-Schicht. Noch nicht final sind Registry-Server, vollständige generische Code-Klonung für alle Instanzen, production-grade WASM-Lowering und UI-Time-Travel-Debugging.
