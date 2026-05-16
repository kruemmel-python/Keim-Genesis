# Keim Genesis v7.8.1 GPU-aware Full EXE Runtime Packager

v7.8.1 verbindet den v7.8 Full EXE Runtime Packager mit der v7.6 GPU Driver Execution Schicht.

## Ziel

Ein gepacktes Keim-Programm soll seine GPU-Schicht mitbringen:

```text
Keim Source
→ exe-pack
→ Runtime Bundle
→ runtime/driver/CC_OpenCl.dll
→ runtime/driver/libCC_OpenCL.so
→ runtime/gpu/gpu_driver_manifest.json
→ runtime/gpu/gpu_driver_plan.json
→ run_gpu.*
```

## Neue Packager-Fähigkeiten

- Windows-DLL und Linux-.so werden automatisch erkannt und kopiert.
- Das Paket enthält ein GPU-Manifest mit SHA-256-Prüfsummen.
- Das Paket enthält einen GPU-Ausführungsplan.
- Das Paket enthält einen GPU-Smoke-Test.
- `exe-verify` prüft GPU-Treiberdateien und Prüfsummen.
- CPU-Fallback bleibt Standard, wenn kein OpenCL-Kontext verfügbar ist.
- `--gpu-required` kann GPU-Artefakte erzwingen.

## CLI

```powershell
python -m keim exe-pack src/main.keim --out build/app --name app
python -m keim exe-pack src/main.keim --out build/app --name app --gpu-driver driver/build/CC_OpenCl.dll
python -m keim exe-pack src/main.keim --out build/app --name app --gpu-required
python -m keim exe-verify build/app --json
python -m keim exe-run build/app --json
```

Im Paket:

```powershell
run_gpu.bat
```

Linux/macOS:

```bash
./run_gpu.sh
```

## Paketstruktur

```text
runtime/driver/CC_OpenCl.dll
runtime/driver/libCC_OpenCL.so
runtime/gpu/gpu_driver_manifest.json
runtime/gpu/gpu_driver_plan.json
runtime/gpu/gpu_smoke.py
GPU_README.txt
run_gpu.bat
run_gpu.ps1
run_gpu.sh
```

## Ehrliche Grenze

v7.8.1 packt und verifiziert die GPU-Schicht professionell. Die Korrektheit einzelner GPU-Kernel bleibt weiterhin Aufgabe der v7.6 Driver-Execution-/Differentialtests. Wenn ein Treiber geladen wird, aber ein Kernel gegen CPU-Referenz abweicht, meldet die GPU-Demo dies weiterhin über `max_abs_error`.
