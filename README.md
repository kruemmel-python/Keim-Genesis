# Keim Genesis Prototype

Keim Genesis ist ein experimenteller Python-Prototyp einer feld-, agenten-, regel- und compilerorientierten Programmiersprache.  
Der aktuelle Stand dieses Repositories ist **v7.8.5**.

> Status: Forschungs-/Prototyp-Code. Die APIs und Sprachfeatures sind bewusst in Bewegung.

## Was ist enthalten?

- `keim/` – Parser, Analyzer, Runtime, Compiler-Varianten, Bytecode, Sandbox, Web-/WASM-/Native-Experimente
- `examples/` – `.keim`-Beispielprogramme über mehrere Sprachgenerationen
- `stdlib/` – kleine Keim-Standardbibliothek
- `tests/` – ausführbare Smoke-/Regressionstests
- `docs/` – Entwicklungsnotizen, Whitepaper und Versionsdokumente
- `native/` und `driver/src/` – optionale Native-/GPU-nahe Experimente
- `autonome_Simulations_API/` – API-/Daemon-Prototyp für autonome Simulationen

## Voraussetzungen

- Python **3.12+**
- Keine zwingenden Python-Framework-Abhängigkeiten für den Kern
- Native-/GPU- und Driver-Experimente benötigen separate Toolchains und sind optional

## Schnellstart aus dem Repository

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e .
keim --version
keim analyze examples/minimal_v12.keim
keim run examples/minimal_v12.keim --rounds 10
```

Alternativ ohne Installation:

```bash
python -m keim.cli --version
```

## Tests

Schnelle syntaktische Prüfung:

```bash
python -m compileall -q keim tests
```

Regressionstests:

```bash
python tests/run_tests.py
```

Hinweis: Einige Tests berühren optionale Native-, GPU-, Web- oder Packaging-Pfade und können je nach Plattform/Toolchain länger laufen oder übersprungen werden müssen.

## Repository-Hygiene

Diese GitHub-Fassung enthält nur Quellcode, Beispiele, Tests und Dokumentation. Entfernt wurden:

- generierte `build/`-Artefakte
- vorkompilierte `.dll`, `.so`, `.lib`, `.exp`
- Logdateien, Cachedateien und Python-Bytecode
- lokale Runtime-Snapshots

Binärartefakte sollten bei Bedarf über Releases oder reproduzierbare Build-Skripte erzeugt werden, nicht direkt im Git-Repository liegen.

## Native-/GPU-Hinweis

Die GPU-/Driver-Pfade sind experimentell. Der Quellcode liegt unter `driver/src/`, `driver/include/` und `native/`.  
Vorkompilierte Bibliotheken sind absichtlich nicht enthalten.

## Lizenz

Siehe [`LICENSE.txt`](LICENSE.txt). Der aktuelle Text beschreibt eine Prototype-/Experimental-Use-Lizenz und sollte vor einer öffentlichen Veröffentlichung bewusst geprüft oder durch eine klare Open-Source-Lizenz ersetzt werden.

## Sicherheitsmodell

Siehe [`SECURITY.md`](SECURITY.md). Keim ist als lokaler Forschungsprototyp gedacht; Netzwerk-, Treiber- und Native-Funktionen sollten nur bewusst aktiviert werden.

## Historische Dokumentation

Die frühere README zum v2.9-Stand wurde nach [`docs/README_LEGACY_V2_9.md`](docs/README_LEGACY_V2_9.md) verschoben.


## Referenz-Teststatus

Auf der bekannten Windows-Entwicklungsumgebung läuft die vollständige Testsuite erfolgreich:

```powershell
python tests\run_tests.py
```

Ergebnis:

```text
[Keim] Tests OK
```
