# Unterrichtsplan

## Modul 1 — Simulation als kontrolliertes System

- Felder: Nahrung und Gefahr
- Agentenzustand: Energie und Hunger
- Kontrollsignal: Wanderung, Food-Follow, Danger-Avoid, Diffusion

## Modul 2 — GUI als Runtime-Steuerung

- Slider verändern Kontrollsignale
- Simulation reagiert sofort
- Optimizer kann GUI-Signale übernehmen oder übersteuern

## Modul 3 — Bytecode im Hintergrund

- Optimizer erzeugt Policy-Kandidaten
- Jeder Kandidat wird in `keim-training-native-policy-bytecode` materialisiert
- Hash macht Kandidaten reproduzierbar

## Modul 4 — Native-VM-Brücke

- Native-Plan wird als C++-Symbol erzeugt
- Der Plan ist minimal, aber buildbar und didaktisch überprüfbar

## Modul 5 — Replay und Time-Travel-Grundlage

- `training_replay.kreplay.json` enthält Simulation- und Optimizer-Events
- Dashboard zeigt Verlauf und beste Policy

## Übung

Ändere die Zielfunktion in `BackgroundBytecodeOptimizer._score` und beobachte, wie sich die Simulation selbst anders steuert.
