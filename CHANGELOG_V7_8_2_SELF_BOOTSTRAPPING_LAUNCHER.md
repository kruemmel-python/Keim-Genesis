# Changelog v7.8.3 — Self-Bootstrapping Runtime Launcher

## Neu

- Native Launcher startet jetzt das Runtime-Paket statt nur Hinweistext auszugeben.
- Neuer interner Linker-Modus `link_command_launcher`.
- Neuer ELF64-Launcher: `execve("/bin/sh", ["sh", "-c", command])`.
- Neuer PE64-Launcher: `WinExec(command, SW_SHOWNORMAL)`.
- `run.bat`, `run.ps1` und `run.sh` setzen GPU-Treiberpfade automatisch.
- `--gpu-required` führt vor App-Start den GPU-Smoke-Test aus.
- `exe-verify` prüft jetzt `self_bootstrap_launcher`.
- Neuer Test: `tests/run_v782_self_bootstrap_launcher_tests.py`.

## Kompatibilität

- v7.8.1 GPU-aware Packaging bleibt erhalten.
- v7.8 Full EXE Runtime Packager bleibt erhalten.
- v7.7 Internal Native Linker bleibt erhalten.
- Keine externe C/C++-Toolchain erforderlich.

## Ehrliche Grenze

Der PE64-Launcher nutzt aktuell den beim Packaging bekannten Paketpfad. Für verschobene Pakete wird zusätzlich eine relative `.cmd`-Companion-Datei erzeugt.
