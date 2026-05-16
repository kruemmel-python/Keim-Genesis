# Changelog v7.6.1 – Windows/MinGW Native-Test-Hotfix

Dieser Hotfix behebt den Abbruch von `python tests/run_tests.py` unter Windows/MinGW im älteren v6.5-Native-MVP-Test.

## Problem

`tests/run_v65_native_generics_binary_tests.py` kompilierte den generierten `keimvm65_subset.cpp` nach `build/v65_tests/keimvm65_subset` ohne Windows-`.exe`-Suffix und ohne robuste Diagnose. Auf Windows/MinGW konnte der Link-Schritt mit `CalledProcessError` abbrechen, wodurch der gesamte Testlauf stoppte.

## Änderungen

- Native-v6.5-C++-Generator verwendet nun `OP_*`-Enum-Namen.
- Dadurch werden mögliche Makro-/Namenskollisionen mit Toolchains vermieden.
- Der v6.5-Native-Test erzeugt auf Windows ein eindeutiges `*.exe` pro Prozess.
- Der Test gibt bei Compilerfehlern jetzt die vollständige Compilerdiagnose aus.
- Lokaler Build/Run wurde mit `g++ -std=c++20 -O2` geprüft.

## Validierung

- `python -S tests/run_v65_native_generics_binary_tests.py`
- `python -S tests/run_v76_gpu_driver_execution_tests.py`
- generierter `keimvm65_subset.cpp` kompiliert und gibt `42` aus.
