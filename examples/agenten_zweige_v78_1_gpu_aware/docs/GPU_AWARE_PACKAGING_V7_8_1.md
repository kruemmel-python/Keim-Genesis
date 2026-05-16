# Keim v7.8.1 GPU-aware Packaging

## Ziel

Dieses Beispiel nutzt die neue v7.8.1-Funktion des Full EXE Runtime Packers:
GPU-Treiber werden direkt in das EXE-Runtime-Paket eingebunden.

## Windows

```powershell
python -m keim exe-pack D:\keim_genesis_prototype_v4_3\examples\agenten_zweige_v78_1_gpu_aware\src\main.keim --out D:\keim_genesis_prototype_v4_3\examples\agenten_zweige_v78_1_gpu_aware\build\agenten_zweige_gpu_aware --name agenten_zweige_gpu_aware --gpu-driver D:\keim_genesis_prototype_v4_3\driver\build\CC_OpenCl.dll
```

## Linux

```bash
python -m keim exe-pack src/main.keim --out build/agenten_zweige_gpu_aware --name agenten_zweige_gpu_aware --gpu-driver driver/build/libCC_OpenCL.so
```

## GPU zwingend machen

Nur verwenden, wenn das Programm ohne GPU nicht sinnvoll laufen soll:

```powershell
python -m keim exe-pack src/main.keim --out build/app --name app --gpu-required
```

## GPU deaktivieren

```powershell
python -m keim exe-pack src/main.keim --out build/app --name app --no-gpu
```

## Paket-Smoke

Nach dem Packen:

```powershell
python D:\keim_genesis_prototype_v4_3\examples\agenten_zweige_v78_1_gpu_aware\build\agenten_zweige_gpu_aware\runtime\gpu\gpu_smoke.py --json
```

## Fallback

GPU ist in diesem Beispiel optional. Die Keim-Fachlogik bleibt über CPU-Referenztests
prüfbar. Wenn kein Treiber ladbar ist, bleibt das Programm fachlich korrekt, nur die
GPU-Beschleunigung ist nicht verfügbar.
