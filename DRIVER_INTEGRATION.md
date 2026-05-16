# Driver Integration v2.0

Die Treiberschicht bleibt diagnostisch.

```powershell
python -m keim driver-info --dll D:\path\to\CC_OpenCl.dll --smoke
python -m keim gpu-validate examples\sprache_v20.keim --dll D:\path\to\CC_OpenCl.dll --smoke
```

v2.0 ergänzt Sprachmodule und Build-Ausgabe, ändert aber nicht die Sicherheitsgrenze:

- keine Prozess-Injection
- keine fremden Prozesse
- keine Kernel-Mode-Operation
- keine automatische GPU-Ausführung

Die GPU-ABI beschreibt weiterhin Kandidaten wie:

- `FIELD_TRAIL_COUPLE`
- `FIELD_COMPUTE`
- `MASK_EXPR`
- `ALLOC_MEMORY`/`MEMORY_CHANGE` als skalare Host-/Uniform-Kandidaten
- `FIELD_TRAIL_EMIT`
- `DIFFUSE_TRAIL`
- `FOLLOW_TRAIL`
- `AVOID_TRAIL`


## v2.0-Hinweis

Kontrollfluss, Speicher und Kontrakte bleiben vollständig deterministisch auf Sprach-/CPU-Ebene. GPU-Validierung betrifft weiterhin nur die IR-/Scatter-/Gather-Kandidaten; `FIELD_COMPUTE` ist als künftiger fused expression kernel markiert.
