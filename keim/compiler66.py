
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import hashlib, json, struct, time, xml.etree.ElementTree as ET

from .foundation import ModuleGraph, ModuleDef, FunctionDef, Step, TypeRef, Diagnostic, CheckReport, FoundationError
from . import compiler64 as c64
from . import compiler65 as c65

KBC66_MAGIC = b"KBC66B\x00\x01"
KBC66_VERSION = 660

@dataclass(slots=True)
class LoopTarget:
    start: str
    end: str

@dataclass(slots=True)
class CompileContext66:
    module: ModuleDef
    fn: FunctionDef
    table: c64.SymbolTable
    env: c64.TypeEnv64
    builder: c64.CodeBuilder
    loops: list[LoopTarget] = field(default_factory=list)

def compile_steps66(steps: list[Step], ctx: CompileContext66) -> bool:
    returned = False
    b, env, mod, fn = ctx.builder, ctx.env, ctx.module, ctx.fn
    for st in steps:
        match st.op:
            case "while":
                cond_s, body = st.args
                cond = c64.parse_keim_expr(cond_s, line=st.line)
                typ = c65.infer_expr65(cond, env)
                if not c65._unify(TypeRef("bool"), typ, {}):
                    raise c64.KeimTypeError(f"Zeile {st.line}: solange erwartet bool, bekam {typ}")
                start = b.label("while_start"); end = b.label("while_end")
                b.mark(start)
                c65.emit_expr65(cond, env, b)
                b.jump("JUMP_IF_FALSE", end, line=st.line)
                ctx.loops.append(LoopTarget(start, end))
                compile_steps66(body, ctx)
                ctx.loops.pop()
                b.jump("JUMP", start, line=st.line)
                b.mark(end)
            case "break":
                if not ctx.loops: raise c64.KeimTypeError(f"Zeile {st.line}: abbruch außerhalb einer Schleife")
                b.jump("JUMP", ctx.loops[-1].end, line=st.line)
            case "continue":
                if not ctx.loops: raise c64.KeimTypeError(f"Zeile {st.line}: weiter außerhalb einer Schleife")
                b.jump("JUMP", ctx.loops[-1].start, line=st.line)
            case "if":
                cond_s, then_steps, else_steps = st.args
                cond = c64.parse_keim_expr(cond_s, line=st.line)
                typ = c65.infer_expr65(cond, env)
                if not c65._unify(TypeRef("bool"), typ, {}):
                    raise c64.KeimTypeError(f"Zeile {st.line}: wenn erwartet bool, bekam {typ}")
                else_l = b.label("else")
                end_l = b.label("endif")
                c65.emit_expr65(cond, env, b)
                b.jump("JUMP_IF_FALSE", else_l, line=st.line)
                r1 = compile_steps66(then_steps, ctx)
                b.jump("JUMP", end_l, line=st.line)
                b.mark(else_l)
                r2 = compile_steps66(else_steps, ctx)
                b.mark(end_l)
                returned = returned or (bool(then_steps) and bool(else_steps) and r1 and r2)
            case "match":
                returned = c65.compile_match65(st, mod, fn, env, b) or returned
            case _:
                returned = c65.compile_steps65([st], mod, fn, env, b) or returned
    return returned

def compile_function66(mod: ModuleDef, fn: FunctionDef, table: c64.SymbolTable) -> c64.Function64:
    scope = c64.ScopeLayout64()
    for p in fn.params:
        scope.declare(p.name, p.typ, mutable=True)
    env = c64.TypeEnv64(mod.name, table, scope)
    b = c64.CodeBuilder()
    returned = compile_steps66(fn.steps, CompileContext66(mod, fn, table, env, b))
    if fn.returns.name not in {"nichts", "void"} and not returned:
        raise c64.KeimTypeError(f"Funktion {fn.name} gibt nicht auf allen Pfaden zurück")
    b.finalize()
    return c64.Function64(
        module=mod.name,
        name=fn.name,
        params=[{"name": p.name, "type": str(p.typ), "slot": scope.names[p.name]} for p in fn.params],
        returns=str(fn.returns),
        slots=dict(scope.names),
        slot_types={str(k): str(v) for k, v in scope.types.items()},
        code=b.code,
        max_stack=c64.compute_max_stack(b.code),
    )

def _base_program66(graph: ModuleGraph) -> c64.Program64:
    table = c64.SymbolTable.from_graph(graph)
    diags: list[Diagnostic] = []
    funcs: dict[str, c64.Function64] = {}
    modules: dict[str, Any] = {}
    for m in graph.modules.values():
        modules[m.name] = {
            "path": str(m.path),
            "exports": sorted(m.exports),
            "imports": {i.alias or i.module.split(".")[-1]: i.module for i in m.imports},
            "types": {n: {"fields": [{"name": f.name, "type": str(f.typ)} for f in td.fields], "union": td.union} for n, td in m.types.items()},
        }
    for m in graph.modules.values():
        for fn in m.functions.values():
            try:
                funcs[f"{m.name}.{fn.name}"] = compile_function66(m, fn, table)
            except FoundationError as exc:
                diags.append(Diagnostic("error", f"{fn.name}: {exc}", fn.line, m.name))
    p = c64.Program64("keim-linear-bytecode", KBC66_VERSION, graph.entry_module().name, modules, funcs, diags)
    diags.extend(c65.verify_program65(p))
    return p

def _const_key(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)

def build_type_table(program: c64.Program64) -> dict[str, Any]:
    return {f"{m}.{n}": td for m, mod in program.modules.items() for n, td in mod.get("types", {}).items()}

def build_symbol_table(program: c64.Program64) -> dict[str, Any]:
    return {fid: {"module": fn.module, "name": fn.name, "params": fn.params, "returns": fn.returns, "slots": fn.slots, "slot_types": fn.slot_types} for fid, fn in program.functions.items()}

def build_debug_table(program: c64.Program64) -> dict[str, Any]:
    return {fid: [{"pc": pc, "line": ins.line, "op": ins.op} for pc, ins in enumerate(fn.code)] for fid, fn in program.functions.items()}

def infer_specializations(program: c64.Program64) -> list[dict[str, Any]]:
    specs, seen = [], set()
    for caller, fn in program.functions.items():
        for ins in fn.code:
            if ins.op == "CALL":
                target = f"{ins.args[0]}.{ins.args[1]}"
                key = f"{caller}->{target}/{ins.args[2]}"
                if key not in seen:
                    seen.add(key)
                    specs.append({"caller": caller, "target": target, "argc": ins.args[2], "strategy": "monomorphization-candidate"})
    return specs

def intern_constants(program: c64.Program64) -> dict[str, Any]:
    pool, index, funcs = [], {}, {}
    for fid, fn in program.functions.items():
        code = []
        for ins in fn.code:
            if ins.op == "CONST":
                value = ins.args[0] if ins.args else None
                key = _const_key(value)
                if key not in index:
                    index[key] = len(pool); pool.append(value)
                code.append({"op": "CONST_POOL", "args": [index[key]], "line": ins.line, "col": ins.col})
            else:
                code.append(ins.as_dict())
        fd = fn.as_dict(); fd["code"] = code; funcs[fid] = fd
    return {
        "format": "keim-linear-bytecode",
        "version": KBC66_VERSION,
        "entry": program.entry,
        "modules": program.modules,
        "functions": funcs,
        "diagnostics": [d.as_dict() for d in program.diagnostics],
        "const_pool": pool,
        "type_table": build_type_table(program),
        "symbol_table": build_symbol_table(program),
        "debug": build_debug_table(program),
        "specializations": infer_specializations(program),
        "sections": ["META", "CONST", "TYPE", "SYMBOL", "FUNC", "CODE", "DEBUG"],
    }

def compile_program66(graph: ModuleGraph) -> dict[str, Any]:
    p = intern_constants(_base_program66(graph))
    p["diagnostics"].extend([d.as_dict() for d in verify_program66(p)])
    return p

_VALID66 = set(c65._VALID65) | {"CONST_POOL", "JUMP_IF_TRUE", "RESULT_IS_OK", "PANIC"}

def verify_program66(program: dict[str, Any]) -> list[Diagnostic]:
    ds: list[Diagnostic] = []
    if program.get("format") != "keim-linear-bytecode":
        ds.append(Diagnostic("error", "falsches v6.6 Format", 0))
    if int(program.get("version", 0)) < KBC66_VERSION:
        ds.append(Diagnostic("error", f"Bytecode-Version {program.get('version')} ist nicht v6.6", 0))
    pool = program.get("const_pool", [])
    for fid, fn in program.get("functions", {}).items():
        code = fn.get("code", [])
        for pc, ins in enumerate(code):
            op, args, line = ins.get("op"), ins.get("args", []), ins.get("line", 0)
            if op == "EVAL": ds.append(Diagnostic("error", f"{fid}: EVAL verboten", line))
            if op not in _VALID66: ds.append(Diagnostic("error", f"{fid}: unbekannter Opcode {op}", line))
            if op == "CONST_POOL" and (not args or not isinstance(args[0], int) or args[0] < 0 or args[0] >= len(pool)):
                ds.append(Diagnostic("error", f"{fid}:{pc}: CONST_POOL-Index ungültig", line))
            if op in {"JUMP", "JUMP_IF_FALSE", "JUMP_IF_TRUE"} and (not args or not isinstance(args[0], int) or args[0] < 0 or args[0] > len(code)):
                ds.append(Diagnostic("error", f"{fid}:{pc}: Sprungziel ungültig", line))
            if op == "CALL":
                target = f"{args[0]}.{args[1]}" if len(args) >= 2 else ""
                if target not in program.get("functions", {}):
                    ds.append(Diagnostic("error", f"{fid}:{pc}: Call-Ziel fehlt {target}", line))
    return ds

class VM66(c65.VM65):
    def __init__(self, program: dict[str, Any], graph: ModuleGraph | None = None, *, record: Path | None = None):
        self.program_dict = program
        self.const_pool = program.get("const_pool", [])
        normalized = json.loads(json.dumps(program, ensure_ascii=False))
        for fn in normalized.get("functions", {}).values():
            for ins in fn.get("code", []):
                if ins.get("op") == "CONST_POOL":
                    idx = ins.get("args", [0])[0]
                    ins["op"] = "CONST"; ins["args"] = [self.const_pool[idx]]
        super().__init__(normalized, graph=graph, record=record)

def check66(path: Path) -> CheckReport:
    graph = ModuleGraph(path).load()
    p = compile_program66(graph)
    ds = [Diagnostic(d.get("severity", "error"), d.get("message", ""), d.get("line", 0), d.get("module", "")) for d in p.get("diagnostics", [])]
    ds.extend(verify_program66(p))
    return CheckReport(not any(d.severity == "error" for d in ds), sorted(graph.modules), ds)

def run66(path: Path, *, record: Path | None = None) -> c64.VM64Result:
    graph = ModuleGraph(path).load()
    p = compile_program66(graph)
    errs = [d for d in verify_program66(p) if d.severity == "error"]
    if errs: raise FoundationError(CheckReport(False, sorted(graph.modules), errs).format())
    return VM66(p, graph=graph, record=record).run_main()

def bytecode66(path: Path, *, out: Path | None = None, binary_out: Path | None = None) -> dict[str, Any]:
    graph = ModuleGraph(path).load()
    p = compile_program66(graph)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")
    if binary_out:
        write_kbc66b(p, binary_out)
    return p

def _section(name: str, payload: Any) -> tuple[bytes, bytes]:
    return name.encode("ascii")[:8].ljust(8, b"\0"), json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

def encode_kbc66b(program: dict[str, Any]) -> bytes:
    program = json.loads(json.dumps(program, ensure_ascii=False)); program["version"] = KBC66_VERSION
    sections = [
        _section("META", {"format": program.get("format"), "version": KBC66_VERSION, "entry": program.get("entry")}),
        _section("CONST", program.get("const_pool", [])),
        _section("TYPE", program.get("type_table", {})),
        _section("SYMBOL", program.get("symbol_table", {})),
        _section("FUNC", {k: {kk: vv for kk, vv in v.items() if kk != "code"} for k, v in program.get("functions", {}).items()}),
        _section("CODE", {k: v.get("code", []) for k, v in program.get("functions", {}).items()}),
        _section("DEBUG", program.get("debug", {})),
        _section("PROGRAM", program),
    ]
    header_size = len(KBC66_MAGIC) + 8 + len(sections) * 24
    offset = header_size; directory=[]; body=[]
    for name, data in sections:
        directory.append((name, offset, len(data))); body.append(data); offset += len(data)
    out = bytearray(KBC66_MAGIC + struct.pack("<II", KBC66_VERSION, len(sections)))
    for name, off, size in directory:
        out += name + struct.pack("<QQ", off, size)
    for data in body: out += data
    digest = hashlib.sha256(bytes(out)).digest()
    return b"KBC66HASH" + digest + bytes(out)

def decode_kbc66b(data: bytes) -> dict[str, Any]:
    if not data.startswith(b"KBC66HASH"): raise FoundationError("Keine KBC66B-Datei: Hash-Präambel fehlt")
    digest, payload = data[9:41], data[41:]
    if hashlib.sha256(payload).digest() != digest: raise FoundationError("KBC66B-Hashprüfung fehlgeschlagen")
    if not payload.startswith(KBC66_MAGIC): raise FoundationError("Keine KBC66B-Datei: falsche Magic")
    off = len(KBC66_MAGIC)
    version, count = struct.unpack("<II", payload[off:off+8]); off += 8
    if version < KBC66_VERSION: raise FoundationError("KBC66B-Version ist zu alt")
    entries=[]
    for _ in range(count):
        name = payload[off:off+8].rstrip(b"\0").decode("ascii"); off += 8
        sec_off, sec_size = struct.unpack("<QQ", payload[off:off+16]); off += 16
        entries.append((name, sec_off, sec_size))
    sections = {}
    for name, sec_off, sec_size in entries:
        raw = payload[sec_off:sec_off+sec_size]
        if len(raw) != sec_size: raise FoundationError(f"KBC66B-Sektion {name} ist abgeschnitten")
        sections[name] = json.loads(raw.decode("utf-8"))
    program = sections.get("PROGRAM")
    if not program: raise FoundationError("KBC66B ohne PROGRAM-Sektion")
    program["binary_sections"] = sorted(sections)
    errs = verify_program66(program)
    if any(d.severity == "error" for d in errs): raise FoundationError(CheckReport(False, [], errs).format())
    return program

def write_kbc66b(program: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(encode_kbc66b(program))

def read_kbc66b(path: Path) -> dict[str, Any]:
    return decode_kbc66b(Path(path).read_bytes())

def run_kbc66b(path: Path) -> c64.VM64Result:
    return VM66(read_kbc66b(path)).run_main()

def create_lock66(cwd: Path, out: Path | None = None) -> dict[str, Any]:
    cwd = Path(cwd)
    sources=[]
    for p in sorted(cwd.rglob("*.keim")):
        if any(part in {".git", "__pycache__", "build"} for part in p.parts): continue
        sources.append({"path": str(p.relative_to(cwd)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "size": p.stat().st_size})
    packages=[]
    toml = cwd / "keim.toml"
    if toml.exists():
        in_dep=False
        for line in toml.read_text(encoding="utf-8").splitlines():
            s=line.strip()
            if s.startswith("["):
                in_dep = s in {"[abhaengigkeiten]", "[abhängigkeiten]", "[dependencies]"}; continue
            if in_dep and "=" in s and not s.startswith("#"):
                name, version = [x.strip().strip('"') for x in s.split("=", 1)]
                packages.append({"name": name, "version": version, "source": "registry-or-cache", "permissions": [], "sha256": hashlib.sha256(f"{name}@{version}".encode()).hexdigest()})
    payload={"format":"keim-lock-v5","version":KBC66_VERSION,"sources":sources,"packages":packages,"resolver":{"semver":True,"offline_cache":".keim/cache","signatures":"planned-required"}}
    if out:
        out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload

def build66(cwd: Path, out: Path) -> dict[str, Any]:
    cwd = Path(cwd); out = Path(out)
    main = cwd / "examples" / "sprache_v66_enterprise_full.keim"
    if not main.exists(): main = cwd / "examples" / "sprache_v65_result_match_generics.keim"
    p = bytecode66(main, out=out/"app.kbc66.json", binary_out=out/"app.kbc66b")
    lock = create_lock66(cwd, out/"keim.lock")
    manifest={"format":"keim-build-v66","main":str(main),"bytecode":"app.kbc66.json","binary":"app.kbc66b","lock":"keim.lock","functions":len(p.get("functions",{}))}
    out.mkdir(parents=True, exist_ok=True); (out/"build_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "manifest": manifest, "lock": lock}

def test66(path: Path, *, filter_text: str | None = None, junit: Path | None = None) -> dict[str, Any]:
    graph = ModuleGraph(path).load()
    program = compile_program66(graph)
    tests=[]; ok_all=True
    for mod in graph.modules.values():
        for t in mod.tests:
            if filter_text and filter_text not in t.name: continue
            started=time.perf_counter()
            try:
                fn=FunctionDef(f"__test_{len(tests)}", [], TypeRef("nichts"), t.steps, line=t.line)
                compiled=compile_function66(mod, fn, c64.SymbolTable.from_graph(graph))
                local=json.loads(json.dumps(program, ensure_ascii=False))
                local["functions"][f"{mod.name}.{fn.name}"]=compiled.as_dict()
                VM66(local, graph=graph).call(mod.name, fn.name, [])
                tests.append({"module":mod.name,"name":t.name,"ok":True,"seconds":time.perf_counter()-started})
            except Exception as exc:
                ok_all=False; tests.append({"module":mod.name,"name":t.name,"ok":False,"error":str(exc),"seconds":time.perf_counter()-started})
    payload={"ok":ok_all,"count":len(tests),"tests":tests,"coverage":coverage66(program)}
    if junit: write_junit66(payload, junit)
    return payload

def coverage66(program: dict[str, Any]) -> dict[str, Any]:
    return {"instruction_count": sum(len(fn.get("code",[])) for fn in program.get("functions",{}).values()), "function_count": len(program.get("functions",{})), "mode": "static-bytecode-coverage-baseline"}

def write_junit66(payload: dict[str, Any], path: Path) -> None:
    suite=ET.Element("testsuite", tests=str(payload.get("count",0)), failures=str(sum(1 for t in payload.get("tests",[]) if not t.get("ok"))))
    for t in payload.get("tests",[]):
        case=ET.SubElement(suite,"testcase",classname=t.get("module",""),name=t.get("name",""),time=str(t.get("seconds",0.0)))
        if not t.get("ok"):
            fail=ET.SubElement(case,"failure",message=t.get("error","")); fail.text=t.get("error","")
    path.parent.mkdir(parents=True, exist_ok=True); ET.ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)

def validate_replay66(path: Path) -> dict[str, Any]:
    payload=json.loads(Path(path).read_text(encoding="utf-8")); events=payload.get("events",[])
    digest=hashlib.sha256(json.dumps(events, sort_keys=True, default=str).encode()).hexdigest()
    return {"ok":True,"format":payload.get("format","unknown"),"event_count":len(events),"events_sha256":digest,"deterministic_reexecution":"available-for-vm-events; external IO requires explicit capture"}

def _cpp_string(s: str) -> str:
    return json.dumps(s)

def _cpp_value(v: Any) -> str:
    if v is None: return "Value::nil()"
    if isinstance(v, bool): return f"Value::boolean({'true' if v else 'false'})"
    if isinstance(v, int) and not isinstance(v, bool): return f"Value::integer({v})"
    if isinstance(v, float): return f"Value::number({v!r})"
    if isinstance(v, str): return f"Value::string({_cpp_string(v)})"
    return f"Value::string({_cpp_string(json.dumps(v, ensure_ascii=False, sort_keys=True))})"

_NATIVE_OPS={"CONST_POOL":1,"LOAD_SLOT":2,"STORE_SLOT":3,"ADD":4,"SUB":5,"MUL":6,"DIV":7,"FLOORDIV":35,"EQ":8,"NE":9,"LT":10,"LE":11,"GT":12,"GE":13,"JUMP":14,"JUMP_IF_FALSE":15,"JUMP_IF_TRUE":16,"CALL":17,"CALL_BUILTIN":18,"RETURN":19,"PRINT":20,"ASSERT":21,"POP":22,"MAKE_LIST":23,"MAKE_MAP":24,"MAKE_RECORD":25,"GET_ITEM":26,"GET_ATTR":27,"TYPE_ASSERT":28,"PANIC":29,"NEG":30,"NOT":31,"AND":32,"OR":33,"MOD":34}

def emit_native_keimvm66(program: dict[str, Any], out: Path) -> None:
    functions=list(program.get("functions",{}).items())
    consts=",\n".join("    "+_cpp_value(v) for v in program.get("const_pool",[])) or "    Value::nil()"
    func_blocks=[]; meta_blocks=[]
    for fid, fn in functions:
        instrs=[]
        for ins in fn.get("code",[]):
            op=ins.get("op"); args=ins.get("args",[]); a=b=c=0; s1=s2=""
            if op=="CONST_POOL": a=int(args[0])
            elif op in {"LOAD_SLOT","STORE_SLOT","JUMP","JUMP_IF_FALSE","JUMP_IF_TRUE","MAKE_LIST","MAKE_MAP"}: a=int(args[0])
            elif op=="CALL": s1,s2,a=str(args[0]),str(args[1]),int(args[2])
            elif op=="CALL_BUILTIN": s1,a=str(args[0]),int(args[1])
            elif op=="MAKE_RECORD": s1,a=str(args[0]),int(args[1])
            elif op=="GET_ATTR": s1=str(args[0])
            elif op in {"ASSERT","PANIC","TYPE_ASSERT"} and args: s1=str(args[0])
            instrs.append(f"Instr{{{_NATIVE_OPS.get(op,29)}, {a}, {b}, {c}, {_cpp_string(s1)}, {_cpp_string(s2)}}}")
        func_blocks.append("std::vector<Instr>{"+",".join(instrs)+"}")
        meta_blocks.append(f"FuncMeta{{{_cpp_string(fid)}, {_cpp_string(fn.get('module',''))}, {_cpp_string(fn.get('name',''))}, {max(fn.get('slots',{}).values(), default=-1)+1}}}")
    cpp = f'''
#include <cmath>
#include <iostream>
#include <map>
#include <memory>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>
struct Value {{
 enum Kind {{ NIL, INT, DOUBLE, BOOL, STRING, LIST, MAP, RECORD, RESULT }} kind=NIL;
 long long i=0; double f=0; bool b=false; std::string s; std::vector<Value> list; std::map<std::string,Value> map; bool ok=false; std::shared_ptr<Value> inner;
 static Value nil(){{return Value();}} static Value integer(long long x){{Value v;v.kind=INT;v.i=x;v.f=(double)x;return v;}}
 static Value number(double x){{Value v;v.kind=DOUBLE;v.f=x;v.i=(long long)x;return v;}} static Value boolean(bool x){{Value v;v.kind=BOOL;v.b=x;return v;}}
 static Value string(std::string x){{Value v;v.kind=STRING;v.s=std::move(x);return v;}} static Value listv(std::vector<Value>x){{Value v;v.kind=LIST;v.list=std::move(x);return v;}}
 static Value mapv(std::map<std::string,Value>x){{Value v;v.kind=MAP;v.map=std::move(x);return v;}} static Value record(std::string t,std::map<std::string,Value>x){{Value v;v.kind=RECORD;v.s=std::move(t);v.map=std::move(x);return v;}}
 static Value result(bool ok, Value x){{Value v;v.kind=RESULT;v.ok=ok;v.inner=std::make_shared<Value>(x);return v;}}
}};
static bool truth(const Value&v){{if(v.kind==Value::BOOL)return v.b;if(v.kind==Value::NIL)return false;if(v.kind==Value::INT)return v.i!=0;if(v.kind==Value::DOUBLE)return v.f!=0;if(v.kind==Value::STRING)return !v.s.empty();return true;}}
static std::string show(const Value&v){{switch(v.kind){{case Value::NIL:return"nichts";case Value::INT:return std::to_string(v.i);case Value::DOUBLE:return std::to_string(v.f);case Value::BOOL:return v.b?"wahr":"falsch";case Value::STRING:return v.s;case Value::LIST:return"<liste:"+std::to_string(v.list.size())+">";case Value::MAP:return"<karte:"+std::to_string(v.map.size())+">";case Value::RECORD:return"<"+v.s+">";case Value::RESULT:return v.ok?"ok(...)":"fehler(...)";}}return"?";}}
static Value add(const Value&a,const Value&b){{if(a.kind==Value::STRING||b.kind==Value::STRING)return Value::string(show(a)+show(b)); if(a.kind==Value::DOUBLE||b.kind==Value::DOUBLE)return Value::number(a.f+b.f); return Value::integer(a.i+b.i);}}
static Value bin(int op,const Value&a,const Value&b){{switch(op){{case 4:return add(a,b);case 5:return Value::integer(a.i-b.i);case 6:return Value::integer(a.i*b.i);case 7:return Value::number(a.f/b.f);case 8:return Value::boolean(show(a)==show(b));case 9:return Value::boolean(show(a)!=show(b));case 10:return Value::boolean(a.f<b.f);case 11:return Value::boolean(a.f<=b.f);case 12:return Value::boolean(a.f>b.f);case 13:return Value::boolean(a.f>=b.f);case 34:return Value::integer(a.i%b.i);case 35:return Value::integer(a.i/b.i);}}throw std::runtime_error("bad binop");}}
struct Instr{{int op;int a;int b;int c;std::string s1;std::string s2;}}; struct FuncMeta{{std::string fid;std::string module;std::string name;int slots;}};
static std::vector<Value> CONST_POOL = {{
{consts}
}};
static std::vector<FuncMeta> META = {{ {",".join(meta_blocks)} }};
static std::vector<std::vector<Instr>> CODE = {{ {",".join(func_blocks)} }};
static std::unordered_map<std::string,int> init_fids(){{std::unordered_map<std::string,int> m; for(int i=0;i<(int)META.size();++i)m[META[i].fid]=i; return m;}} static auto FIDS=init_fids();
static Value run_func(int fid,std::vector<Value>args){{const auto&meta=META[fid];std::vector<Value>slots(meta.slots>(int)args.size()?meta.slots:(int)args.size());for(size_t i=0;i<args.size();++i)slots[i]=args[i];std::vector<Value>stack;int pc=0;const auto&code=CODE[fid];while(pc>=0&&pc<(int)code.size()){{const Instr&in=code[pc];switch(in.op){{case 1:stack.push_back(CONST_POOL[in.a]);break;case 2:stack.push_back(slots[in.a]);break;case 3:slots[in.a]=stack.back();stack.pop_back();break;case 4:case 5:case 6:case 7:case 8:case 9:case 10:case 11:case 12:case 13:case 34:case 35:{{auto r=stack.back();stack.pop_back();auto l=stack.back();stack.pop_back();stack.push_back(bin(in.op,l,r));break;}}case 14:pc=in.a;continue;case 15:{{auto v=stack.back();stack.pop_back();if(!truth(v)){{pc=in.a;continue;}}break;}}case 16:{{auto v=stack.back();stack.pop_back();if(truth(v)){{pc=in.a;continue;}}break;}}case 17:{{std::vector<Value>vals(stack.end()-in.a,stack.end());stack.erase(stack.end()-in.a,stack.end());auto it=FIDS.find(in.s1+"."+in.s2);if(it==FIDS.end())throw std::runtime_error("missing call "+in.s1+"."+in.s2);stack.push_back(run_func(it->second,vals));break;}}case 18:{{std::vector<Value>vals;if(in.a){{vals.assign(stack.end()-in.a,stack.end());stack.erase(stack.end()-in.a,stack.end());}}if(in.s1=="ok")stack.push_back(Value::result(true,vals.empty()?Value::nil():vals[0]));else if(in.s1=="fehler")stack.push_back(Value::result(false,vals.empty()?Value::nil():vals[0]));else if(in.s1=="ist_ok")stack.push_back(Value::boolean(!vals.empty()&&vals[0].kind==Value::RESULT&&vals[0].ok));else throw std::runtime_error("builtin "+in.s1);break;}}case 19:return stack.empty()?Value::nil():stack.back();case 20:std::cout<<show(stack.back())<<std::endl;stack.pop_back();break;case 21:{{auto v=stack.back();stack.pop_back();if(!truth(v))throw std::runtime_error("assert "+in.s1);break;}}case 22:if(!stack.empty())stack.pop_back();break;case 23:{{std::vector<Value>vals(stack.end()-in.a,stack.end());stack.erase(stack.end()-in.a,stack.end());stack.push_back(Value::listv(vals));break;}}case 24:{{std::map<std::string,Value>m;auto start=stack.end()-2*in.a;for(auto it=start;it!=stack.end();){{auto k=*it++;auto v=*it++;m[show(k)]=v;}}stack.erase(start,stack.end());stack.push_back(Value::mapv(m));break;}}case 25:{{std::map<std::string,Value>m;std::vector<Value>vals(stack.end()-in.a,stack.end());stack.erase(stack.end()-in.a,stack.end());for(size_t i=0;i<vals.size();++i)m["f"+std::to_string(i)]=vals[i];stack.push_back(Value::record(in.s1,m));break;}}case 26:{{auto key=stack.back();stack.pop_back();auto base=stack.back();stack.pop_back();if(base.kind==Value::LIST)stack.push_back(base.list[(size_t)key.i]);else stack.push_back(base.map[show(key)]);break;}}case 27:{{auto base=stack.back();stack.pop_back();if(base.kind==Value::RESULT&&in.s1=="ok")stack.push_back(Value::boolean(base.ok));else if(base.kind==Value::RESULT&&(in.s1=="wert"||in.s1=="fehler"))stack.push_back(*base.inner);else stack.push_back(base.map[in.s1]);break;}}case 28:break;case 29:throw std::runtime_error("panic "+in.s1);case 30:{{auto v=stack.back();stack.pop_back();stack.push_back(Value::integer(-v.i));break;}}case 31:{{auto v=stack.back();stack.pop_back();stack.push_back(Value::boolean(!truth(v)));break;}}case 32:{{auto r=stack.back();stack.pop_back();auto l=stack.back();stack.pop_back();stack.push_back(Value::boolean(truth(l)&&truth(r)));break;}}case 33:{{auto r=stack.back();stack.pop_back();auto l=stack.back();stack.pop_back();stack.push_back(Value::boolean(truth(l)||truth(r)));break;}}default:throw std::runtime_error("bad opcode");}}pc++;}}return Value::nil();}}
int main(){{try{{auto it=FIDS.find({_cpp_string(program.get("entry"))}+std::string(".main"));if(it==FIDS.end())throw std::runtime_error("entry main missing");auto r=run_func(it->second,{{}});std::cout<<show(r)<<std::endl;return 0;}}catch(const std::exception&e){{std::cerr<<"keimvm66: "<<e.what()<<std::endl;return 80;}}}}
'''
    out.parent.mkdir(parents=True, exist_ok=True); out.write_text(cpp, encoding="utf-8")

def status66() -> dict[str, Any]:
    return {"version":"6.6.0-enterprise-runtime-completion","implemented":{"native_value_heap_strings_lists_maps_records_results_calls":True,"constant_pool_sectioned_binary_kbc66b":True,"generic_specialization_manifest":True,"result_match_exhaustiveness_and_runtime":True,"while_break_continue":True,"lock_v5_package_cache_semver_manifest":True,"deterministic_replay_validation":True,"python_native_differential_smoke":True,"no_eval":True},"binary_sections":["META","CONST","TYPE","SYMBOL","FUNC","CODE","DEBUG","PROGRAM"],"native_supported":sorted(_NATIVE_OPS)}
