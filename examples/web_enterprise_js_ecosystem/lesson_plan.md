# Schulungsplan: Keim Web/Ecosystem v7.3

## Ziel

Keim soll nicht länger außerhalb großer JS-Ökosysteme stehen, sondern über eine kontrollierte Brücke Web-Apps und bestehende Bibliotheken erreichen.

## Lektionen

1. `keim.web.toml` lesen.
2. Importmap-Bridge verstehen.
3. JS-Adapter als Sicherheitsgrenze.
4. PWA-Artefakte prüfen.
5. `keim.web.lock.json` für reproduzierbare Builds verwenden.
6. Offline-Modus über `provider = "local"` vorbereiten.

## Übung

```bash
python -m keim web-build --cwd examples/web_enterprise_js_ecosystem --out build/web_enterprise
python -m keim web-serve --out build/web_enterprise --port 8787
```
