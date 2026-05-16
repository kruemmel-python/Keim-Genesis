# Architektur: Agenten-Zweige v7.8.1 GPU-aware

Dieses Beispiel trennt bewusst vier Ebenen.

## 1. Keim-Fachlogik

Datei:

```text
src/main.keim
```

Diese Datei enthält die normale Agenten-Zweiglogik:

```text
basis = 1 + zweig
ergebnis = basis * basis
```

Sie ist deterministisch, testbar und ohne GPU lauffähig.

## 2. Keim-Massenreferenz

Datei:

```text
src/gpu_mass_bench.keim
```

Diese Datei enthält den gleichen Rechenkern als kleine Massenreferenz. Sie ist mit
`core-test` prüfbar und vermeidet bewusst erfundene GPU-Syntax.

## 3. GPU-Treiberdiagnose

Die Diagnose läuft über:

```powershell
python -m keim gpu-driver-status --json
python -m keim gpu-driver-plan --json
python -m keim gpu-driver-demo --dll D:\keim_genesis_prototype_v4_3\driver\build\CC_OpenCl.dll --out build\gpu_driver --json
```

Die Diagnose prüft, ob Treiber, Symbole und Kernelprofile verfügbar sind.

## 4. GPU-aware Packaging v7.8.1

Das auslieferbare Paket wird jetzt mit `--gpu-driver` gebaut:

```powershell
python -m keim exe-pack src\main.keim --out build\agenten_zweige_gpu_aware --name agenten_zweige_gpu_aware --gpu-driver D:\keim_genesis_prototype_v4_3\driver\build\CC_OpenCl.dll
```

Erwartete GPU-aware Paketartefakte:

```text
runtime/driver/CC_OpenCl.dll
runtime/gpu/gpu_driver_manifest.json
runtime/gpu/gpu_driver_plan.json
runtime/gpu/gpu_smoke.py
GPU_README.txt
run_gpu.bat
run_gpu.ps1
```

## Diagnosehinweis

Wenn `core-test` und `exe-run` erfolgreich sind, aber ein einzelnes Kernelprofil in
`gpu-driver-demo` `ok=false` meldet, ist das nicht automatisch ein Fehler im Keim-Programm.
Dann sind GPU-Adapter, ABI, Bufferlayout, Kernelreferenz oder numerische Toleranz zu prüfen.


## 5. Web-Ansicht für Schulungen

Die Web-Ansicht liegt unter:

```text
web/index.html
web/keim_agenten_adapter.js
web/assets/style.css
```

Sie visualisiert die Agenten-Zweige als Tabelle, Slider und Ergebnis-Karte. Die GUI ist bewusst
klein gehalten und erfüllt die Keim-v7.8.1-Web-Regeln:

```text
kein eval
keine Function-Konstruktion
keine freie Ausdrucksauswertung
Ganzzahl-Domain passend zum Keim-Kern
Adapter dokumentiert die Spiegelung der Keim-Funktionen
```

Der Adapter spiegelt diese geprüften Keim-Funktionen:

```text
agent_basis(zweig) = 1 + zweig
agent_quadrat(wert) = wert * wert
agent_zweig(zweig) = agent_quadrat(agent_basis(zweig))
agent_batch_summe_10() = Summe agent_zweig(1..10)
```

Damit ist die Web-Ansicht didaktisch nützlich, ohne zu behaupten, dass der Browser selbst den
Keim-Bytecode ausführt. Für echte Web-Runtime-Bridge-Projekte bleibt der dokumentierte
`web-build`-Pfad vorgesehen.
