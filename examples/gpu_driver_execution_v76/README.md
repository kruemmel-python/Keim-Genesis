# Keim v7.6 GPU Driver Execution Beispiel

Dieses Beispiel zeigt, wie `driver/build/CC_OpenCl.dll` in Keim nicht nur erkannt,
sondern über die neue v7.6 Driver-Execution-Schicht geplant, profiliert und im
Runtime-Backend aktiviert wird.

## Prüfen

```bash
python -m keim gpu-driver-status --json
python -m keim gpu-driver-plan --json
```

## Demo mit Report

```bash
python -m keim gpu-driver-demo --out build/gpu_driver --json
```

Auf Linux/CI wird die Windows-DLL per Symbolscan geprüft und eine CPU-Differentialreferenz
ausgeführt. Auf Windows lädt Keim die DLL per `ctypes` und aktiviert echte Dispatch-Hotpaths.

## Runtime-Backend

```bash
python -m keim run examples/minimal_v12.keim --backend gpu --dll driver/build/CC_OpenCl.dll --driver-smoke
```

Die Runtime schreibt GPU-Driver-Metriken in den normalen Report.
