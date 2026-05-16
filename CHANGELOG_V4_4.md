# Keim Genesis v4.4.0

## Große Evolutionsstufe: visuelle Welt, FFI, Pakete, Async

### GUI-Säule
- Neue Web-GUI-Batterie `keim.webui`.
- Neuer Sprachknoten: `webgui NAME bei PORT titel "..." api "..."`.
- CLI-Befehl: `keim gui --port 18081 --api http://127.0.0.1:18080`.
- Die GUI läuft lokal, benötigt keine Cloud und verbindet sich mit Keim-HTTP-Diensten.

### Foreign Function Interface
- Neues Modul `keim.ffi`.
- Neuer Sprachknoten: `bibliothek NAME laedt "PFAD"`.
- Neue Aktion: `ffi NAME ruft "funktion" [mit ...] [in speicher ZIEL] [als TYP]`.
- Unterstützt primitive C-ABI-Typen: `ganzzahl`, `zahl`, `bool`, `text`, `referenz`.

### Async/Await-Grundlage
- Neuer Top-Level-Block: `hintergrund NAME:`.
- Neue Aktion: `erwarte NAME [in speicher ZIEL]`.
- Ausführung über ThreadPoolExecutor, deterministisch abwartbar über `erwarte`.

### Paketmanager
- Neues Modul `keim.package_manager`.
- CLI:
  - `keim init`
  - `keim get ORDNER_ODER_ZIP`
  - `keim packages`
- Lokale, souveräne Paketverwaltung über `.keim_packages/` und `keim.lock.json`.

### CLI-Ausbau
- `keim doctor`
- `keim routes DATEI.keim`
- `keim serve DATEI.keim`
- `keim gui`
- `keim export-bin DATEI.keim --out dist/app`

### Native ABI
- Native VM erhält v4.4-Metadaten-Hooks:
  - `keim_abi_version_v44`
  - `keim_shader_bundle_supported`
  - `keim_gui_backend_supported`

## Validierung
- `python tests/run_tests.py` OK
- `python tests/run_v44_gpl_gui_ffi_tests.py` OK
- C++ Syntaxcheck: OK
