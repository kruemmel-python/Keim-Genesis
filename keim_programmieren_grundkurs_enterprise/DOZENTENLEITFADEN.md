# Dozentenleitfaden – Keim Grundkurs v4.3.3 + v7.5 Enterprise

## Ziel

Dieser Kurs soll weiterhin echte Schulungsunterlage sein, nicht nur Produktübersicht.
Die alte v4.3.3-Didaktik bleibt vollständig erhalten.

## Didaktische Linie

- Erst Programmieren lernen.
- Dann Architektur verstehen.
- Dann Enterprise-Artefakte erzeugen.
- Dann Web/WASM/Runtime/Hardening diskutieren.

## Praktische Labs

Siehe Kapitel 31 in `index.html`.

---

# Ergänzung für Keim v7.8.5

## Neue Unterrichtseinheit: Programme ausliefern

Die v7.8.5-Erweiterung erklärt Anfängern, dass ein Programm aus mehr als Quelltext bestehen kann:
Runtime, Manifest, Startskripte, optional GPU-Treiberplan, Web-Oberfläche und Prüfreport gehören zur Auslieferung.

## Empfohlener Ablauf

| Dauer | Thema |
|---|---|
| 30 min | Was ist ein Runtime-Bundle? |
| 30 min | `exe-status` lesen und Features markieren |
| 45 min | Directory-Bundle bauen und Ordnerstruktur prüfen |
| 30 min | `exe-verify` ausführen und Report besprechen |
| 45 min | GPU-aware Packaging als optionales Fortgeschrittenenthema |
| 30 min | Unterschied: Launcher, Runtime, Compiler |

## Merksätze für Lernende

- Ein Launcher startet ein Programm; er ist nicht automatisch der ganze Compiler.
- GPU-Unterstützung muss prüfbar sein, sonst ist sie nur eine Behauptung.
- Ein Manifest macht versteckte Annahmen sichtbar.
- Ein Directory-Bundle ist für Unterricht und Debugging leichter zu verstehen als ein Single-File-Artefakt.

