# agenten_zweige_v78_1_gpu_aware

Keim Genesis v7.8.1 Beispielprojekt mit GPU-aware Full EXE Runtime Packager.

Dieses Projekt ersetzt das ältere reine Diagnose-GPU-Beispiel durch den neuen v7.8.1-Paketpfad:

```text
exe-pack --gpu-driver
```

## Was das Programm tut

Es bildet Agenten-Zweige:

```text
Zweig 1: 1 + 1 = 2, 2 * 2 = 4
Zweig 2: 1 + 2 = 3, 3 * 3 = 9
...
Zweig 10: 1 + 10 = 11, 11 * 11 = 121
```

Zusätzlich gibt es eine deterministische Massenreferenz für GPU-Diagnose und CPU-Fallback.

## Projektstruktur

```text
agenten_zweige_v78_1_gpu_aware/
    keim.toml
    README.md
    src/
        main.keim
        gpu_mass_bench.keim
    scripts/
        gpu_mass_driver_demo.py
        run_gpu_aware_windows.ps1
    web/
        index.html
        keim_agenten_adapter.js
        assets/style.css
    docs/
        ARCHITEKTUR.md
        GPU_AWARE_PACKAGING_V7_8_1.md
        WEB_ANSICHT_V7_8_1.md
    build/
        .gitkeep
    gpu_reports/
        .gitkeep
```

## PowerShell vom Keim-Hauptordner aus

```powershell
cd D:\keim_genesis_prototype_v4_3
python -m keim core-test D:\keim_genesis_prototype_v4_3\examples\agenten_zweige_v78_1_gpu_aware\src\main.keim
python -m keim core-test D:\keim_genesis_prototype_v4_3\examples\agenten_zweige_v78_1_gpu_aware\src\gpu_mass_bench.keim
python -m keim web-build --cwd D:\keim_genesis_prototype_v4_3\examples\agenten_zweige_v78_1_gpu_aware --out D:\keim_genesis_prototype_v4_3\examples\agenten_zweige_v78_1_gpu_aware\build\web
python -m keim gpu-driver-status --json
python -m keim gpu-driver-plan --json
python -m keim gpu-driver-demo --dll D:\keim_genesis_prototype_v4_3\driver\build\CC_OpenCl.dll --out D:\keim_genesis_prototype_v4_3\examples\agenten_zweige_v78_1_gpu_aware\build\gpu_driver --json
python D:\keim_genesis_prototype_v4_3\examples\agenten_zweige_v78_1_gpu_aware\scripts\gpu_mass_driver_demo.py --repo-root D:\keim_genesis_prototype_v4_3 --dll D:\keim_genesis_prototype_v4_3\driver\build\CC_OpenCl.dll --out D:\keim_genesis_prototype_v4_3\examples\agenten_zweige_v78_1_gpu_aware\gpu_reports --count 100000
python -m keim exe-pack D:\keim_genesis_prototype_v4_3\examples\agenten_zweige_v78_1_gpu_aware\src\main.keim --out D:\keim_genesis_prototype_v4_3\examples\agenten_zweige_v78_1_gpu_aware\build\agenten_zweige_gpu_aware --name agenten_zweige_gpu_aware --gpu-driver D:\keim_genesis_prototype_v4_3\driver\build\CC_OpenCl.dll
python -m keim exe-verify D:\keim_genesis_prototype_v4_3\examples\agenten_zweige_v78_1_gpu_aware\build\agenten_zweige_gpu_aware --json
python -m keim exe-run D:\keim_genesis_prototype_v4_3\examples\agenten_zweige_v78_1_gpu_aware\build\agenten_zweige_gpu_aware --json
python D:\keim_genesis_prototype_v4_3\examples\agenten_zweige_v78_1_gpu_aware\build\agenten_zweige_gpu_aware\runtime\gpu\gpu_smoke.py --json
```


## Web-Ansicht

Das Projekt enthält zusätzlich eine kleine professionelle Web-Ansicht:

```text
web/index.html
web/keim_agenten_adapter.js
web/assets/style.css
```

Die Web-Ansicht ist bewusst **Keim-streng** aufgebaut:

- kein `eval`
- keine `Function("return ...")`
- keine freie JavaScript-Ausdrucksauswertung
- Ganzzahl-Domain passend zum Keim-Kern
- dokumentierter Adapter, der exakt die getesteten Keim-Funktionen aus `src/main.keim` spiegelt

Lokaler Start:

```powershell
cd D:\keim_genesis_prototype_v4_3\examples\agenten_zweige_v78_1_gpu_aware
start web\index.html
```

Optionaler Web-Build vom Projektordner aus:

```powershell
python -m keim web-build --cwd D:\keim_genesis_prototype_v4_3\examples\agenten_zweige_v78_1_gpu_aware --out D:\keim_genesis_prototype_v4_3\examples\agenten_zweige_v78_1_gpu_aware\build\web
```

Wichtig: Die Web-Ansicht ist eine Schulungsvisualisierung mit dokumentiertem Adapter. Die getestete Fachlogik bleibt in `src/main.keim`.


## GPU-Modus

- Windows-Treiber: `driver/build/CC_OpenCl.dll`
- Linux-Treiber: `driver/build/libCC_OpenCL.so`
- Fallback: CPU-Referenz
- Smoke-Test: `python -m keim gpu-driver-demo --out build/gpu_driver --json`
- GPU-aware Paket: `python -m keim exe-pack ... --gpu-driver ...`

## Wichtig

Das Keim-Programm selbst behauptet nicht, dass jede Funktion automatisch auf der GPU läuft.
Die Fachlogik ist CPU-deterministisch. GPU wird als Treiber-, Diagnose- und Paketfähigkeit
eingebunden.

Wenn `core-test` und `exe-run` OK sind, aber ein einzelnes GPU-Kernelprofil `ok=false`
meldet, liegt der Fehler wahrscheinlich nicht im Keim-Beispielprogramm, sondern in
GPU-Adapter, ABI, Bufferlayout, Kernelreferenz oder Toleranz.
