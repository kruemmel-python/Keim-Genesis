# Keim Genesis v4.3.2 — Autonome API Metrics Route Fix

## Behoben

- `autonome_Simulations_API/keim_sources/autonome_api_v43.keim` registriert jetzt `GET /metrics`.
- Die Route liefert Runtime-Metriken direkt aus dem Keim-internen HTTP-Router:
  - `ok`
  - `service`
  - `round`
  - `running`
  - `agents`
  - `energy_mean`
  - `energy_min`
  - `wind_signal`
  - `energy_loss`

## Tests

- `tests/run_v43_http_tests.py` prüft jetzt `GET /metrics` im v4.3-Daemon-Test.
- Validiert mit:
  - `python tests/run_v43_http_tests.py`
  - `python tests/run_tests.py`
