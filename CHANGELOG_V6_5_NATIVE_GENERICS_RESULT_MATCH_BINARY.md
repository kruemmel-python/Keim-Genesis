# Changelog v6.5

## Neu

- `keim/compiler65.py`
- `match`-Parser-Erweiterung in Foundation
- generische Signatur-Unifikation für Typvariablen wie `T`
- `ergebnis<T,E>` mit `ok`, `fehler`, `ist_ok`
- `match` auf Result mit Exhaustiveness-Prüfung
- VM65 mit `JUMP_IF_TRUE`, `RESULT_IS_OK`, `PANIC`
- binäres `.kbc65b`-Format mit Magic, Version, Länge, SHA-256
- `.kbc65b` laden und ausführen
- Native C++ keimvm65 MVP-Generator
- v6.5 Beispiele:
  - `examples/sprache_v65_result_match_generics.keim`
  - `examples/sprache_v65_native_subset.keim`
- v6.5 Tests:
  - `tests/run_v65_native_generics_binary_tests.py`

## Neue CLI-Kommandos

```bash
python -m keim v65-status --json
python -m keim v65-check examples/sprache_v65_result_match_generics.keim
python -m keim v65-bytecode examples/sprache_v65_result_match_generics.keim --out build/v65/app.kbc65.json --binary-out build/v65/app.kbc65b
python -m keim v65-run examples/sprache_v65_result_match_generics.keim
python -m keim v65-run-bin build/v65/app.kbc65b
python -m keim v65-build --cwd . --out build/v65_project
python -m keim v65-test examples/sprache_v65_result_match_generics.keim --json
python -m keim v65-native build/v65/native_subset.kbc65.json --out build/v65/keimvm65_subset.cpp
```

## Bekannte Grenzen

- Native VM ist MVP für Integer/Bool-Control-Flow-Subset.
- Native Heap, Strings, Maps, Listen, Records und Calls sind noch nicht vollständig.
- WASM bleibt v6.4 Seed-Niveau.
- Generics sind Signatur-/Call-Site-Unifikation, noch kein vollständiges Trait-/Bound-System.
