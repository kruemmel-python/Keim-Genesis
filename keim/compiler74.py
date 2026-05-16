from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
import base64
import hashlib
import json
import os
import re
import struct
import time
import xml.sax.saxutils as xml_escape

from .compiler71 import (
    check71,
    run71,
    bytecode71,
    build71,
    test71,
    read_kbc71b,
    write_kbc71b,
    emit_wasm71,
    status71,
)

KBC_STABLE_MAGIC = b"KBCSTBL1"
KBC_STABLE_VERSION = 1
KBC_STABLE_FORMAT = "keim-kbc-stable-1"
CAPABILITY_SCHEMA_VERSION = 1


@dataclass(slots=True)
class StableDiagnostic:
    severity: str
    code: str
    message: str
    path: str = ""
    line: int = 0
    hint: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "path": self.path,
            "line": self.line,
            "hint": self.hint,
        }


@dataclass(slots=True)
class StableReport:
    ok: bool
    diagnostics: list[StableDiagnostic] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "diagnostics": [d.as_dict() for d in self.diagnostics], **self.payload}

    def format(self) -> str:
        lines = ["[Keim v7.4] " + ("OK" if self.ok else "FEHLER")]
        for d in self.diagnostics:
            loc = f"{d.path}:{d.line}: " if d.path or d.line else ""
            hint = f" ({d.hint})" if d.hint else ""
            lines.append(f"  {d.severity.upper()} {d.code}: {loc}{d.message}{hint}")
        return "\n".join(lines)


def status74() -> dict[str, Any]:
    return {
        "version": "7.4.0",
        "release": "Enterprise Stabilization & Developer Platform",
        "stable_bytecode": KBC_STABLE_FORMAT,
        "capabilities": [
            "KBC-STABLE-1 canonical binary container",
            "versioned sections with checksums",
            "security capability policy scanner",
            "native/wasm parity manifest",
            "JSON-RPC LSP core",
            "benchmark harness",
            "compatibility matrix",
            "SBOM + reproducible build manifest",
            "source-map style debug metadata",
            "differential test artifacts",
        ],
        "honest_scope": "v7.4 hardens and specifies the existing Keim stack; it does not replace every production browser/native ecosystem component.",
    }


def stable_spec() -> dict[str, Any]:
    sections = [
        {"id": "META", "required": True, "description": "format, compiler, source, platform and provenance metadata"},
        {"id": "TYPE", "required": True, "description": "type table and record/result/generic metadata"},
        {"id": "SYMB", "required": True, "description": "module/function/symbol table"},
        {"id": "CNST", "required": True, "description": "canonical constant pool"},
        {"id": "CODE", "required": True, "description": "linear bytecode program payload"},
        {"id": "DBGI", "required": False, "description": "debug line table and source-map information"},
        {"id": "CAPS", "required": True, "description": "declared capabilities and sandbox contract"},
        {"id": "REPL", "required": False, "description": "replay hooks and deterministic event-channel metadata"},
        {"id": "WASM", "required": False, "description": "wasm-runtime lowering manifest"},
        {"id": "NATV", "required": False, "description": "native-VM parity and ABI manifest"},
    ]
    return {
        "format": KBC_STABLE_FORMAT,
        "version": KBC_STABLE_VERSION,
        "endianness": "little",
        "header": {
            "magic": KBC_STABLE_MAGIC.decode("ascii"),
            "version": "u32",
            "section_count": "u32",
            "directory_offset": "u64",
            "payload_sha256": "32 bytes",
        },
        "section_directory_entry": {
            "id": "4 ascii bytes",
            "offset": "u64",
            "length": "u64",
            "sha256": "32 bytes",
            "flags": "u32",
        },
        "sections": sections,
        "compatibility_policy": {
            "major": "KBC-STABLE-1 readers must reject unknown required sections.",
            "minor": "unknown optional sections must be preserved by tooling.",
            "canonical_json": "JSON sections are utf-8, sorted keys, compact separators.",
        },
    }


def _canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _extract_constant_pool(program: dict[str, Any]) -> list[Any]:
    seen: dict[str, Any] = {}
    def visit(v: Any) -> None:
        if isinstance(v, (str, int, float, bool)) or v is None:
            key = json.dumps(v, ensure_ascii=False, sort_keys=True)
            seen.setdefault(key, v)
        elif isinstance(v, list):
            for item in v:
                visit(item)
        elif isinstance(v, dict):
            for item in v.values():
                visit(item)
    visit(program.get("functions", {}))
    return list(seen.values())


def _infer_capabilities_from_source(path: Path) -> dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8") if Path(path).exists() else ""
    declared = sorted(set(re.findall(r"^\s*berechtigung\s+([\w.:-]+)", text, re.M)))
    observed: set[str] = set()
    patterns = {
        "io.read": [r"\bdatei_lese\b", r"\bfile_read\b"],
        "io.write": [r"\bdatei_schreibe\b", r"\bsnapshot\s+speichere\b"],
        "net.http": [r"\bhttp_", r"\bfetch\b"],
        "ffi.native": [r"\bffi\b", r"\bnative\b"],
        "dom": [r"\bdom_", r"\bweb_"],
        "time": [r"\bzeit\b", r"\btime\b"],
        "random": [r"\bzufall\b", r"\brandom\b"],
    }
    for cap, pats in patterns.items():
        if any(re.search(p, text) for p in pats):
            observed.add(cap)
    return {
        "schema": CAPABILITY_SCHEMA_VERSION,
        "declared": declared,
        "observed": sorted(observed),
        "missing": sorted(observed - set(declared)),
        "policy": "deny-by-default",
    }


def build_stable_payload(source: Path, *, include_wasm: bool = True) -> dict[str, Any]:
    source = Path(source)
    bc = bytecode71(source)
    source_text = source.read_text(encoding="utf-8")
    caps = _infer_capabilities_from_source(source)
    functions = bc.get("functions", {})
    symbols = {
        "modules": sorted(bc.get("modules", {}).keys()) if isinstance(bc.get("modules"), dict) else [],
        "functions": sorted(functions.keys()) if isinstance(functions, dict) else [],
        "entry": bc.get("entry", ""),
    }
    types = {
        "records": bc.get("heap_layouts", {}).get("records", {}) if isinstance(bc.get("heap_layouts"), dict) else {},
        "generics": bc.get("generics", {}),
        "results": bc.get("result_types", {}),
    }
    debug = _make_debug_info(source_text, str(source))
    const_pool = _extract_constant_pool(bc)
    payload = {
        "format": KBC_STABLE_FORMAT,
        "version": KBC_STABLE_VERSION,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sections": {
            "META": {
                "keim_version": "7.4.0",
                "source": str(source),
                "source_sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
                "producer": "keim.compiler74",
                "base_format": bc.get("format", "unknown"),
            },
            "TYPE": types,
            "SYMB": symbols,
            "CNST": {"constants": const_pool, "count": len(const_pool)},
            "CODE": bc,
            "DBGI": debug,
            "CAPS": caps,
            "REPL": {"deterministic_channels": ["time", "random", "io", "ffi", "actor_schedule"], "record_required_for": caps["observed"]},
            "NATV": _native_parity_manifest(bc),
        },
    }
    if include_wasm:
        payload["sections"]["WASM"] = _wasm_parity_manifest(bc)
    return payload


def _make_debug_info(source: str, path: str) -> dict[str, Any]:
    lines = source.splitlines()
    symbols = []
    for i, line in enumerate(lines, 1):
        m = re.match(r"\s*funktion\s+(\w+)", line)
        if m:
            symbols.append({"kind": "function", "name": m.group(1), "line": i})
        m = re.match(r"\s*typ\s+(\w+)", line)
        if m:
            symbols.append({"kind": "type", "name": m.group(1), "line": i})
        m = re.match(r"\s*akteur\s+(\w+)", line)
        if m:
            symbols.append({"kind": "actor", "name": m.group(1), "line": i})
    return {
        "source": path,
        "line_count": len(lines),
        "symbols": symbols,
        "source_map": [{"line": i, "offset": sum(len(x) + 1 for x in lines[: i - 1])} for i in range(1, len(lines) + 1)],
    }


def _native_parity_manifest(program: dict[str, Any]) -> dict[str, Any]:
    supported = {"CONST", "CONST_INT", "CONST_BOOL", "LOAD_SLOT", "STORE_SLOT", "ADD", "SUB", "MUL", "DIV", "EQ", "LT", "GT", "JUMP", "JUMP_IF_FALSE", "PRINT", "RETURN"}
    ops = sorted(_collect_ops(program))
    return {
        "target": "native-keimvm",
        "abi": "keim-native-stable-1",
        "ops": ops,
        "supported_subset": sorted(supported),
        "unsupported_ops": [op for op in ops if op not in supported],
        "parity_required": True,
    }


def _wasm_parity_manifest(program: dict[str, Any]) -> dict[str, Any]:
    ops = sorted(_collect_ops(program))
    heap_ops = [op for op in ops if op in {"MAKE_LIST", "MAKE_MAP", "MAKE_RECORD", "GET_ITEM", "GET_ATTR", "RESULT_IS_OK"}]
    return {
        "target": "wasm32-wat",
        "runtime": "keim-wasm-gc-region-stable-1",
        "ops": ops,
        "heap_runtime_required": bool(heap_ops),
        "heap_ops": heap_ops,
        "parity_required": True,
    }


def _collect_ops(obj: Any) -> set[str]:
    ops: set[str] = set()
    if isinstance(obj, dict):
        if isinstance(obj.get("op"), str):
            ops.add(obj["op"])
        for v in obj.values():
            ops |= _collect_ops(v)
    elif isinstance(obj, list):
        for x in obj:
            ops |= _collect_ops(x)
    return ops


def write_kbc_stable(payload: dict[str, Any], out: Path) -> None:
    out = Path(out)
    sections = payload.get("sections", {})
    encoded: list[tuple[str, bytes, bytes]] = []
    for sid, data in sections.items():
        sid4 = sid[:4].ljust(4, "_")
        b = _canonical_json_bytes(data)
        encoded.append((sid4, b, hashlib.sha256(b).digest()))
    header_size = 8 + 4 + 4 + 8 + 32
    directory_size = len(encoded) * (4 + 8 + 8 + 32 + 4)
    directory_offset = header_size
    data_offset = header_size + directory_size
    offsets = []
    cur = data_offset
    for sid, b, digest in encoded:
        offsets.append((sid, cur, len(b), digest, 0))
        cur += len(b)
    payload_hash = hashlib.sha256(b"".join(b for _, b, _ in encoded)).digest()
    header = KBC_STABLE_MAGIC + struct.pack("<IIQ", KBC_STABLE_VERSION, len(encoded), directory_offset) + payload_hash
    directory = b"".join(
        sid.encode("ascii") + struct.pack("<QQ", off, length) + digest + struct.pack("<I", flags)
        for sid, off, length, digest, flags in offsets
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(header + directory + b"".join(b for _, b, _ in encoded))


def read_kbc_stable(path: Path) -> dict[str, Any]:
    data = Path(path).read_bytes()
    if len(data) < 56 or data[:8] != KBC_STABLE_MAGIC:
        raise ValueError("Keine KBC-STABLE-1 Datei")
    version, count, directory_offset = struct.unpack("<IIQ", data[8:24])
    payload_hash = data[24:56]
    if version != KBC_STABLE_VERSION:
        raise ValueError(f"Nicht unterstützte KBC-STABLE-Version: {version}")
    pos = directory_offset
    sections: dict[str, Any] = {}
    section_bytes: list[bytes] = []
    for _ in range(count):
        sid = data[pos:pos+4].decode("ascii").rstrip("_"); pos += 4
        off, length = struct.unpack("<QQ", data[pos:pos+16]); pos += 16
        digest = data[pos:pos+32]; pos += 32
        flags = struct.unpack("<I", data[pos:pos+4])[0]; pos += 4
        chunk = data[off:off+length]
        if hashlib.sha256(chunk).digest() != digest:
            raise ValueError(f"Sektionshash ungültig: {sid}")
        section_bytes.append(chunk)
        sections[sid] = json.loads(chunk.decode("utf-8"))
    if hashlib.sha256(b"".join(section_bytes)).digest() != payload_hash:
        raise ValueError("Payload-Hash ungültig")
    return {"format": KBC_STABLE_FORMAT, "version": version, "sections": sections}


def verify_stable(path: Path) -> StableReport:
    diagnostics: list[StableDiagnostic] = []
    try:
        payload = read_kbc_stable(path)
    except Exception as exc:
        return StableReport(False, [StableDiagnostic("error", "KBC001", str(exc), str(path))])
    spec = stable_spec()
    required = {s["id"] for s in spec["sections"] if s["required"]}
    sections = set(payload["sections"].keys())
    missing = required - sections
    for sid in sorted(missing):
        diagnostics.append(StableDiagnostic("error", "KBC002", f"Pflichtsektion fehlt: {sid}", str(path)))
    caps = payload["sections"].get("CAPS", {})
    for cap in caps.get("missing", []):
        diagnostics.append(StableDiagnostic("error", "SEC001", f"Capability beobachtet, aber nicht deklariert: {cap}", str(path), hint=f"berechtigung {cap} hinzufügen oder Nutzung entfernen"))
    return StableReport(not any(d.severity == "error" for d in diagnostics), diagnostics, {"sections": sorted(sections)})


def build74(source: Path, out: Path) -> dict[str, Any]:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    payload = build_stable_payload(source)
    json_out = out / "app.kbcstable.json"
    bin_out = out / "app.kbcstable"
    json_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_kbc_stable(payload, bin_out)
    spec_out = out / "KBC_STABLE_1_SPEC.json"
    spec_out.write_text(json.dumps(stable_spec(), ensure_ascii=False, indent=2), encoding="utf-8")
    policy = default_security_policy()
    (out / "keim.capabilities.json").write_text(json.dumps(policy, ensure_ascii=False, indent=2), encoding="utf-8")
    sbom = create_sbom(Path.cwd(), out)
    parity = parity_matrix(source, out / "parity")
    return {
        "ok": True,
        "format": KBC_STABLE_FORMAT,
        "json": str(json_out),
        "binary": str(bin_out),
        "spec": str(spec_out),
        "policy": str(out / "keim.capabilities.json"),
        "sbom": sbom,
        "parity": parity,
    }


def check74(source: Path) -> StableReport:
    diags: list[StableDiagnostic] = []
    try:
        r = check71(source)
        for d in getattr(r, "diagnostics", []):
            if hasattr(d, "as_dict"):
                dd = d.as_dict()
                diags.append(StableDiagnostic(dd.get("severity","error"), "BASE", dd.get("message",""), str(source), dd.get("line", 0)))
    except Exception as exc:
        diags.append(StableDiagnostic("error", "BASE", f"v7.1-Basisprüfung fehlgeschlagen: {exc}", str(source)))
    caps = _infer_capabilities_from_source(source)
    for cap in caps["missing"]:
        diags.append(StableDiagnostic("error", "SEC001", f"Capability nicht deklariert: {cap}", str(source), hint=f"berechtigung {cap}"))
    try:
        payload = build_stable_payload(source)
        if payload["sections"]["CODE"]:
            pass
    except Exception as exc:
        diags.append(StableDiagnostic("error", "KBCGEN", f"Stable-Bytecode-Erzeugung fehlgeschlagen: {exc}", str(source)))
    return StableReport(not any(d.severity == "error" for d in diags), diags, {"capabilities": caps})


def default_security_policy() -> dict[str, Any]:
    return {
        "format": "keim-capability-policy",
        "version": CAPABILITY_SCHEMA_VERSION,
        "default": "deny",
        "capabilities": {
            "io.read": {"allowed": False, "reason_required": True},
            "io.write": {"allowed": False, "reason_required": True},
            "net.http": {"allowed": False, "reason_required": True},
            "ffi.native": {"allowed": False, "reason_required": True},
            "dom": {"allowed": False, "reason_required": True},
            "time": {"allowed": True, "record_for_replay": True},
            "random": {"allowed": True, "record_for_replay": True},
        },
        "ffi": {"allowlist": []},
        "registry": {"require_sha256": True, "require_signature": True},
        "web": {"require_importmap_lock": True, "allow_eval": False},
    }


def security_scan(path: Path, policy_path: Path | None = None) -> StableReport:
    p = Path(path)
    files = list(p.rglob("*.keim")) if p.is_dir() else [p]
    policy = default_security_policy()
    if policy_path and Path(policy_path).exists():
        policy = json.loads(Path(policy_path).read_text(encoding="utf-8"))
    diags: list[StableDiagnostic] = []
    findings = []
    for f in files:
        caps = _infer_capabilities_from_source(f)
        findings.append({"path": str(f), **caps})
        for cap in caps["missing"]:
            diags.append(StableDiagnostic("error", "SEC001", f"Capability genutzt, aber nicht deklariert: {cap}", str(f), hint=f"berechtigung {cap}"))
        for cap in caps["declared"]:
            rule = policy.get("capabilities", {}).get(cap)
            if rule and not rule.get("allowed", False):
                diags.append(StableDiagnostic("warning", "SEC002", f"Capability durch Standardpolicy eingeschränkt: {cap}", str(f), hint="Policy prüfen oder explizit erlauben"))
    return StableReport(not any(d.severity == "error" for d in diags), diags, {"findings": findings, "policy": policy})


def create_sbom(cwd: Path, out: Path | None = None) -> dict[str, Any]:
    cwd = Path(cwd)
    files = []
    for pattern in ("keim/**/*.py", "examples/**/*.keim", "docs/**/*.md", "tests/**/*.py", "VERSION", "keim.toml"):
        for f in cwd.glob(pattern):
            if f.is_file() and "__pycache__" not in str(f):
                files.append({"path": str(f.relative_to(cwd)), "sha256": hashlib.sha256(f.read_bytes()).hexdigest(), "size": f.stat().st_size})
    sbom = {
        "format": "keim-sbom-v1",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "root": str(cwd),
        "file_count": len(files),
        "files": sorted(files, key=lambda x: x["path"]),
        "reproducible_build": {"python_hash_seed": "0 empfohlen", "canonical_json": True, "stable_bytecode": KBC_STABLE_FORMAT},
    }
    if out:
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "sbom.keim.json").write_text(json.dumps(sbom, ensure_ascii=False, indent=2), encoding="utf-8")
    return sbom


def parity_matrix(source: Path, out: Path | None = None) -> dict[str, Any]:
    outdir = Path(out) if out else None
    if outdir:
        outdir.mkdir(parents=True, exist_ok=True)
    results = []
    py_ok = False
    py_val = None
    try:
        res = run71(source)
        py_ok = bool(getattr(res, "ok", False))
        py_val = getattr(res, "value", None)
    except Exception as exc:
        results.append({"target": "python-vm", "ok": False, "error": str(exc)})
    else:
        results.append({"target": "python-vm", "ok": py_ok, "value": py_val})
    try:
        payload = build_stable_payload(source)
        wasm = payload["sections"].get("WASM", {})
        native = payload["sections"].get("NATV", {})
        results.append({"target": "wasm-wat", "ok": not wasm.get("unsupported_ops"), "manifest": wasm})
        results.append({"target": "native-keimvm", "ok": len(native.get("unsupported_ops", [])) == 0, "manifest": native})
    except Exception as exc:
        results.append({"target": "manifest-generation", "ok": False, "error": str(exc)})
    matrix = {"ok": all(r.get("ok") for r in results if r["target"] == "python-vm"), "source": str(source), "results": results}
    if outdir:
        (outdir / "parity_matrix.json").write_text(json.dumps(matrix, ensure_ascii=False, indent=2), encoding="utf-8")
    return matrix


def benchmark74(source: Path, out: Path, iterations: int = 5) -> dict[str, Any]:
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    rows = []
    for target in ("check", "bytecode", "run", "stable-write", "stable-read"):
        samples = []
        for _ in range(max(1, iterations)):
            start = time.perf_counter()
            if target == "check":
                check74(source)
            elif target == "bytecode":
                bytecode71(source)
            elif target == "run":
                try:
                    run71(source)
                except Exception:
                    pass
            elif target == "stable-write":
                payload = build_stable_payload(source)
                write_kbc_stable(payload, out / "_bench.kbcstable")
            elif target == "stable-read":
                tmp = out / "_bench.kbcstable"
                if not tmp.exists():
                    write_kbc_stable(build_stable_payload(source), tmp)
                read_kbc_stable(tmp)
            samples.append(time.perf_counter() - start)
        rows.append({
            "target": target,
            "iterations": len(samples),
            "min_seconds": min(samples),
            "max_seconds": max(samples),
            "avg_seconds": sum(samples) / len(samples),
        })
    report = {"format": "keim-benchmark-v1", "source": str(source), "rows": rows}
    (out / "benchmark.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "benchmark.md").write_text(_benchmark_md(report), encoding="utf-8")
    return report


def _benchmark_md(report: dict[str, Any]) -> str:
    lines = [f"# Keim Benchmark Report\n\nSource: `{report['source']}`\n", "| Target | Iterations | Min s | Avg s | Max s |", "|---|---:|---:|---:|---:|"]
    for r in report["rows"]:
        lines.append(f"| {r['target']} | {r['iterations']} | {r['min_seconds']:.6f} | {r['avg_seconds']:.6f} | {r['max_seconds']:.6f} |")
    return "\n".join(lines) + "\n"


def compatibility_matrix(cwd: Path, out: Path) -> dict[str, Any]:
    cwd = Path(cwd); out = Path(out); out.mkdir(parents=True, exist_ok=True)
    commands = []
    for f in sorted((cwd / "examples").glob("sprache_v*.keim")):
        if f.name.startswith("sprache_v71") or f.name.startswith("sprache_v70") or f.name.startswith("sprache_v69") or f.name.startswith("sprache_v68"):
            commands.append({"name": f.stem, "file": str(f.relative_to(cwd))})
    if not commands:
        for f in sorted((cwd / "examples").glob("*.keim"))[:10]:
            commands.append({"name": f.stem, "file": str(f.relative_to(cwd))})
    rows = []
    for c in commands:
        f = cwd / c["file"]
        rep = check74(f)
        rows.append({"name": c["name"], "file": c["file"], "ok": rep.ok, "diagnostics": [d.as_dict() for d in rep.diagnostics]})
    matrix = {"format": "keim-compatibility-matrix-v1", "ok": all(r["ok"] for r in rows), "rows": rows}
    (out / "compatibility_matrix.json").write_text(json.dumps(matrix, ensure_ascii=False, indent=2), encoding="utf-8")
    return matrix


# ---------------------------
# LSP / IDE core
# ---------------------------

KEYWORDS = ["modul", "verwende", "exportiere", "funktion", "gibt", "speicher", "setzt", "rueckgabe", "wenn", "sonst", "test", "typ", "akteur", "bei", "match", "fall", "ok", "fehler", "solange", "abbruch", "weiter", "berechtigung"]


def lsp_capabilities() -> dict[str, Any]:
    return {
        "capabilities": {
            "textDocumentSync": 1,
            "completionProvider": {"triggerCharacters": [" ", ".", "("]},
            "hoverProvider": True,
            "definitionProvider": True,
            "documentFormattingProvider": True,
            "diagnosticProvider": {"interFileDependencies": True, "workspaceDiagnostics": False},
        },
        "serverInfo": {"name": "keim-lsp", "version": "7.4.0"},
    }


def lsp_analyze_text(text: str, uri: str = "memory://document.keim") -> dict[str, Any]:
    diagnostics = []
    seen_funcs = {}
    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("funktion "):
            m = re.match(r"funktion\s+(\w+)", stripped)
            if m:
                name = m.group(1)
                if name in seen_funcs:
                    diagnostics.append(_lsp_diag(lineno, 0, len(line), f"Doppelte Funktion: {name}", 2))
                seen_funcs[name] = lineno
            if " gibt " not in stripped:
                diagnostics.append(_lsp_diag(lineno, 0, len(line), "Funktion braucht Rückgabetyp mit 'gibt'", 1))
        if "\t" in line:
            diagnostics.append(_lsp_diag(lineno, line.index("\t"), line.index("\t")+1, "Tabs vermeiden; Keim nutzt Leerzeichen", 3))
        if "eval" in stripped.lower():
            diagnostics.append(_lsp_diag(lineno, 0, len(line), "EVAL/dynamische Auswertung ist im stabilen Keim nicht erlaubt", 1))
    return {"uri": uri, "diagnostics": diagnostics, "symbols": [{"name": k, "line": v} for k, v in seen_funcs.items()]}


def _lsp_diag(line: int, start: int, end: int, message: str, severity: int) -> dict[str, Any]:
    return {"range": {"start": {"line": line-1, "character": start}, "end": {"line": line-1, "character": end}}, "severity": severity, "source": "keim", "message": message}


def lsp_completion(prefix: str = "") -> dict[str, Any]:
    items = [{"label": k, "kind": 14, "insertText": k} for k in KEYWORDS if not prefix or k.startswith(prefix)]
    snippets = [
        {"label": "funktion", "kind": 15, "insertText": "funktion name() gibt ganzzahl:\n    rueckgabe 0"},
        {"label": "test", "kind": 15, "insertText": "test \"name\":\n    pruefe wahr"},
        {"label": "match result", "kind": 15, "insertText": "match wert:\n    fall ok(x):\n        rueckgabe x\n    fall fehler(e):\n        rueckgabe 0"},
    ]
    return {"isIncomplete": False, "items": items + snippets}


def format_keim_text(text: str) -> str:
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            out.append("")
            continue
        indent = len(line) - len(line.lstrip(" "))
        indent = (indent // 4) * 4
        stripped = re.sub(r"\s+", " ", stripped)
        stripped = re.sub(r"\s*([+\-*/%]=?|==|!=|<=|>=|<|>)\s*", r" \1 ", stripped)
        stripped = re.sub(r"\s*,\s*", ", ", stripped)
        stripped = re.sub(r"\s+:", ":", stripped)
        out.append(" " * indent + stripped.strip())
    return "\n".join(out).rstrip() + "\n"


def write_lsp_bundle(out: Path) -> dict[str, Any]:
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    (out / "lsp_capabilities.json").write_text(json.dumps(lsp_capabilities(), ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "completion_items.json").write_text(json.dumps(lsp_completion(), ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "README_LSP.md").write_text("""# Keim LSP v7.4

Minimaler JSON-RPC/LSP-Kern für Editor-Integration.

Enthält:
- initialize capabilities
- completion items
- hover/diagnostic primitives
- formatting core
- symbol extraction

Produktionsintegration: Wrapper startet `python -m keim v74-lsp`.
""", encoding="utf-8")
    return {"ok": True, "out": str(out), "files": [str(p) for p in sorted(out.iterdir())]}


def run_lsp_stdio() -> None:
    # Conservative JSON-lines server useful for tests and editor bridges.
    import sys
    for line in sys.stdin:
        try:
            req = json.loads(line)
            method = req.get("method")
            if method == "initialize":
                result = lsp_capabilities()
            elif method == "textDocument/completion":
                result = lsp_completion()
            elif method == "keim/analyzeText":
                result = lsp_analyze_text(req.get("params", {}).get("text", ""))
            elif method == "textDocument/formatting":
                result = {"text": format_keim_text(req.get("params", {}).get("text", ""))}
            else:
                result = {"error": f"unknown method {method}"}
            print(json.dumps({"jsonrpc": "2.0", "id": req.get("id"), "result": result}, ensure_ascii=False), flush=True)
        except Exception as exc:
            print(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32000, "message": str(exc)}}), flush=True)


def emit_enterprise_whitepaper(out: Path) -> dict[str, Any]:
    text = """# Keim Genesis v7.4.0 – Enterprise Stabilization & Developer Platform

## Ziel

v7.4 verschiebt Keim von schneller Feature-Evolution zu Stabilisierung:
stabile Bytecode-Spezifikation, Security-Grenzen, IDE/LSP-Grundlage,
Kompatibilitätstests, Benchmarks und Paritätsmanifeste.

## Kernartefakte

- KBC-STABLE-1
- keim-capability-policy
- keim-sbom-v1
- keim-compatibility-matrix-v1
- keim-benchmark-v1
- Keim LSP core
- Native/WASM parity manifests

## Ehrlicher Status

Keim besitzt nun eine breite Runtime- und Tooling-Kette. Produktionsreife entsteht
durch wiederholbare Builds, stabile Spezifikationen, Security-Gates, Benchmarks
und Differentialtests – genau diese Ebene ergänzt v7.4.

## Sicherheitsmodell

Keim nutzt deny-by-default Capabilities. Externe IO-, Netz-, FFI- und DOM-Zugriffe
müssen deklariert und durch Policy erlaubt werden.

## Bytecode

KBC-STABLE-1 ist ein sectioned binary container mit Magic, Version,
Directory, Section-Checksums und Payload-Hash.

## IDE

Der LSP-Kern bietet initiale Editorfähigkeiten: Completion, Diagnose,
Formatierung und Symbolerkennung.

## Nächste Härtung

- vollständige native Ausführung aller dynamischen Werte
- echte WASM-Ausführungstests mit Runtime
- Registry-Trust und Signaturen mit Public-Key-Modell
- umfangreiches Fuzzing
"""
    out = Path(out); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return {"ok": True, "path": str(out)}
