# Migration v7.5 → v7.8.5

This file extends the v4.3.3 to v7.5 migration. The v4.3.3 and v7.5 content remains valid.

## New target

v7.5 explained the Enterprise foundation: stable bytecode, Result/Match, data model, runtime, Web, security and hardening.

v7.8.5 adds the delivery layer: Keim programs are packaged as verifiable runtime bundles.

## New concepts

| v7.5 concept | v7.8.5 extension | Why it matters |
|---|---|---|
| Runtime | Full Runtime Packager | Programs are not only executed; they are delivered with runtime and manifest. |
| Native/WASM | internal PE64/ELF64 launcher | Start artefacts can be generated without an external C/C++ toolchain. |
| Web interop | project Web overlay | A project-local `web/index.html` is preserved and extended. |
| Security/SBOM | package manifest, GPU manifest, SHA-256 verification | Delivery becomes reproducible and checkable. |
| GPU driver | GPU-aware packaging | Driver plan, smoke test and CPU fallback become part of the package. |
| Result/Match | runtime value tags | `result_ok` and `result_error` become visible value-model package types. |

## New training commands

```powershell
python -m keim exe-status --json
python -m keim exe-pack examples/agenten_zweige_v78_1_gpu_aware/src/main.keim --out build/agenten_bundle --name agenten_zweige --target auto
python -m keim exe-verify build/agenten_bundle --json
python -m keim exe-run build/agenten_bundle
python -m keim web-build --cwd examples/agenten_zweige_v78_1_gpu_aware --out build/web --json
```

## New exam competence

Participants should be able to explain:

1. which files belong to a runtime bundle,
2. why a bootstrapper is not a full AOT compiler,
3. how GPU drivers are manifested and checked,
4. how CPU fallback makes execution more robust,
5. how Web overlay and runtime artefacts cooperate,
6. why `exe-verify` matters before publication.

## Compatibility

Existing v7.5 examples remain usable. v7.8.5 adds examples and chapters.
