# Keim v4.1 External GPU Driver Bridge

Keim v4.1 bettet den vorhandenen C-/OpenCL-Treiber nicht ein. Die Native VM lädt ihn optional zur Laufzeit:

```python
from keim.native_vm import NativeNumericVm, default_native_library

vm = NativeNumericVm(default_native_library())
driver = vm.load_gpu_driver(r"C:\Pfad\zu\CC_OpenCl.dll")
print(driver.ready())
driver.shadow_init(gpu_index=0, cells=4096, channels=8)
driver.shadow_cycle(gpu_index=0, cycles=10)
driver.close()
```

## Geladene Symbole

Keim prüft zur Laufzeit, welche Symbole vorhanden sind:

- `shadow_init`
- `shadow_cycle`
- `subqg_set_multifield_state`

Fehlende Symbole sind kein Importfehler. Nur der jeweilige Funktionspfad gibt dann `False` zurück.

## ABI-Prinzip

- Agenten bleiben in Keim als SoA (`x[]`, `y[]`, `energy[]`, `alive[]`) modelliert.
- Kernel-Bundles aus `compile_kernel_abi(... )["kernel_bundles_v12"]` markieren, welche Blöcke parallel/GPU-fähig sind.
- Host-IO und dynamische Objektverwaltung bleiben Barrieren.
- Scatter-Operationen verlangen atomare Adds oder deterministische Segment-Reduktion.
