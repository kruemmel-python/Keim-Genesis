# Keim Genesis v6.3 Enterprise Infrastructure

Diese Version baut die zehn geforderten Bausteine nicht als reine Syntax-Demos, sondern als zusammenhängende Infrastruktur aus. Der neue Code liegt vor allem in `keim/enterprise.py` und ist über eigene CLI-Kommandos erreichbar.

## 1. Modulgraph

`ModuleResolver` erzeugt einen `ResolvedModuleGraph` mit:

- Export-/Private-Symboltabellen
- Import-Alias-Prüfung
- Importzyklusdiagnose
- Abhängigkeitssätzen
- Paketpfad-/Cache-Key-Berechnung
- sichtbaren `ModuleRef`-Tabellen pro Modul

CLI:

```bash
python -m keim enterprise-check examples/sprache_v61_compiler_runtime.keim
```

## 2. Funktionen + Scopes

Die vorhandenen slot-basierten Frames werden durch Enterprise-Analyse ergänzt:

- Shadowing-Warnungen
- unbekannte Zuweisungsziele
- garantierte Rückgabepfadanalyse
- lokale Type-Umgebung pro Funktion
- Typprüfung bei `let`, `set`, `return`, `if`, `assert`, `send`

## 3. Type-IR

Neu ist ein Keim-Expression-AST mit Typinferenz:

- `ConstExpr`
- `NameExpr`
- `BinExpr`
- `BoolExpr`
- `CompareExpr`
- `ListExpr`
- `MapExpr`
- `AttrExpr`
- `IndexExpr`
- `CallExpr`

Unterstützt werden unter anderem:

- `ganzzahl`, `kommazahl`, `bool`, `text`, `nichts`
- `liste<T>`
- `karte<K,V>`
- `kanal<T>`
- Record-Konstruktoren
- modulübergreifende Funktionssignaturen
- benannte Record-Felder über `Name(field: wert)`-Rewriting

## 4. Bytecode-VM

`EnterpriseBytecodeVerifier` prüft `.kbc.json`:

- Format
- Version >= 610
- vollständiges Verbot von `EVAL`
- bekannte Opcodes
- Argumentanzahl pro Opcode
- Slotvalidität

## 5. Projektdatei + Lockfile

`EnterpriseProject` erzeugt `keim-lock-v3` mit:

- Projektmetadaten
- Dateihashes aller `.keim`-Quellen
- Paketliste
- Buildprofilen
- Buildmanifest

CLI:

```bash
python -m keim enterprise-build --cwd . --out build/enterprise
```

## 6. Testsystem

`enterprise-test` bietet:

- Einzeldatei- oder Projektmodus
- Filter
- JSON-Report
- JUnit-Report
- einfache Funktions-Coverage

CLI:

```bash
python -m keim enterprise-test examples/sprache_v61_compiler_runtime.keim --coverage --json-out build/tests.json --junit-out build/tests.xml
```

## 7. Formatter/Linter

`enterprise-fmt` und `enterprise-lint` ergänzen die v6.2-Basis:

- Import-/Export-Sortierung
- stabile Leerzeilen
- Typdiagnostik
- Scope-Warnungen
- ungenutzte Variablen
- Modulwarnungen

## 8. Snapshot/Replay

`enterprise-replay` validiert Replay- und Snapshot-Dateien:

- Formatprüfung
- Eventzählung
- Eventtypen
- monotone Zeitprüfung
- Strict-Modus

## 9. Actor/Kanalmodell

Die v6.2-Kanäle/Actors werden durch `DeterministicActorScheduler` ergänzt:

- deterministische Ready-Queue
- priorisierte Zustellung
- Deadlock-/Fehlziel-Liste
- replaybare Scheduler-Events

## 10. Native/WASM

Neue Seed-Generatoren:

```bash
python -m keim enterprise-native build/enterprise/app.kbc.json --out build/enterprise/keimvm_seed.cpp
python -m keim enterprise-wasm build/enterprise/app.kbc.json --out build/enterprise/app_seed.wat
```

Die Generatoren akzeptieren nur validierten Bytecode ohne `EVAL`.

## Test

```bash
python -S tests/run_v63_enterprise_tests.py
```

Erwartung:

```text
[Keim v6.3 Enterprise] Tests OK
```
