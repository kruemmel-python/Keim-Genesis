# Changelog v7.6 GPU Driver Execution

- neue Datei `keim/gpu_driver_execution.py`
- `driver/build/CC_OpenCl.dll` Auto-Discovery
- Kernel-ABI-Registry für CC_OpenCl.dll
- portabler DLL-Symbolscan
- Real-GPU-ctypes-Bindings unter Windows
- persistenter GPU-Buffer-Manager
- erster echter Real-Dispatch-Hotpath: `execute_fused_diffusion_on_gpu`
- CPU-Differentialreferenz für alle v7.6 Demo-Kernel
- neue CLI-Kommandos:
  - `gpu-driver-status`
  - `gpu-driver-plan`
  - `gpu-driver-demo`
- `--backend gpu` in der Runtime
- Hybrid/Auto kann den GPU Driver Execution Backend wählen
- neue Tests `tests/run_v76_gpu_driver_execution_tests.py`
