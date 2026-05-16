# Keim Genesis v4.0

Diese Version zieht die v3.0-Basis zu einer "Best of Both Worlds"-Engine zusammen.

## v3.1/v3.2 Logic & Data
- `neu`-Schlüsselwort für dynamische Objektinstanzen: `neu Klasse als name`.
- Objektzustand besitzt `refcount`, `dynamic` und `alive`; `loesche objekt NAME` + `sammle muell` implementieren einen einfachen Referenz-/GC-Pfad.
- Native Listenform für Speicher/Felder: `speicher werte liste mit zahl startet bei [1,2]`.
- Listenaktionen: `liste werte haengt WERT an`, `liste werte nimmt letztes in speicher ziel`.
- Tabellenindices: `index messungen auf tick`.
- Tabellenabfragen: `tabelle messungen sucht tick == 1 in speicher treffer`.

## v3.3-v3.5 Batteries Included
- Datei-Batterie: JSON/CSV lesen und schreiben aus Runtime-Tabellen.
- Anfrage-Batterie: `anfrage GET URL in speicher antwort`.
- Mathe-Batterie: `perlin`, `simplex`, `rauschen`, `ganz` als sichere Ausdrucksfunktionen.
- A*-Pfadfindung: `pfad von X Y nach X Y [mit spur S] in tabelle T`.
- Visualisierung: `bild schreibt png|bmp PFAD aus spur|feld NAME`.
- Dashboard-Snapshot: `dashboard startet bei PFAD`.

## v4.0 Native Bridge
- Die C++-ABI bleibt kompatibel und wird auf Version 400 gehoben.
- Der native Kern bleibt absichtlich Hotspot-orientiert; vollständige Sprache läuft weiter deterministisch über Python.
- GPU/VRAM-Residenz ist in Bytecode-Regimen und ABI-Hinweisen sichtbar, aber ohne plattformspezifisches CUDA/Metal-Projekt nicht als ausführbarer Device-Interpreter ausgeliefert.
