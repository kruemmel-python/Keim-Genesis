# Dozentenleitfaden für Keim Genesis Schulungsunterlagen v4.3.3 + v7.5

## Zielgruppe

- Einsteigerinnen und Einsteiger: Kapitel 0–22
- Fortgeschrittene: Kapitel 23–30
- Enterprise-/Runtime-Schulungen: Kapitel 31–34
- Compiler-/WASM-/Security-Kurse: Kapitel 24–33

## Kursvarianten

### 1-Tages-Workshop

| Zeit | Inhalt |
|---|---|
| 09:00–10:30 | Keim-Denkmodell, Syntax, erstes Programm |
| 10:45–12:00 | Typen, Speicher, Kontrollfluss |
| 13:00–14:30 | Simulation und API-Grundlagen |
| 14:45–16:00 | KBC-STABLE-1 und Result/Match |
| 16:00–17:00 | Hardening-Matrix-Demo |

### 3-Tages-Kurs

Tag 1: Grundlagen v4.3.3  
Tag 2: Daten, Simulation, Runtime und Debugging  
Tag 3: v7.5 Enterprise: Bytecode, Security, Web, WASM, Hardening

### 5-Tages-Enterprise-Kurs

1. Sprache und Syntax
2. Simulation, Daten und APIs
3. Typed AST, Bytecode, KBC-STABLE-1
4. Native/WASM/GC/Web/Security
5. Training Impossible + Abschlussprojekt

## Praktische Übungen

- `examples/legacy/`: ursprüngliche v4.3.3-Übungen
- `examples/current/v75_01_stable_bytecode.keim`: Bytecode-Grundlage
- `examples/current/v75_02_result_match.keim`: Result/Match
- `examples/current/v75_03_record_map_list.keim`: Datenmodell
- `examples/current/v75_04_actor_replay.keim`: Actor/Replay
- `examples/current/v75_05_web_adapter.keim`: Web-Berechtigungen
- `examples/current/v75_06_training_impossible_policy.keim`: Training Impossible

## Prüfungsaufgabe

Die Teilnehmenden bauen eine kleine Policy-Funktion, erzeugen daraus Bytecode, dokumentieren die Capabilities und erzeugen ein Hardening-Report-Artefakt.

## Bewertungsraster

| Kriterium | Punkte |
|---|---:|
| Keim-Syntax korrekt | 20 |
| Typen sauber verwendet | 20 |
| Result/Match oder Fehlerbehandlung | 15 |
| Runtime-Artefakte nachvollziehbar | 15 |
| Security/Capability erklärt | 15 |
| Dokumentation und Präsentation | 15 |

---

# Ergänzung für Keim v7.8.5

## Neue Zielgruppe

- Fortgeschrittene Teilnehmende, die Keim-Programme nicht nur ausführen, sondern paketieren und veröffentlichen wollen.
- Runtime-/Deployment-Schulungen mit GPU-, Web- und Native-Bezug.
- Dozentinnen und Dozenten, die den Unterschied zwischen Runtime-Bundle, Bootstrapper und nativer Übersetzung sauber erklären müssen.

## Zusätzlicher 1-Tages-Block: v7.8.5 Runtime Packaging

| Zeit | Inhalt |
|---|---|
| 09:00–10:00 | Wiederholung v7.5: Runtime, Bytecode, Result/Match, Web, Security |
| 10:15–11:30 | Full Runtime Packager: Manifest, Scripts, Value Model, Modul-Tabelle |
| 11:30–12:30 | Packaging-Modi: full-runtime, native-subset, zipapp, directory-bundle |
| 13:30–14:30 | GPU-aware Packaging: Treiber, Manifest, Smoke-Test, CPU-Fallback |
| 14:45–15:45 | Self-Bootstrapping Launcher: PE64/ELF64 ohne externe Toolchain |
| 16:00–17:00 | Abschlussübung: Paket bauen, prüfen, starten und dokumentieren |

## Neue Übungen

- `examples/current/v785_01_exe_runtime_packager.keim`: kleines Programm für Runtime-Bundle.
- `examples/current/v785_02_gpu_aware_packaging.keim`: deterministischer CPU/GPU-Fallback als Schulungsmodell.
- `examples/current/v785_03_web_overlay_policy.keim`: Fachlogik für Projekt-Web-Overlay.
- `examples/current/v785_packager_manifest.json`: didaktisches Manifest mit Packaging-Modi, Value-Tags und Features.

## Zusätzliche Prüfungsaufgabe

Die Teilnehmenden erzeugen aus einem Keim-Programm ein Directory-Bundle, prüfen es mit `exe-verify`, erklären die Paketstruktur und dokumentieren, ob GPU optional oder erforderlich ist.

## Zusatz-Bewertungsraster

| Kriterium | Punkte |
|---|---:|
| Paketstruktur korrekt erklärt | 20 |
| `exe-status`, `exe-pack`, `exe-verify`, `exe-run` korrekt eingesetzt | 20 |
| Unterschied Bootstrapper vs. AOT-Compiler erklärt | 20 |
| GPU-Manifest/Smoke-Test/CPU-Fallback erklärt | 20 |
| Web-Overlay oder zipapp/directory-bundle nachvollziehbar dokumentiert | 20 |

