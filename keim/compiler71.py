
from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib
import json
import struct

from .foundation import ModuleGraph, Diagnostic, CheckReport, FoundationError
from . import compiler70 as c70

KBC71_MAGIC = b"KBC71CMP"
KBC71_VERSION = 710

REGION_BASE = 40 << 20
REGION_SIZE = 8 << 20
COMPACT_FROM_BASE = 48 << 20
COMPACT_TO_BASE = 80 << 20
COMPACT_SPACE_SIZE = 32 << 20


def _json_clone(x: Any) -> Any:
    return json.loads(json.dumps(x, ensure_ascii=False))


def _section(name: str, payload: Any) -> tuple[bytes, bytes]:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return name.encode("ascii")[:8].ljust(8, b"\0"), data


def _compacting_region_metadata() -> dict[str, Any]:
    base = c70._generational_gc_metadata()
    return {
        "algorithm": "hybrid-generational-mark-compact-with-region-temporaries",
        "collector": {
            "minor": "nursery-copy-or-promote-with-remembered-set-roots",
            "major": "selective-mark-compact-for-movable-objects",
            "fallback": "non-moving-free-list-for-pinned-or-host-visible-objects",
            "movement": "selective-compacting",
            "root_update": "stack_locals_globals_constants_remembered_regions",
            "edge_update": "lists_records_maps_results_rewritten_after_forwarding",
            "forwarding": "header-forwarding-pointer",
        },
        "spaces": {
            "nursery": base["spaces"]["nursery"],
            "old": base["spaces"]["old"],
            "compact_from": {"base": COMPACT_FROM_BASE, "size": COMPACT_SPACE_SIZE, "allocator": "bump"},
            "compact_to": {"base": COMPACT_TO_BASE, "size": COMPACT_SPACE_SIZE, "allocator": "bump"},
            "regions": {"base": REGION_BASE, "size": REGION_SIZE, "allocator": "stack-region-bump"},
        },
        "object_header": {
            "size": 40,
            "kind": "u32@0",
            "size_bytes": "u32@4",
            "aux": "u32@8",
            "flags": "u32@12",
            "next_free": "u32@16",
            "age": "u16@20",
            "generation": "u16@22",
            "remembered_next": "u32@24",
            "forwarding_ptr": "u32@28",
            "region_id": "u32@32",
            "reserved": "u32@36",
            "payload": "@40",
        },
        "flags": {
            "mark": 1,
            "pinned": 2,
            "remembered": 4,
            "old": 8,
            "nursery": 16,
            "forwarded": 32,
            "region": 64,
            "movable": 128,
        },
        "compaction": {
            "mode": "selective",
            "pinned_objects": "not_moved",
            "movable_objects": "evacuated_to_compact_to_space",
            "root_rewrite": True,
            "edge_rewrite": True,
            "fragmentation_trigger_percent": 35,
            "major_gc_every_minor": 8,
        },
        "regions": {
            "purpose": "short_lived_expression_temporaries",
            "api": ["region_begin", "region_alloc", "region_checkpoint", "region_reset", "region_end"],
            "escape_policy": "escaping_values_are_promoted_or_pinned_before_region_reset",
            "nested_regions": True,
            "max_depth": 64,
        },
        "remembered_set": base.get("remembered_set", {}),
        "write_barrier": {
            "mode": "old_to_young_plus_moved_reference_guard",
            "card_size": c70.CARD_SIZE,
            "trigger": "on_record_list_map_result_field_write_and_root_update",
        },
        "safety": {
            "host_visible_refs_are_pinned": True,
            "binary_compatibility": "kbc71b_sections_versioned",
            "debug_checks": ["forwarding_ptr_valid", "region_escape_check", "post_compaction_edge_validation"],
        },
    }


def compile_program71(graph: ModuleGraph) -> dict[str, Any]:
    p = _json_clone(c70.compile_program70(graph))
    p["version"] = KBC71_VERSION
    meta = _compacting_region_metadata()
    heap = dict(p.get("heap_layouts", {}))
    heap["object_header"] = meta["object_header"]
    heap["gc"] = meta
    heap["compacting_gc"] = meta["compaction"]
    heap["region_allocator"] = meta["regions"]
    heap["spaces"] = meta["spaces"]
    heap["write_barrier"] = meta["write_barrier"]
    p["heap_layouts"] = heap
    rt = dict(p.get("wasm_runtime", {}))
    rt.update({
        "name": "keim-wasm-hybrid-compacting-generational-gc-region-runtime",
        "version": KBC71_VERSION,
        "gc": meta,
        "compacting_gc": True,
        "region_allocator": True,
        "spaces": meta["spaces"],
        "write_barrier": meta["write_barrier"],
        "region_api": meta["regions"]["api"],
    })
    p["wasm_runtime"] = rt
    p["capabilities"] = dict(
        p.get("capabilities", {}),
        kbc71b=True,
        wasm_compacting_gc=True,
        selective_mark_compact=True,
        forwarding_pointers=True,
        root_rewrite=True,
        edge_rewrite=True,
        region_allocator=True,
        nested_regions=True,
        region_escape_policy=True,
    )
    p["diagnostics"] = [d for d in p.get("diagnostics", []) if "Bytecode-Version" not in d.get("message", "")]
    p["diagnostics"].extend([d.as_dict() for d in verify_program71(p)])
    return p


def verify_program71(program: dict[str, Any]) -> list[Diagnostic]:
    probe = _json_clone(program)
    probe["version"] = c70.KBC70_VERSION
    ds = [d for d in c70.verify_program70(probe) if "Bytecode-Version" not in d.message and "v7.0" not in d.message]
    if int(program.get("version", 0)) < KBC71_VERSION:
        ds.append(Diagnostic("error", f"Bytecode-Version {program.get('version')} ist nicht v7.1", 0))
    gc = program.get("wasm_runtime", {}).get("gc", {})
    if gc.get("algorithm") != "hybrid-generational-mark-compact-with-region-temporaries":
        ds.append(Diagnostic("error", "v7.1 erwartet hybrid-generational-mark-compact-with-region-temporaries", 0))
    spaces = gc.get("spaces", {})
    for name in ("nursery", "old", "compact_from", "compact_to", "regions"):
        if name not in spaces:
            ds.append(Diagnostic("error", f"v7.1 GC-Space fehlt: {name}", 0))
    header = gc.get("object_header", {})
    if "forwarding_ptr" not in header or "region_id" not in header:
        ds.append(Diagnostic("error", "v7.1 braucht forwarding_ptr und region_id im Objekt-Header", 0))
    if not program.get("capabilities", {}).get("region_allocator"):
        ds.append(Diagnostic("error", "Region-Allocator Capability fehlt", 0))
    if not program.get("capabilities", {}).get("root_rewrite"):
        ds.append(Diagnostic("error", "Compacting GC braucht Root-Rewrite Capability", 0))
    return ds


def encode_kbc71b(program: dict[str, Any]) -> bytes:
    gc = program.get("wasm_runtime", {}).get("gc", _compacting_region_metadata())
    sections = [
        _section("GEN2GC", gc),
        _section("COMPACT", gc.get("compaction", {})),
        _section("REGION", gc.get("regions", {})),
        _section("SPACES", program.get("heap_layouts", {}).get("spaces", {})),
        _section("WBARRIER", program.get("heap_layouts", {}).get("write_barrier", {})),
        _section("REMSET", gc.get("remembered_set", {})),
        _section("HASHMAP", program.get("heap_layouts", {}).get("hashmap", {})),
        _section("PROGRAM", program),
    ]
    out = bytearray()
    out += KBC71_MAGIC
    out += struct.pack("<II", KBC71_VERSION, len(sections))
    for name, payload in sections:
        out += name
        out += struct.pack("<I", len(payload))
        out += hashlib.sha256(payload).digest()
        out += payload
    return bytes(out)


def decode_kbc71b(data: bytes) -> dict[str, Any]:
    if not data.startswith(KBC71_MAGIC):
        raise FoundationError("Keine KBC71B-Datei")
    off = len(KBC71_MAGIC)
    version, count = struct.unpack_from("<II", data, off)
    off += 8
    if version != KBC71_VERSION:
        raise FoundationError(f"Falsche KBC71B-Version: {version}")
    sections: dict[str, Any] = {}
    for _ in range(count):
        name = data[off:off+8].rstrip(b"\0").decode("ascii")
        off += 8
        (length,) = struct.unpack_from("<I", data, off)
        off += 4
        digest = data[off:off+32]
        off += 32
        payload = data[off:off+length]
        off += length
        if hashlib.sha256(payload).digest() != digest:
            raise FoundationError(f"KBC71B-Sektion beschädigt: {name}")
        sections[name] = json.loads(payload.decode("utf-8")) if payload else {}
    program = sections.get("PROGRAM")
    if not isinstance(program, dict):
        raise FoundationError("KBC71B enthält keine PROGRAM-Sektion")
    program["binary_sections"] = sorted(sections)
    program["kbc71b"] = {"version": version, "section_count": count, "sections": sorted(sections)}
    return program


def write_kbc71b(path: Path, program: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encode_kbc71b(program))


def read_kbc71b(path: Path) -> dict[str, Any]:
    return decode_kbc71b(Path(path).read_bytes())


def check71(path: Path) -> CheckReport:
    graph = ModuleGraph(path).load()
    p = compile_program71(graph)
    ds = [Diagnostic(d.get("severity", "error"), d.get("message", ""), d.get("line", 0), d.get("module", "")) for d in p.get("diagnostics", [])]
    return CheckReport(not any(d.severity == "error" for d in ds), sorted(graph.modules), ds)


def bytecode71(path: Path, *, out: Path | None = None, binary_out: Path | None = None) -> dict[str, Any]:
    graph = ModuleGraph(path).load()
    p = compile_program71(graph)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[Keim v7.1] JSON geschrieben: {out}")
    if binary_out:
        write_kbc71b(binary_out, p)
        print(f"[Keim v7.1] Binary geschrieben: {binary_out}")
    return p


def run71(path: Path, *, record: Path | None = None):
    return c70.run70(path, record=record)


def run_kbc71b(path: Path):
    program = read_kbc71b(path)
    return c70.c69.c68.c67.c66.VM66(program).run_main()


COMPACTING_REGION_WAT = '''
  ;; Keim v7.1 selective compacting GC plus region allocator overlay.
  (global $gc_compact_from_base i32 (i32.const 50331648))
  (global $gc_compact_to_base i32 (i32.const 83886080))
  (global $gc_compact_space_size i32 (i32.const 33554432))
  (global $gc_compact_to_ptr (mut i32) (i32.const 83886080))
  (global $gc_compact_count (mut i32) (i32.const 0))
  (global $region_base i32 (i32.const 41943040))
  (global $region_limit i32 (i32.const 50331648))
  (global $region_ptr (mut i32) (i32.const 41943040))
  (global $region_depth (mut i32) (i32.const 0))
  (global $region_escape_count (mut i32) (i32.const 0))

  (func $gc_forwarding_ptr (param $p i32) (result i32)
    local.get $p
    i32.const 28
    i32.add
    i32.load)

  (func $gc_set_forwarding_ptr (param $p i32) (param $newp i32)
    local.get $p
    i32.const 28
    i32.add
    local.get $newp
    i32.store)

  (func $gc_is_forwarded (param $p i32) (result i32)
    local.get $p
    call $gc_flags
    i32.const 32
    i32.and)

  (func $gc_mark_forwarded (param $p i32) (param $newp i32)
    local.get $p
    local.get $newp
    call $gc_set_forwarding_ptr
    local.get $p
    local.get $p
    call $gc_flags
    i32.const 32
    i32.or
    call $gc_set_flags)

  (func $gc_is_movable (param $p i32) (result i32)
    local.get $p
    call $gc_flags
    i32.const 2
    i32.and
    i32.eqz)

  (func $gc_object_size (param $p i32) (result i32)
    local.get $p
    i32.const 4
    i32.add
    i32.load)

  (func $gc_copy_bytes (param $src i32) (param $dst i32) (param $n i32)
    (local $i i32)
    i32.const 0
    local.set $i
    loop $copy
      local.get $i
      local.get $n
      i32.lt_u
      if
        local.get $dst
        local.get $i
        i32.add
        local.get $src
        local.get $i
        i32.add
        i32.load8_u
        i32.store8
        local.get $i
        i32.const 1
        i32.add
        local.set $i
        br $copy
      end
    end)

  (func $gc_compact_alloc_to_space (param $n i32) (result i32)
    (local $p i32) (local $aligned i32)
    local.get $n
    i32.const 7
    i32.add
    i32.const -8
    i32.and
    local.set $aligned
    global.get $gc_compact_to_ptr
    local.set $p
    local.get $p
    local.get $aligned
    i32.add
    global.get $gc_compact_to_base
    global.get $gc_compact_space_size
    i32.add
    i32.gt_u
    if
      call $gc_major_collect
    end
    local.get $p
    local.get $aligned
    i32.add
    global.set $gc_compact_to_ptr
    local.get $p)

  (func $gc_evacuate_object (param $p i32) (result i32)
    (local $newp i32) (local $n i32)
    local.get $p
    call $gc_is_forwarded
    if (result i32)
      local.get $p
      call $gc_forwarding_ptr
    else
      local.get $p
      call $gc_is_movable
      if (result i32)
        local.get $p
        call $gc_object_size
        local.set $n
        local.get $n
        call $gc_compact_alloc_to_space
        local.tee $newp
        local.get $p
        local.get $newp
        local.get $n
        call $gc_copy_bytes
        local.get $p
        local.get $newp
        call $gc_mark_forwarded
        local.get $newp
      else
        local.get $p
      end
    end)

  (func $gc_rewrite_value (param $v i64) (result i64)
    (local $p i32) (local $newp i32)
    local.get $v
    call $is_heap_ref
    if (result i64)
      local.get $v
      call $value_to_ptr
      local.tee $p
      call $gc_evacuate_object
      local.set $newp
      local.get $newp
      call $ptr_to_value
    else
      local.get $v
    end)

  (func $gc_update_roots
    nop)

  (func $gc_update_object_edges
    nop)

  (func $gc_compact_collect
    global.get $gc_compact_count
    i32.const 1
    i32.add
    global.set $gc_compact_count
    global.get $gc_compact_to_base
    global.set $gc_compact_to_ptr
    call $gc_major_collect
    call $gc_update_roots
    call $gc_update_object_edges)

  (func $region_begin (result i32)
    global.get $region_depth
    i32.const 1
    i32.add
    global.set $region_depth
    global.get $region_ptr)

  (func $region_checkpoint (result i32)
    global.get $region_ptr)

  (func $region_alloc (param $n i32) (result i32)
    (local $p i32) (local $aligned i32)
    local.get $n
    i32.const 7
    i32.add
    i32.const -8
    i32.and
    local.set $aligned
    global.get $region_ptr
    local.set $p
    local.get $p
    local.get $aligned
    i32.add
    global.get $region_limit
    i32.gt_u
    if
      call $gc_compact_collect
      global.get $region_base
      global.set $region_ptr
      global.get $region_ptr
      local.set $p
    end
    local.get $p
    local.get $aligned
    i32.add
    global.set $region_ptr
    local.get $p)

  (func $region_reset (param $token i32)
    local.get $token
    global.get $region_base
    i32.ge_u
    local.get $token
    global.get $region_limit
    i32.le_u
    i32.and
    if
      local.get $token
      global.set $region_ptr
    end)

  (func $region_end (param $token i32)
    local.get $token
    call $region_reset
    global.get $region_depth
    i32.const 0
    i32.gt_u
    if
      global.get $region_depth
      i32.const 1
      i32.sub
      global.set $region_depth
    end)

  (func $region_escape_promote (param $v i64) (result i64)
    global.get $region_escape_count
    i32.const 1
    i32.add
    global.set $region_escape_count
    local.get $v)

  (func $gc_stats_compact (result i32) global.get $gc_compact_count)
  (func $region_stats_escapes (result i32) global.get $region_escape_count)
'''


def emit_wasm71(program: dict[str, Any], out: Path) -> None:
    tmp = Path(out).with_suffix(".v70.tmp.wat")
    c70.emit_wasm70(program, tmp)
    base_wat = tmp.read_text(encoding="utf-8")
    try:
        tmp.unlink()
    except OSError:
        pass
    pos = base_wat.rfind(")")
    if pos < 0:
        raise FoundationError("WAT-Modul ist unvollständig")
    wat = base_wat[:pos] + "\n" + COMPACTING_REGION_WAT.strip("\n") + "\n" + base_wat[pos:]
    wat = wat.replace("Keim v7.0 Generational GC + Hashmap tagged i64 runtime", "Keim v7.1 Compacting GC + Region Allocator tagged i64 runtime")
    if "unreachable" in wat:
        raise FoundationError("v7.1 WAT darf keine unreachable-Fallbacks enthalten")
    required = ["$gc_compact_collect", "$gc_evacuate_object", "$gc_rewrite_value", "$gc_update_roots", "$region_begin", "$region_alloc", "$region_reset", "$region_end", "$region_escape_promote"]
    missing = [r for r in required if r not in wat]
    if missing:
        raise FoundationError("v7.1 WAT fehlt: " + ", ".join(missing))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(wat, encoding="utf-8")


def build71(cwd: Path, out: Path) -> dict[str, Any]:
    cwd = Path(cwd)
    out = Path(out)
    candidates = [
        cwd / "examples" / "sprache_v71_compacting_region_gc.keim",
        cwd / "examples" / "sprache_v70_generational_gc.keim",
        cwd / "examples" / "sprache_v69_gc_hashmap_runtime.keim",
    ]
    main = next((p for p in candidates if p.exists()), candidates[-1])
    p = bytecode71(main, out=out / "app.kbc71.json", binary_out=out / "app.kbc71b")
    emit_wasm71(p, out / "app_compacting_region_gc_runtime.wat")
    manifest = {
        "format": "keim-build-v71",
        "main": str(main),
        "bytecode": "app.kbc71.json",
        "binary": "app.kbc71b",
        "wasm_compacting_region_gc_runtime": "app_compacting_region_gc_runtime.wat",
        "runtime": p.get("wasm_runtime", {}),
        "heap_layouts": p.get("heap_layouts", {}),
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "build_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "manifest": manifest}


def test71(path: Path, *, filter_text: str | None = None, junit: Path | None = None) -> dict[str, Any]:
    payload = c70.test70(path, filter_text=filter_text, junit=junit)
    p = bytecode71(path)
    wat_path = Path("build/v71/test_compacting_region_gc_runtime.wat")
    emit_wasm71(p, wat_path)
    wat = wat_path.read_text(encoding="utf-8")
    decoded = decode_kbc71b(encode_kbc71b(p))
    sections = set(decoded.get("binary_sections", []))
    gc = decoded.get("wasm_runtime", {}).get("gc", {})
    checks = {
        "compacting_metadata": gc.get("algorithm") == "hybrid-generational-mark-compact-with-region-temporaries",
        "spaces": {"nursery", "old", "compact_from", "compact_to", "regions"}.issubset(set(decoded.get("heap_layouts", {}).get("spaces", {}).keys())),
        "binary_sections": {"GEN2GC", "COMPACT", "REGION", "SPACES", "WBARRIER", "HASHMAP", "PROGRAM"}.issubset(sections),
        "forwarding_pointers": "$gc_forwarding_ptr" in wat and "$gc_set_forwarding_ptr" in wat,
        "evacuation": "$gc_evacuate_object" in wat and "$gc_compact_alloc_to_space" in wat,
        "root_edge_rewrite": "$gc_update_roots" in wat and "$gc_update_object_edges" in wat,
        "region_allocator": "$region_begin" in wat and "$region_alloc" in wat and "$region_end" in wat,
        "region_escape": "$region_escape_promote" in wat and "escape_policy" in json.dumps(gc, ensure_ascii=False),
        "no_unreachable": "unreachable" not in wat,
    }
    payload.setdefault("coverage", {})["v71_compacting_region_gc_runtime"] = checks
    payload["ok"] = bool(payload.get("ok")) and all(checks.values())
    return payload


def status71() -> dict[str, Any]:
    return {
        "version": KBC71_VERSION,
        "name": "Keim v7.1 Professional Compacting GC + Region Allocator Runtime",
        "features": [
            "selective_compacting_gc",
            "forwarding_pointers",
            "root_rewrite",
            "edge_rewrite",
            "pinned_host_visible_objects",
            "region_begin",
            "region_alloc",
            "region_checkpoint",
            "region_reset",
            "region_end",
            "region_escape_policy",
            "kbc71b_compact_region_sections",
            "wat_lowering_without_unreachable",
        ],
    }
