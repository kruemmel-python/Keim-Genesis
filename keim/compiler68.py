
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import hashlib
import json
import re
import struct
import time

from .foundation import ModuleGraph, Diagnostic, CheckReport, FoundationError
from . import compiler67 as c67

KBC68_MAGIC = b"KBC68B\x00\x01"
KBC68_VERSION = 680

# Keim WASM value ABI: every runtime value is carried as i64.
# Low 3 bits are the tag; payload is either an integer/bool payload or a heap pointer.
TAG_INT = 0
TAG_BOOL = 1
TAG_NULL = 2
TAG_REF = 3

KIND_TEXT = 1
KIND_LIST = 2
KIND_MAP = 3
KIND_RECORD = 4
KIND_RESULT_OK = 5
KIND_RESULT_ERROR = 6


def _json_clone(x: Any) -> Any:
    return json.loads(json.dumps(x, ensure_ascii=False))


def _section(name: str, payload: Any) -> tuple[bytes, bytes]:
    return name.encode("ascii")[:8].ljust(8, b"\0"), json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sanitize(s: str) -> str:
    return re.sub(r"[^0-9A-Za-z_.$]", "_", s).replace(".", "$")


def _wat_name(fid: str) -> str:
    return "$" + _sanitize(fid)


def _is_int_type(t: str) -> bool:
    return t in {"ganzzahl", "kommazahl", "zahl"} or t.startswith("T")


def _const_type(v: Any) -> str:
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int) and not isinstance(v, bool):
        return "ganzzahl"
    if isinstance(v, float):
        return "kommazahl"
    if isinstance(v, str):
        return "text"
    if v is None:
        return "nichts"
    if isinstance(v, list):
        et = _const_type(v[0]) if v else "beliebig"
        return f"liste<{et}>"
    if isinstance(v, dict) and "ok" in v:
        return "ergebnis<beliebig, beliebig>"
    if isinstance(v, dict):
        return "karte<text, beliebig>"
    return "beliebig"


def _record_layouts(program: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    next_id = 1
    for _mname, mod in sorted(program.get("modules", {}).items()):
        for tname, td in sorted((mod.get("types") or {}).items()):
            fields = td.get("fields") or []
            if fields:
                out[tname] = {
                    "type_id": next_id,
                    "fields": {f.get("name", ""): i for i, f in enumerate(fields)},
                    "field_types": {f.get("name", ""): f.get("type", "beliebig") for f in fields},
                    "field_count": len(fields),
                }
                next_id += 1
    return out


def _heap_layouts(program: dict[str, Any]) -> dict[str, Any]:
    strings: dict[str, int] = {}
    for v in program.get("const_pool", []):
        if isinstance(v, str) and v not in strings:
            strings[v] = len(strings)
    return {
        "value_abi": {
            "carrier": "i64",
            "tag_bits": 3,
            "tags": {"int": TAG_INT, "bool": TAG_BOOL, "null": TAG_NULL, "ref": TAG_REF},
        },
        "object_header": {"kind": "u32@0", "size": "u32@4", "aux": "u32@8", "reserved": "u32@12", "payload": "@16"},
        "kinds": {"text": KIND_TEXT, "list": KIND_LIST, "map": KIND_MAP, "record": KIND_RECORD, "result_ok": KIND_RESULT_OK, "result_error": KIND_RESULT_ERROR},
        "records": _record_layouts(program),
        "strings": strings,
    }


def compile_program68(graph: ModuleGraph) -> dict[str, Any]:
    p = c67.compile_program67(graph)
    p = _json_clone(p)
    p["version"] = KBC68_VERSION
    p["format"] = "keim-linear-bytecode"
    p["heap_layouts"] = _heap_layouts(p)
    p["wasm_runtime"] = {
        "name": "keim-wasm-heap-runtime",
        "version": KBC68_VERSION,
        "tagged_value_i64": True,
        "linear_memory_heap": True,
        "bump_allocator": True,
        "text_runtime": True,
        "list_runtime": True,
        "map_runtime": True,
        "record_runtime": True,
        "result_runtime": True,
    }
    p["capabilities"] = dict(p.get("capabilities", {}), wasm_heap_runtime=True, kbc68b=True)
    p["diagnostics"] = [d for d in p.get("diagnostics", []) if "Bytecode-Version" not in d.get("message", "")]
    p["diagnostics"].extend([d.as_dict() for d in verify_program68(p)])
    return p


def verify_program68(program: dict[str, Any]) -> list[Diagnostic]:
    probe = _json_clone(program)
    probe["version"] = c67.KBC67_VERSION
    ds = [d for d in c67.verify_program67(probe) if not ("Bytecode-Version" in d.message)]
    if int(program.get("version", 0)) < KBC68_VERSION:
        ds.append(Diagnostic("error", f"Bytecode-Version {program.get('version')} ist nicht v6.8", 0))
    if "heap_layouts" not in program:
        ds.append(Diagnostic("error", "heap_layouts fehlen", 0))
    for fid, fn in program.get("functions", {}).items():
        for pc, ins in enumerate(fn.get("code", [])):
            if ins.get("op") == "EVAL":
                ds.append(Diagnostic("error", f"{fid}:{pc}: EVAL verboten", ins.get("line", 0)))
    return ds


def encode_kbc68b(program: dict[str, Any]) -> bytes:
    program = _json_clone(program)
    program["version"] = KBC68_VERSION
    sections = [
        _section("META", {"format": program.get("format"), "version": KBC68_VERSION, "entry": program.get("entry"), "created": int(time.time())}),
        _section("CONST", program.get("const_pool", [])),
        _section("TYPE", program.get("type_table", {})),
        _section("SYMBOL", program.get("symbol_table", {})),
        _section("GENERIC", program.get("generic_monomorphization", {})),
        _section("HEAP", program.get("heap_layouts", {})),
        _section("WASMRT", program.get("wasm_runtime", {})),
        _section("FUNC", {k: {kk: vv for kk, vv in v.items() if kk != "code"} for k, v in program.get("functions", {}).items()}),
        _section("CODE", {k: v.get("code", []) for k, v in program.get("functions", {}).items()}),
        _section("DEBUG", program.get("debug", {})),
        _section("PROGRAM", program),
    ]
    header_size = len(KBC68_MAGIC) + 8 + len(sections) * 24
    offset = header_size
    directory = []
    body = []
    for name, data in sections:
        directory.append((name, offset, len(data)))
        body.append(data)
        offset += len(data)
    out = bytearray(KBC68_MAGIC + struct.pack("<II", KBC68_VERSION, len(sections)))
    for name, off, size in directory:
        out += name + struct.pack("<QQ", off, size)
    for data in body:
        out += data
    digest = hashlib.sha256(bytes(out)).digest()
    return b"KBC68HASH" + digest + bytes(out)


def decode_kbc68b(data: bytes) -> dict[str, Any]:
    if not data.startswith(b"KBC68HASH"):
        raise FoundationError("Keine KBC68B-Datei: Hash-Präambel fehlt")
    digest, payload = data[9:41], data[41:]
    if hashlib.sha256(payload).digest() != digest:
        raise FoundationError("KBC68B-Hashprüfung fehlgeschlagen")
    if not payload.startswith(KBC68_MAGIC):
        raise FoundationError("Keine KBC68B-Datei: falsche Magic")
    off = len(KBC68_MAGIC)
    version, count = struct.unpack("<II", payload[off:off + 8])
    off += 8
    if version < KBC68_VERSION:
        raise FoundationError("KBC68B-Version ist zu alt")
    sections: dict[str, Any] = {}
    for _ in range(count):
        name = payload[off:off + 8].rstrip(b"\0").decode("ascii")
        off += 8
        sec_off, sec_size = struct.unpack("<QQ", payload[off:off + 16])
        off += 16
        raw = payload[sec_off:sec_off + sec_size]
        if len(raw) != sec_size:
            raise FoundationError(f"KBC68B-Sektion {name} ist abgeschnitten")
        sections[name] = json.loads(raw.decode("utf-8"))
    p = sections.get("PROGRAM")
    if not p:
        raise FoundationError("KBC68B ohne PROGRAM-Sektion")
    p["binary_sections"] = sorted(sections)
    errs = verify_program68(p)
    if any(d.severity == "error" for d in errs):
        raise FoundationError(CheckReport(False, [], errs).format())
    return p


def write_kbc68b(program: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encode_kbc68b(program))


def read_kbc68b(path: Path) -> dict[str, Any]:
    return decode_kbc68b(Path(path).read_bytes())


def check68(path: Path) -> CheckReport:
    graph = ModuleGraph(path).load()
    p = compile_program68(graph)
    ds = [Diagnostic(d.get("severity", "error"), d.get("message", ""), d.get("line", 0), d.get("module", "")) for d in p.get("diagnostics", [])]
    ds.extend(verify_program68(p))
    return CheckReport(not any(d.severity == "error" for d in ds), sorted(graph.modules), ds)


def bytecode68(path: Path, *, out: Path | None = None, binary_out: Path | None = None) -> dict[str, Any]:
    graph = ModuleGraph(path).load()
    p = compile_program68(graph)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")
    if binary_out:
        write_kbc68b(p, binary_out)
    return p


def run68(path: Path, *, record: Path | None = None):
    graph = ModuleGraph(path).load()
    p = compile_program68(graph)
    errs = [d for d in verify_program68(p) if d.severity == "error"]
    if errs:
        raise FoundationError(CheckReport(False, sorted(graph.modules), errs).format())
    return c67.c66.VM66(p, graph=graph, record=record).run_main()


def run_kbc68b(path: Path):
    return c67.c66.VM66(read_kbc68b(path)).run_main()


def _collect_strings(program: dict[str, Any]) -> dict[str, tuple[int, int, str]]:
    offset = 1024
    out: dict[str, tuple[int, int, str]] = {}
    for s in sorted(program.get("heap_layouts", {}).get("strings", {}), key=lambda x: (len(x), x)):
        data = s.encode("utf-8")
        name = "$str_" + hashlib.sha1(data).hexdigest()[:10]
        out[s] = (offset, len(data), name)
        offset += len(data)
    return out


def _runtime_wat() -> list[str]:
    return [
        '  ;; Keim v6.8 tagged i64 runtime',
        '  (import "keim_host" "print_i64" (func $host_print_i64 (param i64)))',
        '  (import "keim_host" "panic" (func $host_panic (param i32)))',
        '  (memory (export "memory") 4)',
        '  (global $heap_ptr (mut i32) (i32.const 65536))',
        '  (global $vstack_ptr (mut i32) (i32.const 32768))',
        '  (func $align8 (param $n i32) (result i32) local.get $n i32.const 7 i32.add i32.const -8 i32.and)',
        '  (func $alloc (param $n i32) (result i32) (local $p i32) global.get $heap_ptr local.set $p global.get $heap_ptr local.get $n call $align8 i32.add global.set $heap_ptr local.get $p)',
        '  (func $tag_int (param $x i64) (result i64) local.get $x i64.const 3 i64.shl)',
        '  (func $untag_int (param $v i64) (result i64) local.get $v i64.const 3 i64.shr_s)',
        '  (func $tag_bool (param $x i32) (result i64) local.get $x i64.extend_i32_u i64.const 3 i64.shl i64.const 1 i64.or)',
        '  (func $truthy (param $v i64) (result i32) local.get $v i64.const 7 i64.and i64.const 1 i64.eq if (result i32) local.get $v i64.const 3 i64.shr_u i32.wrap_i64 else local.get $v i64.const 2 i64.ne end)',
        '  (func $heap_ref (param $p i32) (result i64) local.get $p i64.extend_i32_u i64.const 3 i64.shl i64.const 3 i64.or)',
        '  (func $ptr_from_ref (param $v i64) (result i32) local.get $v i64.const 3 i64.shr_u i32.wrap_i64)',
        '  (func $stack_push (param $v i64) global.get $vstack_ptr local.get $v i64.store global.get $vstack_ptr i32.const 8 i32.add global.set $vstack_ptr)',
        '  (func $stack_pop (result i64) global.get $vstack_ptr i32.const 8 i32.sub global.set $vstack_ptr global.get $vstack_ptr i64.load)',
        '  (func $object_kind (param $ref i64) (result i32) local.get $ref call $ptr_from_ref i32.load)',
        '  (func $keim_text_new (param $src i32) (param $len i32) (result i64) (local $p i32) local.get $len i32.const 16 i32.add call $alloc local.set $p local.get $p i32.const 1 i32.store local.get $p i32.const 4 i32.add local.get $len i32.store local.get $p i32.const 8 i32.add i32.const 0 i32.store local.get $p i32.const 16 i32.add local.get $src local.get $len memory.copy local.get $p call $heap_ref)',
        '  (func $keim_text_eq (param $a i64) (param $b i64) (result i32) (local $pa i32) (local $pb i32) (local $len i32) (local $i i32) local.get $a call $ptr_from_ref local.set $pa local.get $b call $ptr_from_ref local.set $pb local.get $pa i32.const 4 i32.add i32.load local.tee $len local.get $pb i32.const 4 i32.add i32.load i32.ne if i32.const 0 return end i32.const 0 local.set $i block $out loop $loop local.get $i local.get $len i32.ge_u br_if $out local.get $pa i32.const 16 i32.add local.get $i i32.add i32.load8_u local.get $pb i32.const 16 i32.add local.get $i i32.add i32.load8_u i32.ne if i32.const 0 return end local.get $i i32.const 1 i32.add local.set $i br $loop end end i32.const 1)',
        '  (func $keim_value_eq (param $a i64) (param $b i64) (result i32) local.get $a i64.const 7 i64.and local.get $b i64.const 7 i64.and i64.ne if i32.const 0 return end local.get $a i64.const 7 i64.and i64.const 3 i64.ne if local.get $a local.get $b i64.eq return end local.get $a call $object_kind local.get $b call $object_kind i32.ne if i32.const 0 return end local.get $a call $object_kind i32.const 1 i32.eq if local.get $a local.get $b call $keim_text_eq return end local.get $a local.get $b i64.eq)',
        '  (func $keim_list_new (param $cap i32) (result i64) (local $p i32) (local $items i32) i32.const 32 call $alloc local.set $p local.get $cap i32.const 8 i32.mul call $alloc local.set $items local.get $p i32.const 2 i32.store local.get $p i32.const 4 i32.add i32.const 0 i32.store local.get $p i32.const 8 i32.add local.get $cap i32.store local.get $p i32.const 16 i32.add local.get $items i32.store local.get $p call $heap_ref)',
        '  (func $keim_list_push (param $list i64) (param $value i64) (local $p i32) (local $len i32) (local $items i32) local.get $list call $ptr_from_ref local.set $p local.get $p i32.const 4 i32.add i32.load local.set $len local.get $p i32.const 16 i32.add i32.load local.set $items local.get $items local.get $len i32.const 8 i32.mul i32.add local.get $value i64.store local.get $p i32.const 4 i32.add local.get $len i32.const 1 i32.add i32.store)',
        '  (func $keim_list_get (param $list i64) (param $index i64) (result i64) (local $p i32) (local $idx i32) (local $len i32) (local $items i32) local.get $list call $ptr_from_ref local.set $p local.get $index call $untag_int i32.wrap_i64 local.set $idx local.get $p i32.const 4 i32.add i32.load local.set $len local.get $idx local.get $len i32.ge_u if i32.const 2 call $host_panic end local.get $p i32.const 16 i32.add i32.load local.set $items local.get $items local.get $idx i32.const 8 i32.mul i32.add i64.load)',
        '  (func $keim_record_new (param $type_id i32) (param $fields i32) (result i64) (local $p i32) local.get $fields i32.const 8 i32.mul i32.const 16 i32.add call $alloc local.set $p local.get $p i32.const 4 i32.store local.get $p i32.const 4 i32.add local.get $fields i32.store local.get $p i32.const 8 i32.add local.get $type_id i32.store local.get $p call $heap_ref)',
        '  (func $keim_record_set (param $rec i64) (param $idx i32) (param $val i64) local.get $rec call $ptr_from_ref i32.const 16 i32.add local.get $idx i32.const 8 i32.mul i32.add local.get $val i64.store)',
        '  (func $keim_record_get (param $rec i64) (param $idx i32) (result i64) local.get $rec call $ptr_from_ref i32.const 16 i32.add local.get $idx i32.const 8 i32.mul i32.add i64.load)',
        '  (func $keim_map_new (param $cap i32) (result i64) (local $p i32) (local $entries i32) i32.const 32 call $alloc local.set $p local.get $cap i32.const 16 i32.mul call $alloc local.set $entries local.get $p i32.const 3 i32.store local.get $p i32.const 4 i32.add i32.const 0 i32.store local.get $p i32.const 8 i32.add local.get $cap i32.store local.get $p i32.const 16 i32.add local.get $entries i32.store local.get $p call $heap_ref)',
        '  (func $keim_map_set (param $map i64) (param $key i64) (param $val i64) (local $p i32) (local $len i32) (local $entries i32) local.get $map call $ptr_from_ref local.set $p local.get $p i32.const 4 i32.add i32.load local.set $len local.get $p i32.const 16 i32.add i32.load local.set $entries local.get $entries local.get $len i32.const 16 i32.mul i32.add local.get $key i64.store local.get $entries local.get $len i32.const 16 i32.mul i32.add i32.const 8 i32.add local.get $val i64.store local.get $p i32.const 4 i32.add local.get $len i32.const 1 i32.add i32.store)',
        '  (func $keim_map_get (param $map i64) (param $key i64) (result i64) (local $p i32) (local $len i32) (local $entries i32) (local $i i32) local.get $map call $ptr_from_ref local.set $p local.get $p i32.const 4 i32.add i32.load local.set $len local.get $p i32.const 16 i32.add i32.load local.set $entries i32.const 0 local.set $i block $miss loop $loop local.get $i local.get $len i32.ge_u br_if $miss local.get $entries local.get $i i32.const 16 i32.mul i32.add i64.load local.get $key call $keim_value_eq if local.get $entries local.get $i i32.const 16 i32.mul i32.add i32.const 8 i32.add i64.load return end local.get $i i32.const 1 i32.add local.set $i br $loop end end i32.const 3 call $host_panic i64.const 2)',
        '  (func $keim_result_ok (param $payload i64) (result i64) (local $p i32) i32.const 24 call $alloc local.set $p local.get $p i32.const 5 i32.store local.get $p i32.const 4 i32.add i32.const 1 i32.store local.get $p i32.const 16 i32.add local.get $payload i64.store local.get $p call $heap_ref)',
        '  (func $keim_result_error (param $payload i64) (result i64) (local $p i32) i32.const 24 call $alloc local.set $p local.get $p i32.const 6 i32.store local.get $p i32.const 4 i32.add i32.const 1 i32.store local.get $p i32.const 16 i32.add local.get $payload i64.store local.get $p call $heap_ref)',
        '  (func $keim_result_is_ok (param $r i64) (result i64) local.get $r call $object_kind i32.const 5 i32.eq call $tag_bool)',
        '  (func $keim_result_payload (param $r i64) (result i64) local.get $r call $ptr_from_ref i32.const 16 i32.add i64.load)',
    ]


@dataclass(slots=True)
class _LowerState:
    type_stack: list[str]
    slots: dict[int, str]
    const_pool: list[Any]
    records: dict[str, dict[str, Any]]
    string_lits: dict[str, tuple[int, int, str]]

    def push(self, t: str) -> None:
        self.type_stack.append(t)

    def pop(self) -> str:
        return self.type_stack.pop() if self.type_stack else "beliebig"

    def popn(self, n: int) -> list[str]:
        vals = self.type_stack[-n:] if n else []
        if n:
            del self.type_stack[-n:]
        return vals


def _type_after_binary(a: str, b: str, op: str) -> str:
    if op in {"EQ", "NE", "LT", "LE", "GT", "GE", "AND", "OR"}:
        return "bool"
    if a == "text" and b == "text" and op == "ADD":
        return "text"
    if "kommazahl" in {a, b}:
        return "kommazahl"
    return "ganzzahl"


def _emit_const_push(v: Any, st: _LowerState, out: list[str]) -> str:
    if isinstance(v, bool):
        out.append(f"        i32.const {1 if v else 0}")
        out.append("        call $tag_bool")
    elif isinstance(v, int) and not isinstance(v, bool):
        out.append(f"        i64.const {int(v)}")
        out.append("        call $tag_int")
    elif isinstance(v, str):
        off, ln, _name = st.string_lits[v]
        out.append(f"        i32.const {off}")
        out.append(f"        i32.const {ln}")
        out.append("        call $keim_text_new")
    elif v is None:
        out.append("        i64.const 2")
    else:
        out.append("        i64.const 2")
    out.append("        call $stack_push")
    return _const_type(v)


def _emit_pop_untag_int(out: list[str]) -> None:
    out.append("        call $stack_pop")
    out.append("        call $untag_int")


def _emit_push_tagged_int_from_stack(out: list[str]) -> None:
    out.append("        call $tag_int")
    out.append("        call $stack_push")


def _emit_pc_body(program: dict[str, Any], fid: str, fn: dict[str, Any], ins: dict[str, Any], pc: int, st: _LowerState, out: list[str]) -> int | None:
    op = ins.get("op")
    args = ins.get("args", [])
    next_pc = pc + 1
    if op == "CONST_POOL":
        idx = int(args[0])
        t = _emit_const_push(st.const_pool[idx], st, out)
        st.push(t)
    elif op == "CONST":
        t = _emit_const_push(args[0] if args else None, st, out)
        st.push(t)
    elif op == "LOAD_SLOT":
        slot = int(args[0])
        out.append(f"        local.get $s{slot}")
        out.append("        call $stack_push")
        st.push(st.slots.get(slot, "beliebig"))
    elif op == "STORE_SLOT":
        slot = int(args[0])
        t = st.pop()
        out.append("        call $stack_pop")
        out.append(f"        local.set $s{slot}")
        st.slots[slot] = t
    elif op == "TYPE_ASSERT":
        pass
    elif op in {"ADD", "SUB", "MUL", "DIV", "FLOORDIV", "MOD"}:
        b = st.pop(); a = st.pop()
        _emit_pop_untag_int(out)
        out.append("        local.set $tmp_b")
        _emit_pop_untag_int(out)
        out.append("        local.get $tmp_b")
        out.append({
            "ADD": "        i64.add",
            "SUB": "        i64.sub",
            "MUL": "        i64.mul",
            "DIV": "        i64.div_s",
            "FLOORDIV": "        i64.div_s",
            "MOD": "        i64.rem_s",
        }[op])
        _emit_push_tagged_int_from_stack(out)
        st.push(_type_after_binary(a, b, op))
    elif op in {"EQ", "NE", "LT", "LE", "GT", "GE"}:
        b = st.pop(); a = st.pop()
        if a == "text" or b == "text":
            out.append("        call $stack_pop")
            out.append("        local.set $tmp_b")
            out.append("        call $stack_pop")
            out.append("        local.get $tmp_b")
            out.append("        call $keim_value_eq")
            if op == "NE":
                out.append("        i32.eqz")
            elif op != "EQ":
                out.append("        i32.const 4")
                out.append("        call $host_panic")
                out.append("        i32.const 0")
            out.append("        call $tag_bool")
            out.append("        call $stack_push")
        else:
            _emit_pop_untag_int(out)
            out.append("        local.set $tmp_b")
            _emit_pop_untag_int(out)
            out.append("        local.get $tmp_b")
            out.append({
                "EQ": "        i64.eq",
                "NE": "        i64.ne",
                "LT": "        i64.lt_s",
                "LE": "        i64.le_s",
                "GT": "        i64.gt_s",
                "GE": "        i64.ge_s",
            }[op])
            out.append("        call $tag_bool")
            out.append("        call $stack_push")
        st.push("bool")
    elif op == "NEG":
        a = st.pop()
        _emit_pop_untag_int(out)
        out.append("        i64.const -1")
        out.append("        i64.mul")
        _emit_push_tagged_int_from_stack(out)
        st.push(a)
    elif op == "NOT":
        st.pop()
        out.append("        call $stack_pop")
        out.append("        call $truthy")
        out.append("        i32.eqz")
        out.append("        call $tag_bool")
        out.append("        call $stack_push")
        st.push("bool")
    elif op in {"AND", "OR"}:
        st.pop(); st.pop()
        out.append("        call $stack_pop")
        out.append("        call $truthy")
        out.append("        local.set $tmp_i")
        out.append("        call $stack_pop")
        out.append("        call $truthy")
        out.append("        local.get $tmp_i")
        out.append("        i32.and" if op == "AND" else "        i32.or")
        out.append("        call $tag_bool")
        out.append("        call $stack_push")
        st.push("bool")
    elif op == "MAKE_LIST":
        n = int(args[0])
        elems = st.popn(n)
        for i in range(n - 1, -1, -1):
            out.append("        call $stack_pop")
            out.append(f"        local.set $arg{i}")
        out.append(f"        i32.const {max(n, 1)}")
        out.append("        call $keim_list_new")
        out.append("        local.set $tmp_v")
        for i in range(n):
            out.append("        local.get $tmp_v")
            out.append(f"        local.get $arg{i}")
            out.append("        call $keim_list_push")
        out.append("        local.get $tmp_v")
        out.append("        call $stack_push")
        et = elems[0] if elems else "beliebig"
        st.push(f"liste<{et}>")
    elif op == "MAKE_MAP":
        n = int(args[0])
        st.popn(n * 2)
        for i in range(n * 2 - 1, -1, -1):
            out.append("        call $stack_pop")
            out.append(f"        local.set $arg{i}")
        out.append(f"        i32.const {max(n, 1)}")
        out.append("        call $keim_map_new")
        out.append("        local.set $tmp_v")
        for i in range(n):
            out.append("        local.get $tmp_v")
            out.append(f"        local.get $arg{2*i}")
            out.append(f"        local.get $arg{2*i+1}")
            out.append("        call $keim_map_set")
        out.append("        local.get $tmp_v")
        out.append("        call $stack_push")
        st.push("karte<text, beliebig>")
    elif op == "MAKE_RECORD":
        rname, n = str(args[0]), int(args[1])
        st.popn(n)
        for i in range(n - 1, -1, -1):
            out.append("        call $stack_pop")
            out.append(f"        local.set $arg{i}")
        layout = st.records.get(rname, {"type_id": 0, "field_count": n})
        out.append(f"        i32.const {int(layout.get('type_id', 0))}")
        out.append(f"        i32.const {n}")
        out.append("        call $keim_record_new")
        out.append("        local.set $tmp_v")
        for i in range(n):
            out.append("        local.get $tmp_v")
            out.append(f"        i32.const {i}")
            out.append(f"        local.get $arg{i}")
            out.append("        call $keim_record_set")
        out.append("        local.get $tmp_v")
        out.append("        call $stack_push")
        st.push(rname)
    elif op == "GET_ITEM":
        key_t = st.pop(); base_t = st.pop()
        out.append("        call $stack_pop")
        out.append("        local.set $tmp_b")
        out.append("        call $stack_pop")
        out.append("        local.get $tmp_b")
        if base_t.startswith("liste"):
            out.append("        call $keim_list_get")
            inner = base_t[base_t.find("<")+1:-1] if "<" in base_t else "beliebig"
            st.push(inner)
        else:
            out.append("        call $keim_map_get")
            st.push("beliebig")
        out.append("        call $stack_push")
    elif op == "GET_ATTR":
        attr = str(args[0])
        base_t = st.pop()
        out.append("        call $stack_pop")
        if base_t.startswith("ergebnis"):
            if attr == "ok":
                out.append("        call $keim_result_is_ok")
                st.push("bool")
            else:
                out.append("        call $keim_result_payload")
                st.push("beliebig")
        elif base_t.startswith("karte"):
            out.append("        local.set $tmp_v")
            off, ln, _ = st.string_lits[attr]
            out.append("        local.get $tmp_v")
            out.append(f"        i32.const {off}")
            out.append(f"        i32.const {ln}")
            out.append("        call $keim_text_new")
            out.append("        call $keim_map_get")
            st.push("beliebig")
        elif base_t in st.records and attr in st.records[base_t].get("fields", {}):
            idx = int(st.records[base_t]["fields"][attr])
            out.append(f"        i32.const {idx}")
            out.append("        call $keim_record_get")
            st.push(st.records[base_t].get("field_types", {}).get(attr, "beliebig"))
        else:
            out.append("        ;; fallback: attr as map key")
            out.append("        local.set $tmp_v")
            off, ln, _ = st.string_lits[attr]
            out.append("        local.get $tmp_v")
            out.append(f"        i32.const {off}")
            out.append(f"        i32.const {ln}")
            out.append("        call $keim_text_new")
            out.append("        call $keim_map_get")
            st.push("beliebig")

        out.append("        call $stack_push")
    elif op == "CALL_BUILTIN":
        name, argc = str(args[0]), int(args[1])
        st.popn(argc)
        for i in range(argc - 1, -1, -1):
            out.append("        call $stack_pop")
            out.append(f"        local.set $arg{i}")
        if name == "ok":
            out.append("        local.get $arg0")
            out.append("        call $keim_result_ok")
            out.append("        call $stack_push")
            st.push("ergebnis<beliebig, beliebig>")
        elif name == "fehler":
            out.append("        local.get $arg0")
            out.append("        call $keim_result_error")
            out.append("        call $stack_push")
            st.push("ergebnis<beliebig, beliebig>")
        elif name == "ist_ok":
            out.append("        local.get $arg0")
            out.append("        call $keim_result_is_ok")
            out.append("        call $stack_push")
            st.push("bool")
        else:
            out.append("        i32.const 9")
            out.append("        call $host_panic")
            out.append("        i64.const 2")
            out.append("        call $stack_push")
            st.push("beliebig")
    elif op == "CALL":
        mod, name, argc = str(args[0]), str(args[1]), int(args[2])
        st.popn(argc)
        for i in range(argc - 1, -1, -1):
            out.append("        call $stack_pop")
            out.append(f"        local.set $arg{i}")
        for i in range(argc):
            out.append(f"        local.get $arg{i}")
        out.append(f"        call {_wat_name(mod + '.' + name)}")
        out.append("        call $stack_push")
        target = program.get("functions", {}).get(mod + "." + name, {})
        st.push(target.get("returns", "beliebig"))
    elif op == "PRINT":
        t = st.pop()
        out.append("        call $stack_pop")
        if _is_int_type(t) or t == "bool":
            out.append("        call $untag_int")
        out.append("        call $host_print_i64")
    elif op == "ASSERT":
        st.pop()
        out.append("        call $stack_pop")
        out.append("        call $truthy")
        out.append("        i32.eqz")
        out.append("        if i32.const 10 call $host_panic end")
    elif op == "RETURN":
        out.append("        call $stack_pop")
        out.append("        local.set $ret")
        out.append("        i32.const 0")
        out.append("        local.set $running")
    elif op == "POP":
        st.pop()
        out.append("        call $stack_pop")
        out.append("        drop")
    elif op == "JUMP":
        next_pc = int(args[0])
    elif op == "JUMP_IF_FALSE":
        st.pop()
        out.append("        call $stack_pop")
        out.append("        call $truthy")
        out.append("        i32.eqz")
        out.append(f"        if i32.const {int(args[0])} local.set $pc else i32.const {pc+1} local.set $pc end")
        return None
    elif op == "JUMP_IF_TRUE":
        st.pop()
        out.append("        call $stack_pop")
        out.append("        call $truthy")
        out.append(f"        if i32.const {int(args[0])} local.set $pc else i32.const {pc+1} local.set $pc end")
        return None
    elif op == "PANIC":
        out.append("        i32.const 99")
        out.append("        call $host_panic")
        out.append("        i32.const 0")
        out.append("        local.set $running")
    else:
        out.append(f"        ;; unsupported {op}: deterministic trap")
        out.append("        i32.const 127")
        out.append("        call $host_panic")
        out.append("        i32.const 0")
        out.append("        local.set $running")
    out.append(f"        i32.const {next_pc}")
    out.append("        local.set $pc")
    return next_pc


def _prepare_string_literals(program: dict[str, Any]) -> dict[str, tuple[int, int, str]]:
    strings = _collect_strings(program)
    # Include attribute map keys that are not necessarily constants.
    off = max((o + l for o, l, _ in strings.values()), default=1024)
    for fn in program.get("functions", {}).values():
        for ins in fn.get("code", []):
            if ins.get("op") == "GET_ATTR":
                attr = str(ins.get("args", [""])[0])
                if attr and attr not in strings:
                    data = attr.encode("utf-8")
                    strings[attr] = (off, len(data), "$str_" + hashlib.sha1(data).hexdigest()[:10])
                    off += len(data)
    return strings


def emit_wasm68(program: dict[str, Any], out: Path) -> None:
    if "heap_layouts" not in program:
        program = _json_clone(program)
        program["heap_layouts"] = _heap_layouts(program)
    strings = _prepare_string_literals(program)
    lines: list[str] = ["(module"]
    lines.extend(_runtime_wat())
    for s, (off, _ln, name) in strings.items():
        escaped = s.encode("unicode_escape").decode("ascii").replace('"', '\\"')
        lines.append(f'  (data (i32.const {off}) "{escaped}") ;; {name}')
    records = program.get("heap_layouts", {}).get("records", {})
    const_pool = program.get("const_pool", [])
    for fid, fn in program.get("functions", {}).items():
        params = fn.get("params", [])
        slot_count = max([*fn.get("slots", {}).values(), -1]) + 1
        param_decl = " ".join(f"(param ${p.get('name','p'+str(i))} i64)" for i, p in enumerate(params))
        local_slots = " ".join(f"(local $s{i} i64)" for i in range(max(slot_count, 1)))
        arg_locals = " ".join(f"(local $arg{i} i64)" for i in range(32))
        lines.append(f"  (func {_wat_name(fid)} {param_decl} (result i64)")
        lines.append(f"    (local $pc i32) (local $oldpc i32) (local $running i32) (local $ret i64) (local $tmp_v i64) (local $tmp_b i64) (local $tmp_i i32) {local_slots} {arg_locals}")
        for i, p in enumerate(params):
            lines.append(f"    local.get ${p.get('name','p'+str(i))}")
            lines.append(f"    local.set $s{p.get('slot', i)}")
        lines.append("    i32.const 0")
        lines.append("    local.set $pc")
        lines.append("    i32.const 1")
        lines.append("    local.set $running")
        lines.append("    block $exit")
        lines.append("      loop $dispatch")
        lines.append("        local.get $running")
        lines.append("        i32.eqz")
        lines.append("        br_if $exit")
        lines.append("        local.get $pc")
        lines.append("        local.set $oldpc")
        st = _LowerState(
            type_stack=[],
            slots={int(k): v for k, v in fn.get("slot_types", {}).items()},
            const_pool=const_pool,
            records=records,
            string_lits=strings,
        )
        for pc, ins in enumerate(fn.get("code", [])):
            lines.append(f"        local.get $oldpc")
            lines.append(f"        i32.const {pc}")
            lines.append("        i32.eq")
            lines.append("        if")
            lines.append(f"          ;; pc {pc} line {ins.get('line', 0)} {ins.get('op')} {ins.get('args', [])}")
            _emit_pc_body(program, fid, fn, ins, pc, st, lines)
            lines.append("        end")
        lines.append("        br $dispatch")
        lines.append("      end")
        lines.append("    end")
        lines.append("    local.get $ret")
        lines.append("  )")
        lines.append(f'  (export "{fid}" (func {_wat_name(fid)}))')
    entry = program.get("entry", "")
    if f"{entry}.main" in program.get("functions", {}):
        lines.append(f'  (export "main" (func {_wat_name(entry + ".main")}))')
    lines.append(")")
    text = "\n".join(lines) + "\n"
    if "unreachable" in text:
        raise FoundationError("v6.8 WAT enthält weiterhin unreachable; Heap-Lowering fehlgeschlagen")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")


def build68(cwd: Path, out: Path) -> dict[str, Any]:
    cwd = Path(cwd)
    out = Path(out)
    candidates = [
        cwd / "examples" / "sprache_v68_wasm_heap_runtime.keim",
        cwd / "examples" / "sprache_v66_enterprise_full.keim",
        cwd / "examples" / "sprache_v67_full_enterprise.keim",
    ]
    main = next((p for p in candidates if p.exists()), candidates[-1])
    p = bytecode68(main, out=out / "app.kbc68.json", binary_out=out / "app.kbc68b")
    emit_wasm68(p, out / "app_heap_runtime.wat")
    manifest = {
        "format": "keim-build-v68",
        "main": str(main),
        "bytecode": "app.kbc68.json",
        "binary": "app.kbc68b",
        "wasm_heap_runtime": "app_heap_runtime.wat",
        "heap_runtime": p.get("wasm_runtime", {}),
        "heap_layouts": p.get("heap_layouts", {}),
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "build_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "manifest": manifest}


def test68(path: Path, *, filter_text: str | None = None, junit: Path | None = None) -> dict[str, Any]:
    payload = c67.test67(path, filter_text=filter_text, junit=junit)
    p = bytecode68(path)
    wat_path = Path("build/v68/test_heap_runtime.wat")
    emit_wasm68(p, wat_path)
    wat = wat_path.read_text(encoding="utf-8")
    checks = {
        "heap_runtime": "$keim_list_new" in wat and "$keim_record_new" in wat and "$keim_map_new" in wat and "$keim_result_ok" in wat,
        "no_unreachable": "unreachable" not in wat,
        "tagged_values": "$tag_int" in wat and "$heap_ref" in wat,
        "lowered_heap_ops": "call $keim_list_get" in wat or "call $keim_record_get" in wat or "call $keim_map_get" in wat,
    }
    payload.setdefault("coverage", {})["v68_wasm_heap_runtime"] = checks
    payload["ok"] = bool(payload.get("ok")) and all(checks.values())
    return payload


def status68() -> dict[str, Any]:
    return {
        "version": KBC68_VERSION,
        "name": "Keim v6.8 WASM Heap Runtime",
        "features": [
            "tagged_i64_value_abi",
            "linear_memory_heap",
            "bump_allocator",
            "text_runtime",
            "list_runtime",
            "map_runtime_linear_entries",
            "record_runtime_layout_table",
            "result_runtime",
            "heap_lowering_without_unreachable",
            "kbc68b_heap_sections",
        ],
    }
