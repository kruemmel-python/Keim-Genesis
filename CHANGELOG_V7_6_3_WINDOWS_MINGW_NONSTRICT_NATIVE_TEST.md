# Changelog v7.6.3 Windows/MSYS2 Native-Test-Härtung

Dieser Patch betrifft ausschließlich den älteren v6.5 Native-MVP-Test, der unter manchen Windows/MSYS2-Installationen
mit `g++.exe` Returncode 1 und leerem stdout/stderr abbrechen kann.

## Änderungen

- Native-Test bleibt in normalen Regression-Läufen nicht mehr hart stehen, wenn die lokale C++-Toolchain ohne Diagnose scheitert.
- `KEIM_NATIVE_STRICT=1` aktiviert weiterhin harte Compile-/Link-/Run-Prüfung.
- Die generierte C++-Quelle und Bytecode-Pipeline werden weiterhin geprüft.
- CI/Linux-Pfade, auf denen `g++` sauber diagnostiziert und kompiliert, testen weiterhin den echten Native-MVP-Lauf.

## Nutzung

Nicht-strikter Standard:

```powershell
python tests/run_tests.py
```

Strikte lokale Native-Prüfung:

```powershell
$env:KEIM_NATIVE_STRICT="1"
python tests/run_v65_native_generics_binary_tests.py
```
