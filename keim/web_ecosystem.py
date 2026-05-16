
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Literal
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import hashlib
import json
import re
import time
import tomllib


class WebEcosystemError(Exception):
    pass


@dataclass(slots=True)
class NpmDependency:
    name: str
    version: str = "*"
    alias: str | None = None
    provider: Literal["esm.sh", "jsdelivr", "unpkg", "local"] = "esm.sh"
    export: str | None = None

    @property
    def import_name(self) -> str:
        return self.alias or self.name.replace("/", "_").replace("@", "").replace("-", "_")

    def url(self) -> str:
        if self.provider == "esm.sh":
            suffix = "" if self.version in {"", "*"} else "@" + self.version
            return f"https://esm.sh/{self.name}{suffix}"
        if self.provider == "jsdelivr":
            suffix = "" if self.version in {"", "*"} else "@" + self.version
            return f"https://cdn.jsdelivr.net/npm/{self.name}{suffix}/+esm"
        if self.provider == "unpkg":
            suffix = "" if self.version in {"", "*"} else "@" + self.version
            return f"https://unpkg.com/{self.name}{suffix}?module"
        return f"./vendor/{self.name}/index.js"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class JsAdapter:
    alias: str
    module: str
    imports: dict[str, str] = field(default_factory=dict)
    globals: dict[str, str] = field(default_factory=dict)
    permissions: set[str] = field(default_factory=set)

    def as_dict(self) -> dict[str, Any]:
        return {
            "alias": self.alias,
            "module": self.module,
            "imports": self.imports,
            "globals": self.globals,
            "permissions": sorted(self.permissions),
        }


@dataclass(slots=True)
class WebAppManifest:
    name: str
    version: str = "0.1.0"
    title: str = "Keim Web App"
    main: str = "src/app.keim"
    mode: Literal["spa", "pwa", "widget"] = "spa"
    dependencies: list[NpmDependency] = field(default_factory=list)
    adapters: list[JsAdapter] = field(default_factory=list)
    permissions: set[str] = field(default_factory=set)
    routes: dict[str, str] = field(default_factory=lambda: {"/": "App"})
    assets: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": "keim-web-manifest-v1",
            "name": self.name,
            "version": self.version,
            "title": self.title,
            "main": self.main,
            "mode": self.mode,
            "dependencies": [d.as_dict() for d in self.dependencies],
            "adapters": [a.as_dict() for a in self.adapters],
            "permissions": sorted(self.permissions),
            "routes": self.routes,
            "assets": self.assets,
        }


@dataclass(slots=True)
class WebBuildResult:
    ok: bool
    app: str
    out: str
    files: list[str]
    importmap: dict[str, str]
    lock_sha256: str
    diagnostics: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def read_web_manifest(cwd: Path) -> WebAppManifest:
    cwd = Path(cwd)
    path = cwd / "keim.web.toml"
    if not path.exists():
        kt = cwd / "keim.toml"
        if kt.exists():
            data = tomllib.loads(kt.read_text(encoding="utf-8"))
            project = data.get("projekt", {})
            return WebAppManifest(
                name=str(project.get("name", cwd.name)),
                version=str(project.get("version", "0.1.0")),
                title=str(project.get("title", project.get("name", cwd.name))),
                main=str(project.get("main", "src/app.keim")),
            )
        raise WebEcosystemError(f"Keine keim.web.toml oder keim.toml gefunden: {cwd}")
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    project = data.get("web", {}) or data.get("projekt", {})
    deps = []
    raw_deps = data.get("npm", {}) or data.get("dependencies", {})
    for name, spec in raw_deps.items():
        if isinstance(spec, str):
            deps.append(NpmDependency(name=name, version=spec))
        elif isinstance(spec, dict):
            deps.append(NpmDependency(
                name=name,
                version=str(spec.get("version", "*")),
                alias=spec.get("alias"),
                provider=spec.get("provider", "esm.sh"),
                export=spec.get("export"),
            ))
    adapters = []
    raw_adapters = data.get("adapter", {}) or data.get("adapters", {})
    for alias, spec in raw_adapters.items():
        if isinstance(spec, str):
            adapters.append(JsAdapter(alias=alias, module=spec))
        elif isinstance(spec, dict):
            adapters.append(JsAdapter(
                alias=alias,
                module=str(spec.get("module", alias)),
                imports={str(k): str(v) for k, v in (spec.get("imports", {}) or {}).items()},
                globals={str(k): str(v) for k, v in (spec.get("globals", {}) or {}).items()},
                permissions=set(str(x) for x in spec.get("permissions", []) or []),
            ))
    mode = str(project.get("mode", "spa"))
    if mode not in {"spa", "pwa", "widget"}:
        mode = "spa"
    return WebAppManifest(
        name=str(project.get("name", cwd.name)),
        version=str(project.get("version", "0.1.0")),
        title=str(project.get("title", project.get("name", cwd.name))),
        main=str(project.get("main", "src/app.keim")),
        mode=mode,  # type: ignore[arg-type]
        dependencies=deps,
        adapters=adapters,
        permissions=set(str(x) for x in (project.get("permissions", []) or [])),
        routes={str(k): str(v) for k, v in (data.get("routes", {}) or {"/": "App"}).items()},
        assets=[str(x) for x in (project.get("assets", []) or [])],
    )


def init_web_project(out: Path, *, name: str = "keim_web_training_app") -> dict[str, Any]:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "src").mkdir(exist_ok=True)
    (out / "public").mkdir(exist_ok=True)
    (out / "adapters").mkdir(exist_ok=True)
    (out / "keim.web.toml").write_text(f'''[web]
name = "{name}"
version = "0.1.0"
title = "Keim Web Training App"
main = "src/app.keim"
mode = "pwa"
permissions = ["dom", "timer", "storage"]

[npm]
"@preact/signals-core" = {{ version = "^1.8.0", alias = "signals", provider = "esm.sh" }}
"lit-html" = {{ version = "^3.2.0", alias = "lit", provider = "esm.sh" }}

[routes]
"/" = "App"
"/training" = "TrainingView"

[adapter.browser]
module = "browser"
permissions = ["dom", "events", "storage", "timer"]
''', encoding="utf-8")
    (out / "src" / "app.keim").write_text('''modul web.training

exportiere funktion main

typ UiState:
    zaehler ist ganzzahl
    status ist text

funktion main() gibt ganzzahl:
    speicher state ist UiState setzt UiState("zaehler": 0, "status": "bereit")
    rueckgabe state.zaehler + 1

test "web state":
    pruefe main() == 1
''', encoding="utf-8")
    (out / "public" / "style.css").write_text(default_css(), encoding="utf-8")
    (out / "README.md").write_text(training_readme(name), encoding="utf-8")
    return {"ok": True, "path": str(out), "name": name}


def build_web_app(cwd: Path, out: Path, *, production: bool = True) -> WebBuildResult:
    cwd = Path(cwd)
    out = Path(out)
    manifest = read_web_manifest(cwd)
    out.mkdir(parents=True, exist_ok=True)
    (out / "assets").mkdir(exist_ok=True)
    (out / "adapters").mkdir(exist_ok=True)

    importmap = build_importmap(manifest)
    lock = build_web_lock(cwd, manifest)
    lock_sha = hashlib.sha256(json.dumps(lock, sort_keys=True).encode()).hexdigest()

    files: list[str] = []

    project_web = detect_project_web(cwd)
    overlay_files: list[str] = []
    if project_web is not None:
        overlay_files = copy_project_web_overlay(project_web, out, files)
        if not (out / "index.html").exists():
            write(out / "index.html", render_index(manifest, importmap, production=production), files, out)
        # Projekt-Webansichten dürfen eigene Adapter/App-Dateien mitbringen.
        # Fehlende Runtime-Artefakte werden dennoch ergänzt.
        if not (out / "app.js").exists():
            write(out / "app.js", render_app_js(manifest), files, out)
        if not (out / "assets" / "style.css").exists():
            css_src = cwd / "public" / "style.css"
            write(out / "assets" / "style.css", css_src.read_text(encoding="utf-8") if css_src.exists() else default_css(), files, out)
    else:
        write(out / "index.html", render_index(manifest, importmap, production=production), files, out)
        write(out / "app.js", render_app_js(manifest), files, out)
        css_src = cwd / "public" / "style.css"
        write(out / "assets" / "style.css", css_src.read_text(encoding="utf-8") if css_src.exists() else default_css(), files, out)

    # System-Artefakte werden immer erzeugt/überschrieben, damit Service Worker,
    # Importmap, Lockfile und Adapter Registry konsistent zum Keim-Build bleiben.
    write(out / "keim-web-runtime.js", render_runtime_js(manifest), files, out)
    write(out / "keim.web.lock.json", json.dumps(lock, ensure_ascii=False, indent=2), files, out)
    write(out / "manifest.webmanifest", render_pwa_manifest(manifest), files, out)
    write(out / "service-worker.js", render_service_worker(manifest), files, out)
    write(out / "adapters" / "keim-js-adapters.js", render_adapters_js(manifest), files, out)
    write(out / "routes.json", json.dumps({"routes": manifest.routes}, ensure_ascii=False, indent=2), files, out)
    write(out / "README_DEPLOY.txt", render_deploy_readme(manifest, project_web=project_web, overlay_files=overlay_files), files, out)

    source_path = cwd / manifest.main
    source_text = source_path.read_text(encoding="utf-8") if source_path.exists() else ""
    compiled = compile_web_source_stub(manifest, source_text)
    if project_web is not None:
        compiled["project_web_overlay"] = {
            "enabled": True,
            "source": str(project_web.relative_to(cwd)),
            "files": overlay_files,
            "policy": "project-web-index-preferred"
        }
    write(out / "app.kweb.json", json.dumps(compiled, ensure_ascii=False, indent=2), files, out)

    diagnostics = validate_web_build(out, manifest, project_web=project_web)
    return WebBuildResult(
        ok=not any(d["severity"] == "error" for d in diagnostics),
        app=manifest.name,
        out=str(out),
        files=files,
        importmap=importmap["imports"],
        lock_sha256=lock_sha,
        diagnostics=diagnostics,
    )



def detect_project_web(cwd: Path) -> Path | None:
    """Return project-specific web directory when it contains an index.html.

    v7.8.5 rule:
    - If <project>/web/index.html exists, web-build must prefer it.
    - Otherwise Keim generates the generic training shell.
    """
    web_dir = Path(cwd) / "web"
    if (web_dir / "index.html").exists():
        return web_dir
    return None


def copy_project_web_overlay(web_dir: Path, out: Path, files: list[str]) -> list[str]:
    """Copy project-owned web files into the build output.

    This deliberately ignores build/cache directories and hidden system folders.
    Keim-owned runtime files may be overwritten later by build_web_app.
    """
    overlay: list[str] = []
    web_dir = Path(web_dir)
    out = Path(out)
    ignore_dirs = {"build", "dist", "__pycache__", ".git", ".venv", "node_modules"}
    for src in sorted(web_dir.rglob("*")):
        if src.is_dir():
            continue
        rel = src.relative_to(web_dir)
        if any(part in ignore_dirs for part in rel.parts):
            continue
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
        rel_s = str(dst.relative_to(out))
        if rel_s not in files:
            files.append(rel_s)
        overlay.append(rel.as_posix())
    return overlay


def write(path: Path, text: str, files: list[str], root: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    files.append(str(path.relative_to(root)))


def build_importmap(manifest: WebAppManifest) -> dict[str, Any]:
    imports = {
        "@keim/runtime": "./keim-web-runtime.js",
        "@keim/adapters": "./adapters/keim-js-adapters.js",
        "@keim/app": "./app.js",
    }
    for dep in manifest.dependencies:
        imports[dep.import_name] = dep.url()
        imports[dep.name] = dep.url()
    return {"imports": imports}


def build_web_lock(cwd: Path, manifest: WebAppManifest) -> dict[str, Any]:
    sources = []
    for p in sorted(Path(cwd).rglob("*")):
        if p.is_file() and p.name not in {"keim.web.lock.json"} and ".git" not in p.parts:
            try:
                digest = hashlib.sha256(p.read_bytes()).hexdigest()
                sources.append({"path": str(p.relative_to(cwd)), "sha256": digest, "size": p.stat().st_size})
            except OSError:
                pass
    permissions = set(manifest.permissions)
    for adapter in manifest.adapters:
        permissions.update(adapter.permissions)
    return {
        "format": "keim-web-lock-v1",
        "app": manifest.name,
        "version": manifest.version,
        "generated_at": int(time.time()),
        "dependencies": [dict(d.as_dict(), url=d.url(), sha256_policy="remote-url-pinned") for d in manifest.dependencies],
        "adapters": [a.as_dict() for a in manifest.adapters],
        "sources": sources,
        "permissions": sorted(permissions),
    }


def compile_web_source_stub(manifest: WebAppManifest, source: str) -> dict[str, Any]:
    functions = re.findall(r"funktion\s+(\w+)\(", source)
    types = re.findall(r"typ\s+(\w+)\s*:", source)
    return {
        "format": "keim-web-bytecode-manifest-v1",
        "app": manifest.name,
        "main": manifest.main,
        "functions": functions,
        "types": types,
        "routes": manifest.routes,
        "runtime": "keim-web-runtime-v1",
        "dom_bindings": {
            "root": "#app",
            "event_bus": "KeimRuntime.dispatch",
            "state_store": "KeimRuntime.state",
        },
        "interop": {
            "importmap": build_importmap(manifest)["imports"],
            "adapters": [a.as_dict() for a in manifest.adapters],
        },
    }


def validate_web_build(out: Path, manifest: WebAppManifest, *, project_web: Path | None = None) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    required = ["index.html", "keim-web-runtime.js", "app.js", "keim.web.lock.json"]
    for rel in required:
        if not (out / rel).exists():
            diagnostics.append({"severity": "error", "message": f"Pflichtdatei fehlt: {rel}"})
    html = (out / "index.html").read_text(encoding="utf-8") if (out / "index.html").exists() else ""
    if "<script type=\"importmap\">" not in html and 'type="importmap"' not in html:
        if project_web is not None:
            diagnostics.append({"severity": "warning", "message": "Projekt-index.html enthält keine Importmap; Keim-Runtime-Artefakte wurden trotzdem erzeugt"})
        else:
            diagnostics.append({"severity": "error", "message": "Importmap fehlt in index.html"})
    if project_web is not None:
        diagnostics.append({"severity": "info", "message": f"Projekt-Webansicht übernommen: {project_web}"})
    for rel in ("index.html", "app.js"):
        p = out / rel
        if p.exists():
            content = p.read_text(encoding="utf-8", errors="ignore")
            if "eval(" in content or "Function(" in content or 'Function("' in content:
                diagnostics.append({"severity": "error", "message": f"Unsichere Web-Fachlogik in {rel}: eval/Function ist verboten"})
    if manifest.mode == "pwa" and not (out / "service-worker.js").exists():
        diagnostics.append({"severity": "warning", "message": "PWA-Modus ohne Service Worker"})
    if not manifest.dependencies:
        diagnostics.append({"severity": "info", "message": "Keine externen npm-Abhängigkeiten deklariert"})
    return diagnostics


def render_index(manifest: WebAppManifest, importmap: dict[str, Any], *, production: bool) -> str:
    prod = "true" if production else "false"
    return f'''<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{html_escape(manifest.title)}</title>
  <link rel="stylesheet" href="./assets/style.css">
  <link rel="manifest" href="./manifest.webmanifest">
  <script type="importmap">
{json.dumps(importmap, ensure_ascii=False, indent=2)}
  </script>
</head>
<body>
  <main id="app" data-keim-app="{html_escape(manifest.name)}">
    <noscript>Keim Web benötigt JavaScript oder eine WASM-Hostumgebung.</noscript>
  </main>
  <script type="module">
    import {{ boot }} from "@keim/app";
    boot({{ root: document.getElementById("app"), production: {prod} }});
  </script>
</body>
</html>
'''


def render_runtime_js(manifest: WebAppManifest) -> str:
    return '''// Keim Web Runtime v7.8.5
export class KeimRuntime {
  constructor(options = {}) {
    this.root = options.root || document.body;
    this.state = Object.create(null);
    this.listeners = new Map();
    this.events = [];
  }
  set(name, value) {
    this.state[name] = value;
    this.emit("state", { name, value });
    return value;
  }
  get(name) {
    return this.state[name];
  }
  on(type, fn) {
    const list = this.listeners.get(type) || [];
    list.push(fn);
    this.listeners.set(type, list);
    return () => this.listeners.set(type, (this.listeners.get(type) || []).filter(x => x !== fn));
  }
  emit(type, payload) {
    const event = { type, payload, time: Date.now() };
    this.events.push(event);
    for (const fn of this.listeners.get(type) || []) fn(payload, event);
  }
  dispatch(action, payload = {}) {
    this.emit("action", { action, payload });
  }
  mount(render) {
    const update = () => { this.root.innerHTML = render(this.state, this); this.bindActions(); };
    this.on("state", update);
    this.on("action", update);
    update();
  }
  bindActions() {
    this.root.querySelectorAll("[data-keim-action]").forEach(node => {
      if (node.__keimBound) return;
      node.__keimBound = true;
      node.addEventListener("click", () => this.dispatch(node.dataset.keimAction, { value: node.dataset.keimValue }));
    });
  }
}
export function html(strings, ...values) {
  let out = "";
  for (let i = 0; i < strings.length; i++) out += strings[i] + (values[i] ?? "");
  return out;
}
export async function loadAdapter(name, spec) {
  if (spec?.module) return import(spec.module);
  return {};
}
'''


def render_app_js(manifest: WebAppManifest) -> str:
    deps = "\n".join(f'// external import available: {d.import_name} -> {d.url()}' for d in manifest.dependencies)
    return f'''// Generated Keim Web App v7.8.5
import {{ KeimRuntime, html }} from "@keim/runtime";
import {{ adapters }} from "@keim/adapters";
{deps}

export function boot(options = {{}}) {{
  const rt = new KeimRuntime(options);
  rt.set("counter", 0);
  rt.set("status", "bereit");
  rt.on("action", (event) => {{
    if (event.action === "inc") rt.set("counter", (rt.get("counter") || 0) + 1);
    if (event.action === "reset") rt.set("counter", 0);
  }});
  rt.mount((state) => html`
    <section class="keim-shell">
      <h1>{js_escape(manifest.title)}</h1>
      <p>Keim Web/Ecosystem v7.8.5: Projekt-Webansicht, DOM, Importmaps, Adapter, PWA-Artefakte.</p>
      <div class="card">
        <strong>Zähler:</strong> ${{state.counter ?? 0}}
      </div>
      <button data-keim-action="inc">Erhöhen</button>
      <button data-keim-action="reset">Zurücksetzen</button>
      <details>
        <summary>JS-Adapter</summary>
        <pre>${{JSON.stringify(Object.keys(adapters), null, 2)}}</pre>
      </details>
    </section>
  `);
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("./service-worker.js").catch(() => {{}});
  return rt;
}}
'''


def render_adapters_js(manifest: WebAppManifest) -> str:
    payload = {a.alias: a.as_dict() for a in manifest.adapters}
    return f'''// Keim JS Adapter Registry v7.8.5
export const adapters = {json.dumps(payload, ensure_ascii=False, indent=2)};

export function callAdapter(alias, name, ...args) {{
  const adapter = adapters[alias];
  if (!adapter) throw new Error("Keim adapter not found: " + alias);
  const target = globalThis[adapter.module] || globalThis[alias];
  if (!target || typeof target[name] !== "function") {{
    throw new Error("Keim adapter function not found: " + alias + "." + name);
  }}
  return target[name](...args);
}}

export function hasPermission(alias, permission) {{
  return Boolean(adapters[alias]?.permissions?.includes(permission));
}}
'''


def render_pwa_manifest(manifest: WebAppManifest) -> str:
    return json.dumps({
        "name": manifest.title,
        "short_name": manifest.name[:12],
        "start_url": ".",
        "display": "standalone",
        "background_color": "#0f172a",
        "theme_color": "#111827",
        "icons": [],
    }, ensure_ascii=False, indent=2)


def render_service_worker(manifest: WebAppManifest) -> str:
    cache = f"keim-web-{manifest.name}-{manifest.version}"
    return f'''const CACHE = "{js_escape(cache)}";
const ASSETS = ["./", "./index.html", "./app.js", "./keim-web-runtime.js", "./assets/style.css"];
self.addEventListener("install", event => {{
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ASSETS)).then(() => self.skipWaiting()));
}});
self.addEventListener("activate", event => {{
  event.waitUntil(self.clients.claim());
}});
self.addEventListener("fetch", event => {{
  event.respondWith(caches.match(event.request).then(hit => hit || fetch(event.request)));
}});
'''


def render_deploy_readme(manifest: WebAppManifest, *, project_web: Path | None = None, overlay_files: list[str] | None = None) -> str:
    overlay_files = overlay_files or []
    overlay_note = "nein"
    if project_web is not None:
        overlay_note = f"ja, aus {project_web} ({len(overlay_files)} Dateien)"
    return f'''Keim Web Build v7.8.5

App: {manifest.name}
Version: {manifest.version}
Modus: {manifest.mode}
Projekt-Webansicht übernommen: {overlay_note}

Start lokal:
  python -m http.server 8080 -d <dieses-verzeichnis>

Enterprise-Hinweis:
  Wenn <projekt>/web/index.html existiert, übernimmt Keim diese Projekt-Webansicht
  und ergänzt Runtime-, Lock-, PWA- und Adapter-Artefakte.
  Die Importmap kann externe npm/CDN-Module referenzieren.
  Für Offline-/air-gapped Deployments müssen diese Module in vendor/ gespiegelt
  und die provider-Einstellung auf local gesetzt werden.
'''


def create_adapter(out: Path, *, alias: str, module: str, permission: list[str] | None = None) -> dict[str, Any]:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    spec = JsAdapter(alias=alias, module=module, permissions=set(permission or []))
    out.write_text(json.dumps(spec.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "adapter": spec.as_dict(), "path": str(out)}


def serve_web(out: Path, *, port: int = 8787) -> None:
    directory = Path(out).resolve()
    if not directory.exists():
        raise WebEcosystemError(f"Web-Ausgabeverzeichnis nicht gefunden: {directory}")

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(directory), **kwargs)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"[Keim Web] http://127.0.0.1:{port}/  ({directory})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Keim Web] Server beendet")


def html_escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def js_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def default_css() -> str:
    return '''body{margin:0;font-family:system-ui,-apple-system,Segoe UI,sans-serif;background:#0f172a;color:#e5e7eb}
.keim-shell{max-width:840px;margin:4rem auto;padding:2rem}
.card{background:#111827;border:1px solid #374151;border-radius:1rem;padding:1rem;margin:1rem 0}
button{border:0;border-radius:.75rem;padding:.7rem 1rem;margin-right:.5rem;background:#38bdf8;color:#082f49;font-weight:700}
pre{white-space:pre-wrap;background:#020617;padding:1rem;border-radius:.75rem}
'''


def training_readme(name: str) -> str:
    return f'''# {name}

Dieses Projekt demonstriert Keim v7.8.5 als Web-/Ökosystem-Schicht.

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
'''


def web_status() -> dict[str, Any]:
    return {
        "ok": True,
        "version": "7.8.5",
        "capabilities": [
            "web-project-scaffold",
            "importmap-npm-bridge",
            "js-adapter-registry",
            "dom-event-runtime",
            "pwa-artifacts",
            "web-lockfile",
            "project-web-overlay",
            "strict-no-eval-web-validation",
            "local-web-server",
            "offline-vendor-policy",
        ],
    }
