# Keim Genesis v5.0.0 Sovereign Edition

## Neu

- Keim-Kit: `system.grafik` und `system.audio` mit plattformneutralen Host-Events.
- Standalone-Export: `keim export-bin` erzeugt `keim_app.py`, `app.kbc.json`, `assets/`, `runtime/`, `bundle_manifest.json` und `README_RUN.txt`.
- Single-File-Python-Export: `keim export-py`.
- Generics: `liste<T>` und `karte<K,V>` werden vom Parser akzeptiert und bei offensichtlichen Einfüge-/Zuweisungsfehlern geprüft.
- DebugBus: `debug beobachtet speicher NAME` und `debug sendet "marke"` schreiben in einen Ringbuffer; `keim debug` stellt HTTP-Endpunkte bereit.
- Sandbox: `berechtigung system.netz|system.io|system.prozess|system.ffi` plus CLI `--sandbox strict --allow ...`.
- Native ABI v5-Hooks: Debug-, Grafik-, Audio- und Permission-Sinks ohne SDL-/Audio-Linkzwang.

## Ehrliche Grenze

Eine echte einzelne native `.exe` wird ohne externen Linker/Packager nicht garantiert. v5 liefert einen lauffähigen Python-Standalone-Ordner und ein Single-File-Python-Bundle.
