# Migration v4.3.3 → v7.5 Enterprise

Diese Datei erklärt, wie die ursprünglichen Keim-Schulungsunterlagen auf den aktuellen Projektstand erweitert wurden.

## Grundsatz

Die v4.3.3-Schulung bleibt vollständig erhalten. Sie wurde nicht gekürzt, nicht ersetzt und nicht didaktisch umgebaut. Der v7.5-Stand wurde als zusätzlicher Aufbaukurs ergänzt.

## Alte Begriffe und neue Entsprechungen

| v4.3.3-Konzept | v7.5-Erweiterung | Bedeutung |
|---|---|---|
| Native VM | Native-VM-MVP, Paritätsmanifeste | Der Weg zur souveränen Ausführung ist konkreter geworden. |
| Bytecode | KBC-STABLE-1 | Bytecode ist nun als stabile Enterprise-Spezifikation erklärbar. |
| Debugging | Replay, Time-Travel, Hardening Reports | Fehlersuche wird reproduzierbarer. |
| HTTP/API | Web-Interop, Importmaps, JS-Adapter | Keim kann Web-Schulungsprojekte kontrolliert einbinden. |
| Speicher/Collections | WASM Heap, Hashmap, GC, Region Allocator | Datenstrukturen sind nun auch aus Runtime-Sicht erklärbar. |
| Projekte | Training Impossible, Hardening Matrix | Keim besitzt aktuelle Schulungsprojekte für Runtime und Optimierung. |

## Empfohlene Unterrichtsfolge

1. Alte Kapitel 0–22 vollständig durchführen.
2. Danach Kapitel 23 als Update-Brücke.
3. KBC-STABLE-1 und Result/Match erklären.
4. Native/WASM/GC als Architekturmodule einsetzen.
5. Web/Interop und Training Impossible als Projektmodule nutzen.
6. Hardening Matrix als Abschlussprüfung verwenden.

## Wichtiger Hinweis

Nicht jede v7.5-Funktion ist für Einsteiger geeignet. Die neuen Kapitel sind bewusst als Aufbaukurs formuliert.
