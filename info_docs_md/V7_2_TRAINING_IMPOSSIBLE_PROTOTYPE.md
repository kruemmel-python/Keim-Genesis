# Keim v7.2 Training: Der „unmögliche“ Prototyp

Dieses Schulungsprojekt demonstriert Keim als selbstbeobachtendes Runtime-System:

- Eine Agenten-/Feldsimulation läuft kontinuierlich.
- GUI oder Headless-Control-Signale steuern die Simulation.
- Ein Hintergrundoptimizer erzeugt laufend Policy-Kandidaten.
- Jeder Kandidat wird als didaktischer Bytecode `keim-training-native-policy-bytecode` materialisiert.
- Aus dem Bytecode wird ein Native-VM-Plan erzeugt.
- Metriken, Replay und Dashboard werden als Schulungsartefakte geschrieben.

## Start

```bash
python -m keim training-impossible --steps 120 --out build/training_impossible
```

Interaktiv:

```bash
python -m keim training-impossible --gui --out build/training_impossible_gui
```

## Artefakte

- `metrics.json`
- `optimized_policy.kbc72.json`
- `optimized_policy_native_plan.cpp`
- `training_replay.kreplay.json`
- `training_dashboard.html`
- `report.json`

## Didaktisches Ziel

Das Projekt beantwortet die Frage:

> Was wäre der erste „unmögliche“ Prototyp?

Antwort: Eine Simulation, die live steuerbar ist, während sie im Hintergrund eine eigene Policy optimiert, Bytecode erzeugt und Native-VM-Pläne materialisiert.

## Ehrliche Grenze

Der Native-Plan ist in v7.2 ein didaktischer Optimierungsplan, kein vollständiger JIT. Er ist bewusst klein, hashbar und nachvollziehbar. Die Pipeline ist aber real: Metrik → Kandidat → Bytecode → Native-Plan → Replay/Dashboard.
