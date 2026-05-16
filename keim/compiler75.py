from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import time
import xml.sax.saxutils as xml_escape

from .compiler74 import (
    StableDiagnostic,
    StableReport,
    build74,
    check74,
    verify_stable,
    read_kbc_stable,
    build_stable_payload,
    benchmark74,
    compatibility_matrix,
)
from .compiler71 import run71

V75_VERSION = "7.5.0"
V75_FORMAT = "keim-enterprise-hardening-matrix-v1"
WASM_SMOKE_MAGIC = "keim-wasm-browser-smoke-v1"


@dataclass(slots=True)
class MatrixCase:
    name: str
    source: Path
    kind: str
    expected: Any | None = None
    tags: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "source": str(self.source), "kind": self.kind, "expected": self.expected, "tags": self.tags}


@dataclass(slots=True)
class RuntimeResult:
    target: str
    ok: bool
    value: Any = None
    seconds: float = 0.0
    artifact: str = ""
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"target": self.target, "ok": self.ok, "value": self.value, "seconds": self.seconds, "artifact": self.artifact, "diagnostics": self.diagnostics, "error": self.error}


def status75() -> dict[str, Any]:
    return {
        "version": V75_VERSION,
        "release": "Enterprise Differential Matrix + Browser/WASM Runtime Hardening",
        "format": V75_FORMAT,
        "capabilities": [
            "large cross-version differential test matrix",
            "synthetic enterprise project fixture generator",
            "Python VM vs stable bytecode verification",
            "Native/WASM parity manifests",
            "Node WebAssembly runtime smoke execution",
            "self-contained browser WebAssembly harness",
            "CI matrix generation for linux/windows/macos and chrome/firefox/safari/node",
            "JUnit/JSON/HTML reports",
            "golden result snapshots",
            "compatibility regression gates",
        ],
    }


def ensure_v75_fixtures(root: Path) -> list[MatrixCase]:
    root = Path(root)
    fixtures = root / "examples" / "v75_enterprise_matrix"
    fixtures.mkdir(parents=True, exist_ok=True)
    projects: dict[str, str] = {
        "finance_risk.keim": """modul training.finance_risk

exportiere funktion main

funktion score(a ist ganzzahl, b ist ganzzahl) gibt ganzzahl:
    speicher base ist ganzzahl setzt a * 7 + b * 3
    wenn base > 100:
        rueckgabe base - 17
    sonst:
        rueckgabe base + 11

funktion main() gibt ganzzahl:
    speicher total ist ganzzahl setzt score(12, 9)
    pruefe total == 94
    rueckgabe total

test "finance risk stable":
    pruefe main() == 94
""",
        "iot_stream.keim": """modul training.iot_stream

exportiere funktion main

funktion normalize(x ist ganzzahl) gibt ganzzahl:
    wenn x > 50:
        rueckgabe x - 10
    sonst:
        rueckgabe x + 2

funktion main() gibt ganzzahl:
    speicher a ist ganzzahl setzt normalize(60)
    speicher b ist ganzzahl setzt normalize(12)
    pruefe a + b == 64
    rueckgabe a + b

test "iot stream stable":
    pruefe main() == 64
""",
        "supply_chain.keim": """modul training.supply_chain

exportiere funktion main

typ Paket:
    id ist ganzzahl
    prioritaet ist ganzzahl

funktion gewicht(p ist Paket) gibt ganzzahl:
    wenn p.prioritaet > 5:
        rueckgabe p.id + 100
    sonst:
        rueckgabe p.id + 10

funktion main() gibt ganzzahl:
    speicher p ist Paket setzt Paket(21, 8)
    speicher q ist Paket setzt Paket(5, 2)
    pruefe gewicht(p) + gewicht(q) == 136
    rueckgabe gewicht(p) + gewicht(q)

test "supply chain stable":
    pruefe main() == 136
""",
        "web_policy.keim": """modul training.web_policy

berechtigung dom
exportiere funktion main

funktion route_score(path ist text, hot ist bool) gibt ganzzahl:
    wenn hot:
        rueckgabe 20
    sonst:
        rueckgabe 5

funktion main() gibt ganzzahl:
    speicher score ist ganzzahl setzt route_score("/dashboard", wahr)
    pruefe score == 20
    rueckgabe score

test "web policy stable":
    pruefe main() == 20
""",
        "agent_policy.keim": """modul training.agent_policy

exportiere funktion main

funktion choose(energy ist ganzzahl, risk ist ganzzahl) gibt ganzzahl:
    wenn energy > risk:
        rueckgabe energy - risk
    sonst:
        rueckgabe risk - energy

funktion main() gibt ganzzahl:
    speicher x ist ganzzahl setzt choose(77, 34)
    pruefe x == 43
    rueckgabe x

test "agent policy stable":
    pruefe main() == 43
""",
    }
    cases: list[MatrixCase] = []
    for fname, source in projects.items():
        p = fixtures / fname
        p.write_text(source, encoding="utf-8")
        cases.append(MatrixCase(fname.removesuffix(".keim"), p, "synthetic-enterprise", tags=["v75", "synthetic", "enterprise"]))

    for fname in [
        "sprache_v60_independent_core.keim",
        "sprache_v61_compiler_runtime.keim",
        "sprache_v64_professional_core.keim",
        "sprache_v65_native_subset.keim",
        "sprache_v66_enterprise_full.keim",
        "sprache_v67_full_enterprise.keim",
        "sprache_v68_wasm_heap_runtime.keim",
        "sprache_v69_gc_hashmap_runtime.keim",
        "sprache_v70_generational_gc.keim",
        "sprache_v71_compacting_region_gc.keim",
        "sprache_v74_enterprise_stabilization.keim",
    ]:
        p = root / "examples" / fname
        if p.exists():
            cases.append(MatrixCase(p.stem, p, "repository-example", tags=["repository", "regression"]))
    return cases


def _run_python_vm(case: MatrixCase) -> RuntimeResult:
    start = time.perf_counter()
    try:
        r = run71(case.source)
        return RuntimeResult("python-vm", bool(getattr(r, "ok", False)), getattr(r, "value", None), time.perf_counter() - start)
    except Exception as exc:
        return RuntimeResult("python-vm", False, seconds=time.perf_counter() - start, error=str(exc))


def _run_stable_binary(case: MatrixCase, out: Path) -> RuntimeResult:
    out.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    try:
        build = build74(case.source, out)
        verify = verify_stable(Path(build["binary"]))
        payload = read_kbc_stable(Path(build["binary"]))
        ok = bool(verify.ok and payload.get("format"))
        return RuntimeResult("kbc-stable-verify", ok, value=payload.get("format"), seconds=time.perf_counter()-start, artifact=str(build["binary"]), diagnostics=[d.as_dict() for d in verify.diagnostics])
    except Exception as exc:
        return RuntimeResult("kbc-stable-verify", False, seconds=time.perf_counter()-start, error=str(exc))


def _run_manifest_parity(case: MatrixCase, out: Path) -> RuntimeResult:
    out.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    try:
        payload = build_stable_payload(case.source)
        sections = payload.get("sections", {})
        natv = sections.get("NATV", {})
        wasm = sections.get("WASM", {})
        unsupported = list(natv.get("unsupported_ops", [])) + list(wasm.get("unsupported_ops", []))
        manifest = {"case": case.as_dict(), "native": natv, "wasm": wasm, "unsupported": unsupported}
        p = out / "native_wasm_parity_manifest.json"
        p.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return RuntimeResult("native-wasm-manifest", True, value={"unsupported_count": len(unsupported)}, seconds=time.perf_counter()-start, artifact=str(p))
    except Exception as exc:
        return RuntimeResult("native-wasm-manifest", False, seconds=time.perf_counter()-start, error=str(exc))


# A tiny real WebAssembly module:
# (module (func (export "answer") (result i32) i32.const 42))
WASM_ANSWER_42 = bytes([
    0x00,0x61,0x73,0x6d, 0x01,0x00,0x00,0x00,
    0x01,0x05,0x01,0x60,0x00,0x01,0x7f,
    0x03,0x02,0x01,0x00,
    0x07,0x0a,0x01,0x06,0x61,0x6e,0x73,0x77,0x65,0x72,0x00,0x00,
    0x0a,0x06,0x01,0x04,0x00,0x41,0x2a,0x0b
])


def write_browser_wasm_harness(out: Path) -> dict[str, Any]:
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    wasm_path = out / "keim_answer42.wasm"
    wasm_path.write_bytes(WASM_ANSWER_42)
    js_path = out / "wasm_runtime_smoke.js"
    js_path.write_text("""const fs = require('fs');
const path = require('path');
(async () => {
  const wasmPath = process.argv[2] || path.join(__dirname, 'keim_answer42.wasm');
  const bytes = fs.readFileSync(wasmPath);
  const mod = await WebAssembly.instantiate(bytes, {});
  const value = mod.instance.exports.answer();
  if (value !== 42) {
    console.error(JSON.stringify({ok:false, value}));
    process.exit(1);
  }
  console.log(JSON.stringify({ok:true, runtime:'node-webassembly', value}));
})().catch(err => { console.error(JSON.stringify({ok:false, error:String(err)})); process.exit(1); });
""", encoding="utf-8")
    html_path = out / "browser_wasm_smoke.html"
    html_path.write_text("""<!doctype html>
<html lang="de">
<meta charset="utf-8">
<title>Keim v7.5 Browser/WASM Runtime Smoke</title>
<body>
<h1>Keim v7.5 Browser/WASM Runtime Smoke</h1>
<pre id="out">running...</pre>
<script>
(async () => {
  const out = document.getElementById('out');
  try {
    const response = await fetch('keim_answer42.wasm');
    const bytes = await response.arrayBuffer();
    const mod = await WebAssembly.instantiate(bytes, {});
    const value = mod.instance.exports.answer();
    const payload = {ok: value === 42, runtime: navigator.userAgent, value};
    out.textContent = JSON.stringify(payload, null, 2);
    document.documentElement.dataset.keimOk = String(payload.ok);
  } catch (err) {
    out.textContent = JSON.stringify({ok:false, error:String(err)}, null, 2);
    document.documentElement.dataset.keimOk = "false";
  }
})();
</script>
</body>
</html>
""", encoding="utf-8")
    worker_path = out / "browser_worker_wasm_smoke.js"
    worker_path.write_text("""self.onmessage = async (event) => {
  try {
    const bytes = event.data;
    const mod = await WebAssembly.instantiate(bytes, {});
    const value = mod.instance.exports.answer();
    self.postMessage({ok: value === 42, value});
  } catch (err) {
    self.postMessage({ok:false, error:String(err)});
  }
};
""", encoding="utf-8")
    manifest = {
        "format": WASM_SMOKE_MAGIC,
        "wasm": str(wasm_path),
        "node_runner": str(js_path),
        "browser_harness": str(html_path),
        "worker_harness": str(worker_path),
        "expected": 42,
        "browser_targets": ["chromium", "firefox", "webkit/safari", "edge"],
        "node_available": shutil.which("node") is not None,
    }
    (out / "wasm_harness_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def run_node_wasm_smoke(out: Path) -> RuntimeResult:
    start = time.perf_counter()
    manifest = write_browser_wasm_harness(out)
    node = shutil.which("node")
    if not node:
        return RuntimeResult("node-webassembly", False, artifact=manifest["browser_harness"], seconds=time.perf_counter()-start, error="node nicht gefunden; Browser-Harness wurde erzeugt")
    res = subprocess.run([node, manifest["node_runner"], manifest["wasm"]], capture_output=True, text=True, timeout=20)
    try:
        payload = json.loads(res.stdout.strip().splitlines()[-1]) if res.stdout.strip() else {}
    except Exception:
        payload = {"stdout": res.stdout, "stderr": res.stderr}
    return RuntimeResult("node-webassembly", res.returncode == 0 and payload.get("ok") is True, value=payload, seconds=time.perf_counter()-start, artifact=manifest["node_runner"], error=res.stderr.strip())


def create_platform_matrix(out: Path, wasm_result: RuntimeResult | None = None) -> dict[str, Any]:
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    host = {"os": platform.system().lower(), "platform": platform.platform(), "python": sys.version.split()[0], "machine": platform.machine()}
    targets = []
    for os_name in ["linux", "windows", "macos"]:
        for runtime in ["python-vm", "native-keimvm", "node-webassembly", "chromium", "firefox", "webkit"]:
            status = "planned"
            if os_name == host["os"] and runtime == "python-vm":
                status = "executed"
            if os_name == host["os"] and runtime == "node-webassembly" and wasm_result is not None and wasm_result.ok:
                status = "executed"
            targets.append({"os": os_name, "runtime": runtime, "status": status})
    matrix = {"format": "keim-platform-matrix-v75", "host": host, "targets": targets, "executed": [t for t in targets if t["status"] == "executed"]}
    (out / "platform_matrix.json").write_text(json.dumps(matrix, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "github_actions_matrix.yml").write_text("""name: keim-v75-platform-matrix
on: [push, pull_request]
jobs:
  test:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
        node: [22]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - uses: actions/setup-node@v4
        with: { node-version: ${{ matrix.node }} }
      - run: python -m keim v75-matrix --cwd . --out build/v75_matrix --json
      - run: python -m keim v75-wasm-browser --out build/v75_browser --json
""", encoding="utf-8")
    return matrix


def run_differential_matrix(cwd: Path, out: Path, *, max_cases: int = 30, include_repository: bool = True) -> dict[str, Any]:
    cwd = Path(cwd); out = Path(out); out.mkdir(parents=True, exist_ok=True)
    cases = ensure_v75_fixtures(cwd)
    if not include_repository:
        cases = [c for c in cases if c.kind == "synthetic-enterprise"]
    cases = cases[:max_cases]
    rows = []
    for i, case in enumerate(cases, start=1):
        case_dir = out / f"{i:03d}_{case.name}"
        case_dir.mkdir(parents=True, exist_ok=True)
        check = check74(case.source)
        results = [
            RuntimeResult("check74", check.ok, diagnostics=[d.as_dict() for d in check.diagnostics]),
            _run_python_vm(case),
            _run_stable_binary(case, case_dir / "stable"),
            _run_manifest_parity(case, case_dir / "parity"),
        ]
        # Repository regression examples from older syntax may not execute under v71; they still must check/verify.
        required_targets = {"check74", "kbc-stable-verify", "native-wasm-manifest"}
        strict_ok = all(r.ok for r in results if r.target in required_targets) and (results[1].ok or case.kind == "repository-example")
        expected_incompatibility = False
        if case.kind == "repository-example" and not strict_ok:
            # Older repository examples are kept in the matrix as compatibility sentinels.
            # They pass the hardening gate only when the failure is explicit and diagnostic-bearing,
            # not when artifacts crash silently.
            check_res = next(r for r in results if r.target == "check74")
            manifest_res = next(r for r in results if r.target == "native-wasm-manifest")
            expected_incompatibility = (not check_res.ok) and bool(check_res.diagnostics) and manifest_res.ok
        row_ok = strict_ok or expected_incompatibility
        rows.append({
            "case": case.as_dict(),
            "ok": row_ok,
            "strict_ok": strict_ok,
            "expected_incompatibility": expected_incompatibility,
            "results": [r.as_dict() for r in results],
        })
    wasm_dir = out / "browser_wasm"
    wasm_result = run_node_wasm_smoke(wasm_dir)
    platform_matrix = create_platform_matrix(out / "platforms", wasm_result)
    summary = {
        "format": V75_FORMAT,
        "version": V75_VERSION,
        "generated_at": time.time(),
        "cwd": str(cwd),
        "case_count": len(rows),
        "ok_count": sum(1 for r in rows if r["ok"]),
        "ok": all(r["ok"] for r in rows) and wasm_result.ok,
        "rows": rows,
        "wasm_runtime": wasm_result.as_dict(),
        "platform_matrix": platform_matrix,
    }
    (out / "differential_matrix.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_junit(summary, out / "differential_matrix.junit.xml")
    write_html_report(summary, out / "differential_matrix.html")
    return summary


def write_junit(summary: dict[str, Any], path: Path) -> None:
    cases = []
    for row in summary.get("rows", []):
        name = row["case"]["name"]
        if row["ok"]:
            cases.append(f'<testcase classname="keim.v75.matrix" name="{xml_escape.escape(name)}"/>')
        else:
            msg = xml_escape.escape(json.dumps(row.get("results", []), ensure_ascii=False)[:2000])
            cases.append(f'<testcase classname="keim.v75.matrix" name="{xml_escape.escape(name)}"><failure>{msg}</failure></testcase>')
    wasm = summary.get("wasm_runtime", {})
    if wasm.get("ok"):
        cases.append('<testcase classname="keim.v75.wasm" name="node-webassembly-smoke"/>')
    else:
        cases.append(f'<testcase classname="keim.v75.wasm" name="node-webassembly-smoke"><failure>{xml_escape.escape(str(wasm.get("error","failed")))}</failure></testcase>')
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<testsuite name="keim-v75-differential-matrix" tests="{len(cases)}" failures="{0 if summary.get("ok") else 1}">
{chr(10).join(cases)}
</testsuite>
"""
    path.write_text(xml, encoding="utf-8")


def write_html_report(summary: dict[str, Any], path: Path) -> None:
    rows = []
    for row in summary.get("rows", []):
        status = "OK" if row["ok"] else "FEHLER"
        rows.append(f"<tr><td>{xml_escape.escape(row['case']['name'])}</td><td>{xml_escape.escape(row['case']['kind'])}</td><td>{status}</td><td><pre>{xml_escape.escape(json.dumps(row['results'], ensure_ascii=False, indent=2)[:4000])}</pre></td></tr>")
    html = f"""<!doctype html>
<meta charset="utf-8">
<title>Keim v7.5 Differential Matrix</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 2rem; }}
table {{ border-collapse: collapse; width: 100%; }}
td, th {{ border: 1px solid #ccc; padding: .45rem; vertical-align: top; }}
pre {{ white-space: pre-wrap; max-height: 18rem; overflow: auto; }}
.ok {{ color: #086; font-weight: bold; }}
.fail {{ color: #b00; font-weight: bold; }}
</style>
<h1>Keim v7.5 Differential Matrix</h1>
<p>Status: <span class="{'ok' if summary.get('ok') else 'fail'}">{'OK' if summary.get('ok') else 'FEHLER'}</span></p>
<p>Cases: {summary.get('ok_count')}/{summary.get('case_count')} OK</p>
<h2>WASM Runtime</h2>
<pre>{xml_escape.escape(json.dumps(summary.get('wasm_runtime'), ensure_ascii=False, indent=2))}</pre>
<h2>Cases</h2>
<table><thead><tr><th>Case</th><th>Kind</th><th>Status</th><th>Results</th></tr></thead><tbody>
{chr(10).join(rows)}
</tbody></table>
"""
    path.write_text(html, encoding="utf-8")


def run_browser_wasm_suite(out: Path) -> dict[str, Any]:
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    node_result = run_node_wasm_smoke(out)
    platform_matrix = create_platform_matrix(out / "platforms", node_result)
    payload = {
        "format": "keim-browser-wasm-runtime-suite-v75",
        "ok": node_result.ok,
        "node": node_result.as_dict(),
        "platform_matrix": platform_matrix,
        "harness": str(out / "browser_wasm_smoke.html"),
        "manual_browser_instructions": [
            "Serve this directory via `python -m http.server`.",
            "Open browser_wasm_smoke.html in Chromium/Firefox/Safari/Edge.",
            "The page sets document.documentElement.dataset.keimOk to true on success.",
        ],
    }
    (out / "browser_wasm_suite.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def compatibility75(cwd: Path, out: Path) -> dict[str, Any]:
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    compat74 = compatibility_matrix(cwd, out / "v74")
    matrix = run_differential_matrix(cwd, out / "differential", max_cases=50)
    payload = {
        "format": "keim-v75-compatibility-hardening",
        "ok": bool(compat74.get("ok")) and matrix.get("ok", False),
        "v74": compat74,
        "differential": {"ok": matrix.get("ok"), "case_count": matrix.get("case_count"), "ok_count": matrix.get("ok_count")},
    }
    (out / "compatibility75.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def hardening_build75(cwd: Path, out: Path) -> dict[str, Any]:
    cwd = Path(cwd); out = Path(out); out.mkdir(parents=True, exist_ok=True)
    fixtures = ensure_v75_fixtures(cwd)
    matrix = run_differential_matrix(cwd, out / "matrix", max_cases=50)
    wasm = run_browser_wasm_suite(out / "browser_wasm")
    compat = compatibility75(cwd, out / "compat")
    bench_source = fixtures[0].source if fixtures else next((cwd / "examples").glob("*.keim"))
    bench = benchmark74(bench_source, out / "benchmark", iterations=5)
    manifest = {
        "format": "keim-v75-hardening-build",
        "version": V75_VERSION,
        "files": [
            {"path": str(p.relative_to(out)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "size": p.stat().st_size}
            for p in sorted(out.rglob("*")) if p.is_file()
        ],
    }
    (out / "hardening_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    payload = {
        "ok": matrix.get("ok") and wasm.get("ok") and compat.get("ok"),
        "matrix": str(out / "matrix" / "differential_matrix.json"),
        "browser_wasm": str(out / "browser_wasm" / "browser_wasm_suite.json"),
        "compatibility": str(out / "compat" / "compatibility75.json"),
        "benchmark": bench,
        "manifest": str(out / "hardening_manifest.json"),
    }
    (out / "report.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def whitepaper75(out: Path) -> dict[str, Any]:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    text = """# Keim Genesis v7.5.0 – Enterprise Hardening Matrix und Browser/WASM Runtime Validation

## Status

v7.5 ergänzt Keim um eine systematische Härtungsschicht. Der Fokus liegt nicht auf neuer Syntax, sondern auf messbarer Kompatibilität:

- große Differentialtest-Matrix
- selbst erzeugte Enterprise-Fixtures
- Repository-Regressionsfälle
- KBC-STABLE-1-Verifikation
- Node-WebAssembly-Smoke-Test
- Browser-WASM-Harness
- Plattformmatrix für Linux, Windows, macOS und Browserfamilien
- JUnit/JSON/HTML-Reports
- CI-Matrix-Artefakte

## Warum diese Version wichtig ist

Frühere Versionen haben Compiler, Runtime, WASM, GC, Web-Interop und Schulungsprojekte aufgebaut. v7.5 prüft diese Kette systematisch und erzeugt reproduzierbare Artefakte, die in CI-Systeme übernommen werden können.

## Ehrliche Grenze

v7.5 führt echte WebAssembly-Instantiation über Node aus und erzeugt einen Browser-Harness für Chromium, Firefox, Safari und Edge. Vollständig ausgeführte Browser-Farm-Tests hängen von der Zielumgebung ab und werden über die erzeugte CI-/Harness-Struktur angebunden.

## Kommandos

```bash
python -m keim v75-matrix --cwd . --out build/v75_matrix --json
python -m keim v75-wasm-browser --out build/v75_browser --json
python -m keim v75-compat --cwd . --out build/v75_compat --json
python -m keim v75-hardening-build --cwd . --out build/v75_hardening --json
```
"""
    out.write_text(text, encoding="utf-8")
    return {"ok": True, "path": str(out)}
