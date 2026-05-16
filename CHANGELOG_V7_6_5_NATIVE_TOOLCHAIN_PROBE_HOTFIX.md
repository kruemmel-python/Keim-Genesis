# Changelog v7.6.5 Native Toolchain Probe Hotfix

Dieses Hotfix löst den Windows/MSYS2-Sonderfall, in dem `g++` aus einem
Python-Subprozess mit Returncode 1 und leerer stdout/stderr-Diagnose beendet.

## Änderungen

- `tests/run_v65_native_generics_binary_tests.py` prüft weiterhin Bytecode und
  generierte Native-MVP-C++-Quelle.
- Falls der Native-Link/Run fehlschlägt, wird ein trivialer `hello.cpp`-Probe-Build
  ausgeführt.
- In nicht-striktem Repository-Testmodus blockiert ein lokal still fehlschlagender
  Compiler nicht mehr `tests/run_tests.py`.
- Harte Native-Prüfung bleibt über `KEIM_NATIVE_STRICT=1` verfügbar.
- Vollständige Diagnose wird im Strict-Modus weiterhin ausgegeben.

## Hintergrund

Der Fehler ist kein GPU-Treiberproblem. `tests/run_v764_linux_gpu_driver_tests.py`
und die v7.6 GPU-Driver-Schicht laufen unabhängig davon.
