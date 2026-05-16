from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = [sys.executable, "-S"]


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(PY + ["-m", "keim", *args], cwd=ROOT, text=True, capture_output=True, check=True)


def test_web_build_prefers_project_web_index() -> None:
    project = ROOT / "build" / "v784_project_web_overlay"
    out = project / "build" / "web"
    if project.exists():
        shutil.rmtree(project)
    (project / "src").mkdir(parents=True)
    (project / "web" / "assets").mkdir(parents=True)
    (project / "web").mkdir(exist_ok=True)
    (project / "keim.toml").write_text("""
[projekt]
name = "agenten_zweige_overlay_test"
version = "0.1.0"
title = "Agenten Zweige Web"
main = "src/main.keim"
""".strip() + "\n", encoding="utf-8")
    (project / "src" / "main.keim").write_text("""
modul overlay.main

exportiere funktion main

funktion main() gibt ganzzahl:
    rueckgabe 42

test "main":
    pruefe main() == 42
""".strip() + "\n", encoding="utf-8")
    (project / "web" / "index.html").write_text("""<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <title>Agenten Zweige Fachansicht</title>
  <link rel="stylesheet" href="./assets/style.css">
</head>
<body>
  <main id="app">
    <h1>Agenten-Zweige Webansicht</h1>
    <p id="marker">Projekt-Webansicht statt generischer Zähler-Shell</p>
    <script type="module" src="./keim_agenten_adapter.js"></script>
  </main>
</body>
</html>
""", encoding="utf-8")
    (project / "web" / "keim_agenten_adapter.js").write_text("""
export function agentBasis(zweig) {
  return 1 + Number(zweig);
}
export function agentQuadrat(wert) {
  return Number(wert) * Number(wert);
}
""".strip() + "\n", encoding="utf-8")
    (project / "web" / "assets" / "style.css").write_text("body{background:#0f172a;color:white}\n", encoding="utf-8")

    res = run("web-build", "--cwd", str(project), "--out", str(out), "--json")
    payload = json.loads(res.stdout)
    assert payload["ok"], payload
    html = (out / "index.html").read_text(encoding="utf-8")
    assert "Agenten-Zweige Webansicht" in html
    assert "Projekt-Webansicht statt generischer Zähler-Shell" in html
    assert "Zähler:" not in html
    assert (out / "keim_agenten_adapter.js").exists()
    assert (out / "keim-web-runtime.js").exists()
    assert (out / "app.kweb.json").exists()
    kweb = json.loads((out / "app.kweb.json").read_text(encoding="utf-8"))
    assert kweb["project_web_overlay"]["enabled"] is True
    diagnostics = payload["diagnostics"]
    assert any("Projekt-Webansicht übernommen" in d["message"] for d in diagnostics)


def test_web_build_rejects_eval_in_project_web() -> None:
    project = ROOT / "build" / "v784_project_web_eval_reject"
    out = project / "build" / "web"
    if project.exists():
        shutil.rmtree(project)
    (project / "src").mkdir(parents=True)
    (project / "web").mkdir(parents=True)
    (project / "keim.toml").write_text("""
[projekt]
name = "bad_eval_project"
version = "0.1.0"
main = "src/main.keim"
""".strip() + "\n", encoding="utf-8")
    (project / "src" / "main.keim").write_text("modul bad\n\nfunktion main() gibt ganzzahl:\n    rueckgabe 0\n", encoding="utf-8")
    (project / "web" / "index.html").write_text("<script>eval('1+1')</script>", encoding="utf-8")
    res = subprocess.run(PY + ["-m", "keim", "web-build", "--cwd", str(project), "--out", str(out), "--json"], cwd=ROOT, text=True, capture_output=True)
    assert res.returncode == 1, res.stdout + res.stderr
    payload = json.loads(res.stdout)
    assert any("eval/Function" in d["message"] for d in payload["diagnostics"])


def main() -> int:
    test_web_build_prefers_project_web_index()
    test_web_build_rejects_eval_in_project_web()
    print("[Keim v7.8.4] Project Web Overlay Tests OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
