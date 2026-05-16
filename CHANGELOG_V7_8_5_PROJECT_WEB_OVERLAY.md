# Changelog v7.8.5 Project Web Overlay

- `web-build` übernimmt nun `<projekt>/web/index.html`, wenn vorhanden.
- Projekt-Webdateien werden nach `build/web` kopiert.
- Keim-Runtime-, PWA-, Lock- und Adapter-Artefakte werden weiterhin ergänzt.
- Generische Zähler-Shell wird nur noch erzeugt, wenn keine Projekt-Webansicht existiert.
- `eval` und `Function` in Projekt-Webdateien führen zu einem Fehler.
- `app.kweb.json` dokumentiert `project_web_overlay`.
- Neues Beispiel `examples/agenten_zweige_v78_1_gpu_aware`.
- Neuer Test `tests/run_v784_project_web_overlay_tests.py`.
