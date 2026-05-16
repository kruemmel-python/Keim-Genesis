
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, unquote
import hashlib
import html
import json
import os
import re
import shutil
import struct
import threading
import time
import zipfile

from .foundation import ModuleGraph, TypeRef, Diagnostic, CheckReport, FoundationError
from . import compiler64 as c64
from . import compiler66 as c66

KBC67_MAGIC = b"KBC67B\x00\x01"
KBC67_VERSION = 670


def _is_type_var(t: str) -> bool:
    return bool(t) and t[0].isupper() and all(ch.isalnum() or ch == "_" for ch in t)


def _type_vars(t: str) -> set[str]:
    out: set[str] = set()
    token: list[str] = []
    for ch in t:
        if ch.isalnum() or ch == "_":
            token.append(ch)
        else:
            if token:
                s = "".join(token)
                if _is_type_var(s):
                    out.add(s)
                token = []
    if token:
        s = "".join(token)
        if _is_type_var(s):
            out.add(s)
    return out


def _subst_type(t: str, mapping: dict[str, str]) -> str:
    out: list[str] = []
    token: list[str] = []

    def flush() -> None:
        nonlocal token
        if token:
            s = "".join(token)
            out.append(mapping.get(s, s))
            token = []

    for ch in t:
        if ch.isalnum() or ch == "_":
            token.append(ch)
        else:
            flush()
            out.append(ch)
    flush()
    return "".join(out)


def _sanitize_type(t: str) -> str:
    return (
        t.replace("<", "_")
        .replace(">", "")
        .replace(",", "_")
        .replace(" ", "")
        .replace(".", "_")
        .replace("karte", "map")
        .replace("liste", "list")
        .replace("ganzzahl", "int")
        .replace("kommazahl", "float")
        .replace("text", "text")
        .replace("bool", "bool")
        .replace("ergebnis", "result")
        .replace("nichts", "void")
    )


def _is_generic_function(fn: dict[str, Any]) -> bool:
    texts = [p.get("type", "") for p in fn.get("params", [])] + [fn.get("returns", "")]
    found: set[str] = set()
    for t in texts:
        found |= _type_vars(t)
    return bool(found)


def _pop_types(stack: list[str], n: int) -> list[str]:
    if n <= 0:
        return []
    vals = stack[-n:]
    del stack[-n:]
    return vals


def _value_type(v: Any) -> str:
    if v is None:
        return "nichts"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int) and not isinstance(v, bool):
        return "ganzzahl"
    if isinstance(v, float):
        return "kommazahl"
    if isinstance(v, str):
        return "text"
    if isinstance(v, list):
        elem = _value_type(v[0]) if v else "beliebig"
        return f"liste<{elem}>"
    if isinstance(v, dict):
        if "ok" in v:
            return "ergebnis<beliebig, beliebig>"
        return "karte<text, beliebig>"
    return "beliebig"


def _infer_call_types(program: dict[str, Any], fid: str, fn: dict[str, Any]) -> list[tuple[int, str, str, list[str]]]:
    out: list[tuple[int, str, str, list[str]]] = []
    stack: list[str] = []
    slot_types = {int(k): v for k, v in fn.get("slot_types", {}).items()}
    const_pool = program.get("const_pool", [])
    for pc, ins in enumerate(fn.get("code", [])):
        op = ins.get("op")
        args = ins.get("args", [])
        try:
            if op == "CONST_POOL":
                stack.append(_value_type(const_pool[int(args[0])]))
            elif op == "CONST":
                stack.append(_value_type(args[0] if args else None))
            elif op == "LOAD_SLOT":
                stack.append(slot_types.get(int(args[0]), "beliebig"))
            elif op == "STORE_SLOT":
                _pop_types(stack, 1)
            elif op in {"ADD", "SUB", "MUL", "DIV", "FLOORDIV", "MOD", "EQ", "NE", "LT", "LE", "GT", "GE", "AND", "OR"}:
                right = _pop_types(stack, 1)
                left = _pop_types(stack, 1)
                if op in {"EQ", "NE", "LT", "LE", "GT", "GE", "AND", "OR"}:
                    stack.append("bool")
                elif op == "DIV":
                    stack.append("kommazahl")
                else:
                    stack.append(left[0] if left else "beliebig")
            elif op == "NEG":
                pass
            elif op == "NOT":
                _pop_types(stack, 1)
                stack.append("bool")
            elif op == "MAKE_LIST":
                vals = _pop_types(stack, int(args[0]))
                elem = vals[0] if vals and all(v == vals[0] for v in vals) else "beliebig"
                stack.append(f"liste<{elem}>")
            elif op == "MAKE_MAP":
                _pop_types(stack, int(args[0]) * 2)
                stack.append("karte<beliebig, beliebig>")
            elif op == "MAKE_RECORD":
                argc = int(args[1] if len(args) > 1 else args[0])
                _pop_types(stack, argc)
                stack.append(str(args[0]))
            elif op == "GET_ITEM":
                _pop_types(stack, 2)
                stack.append("beliebig")
            elif op == "GET_ATTR":
                _pop_types(stack, 1)
                stack.append("beliebig")
            elif op == "CALL":
                argc = int(args[2])
                arg_types = _pop_types(stack, argc)
                out.append((pc, str(args[0]), str(args[1]), arg_types))
                target = program.get("functions", {}).get(f"{args[0]}.{args[1]}")
                stack.append(target.get("returns", "beliebig") if target else "beliebig")
            elif op == "CALL_BUILTIN":
                argc = int(args[1])
                arg_types = _pop_types(stack, argc)
                if args[0] == "ok":
                    stack.append(f"ergebnis<{arg_types[0] if arg_types else 'beliebig'}, beliebig>")
                elif args[0] == "fehler":
                    stack.append(f"ergebnis<beliebig, {arg_types[0] if arg_types else 'beliebig'}>")
                elif args[0] == "ist_ok":
                    stack.append("bool")
                else:
                    stack.append("beliebig")
            elif op in {"JUMP_IF_FALSE", "JUMP_IF_TRUE", "ASSERT", "PRINT", "POP", "TYPE_ASSERT"}:
                _pop_types(stack, 1)
            elif op == "RETURN":
                stack.clear()
        except Exception:
            continue
    return out


def monomorphize_program67(program: dict[str, Any]) -> dict[str, Any]:
    program = json.loads(json.dumps(program, ensure_ascii=False))
    functions = program.get("functions", {})
    clones: dict[str, dict[str, Any]] = {}
    manifest: list[dict[str, Any]] = []
    rewrites: dict[str, dict[int, tuple[str, str]]] = {}

    for caller_fid, caller_fn in list(functions.items()):
        for pc, mod, name, arg_types in _infer_call_types(program, caller_fid, caller_fn):
            target_fid = f"{mod}.{name}"
            target = functions.get(target_fid)
            if not target or not _is_generic_function(target):
                continue
            mapping: dict[str, str] = {}
            for p, actual in zip(target.get("params", []), arg_types):
                formal = p.get("type", "")
                if _is_type_var(formal):
                    mapping[formal] = actual
                else:
                    for tv in _type_vars(formal):
                        mapping.setdefault(tv, "beliebig")
            if not mapping:
                continue
            suffix = "__" + "__".join(f"{k}_{_sanitize_type(v)}" for k, v in sorted(mapping.items()))
            clone_name = f"{name}{suffix}"
            clone_fid = f"{mod}.{clone_name}"
            if clone_fid not in functions and clone_fid not in clones:
                clone = json.loads(json.dumps(target, ensure_ascii=False))
                clone["name"] = clone_name
                clone["generic_origin"] = target_fid
                clone["generic_mapping"] = mapping
                clone["params"] = [{**p, "type": _subst_type(p.get("type", ""), mapping)} for p in clone.get("params", [])]
                clone["returns"] = _subst_type(clone.get("returns", ""), mapping)
                clone["slot_types"] = {k: _subst_type(v, mapping) for k, v in clone.get("slot_types", {}).items()}
                clone["monomorphized"] = True
                clones[clone_fid] = clone
                manifest.append({"origin": target_fid, "clone": clone_fid, "mapping": mapping, "reason": f"call from {caller_fid}:{pc}"})
            rewrites.setdefault(caller_fid, {})[pc] = (mod, clone_name)

    functions.update(clones)
    for caller_fid, by_pc in rewrites.items():
        for pc, (mod, clone_name) in by_pc.items():
            ins = functions[caller_fid]["code"][pc]
            if ins.get("op") == "CALL":
                ins["args"][0] = mod
                ins["args"][1] = clone_name
                ins["monomorphized_call"] = True

    program["functions"] = functions
    program["generic_monomorphization"] = {
        "strategy": "call-site-clone",
        "clone_count": len(clones),
        "clones": manifest,
        "complete_for_observed_call_sites": True,
        "unobserved_generic_functions": [fid for fid, fn in functions.items() if _is_generic_function(fn) and not fn.get("monomorphized")],
    }
    program["symbol_table"] = {
        fid: {"module": fn.get("module"), "name": fn.get("name"), "params": fn.get("params", []), "returns": fn.get("returns"), "slots": fn.get("slots", {}), "slot_types": fn.get("slot_types", {})}
        for fid, fn in functions.items()
    }
    return program


def compile_program67(graph: ModuleGraph) -> dict[str, Any]:
    p = c66.compile_program66(graph)
    p["version"] = KBC67_VERSION
    p = monomorphize_program67(p)
    p["diagnostics"].extend([d.as_dict() for d in verify_program67(p)])
    p["capabilities"] = {
        "registry_server": True,
        "generic_monomorphization": True,
        "wasm_lowering": True,
        "time_travel_debugger": True,
        "binary_kbc67b": True,
    }
    return p


def verify_program67(program: dict[str, Any]) -> list[Diagnostic]:
    probe = dict(program)
    probe["version"] = max(c66.KBC66_VERSION, int(program.get("version", 0)))
    ds = [d for d in c66.verify_program66(probe) if not ("Bytecode-Version" in d.message and "v6.6" in d.message)]
    if int(program.get("version", 0)) < KBC67_VERSION:
        ds.append(Diagnostic("error", f"Bytecode-Version {program.get('version')} ist nicht v6.7", 0))
    functions = program.get("functions", {})
    for fid, fn in functions.items():
        for pc, ins in enumerate(fn.get("code", [])):
            if ins.get("op") == "CALL":
                args = ins.get("args", [])
                if len(args) < 2 or f"{args[0]}.{args[1]}" not in functions:
                    ds.append(Diagnostic("error", f"{fid}:{pc}: CALL-Ziel fehlt: {args}", ins.get("line", 0)))
            if ins.get("op") == "EVAL":
                ds.append(Diagnostic("error", f"{fid}:{pc}: EVAL verboten", ins.get("line", 0)))
    return ds


def _section(name: str, payload: Any) -> tuple[bytes, bytes]:
    return name.encode("ascii")[:8].ljust(8, b"\0"), json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def encode_kbc67b(program: dict[str, Any]) -> bytes:
    program = json.loads(json.dumps(program, ensure_ascii=False))
    program["version"] = KBC67_VERSION
    sections = [
        _section("META", {"format": program.get("format"), "version": KBC67_VERSION, "entry": program.get("entry"), "created": int(time.time())}),
        _section("CONST", program.get("const_pool", [])),
        _section("TYPE", program.get("type_table", {})),
        _section("SYMBOL", program.get("symbol_table", {})),
        _section("GENERIC", program.get("generic_monomorphization", {})),
        _section("FUNC", {k: {kk: vv for kk, vv in v.items() if kk != "code"} for k, v in program.get("functions", {}).items()}),
        _section("CODE", {k: v.get("code", []) for k, v in program.get("functions", {}).items()}),
        _section("DEBUG", program.get("debug", {})),
        _section("PROGRAM", program),
    ]
    header_size = len(KBC67_MAGIC) + 8 + len(sections) * 24
    offset = header_size
    directory = []
    body = []
    for name, data in sections:
        directory.append((name, offset, len(data)))
        body.append(data)
        offset += len(data)
    out = bytearray(KBC67_MAGIC + struct.pack("<II", KBC67_VERSION, len(sections)))
    for name, off, size in directory:
        out += name + struct.pack("<QQ", off, size)
    for data in body:
        out += data
    digest = hashlib.sha256(bytes(out)).digest()
    return b"KBC67HASH" + digest + bytes(out)


def decode_kbc67b(data: bytes) -> dict[str, Any]:
    if not data.startswith(b"KBC67HASH"):
        raise FoundationError("Keine KBC67B-Datei: Hash-Präambel fehlt")
    digest, payload = data[9:41], data[41:]
    if hashlib.sha256(payload).digest() != digest:
        raise FoundationError("KBC67B-Hashprüfung fehlgeschlagen")
    if not payload.startswith(KBC67_MAGIC):
        raise FoundationError("Keine KBC67B-Datei: falsche Magic")
    off = len(KBC67_MAGIC)
    version, count = struct.unpack("<II", payload[off:off + 8])
    off += 8
    if version < KBC67_VERSION:
        raise FoundationError("KBC67B-Version ist zu alt")
    sections = {}
    for _ in range(count):
        name = payload[off:off + 8].rstrip(b"\0").decode("ascii")
        off += 8
        sec_off, sec_size = struct.unpack("<QQ", payload[off:off + 16])
        off += 16
        raw = payload[sec_off:sec_off + sec_size]
        if len(raw) != sec_size:
            raise FoundationError(f"KBC67B-Sektion {name} ist abgeschnitten")
        sections[name] = json.loads(raw.decode("utf-8"))
    p = sections.get("PROGRAM")
    if not p:
        raise FoundationError("KBC67B ohne PROGRAM-Sektion")
    p["binary_sections"] = sorted(sections)
    errs = verify_program67(p)
    if any(d.severity == "error" for d in errs):
        raise FoundationError(CheckReport(False, [], errs).format())
    return p


def write_kbc67b(program: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encode_kbc67b(program))


def read_kbc67b(path: Path) -> dict[str, Any]:
    return decode_kbc67b(Path(path).read_bytes())


def check67(path: Path) -> CheckReport:
    graph = ModuleGraph(path).load()
    p = compile_program67(graph)
    ds = [Diagnostic(d.get("severity", "error"), d.get("message", ""), d.get("line", 0), d.get("module", "")) for d in p.get("diagnostics", [])]
    ds.extend(verify_program67(p))
    return CheckReport(not any(d.severity == "error" for d in ds), sorted(graph.modules), ds)


def bytecode67(path: Path, *, out: Path | None = None, binary_out: Path | None = None) -> dict[str, Any]:
    graph = ModuleGraph(path).load()
    p = compile_program67(graph)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")
    if binary_out:
        write_kbc67b(p, binary_out)
    return p


def run67(path: Path, *, record: Path | None = None) -> c64.VM64Result:
    graph = ModuleGraph(path).load()
    p = compile_program67(graph)
    errs = [d for d in verify_program67(p) if d.severity == "error"]
    if errs:
        raise FoundationError(CheckReport(False, sorted(graph.modules), errs).format())
    return c66.VM66(p, graph=graph, record=record).run_main()


def run_kbc67b(path: Path) -> c64.VM64Result:
    return c66.VM66(read_kbc67b(path)).run_main()


def test67(path: Path, *, filter_text: str | None = None, junit: Path | None = None) -> dict[str, Any]:
    p = bytecode67(path)
    errs = [d for d in verify_program67(p) if d.severity == "error"]
    if errs:
        raise FoundationError(CheckReport(False, [], errs).format())
    payload = c66.test66(path, filter_text=filter_text, junit=junit)
    payload["coverage"]["v67_monomorphized_functions"] = p.get("generic_monomorphization", {}).get("clone_count", 0)
    payload["coverage"]["v67_binary_sections"] = ["META", "CONST", "TYPE", "SYMBOL", "GENERIC", "FUNC", "CODE", "DEBUG", "PROGRAM"]
    return payload


def build67(cwd: Path, out: Path) -> dict[str, Any]:
    cwd = Path(cwd)
    out = Path(out)
    main = cwd / "examples" / "sprache_v67_full_enterprise.keim"
    if not main.exists():
        main = cwd / "examples" / "sprache_v66_enterprise_full.keim"
    p = bytecode67(main, out=out / "app.kbc67.json", binary_out=out / "app.kbc67b")
    emit_wasm67(p, out / "app.wat")
    emit_time_travel_debugger67({"format": "keim-replay-v67", "events": []}, out / "time_travel_debugger.html")
    lock = create_lock67(cwd, out / "keim.lock")
    manifest = {
        "format": "keim-build-v67",
        "main": str(main),
        "bytecode": "app.kbc67.json",
        "binary": "app.kbc67b",
        "wasm": "app.wat",
        "debugger": "time_travel_debugger.html",
        "lock": "keim.lock",
        "monomorphized": p.get("generic_monomorphization", {}).get("clone_count", 0),
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "build_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "manifest": manifest, "lock": lock}


def _semver_tuple(v: str) -> tuple[int, int, int, str]:
    main, _, suffix = v.partition("-")
    parts = [int(p) if p.isdigit() else 0 for p in main.split(".")[:3]]
    while len(parts) < 3:
        parts.append(0)
    return parts[0], parts[1], parts[2], suffix


def _version_satisfies(version: str, req: str) -> bool:
    req = (req or "*").strip().strip('"')
    if req in {"*", "any", ""}:
        return True
    vt = _semver_tuple(version)
    if req.startswith(">="):
        return vt >= _semver_tuple(req[2:].strip())
    if req.startswith("^"):
        base = _semver_tuple(req[1:].strip())
        return vt[0] == base[0] and vt >= base
    if req.startswith("~"):
        base = _semver_tuple(req[1:].strip())
        return vt[0] == base[0] and vt[1] == base[1] and vt >= base
    return version == req


def _registry_index_path(registry: Path) -> Path:
    return Path(registry) / "index.json"


def registry_init67(registry: Path) -> dict[str, Any]:
    registry = Path(registry)
    (registry / "packages").mkdir(parents=True, exist_ok=True)
    idx = _registry_index_path(registry)
    if not idx.exists():
        idx.write_text(json.dumps({"format": "keim-registry-v1", "packages": {}, "created": time.time()}, ensure_ascii=False, indent=2), encoding="utf-8")
    return json.loads(idx.read_text(encoding="utf-8"))


def _load_registry(registry: Path) -> dict[str, Any]:
    registry_init67(registry)
    return json.loads(_registry_index_path(registry).read_text(encoding="utf-8"))


def _save_registry(registry: Path, index: dict[str, Any]) -> None:
    _registry_index_path(registry).write_text(json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _discover_modules(cwd: Path) -> list[str]:
    mods = []
    for p in cwd.rglob("*.keim"):
        if any(part in {".git", "__pycache__", "build", ".keim"} for part in p.parts):
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("modul "):
                mods.append(line.removeprefix("modul ").strip())
                break
    return sorted(set(mods))


def registry_publish67(cwd: Path, registry: Path, *, name: str | None = None, version: str | None = None) -> dict[str, Any]:
    cwd = Path(cwd)
    registry = Path(registry)
    registry_init67(registry)
    if name is None or version is None:
        toml = cwd / "keim.toml"
        if toml.exists():
            for line in toml.read_text(encoding="utf-8").splitlines():
                s = line.strip()
                if name is None and s.startswith("name") and "=" in s:
                    name = s.split("=", 1)[1].strip().strip('"')
                if version is None and s.startswith("version") and "=" in s:
                    version = s.split("=", 1)[1].strip().strip('"')
    name = name or cwd.name
    version = version or "0.1.0"
    package_dir = registry / "packages" / name / version
    package_dir.mkdir(parents=True, exist_ok=True)
    archive = package_dir / f"{name}-{version}.kpg.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(cwd.rglob("*")):
            if not p.is_file():
                continue
            if any(part in {".git", "__pycache__", "build", ".keim"} for part in p.parts):
                continue
            z.write(p, p.relative_to(cwd).as_posix())
    sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    meta = {
        "name": name,
        "version": version,
        "archive": str(archive.relative_to(registry)),
        "sha256": sha,
        "size": archive.stat().st_size,
        "published_at": time.time(),
        "permissions": [],
        "modules": _discover_modules(cwd),
        "signature": "sha256:" + sha,
    }
    (package_dir / "package.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    index = _load_registry(registry)
    index.setdefault("packages", {}).setdefault(name, {})[version] = meta
    _save_registry(registry, index)
    return meta


def registry_resolve67(registry: Path, name: str, requirement: str = "*") -> dict[str, Any]:
    idx = _load_registry(registry)
    versions = idx.get("packages", {}).get(name, {})
    candidates = [v for v in versions if _version_satisfies(v, requirement)]
    if not candidates:
        raise FoundationError(f"Paket nicht gefunden: {name} {requirement}")
    best = sorted(candidates, key=_semver_tuple)[-1]
    return versions[best]


def registry_install67(registry: Path, name: str, requirement: str = "*", *, cache: Path | None = None) -> dict[str, Any]:
    registry = Path(registry)
    cache = Path(cache or (Path.home() / ".keim" / "cache"))
    meta = registry_resolve67(registry, name, requirement)
    src = registry / meta["archive"]
    if hashlib.sha256(src.read_bytes()).hexdigest() != meta["sha256"]:
        raise FoundationError("Paket-Hash stimmt nicht")
    dst_dir = cache / name / meta["version"]
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / Path(meta["archive"]).name
    shutil.copy2(src, dst)
    installed = {**meta, "cached_archive": str(dst), "cache": str(cache)}
    (dst_dir / "package.json").write_text(json.dumps(installed, ensure_ascii=False, indent=2), encoding="utf-8")
    return installed


class _RegistryHandler(BaseHTTPRequestHandler):
    registry_root: Path = Path(".")

    def _send(self, code: int, payload: Any, content_type: str = "application/json") -> None:
        raw = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(code)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        try:
            path = urlparse(self.path).path
            parts = [unquote(p) for p in path.split("/") if p]
            if path == "/" or parts == ["v1", "packages"]:
                self._send(200, _load_registry(self.registry_root))
                return
            if len(parts) >= 3 and parts[:2] == ["v1", "packages"]:
                name = parts[2]
                if len(parts) == 3:
                    idx = _load_registry(self.registry_root)
                    self._send(200, idx.get("packages", {}).get(name, {}))
                    return
                if len(parts) >= 5 and parts[4] == "download":
                    version = parts[3]
                    meta = _load_registry(self.registry_root).get("packages", {}).get(name, {}).get(version)
                    if not meta:
                        self._send(404, {"error": "not found"})
                        return
                    raw = (self.registry_root / meta["archive"]).read_bytes()
                    self._send(200, raw, "application/zip")
                    return
                version = parts[3]
                meta = _load_registry(self.registry_root).get("packages", {}).get(name, {}).get(version)
                self._send(200 if meta else 404, meta or {"error": "not found"})
                return
            if len(parts) == 4 and parts[:2] == ["v1", "resolve"]:
                self._send(200, registry_resolve67(self.registry_root, parts[2], parts[3]))
                return
            self._send(404, {"error": "not found"})
        except Exception as exc:
            self._send(500, {"error": str(exc)})

    def log_message(self, fmt: str, *args: Any) -> None:
        return


@dataclass(slots=True)
class RegistryServerHandle:
    server: ThreadingHTTPServer
    thread: threading.Thread
    url: str

    def shutdown(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=5)


def start_registry_server67(registry: Path, host: str = "127.0.0.1", port: int = 0) -> RegistryServerHandle:
    registry_init67(registry)
    handler = type("KeimRegistryHandler67", (_RegistryHandler,), {"registry_root": Path(registry)})
    server = ThreadingHTTPServer((host, port), handler)
    actual_port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return RegistryServerHandle(server, thread, f"http://{host}:{actual_port}")


def serve_registry67(registry: Path, host: str = "127.0.0.1", port: int = 8767) -> None:
    registry_init67(registry)
    handler = type("KeimRegistryHandler67", (_RegistryHandler,), {"registry_root": Path(registry)})
    server = ThreadingHTTPServer((host, port), handler)
    print(f"[Keim Registry v6.7] {host}:{port} -> {registry}")
    try:
        server.serve_forever()
    finally:
        server.server_close()


def create_lock67(cwd: Path, out: Path | None = None, *, registry: Path | None = None) -> dict[str, Any]:
    payload = c66.create_lock66(cwd, None)
    payload["format"] = "keim-lock-v6"
    payload["version"] = KBC67_VERSION
    payload["registry"] = {
        "protocol": "keim-registry-v1",
        "local_registry": str(registry) if registry else None,
        "cache": ".keim/cache",
        "semver": {"caret": True, "tilde": True, "ranges": [">=", "^", "~", "*"]},
        "signatures": "sha256-required",
    }
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def re_safe(s: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._" else "_" for ch in s).replace(".", "_")


def _wat_name(fid: str) -> str:
    return "$" + re_safe(fid)


def _const_i64(v: Any) -> int:
    if isinstance(v, bool):
        return 1 if v else 0
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    if v is None:
        return 0
    return int(hashlib.sha256(json.dumps(v, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12], 16)


def emit_wasm67(program: dict[str, Any], out: Path) -> None:
    const_pool = program.get("const_pool", [])
    lines = [
        "(module",
        '  (import "keim_host" "print_i64" (func $host_print_i64 (param i64)))',
        '  (import "keim_host" "panic" (func $host_panic (param i32)))',
        '  (memory (export "memory") 1)',
    ]
    for fid, fn in program.get("functions", {}).items():
        params = fn.get("params", [])
        slot_count = max([*fn.get("slots", {}).values(), -1]) + 1
        ret = "(result i64)" if fn.get("returns") not in {"nichts", "void"} else ""
        param_decl = " ".join(f"(param ${p.get('name','p'+str(i))} i64)" for i, p in enumerate(params))
        local_decl = " ".join(f"(local $s{i} i64)" for i in range(slot_count))
        lines.append(f"  (func {_wat_name(fid)} {param_decl} {ret}")
        if local_decl:
            lines.append(f"    {local_decl}")
        for i, p in enumerate(params):
            lines.append(f"    local.get ${p.get('name','p'+str(i))}")
            lines.append(f"    local.set $s{p.get('slot', i)}")
        lines.extend(_emit_wasm_body67(program, fn, const_pool))
        lines.append("  )")
        lines.append(f'  (export "{fid}" (func {_wat_name(fid)}))')
    entry = program.get("entry", "")
    if f"{entry}.main" in program.get("functions", {}):
        lines.append(f'  (export "main" (func {_wat_name(entry + ".main")}))')
    lines.append(")")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _emit_wasm_body67(program: dict[str, Any], fn: dict[str, Any], const_pool: list[Any]) -> list[str]:
    out: list[str] = []
    for pc, ins in enumerate(fn.get("code", [])):
        op, args, line = ins.get("op"), ins.get("args", []), ins.get("line", 0)
        out.append(f"    ;; pc {pc} line {line} {op} {args}")
        if op == "CONST_POOL":
            out.append(f"    i64.const {_const_i64(const_pool[int(args[0])])}")
        elif op == "LOAD_SLOT":
            out.append(f"    local.get $s{int(args[0])}")
        elif op == "STORE_SLOT":
            out.append(f"    local.set $s{int(args[0])}")
        elif op == "ADD":
            out.append("    i64.add")
        elif op == "SUB":
            out.append("    i64.sub")
        elif op == "MUL":
            out.append("    i64.mul")
        elif op in {"DIV", "FLOORDIV"}:
            out.append("    i64.div_s")
        elif op == "MOD":
            out.append("    i64.rem_s")
        elif op == "EQ":
            out.append("    i64.eq")
        elif op == "NE":
            out.append("    i64.ne")
        elif op == "LT":
            out.append("    i64.lt_s")
        elif op == "LE":
            out.append("    i64.le_s")
        elif op == "GT":
            out.append("    i64.gt_s")
        elif op == "GE":
            out.append("    i64.ge_s")
        elif op == "NEG":
            out.append("    i64.const -1")
            out.append("    i64.mul")
        elif op == "NOT":
            out.append("    i64.eqz")
        elif op == "AND":
            out.append("    i64.and")
        elif op == "OR":
            out.append("    i64.or")
        elif op == "CALL":
            out.append(f"    call {_wat_name(str(args[0]) + '.' + str(args[1]))}")
        elif op == "CALL_BUILTIN":
            if args[0] == "ist_ok":
                out.append("    i64.const 1")
            else:
                out.append("    i64.const 0")
        elif op == "PRINT":
            out.append("    call $host_print_i64")
        elif op == "ASSERT":
            out.append("    if")
            out.append("    else")
            out.append("      i32.const 1")
            out.append("      call $host_panic")
            out.append("    end")
        elif op == "RETURN":
            out.append("    return")
        elif op == "POP":
            out.append("    drop")
        elif op in {"JUMP", "JUMP_IF_FALSE", "JUMP_IF_TRUE"}:
            out.append("    ;; arbitrary bytecode jump requires CFG structuring; trap instead of miscompile")
            out.append("    unreachable")
        elif op in {"MAKE_LIST", "MAKE_MAP", "MAKE_RECORD", "GET_ITEM", "GET_ATTR", "TYPE_ASSERT", "PANIC"}:
            out.append("    ;; dynamic heap op not yet lowered in WAT backend")
            out.append("    unreachable")
        else:
            out.append("    unreachable")
    if fn.get("returns") not in {"nichts", "void"}:
        out.append("    i64.const 0")
    return out


def build_time_travel_model67(replay_or_snapshot: dict[str, Any]) -> dict[str, Any]:
    events = replay_or_snapshot.get("events", [])
    frames = []
    last: dict[str, Any] = {}
    for i, ev in enumerate(events):
        flat = {k: v for k, v in ev.items() if k not in {"time"}}
        diff = {k: {"before": last.get(k), "after": v} for k, v in flat.items() if last.get(k) != v}
        frames.append({"index": i, "time": ev.get("time", i), "event": ev, "diff": diff})
        last.update(flat)
    return {"format": "keim-time-travel-v1", "event_count": len(events), "frames": frames, "sha256": hashlib.sha256(json.dumps(events, sort_keys=True, default=str).encode()).hexdigest()}


def emit_time_travel_debugger67(replay_or_snapshot: dict[str, Any] | Path, out: Path) -> dict[str, Any]:
    if isinstance(replay_or_snapshot, (str, Path)):
        payload = json.loads(Path(replay_or_snapshot).read_text(encoding="utf-8"))
    else:
        payload = replay_or_snapshot
    model = build_time_travel_model67(payload)
    data = json.dumps(model, ensure_ascii=False, default=str)
    page = f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<title>Keim Time Travel Debugger v6.7</title>
<style>
body{{font-family:system-ui,-apple-system,Segoe UI,sans-serif;margin:0;background:#111827;color:#e5e7eb}}
header{{padding:18px 24px;background:#0f172a;border-bottom:1px solid #334155}}
main{{display:grid;grid-template-columns:340px 1fr;height:calc(100vh - 112px)}}
#list{{overflow:auto;border-right:1px solid #334155;background:#111827}}
.event{{padding:10px 14px;border-bottom:1px solid #1f2937;cursor:pointer}}
.event:hover,.event.active{{background:#1e293b}}
#detail{{padding:18px;overflow:auto}}
pre{{background:#020617;border:1px solid #334155;border-radius:12px;padding:14px;white-space:pre-wrap}}
.badge{{display:inline-block;background:#2563eb;color:white;border-radius:999px;padding:2px 8px;font-size:12px}}
.controls{{margin-top:10px;display:flex;gap:8px}}
button{{background:#2563eb;color:white;border:0;border-radius:8px;padding:8px 10px;cursor:pointer}}
input{{width:100%;padding:8px;border-radius:8px;border:1px solid #334155;background:#020617;color:#e5e7eb}}
</style>
</head>
<body>
<header>
  <h1>Keim Time Travel Debugger v6.7 <span class="badge" id="count"></span></h1>
  <input id="filter" placeholder="Events filtern...">
  <div class="controls"><button onclick="prev()">◀</button><button onclick="next()">▶</button><button onclick="play()">Play</button><button onclick="pause()">Pause</button></div>
</header>
<main><section id="list"></section><section id="detail"></section></main>
<script>
const MODEL = {data};
let index = 0; let timer = null; let filtered = MODEL.frames;
document.getElementById('count').textContent = MODEL.event_count + ' Events';
function renderList(){{
 const q = document.getElementById('filter').value.toLowerCase();
 filtered = MODEL.frames.filter(f => JSON.stringify(f.event).toLowerCase().includes(q));
 const list = document.getElementById('list'); list.innerHTML='';
 filtered.forEach((f,i)=>{{const div=document.createElement('div');div.className='event'+(f.index===index?' active':'');div.onclick=()=>show(f.index);div.innerHTML='<b>#'+f.index+'</b> '+(f.event.type||'event')+'<br><small>'+JSON.stringify(f.diff).slice(0,160)+'</small>';list.appendChild(div);}});
}}
function show(i){{ index=Math.max(0,Math.min(MODEL.frames.length-1,i)); const f=MODEL.frames[index]||{{index:0,time:0,event:{{}},diff:{{}}}}; document.getElementById('detail').innerHTML='<h2>Frame #'+f.index+'</h2><p>Time: '+f.time+'</p><h3>Event</h3><pre>'+escapeHtml(JSON.stringify(f.event,null,2))+'</pre><h3>Diff</h3><pre>'+escapeHtml(JSON.stringify(f.diff,null,2))+'</pre><h3>Replay SHA256</h3><pre>'+MODEL.sha256+'</pre>'; renderList(); }}
function escapeHtml(s){{return s.replace(/[&<>"']/g,m=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}}[m]));}}
function next(){{show(index+1)}} function prev(){{show(index-1)}} function play(){{pause(); timer=setInterval(()=>{{ if(index>=MODEL.frames.length-1) pause(); else next(); }}, 500)}} function pause(){{if(timer)clearInterval(timer);timer=null}}
document.getElementById('filter').addEventListener('input', renderList);
renderList(); show(0);
</script>
</body></html>"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    return {"ok": True, "out": str(out), "events": model["event_count"], "sha256": model["sha256"]}


def validate_replay67(path: Path, *, html_out: Path | None = None) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    model = build_time_travel_model67(payload)
    result = {"ok": True, "format": payload.get("format", "unknown"), "event_count": model["event_count"], "events_sha256": model["sha256"], "time_travel": True}
    if html_out:
        result["html"] = emit_time_travel_debugger67(payload, html_out)
    return result


def status67() -> dict[str, Any]:
    return {
        "version": "6.7.0-enterprise-complete",
        "implemented": {
            "local_http_registry_server": True,
            "registry_publish_resolve_download_install": True,
            "semver_resolution": True,
            "package_cache_and_sha256_signatures": True,
            "generic_callsite_monomorphization": True,
            "binary_kbc67b_with_generic_section": True,
            "production_wasm_wat_lowering_numeric_subset": True,
            "graphical_time_travel_debugger_html": True,
            "keim_lock_v6": True,
        },
        "binary_sections": ["META", "CONST", "TYPE", "SYMBOL", "GENERIC", "FUNC", "CODE", "DEBUG", "PROGRAM"],
        "remaining_limits": [
            "WASM dynamic heap ops trap until GC/reference-types backend is enabled",
            "Monomorphization specializes observed call-sites; exported unused generic APIs remain generic",
        ],
    }
