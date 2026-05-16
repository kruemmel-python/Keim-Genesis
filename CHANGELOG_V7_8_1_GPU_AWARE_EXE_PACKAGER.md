# Changelog v7.8.1 GPU-aware Full EXE Runtime Packager

## Neu

- `exe-pack` akzeptiert `--gpu-driver`.
- `exe-pack` akzeptiert `--gpu-required`.
- `exe-pack` akzeptiert `--no-gpu-smoke`.
- GPU-Treiber werden ins Paket kopiert.
- `runtime/gpu/gpu_driver_manifest.json`.
- `runtime/gpu/gpu_driver_plan.json`.
- `runtime/gpu/gpu_smoke.py`.
- `run_gpu.bat`, `run_gpu.ps1`, `run_gpu.sh`.
- `GPU_README.txt`.
- `exe-verify` prüft GPU-Artefakte und SHA-256.
- Test: `tests/run_v781_gpu_aware_exe_packager_tests.py`.

## Kompatibilität

v7.8 bleibt kompatibel: Ohne GPU-Treiber läuft das Paket weiter über die eingebettete Keim-Runtime. GPU ist optional, außer `--gpu-required` wird gesetzt.
