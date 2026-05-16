# Keim Genesis Prototype v2.9

v2.9 vertieft Keim zur Daten- und Objektprogrammiersprache.

## v2.7 — Tabellen als Runtime-Zustand

Neue Syntax:

```keim
tabelle messungen mit tick zahl, risiko zahl, modus text
tabelle messungen fuegt tick=zeit risiko=speicher.risiko_max modus=aktiv ein
```

Tabellen sind kein Exportformat, sondern Teil des Runtime-Zustands. Eine Tabellenzeile kann Werte aus `zeit`, `speicher.NAME`, `feld.NAME`, `spur.NAME` und `objekt.NAME.eigenschaft` lesen.

## v2.8 — Datenbanken

Neue Syntax:

```keim
datenbank log bei "out/messungen.sqlite"
datenbank log speichert tabelle messungen
```

Die CPU-Referenz schreibt neue Tabellenzeilen nach SQLite. Bereits exportierte Zeilen werden pro `(datenbank, tabelle)` gemerkt, damit periodisches Speichern nicht immer alle alten Zeilen erneut ausgibt.

## v2.9 — Klassen, Objekte und Methoden

Neue Syntax:

```keim
klasse waechter:
    eigenschaft schwelle = 0.18
    methode pruefe:
        wenn speicher risiko_max > selbst.schwelle:
            speicher alarm setzt 1.0

objekt alarmwache ist waechter mit schwelle=0.16

jede runde:
    objekt alarmwache ruft pruefe
```

Methoden bestehen aus normalen Keim-Schritten. Innerhalb von Methoden kann `selbst.EIGENSCHAFT` als rechte Seite in Bedingungen genutzt werden.

## Architektur

Neue AST-Knoten:

- `TableDecl`
- `TableInsert`
- `DatabaseDecl`
- `DatabaseSave`
- `ClassDecl`
- `ObjectDecl`
- `ObjectCall`
- `SelfPropertyRef`

Neue Bytecode-Ops:

- `ALLOC_TABLE`
- `TABLE_INSERT`
- `ALLOC_DATABASE`
- `DATABASE_SAVE`
- `DEFINE_CLASS`
- `ALLOC_OBJECT`
- `CALL_METHOD`

## Grenzen

- Tabellen sind aktuell append-only.
- SQLite-Export ist CPU-seitig und bewusst eine Host-Barriere.
- Objektmethoden haben `selbst` in Bedingungen, aber noch keine frei berechenbaren Objekt-Ausdrücke.
- Klassen sind flache Wertbehälter; Vererbung ist noch nicht implementiert.
