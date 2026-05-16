# autonome_Simulations_API

Erstes vollständiges Anwendungsprogramm für Keim Genesis v4.2: ein dauerhafter Simulations-Daemon mit JSON/HTTP-Steuerung, Hintergrund-Loop und optionaler Native-Hotspot-Ausführung.

## Start

Vom Projektroot:

```bash
python autonome_Simulations_API/api_service.py --host 127.0.0.1 --port 8080
```

Die API nutzt automatisch `build/native/keim_vm_native.*`, falls die Native-VM gebaut ist. Ohne native Bibliothek läuft derselbe Dienst im Python-Fallback.

## Endpunkte

```text
GET  /health
GET  /snapshot
GET  /metrics
GET  /control
POST /control
POST /step
POST /reset
POST /command
POST /gc
```

Beispiele:

```bash
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/snapshot
curl -X POST http://127.0.0.1:8080/control \
  -H "Content-Type: application/json" \
  -d '{"running":false,"wind_x":2,"energy_delta":-0.002}'
curl -X POST http://127.0.0.1:8080/step \
  -H "Content-Type: application/json" \
  -d '{"rounds":10}'
```

## Architektur

```text
api_service.py
  ThreadingHTTPServer, JSON-Mapping, Fehlerantworten

sim_engine.py
  Background-Loop, Command-Queue, SoA-State, NativeAgentStore-Synchronisation

keim_sources/
  sim_kern.keim          Simulationslogik als Keim-Makromodul
  api_steuerung.keim     JSON/HTTP/GC-Steuerlogik als Keim-Makromodul
  autonome_api.keim      zusammenführbares Keim-v4.2-Programm
```

## SoA- und Hotspot-Verhalten

Der Dienst hält Agenten im Structure-of-Arrays-Layout:

```text
x[]
y[]
energy[]
alive[]
```

Wenn die Native-VM verfügbar ist, wird dieser Zustand in `NativeAgentStore` importiert. Der Hintergrund-Loop ruft dann den C++-Opcode-Dispatcher auf. Parameter wie `wind_x`, `wind_y` und `energy_delta` werden als unmittelbare Hotspot-Parameter injiziert.

## Externer GPU-C-Treiber

Der Treiber wird nicht mitgeliefert. In `config.json` kann `gpu_driver_path` gesetzt werden. Der Dienst prüft dann beim Reset, ob die v4.1/v4.2-GPU-Bridge den Treiber laden kann. Ohne Treiber bleibt die API funktionsfähig.

## Keim-v4.2-Sprachseite prüfen

```bash
python -m keim.cli autonome_Simulations_API/keim_sources/autonome_api.keim
```

Oder über die Tests:

```bash
python autonome_Simulations_API/tests/test_api_smoke.py
```


## v4.3: internes Keim-Routing

Die frühere `api_service.py` bleibt als Host-Kompatibilitätsschicht erhalten. Der neue bevorzugte Startpunkt ist:

```bash
python autonome_Simulations_API/keim_daemon.py
```

Dabei liegt das Routing nicht mehr in Python-`match`-Blöcken, sondern im Keim-Programm:

```text
autonome_Simulations_API/keim_sources/autonome_api_v43.keim
```

Beispielsyntax:

```keim
server api bei 18080 parallel 8:
    route GET "/health" antwortet speicher antwort:
        karte api_status setzt "ok" auf wahr
        json schreibt speicher api_status in speicher antwort

    route POST "/control" liest speicher eingang_json antwortet speicher antwort status speicher status_code:
        versuche:
            json liest speicher eingang_json in speicher api_befehl
            karte api_befehl liest "running" in speicher laufend
        fange fehler in speicher api_fehler:
            speicher status_code setzt 400
        json schreibt speicher api_status in speicher antwort
```

Der Host-Daemon tickt nur die Simulation; Request-Body, JSON-Parsing, Fehlerfang, Statuscode und Response werden in Keim ausgeführt.


## v4.3.3 Ergänzungen

Die Control-API unterstützt jetzt echte partielle Updates. Beispiel:

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:18080/control" -ContentType "application/json" -Body '{"wind_signal":0.05}'
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:18080/control" -ContentType "application/json" -Body '{"running":true}'
```

`wind_signal` bleibt dabei erhalten, weil die Keim-Route vor dem Lesen einzelner JSON-Felder prüft:

```keim
wenn karte api_befehl enthaelt "wind_signal":
    karte api_befehl liest "wind_signal" in speicher wind_signal
```

Neue Endpunkte:

```text
GET  /routes
GET  /config
POST /save
```

`POST /save` schreibt den Snapshot-Verlauf nach:

```text
autonome_Simulations_API/state_snapshot.json
```
