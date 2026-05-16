# Keim Genesis v7.6 GPU Driver Execution

v7.6 macht aus der bisherigen Treiberdiagnose eine echte GPU-Execution-Schicht für `driver/build/CC_OpenCl.dll`.

## Ziel

Die DLL wird nicht nur geprüft, sondern in eine Dispatch-Pipeline integriert:

```text
Keim Runtime/IR
→ GPU Driver Execution Plan
→ CC_OpenCl.dll Kernel ABI
→ persistente GPU-Buffer
→ Kernel Dispatch
→ Readback / Differentialtest / Profiling
```

## Neue Kommandos

```bash
python -m keim gpu-driver-status --json
python -m keim gpu-driver-plan --json
python -m keim gpu-driver-demo --out build/gpu_driver --json
python -m keim run examples/minimal_v12.keim --backend gpu --dll driver/build/CC_OpenCl.dll --driver-smoke
```

## Unterstützte Treiber-Symbole

- `execute_fused_diffusion_on_gpu`
- `execute_energy_gated_scheduler_gpu`
- `execute_resonant_field_step_gpu`
- `execute_morphogenetic_rule_step_gpu`
- `execute_proto_segmented_sum_gpu`
- `execute_proto_update_step_gpu`
- `subqg_simulation_step_host_fields`
- `subqg_simulation_step_native_fields`

## Enterprise-Eigenschaften

- Auto-Discovery von `driver/build/CC_OpenCl.dll`
- portabler Symbolscan auf Nicht-Windows-Systemen
- echter ctypes-Dispatch unter Windows
- persistenter Buffer-Manager für Real-GPU-Hotpaths
- CPU-Differentialreferenz für CI und Debugging
- Profiling von Upload, Kernel, Download und Gesamtzeit
- `--backend gpu` in der Keim Runtime

## Ehrliche Grenze

In Linux/CI kann eine Windows-DLL nicht geladen werden. Keim erkennt aber die Symbole portabel und führt deterministische CPU-Differentialreferenzen aus. Unter Windows wird der reale `ctypes`-Dispatch für `execute_fused_diffusion_on_gpu` aktiviert; weitere Kernel sind ABI-gebunden und als Dispatchregeln eingetragen.
