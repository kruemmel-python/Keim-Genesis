# Instructor Guide – Keim Training v4.3.3 + Enterprise v7.5 + Packaging v7.8.5

This course is a real teaching package, not only a product overview. The original v4.3.3 didactic line remains valid and is extended with runtime, Enterprise and packaging topics.

## Didactic line

1. Teach programming basics first.
2. Then explain architecture.
3. Then create Enterprise artefacts.
4. Then discuss Web/WASM/runtime/hardening.
5. Finally package and verify a v7.8.5 runtime bundle.

## Recommended v7.8.5 unit: Delivering programs

Learners should understand that a program may consist of more than source code:

- runtime
- manifest
- launcher scripts
- optional GPU driver plan
- Web surface
- verification report

## Suggested timing

| Duration | Topic |
|---|---|
| 30 min | What is a runtime bundle? |
| 30 min | Read `exe-status` and mark supported features |
| 45 min | Build a directory bundle and inspect the folder structure |
| 30 min | Run `exe-verify` and discuss the report |
| 45 min | GPU-aware packaging as optional advanced topic |
| 30 min | Difference between launcher, runtime and compiler |

## Key sentences for learners

- A launcher starts a program; it is not automatically the whole compiler.
- GPU support must be testable, otherwise it is only a claim.
- A manifest makes hidden assumptions visible.
- A directory bundle is easier to teach and debug than a single opaque artefact.
