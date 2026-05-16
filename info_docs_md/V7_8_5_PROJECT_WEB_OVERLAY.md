# Keim v7.8.5 Project Web Overlay

v7.8.5 korrigiert den Web-Build-Pfad für reale Schulungs- und Beispielprojekte.

## Problem

Vor v7.8.5 erzeugte `python -m keim web-build` immer die generische Keim-Web-Shell mit Zähler-Demo, auch wenn im Projekt bereits eine eigene Webansicht unter `web/index.html` vorhanden war.

Dadurch sah ein Projekt mit eigener fachlicher Oberfläche nach dem Build wie eine Standard-Demo aus.

## Lösung

`web-build` erkennt jetzt:

```text
<projekt>/web/index.html
```

Wenn diese Datei existiert, wird die komplette Projekt-Webansicht nach `build/web` übernommen.

Zusätzlich erzeugt Keim weiterhin die Enterprise-Artefakte:

```text
keim-web-runtime.js
app.js, falls nicht projektseitig vorhanden
keim.web.lock.json
manifest.webmanifest
service-worker.js
adapters/keim-js-adapters.js
routes.json
README_DEPLOY.txt
app.kweb.json
```

## Sicherheitsregel

Projekt-Webansichten werden streng geprüft:

```text
eval(...)
Function(...)
```

führen zu einem Buildfehler. Damit bleibt die Keim-v1.4-Systemprompt-Regel erhalten: Fachlogik darf nicht versteckt als freie JavaScript-Evaluation laufen.

## Beispiel

```powershell
python -m keim web-build --cwd examples/agenten_zweige_v78_1_gpu_aware --out build/agenten_web
cd build/agenten_web
python -m http.server 8080
```

Browser:

```text
http://127.0.0.1:8080/
```

## Diagnose

`app.kweb.json` enthält bei Projekt-Webansichten:

```json
{
  "project_web_overlay": {
    "enabled": true,
    "source": "web",
    "files": ["index.html", "..."],
    "policy": "project-web-index-preferred"
  }
}
```
