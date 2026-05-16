# GitHub Cleanup Report

## Ergebnis

Dieses Verzeichnis wurde als GitHub-taugliche Quellcodefassung aus dem gelieferten ZIP erzeugt.

## Geändert

- `README.md` auf aktuellen Projektstand **v7.8.5** gebracht.
- Frühere v2.9-README nach `docs/README_LEGACY_V2_9.md` verschoben.
- `.gitignore` und `.gitattributes` ergänzt.
- `pyproject.toml` mit `build-system`, aktueller Version und Paketfindung ergänzt.
- `keim/cli.py` um `python -m keim.cli`-Startpfad ergänzt.
- Lokaler Runtime-Snapshot `autonome_Simulations_API/state_snapshot.json` entfernt.

## Entfernt / nicht übernommen

- `150` generierte oder lokale Dateien
- ca. `6.56 MiB` Binär-/Build-/Cache-/Runtime-Artefakte

Dazu gehören insbesondere:

- top-level `build/`
- `driver/build/`
- vorkompilierte `.dll`, `.so`, `.lib`, `.exp`
- Logs und lokale Snapshots
- Python-Bytecode/Caches

## Validierung in der Sandbox

- `python -m compileall -q keim tests`: erfolgreich
- Vollständiger `tests/run_tests.py`: in der Sandbox nicht abgeschlossen; vermutlich wegen Laufzeit/optionalem Umfang. Vor Release lokal erneut ausführen.

## Vor GitHub-Upload empfohlen

1. Lizenzentscheidung prüfen: `LICENSE.txt` ist aktuell nur eine Prototype-Lizenz.
2. Öffentlichkeitsfähigkeit der Driver-/OpenCL-Header und des großen `driver/src/CC_OpenCL.c` prüfen.
3. Lokal mit Python 3.12 testen.
4. Optional Git initialisieren:

```bash
git init
git add .
git commit -m "Prepare Keim Genesis prototype for GitHub"
```


## Nachtrag v7.8.5

Projektbezeichnung und Paketmetadaten wurden auf `keim_genesis_prototype_v7_8_5` / `Keim v7.8.5` aktualisiert.

Referenz-Teststatus auf Windows PowerShell:

```powershell
python tests\run_tests.py
```

Ergebnis:

```text
[Keim] Tests OK
```
