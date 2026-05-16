# Keim Genesis Prototype v2.9

Keim entwickelt sich weiter von einer Simulations-DSL zu einer kleinen Programmiersprache für Feld-, Agenten-, Regel-, Daten- und Objektprogramme.

v2.9 baut auf v2.6 auf und vertieft die Sprache in drei Richtungen:

1. Tabellen als Runtime-Datenstruktur
2. SQLite-Datenbankexport
3. Klassen, Objekte und Methoden mit `selbst`-Eigenschaften

## v2.7 — Tabellen

Neue Syntax:

```keim
tabelle messungen mit tick zahl, risiko zahl, alarm zahl, modus text

jede runde:
    tabelle messungen fuegt tick=zeit risiko=speicher.risiko_max alarm=speicher.alarm modus=aktiv ein
```

Tabellen sind jetzt deklarierte Laufzeitstrukturen. Eine Zeile ist ein strukturierter Datensatz mit festen Spalten. Unterstützte Spaltentypen:

- `zahl`
- `text`

Tabellenwerte können aus Runtime-Quellen gelesen werden:

```keim
tick=zeit
risiko=speicher.risiko_max
hunger=feld.hunger
gefahr=spur.gefahr
schwelle=objekt.alarmwache.schwelle
modus=aktiv
```

Damit entsteht ein erster Datenmodell-Kern: Programme können nicht nur Felder verändern, sondern strukturierte Messreihen erzeugen.

## v2.8 — Datenbanken

Neue Syntax:

```keim
datenbank log bei "out/keim_v29_messungen.sqlite"

jede runde:
    datenbank log speichert tabelle messungen
```

Die CPU-Referenz schreibt Tabellen nach SQLite. Der Export ist inkrementell: Bereits geschriebene Tabellenzeilen werden nicht erneut exportiert.

Im Bytecode erscheinen:

- `ALLOC_DATABASE`
- `DATABASE_SAVE`

Diese Operationen sind bewusst CPU-/Host-Barrieren. Sie gehören nicht in GPU-Batches, sondern markieren Persistenzpunkte.

## v2.9 — Klassen, Objekte und Methoden

Neue Syntax:

```keim
klasse waechter:
    eigenschaft schwelle = 0.18
    methode pruefe:
        wenn speicher risiko_max > selbst.schwelle:
            speicher alarm setzt 1.0
            agent meidet spur gefahr

objekt alarmwache ist waechter mit schwelle=0.16

jede runde:
    objekt alarmwache ruft pruefe
```

Eigenschaften sind skalare Objektwerte. Methoden enthalten normale Keim-Schritte. In Methoden kann `selbst.EIGENSCHAFT` als rechte Vergleichsseite in Bedingungen genutzt werden.

Damit gibt es jetzt ein kleines Objektmodell ohne Python-Objekt-Dispatch pro Agent. Objekte sind Host-seitige Steuerzellen; die agentenbezogenen Daten bleiben weiterhin kompakt in Feldern, Spuren und Speicherwerten.

## Sprachstand nach v2.9

Keim hat nun:

- Werte mit sicheren arithmetischen Ausdrücken
- Imports/Module
- parametrisierte Makro-Bausteine
- benannte Runtime-Regeln
- reine Ausdrucksfunktionen
- native strukturierte Kontrollblöcke
- Wiederholung
- boolesche Bedingungsalgebra
- skalare Zeitspeicher
- aggregierende Speicherzuweisungen
- Ereignisblöcke mit Rising-Edge-Auslösung
- agentenlokale Ausdrucksfelder mit Funktionsaufrufen
- Tabellen mit festem Schema
- inkrementellen SQLite-Export
- Klassen, Objekte, Eigenschaften und Methoden
- `selbst.EIGENSCHAFT` in Objektmethoden
- eingebaute Sprachtests/Kontrakte
- mehrere Backends
- Bytecode-/Kernel-ABI-Planung
- Export/Build-Pfad nach Python

## Schnellstart

```powershell
python run_demo.py
python tests\run_tests.py
```

Neue v2.9-Demo:

```powershell
python -m keim run examples/sprache_v29.keim --backend segmented --rounds 60 --show-every 20
```

Analyse und Bytecode:

```powershell
python -m keim analyze examples/sprache_v29.keim
python -m keim bytecode examples/sprache_v29.keim
python -m keim optimize examples/sprache_v29.keim
```

Sprachtests/Kontrakte:

```powershell
python -m keim test examples/sprache_v29.keim --rounds 30
```

Build:

```powershell
python -m keim build examples/sprache_v29.keim --out out\build_v29
python out\build_v29\runner.py --rounds 40 --backend segmented
```

## Architekturbruch gegenüber v2.6

| Schritt | Vorher | Jetzt | Vorteil | Risiko |
|---|---|---|---|---|
| Datenmodell | Nur Felder, Spuren, Speicher | `tabelle NAME mit ...` | strukturierte Laufzeitdaten | Append-only, noch keine Indizes |
| Persistenz | Trace/JSON über Host-Tools | `datenbank DB speichert tabelle T` | SQLite als echtes Datenbankziel | Host-I/O bremst Simulation |
| Objektmodell | Regeln ohne Instanzzustand | `klasse`, `objekt`, `methode`, `selbst` | steuerbare Instanzen und gekapselte Schwellwerte | noch keine Vererbung, keine freien Objekt-Ausdrücke |

## Sicherheitsgrenzen

Keim v2.9 führt weiterhin keine beliebigen Python-Ausdrücke aus. Ausdrucksfunktionen bleiben sicher geparst. SQLite-Pfade kommen aus dem Keim-Programm; bei untrusted Programmen sollte der Ausführungsordner deshalb isoliert werden.

## Beispiel

```keim
tabelle messungen mit tick zahl, risiko zahl, alarm zahl, modus text
datenbank log bei "out/keim_v29_messungen.sqlite"

klasse waechter:
    eigenschaft schwelle = 0.18
    methode pruefe:
        wenn speicher risiko_max > selbst.schwelle:
            speicher alarm setzt 1.0

objekt alarmwache ist waechter mit schwelle=0.16

jede runde:
    tabelle messungen fuegt tick=zeit risiko=speicher.risiko_max alarm=speicher.alarm modus=aktiv ein
    objekt alarmwache ruft pruefe
    datenbank log speichert tabelle messungen
```


## v3.0 Genesis Engine: Typen, Vererbung, dynamische Allokation, Native-VM

Siehe `examples/sprache_v30.keim` und `CHANGELOG_V3_0.md`.

Native-VM bauen:

```bash
python scripts/build_native_vm.py
```

Native-Kernel direkt testen:

```python
from keim.native_vm import NativeNumericVm, default_native_library
vm = NativeNumericVm(default_native_library())
print(vm.field_add_clamp([0.1, 0.95], 0.1))
```


## v4.2 GPL-Kern

Keim v4.2 ergänzt General-Purpose-Bausteine über den Simulationskern hinaus:

- `karte` und `referenz`
- `versuche` / `fange`
- Mark-and-Sweep-GC für dynamische Objekte
- JSON-Parser und JSON-Serialisierung
- lokaler HTTP-Server
- `zeit`, `krypto`, `prozess`

Siehe `examples/sprache_v42.keim` und `CHANGELOG_V4_2.md`.


## Keim Genesis v6.3 Enterprise Infrastructure

Die v6.3-Ausbaustufe ergänzt die zehn Enterprise-Bausteine:

```bash
python -m keim enterprise-status
python -m keim enterprise-check examples/sprache_v61_compiler_runtime.keim
python -m keim enterprise-build --cwd . --out build/enterprise
python -m keim enterprise-test examples/sprache_v61_compiler_runtime.keim --coverage
python -m keim enterprise-native build/enterprise/app.kbc.json --out build/enterprise/keimvm_seed.cpp
python -m keim enterprise-wasm build/enterprise/app.kbc.json --out build/enterprise/app_seed.wat
```

Dokumentation: `docs/V6_3_ENTERPRISE_INFRASTRUCTURE.md`.
