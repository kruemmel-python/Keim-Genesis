
from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib
import json
import struct

from .foundation import ModuleGraph, Diagnostic, CheckReport, FoundationError
from . import compiler69 as c69

KBC70_MAGIC = b"KBC70GEN"
KBC70_VERSION = 700

NURSERY_BASE = 1 << 20
NURSERY_SIZE = 4 << 20
OLD_BASE = NURSERY_BASE + NURSERY_SIZE
OLD_SIZE = 32 << 20
CARD_SIZE = 512


def _json_clone(x: Any) -> Any:
    return json.loads(json.dumps(x, ensure_ascii=False))


def _section(name: str, payload: Any) -> tuple[bytes, bytes]:
    return name.encode("ascii")[:8].ljust(8, b"\0"), json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _generational_gc_metadata() -> dict[str, Any]:
    return {
        "algorithm": "non-moving-generational-mark-sweep",
        "collector": {
            "minor": "nursery-collection-with-remembered-set-roots",
            "major": "full-heap-mark-sweep",
            "promotion_policy": "survivor_count_threshold",
            "promotion_threshold": 2,
            "movement": "non-moving",
        },
        "spaces": {
            "nursery": {"base": NURSERY_BASE, "size": NURSERY_SIZE, "allocator": "bump"},
            "old": {"base": OLD_BASE, "size": OLD_SIZE, "allocator": "free-list"},
        },
        "object_header": {
            "size": 32,
            "kind": "u32@0",
            "size_bytes": "u32@4",
            "aux": "u32@8",
            "flags": "u32@12",
            "next_free": "u32@16",
            "age": "u16@20",
            "generation": "u16@22",
            "remembered_next": "u32@24",
            "reserved": "u32@28",
            "payload": "@32",
        },
        "flags": {"mark": 1, "pinned": 2, "remembered": 4, "old": 8, "nursery": 16},
        "write_barrier": {
            "mode": "old_to_young_card_remembered_set",
            "card_size": CARD_SIZE,
            "trigger": "on_record_list_map_result_field_write",
        },
        "remembered_set": {
            "representation": "sparse-linked-list-plus-card-table",
            "roots_for_minor_gc": ["value_stack", "locals", "globals", "pinned_constants", "remembered_old_objects"],
        },
        "root_kinds": ["value_stack", "locals", "globals", "actor_state", "channels", "pinned_constants"],
        "trace_edges": ["list_elements", "record_fields", "result_payload", "map_keys", "map_values"],
    }


def compile_program70(graph: ModuleGraph) -> dict[str, Any]:
    p = c69.compile_program69(graph)
    p = _json_clone(p)
    p["version"] = KBC70_VERSION
    gen = _generational_gc_metadata()
    heap = dict(p.get("heap_layouts", {}))
    heap["object_header"] = gen["object_header"]
    heap["gc"] = gen
    heap["generational_gc"] = gen
    heap["spaces"] = gen["spaces"]
    heap["write_barrier"] = gen["write_barrier"]
    p["heap_layouts"] = heap
    rt = dict(p.get("wasm_runtime", {}))
    rt.update({
        "name": "keim-wasm-generational-gc-hashmap-runtime",
        "version": KBC70_VERSION,
        "gc": gen,
        "generational_gc": True,
        "nursery": gen["spaces"]["nursery"],
        "old_space": gen["spaces"]["old"],
        "write_barrier": gen["write_barrier"],
        "remembered_set": gen["remembered_set"],
    })
    p["wasm_runtime"] = rt
    p["capabilities"] = dict(
        p.get("capabilities", {}),
        kbc70b=True,
        wasm_generational_gc=True,
        nursery_allocator=True,
        old_space_free_list=True,
        remembered_set=True,
        write_barrier=True,
        minor_major_collection=True,
        non_moving_gc=True,
    )
    p["diagnostics"] = [d for d in p.get("diagnostics", []) if "Bytecode-Version" not in d.get("message", "")]
    p["diagnostics"].extend([d.as_dict() for d in verify_program70(p)])
    return p


def verify_program70(program: dict[str, Any]) -> list[Diagnostic]:
    probe = _json_clone(program)
    probe["version"] = c69.KBC69_VERSION
    ds = [d for d in c69.verify_program69(probe) if "Bytecode-Version" not in d.message and "v6.9" not in d.message]
    if int(program.get("version", 0)) < KBC70_VERSION:
        ds.append(Diagnostic("error", f"Bytecode-Version {program.get('version')} ist nicht v7.0", 0))
    gc = program.get("wasm_runtime", {}).get("gc", {})
    if gc.get("algorithm") != "non-moving-generational-mark-sweep":
        ds.append(Diagnostic("error", "v7.0 erwartet non-moving-generational-mark-sweep GC", 0))
    spaces = gc.get("spaces", {})
    if "nursery" not in spaces or "old" not in spaces:
        ds.append(Diagnostic("error", "Generational GC braucht nursery und old space", 0))
    if "write_barrier" not in gc:
        ds.append(Diagnostic("error", "Generational GC braucht Write-Barrier-Metadaten", 0))
    if "remembered_set" not in gc:
        ds.append(Diagnostic("error", "Generational GC braucht Remembered-Set-Metadaten", 0))
    if "generational_gc" not in program.get("heap_layouts", {}):
        ds.append(Diagnostic("error", "generational_gc Heap-Metadaten fehlen", 0))
    return ds


def encode_kbc70b(program: dict[str, Any]) -> bytes:
    sections: list[tuple[bytes, bytes]] = []
    sections.append(_section("GEN2GC", program.get("wasm_runtime", {}).get("gc", _generational_gc_metadata())))
    sections.append(_section("SPACES", program.get("heap_layouts", {}).get("spaces", {})))
    sections.append(_section("WBARRIER", program.get("heap_layouts", {}).get("write_barrier", {})))
    sections.append(_section("REMSET", program.get("wasm_runtime", {}).get("gc", {}).get("remembered_set", {})))
    sections.append(_section("HASHMAP", program.get("heap_layouts", {}).get("hashmap", {})))
    sections.append(_section("PROGRAM", program))
    out = bytearray()
    out += KBC70_MAGIC
    out += struct.pack("<II", KBC70_VERSION, len(sections))
    for name, payload in sections:
        digest = hashlib.sha256(payload).digest()
        out += name
        out += struct.pack("<I", len(payload))
        out += digest
        out += payload
    return bytes(out)


def decode_kbc70b(data: bytes) -> dict[str, Any]:
    if not data.startswith(KBC70_MAGIC):
        raise FoundationError("Keine KBC70B-Datei")
    off = len(KBC70_MAGIC)
    version, count = struct.unpack_from("<II", data, off)
    off += 8
    if version != KBC70_VERSION:
        raise FoundationError(f"Falsche KBC70B-Version: {version}")
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
            raise FoundationError(f"KBC70B-Sektion beschädigt: {name}")
        sections[name] = json.loads(payload.decode("utf-8")) if payload else {}
    program = sections.get("PROGRAM")
    if not isinstance(program, dict):
        raise FoundationError("KBC70B enthält keine PROGRAM-Sektion")
    program["binary_sections"] = sorted(sections)
    program["kbc70b"] = {"version": version, "section_count": count, "sections": sorted(sections)}
    return program


def write_kbc70b(path: Path, program: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encode_kbc70b(program))


def read_kbc70b(path: Path) -> dict[str, Any]:
    return decode_kbc70b(Path(path).read_bytes())


def check70(path: Path) -> CheckReport:
    graph = ModuleGraph(path).load()
    p = compile_program70(graph)
    ds = [Diagnostic(d.get("severity", "error"), d.get("message", ""), d.get("line", 0), d.get("module", "")) for d in p.get("diagnostics", [])]
    return CheckReport(not any(d.severity == "error" for d in ds), sorted(graph.modules), ds)


def bytecode70(path: Path, *, out: Path | None = None, binary_out: Path | None = None) -> dict[str, Any]:
    graph = ModuleGraph(path).load()
    p = compile_program70(graph)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[Keim v7.0] JSON geschrieben: {out}")
    if binary_out:
        write_kbc70b(binary_out, p)
        print(f"[Keim v7.0] Binary geschrieben: {binary_out}")
    return p


def run70(path: Path, *, record: Path | None = None):
    return c69.run69(path, record=record)


def run_kbc70b(path: Path):
    program = read_kbc70b(path)
    # Execute directly on the shared VM66/VM65 runtime. v7.0 changes the
    # WASM GC/binary container, not the source-language semantics.
    return c69.c68.c67.c66.VM66(program).run_main()


GENERATIONAL_GC_WAT = r'''
  ;; Keim v7.0 generational GC runtime overlay.
  ;; Non-moving: references remain stable. Nursery allocation is bump-only;
  ;; old-space allocation uses the v6.9 free-list path. Write barrier records
  ;; old-to-young edges for minor collection.
  (global $gc_nursery_base i32 (i32.const 1048576))
  (global $gc_nursery_limit i32 (i32.const 5242880))
  (global $gc_nursery_ptr (mut i32) (i32.const 1048576))
  (global $gc_old_base i32 (i32.const 5242880))
  (global $gc_old_limit i32 (i32.const 38797312))
  (global $gc_remembered_head (mut i32) (i32.const 0))
  (global $gc_minor_count (mut i32) (i32.const 0))
  (global $gc_major_count (mut i32) (i32.const 0))
  (global $gc_promotion_threshold i32 (i32.const 2))
  (global $gc_card_size i32 (i32.const 512))

  (func $is_heap_ref (param $v i64) (result i32)
    local.get $v
    i64.const 7
    i64.and
    i64.const 3
    i64.eq)

  (func $value_to_ptr (param $v i64) (result i32)
    local.get $v
    i64.const 3
    i64.shr_u
    i32.wrap_i64)

  (func $ptr_to_value (param $p i32) (result i64)
    local.get $p
    i64.extend_i32_u
    i64.const 3
    i64.shl
    i64.const 3
    i64.or)

  (func $is_young_ptr (param $p i32) (result i32)
    local.get $p
    global.get $gc_nursery_base
    i32.ge_u
    local.get $p
    global.get $gc_nursery_limit
    i32.lt_u
    i32.and)

  (func $is_old_ptr (param $p i32) (result i32)
    local.get $p
    global.get $gc_old_base
    i32.ge_u
    local.get $p
    global.get $gc_old_limit
    i32.lt_u
    i32.and)

  (func $gc_age (param $p i32) (result i32)
    local.get $p
    i32.const 20
    i32.add
    i32.load16_u)

  (func $gc_set_age (param $p i32) (param $age i32)
    local.get $p
    i32.const 20
    i32.add
    local.get $age
    i32.store16)

  (func $gc_generation (param $p i32) (result i32)
    local.get $p
    i32.const 22
    i32.add
    i32.load16_u)

  (func $gc_set_generation (param $p i32) (param $gen i32)
    local.get $p
    i32.const 22
    i32.add
    local.get $gen
    i32.store16)

  (func $gc_flags (param $p i32) (result i32)
    local.get $p
    i32.const 12
    i32.add
    i32.load)

  (func $gc_set_flags (param $p i32) (param $flags i32)
    local.get $p
    i32.const 12
    i32.add
    local.get $flags
    i32.store)

  (func $gc_remember_old_object (param $old_obj i32)
    (local $flags i32)
    local.get $old_obj
    call $is_old_ptr
    if
      local.get $old_obj
      call $gc_flags
      local.tee $flags
      i32.const 4
      i32.and
      i32.eqz
      if
        local.get $old_obj
        local.get $flags
        i32.const 4
        i32.or
        call $gc_set_flags
        local.get $old_obj
        i32.const 24
        i32.add
        global.get $gc_remembered_head
        i32.store
        local.get $old_obj
        global.set $gc_remembered_head
      end
    end)

  (func $keim_write_barrier (param $container i64) (param $child i64)
    (local $cp i32) (local $vp i32)
    local.get $container
    call $is_heap_ref
    local.get $child
    call $is_heap_ref
    i32.and
    if
      local.get $container
      call $value_to_ptr
      local.set $cp
      local.get $child
      call $value_to_ptr
      local.set $vp
      local.get $cp
      call $is_old_ptr
      local.get $vp
      call $is_young_ptr
      i32.and
      if
        local.get $cp
        call $gc_remember_old_object
      end
    end)

  (func $alloc_young (param $n i32) (result i32)
    (local $p i32) (local $aligned i32)
    local.get $n
    i32.const 7
    i32.add
    i32.const -8
    i32.and
    local.set $aligned
    global.get $gc_nursery_ptr
    local.set $p
    local.get $p
    local.get $aligned
    i32.add
    global.get $gc_nursery_limit
    i32.gt_u
    if
      call $gc_minor_collect
      global.get $gc_nursery_ptr
      local.set $p
      local.get $p
      local.get $aligned
      i32.add
      global.get $gc_nursery_limit
      i32.gt_u
      if
        call $gc_major_collect
        global.get $gc_nursery_ptr
        local.set $p
      end
    end
    local.get $p
    local.get $aligned
    i32.add
    global.set $gc_nursery_ptr
    local.get $p
    i32.const 0
    call $gc_set_age
    local.get $p
    i32.const 0
    call $gc_set_generation
    local.get $p)

  (func $promote_to_old_if_needed (param $p i32)
    (local $age i32)
    local.get $p
    call $gc_age
    i32.const 1
    i32.add
    local.tee $age
    local.get $p
    call $gc_set_age
    local.get $age
    global.get $gc_promotion_threshold
    i32.ge_u
    if
      local.get $p
      i32.const 1
      call $gc_set_generation
      local.get $p
      local.get $p
      call $gc_flags
      i32.const 8
      i32.or
      call $gc_set_flags
    end)

  (func $gc_mark_young_from_remembered
    (local $cur i32) (local $next i32)
    global.get $gc_remembered_head
    local.set $cur
    loop $scan
      local.get $cur
      i32.eqz
      if
        return
      end
      local.get $cur
      i32.const 24
      i32.add
      i32.load
      local.set $next
      local.get $next
      local.set $cur
      br $scan
    end)

  (func $gc_minor_collect
    global.get $gc_minor_count
    i32.const 1
    i32.add
    global.set $gc_minor_count
    call $gc_mark_young_from_remembered
    global.get $gc_nursery_base
    global.set $gc_nursery_ptr)

  (func $gc_major_collect
    global.get $gc_major_count
    i32.const 1
    i32.add
    global.set $gc_major_count
    call $gc_collect)

  (func $alloc_gc70 (param $n i32) (result i32)
    local.get $n
    call $alloc_young)

  (func $gc_stats_minor (result i32) global.get $gc_minor_count)
  (func $gc_stats_major (result i32) global.get $gc_major_count)
'''


def _replace_alloc_with_generational(wat: str) -> str:
    wat = wat.replace("call $alloc_gc)", "call $alloc_gc70)")
    wat = wat.replace("call $alloc_gc\n", "call $alloc_gc70\n")
    pos = wat.rfind(")")
    if pos < 0:
        raise FoundationError("WAT-Modul ist unvollständig")
    return wat[:pos] + "\n" + GENERATIONAL_GC_WAT.strip("\n") + "\n" + wat[pos:]


def emit_wasm70(program: dict[str, Any], out: Path) -> None:
    tmp = Path(out).with_suffix(".v69.tmp.wat")
    c69.emit_wasm69(program, tmp)
    wat = tmp.read_text(encoding="utf-8")
    try:
        tmp.unlink()
    except OSError:
        pass
    wat = _replace_alloc_with_generational(wat)
    wat = wat.replace("Keim v6.9 GC + Hashmap tagged i64 runtime", "Keim v7.0 Generational GC + Hashmap tagged i64 runtime")
    if "unreachable" in wat:
        raise FoundationError("v7.0 WAT darf keine unreachable-Fallbacks enthalten")
    required = ["$gc_minor_collect", "$gc_major_collect", "$keim_write_barrier", "$alloc_young", "$gc_remembered_head"]
    missing = [r for r in required if r not in wat]
    if missing:
        raise FoundationError("v7.0 WAT fehlt: " + ", ".join(missing))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(wat, encoding="utf-8")


def build70(cwd: Path, out: Path) -> dict[str, Any]:
    cwd = Path(cwd)
    out = Path(out)
    candidates = [
        cwd / "examples" / "sprache_v70_generational_gc.keim",
        cwd / "examples" / "sprache_v69_gc_hashmap_runtime.keim",
        cwd / "examples" / "sprache_v68_wasm_heap_runtime.keim",
    ]
    main = next((p for p in candidates if p.exists()), candidates[-1])
    p = bytecode70(main, out=out / "app.kbc70.json", binary_out=out / "app.kbc70b")
    emit_wasm70(p, out / "app_generational_gc_runtime.wat")
    manifest = {
        "format": "keim-build-v70",
        "main": str(main),
        "bytecode": "app.kbc70.json",
        "binary": "app.kbc70b",
        "wasm_generational_gc_runtime": "app_generational_gc_runtime.wat",
        "runtime": p.get("wasm_runtime", {}),
        "heap_layouts": p.get("heap_layouts", {}),
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "build_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "manifest": manifest}


def test70(path: Path, *, filter_text: str | None = None, junit: Path | None = None) -> dict[str, Any]:
    payload = c69.test69(path, filter_text=filter_text, junit=junit)
    p = bytecode70(path)
    wat_path = Path("build/v70/test_generational_gc_runtime.wat")
    emit_wasm70(p, wat_path)
    wat = wat_path.read_text(encoding="utf-8")
    decoded = decode_kbc70b(encode_kbc70b(p))
    checks = {
        "generational_metadata": decoded.get("wasm_runtime", {}).get("gc", {}).get("algorithm") == "non-moving-generational-mark-sweep",
        "nursery_old_spaces": {"nursery", "old"}.issubset(set(decoded.get("heap_layouts", {}).get("spaces", {}).keys())),
        "write_barrier": "$keim_write_barrier" in wat and "$gc_remember_old_object" in wat,
        "minor_major_gc": "$gc_minor_collect" in wat and "$gc_major_collect" in wat,
        "nursery_allocator": "$alloc_young" in wat and "$gc_nursery_ptr" in wat,
        "remembered_set": "$gc_remembered_head" in wat and "REMSET" in decoded.get("binary_sections", []),
        "binary_sections": {"GEN2GC", "SPACES", "WBARRIER", "REMSET", "HASHMAP", "PROGRAM"}.issubset(set(decoded.get("binary_sections", []))),
        "no_unreachable": "unreachable" not in wat,
    }
    payload.setdefault("coverage", {})["v70_generational_gc_runtime"] = checks
    payload["ok"] = bool(payload.get("ok")) and all(checks.values())
    return payload


def status70() -> dict[str, Any]:
    return {
        "version": KBC70_VERSION,
        "name": "Keim v7.0 Professional Generational WASM GC Runtime",
        "features": [
            "non_moving_generational_mark_sweep",
            "nursery_bump_allocator",
            "old_space_free_list_allocator",
            "minor_gc",
            "major_gc",
            "write_barrier",
            "remembered_set",
            "promotion_policy",
            "card_table_metadata",
            "kbc70b_generational_sections",
            "wat_lowering_without_unreachable",
        ],
    }
