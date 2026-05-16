# CHANGELOG v2.6

## v2.4 — Ausdrucksfunktionen

- Neuer Top-Level-Knoten `FunctionDecl`
- Neue Syntax: `funktion NAME(a, b) = AUSDRUCK`
- Neue sichere Funktionsaufrufe in `feld NAME wird ...`
- Neuer Bytecode-Op `DEFINE_FUNCTION`
- Funktionsrekursion wird statisch diagnostiziert und zusätzlich zur Laufzeit begrenzt

## v2.5 — Aggregierende Speicher

- Neuer Step-Knoten `MemoryAggregate`
- Neue Syntax:
  - `speicher X liest mittel feld Y`
  - `speicher X liest max feld Y`
  - `speicher X liest min spur Y`
  - `speicher X liest summe spur Y`
- Neuer Bytecode-Op `MEMORY_AGGREGATE`
- Optimierer markiert Aggregate als Reduction-Kandidaten
- Runtime respektiert Masken bei Feldaggregaten und maskierten Spuraggregaten

## v2.6 — Ereignisblöcke

- Neuer Top-Level-Knoten `EventDecl`
- Neue Syntax: `ereignis NAME wenn BEDINGUNG:`
- Ereignisse feuern auf Rising Edge
- Neuer Bytecode-Op `BEGIN_EVENT`
- Runtime zählt ausgelöste Ereignisse in den Backend-Metriken

## Tests

- Neuer Test: `test_v26_functions_aggregates_events`
- Alle bestehenden Tests für v1.x, v2.0 und v2.3 bleiben grün.
