# Keim Genesis Prototype v4.2

v4.2 verschiebt Keim von einer Simulationssprache in Richtung General-Purpose-Language.

## Sprachkern

- Neuer nativer Typ `karte` für dynamische HashMaps.
- Neuer nativer Typ `referenz` als Objekt-Referenzspeicher.
- `versuche:` / `fange fehler in speicher NAME:` als interne Fehlerbehandlung.
- Mark-and-Sweep-GC für dynamische `neu`-Objekte.
- Automatischer GC-Lauf pro Runde plus explizites `sammle muell`.
- Neue Bytecode-Ops:
  - `MAP_SET`
  - `MAP_GET`
  - `MAP_DELETE`
  - `JSON_PARSE`
  - `JSON_STRINGIFY`
  - `HTTP_SERVER_START`
  - `TIME_NOW`
  - `CRYPTO_HASH`
  - `PROCESS_RUN`
  - `TRY_BEGIN`
  - `CATCH_BEGIN`

## Collections

```keim
speicher daten karte startet bei {}
karte daten setzt "name" auf "Ada"
karte daten liest "name" in speicher ziel
karte daten loescht "name"
```

## Fehlerbehandlung

```keim
versuche:
    objekt fehlt ruft ping
fange fehler in speicher fehler:
    speicher status setzt 1
```

Nur `KeimRuntimeError` wird gefangen; Syntaxfehler bleiben Host-Fehler.

## Standardbibliothek / Batteries

### JSON

```keim
json liest speicher raw in speicher obj
json schreibt speicher obj in speicher raw
```

### HTTP-Server

```keim
server startet bei 18080 antwortet speicher antwort
```

Der Server läuft lokal auf `127.0.0.1` in einem Daemon-Thread.

### Zeit

```keim
zeit jetzt in speicher zeitpunkt
```

Textspeicher erhalten ISO-UTC-Zeit, Ganzzahlspeicher Nanosekunden, Zahlspeicher Sekunden.

### Krypto

```keim
krypto sha256 speicher quelle in speicher digest
```

Unterstützt `sha256`, `sha1`, `md5`.

### Prozess

```keim
prozess fuehrt "python --version" in speicher ausgabe
```

Der Prozessaufruf nutzt `shlex.split`, kein Shell-String, Timeout 5 Sekunden.

## Validierung

- `tests/run_tests.py` enthält jetzt `test_v42_gpl_core_features`.
- `tests/run_v42_gpl_tests.py` validiert Collections, JSON, Fehlerbehandlung, GC, Zeit, Krypto, HTTP-Server-Bytecode und Prozess-Bytecode.

## Grenzen

- `prozess` ist absichtlich konservativ: kein Shell-Modus, Timeout, nur stdout/stderr als Text.
- HTTP-Server sind aktuell einfache lokale Text-Responder.
- Generics sind noch nicht implementiert; `karte` und `liste` sind dynamisch typisierte Container.
