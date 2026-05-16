# Keim v4.4: GUI, FFI, Pakete und Async

## Web-GUI starten

```powershell
python -m keim gui --port 18081 --api http://127.0.0.1:18080
```

Öffne danach:

```text
http://127.0.0.1:18081/
```

## Web-GUI aus Keim deklarieren

```keim
webgui kontrollraum bei 18081 titel "Keim Kontrollraum" api "http://127.0.0.1:18080"
```

## FFI

```keim
bibliothek mathlib laedt "meine.dll"

speicher ergebnis ganzzahl startet bei 0

jede runde:
    ffi mathlib ruft "addiere" mit 2 3 in speicher ergebnis als ganzzahl
```

## Async/Await

```keim
hintergrund vorbereiten:
    speicher status setzt "fertig"

jede runde:
    erwarte vorbereiten in speicher ok
```

## Pakete

```powershell
python -m keim init --name meine_app
python -m keim get ./mein_paket
python -m keim packages
```

## Standalone-Starter

```powershell
python -m keim export-bin examples/sprache_v44_gui_ffi_async.keim --out dist/meine_app
```
