# Keim Genesis v4.3 — Internes HTTP-Handler-Modell

v4.3 schließt die v4.2-Lücke zwischen HTTP-Batterie und echter Anwendungsplattform.

## Neu

- Top-Level-HTTP-Dienste:
  - `server NAME bei PORT parallel WORKERS:`
  - mehrere `route METHOD "/pfad"`-Blöcke pro Dienst
- Interne Handler-Registry im Keim-CPU-Backend
- Parallele Handler-Ausführung über `ThreadingHTTPServer`
- Deterministische Zustandsmutation über Runtime-`RLock`
- Request-Mapping:
  - `route POST "/x" liest speicher BODY ...`
  - Body wird in Keim-Speicher injiziert
  - optionale Metadaten-Speicher: `anfrage_methode`, `anfrage_pfad`, `anfrage_query`, `anfrage_header`
- Response-Mapping:
  - `antwortet speicher RESPONSE`
  - optional `status speicher STATUS_CODE`
- Bytecode:
  - `HTTP_SERVICE_START`
  - `HTTP_ROUTE`
- Analyzer-Prüfungen für:
  - doppelte Routen
  - ungültige Ports
  - unbekannte Request-/Response-/Status-Speicher
- Explizites `CpuBackend.shutdown_http()` für Tests und Daemons

## Autonome Simulations-API

Neuer interner Dienst:

```text
autonome_Simulations_API/
├─ keim_daemon.py
└─ keim_sources/
   └─ autonome_api_v43.keim
```

`keim_daemon.py` macht kein URL-Routing mehr. Der Host lädt nur das Keim-Programm, startet den internen Keim-HTTP-Dienst und tickt die Simulation.

## Validierung

- `tests/run_v43_http_tests.py`
- `tests/run_tests.py` ruft v4.3-Tests mit auf

## Bekannte Grenze

Die Handler laufen parallel auf HTTP-Ebene, aber mutierende Keim-State-Zugriffe werden absichtlich serialisiert. Das erhält deterministische Semantik. Für zukünftige Versionen kann ein isolierter Handler-Modus mit Copy-on-Write-Speicher ergänzt werden.
