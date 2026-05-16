# Autonome Simulations-API

Neu im Paket:

- Neuer Ordner `autonome_Simulations_API`
- Dauerhafter HTTP-Daemon mit Hintergrund-Simulationsloop
- JSON-Endpunkte für Steuerung, Snapshot, Metrics, Reset, Step und GC
- SoA-Agentenzustand mit optionaler Native-VM-Synchronisation
- Fallback-Modus ohne Native-Bibliothek
- Keim-v4.2-Quellenmodule:
  - `sim_kern.keim`
  - `api_steuerung.keim`
  - `autonome_api.keim`
- Smoke-Test:
  - `autonome_Simulations_API/tests/test_api_smoke.py`
  - `tests/run_autonome_api_tests.py`
