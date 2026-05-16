# Sicherheit

Keim Genesis v2.0 ist ein lokaler Sprachprototyp.

Erlaubt und implementiert:

- lokale Python-3.12-Ausführung
- sichere Wertausdrücke ohne `eval`
- textuelle Baustein- und Kontrollfluss-Expansion
- lokale `erwarte`-Kontrakte
- optionale lokale DLL-Diagnose über expliziten Pfad

Nicht implementiert:

- Prozess-Injection
- Kernel-Mode-Zugriff
- automatische Treiberinstallation
- Remote-Code-Ausführung
- Makros mit Python-Code
- Netzwerkzugriff

`wenn`-/`sonst`-/`wiederhole`-Blöcke werden vor dem Parser in einfache Keim-Regeln desugared. Sie führen keinen Python-Code aus.
