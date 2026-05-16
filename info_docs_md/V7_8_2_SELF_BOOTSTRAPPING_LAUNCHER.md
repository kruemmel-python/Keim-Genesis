# Keim Genesis v7.8.3 — Self-Bootstrapping Runtime Launcher

v7.8.3 behebt den wichtigsten UX-Bruch des Full EXE Runtime Packers: Der native Launcher im `bin/`-Ordner ist nicht länger nur ein Paketmarker/Hinweistext. Er startet jetzt das Full Runtime Package.

## Ziel

Vorher:

```text
bin/<name>_launcher.exe
→ gibt nur Hinweistext aus
```

Jetzt:

```text
bin/<name>_launcher.exe
→ startet run.bat
→ run.bat setzt Runtime-/GPU-Umgebung
→ keim_app.py startet eingebettete Keim-Runtime
```

Auf Linux:

```text
bin/<name>_launcher
→ startet run.sh
→ run.sh setzt LD_LIBRARY_PATH/DYLD_LIBRARY_PATH
→ keim_app.py startet eingebettete Keim-Runtime
```

## Keine externe Toolchain

Der Launcher wird weiterhin ohne `g++`, `clang`, `link.exe` oder MinGW erzeugt. Keim erzeugt den PE64-/ELF64-Bootstrapper selbst.

## GPU-aware Verhalten

Wenn GPU-Treiber im Paket liegen:

```text
runtime/driver/CC_OpenCl.dll
runtime/driver/libCC_OpenCL.so
```

setzen `run.bat`, `run.ps1` und `run.sh` automatisch die passenden Suchpfade.

Wenn `--gpu-required` genutzt wurde, wird vor dem Start der App `runtime/gpu/gpu_smoke.py` ausgeführt. Scheitert der Smoke-Test, bricht der Launcher sauber ab.

## Grenzen

Der Windows-PE-Launcher nutzt den beim Packaging bekannten Paketpfad für `run.bat`. Zusätzlich erzeugt Keim eine relative Companion-Datei:

```text
bin/<name>_launcher.cmd
```

Für portable Umzüge des Paketordners bleibt `run.bat` oder die `.cmd`-Companion-Datei der robusteste Pfad. Der Linux-ELF-Launcher wurde in der Testumgebung real ausgeführt und startet die Runtime korrekt.
