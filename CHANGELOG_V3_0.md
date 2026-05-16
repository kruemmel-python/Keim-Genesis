# Keim Genesis v3.0

## Implementiert

- Erweitertes Typsystem:
  - `zahl`, `ganzzahl`, `bool`, `text`, `array`
  - Felder: `feld alter ganzzahl startet bei 1`
  - Speicher: `speicher alarm bool startet bei falsch`
  - Eigenschaften: `eigenschaft modus text = wach`
  - Tabellen: `tabelle log mit tick ganzzahl, alarm bool, daten array`
- Klassenvererbung:
  - `klasse spezial_waechter ist waechter:`
  - Eigenschaften und Methoden werden vererbt; Kindmethoden überschreiben Elternmethoden.
- Dynamische Laufzeitallokation:
  - `erzeuge agent`
  - `erzeuge 10 agenten`
  - `loesche 3 agenten`
  - `loesche aktive agenten`
  - `erzeuge objekt NAME ist KLASSE mit eigenschaft=wert`
- Bytecode-Erweiterung:
  - neue Ops `SPAWN_AGENTS`, `KILL_AGENTS`, `SPAWN_OBJECT`
  - typisierte `ALLOC_FIELD`/`ALLOC_MEMORY`
  - `DEFINE_CLASS` trägt Parent und typisierte Properties.
- Native-VM-Pfad:
  - `native/keim_vm_native.cpp` enthält eine C-ABI für numerische Hotspot-Kerne.
  - `scripts/build_native_vm.py` baut `libkeim_vm_native.so`/`.dll`/`.dylib`.
  - `keim.native_vm.NativeNumericVm` lädt die Bibliothek per `ctypes`.
  - `backend="native"` ist als stabiler Laufzeitmodus registriert.

## Semantik

- Numerische Felder bleiben clamp-basiert, aber `ganzzahl` rundet auf Integer und `bool` bleibt echter boolescher Zustand.
- Ausdrucksauswertung behandelt nichtnumerische Werte bei Vergleichen/Aggregaten über eine definierte Projektion nach Float.
- Dynamische Agenten erweitern alle Feld-SoA-Arrays konsistent und halten `world.agents`, Positionen und Ruhemaske synchron.
- Dynamisches Löschen entfernt Agenten aus allen SoA-Arrays; Maskenbedingungen können die zu entfernende Gruppe bestimmen.

## Grenzen

- Der native C++-Interpreter deckt aktuell numerische Hotspot-Primitive ab, nicht die vollständige Keim-Semantik.
- Text- und Array-Felder sind bewusst zugelassen, aber nicht für GPU-Kerne geeignet.
- Dynamische Objekt-Erzeugung mit gleichem Namen ist idempotent, damit Schleifen nicht permanent kollidieren.
