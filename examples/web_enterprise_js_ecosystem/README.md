# keim_web_enterprise_training

Dieses Projekt demonstriert Keim v7.3 als Web-/Ökosystem-Schicht.

## Kommandos

```bash
python -m keim web-build --cwd . --out dist
python -m keim web-serve --out dist --port 8787
```

## Konzepte

- Importmap statt verstecktem Bundler-Zwang
- JS-Adapter für bestehende Bibliotheken
- PWA-Artefakte
- keim.web.lock.json mit Quellhashes
- DOM/Event-Runtime für Schulungen
