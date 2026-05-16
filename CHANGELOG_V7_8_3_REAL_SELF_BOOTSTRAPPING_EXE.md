# Changelog v7.8.3 – Real Self-Bootstrapping EXE Launcher

Dieser Hotfix korrigiert die v7.8.2-Grenze: Der Windows-Launcher darf kein Hinweis-Stub sein und darf nicht nur asynchron `WinExec` starten.

## Änderungen

- PE64-Launcher importiert jetzt `msvcrt.dll!system`.
- Der Launcher wartet auf `run.bat` und zeigt die echte Runtime-Ausgabe.
- Keine externe C/C++-Toolchain.
- `exe-verify` erkennt echte Runtime-Launcher und Hinweis-Stubs.
- Neuer Test `tests/run_v783_real_self_bootstrap_launcher_tests.py`.
- ELF64-Launcher bleibt direkt ausführbar und startet `run.sh`.

## Ehrliche Grenze

Der PE-Launcher startet die gebündelte Keim-Runtime über das Paket-Skript `run.bat`. Er ist damit ein echter nativer Bootstrapper, aber keine vollständige AOT-Übersetzung jedes Keim-Opcodes in Maschinencode. Für Native-MVP-Subset bleibt `native-link` zuständig.
