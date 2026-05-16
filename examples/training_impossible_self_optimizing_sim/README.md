# Schulungsprojekt: Der „unmögliche“ Keim-Prototyp

Dieses Beispiel zeigt eine Simulation, die über eine GUI steuerbar ist, während ein Hintergrundprozess fortlaufend Policy-Kandidaten optimiert, Bytecode erzeugt und daraus einen Native-VM-Plan ableitet.

## Lernziel

Die Teilnehmenden sehen in einem einzigen Projekt:

1. Agenten-/Feldsimulation
2. GUI-Steuerung als Kontrollsignal
3. Hintergrund-Optimizer
4. Bytecode-Artefakte
5. Native-VM-Plan
6. Replay/Eventlog
7. Dashboard für Schulungsanalyse

## Headless ausführen

```bash
python -m keim training-impossible --steps 120 --out build/training_impossible
```

## GUI starten

```bash
python -m keim training-impossible --gui --out build/training_impossible_gui
```

## Erwartete Artefakte

- `metrics.json`
- `optimized_policy.kbc72.json`
- `optimized_policy_native_plan.cpp`
- `training_replay.kreplay.json`
- `training_dashboard.html`
- `report.json`

## Warum dieses Beispiel wichtig ist

Keim wird hier nicht nur als Sprache gezeigt, sondern als selbstbeobachtendes Runtime-System:
Die laufende Simulation erzeugt Signale, der Optimizer erzeugt daraus Bytecode, und die Native-VM-Schicht bekommt sofort eine optimierte Planrepräsentation.
