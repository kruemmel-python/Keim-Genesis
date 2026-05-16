
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import hashlib
import json
import struct
import time

from .foundation import ModuleGraph, ModuleDef, FunctionDef, Step, TypeRef, Diagnostic, CheckReport, FoundationError
from . import compiler64 as c64

KBC65_MAGIC = b"KBC65B\x00\x01"
KBC65_VERSION = 650


def _is_typevar(t: TypeRef) -> bool:
    return bool(t.name) and (t.name[0].isupper() or t.name.startswith("'")) and not t.args


def _subst_type(t: TypeRef, subst: dict[str, TypeRef]) -> TypeRef:
    if _is_typevar(t) and t.name in subst:
        return subst[t.name]
    if not t.args:
        return t
    return TypeRef(t.name, tuple(_subst_type(a, subst) for a in t.args))


def _unify(want: TypeRef, got: TypeRef, subst: dict[str, TypeRef]) -> bool:
    if _is_typevar(want):
        old = subst.get(want.name)
        if old is None:
            subst[want.name] = got
            return True
        return c64.same_type(old, got)
    if _is_typevar(got):
        old = subst.get(got.name)
        if old is None:
            subst[got.name] = want
            return True
        return c64.same_type(old, want)
    if want.name in {"beliebig", "any"} or got.name in {"beliebig", "any"}:
        return True
    if want.name in {"zahl", "kommazahl"} and got.name in {"ganzzahl", "kommazahl", "zahl"}:
        return True
    if got.name in {"zahl", "kommazahl"} and want.name in {"ganzzahl", "kommazahl", "zahl"}:
        return True
    if want.name != got.name or len(want.args) != len(got.args):
        return False
    return all(_unify(w, g, subst) for w, g in zip(want.args, got.args))


def check_sig65(name: str, sig: c64.FunctionSig, args: list[TypeRef]) -> dict[str, TypeRef]:
    if len(args) != len(sig.params):
        raise c64.KeimTypeError(f"{name} erwartet {len(sig.params)} Argumente, bekam {len(args)}")
    subst: dict[str, TypeRef] = {}
    for i, (got, (_, want)) in enumerate(zip(args, sig.params), 1):
        if not _unify(want, got, subst):
            raise c64.KeimTypeError(f"{name} Argument {i} erwartet {want}, bekam {got}")
    return subst


def infer_call65(e: c64.CallExpr, env: c64.TypeEnv64) -> TypeRef:
    args = [infer_expr65(a.expr, env) for a in e.args]
    callee = e.callee
    if isinstance(callee, c64.NameExpr):
        name = callee.name
        if name == "ok":
            return TypeRef("ergebnis", (args[0] if args else TypeRef("nichts"), TypeRef("text")))
        if name == "fehler":
            return TypeRef("ergebnis", (TypeRef("beliebig"), args[0] if args else TypeRef("text")))
        if name == "ist_ok":
            if not args or args[0].name != "ergebnis":
                raise c64.KeimTypeError("ist_ok erwartet ergebnis<T,E>")
            return TypeRef("bool")
        if name == "kanal":
            return TypeRef("kanal", (TypeRef("beliebig"),))
        if name == "empfange":
            if not args or args[0].name != "kanal":
                raise c64.KeimTypeError("empfange erwartet kanal<T>")
            return args[0].args[0] if args[0].args else TypeRef("beliebig")
        ms = env.table.modules[env.module]
        if name in ms.types:
            td = ms.types[name]
            named = {a.name: infer_expr65(a.expr, env) for a in e.args if a.name}
            if named:
                for f in td.fields:
                    if f.name not in named:
                        raise c64.KeimTypeError(f"Record {name}: Feld {f.name} fehlt")
                    if not _unify(f.typ, named[f.name], {}):
                        raise c64.KeimTypeError(f"{name}.{f.name} erwartet {f.typ}, bekam {named[f.name]}")
            elif len(args) != len(td.fields):
                raise c64.KeimTypeError(f"Record {name} erwartet {len(td.fields)} Felder, bekam {len(args)}")
            else:
                for f, got in zip(td.fields, args):
                    if not _unify(f.typ, got, {}):
                        raise c64.KeimTypeError(f"{name}.{f.name} erwartet {f.typ}, bekam {got}")
            return TypeRef(name)
        if name not in ms.functions:
            raise c64.KeimTypeError(f"Unbekannte Funktion {name}")
        sig = ms.functions[name]
        subst = check_sig65(name, sig, args)
        return _subst_type(sig.returns, subst)
    if isinstance(callee, c64.AttrExpr) and isinstance(callee.base, c64.NameExpr):
        alias = callee.base.name
        ms = env.table.modules[env.module]
        if alias not in ms.imports:
            raise c64.KeimTypeError(f"Unbekannter Import-Alias {alias}")
        target = ms.imports[alias]
        tms = env.table.modules[target]
        name = callee.attr
        if name not in tms.exports:
            raise c64.KeimTypeError(f"{target}.{name} ist nicht exportiert")
        if name not in tms.functions:
            raise c64.KeimTypeError(f"{target}.{name} ist keine Funktion")
        sig = tms.functions[name]
        subst = check_sig65(f"{target}.{name}", sig, args)
        return _subst_type(sig.returns, subst)
    raise c64.KeimTypeError("Dynamische Calls sind nicht erlaubt")


def infer_expr65(e: c64.Expr, env: c64.TypeEnv64) -> TypeRef:
    if isinstance(e, c64.CallExpr):
        return infer_call65(e, env)
    if isinstance(e, c64.ListExpr):
        return TypeRef("liste", (c64.common_type(infer_expr65(x, env) for x in e.items),))
    if isinstance(e, c64.MapExpr):
        return TypeRef("karte", (
            c64.common_type(infer_expr65(k, env) for k, _ in e.items),
            c64.common_type(infer_expr65(v, env) for _, v in e.items),
        ))
    if isinstance(e, c64.IndexExpr):
        bt = infer_expr65(e.base, env)
        it = infer_expr65(e.index, env)
        if bt.name == "liste":
            if not c64.same_type(it, TypeRef("ganzzahl")):
                raise c64.KeimTypeError("Listenindex muss ganzzahl sein")
            return bt.args[0] if bt.args else TypeRef("beliebig")
        if bt.name == "karte":
            if bt.args and not _unify(bt.args[0], it, {}):
                raise c64.KeimTypeError(f"Kartenindex erwartet {bt.args[0]}, bekam {it}")
            return bt.args[1] if len(bt.args) > 1 else TypeRef("beliebig")
        raise c64.KeimTypeError(f"Indexzugriff auf Nicht-Container {bt}")
    if isinstance(e, c64.AttrExpr):
        bt = infer_expr65(e.base, env)
        if bt.name == "ergebnis":
            if e.attr == "ok":
                return TypeRef("bool")
            if e.attr == "wert":
                return bt.args[0] if bt.args else TypeRef("beliebig")
            if e.attr == "fehler":
                return bt.args[1] if len(bt.args) > 1 else TypeRef("beliebig")
        return c64.infer_expr(e, env)
    old = c64.infer_call
    try:
        c64.infer_call = infer_call65
        return c64.infer_expr(e, env)
    finally:
        c64.infer_call = old


def emit_expr65(e: c64.Expr, env: c64.TypeEnv64, b: c64.CodeBuilder) -> None:
    old = c64.emit_call64
    try:
        c64.emit_call64 = emit_call65
        c64.emit_expr64(e, env, b)
    finally:
        c64.emit_call64 = old


def emit_call65(e: c64.CallExpr, env: c64.TypeEnv64, b: c64.CodeBuilder) -> None:
    c = e.callee
    if isinstance(c, c64.NameExpr):
        name = c.name
        if name == "ist_ok":
            for a in e.args:
                emit_expr65(a.expr, env, b)
            b.emit("RESULT_IS_OK", line=e.pos.line, col=e.pos.col)
            return
        if name in env.table.modules[env.module].types:
            td = env.table.modules[env.module].types[name]
            named = {a.name: a.expr for a in e.args if a.name}
            if named:
                for f in td.fields:
                    emit_expr65(named[f.name], env, b)
            else:
                for a in e.args:
                    emit_expr65(a.expr, env, b)
            b.emit("MAKE_RECORD", name, len(td.fields), line=e.pos.line, col=e.pos.col)
            return
        for a in e.args:
            emit_expr65(a.expr, env, b)
        if name in {"ok", "fehler", "kanal", "empfange"}:
            b.emit("CALL_BUILTIN", name, len(e.args), line=e.pos.line, col=e.pos.col)
        else:
            b.emit("CALL", env.module, name, len(e.args), line=e.pos.line, col=e.pos.col)
        return
    if isinstance(c, c64.AttrExpr) and isinstance(c.base, c64.NameExpr):
        module = env.table.modules[env.module].imports[c.base.name]
        for a in e.args:
            emit_expr65(a.expr, env, b)
        b.emit("CALL", module, c.attr, len(e.args), line=e.pos.line, col=e.pos.col)
        return
    raise c64.KeimTypeError("Dynamischer Call nicht erlaubt")


def compile_function65(mod: ModuleDef, fn: FunctionDef, table: c64.SymbolTable) -> c64.Function64:
    scope = c64.ScopeLayout64()
    for p in fn.params:
        scope.declare(p.name, p.typ)
    env = c64.TypeEnv64(mod.name, table, scope)
    b = c64.CodeBuilder()
    returned = compile_steps65(fn.steps, mod, fn, env, b)
    if fn.returns.name not in {"nichts", "void"} and not returned:
        raise c64.KeimTypeError(f"Funktion {fn.name} gibt nicht garantiert zurück")
    code = b.finalize()
    return c64.Function64(
        mod.name, fn.name,
        [{"name": p.name, "type": str(p.typ), "slot": scope.names[p.name]} for p in fn.params],
        str(fn.returns), dict(scope.names),
        {str(k): str(v) for k, v in scope.types.items()},
        code, c64.compute_max_stack(code), fn.name in mod.exports
    )


def _declare_or_reuse(scope: c64.ScopeLayout64, name: str, typ: TypeRef) -> int:
    if name in scope.names:
        return scope.resolve(name)
    return scope.declare(name, typ)


def _result_payload_type(t: TypeRef, kind: str) -> TypeRef:
    if t.name != "ergebnis":
        return TypeRef("beliebig")
    if kind == "ok":
        return t.args[0] if t.args else TypeRef("beliebig")
    return t.args[1] if len(t.args) > 1 else TypeRef("beliebig")


def _emit_result_case_bind(tmp_slot: int, bind: str | None, kind: str, env: c64.TypeEnv64, b: c64.CodeBuilder, line: int) -> None:
    if not bind:
        return
    src_t = env.scope.types[tmp_slot]
    payload_t = _result_payload_type(src_t, kind)
    slot = _declare_or_reuse(env.scope, bind, payload_t)
    b.emit("LOAD_SLOT", tmp_slot, line=line)
    b.emit("GET_ATTR", "wert" if kind == "ok" else "fehler", line=line)
    b.emit("STORE_SLOT", slot, line=line)


def compile_match65(st: Step, mod: ModuleDef, fn: FunctionDef, env: c64.TypeEnv64, b: c64.CodeBuilder) -> bool:
    expr_s, cases = st.args
    expr = c64.parse_keim_expr(expr_s, line=st.line)
    expr_t = infer_expr65(expr, env)
    if expr_t.name != "ergebnis":
        raise c64.KeimTypeError(f"Zeile {st.line}: match erwartet ergebnis<T,E>, bekam {expr_t}")
    tmp_name = f"__match_{st.line}_{len(env.scope.names)}"
    tmp_slot = env.scope.declare(tmp_name, expr_t)
    emit_expr65(expr, env, b)
    b.emit("STORE_SLOT", tmp_slot, line=st.line)

    end = b.label("match_end")
    returned_cases: list[bool] = []
    has_ok = has_err = has_any = False

    for kind, bind, body, line_no in cases:
        next_case = b.label("next_case")
        if kind == "ok":
            has_ok = True
            b.emit("LOAD_SLOT", tmp_slot, line=line_no)
            b.emit("GET_ATTR", "ok", line=line_no)
            b.jump("JUMP_IF_FALSE", next_case, line=line_no)
            _emit_result_case_bind(tmp_slot, bind, "ok", env, b, line_no)
            returned_cases.append(compile_steps65(body, mod, fn, env, b))
            b.jump("JUMP", end, line=line_no)
            b.mark(next_case)
        elif kind == "fehler":
            has_err = True
            b.emit("LOAD_SLOT", tmp_slot, line=line_no)
            b.emit("GET_ATTR", "ok", line=line_no)
            b.jump("JUMP_IF_TRUE", next_case, line=line_no)
            _emit_result_case_bind(tmp_slot, bind, "fehler", env, b, line_no)
            returned_cases.append(compile_steps65(body, mod, fn, env, b))
            b.jump("JUMP", end, line=line_no)
            b.mark(next_case)
        elif kind in {"_", "sonst"}:
            has_any = True
            returned_cases.append(compile_steps65(body, mod, fn, env, b))
            b.jump("JUMP", end, line=line_no)
        else:
            raise c64.KeimTypeError(f"Zeile {line_no}: unbekanntes match-Muster {kind}")
    b.emit("PANIC", f"Nicht erschöpfendes match in Zeile {st.line}", line=st.line)
    b.mark(end)
    if not has_any and not (has_ok and has_err):
        raise c64.KeimTypeError(f"Zeile {st.line}: match auf ergebnis<T,E> braucht ok- und fehler-Fall oder '_'")
    return bool(returned_cases) and all(returned_cases)


def compile_steps65(steps: list[Step], mod: ModuleDef, fn: FunctionDef, env: c64.TypeEnv64, b: c64.CodeBuilder) -> bool:
    returned = False
    for st in steps:
        match st.op:
            case "let":
                name, typ, es = st.args
                e = c64.parse_keim_expr(es, line=st.line)
                got = infer_expr65(e, env)
                if not _unify(typ, got, {}):
                    raise c64.KeimTypeError(f"Zeile {st.line}: {name} erwartet {typ}, bekam {got}")
                concrete = got if _is_typevar(typ) else typ
                slot = env.scope.declare(name, concrete)
                emit_expr65(e, env, b)
                b.emit("TYPE_ASSERT", str(concrete), line=st.line)
                b.emit("STORE_SLOT", slot, line=st.line)
            case "set":
                name, es = st.args
                slot = env.scope.resolve(name)
                e = c64.parse_keim_expr(es, line=st.line)
                got = infer_expr65(e, env)
                want = env.scope.types[slot]
                if not _unify(want, got, {}):
                    raise c64.KeimTypeError(f"Zeile {st.line}: {name} erwartet {want}, bekam {got}")
                emit_expr65(e, env, b)
                b.emit("TYPE_ASSERT", str(want), line=st.line)
                b.emit("STORE_SLOT", slot, line=st.line)
            case "return":
                e = c64.parse_keim_expr(st.args[0], line=st.line)
                got = infer_expr65(e, env)
                if not _unify(fn.returns, got, {}):
                    raise c64.KeimTypeError(f"Zeile {st.line}: Rückgabe erwartet {fn.returns}, bekam {got}")
                emit_expr65(e, env, b)
                b.emit("RETURN", line=st.line)
                returned = True
            case "print":
                e = c64.parse_keim_expr(st.args[0], line=st.line)
                infer_expr65(e, env)
                emit_expr65(e, env, b)
                b.emit("PRINT", line=st.line)
            case "assert":
                e = c64.parse_keim_expr(st.args[0], line=st.line)
                got = infer_expr65(e, env)
                if not _unify(TypeRef("bool"), got, {}):
                    raise c64.KeimTypeError(f"Zeile {st.line}: pruefe erwartet bool, bekam {got}")
                emit_expr65(e, env, b)
                b.emit("ASSERT", st.args[0], line=st.line)
            case "expr":
                e = c64.parse_keim_expr(st.args[0], line=st.line)
                infer_expr65(e, env)
                emit_expr65(e, env, b)
                b.emit("POP", line=st.line)
            case "if":
                cond_s, then, els = st.args
                ce = c64.parse_keim_expr(cond_s, line=st.line)
                ct = infer_expr65(ce, env)
                if not _unify(TypeRef("bool"), ct, {}):
                    raise c64.KeimTypeError(f"Zeile {st.line}: wenn erwartet bool, bekam {ct}")
                else_l = b.label("else")
                end = b.label("endif")
                emit_expr65(ce, env, b)
                b.jump("JUMP_IF_FALSE", else_l, line=st.line)
                rt = compile_steps65(then, mod, fn, env, b)
                b.jump("JUMP", end, line=st.line)
                b.mark(else_l)
                retn = compile_steps65(els, mod, fn, env, b) if els else False
                b.mark(end)
                returned = returned or (rt and retn)
            case "match":
                returned = returned or compile_match65(st, mod, fn, env, b)
            case "snapshot_save":
                b.emit("SNAPSHOT_SAVE", st.args[0], line=st.line)
            case "snapshot_load":
                b.emit("SNAPSHOT_LOAD", st.args[0], line=st.line)
            case "replay_mark":
                b.emit("REPLAY_MARK", st.args[0], line=st.line)
            case "send":
                target, es = st.args
                slot = env.scope.resolve(target)
                if env.scope.types[slot].name != "kanal":
                    raise c64.KeimTypeError(f"Zeile {st.line}: sende-Ziel ist kein kanal")
                e = c64.parse_keim_expr(es, line=st.line)
                emit_expr65(c64.NameExpr(c64.SourcePos(st.line, 1), target), env, b)
                emit_expr65(e, env, b)
                b.emit("CHANNEL_SEND", line=st.line)
            case "expect_error":
                try:
                    compile_steps65(st.args[0], mod, fn, env, b)
                except FoundationError:
                    b.emit("CONST", True, line=st.line)
                    b.emit("POP", line=st.line)
            case _:
                raise c64.KeimTypeError(f"Zeile {st.line}: Unsupported Step {st.op}")
    return returned


_VALID65 = set(c64._VALID_OPS) | {"JUMP_IF_TRUE", "RESULT_IS_OK", "PANIC"}


def compile_program65(graph: ModuleGraph) -> c64.Program64:
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
        for i in m.imports:
            if i.module not in graph.modules:
                diags.append(Diagnostic("error", f"Import nicht gefunden: {i.module}", i.line, m.name))
    for m in graph.modules.values():
        for fn in m.functions.values():
            try:
                funcs[f"{m.name}.{fn.name}"] = compile_function65(m, fn, table)
            except FoundationError as exc:
                diags.append(Diagnostic("error", f"{fn.name}: {exc}", fn.line, m.name))
    p = c64.Program64("keim-linear-bytecode", KBC65_VERSION, graph.entry_module().name, modules, funcs, diags)
    diags.extend(verify_program65(p))
    return p


def verify_program65(p: c64.Program64) -> list[Diagnostic]:
    ds: list[Diagnostic] = []
    if p.format != "keim-linear-bytecode":
        ds.append(Diagnostic("error", "falsches v6.5 Format", 0))
    if int(p.version) < KBC65_VERSION:
        ds.append(Diagnostic("error", f"Bytecode-Version {p.version} ist nicht v6.5", 0))
    for fid, fn in p.functions.items():
        for pc, i in enumerate(fn.code):
            if i.op == "EVAL":
                ds.append(Diagnostic("error", f"{fid}: EVAL verboten", i.line))
            if i.op not in _VALID65:
                ds.append(Diagnostic("error", f"{fid}: unbekannter Opcode {i.op}", i.line))
            if i.op in {"JUMP", "JUMP_IF_FALSE", "JUMP_IF_TRUE"} and (not isinstance(i.args[0], int) or i.args[0] < 0 or i.args[0] > len(fn.code)):
                ds.append(Diagnostic("error", f"{fid}: ungültiges Sprungziel {i.args[0]}", i.line))
            if i.op == "CALL" and f"{i.args[0]}.{i.args[1]}" not in p.functions:
                ds.append(Diagnostic("error", f"{fid}: Call-Ziel fehlt {i.args[0]}.{i.args[1]}", i.line))
    return ds


class VM65(c64.VM64):
    def __init__(self, program: c64.Program64 | dict[str, Any], graph: ModuleGraph | None = None, *, record: Path | None = None):
        self.program = program if isinstance(program, c64.Program64) else c64.program64_from_dict(program)
        self.graph = graph
        self.output: list[str] = []
        self.events: list[dict[str, Any]] = []
        self.frames: list[c64.Frame64] = []
        self.record = record
        errs = verify_program65(self.program)
        if any(d.severity == "error" for d in errs):
            raise c64.KeimVerifyError(CheckReport(False, [], errs).format())

    def exec(self, fn: c64.Function64, frame: c64.Frame64) -> Any:
        stack: list[Any] = []
        pc = 0
        while pc < len(fn.code):
            i = fn.code[pc]
            op = i.op
            if op == "JUMP_IF_TRUE":
                if bool(stack.pop()):
                    pc = i.args[0]
                    continue
            elif op == "RESULT_IS_OK":
                r = stack.pop()
                stack.append(bool(r.get("ok")) if isinstance(r, dict) else False)
            elif op == "PANIC":
                raise FoundationError(str(i.args[0]) if i.args else "panic")
            else:
                if op == "CONST": stack.append(i.args[0])
                elif op == "LOAD_SLOT": stack.append(frame.slots[i.args[0]])
                elif op == "STORE_SLOT":
                    s = i.args[0]
                    if s >= len(frame.slots): frame.slots.extend([None] * (s - len(frame.slots) + 1))
                    frame.slots[s] = stack.pop(); self.event("store", slot=s, value=frame.slots[s])
                elif op == "TYPE_ASSERT": pass
                elif op in {"ADD","SUB","MUL","DIV","FLOORDIV","MOD","EQ","NE","LT","LE","GT","GE","AND","OR"}:
                    b = stack.pop(); a = stack.pop(); stack.append(c64.eval_bin(op, a, b))
                elif op == "NEG": stack.append(-stack.pop())
                elif op == "NOT": stack.append(not stack.pop())
                elif op == "MAKE_LIST":
                    n = i.args[0]; vals = stack[-n:] if n else []
                    if n: del stack[-n:]
                    stack.append(list(vals))
                elif op == "MAKE_MAP":
                    n = i.args[0]; vals = stack[-2*n:] if n else []
                    if n: del stack[-2*n:]
                    it = iter(vals); stack.append({k:v for k,v in zip(it,it)})
                elif op == "MAKE_RECORD":
                    name, argc = i.args; vals = stack[-argc:] if argc else []
                    if argc: del stack[-argc:]
                    fields = self.program.modules[frame.module]["types"][name]["fields"]
                    stack.append({"__typ__": name, **{f["name"]: v for f, v in zip(fields, vals)}})
                elif op == "GET_ITEM":
                    ix = stack.pop(); base = stack.pop(); stack.append(base[ix])
                elif op == "GET_ATTR":
                    attr = i.args[0]; base = stack.pop()
                    stack.append(base[attr] if isinstance(base, dict) else getattr(base, attr))
                elif op == "CALL":
                    mod, name, argc = i.args; vals = stack[-argc:] if argc else []
                    if argc: del stack[-argc:]
                    stack.append(self.call(mod, name, list(vals)))
                elif op == "CALL_BUILTIN":
                    name, argc = i.args; vals = stack[-argc:] if argc else []
                    if argc: del stack[-argc:]
                    stack.append(self.builtin(name, list(vals)))
                elif op == "CHANNEL_SEND":
                    val = stack.pop(); ch = stack.pop()
                    if not isinstance(ch, c64.Channel64): raise FoundationError("sende erwartet kanal")
                    ch.queue.append(val); self.event("channel_send", value=val)
                elif op == "PRINT":
                    v = stack.pop(); self.output.append(str(v)); print(v)
                elif op == "ASSERT":
                    if not bool(stack.pop()): raise FoundationError(f"Assertion fehlgeschlagen: {i.args[0] if i.args else ''}")
                elif op == "POP": stack.pop()
                elif op == "JUMP": pc = i.args[0]; continue
                elif op == "JUMP_IF_FALSE":
                    if not stack.pop(): pc = i.args[0]; continue
                elif op == "RETURN": return stack.pop() if stack else None
                elif op == "SNAPSHOT_SAVE": self.save_snapshot(Path(i.args[0]))
                elif op == "SNAPSHOT_LOAD": self.load_snapshot(Path(i.args[0]))
                elif op == "REPLAY_MARK": self.event("mark", name=i.args[0])
                else: raise FoundationError(f"VM65 unbekannter Opcode {op}")
            pc += 1
        return None

    def builtin(self, name: str, args: list[Any]) -> Any:
        if name == "ist_ok":
            return bool(args and isinstance(args[0], dict) and args[0].get("ok"))
        return super().builtin(name, args)


def encode_kbc65b(program: c64.Program64 | dict[str, Any]) -> bytes:
    d = program.as_dict() if isinstance(program, c64.Program64) else program
    if int(d.get("version", 0)) < KBC65_VERSION:
        d = dict(d); d["version"] = KBC65_VERSION
    payload = json.dumps(d, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(payload).digest()
    return KBC65_MAGIC + struct.pack("<IQ", KBC65_VERSION, len(payload)) + digest + payload


def decode_kbc65b(data: bytes) -> dict[str, Any]:
    if not data.startswith(KBC65_MAGIC):
        raise FoundationError("Keine KBC65B-Datei: falsche Magic")
    off = len(KBC65_MAGIC)
    version, size = struct.unpack("<IQ", data[off:off+12])
    off += 12
    digest = data[off:off+32]
    off += 32
    payload = data[off:off+size]
    if len(payload) != size:
        raise FoundationError("KBC65B-Datei ist abgeschnitten")
    if hashlib.sha256(payload).digest() != digest:
        raise FoundationError("KBC65B-Hashprüfung fehlgeschlagen")
    d = json.loads(payload.decode("utf-8"))
    if version < KBC65_VERSION or int(d.get("version", 0)) < KBC65_VERSION:
        raise FoundationError("KBC65B-Version ist zu alt")
    return d


def write_kbc65b(program: c64.Program64, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encode_kbc65b(program))


def read_kbc65b(path: Path) -> c64.Program64:
    return c64.program64_from_dict(decode_kbc65b(path.read_bytes()))


def check65(path: Path) -> CheckReport:
    g = ModuleGraph(path).load()
    p = compile_program65(g)
    return CheckReport(not any(d.severity == "error" for d in p.diagnostics), sorted(g.modules), p.diagnostics)


def run65(path: Path, *, record: Path | None = None) -> c64.VM64Result:
    g = ModuleGraph(path).load()
    p = compile_program65(g)
    if any(d.severity == "error" for d in p.diagnostics):
        raise FoundationError(CheckReport(False, sorted(g.modules), p.diagnostics).format())
    return VM65(p, g, record=record).run_main()


def bytecode65(path: Path) -> c64.Program64:
    g = ModuleGraph(path).load()
    p = compile_program65(g)
    if any(d.severity == "error" for d in p.diagnostics):
        raise FoundationError(CheckReport(False, sorted(g.modules), p.diagnostics).format())
    return p


def build65(cwd: Path, out: Path) -> dict[str, Any]:
    pr = c64.Project64.load(cwd)
    p = bytecode65(pr.main)
    out.mkdir(parents=True, exist_ok=True)
    (out / "app.kbc65.json").write_text(json.dumps(p.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    write_kbc65b(p, out / "app.kbc65b")
    lock = pr.lock()
    lock["format"] = "keim-lock-v5"
    lock["binary_bytecode"] = {"file": "app.kbc65b", "sha256": hashlib.sha256((out / "app.kbc65b").read_bytes()).hexdigest()}
    (out / "keim.lock").write_text(json.dumps(lock, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "out": str(out), "json": "app.kbc65.json", "binary": "app.kbc65b", "lock": "keim.lock"}


def run_kbc65b(path: Path) -> c64.VM64Result:
    p = read_kbc65b(path)
    return VM65(p).run_main()


def test65(path: Path, *, junit: Path | None = None) -> dict[str, Any]:
    g = ModuleGraph(path).load()
    p = compile_program65(g)
    if any(d.severity == "error" for d in p.diagnostics):
        return {"ok": False, "diagnostics": [d.as_dict() for d in p.diagnostics], "tests": []}
    table = c64.SymbolTable.from_graph(g)
    tests = []
    ok = True
    for m in g.modules.values():
        for t in m.tests:
            start = time.perf_counter()
            try:
                fn = FunctionDef(f"__test65_{len(tests)}", [], TypeRef("nichts"), t.steps)
                f65 = compile_function65(m, fn, table)
                p.functions[f"{m.name}.{fn.name}"] = f65
                VM65(p, g).call(m.name, fn.name, [])
                tests.append({"module": m.name, "name": t.name, "ok": True, "seconds": time.perf_counter() - start})
            except Exception as exc:
                ok = False
                tests.append({"module": m.name, "name": t.name, "ok": False, "error": str(exc), "seconds": time.perf_counter() - start})
    payload = {"ok": ok, "count": len(tests), "tests": tests}
    if junit:
        c64.write_junit64(junit, payload)
    return payload


_NATIVE_HEADER = r"""
#include <cstdint>
#include <cstdio>

enum KeimOp {
    OP_CONST_INT=1, OP_CONST_BOOL=2, OP_LOAD_SLOT=3, OP_STORE_SLOT=4,
    OP_ADD=5, OP_SUB=6, OP_MUL=7, OP_EQ=8,
    OP_JUMP=9, OP_JUMP_IF_FALSE=10, OP_RETURN=11, OP_PRINT=12, OP_PANIC=13
};

struct Instr { int op; int a; int b; int c; };

struct Value {
    int64_t i;
    bool b;
    int kind; // 0 int, 1 bool
};

static Value vi(int64_t x){ Value v; v.kind=0; v.i=x; v.b=false; return v; }
static Value vb(bool x){ Value v; v.kind=1; v.i=0; v.b=x; return v; }
static bool truth(Value v){ return v.kind == 1 ? v.b : v.i != 0; }

#ifndef KEIM_NATIVE_STACK_MAX
#define KEIM_NATIVE_STACK_MAX 1024
#endif
"""


def _native_opcode_for(i: c64.BCInstr) -> tuple[str, int, int, int] | None:
    if i.op == "CONST" and isinstance(i.args[0], bool):
        return ("OP_CONST_BOOL", 1 if i.args[0] else 0, 0, 0)
    if i.op == "CONST" and isinstance(i.args[0], int) and not isinstance(i.args[0], bool):
        return ("OP_CONST_INT", int(i.args[0]), 0, 0)
    if i.op == "LOAD_SLOT":
        return ("OP_LOAD_SLOT", int(i.args[0]), 0, 0)
    if i.op == "STORE_SLOT":
        return ("OP_STORE_SLOT", int(i.args[0]), 0, 0)
    if i.op in {"ADD", "SUB", "MUL", "EQ"}:
        return ("OP_" + i.op, 0, 0, 0)
    if i.op == "JUMP":
        return ("OP_JUMP", int(i.args[0]), 0, 0)
    if i.op == "JUMP_IF_FALSE":
        return ("OP_JUMP_IF_FALSE", int(i.args[0]), 0, 0)
    if i.op == "RETURN":
        return ("OP_RETURN", 0, 0, 0)
    if i.op == "PRINT":
        return ("OP_PRINT", 0, 0, 0)
    if i.op == "TYPE_ASSERT":
        return None
    if i.op == "PANIC":
        return ("OP_PANIC", 0, 0, 0)
    return ("OP_PANIC", 0, 0, 0)

def emit_native_keimvm65(program: c64.Program64 | dict[str, Any], out: Path) -> None:
    p = program if isinstance(program, c64.Program64) else c64.program64_from_dict(program)
    fid = f"{p.entry}.main"
    if fid not in p.functions:
        raise FoundationError("Native v6.5 MVP braucht entry.main")
    fn = p.functions[fid]
    instrs: list[tuple[str,int,int,int]] = []
    for ins in fn.code:
        mapped = _native_opcode_for(ins)
        if mapped is not None:
            instrs.append(mapped)
    array = ",\n".join(f"    {{{op}, {a}, {b}, {c}}}" for op,a,b,c in instrs)
    slot_count = max(fn.slots.values(), default=-1) + 1
    cpp = _NATIVE_HEADER + f'''
static Instr PROGRAM[] = {{
{array}
}};
int main() {{
    Value stack[KEIM_NATIVE_STACK_MAX];
    int sp = 0;
    Value slots[{max(slot_count, 1)}];
    for (int i = 0; i < {max(slot_count, 1)}; ++i) slots[i] = vi(0);
    int pc = 0;
    while (pc >= 0 && pc < (int)(sizeof(PROGRAM)/sizeof(PROGRAM[0]))) {{
        Instr in = PROGRAM[pc];
        switch(in.op) {{
            case OP_CONST_INT: stack[sp++] = vi(in.a); break;
            case OP_CONST_BOOL: stack[sp++] = vb(in.a != 0); break;
            case OP_LOAD_SLOT: stack[sp++] = slots[in.a]; break;
            case OP_STORE_SLOT: slots[in.a] = stack[--sp]; break;
            case OP_ADD: {{ Value r=stack[--sp]; Value l=stack[--sp]; stack[sp++] = vi(l.i + r.i); break; }}
            case OP_SUB: {{ Value r=stack[--sp]; Value l=stack[--sp]; stack[sp++] = vi(l.i - r.i); break; }}
            case OP_MUL: {{ Value r=stack[--sp]; Value l=stack[--sp]; stack[sp++] = vi(l.i * r.i); break; }}
            case OP_EQ: {{ Value r=stack[--sp]; Value l=stack[--sp]; stack[sp++] = vb(l.i == r.i); break; }}
            case OP_JUMP: pc = in.a; continue;
            case OP_JUMP_IF_FALSE: {{ Value v=stack[--sp]; if(!truth(v)) {{ pc = in.a; continue; }} break; }}
            case OP_PRINT: {{ Value v=stack[--sp]; if(v.kind==0) std::printf("%lld\\n", (long long)v.i); else std::printf("%s\\n", v.b ? "wahr" : "falsch"); break; }}
            case OP_RETURN: {{ Value v = sp > 0 ? stack[sp-1] : vi(0); if(v.kind==0) {{ std::printf("%lld\\n", (long long)v.i); return 0; }} std::printf("%s\\n", v.b?"wahr":"falsch"); return v.b?0:1; }}
            case OP_PANIC: std::fprintf(stderr, "native keimvm65 unsupported opcode or panic\\n"); return 90;
            default: std::fprintf(stderr, "native keimvm65 bad opcode %d\\n", in.op); return 91;
        }}
        pc++;
    }}
    return 0;
}}
'''
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(cpp, encoding="utf-8")


def status65() -> dict[str, Any]:
    return {
        "version": "6.5.0-native-generics-result-match-binary",
        "implemented": {
            "generic_function_signatures_typevars": True,
            "result_type_ok_fehler": True,
            "match_ok_fehler_exhaustiveness": True,
            "binary_kbc65b_magic_version_hash": True,
            "python_vm65_runs_kbc65b": True,
            "native_keimvm65_mvp_generates_executable_cpp_vm": True,
            "no_eval": True,
        },
        "native_vm_mvp_supported_ops": ["CONST_INT", "CONST_BOOL", "LOAD_SLOT", "STORE_SLOT", "ADD", "SUB", "MUL", "EQ", "JUMP", "JUMP_IF_FALSE", "RETURN", "PRINT"],
        "remaining_after_65": ["full native heap strings/lists/maps/records/calls", "full WASM lowering", "registry and LSP hardening"],
    }


def load_program65(path: Path) -> c64.Program64:
    if path.suffix == ".kbc65b" or path.name.endswith(".kbc65b"):
        return read_kbc65b(path)
    return c64.program64_from_dict(json.loads(path.read_text(encoding="utf-8")))
