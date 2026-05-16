# Web-Ansicht v7.8.1

Dieses Beispiel enthält eine kleine professionelle Web-Ansicht für Schulungen.

## Ziel

Die Seite visualisiert die Keim-Fachlogik aus `src/main.keim`:

```text
basis = 1 + zweig
quadrat = basis * basis
batch_summe_10 = 505
```

## Dateien

```text
web/index.html
web/keim_agenten_adapter.js
web/assets/style.css
```

## Keim-strenge GUI-Regeln

Die Web-Ansicht verwendet:

```text
kein eval
keine Function-Konstruktion
keine freie Ausdrucksauswertung
keine versteckte dynamische Businesslogik
```

Der Adapter ist bewusst statisch, deterministisch und dokumentiert. Er spiegelt die
Keim-Funktionen, damit die Schulungsseite ohne Webserver lokal geöffnet werden kann.

## Lokaler Start

```powershell
start web\index.html
```

## Optionaler Web-Build

```powershell
python -m keim web-build --cwd . --out build/web
```

## Grenzen

Diese Web-Ansicht ist eine Schulungsvisualisierung. Sie behauptet nicht, dass der Browser
direkt Keim-Bytecode ausführt. Für produktive Web-Bridge-Projekte ist der dokumentierte
Keim-Web-Adapter/Web-Build-Pfad zu verwenden.
