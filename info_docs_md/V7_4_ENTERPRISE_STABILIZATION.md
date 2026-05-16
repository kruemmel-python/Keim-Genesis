# Keim Genesis v7.4 – Enterprise Stabilization & Developer Platform

v7.4 ist die Härtungsstufe nach der schnellen Runtime-Evolution bis v7.3.

## Implementierte Schichten

- KBC-STABLE-1 Spezifikation
- sectioned Stable-Binary mit Section-Checksums und Payload-Hash
- Capability-Security-Scanner mit Deny-by-Default-Policy
- SBOM und reproduzierbares Buildmanifest
- Native/WASM-Paritätsmanifeste
- Benchmark-Harness
- Kompatibilitätsmatrix
- JSON-RPC/LSP-Kern
- LSP-Artefaktbundle für Editor-Integration
- Enterprise Whitepaper Generator

## CLI

```bash
python -m keim v74-status --json
python -m keim v74-check examples/sprache_v74_enterprise_stabilization.keim
python -m keim v74-build examples/sprache_v74_enterprise_stabilization.keim --out build/v74
python -m keim v74-verify build/v74/app.kbcstable
python -m keim v74-security examples/sprache_v74_enterprise_stabilization.keim
python -m keim v74-sbom --cwd . --out build/v74/sbom
python -m keim v74-parity examples/sprache_v74_enterprise_stabilization.keim --out build/v74/parity
python -m keim v74-benchmark examples/sprache_v74_enterprise_stabilization.keim --out build/v74/bench
python -m keim v74-compat --cwd . --out build/v74/compat
python -m keim v74-lsp-bundle --out build/v74/lsp
```

## Ehrliche Grenze

v7.4 stabilisiert Spezifikation, Security, IDE und Testbarkeit. Die nächste harte Runtime-Aufgabe bleibt vollständige native/WASM-Ausführungsparität für alle dynamischen Werte.
