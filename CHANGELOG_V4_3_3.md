# Keim Genesis v4.3.3 — Partial-Control & GPL-Komfort-Patch

## Fixes

- `POST /control` nutzt jetzt echte partielle Updates:
  - nicht mitgesendete Felder bleiben unverändert
  - `{"running": true}` setzt `wind_signal` und `energy_loss` nicht mehr auf Defaultwerte zurück
- Strukturierte `wenn`-Blöcke überspringen Host-/Skalaraktionen jetzt korrekt, wenn ihre Bedingungsmaske vollständig falsch ist.
  Dadurch funktionieren nicht nur Agentenmasken, sondern auch API-/Service-Logik deterministisch.

## Neue Sprachfunktion

- Karten-Präsenztest als Bedingung:

```keim
wenn karte api_befehl enthaelt "wind_signal":
    karte api_befehl liest "wind_signal" in speicher wind_signal
```

- Karten-Präsenztest als Aktion:

```keim
karte api_befehl enthaelt "running" in speicher hat_running
```

Neue Bytecode-Operation:

```text
MAP_HAS
```

## Neue API-Endpunkte

- `GET /routes`
- `GET /config`
- `POST /save`

`/routes` macht den Dienst introspektierbar.
`/config` liefert die steuerbaren Laufzeitparameter.
`/save` persistiert den Snapshot-Verlauf als JSON-Datei.

## Validierung

- `python tests/run_v43_http_tests.py` → OK
- `python tests/run_tests.py` → OK
- `python scripts/build_native_vm.py` → OK
