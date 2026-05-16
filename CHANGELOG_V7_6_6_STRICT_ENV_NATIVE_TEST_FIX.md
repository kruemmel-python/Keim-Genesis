# Changelog v7.6.6 – Strict-Env Native Test Fix

## Problem

On Windows PowerShell, a previously set `KEIM_NATIVE_STRICT=1` environment variable can be inherited by the full repository test suite. If the local MinGW toolchain exits with `returncode=1` and empty stdout/stderr even for a trivial `hello.cpp`, the old v6.5 native MVP test fails the whole `tests/run_tests.py` suite.

## Fix

- `tests/run_tests.py` now forces `KEIM_NATIVE_STRICT=0` for the v6.5 native MVP subtest.
- A hard repository-wide native check can still be requested explicitly with `KEIM_NATIVE_STRICT_SUITE=1`.
- `tests/run_v65_native_generics_binary_tests.py` now prints an explicit strict-mode explanation and the PowerShell command to unset the strict flag.

## Commands

Normal full suite:

```powershell
python tests/run_tests.py
```

Hard native-only toolchain test:

```powershell
$env:KEIM_NATIVE_STRICT="1"
python tests/run_v65_native_generics_binary_tests.py
```

Disable strict mode:

```powershell
Remove-Item Env:\KEIM_NATIVE_STRICT
```
