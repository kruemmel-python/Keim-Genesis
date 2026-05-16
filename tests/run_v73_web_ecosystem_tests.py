from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = [sys.executable, "-S"]


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(PY + ["-m", "keim", *args], cwd=ROOT, text=True, capture_output=True, check=True)


def test_web_status() -> None:
    res = run("web-status", "--json")
    payload = json.loads(res.stdout)
    assert payload["ok"] is True
    assert "importmap-npm-bridge" in payload["capabilities"]


def test_web_new_and_build() -> None:
    project = ROOT / "build" / "v73_test_web_project"
    out = ROOT / "build" / "v73_test_web_dist"
    if project.exists():
        import shutil
        shutil.rmtree(project)
    if out.exists():
        import shutil
        shutil.rmtree(out)

    run("web-new", str(project), "--name", "v73_test_web")
    assert (project / "keim.web.toml").exists()
    assert (project / "src" / "app.keim").exists()

    res = run("web-build", "--cwd", str(project), "--out", str(out), "--json")
    payload = json.loads(res.stdout)
    assert payload["ok"] is True
    assert "index.html" in payload["files"]
    assert "keim-web-runtime.js" in payload["files"]
    assert "app.js" in payload["files"]
    assert "@keim/runtime" in payload["importmap"]
    assert "signals" in payload["importmap"]
    assert (out / "service-worker.js").exists()
    assert (out / "keim.web.lock.json").exists()
    html = (out / "index.html").read_text(encoding="utf-8")
    assert '<script type="importmap">' in html
    app_js = (out / "app.js").read_text(encoding="utf-8")
    assert "KeimRuntime" in app_js


def test_web_adapter() -> None:
    out = ROOT / "build" / "v73_adapter.json"
    res = run("web-adapter", "--out", str(out), "--alias", "chart", "--module", "Chart", "--permission", "dom")
    payload = json.loads(res.stdout)
    assert payload["ok"] is True
    assert payload["adapter"]["alias"] == "chart"
    assert "dom" in payload["adapter"]["permissions"]
    assert out.exists()


def test_example_project_builds() -> None:
    out = ROOT / "build" / "v73_example_dist"
    res = run("web-build", "--cwd", "examples/web_enterprise_js_ecosystem", "--out", str(out), "--json")
    payload = json.loads(res.stdout)
    assert payload["ok"] is True
    lock = json.loads((out / "keim.web.lock.json").read_text(encoding="utf-8"))
    assert lock["format"] == "keim-web-lock-v1"
    assert any(d["name"] == "lit-html" for d in lock["dependencies"])


def main() -> int:
    test_web_status()
    test_web_new_and_build()
    test_web_adapter()
    test_example_project_builds()
    print("[Keim v7.3] Web/Ecosystem Tests OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
