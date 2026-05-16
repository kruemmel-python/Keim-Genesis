# Changelog v7.7.1 HTTP Save Concurrency Fix

- Serialisiert den internen v4.3 HTTP-Daemon-Tick mit HTTP-Routen über denselben Backend-Lock.
- Schreibt Tabellenexporte aus einem stabilen Snapshot statt direkt aus der live mutierten Tabellenliste.
- Nutzt atomare Temporary-File-Ersetzung beim Tabellenexport.
- Ziel: Windows-Timeouts beim `/save`-Endpoint in `tests/run_v43_http_tests.py` verhindern.
- GPU-Treiberintegration und interner Native-Linker bleiben unverändert.
