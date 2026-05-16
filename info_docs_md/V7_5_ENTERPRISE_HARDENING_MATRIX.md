# Keim Genesis v7.5 – Enterprise Hardening Matrix

v7.5 ist die Härtungsschicht nach v7.4. Der Schwerpunkt liegt auf reproduzierbarer Kompatibilität statt neuer Syntax.

## Enthalten

- Große Differentialtest-Matrix aus synthetischen Enterprise-Fixtures und Repository-Regressionsfällen.
- KBC-STABLE-1-Verifikation pro Fall.
- Python-VM-Ausführung, soweit der Fall von der aktuellen stabilen VM unterstützt wird.
- Native/WASM-Paritätsmanifeste.
- Echter Node-WebAssembly-Smoke-Test mit realer WASM-Instantiation.
- Selbstständiger Browser-Harness für Chromium, Firefox, Safari und Edge.
- Plattformmatrix und GitHub-Actions-Matrix.
- JSON-, JUnit- und HTML-Reports.
- Hardening-Build, der Matrix, Browser/WASM, Kompatibilität und Benchmarking bündelt.

## Wichtige Grenze

v7.5 führt WebAssembly lokal über Node wirklich aus. Browser-Farm-Ausführung wird als Harness und CI-Artefakt erzeugt; die tatsächliche Ausführung in Chromium/Firefox/Safari hängt von der Zielumgebung ab.

## Kommandos

```bash
python -m keim v75-status --json
python -m keim v75-matrix --cwd . --out build/v75_matrix --json
python -m keim v75-wasm-browser --out build/v75_browser --json
python -m keim v75-compat --cwd . --out build/v75_compat --json
python -m keim v75-hardening-build --cwd . --out build/v75_hardening --json
python -m keim v75-whitepaper --out docs/WHITEPAPER_V7_5_HARDENING.md
```
