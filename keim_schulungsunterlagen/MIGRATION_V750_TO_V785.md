# Migration v7.5 → v7.8.5

Diese Datei ergänzt die vorhandene Migration `MIGRATION_V433_TO_V750.md`. Die v4.3.3- und v7.5-Inhalte bleiben gültig.

## Neue Zielsetzung

v7.5 erklärte den Enterprise-Unterbau: stabiler Bytecode, Result/Match, Datenmodell, Runtime, Web, Security und Hardening.
v7.8.5 ergänzt die Auslieferungsschicht: Keim-Programme werden als prüfbare Runtime-Bundles paketiert.

## Neue Konzepte

| v7.5-Konzept | Erweiterung in v7.8.5 | Warum wichtig? |
|---|---|---|
| Runtime | Full Runtime Packager | Programme werden nicht nur ausgeführt, sondern mit Runtime und Manifest ausgeliefert. |
| Native/WASM | interner PE64-/ELF64-Launcher | Startartefakte können ohne externe C/C++-Toolchain erzeugt werden. |
| Web-Interop | Projekt-Web-Overlay | Eine projektlokale `web/index.html` bleibt erhalten und wird ergänzt. |
| Security/SBOM | Paketmanifest, GPU-Manifest, SHA-256-Prüfung | Auslieferung wird reproduzierbar und prüfbar. |
| GPU-Treiber | GPU-aware Packaging | Treiber, Smoke-Test und CPU-Fallback werden Teil des Pakets. |
| Result/Match | Runtime Value Tags | `result_ok` und `result_error` werden im Value Model als Paketwerttypen sichtbar. |

## Neue Befehle für den Unterricht

```powershell
python -m keim exe-status --json
python -m keim exe-pack examples/agenten_zweige_v78_1_gpu_aware/src/main.keim --out build/agenten_bundle --name agenten_zweige --target auto
python -m keim exe-verify build/agenten_bundle --json
python -m keim exe-run build/agenten_bundle
python -m keim web-build --cwd examples/agenten_zweige_v78_1_gpu_aware --out build/web --json
```

## Neue Prüfkompetenz

Teilnehmende sollen erklären können:

1. welche Dateien zum Runtime-Bundle gehören,
2. warum ein Bootstrapper keine vollständige AOT-Übersetzung ist,
3. wie GPU-Treiber manifestiert und geprüft werden,
4. wie ein CPU-Fallback die Ausführung robuster macht,
5. wie Web-Overlay und Runtime-Artefakte zusammenarbeiten,
6. warum `exe-verify` vor Veröffentlichung wichtig ist.

## Kompatibilität

Die bestehenden v7.5-Beispiele bleiben im Kurs verwendbar. v7.8.5 fügt zusätzliche Beispiele und Kapitel hinzu.
