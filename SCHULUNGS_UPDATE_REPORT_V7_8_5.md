# Schulungsunterlagen Update Report v7.8.5

Datum: 2026-05-16

## Ziel

Die vorhandenen Schulungsunterlagen wurden additiv auf Keim Genesis v7.8.5 erweitert.
Bereits vorhandene und korrekte v4.3.3- und v7.5-Inhalte wurden erhalten.

## Aktualisierte Bereiche

- `keim_schulungsunterlagen/index.html`
  - neues Kapitel 35: Self-Bootstrapping Runtime Packager
  - Packaging-Modi, GPU-aware Packaging, Runtime Value Model, Web Overlay und Native Launcher ergänzt

- `keim_programmieren_grundkurs_enterprise/index.html`
  - neues Kapitel 33: Programme ausliefern statt nur ausführen
  - anfängerfreundliche Erklärung von Runtime-Bundle, Launcher, GPU-aware Packaging und Web Overlay ergänzt

- Beide Schulungsordner
  - README aktualisiert
  - Dozentenleitfaden erweitert
  - Migration v7.5 → v7.8.5 ergänzt
  - Changelog v7.8.5 ergänzt
  - Beispiele unter `examples/current/` ergänzt
  - `site_manifest.json` mit aktuellen SHA-256-Prüfsummen neu erzeugt

## Neue Beispiele

- `v785_01_exe_runtime_packager.keim`
- `v785_02_gpu_aware_packaging.keim`
- `v785_03_web_overlay_policy.keim`
- `v785_packager_manifest.json`

## Abgedeckte neue Funktionen

- Full Runtime Packager
- Self-Bootstrapping Runtime Launcher
- PE64-/ELF64-Zielpfade ohne externe C/C++-Toolchain
- GPU-aware Packaging
- gebündelte GPU-Treiber
- GPU-Manifest, GPU-Plan und GPU-Smoke-Test
- CPU-Fallback für GPU-Pfade
- Runtime Value Model mit Value-Tags
- String/List/Map/Record/Result-Handles
- Module Table und Host Imports
- Runtime-Imports für IO/GPU/Web
- Zipapp Single-File Full Runtime
- Directory-Bundle für Unterricht und Debugging
- Projekt-Web-Overlay über `web/index.html`
- Teststatus auf der Windows-Referenzumgebung: `[Keim] Tests OK`

## Erhaltungsregel

Keine bestehenden Grundlagenkapitel wurden gelöscht. Die v7.8.5-Inhalte wurden als additive Erweiterung ergänzt.
