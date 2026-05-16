
from __future__ import annotations

from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from urllib.request import urlopen, Request
from urllib.error import URLError


HTML_TEMPLATE = r"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
body{{font-family:system-ui,-apple-system,Segoe UI,sans-serif;background:#10131a;color:#eef2ff;margin:0}}
header{{padding:24px 28px;background:#171b25;border-bottom:1px solid #2b3142}}
main{{padding:24px;display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}}
.card{{background:#171b25;border:1px solid #2b3142;border-radius:18px;padding:18px;box-shadow:0 12px 30px #0005}}
h1{{margin:0;font-size:24px}} h2{{margin:0 0 12px;font-size:18px}}
pre{{white-space:pre-wrap;word-break:break-word;background:#0b0d12;border-radius:12px;padding:12px}}
button,input{{border-radius:12px;border:1px solid #384055;background:#0f1320;color:#eef2ff;padding:10px 12px;margin:4px}}
button{{cursor:pointer;background:#24304a}} .ok{{color:#76f7b1}} .bad{{color:#ff8a8a}}
</style>
</head>
<body>
<header><h1>{title}</h1><p>Keim Web-GUI · API: <code>{api}</code></p></header>
<main>
<section class="card"><h2>Status</h2><pre id="health">lädt…</pre></section>
<section class="card"><h2>Snapshot</h2><pre id="snapshot">lädt…</pre></section>
<section class="card"><h2>Metriken</h2><pre id="metrics">lädt…</pre></section>
<section class="card"><h2>Steuerung</h2>
<button onclick="control({{running:false}})">Stop</button>
<button onclick="control({{running:true}})">Start</button>
<br>
<label>Wind <input id="wind" value="0.05"></label>
<button onclick="control({{wind_signal:Number(document.getElementById('wind').value)}})">Wind setzen</button>
<button onclick="step()">25 Schritte</button>
<pre id="control">bereit</pre>
</section>
</main>
<script>
const api="{api}";
async function get(path,id){{try{{const r=await fetch(api+path); const j=await r.json(); document.getElementById(id).textContent=JSON.stringify(j,null,2)}}catch(e){{document.getElementById(id).textContent=String(e)}}}}
async function control(body){{const r=await fetch(api+"/control",{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify(body)}}); document.getElementById("control").textContent=JSON.stringify(await r.json(),null,2); refresh();}}
async function step(){{const r=await fetch(api+"/step",{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{rounds:25}})}}); document.getElementById("control").textContent=JSON.stringify(await r.json(),null,2); refresh();}}
function refresh(){{get("/health","health");get("/snapshot","snapshot");get("/metrics","metrics");}}
refresh(); setInterval(refresh,1000);
</script>
</body>
</html>"""


@dataclass(slots=True)
class WebGuiServer:
    name: str
    port: int
    title: str
    api_base: str
    server: ThreadingHTTPServer
    thread: threading.Thread

    def shutdown(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def start_web_gui(name: str, port: int, title: str, api_base: str, debug_base: str | None = None) -> WebGuiServer:
    html = HTML_TEMPLATE.format(title=title, api=api_base.rstrip("/"))
    if debug_base:
        html = html.replace("</main>", f"<section class='card'><h2>DebugBus</h2><pre id='debug'>lade…</pre></section></main>").replace(
            "refresh(); setInterval(refresh,1000);",
            "async function debugRefresh(){try{const r=await fetch('" + debug_base.rstrip("/") + "/debug/state');document.getElementById('debug').textContent=JSON.stringify(await r.json(),null,2)}catch(e){document.getElementById('debug').textContent=String(e)}}\nrefresh(); debugRefresh(); setInterval(()=>{refresh();debugRefresh()},1000);"
        )

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: object) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802
            if self.path in {"/", "/index.html"}:
                payload = html.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            if self.path == "/health":
                payload = json.dumps({"ok": True, "gui": name, "api": api_base, "debug": debug_base}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            self.send_response(404)
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", int(port)), Handler)
    thread = threading.Thread(target=server.serve_forever, name=f"keim-webgui-{name}", daemon=True)
    thread.start()
    return WebGuiServer(name=name, port=port, title=title, api_base=api_base, server=server, thread=thread)
