# Keim Genesis v2.3 Änderungen

## Drei implementierte Sprachschritte

1. **Benannte Laufzeitregeln**
   - Neue Syntax: `regel NAME:` und `rufe NAME`
   - Neue AST-Knoten: `RuleDecl`, `CallRule`
   - Neue Bytecode-Ops: `BEGIN_RULE`, `CALL_RULE`
   - Statische Analyse für unbekannte Regeln, Duplikate und Call-Zyklen
   - Runtime-Rekursionsschutz

2. **Native strukturierte Kontrollblöcke**
   - Parser trägt `wenn ...:`, `sonst:` und `wiederhole N mal:` als AST
   - Neue AST-Knoten: `IfBlock`, `RepeatBlock`
   - Neue Bytecode-Ops: `BEGIN_IF`, `BEGIN_ELSE`, `BEGIN_REPEAT`
   - Masken werden durch verschachtelte Blöcke weitergereicht

3. **Sichere Ausdrucksfunktionen**
   - Neue Funktionen in `feld NAME wird ...`:
     `min`, `max`, `abs`, `clamp`, `mix`, `step`
   - Weiterhin kein Python-`eval`, keine Attribute, keine Imports
   - Ausdrucksreferenzen für Felder/Spuren/Speicher bleiben statisch analysierbar

## Validierung

Ausgeführt:

```powershell
python tests\run_tests.py
python -m compileall keim
python -m keim analyze examples\sprache_v23.keim
python -m keim bytecode examples\sprache_v23.keim
python -m keim run examples\sprache_v23.keim --backend segmented --rounds 3 --show-every 0
```

Alle Keim-Tests liefen erfolgreich. Die Sandbox meldete beim Python-Start eine externe `artifact_tool`-Spreadsheet-Warmup-Warnung; sie gehört nicht zum Keim-Code.
