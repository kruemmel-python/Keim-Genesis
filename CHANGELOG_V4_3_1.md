# Keim Genesis v4.3.1

MSVC compatibility patch for the native VM build on Windows.

## Fixes

- Defines `NOMINMAX` before including `windows.h`.
- Uses parenthesized `(std::min)` and `(std::max)` calls in `native/keim_vm_native.cpp`
  to avoid collisions with Windows `min`/`max` macros.
- No language/runtime semantics changed.
