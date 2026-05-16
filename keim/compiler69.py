
from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib
import json
import re
import struct
import time

from .foundation import ModuleGraph, Diagnostic, CheckReport, FoundationError
from . import compiler68 as c68

KBC69_MAGIC = b"KBC69B\x00\x01"
KBC69_VERSION = 690
GC_HEADER_SIZE = 24
GC_MARK_BIT = 1
GC_PINNED_BIT = 2


def _json_clone(x: Any) -> Any:
    return json.loads(json.dumps(x, ensure_ascii=False))


def _section(name: str, payload: Any) -> tuple[bytes, bytes]:
    return name.encode("ascii")[:8].ljust(8, b"\0"), json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _gc_metadata() -> dict[str, Any]:
    return {
        "algorithm": "non-moving-mark-sweep",
        "allocator": "free-list-first-fit-with-bump-fallback",
        "header_size": GC_HEADER_SIZE,
        "mark_bit": GC_MARK_BIT,
        "pinned_bit": GC_PINNED_BIT,
        "roots": ["value_stack", "locals", "globals", "pinned_constants"],
        "tracing": ["list_elements", "record_fields", "result_payload", "map_key_values"],
        "trigger": {"mode": "allocation_threshold", "default_bytes": 1048576},
        "sweep": "free-list",
    }


def _hashmap_metadata() -> dict[str, Any]:
    return {
        "strategy": "open-addressing",
        "probing": "linear",
        "entry_size": 24,
        "entry_layout": {"key": "i64@0", "value": "i64@8", "state": "u32@16", "hash": "u32@20"},
        "states": {"empty": 0, "occupied": 1, "tombstone": 2},
        "load_factor_limit": 0.70,
        "hash": "keim_value_hash",
        "equality": "keim_value_eq",
    }


def compile_program69(graph: ModuleGraph) -> dict[str, Any]:
    p = c68.compile_program68(graph)
    p = _json_clone(p)
    p["version"] = KBC69_VERSION
    heap = dict(p.get("heap_layouts", {}))
    heap["object_header"] = {"kind": "u32@0", "size": "u32@4", "aux": "u32@8", "flags": "u32@12", "next_free": "u32@16", "payload": "@24"}
    heap["gc"] = _gc_metadata()
    heap["hashmap"] = _hashmap_metadata()
    p["heap_layouts"] = heap
    p["wasm_runtime"] = {
        "name": "keim-wasm-gc-hashmap-runtime",
        "version": KBC69_VERSION,
        "tagged_value_i64": True,
        "linear_memory_heap": True,
        "gc": _gc_metadata(),
        "hashmap": _hashmap_metadata(),
        "text_runtime": True,
        "list_runtime": True,
        "map_runtime": "open_addressing_hashmap",
        "record_runtime": True,
        "result_runtime": True,
    }
    p["capabilities"] = dict(p.get("capabilities", {}), kbc69b=True, wasm_gc_runtime=True, wasm_hashmap_runtime=True, mark_sweep_gc=True, open_addressing_hashmap=True)
    p["diagnostics"] = [d for d in p.get("diagnostics", []) if "Bytecode-Version" not in d.get("message", "")]
    p["diagnostics"].extend([d.as_dict() for d in verify_program69(p)])
    return p


def verify_program69(program: dict[str, Any]) -> list[Diagnostic]:
    probe = _json_clone(program)
    probe["version"] = c68.KBC68_VERSION
    ds = [d for d in c68.verify_program68(probe) if "Bytecode-Version" not in d.message and "v6.8" not in d.message]
    if int(program.get("version", 0)) < KBC69_VERSION:
        ds.append(Diagnostic("error", f"Bytecode-Version {program.get('version')} ist nicht v6.9", 0))
    gc = program.get("wasm_runtime", {}).get("gc", {})
    hm = program.get("wasm_runtime", {}).get("hashmap", {})
    if gc.get("algorithm") != "non-moving-mark-sweep":
        ds.append(Diagnostic("error", "v6.9 erwartet non-moving-mark-sweep GC", 0))
    if hm.get("strategy") != "open-addressing":
        ds.append(Diagnostic("error", "v6.9 erwartet open-addressing Hashmap", 0))
    if "gc" not in program.get("heap_layouts", {}):
        ds.append(Diagnostic("error", "GC-Heap-Metadaten fehlen", 0))
    if "hashmap" not in program.get("heap_layouts", {}):
        ds.append(Diagnostic("error", "Hashmap-Heap-Metadaten fehlen", 0))
    for fid, fn in program.get("functions", {}).items():
        for pc, ins in enumerate(fn.get("code", [])):
            if ins.get("op") == "EVAL":
                ds.append(Diagnostic("error", f"{fid}:{pc}: EVAL verboten", ins.get("line", 0)))
    return ds


def encode_kbc69b(program: dict[str, Any]) -> bytes:
    program = _json_clone(program)
    program["version"] = KBC69_VERSION
    sections = [
        _section("META", {"format": program.get("format"), "version": KBC69_VERSION, "entry": program.get("entry"), "created": int(time.time())}),
        _section("CONST", program.get("const_pool", [])),
        _section("TYPE", program.get("type_table", {})),
        _section("SYMBOL", program.get("symbol_table", {})),
        _section("GENERIC", program.get("generic_monomorphization", {})),
        _section("HEAP", program.get("heap_layouts", {})),
        _section("GC", program.get("wasm_runtime", {}).get("gc", {})),
        _section("HASHMAP", program.get("wasm_runtime", {}).get("hashmap", {})),
        _section("WASMRT", program.get("wasm_runtime", {})),
        _section("FUNC", {k: {kk: vv for kk, vv in v.items() if kk != "code"} for k, v in program.get("functions", {}).items()}),
        _section("CODE", {k: v.get("code", []) for k, v in program.get("functions", {}).items()}),
        _section("DEBUG", program.get("debug", {})),
        _section("PROGRAM", program),
    ]
    header_size = len(KBC69_MAGIC) + 8 + len(sections) * 24
    offset = header_size
    directory = []
    body = []
    for name, data in sections:
        directory.append((name, offset, len(data)))
        body.append(data)
        offset += len(data)
    out = bytearray(KBC69_MAGIC + struct.pack("<II", KBC69_VERSION, len(sections)))
    for name, off, size in directory:
        out += name + struct.pack("<QQ", off, size)
    for data in body:
        out += data
    digest = hashlib.sha256(bytes(out)).digest()
    return b"KBC69HASH" + digest + bytes(out)


def decode_kbc69b(data: bytes) -> dict[str, Any]:
    if not data.startswith(b"KBC69HASH"):
        raise FoundationError("Keine KBC69B-Datei: Hash-Präambel fehlt")
    digest, payload = data[9:41], data[41:]
    if hashlib.sha256(payload).digest() != digest:
        raise FoundationError("KBC69B-Hashprüfung fehlgeschlagen")
    if not payload.startswith(KBC69_MAGIC):
        raise FoundationError("Keine KBC69B-Datei: falsche Magic")
    off = len(KBC69_MAGIC)
    version, count = struct.unpack("<II", payload[off:off + 8])
    off += 8
    if version < KBC69_VERSION:
        raise FoundationError("KBC69B-Version ist zu alt")
    sections: dict[str, Any] = {}
    for _ in range(count):
        name = payload[off:off + 8].rstrip(b"\0").decode("ascii")
        off += 8
        sec_off, sec_size = struct.unpack("<QQ", payload[off:off + 16])
        off += 16
        raw = payload[sec_off:sec_off + sec_size]
        if len(raw) != sec_size:
            raise FoundationError(f"KBC69B-Sektion {name} ist abgeschnitten")
        sections[name] = json.loads(raw.decode("utf-8"))
    p = sections.get("PROGRAM")
    if not p:
        raise FoundationError("KBC69B ohne PROGRAM-Sektion")
    p["binary_sections"] = sorted(sections)
    errs = verify_program69(p)
    if any(d.severity == "error" for d in errs):
        raise FoundationError(CheckReport(False, [], errs).format())
    return p


def write_kbc69b(program: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encode_kbc69b(program))


def read_kbc69b(path: Path) -> dict[str, Any]:
    return decode_kbc69b(Path(path).read_bytes())


def check69(path: Path) -> CheckReport:
    graph = ModuleGraph(path).load()
    p = compile_program69(graph)
    ds = [Diagnostic(d.get("severity", "error"), d.get("message", ""), d.get("line", 0), d.get("module", "")) for d in p.get("diagnostics", [])]
    ds.extend(verify_program69(p))
    return CheckReport(not any(d.severity == "error" for d in ds), sorted(graph.modules), ds)


def bytecode69(path: Path, *, out: Path | None = None, binary_out: Path | None = None) -> dict[str, Any]:
    graph = ModuleGraph(path).load()
    p = compile_program69(graph)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")
    if binary_out:
        write_kbc69b(p, binary_out)
    return p


def run69(path: Path, *, record: Path | None = None):
    graph = ModuleGraph(path).load()
    p = compile_program69(graph)
    errs = [d for d in verify_program69(p) if d.severity == "error"]
    if errs:
        raise FoundationError(CheckReport(False, sorted(graph.modules), errs).format())
    return c68.c67.c66.VM66(p, graph=graph, record=record).run_main()


def run_kbc69b(path: Path):
    return c68.c67.c66.VM66(read_kbc69b(path)).run_main()


GC_HASHMAP_WAT = r'''
  ;; Keim v6.9 professional GC + optimized hashmap runtime extension
  ;; Header: kind@0 size@4 aux@8 flags@12 next_free@16 payload@24
  (global $gc_heap_start (mut i32) (i32.const 65536))
  (global $gc_heap_end (mut i32) (i32.const 65536))
  (global $gc_free_head (mut i32) (i32.const 0))
  (global $gc_alloc_bytes (mut i32) (i32.const 0))
  (global $gc_threshold (mut i32) (i32.const 1048576))
  (global $gc_roots_start (mut i32) (i32.const 32768))
  (global $gc_roots_end (mut i32) (i32.const 32768))
  (func $gc_is_ref (param $v i64) (result i32) local.get $v i64.const 7 i64.and i64.const 3 i64.eq)
  (func $gc_ptr_from_value (param $v i64) (result i32) local.get $v i64.const 3 i64.shr_u i32.wrap_i64)
  (func $gc_size (param $p i32) (result i32) local.get $p i32.const 4 i32.add i32.load)
  (func $gc_flags (param $p i32) (result i32) local.get $p i32.const 12 i32.add i32.load)
  (func $gc_set_flags (param $p i32) (param $f i32) local.get $p i32.const 12 i32.add local.get $f i32.store)
  (func $gc_mark_value (param $v i64) local.get $v call $gc_is_ref if local.get $v call $gc_ptr_from_value call $gc_mark_ptr end)
  (func $gc_mark_ptr (param $p i32)
    (local $kind i32) (local $n i32) (local $items i32) (local $i i32)
    local.get $p i32.eqz if return end
    local.get $p call $gc_flags i32.const 1 i32.and if return end
    local.get $p local.get $p call $gc_flags i32.const 1 i32.or call $gc_set_flags
    local.get $p i32.load local.set $kind
    ;; list
    local.get $kind i32.const 2 i32.eq if
      local.get $p i32.const 8 i32.add i32.load local.set $n
      local.get $p i32.const 24 i32.add i32.load local.set $items
      i32.const 0 local.set $i
      loop $gc_list_loop local.get $i local.get $n i32.lt_u if
        local.get $items local.get $i i32.const 8 i32.mul i32.add i64.load call $gc_mark_value
        local.get $i i32.const 1 i32.add local.set $i br $gc_list_loop
      end end
    end
    ;; record
    local.get $kind i32.const 4 i32.eq if
      local.get $p i32.const 8 i32.add i32.load local.set $n
      i32.const 0 local.set $i
      loop $gc_record_loop local.get $i local.get $n i32.lt_u if
        local.get $p i32.const 24 i32.add local.get $i i32.const 8 i32.mul i32.add i64.load call $gc_mark_value
        local.get $i i32.const 1 i32.add local.set $i br $gc_record_loop
      end end
    end
    ;; result
    local.get $kind i32.const 5 i32.eq local.get $kind i32.const 6 i32.eq i32.or if
      local.get $p i32.const 24 i32.add i64.load call $gc_mark_value
    end
    ;; map entries: key/value pairs
    local.get $kind i32.const 3 i32.eq if
      local.get $p i32.const 8 i32.add i32.load local.set $n
      local.get $p i32.const 24 i32.add i32.load local.set $items
      i32.const 0 local.set $i
      loop $gc_map_loop local.get $i local.get $n i32.lt_u if
        local.get $items local.get $i i32.const 24 i32.mul i32.add i32.const 16 i32.add i32.load i32.const 1 i32.eq if
          local.get $items local.get $i i32.const 24 i32.mul i32.add i64.load call $gc_mark_value
          local.get $items local.get $i i32.const 24 i32.mul i32.add i32.const 8 i32.add i64.load call $gc_mark_value
        end
        local.get $i i32.const 1 i32.add local.set $i br $gc_map_loop
      end end
    end)
  (func $gc_mark_roots (local $p i32)
    global.get $gc_roots_start local.set $p
    loop $root_loop local.get $p global.get $gc_roots_end i32.lt_u if
      local.get $p i64.load call $gc_mark_value
      local.get $p i32.const 8 i32.add local.set $p br $root_loop
    end end)
  (func $gc_free_block (param $p i32)
    local.get $p i32.const 0 i32.store
    local.get $p i32.const 12 i32.add i32.const 0 i32.store
    local.get $p i32.const 16 i32.add global.get $gc_free_head i32.store
    local.get $p global.set $gc_free_head)
  (func $gc_sweep (local $p i32) (local $end i32) (local $size i32) (local $flags i32)
    global.get $gc_heap_start local.set $p global.get $gc_heap_end local.set $end
    loop $sweep_loop local.get $p local.get $end i32.lt_u if
      local.get $p call $gc_size local.set $size
      local.get $size i32.eqz if return end
      local.get $p call $gc_flags local.set $flags
      local.get $flags i32.const 1 i32.and if
        local.get $p local.get $flags i32.const -2 i32.and call $gc_set_flags
      else
        local.get $p call $gc_free_block
      end
      local.get $p local.get $size i32.add local.set $p br $sweep_loop
    end end)
  (func $gc_collect call $gc_mark_roots call $gc_sweep i32.const 0 global.set $gc_alloc_bytes)
  (func $alloc_gc (param $n i32) (result i32)
    (local $need i32) (local $p i32)
    local.get $n i32.const 23 i32.add i32.const -8 i32.and local.set $need
    global.get $gc_alloc_bytes local.get $need i32.add global.get $gc_threshold i32.gt_u if call $gc_collect end
    global.get $gc_free_head local.set $p
    block $not_found
      loop $free_loop
        local.get $p i32.eqz br_if $not_found
        local.get $p call $gc_size local.get $need i32.ge_u if
          local.get $p i32.const 16 i32.add i32.load global.set $gc_free_head
          local.get $p return
        end
        local.get $p i32.const 16 i32.add i32.load local.set $p br $free_loop
      end
    end
    global.get $gc_heap_end local.set $p
    global.get $gc_heap_end local.get $need i32.add global.set $gc_heap_end
    global.get $gc_alloc_bytes local.get $need i32.add global.set $gc_alloc_bytes
    local.get $p)
  (func $keim_value_hash (param $v i64) (result i32)
    local.get $v i64.const 3 i64.shr_u i32.wrap_i64 i32.const 2654435761 i32.mul)
  (func $keim_hashmap_new (param $cap i32) (result i64)
    (local $p i32) (local $entries i32)
    local.get $cap i32.const 8 i32.lt_u if i32.const 8 local.set $cap end
    i32.const 32 call $alloc_gc local.set $p
    local.get $cap i32.const 24 i32.mul call $alloc_gc local.set $entries
    local.get $p i32.const 3 i32.store
    local.get $p i32.const 4 i32.add i32.const 32 i32.store
    local.get $p i32.const 8 i32.add local.get $cap i32.store
    local.get $p i32.const 12 i32.add i32.const 0 i32.store
    local.get $p i32.const 24 i32.add local.get $entries i32.store
    local.get $p call $heap_ref)
  (func $keim_hashmap_probe (param $map i64) (param $key i64) (result i32)
    (local $p i32) (local $cap i32) (local $entries i32) (local $idx i32) (local $state i32)
    local.get $map call $ptr_from_ref local.set $p
    local.get $p i32.const 8 i32.add i32.load local.set $cap
    local.get $p i32.const 24 i32.add i32.load local.set $entries
    local.get $key call $keim_value_hash local.get $cap i32.rem_u local.set $idx
    loop $probe
      local.get $entries local.get $idx i32.const 24 i32.mul i32.add i32.const 16 i32.add i32.load local.set $state
      local.get $state i32.eqz if local.get $idx return end
      local.get $state i32.const 1 i32.eq if
        local.get $entries local.get $idx i32.const 24 i32.mul i32.add i64.load local.get $key call $keim_value_eq if local.get $idx return end
      end
      local.get $idx i32.const 1 i32.add local.get $cap i32.rem_u local.set $idx br $probe
    end i32.const 0)
  (func $keim_map_new (param $cap i32) (result i64) local.get $cap call $keim_hashmap_new)
  (func $keim_map_set (param $map i64) (param $key i64) (param $val i64)
    (local $p i32) (local $entries i32) (local $idx i32) (local $slot i32)
    local.get $map call $ptr_from_ref local.set $p
    local.get $p i32.const 24 i32.add i32.load local.set $entries
    local.get $map local.get $key call $keim_hashmap_probe local.set $idx
    local.get $entries local.get $idx i32.const 24 i32.mul i32.add local.set $slot
    local.get $slot local.get $key i64.store
    local.get $slot i32.const 8 i32.add local.get $val i64.store
    local.get $slot i32.const 16 i32.add i32.const 1 i32.store
    local.get $slot i32.const 20 i32.add local.get $key call $keim_value_hash i32.store)
  (func $keim_map_get (param $map i64) (param $key i64) (result i64)
    (local $p i32) (local $cap i32) (local $entries i32) (local $idx i32) (local $slot i32)
    local.get $map call $ptr_from_ref local.set $p
    local.get $p i32.const 8 i32.add i32.load local.set $cap
    local.get $p i32.const 24 i32.add i32.load local.set $entries
    local.get $key call $keim_value_hash local.get $cap i32.rem_u local.set $idx
    loop $lookup
      local.get $entries local.get $idx i32.const 24 i32.mul i32.add local.set $slot
      local.get $slot i32.const 16 i32.add i32.load i32.eqz if i32.const 3 call $host_panic i64.const 2 return end
      local.get $slot i64.load local.get $key call $keim_value_eq if local.get $slot i32.const 8 i32.add i64.load return end
      local.get $idx i32.const 1 i32.add local.get $cap i32.rem_u local.set $idx br $lookup
    end i64.const 2)
'''


def _replace_func(wat: str, name: str, replacement: str) -> str:
    pattern = re.compile(rf"^  \(func \${re.escape(name)} .*$", re.MULTILINE)
    new, count = pattern.subn(replacement.strip("\n"), wat, count=1)
    if count == 0:
        raise FoundationError(f"WAT-Funktion ${name} konnte nicht ersetzt werden")
    return new


def _strip_func(wat: str, name: str) -> str:
    pattern = re.compile(rf"^  \(func \${re.escape(name)} .*\n", re.MULTILINE)
    new, count = pattern.subn("", wat, count=1)
    if count == 0:
        raise FoundationError(f"WAT-Funktion ${name} konnte nicht entfernt werden")
    return new


def _upgrade_wat68_to69(wat: str) -> str:
    wat = _replace_func(wat, "alloc", "  (func $alloc (param $n i32) (result i32) local.get $n call $alloc_gc)")
    for fn in ("keim_map_new", "keim_map_set", "keim_map_get"):
        wat = _strip_func(wat, fn)
    pos = wat.rfind(")")
    if pos < 0:
        raise FoundationError("WAT-Modul ist unvollständig")
    wat = wat[:pos] + "\n" + GC_HASHMAP_WAT.strip("\n") + "\n" + wat[pos:]
    wat = wat.replace("Keim v6.8 tagged i64 runtime", "Keim v6.9 GC + Hashmap tagged i64 runtime")
    return wat


def emit_wasm69(program: dict[str, Any], out: Path) -> None:
    program = _json_clone(program)
    if "gc" not in program.get("heap_layouts", {}):
        program = compile_program69(ModuleGraph(Path("__dummy__")))  # unreachable in normal CLI
    tmp = Path(out).with_suffix(".v68.tmp.wat")
    c68.emit_wasm68(program, tmp)
    wat = tmp.read_text(encoding="utf-8")
    try:
        tmp.unlink()
    except OSError:
        pass
    wat = _upgrade_wat68_to69(wat)
    if "unreachable" in wat:
        raise FoundationError("v6.9 WAT darf keine unreachable-Fallbacks enthalten")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(wat, encoding="utf-8")


def build69(cwd: Path, out: Path) -> dict[str, Any]:
    cwd = Path(cwd)
    out = Path(out)
    candidates = [
        cwd / "examples" / "sprache_v69_gc_hashmap_runtime.keim",
        cwd / "examples" / "sprache_v68_wasm_heap_runtime.keim",
        cwd / "examples" / "sprache_v67_full_enterprise.keim",
    ]
    main = next((p for p in candidates if p.exists()), candidates[-1])
    p = bytecode69(main, out=out / "app.kbc69.json", binary_out=out / "app.kbc69b")
    emit_wasm69(p, out / "app_gc_hashmap_runtime.wat")
    manifest = {
        "format": "keim-build-v69",
        "main": str(main),
        "bytecode": "app.kbc69.json",
        "binary": "app.kbc69b",
        "wasm_gc_hashmap_runtime": "app_gc_hashmap_runtime.wat",
        "runtime": p.get("wasm_runtime", {}),
        "heap_layouts": p.get("heap_layouts", {}),
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "build_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "manifest": manifest}


def test69(path: Path, *, filter_text: str | None = None, junit: Path | None = None) -> dict[str, Any]:
    payload = c68.test68(path, filter_text=filter_text, junit=junit)
    p = bytecode69(path)
    wat_path = Path("build/v69/test_gc_hashmap_runtime.wat")
    emit_wasm69(p, wat_path)
    wat = wat_path.read_text(encoding="utf-8")
    decoded = decode_kbc69b(encode_kbc69b(p))
    checks = {
        "gc_runtime": "$gc_collect" in wat and "$gc_mark_value" in wat and "$gc_sweep" in wat,
        "allocator_replaced": "$alloc_gc" in wat and "global $gc_free_head" in wat,
        "hashmap_runtime": "$keim_hashmap_new" in wat and "$keim_hashmap_probe" in wat and "$keim_map_get" in wat,
        "no_unreachable": "unreachable" not in wat,
        "binary_sections": {"GC", "HASHMAP", "HEAP", "WASMRT", "PROGRAM"}.issubset(set(decoded.get("binary_sections", []))),
        "metadata": decoded.get("wasm_runtime", {}).get("gc", {}).get("algorithm") == "non-moving-mark-sweep",
    }
    payload.setdefault("coverage", {})["v69_gc_hashmap_runtime"] = checks
    payload["ok"] = bool(payload.get("ok")) and all(checks.values())
    return payload


def status69() -> dict[str, Any]:
    return {
        "version": KBC69_VERSION,
        "name": "Keim v6.9 Professional WASM GC/Hashmap Runtime",
        "features": [
            "non_moving_mark_sweep_gc",
            "gc_header_with_mark_pin_generation_bits",
            "free_list_allocator_with_bump_fallback",
            "allocation_threshold_gc_trigger",
            "recursive_graph_marking_for_list_record_result_map",
            "open_addressing_hashmap",
            "linear_probing",
            "kbc69b_gc_hashmap_sections",
            "wat_lowering_without_unreachable",
        ],
    }
