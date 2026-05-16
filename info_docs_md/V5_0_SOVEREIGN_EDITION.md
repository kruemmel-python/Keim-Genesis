# Keim Genesis v5.0 Sovereign Edition

## Keim-Kit

```keim
verwende system.grafik
verwende system.audio
```

`system.grafik` erzeugt Host-/Canvas-Kommandos:

```keim
fenster haupt erzeugen 800 600 titel "Keim Fenster"
grafik farbe 20 30 40
grafik rechteck 10 20 120 60
grafik kreis 200 120 30
grafik text 20 20 "Hallo Keim"
grafik anzeigen
fenster haupt schliessen
```

`system.audio` erzeugt plattformneutrale Events. Auf Windows kann `winsound.Beep` optional genutzt werden:

```keim
audio ton 440 dauer 250
audio signal "ok"
audio stumm wahr
```

## Generics

```keim
speicher zahlen ist liste<ganzzahl>
speicher index ist karte<text, ganzzahl>

jede runde:
    liste zahlen fuegt 1 hinzu
    karte index setzt "status" auf 200
```

Offensichtliche Fehler wie `liste zahlen fuegt "falsch" hinzu` werden statisch gemeldet und zur Laufzeit zusätzlich geschützt.

## Debug-Protokoll

```keim
debug beobachtet speicher running
debug sendet "runde"
```

CLI:

```powershell
python -m keim debug app.keim --port 18082
```

HTTP-Endpunkte:

- `GET /debug/events`
- `GET /debug/state`

Die Runtime nutzt einen `collections.deque(maxlen=...)`, damit Debug-Events im Hotspot nur angehängt werden.

## Sandbox

Deklaration:

```keim
berechtigung system.netz
berechtigung system.io
berechtigung system.prozess
berechtigung system.ffi
```

CLI:

```powershell
python -m keim run app.keim --sandbox strict --allow netz
python -m keim serve app.keim --sandbox strict --allow netz
```

Im permissiven Modus bleibt alte Kompatibilität erhalten. Im strict-Modus werden Netzwerk, Dateisystem, Prozessstart und FFI geprüft.

## Standalone-Export

```powershell
python -m keim export-bin examples/sprache_v50_sovereign.keim --out dist/app --asset config.json
python dist/app/keim_app.py
```

Erzeugt:

```text
dist/app/
├─ keim_app.py
├─ keim_app.bat
├─ app.kbc.json
├─ assets/
├─ runtime/
├─ bundle_manifest.json
└─ README_RUN.txt
```

Optional:

```powershell
python -m keim export-py examples/sprache_v50_sovereign.keim --out dist/app_single.py
```

## Grenzen

- Grafik ist standardmäßig Host-/WebCanvas-orientiert; SDL/Raylib sind FFI-/Native-Erweiterungspunkte.
- Audio ist plattformneutral als Event-Log, mit optionalem Windows-Beep.
- Eine native Single-File-EXE braucht weiterhin PyInstaller, Nuitka, MSVC/Linker oder einen anderen externen Packager.
