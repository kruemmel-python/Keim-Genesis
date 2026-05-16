# Changelog v7.6.4 – Linux GPU Driver Support

Diese Version korrigiert die v7.6-Annahme, dass der CipherCore/OpenCL-Treiber nur als Windows-DLL genutzt wird.

## Neu

- `driver/build/libCC_OpenCL.so` wird als Linux-Treiberartefakt first-class erkannt.
- `default_driver_path()` bevorzugt unter Linux automatisch `driver/build/libCC_OpenCL.so`.
- `gpu-driver-status`, `gpu-driver-plan` und `gpu-driver-demo` arbeiten mit DLL und `.so`.
- `CipherCoreGpuExecutor` kann native Treiberbibliotheken über `ctypes.CDLL` auf Windows und Linux laden.
- Wenn ein OpenCL-Kontext/Gerät fehlt, fällt der Hotpath sauber auf CPU-Differentialreferenz zurück.
- JSON-Ausgaben unterdrücken native C/C++-Treiberlogs, damit maschinenlesbares JSON stabil bleibt.
- Neuer Test: `tests/run_v764_linux_gpu_driver_tests.py`.

## Enthaltene Treiberartefakte

- `driver/build/CC_OpenCl.dll`
- `driver/build/libCC_OpenCL.so`

## Beispiel

```bash
python -m keim gpu-driver-status --json
python -m keim gpu-driver-plan --dll driver/build/libCC_OpenCL.so --json
python -m keim gpu-driver-demo --dll driver/build/libCC_OpenCL.so --out build/gpu_linux --json
```
