# Keim v7.6.4 – Linux GPU Driver Support

v7.6.4 macht den vorhandenen Linux-Treiber `driver/build/libCC_OpenCL.so` zu einem echten Keim-GPU-Treiberartefakt.

## Was geändert wurde

Vorher war die v7.6-Schicht stark auf `driver/build/CC_OpenCl.dll` fokussiert. Das war für Windows korrekt, aber unvollständig, weil im Driver-Ordner zusätzlich ein Linux-Build liegt.

Jetzt gilt:

| Plattform | bevorzugtes Artefakt |
|---|---|
| Windows | `driver/build/CC_OpenCl.dll` |
| Linux | `driver/build/libCC_OpenCL.so` |
| macOS | vorbereitet für `.dylib` / `.so` |

## Laufzeitverhalten

Keim prüft:

- Existenz des Treiberartefakts
- SHA-256
- Core-Symbole
- Kernel-Symbole
- optionale Utility-Symbole
- native Ladefähigkeit mit `ctypes.CDLL`

Wenn die Bibliothek ladbar ist, aber kein OpenCL-Gerät vorhanden ist, bricht Keim nicht unkontrolliert ab. Der Dispatcher fällt auf die CPU-Differentialreferenz zurück und dokumentiert den Grund im Profil.

## JSON-Vertrag

Einige native OpenCL-Treiber schreiben direkt nach stdout/stderr. Für `--json` werden native Ausgaben deshalb während des Demo-Dispatchs unterdrückt, damit die CLI-Ausgabe gültiges JSON bleibt.

## Test

```bash
python -S tests/run_v764_linux_gpu_driver_tests.py
```
