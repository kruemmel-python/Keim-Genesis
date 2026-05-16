# Keim Genesis v7.8 – Full EXE Runtime Packager

v7.8 erweitert den internen Native-Linker zu einem vollständigen Runtime-Packager. Ziel ist: Keim-Programme sollen ohne externes C/C++-Compiler-Modul als ausführbare Artefakte verteilt werden können.

## Kern

Der Packager erzeugt ein Runtime-Bundle mit:

- Native Value Model
- Heap
- Strings
- Listen
- Maps
- Records
- Result/Match-Grundruntime
- Funktionsaufrufen über eingebettete Keim-Runtime
- Modul-Tabelle
- Runtime-Imports für IO/GPU/Web
- optionalem PE/ELF-Launcher über Keims internen Linker
- `.pyz` Single-File Runtime-Artefakt

## Kommandos

```bash
python -m keim exe-status --json
python -m keim exe-pack examples/exe_runtime_packager_v78/main.keim --out build/v78_exe --name keim_v78_demo
python -m keim exe-verify build/v78_exe --json
python -m keim exe-run build/v78_exe --json
```

## Architektur

```text
Keim Source
→ Bytecode/Manifest
→ Runtime Bundle
→ keim_app.py / run.bat / run.sh
→ optionaler interner PE/ELF Launcher
→ optionales .pyz Single-File-Artefakt
```

## Wichtig

Direkte maschinennahe Native-Linkung bleibt für das kleine Native-Subset verfügbar. Komplexe Keim-Programme laufen über die eingebettete Runtime im Bundle. Dadurch bleiben Listen, Maps, Records, Result/Match, Module und Runtime-Imports erhalten, ohne auf g++, clang oder link.exe angewiesen zu sein.
