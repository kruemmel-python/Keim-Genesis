# Keim Genesis v7.3 – Web/Ecosystem Layer

v7.3 behebt die Einschränkung, dass Keim nicht für große Standard-Ökosysteme oder Web-Apps mit existierenden JavaScript-Bibliotheken geeignet sei.

## Kernidee

Keim versucht nicht, das npm-Ökosystem zu kopieren. Stattdessen definiert v7.3 eine kontrollierte Brücke:

```text
keim.web.toml
→ Importmap
→ JS-Adapter
→ Keim Web Runtime
→ PWA-/SPA-Artefakte
→ keim.web.lock.json
```

## Neue Fähigkeiten

- Web-Projekt-Scaffold
- Importmap-Brücke zu npm/CDN/Local-Vendor
- JS-Adapter-Registry mit Berechtigungsmodell
- DOM/Event-Runtime
- PWA-Artefakte
- Web-Lockfile mit Quellhashes
- lokaler Web-Server
- Schulungsprojekt `examples/web_enterprise_js_ecosystem`

## Warum Importmaps?

Importmaps sind transparent. Sie vermeiden versteckte Bundler-Magie und erlauben trotzdem Zugriff auf viele bestehende JS-Module. Für Enterprise-/Offline-Deployments können externe URLs durch lokale `vendor/`-Pfade ersetzt werden.

## Grenzen

v7.3 ist eine Web/Ecosystem-Schicht, kein vollständiger Ersatz für Vite, Webpack oder npm. Der professionelle Weg ist Interop statt Nachbau: Keim erzeugt kontrollierte Artefakte und bindet existierende Bibliotheken über Adapter ein.
