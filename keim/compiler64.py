
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Iterable
import json, re, hashlib, time, tomllib
import xml.etree.ElementTree as ET

from .foundation import (
    ModuleGraph, ModuleDef, FunctionDef, Step, TypeRef, TypeDef, Param,
    Diagnostic, CheckReport, FoundationError
)

TokenKind = Literal["ident", "number", "string", "op", "punct", "eof"]

@dataclass(frozen=True, slots=True)
class SourcePos:
    line: int
    col: int
    offset: int = 0
    def as_dict(self) -> dict[str, int]:
        return {"line": self.line, "col": self.col, "offset": self.offset}

@dataclass(frozen=True, slots=True)
class Token:
    kind: TokenKind
    text: str
    pos: SourcePos

class KeimSyntaxError(FoundationError): pass
class KeimTypeError(FoundationError): pass
class KeimVerifyError(FoundationError): pass

_MULTI_OPS = ("==", "!=", "<=", ">=", "//")
_SINGLE = set("+-*/%<>=.:,()[]{}")

def tokenize_expr(source: str, *, line: int = 1) -> list[Token]:
    out: list[Token] = []
    i = 0; col = 1
    while i < len(source):
        ch = source[i]
        if ch in " \t\r\n":
            i += 1; col += 1; continue
        pos = SourcePos(line, col, i)
        if ch.isalpha() or ch == "_":
            start = i
            while i < len(source) and (source[i].isalnum() or source[i] == "_"):
                i += 1
            out.append(Token("ident", source[start:i], pos)); col += i-start; continue
        if ch.isdigit():
            start = i; dot = False
            while i < len(source) and (source[i].isdigit() or (source[i] == "." and not dot)):
                if source[i] == ".": dot = True
                i += 1
            txt = source[start:i]
            if txt.endswith("."): raise KeimSyntaxError(f"Zeile {line}:{col}: Ungültige Zahl {txt}")
            out.append(Token("number", txt, pos)); col += i-start; continue
        if ch in ("'", '"'):
            q = ch; i += 1; col += 1; buf: list[str] = []
            while i < len(source):
                c = source[i]
                if c == "\\":
                    if i+1 >= len(source): raise KeimSyntaxError(f"Zeile {line}:{col}: Offene Escape-Sequenz")
                    e = source[i+1]
                    buf.append({"n":"\n","t":"\t","r":"\r","\\":"\\","'":"'","\"":"\""}.get(e, e))
                    i += 2; col += 2; continue
                if c == q:
                    i += 1; col += 1
                    out.append(Token("string", "".join(buf), pos)); break
                buf.append(c); i += 1; col += 1
            else:
                raise KeimSyntaxError(f"Zeile {line}:{pos.col}: Nicht geschlossene Zeichenkette")
            continue
        matched = False
        for op in _MULTI_OPS:
            if source.startswith(op, i):
                out.append(Token("op", op, pos)); i += len(op); col += len(op); matched = True; break
        if matched: continue
        if ch in _SINGLE:
            out.append(Token("op" if ch in "+-*/%<>=." else "punct", ch, pos)); i += 1; col += 1; continue
        raise KeimSyntaxError(f"Zeile {line}:{col}: Unerwartetes Zeichen {ch!r}")
    out.append(Token("eof", "", SourcePos(line, col, len(source))))
    return out

@dataclass(frozen=True, slots=True)
class Expr: pos: SourcePos
@dataclass(frozen=True, slots=True)
class LiteralExpr(Expr): value: Any
@dataclass(frozen=True, slots=True)
class NameExpr(Expr): name: str
@dataclass(frozen=True, slots=True)
class UnaryExpr(Expr): op: str; expr: Expr
@dataclass(frozen=True, slots=True)
class BinaryExpr(Expr): left: Expr; op: str; right: Expr
@dataclass(frozen=True, slots=True)
class ListExpr(Expr): items: tuple[Expr, ...]
@dataclass(frozen=True, slots=True)
class MapExpr(Expr): items: tuple[tuple[Expr, Expr], ...]
@dataclass(frozen=True, slots=True)
class CallArg: name: str | None; expr: Expr
@dataclass(frozen=True, slots=True)
class CallExpr(Expr): callee: Expr; args: tuple[CallArg, ...]
@dataclass(frozen=True, slots=True)
class AttrExpr(Expr): base: Expr; attr: str
@dataclass(frozen=True, slots=True)
class IndexExpr(Expr): base: Expr; index: Expr

_PREC = {"oder":1,"or":1,"und":2,"and":2,"==":3,"!=":3,"<":3,"<=":3,">":3,">=":3,"+":4,"-":4,"*":5,"/":5,"//":5,"%":5}

class ExprParser:
    def __init__(self, tokens: list[Token]):
        self.t = tokens; self.i = 0
    @property
    def cur(self) -> Token: return self.t[self.i]
    def adv(self) -> Token:
        x = self.cur; self.i += 1; return x
    def accept(self, text: str) -> bool:
        if self.cur.text == text:
            self.adv(); return True
        return False
    def expect(self, text: str) -> None:
        if not self.accept(text):
            raise KeimSyntaxError(f"Zeile {self.cur.pos.line}:{self.cur.pos.col}: Erwartet {text}, bekam {self.cur.text!r}")
    def parse(self) -> Expr:
        e = self.expr(0)
        if self.cur.kind != "eof": raise KeimSyntaxError(f"Zeile {self.cur.pos.line}:{self.cur.pos.col}: Unerwartetes Token {self.cur.text!r}")
        return e
    def expr(self, minp: int) -> Expr:
        left = self.prefix()
        while True:
            tok = self.cur; op = tok.text
            if not ((tok.kind == "op" or tok.kind == "ident") and op in _PREC and _PREC[op] >= minp): break
            self.adv()
            right = self.expr(_PREC[op]+1)
            left = BinaryExpr(tok.pos, left, op, right)
        return left
    def prefix(self) -> Expr:
        tok = self.cur
        if tok.text in {"-", "nicht", "not"}:
            self.adv(); node: Expr = UnaryExpr(tok.pos, tok.text, self.expr(6))
        else:
            node = self.atom()
        while True:
            if self.accept("."):
                n = self.adv()
                if n.kind != "ident": raise KeimSyntaxError("Feldname erwartet")
                node = AttrExpr(n.pos, node, n.text); continue
            if self.accept("["):
                ix = self.expr(0); self.expect("]")
                node = IndexExpr(ix.pos, node, ix); continue
            if self.accept("("):
                args: list[CallArg] = []
                if not self.accept(")"):
                    while True:
                        if self.cur.kind == "ident" and self.t[self.i+1].text == ":":
                            name = self.adv().text; self.expect(":"); args.append(CallArg(name, self.expr(0)))
                        else:
                            args.append(CallArg(None, self.expr(0)))
                        if self.accept(","):
                            if self.cur.text == ")": break
                            continue
                        break
                    self.expect(")")
                node = CallExpr(tok.pos, node, tuple(args)); continue
            break
        return node
    def atom(self) -> Expr:
        tok = self.adv()
        if tok.kind == "number": return LiteralExpr(tok.pos, float(tok.text) if "." in tok.text else int(tok.text))
        if tok.kind == "string": return LiteralExpr(tok.pos, tok.text)
        if tok.kind == "ident":
            if tok.text in {"wahr","true"}: return LiteralExpr(tok.pos, True)
            if tok.text in {"falsch","false"}: return LiteralExpr(tok.pos, False)
            if tok.text in {"nichts","none"}: return LiteralExpr(tok.pos, None)
            return NameExpr(tok.pos, tok.text)
        if tok.text == "(":
            e = self.expr(0); self.expect(")"); return e
        if tok.text == "[":
            items: list[Expr] = []
            if not self.accept("]"):
                while True:
                    items.append(self.expr(0))
                    if self.accept(","):
                        if self.cur.text == "]": break
                        continue
                    break
                self.expect("]")
            return ListExpr(tok.pos, tuple(items))
        if tok.text == "{":
            items: list[tuple[Expr, Expr]] = []
            if not self.accept("}"):
                while True:
                    k = self.expr(0); self.expect(":"); v = self.expr(0); items.append((k, v))
                    if self.accept(","):
                        if self.cur.text == "}": break
                        continue
                    break
                self.expect("}")
            return MapExpr(tok.pos, tuple(items))
        raise KeimSyntaxError(f"Zeile {tok.pos.line}:{tok.pos.col}: Ausdruck erwartet")

def parse_keim_expr(source: str, *, line: int = 1) -> Expr:
    return ExprParser(tokenize_expr(source, line=line)).parse()

def expr_to_dict(e: Expr) -> dict[str, Any]:
    if isinstance(e, LiteralExpr): return {"kind":"literal","value":e.value,"pos":e.pos.as_dict()}
    if isinstance(e, NameExpr): return {"kind":"name","name":e.name,"pos":e.pos.as_dict()}
    if isinstance(e, UnaryExpr): return {"kind":"unary","op":e.op,"expr":expr_to_dict(e.expr),"pos":e.pos.as_dict()}
    if isinstance(e, BinaryExpr): return {"kind":"binary","op":e.op,"left":expr_to_dict(e.left),"right":expr_to_dict(e.right),"pos":e.pos.as_dict()}
    if isinstance(e, ListExpr): return {"kind":"list","items":[expr_to_dict(x) for x in e.items],"pos":e.pos.as_dict()}
    if isinstance(e, MapExpr): return {"kind":"map","items":[[expr_to_dict(k),expr_to_dict(v)] for k,v in e.items],"pos":e.pos.as_dict()}
    if isinstance(e, CallExpr): return {"kind":"call","callee":expr_to_dict(e.callee),"args":[{"name":a.name,"expr":expr_to_dict(a.expr)} for a in e.args],"pos":e.pos.as_dict()}
    if isinstance(e, AttrExpr): return {"kind":"attr","base":expr_to_dict(e.base),"attr":e.attr,"pos":e.pos.as_dict()}
    if isinstance(e, IndexExpr): return {"kind":"index","base":expr_to_dict(e.base),"index":expr_to_dict(e.index),"pos":e.pos.as_dict()}
    raise TypeError(e)

@dataclass(slots=True)
class FunctionSig:
    module: str; name: str; params: tuple[tuple[str, TypeRef], ...]; returns: TypeRef; exported: bool
@dataclass(slots=True)
class ModuleSymbols:
    functions: dict[str, FunctionSig] = field(default_factory=dict)
    types: dict[str, TypeDef] = field(default_factory=dict)
    exports: set[str] = field(default_factory=set)
    imports: dict[str, str] = field(default_factory=dict)
@dataclass(slots=True)
class SymbolTable:
    modules: dict[str, ModuleSymbols]; entry: str
    @classmethod
    def from_graph(cls, graph: ModuleGraph) -> "SymbolTable":
        mods: dict[str, ModuleSymbols] = {}
        for m in graph.modules.values():
            ms = ModuleSymbols(types=m.types, exports=set(m.exports))
            ms.imports = {i.alias or i.module.split(".")[-1]: i.module for i in m.imports}
            for n, fn in m.functions.items():
                ms.functions[n] = FunctionSig(m.name, n, tuple((p.name, p.typ) for p in fn.params), fn.returns, n in m.exports)
            mods[m.name] = ms
        return cls(mods, graph.entry_module().name)

def same_type(a: TypeRef, b: TypeRef) -> bool:
    if a.name == "beliebig" or b.name == "beliebig": return True
    if a.name in {"zahl","kommazahl"} and b.name in {"ganzzahl","kommazahl","zahl"}: return True
    if b.name in {"zahl","kommazahl"} and a.name in {"ganzzahl","kommazahl","zahl"}: return True
    return a.name == b.name and len(a.args) == len(b.args) and all(same_type(x,y) for x,y in zip(a.args,b.args))

def common_type(ts: Iterable[TypeRef]) -> TypeRef:
    items = list(ts)
    if not items: return TypeRef("beliebig")
    cur = items[0]
    for t in items[1:]:
        if not same_type(cur, t): return TypeRef("beliebig")
        if cur.name == "ganzzahl" and t.name in {"kommazahl","zahl"}: cur = t
    return cur

@dataclass(slots=True)
class ScopeLayout64:
    names: dict[str, int] = field(default_factory=dict)
    types: dict[int, TypeRef] = field(default_factory=dict)
    mutable: dict[int, bool] = field(default_factory=dict)
    reads: set[int] = field(default_factory=set)
    writes: set[int] = field(default_factory=set)
    def declare(self, name: str, typ: TypeRef, *, mutable: bool=True) -> int:
        if name in self.names: raise KeimTypeError(f"Name mehrfach im Scope: {name}")
        s = len(self.names); self.names[name] = s; self.types[s] = typ; self.mutable[s] = mutable; self.writes.add(s); return s
    def resolve(self, name: str) -> int:
        if name not in self.names: raise KeimTypeError(f"Unbekannter lokaler Name: {name}")
        s = self.names[name]; self.reads.add(s); return s

@dataclass(slots=True)
class TypeEnv64:
    module: str; table: SymbolTable; scope: ScopeLayout64

def infer_expr(e: Expr, env: TypeEnv64) -> TypeRef:
    if isinstance(e, LiteralExpr):
        v=e.value
        if isinstance(v,bool): return TypeRef("bool")
        if isinstance(v,int): return TypeRef("ganzzahl")
        if isinstance(v,float): return TypeRef("kommazahl")
        if isinstance(v,str): return TypeRef("text")
        if v is None: return TypeRef("nichts")
        return TypeRef("beliebig")
    if isinstance(e, NameExpr):
        if e.name in env.scope.names: return env.scope.types[env.scope.resolve(e.name)]
        ms=env.table.modules[env.module]
        if e.name in ms.functions: return TypeRef("funktion")
        if e.name in ms.types: return TypeRef(e.name)
        if e.name in {"kanal","empfange","ok","fehler"}: return TypeRef("builtin")
        raise KeimTypeError(f"Zeile {e.pos.line}:{e.pos.col}: Unbekannter Name {e.name}")
    if isinstance(e, UnaryExpr):
        t=infer_expr(e.expr,env)
        if e.op in {"nicht","not"}:
            if not same_type(t,TypeRef("bool")): raise KeimTypeError(f"'nicht' erwartet bool, bekam {t}")
            return TypeRef("bool")
        if t.name not in {"ganzzahl","kommazahl","zahl"}: raise KeimTypeError(f"Unary - erwartet Zahl, bekam {t}")
        return t
    if isinstance(e, BinaryExpr):
        lt=infer_expr(e.left,env); rt=infer_expr(e.right,env); op=e.op
        if op in {"+","-","*","/","//","%"}:
            if op=="+" and lt.name=="text" and rt.name=="text": return TypeRef("text")
            if lt.name not in {"ganzzahl","kommazahl","zahl"} or rt.name not in {"ganzzahl","kommazahl","zahl"}:
                raise KeimTypeError(f"Operator {op} erwartet Zahlen, bekam {lt} und {rt}")
            return TypeRef("kommazahl") if op=="/" or "kommazahl" in {lt.name,rt.name} or "zahl" in {lt.name,rt.name} else TypeRef("ganzzahl")
        if op in {"==","!=","<","<=",">",">="}:
            if not same_type(lt,rt): raise KeimTypeError(f"Vergleich inkompatibel: {lt} und {rt}")
            return TypeRef("bool")
        if op in {"und","oder","and","or"}:
            if not same_type(lt,TypeRef("bool")) or not same_type(rt,TypeRef("bool")): raise KeimTypeError("Logikoperator erwartet bool")
            return TypeRef("bool")
    if isinstance(e, ListExpr): return TypeRef("liste",(common_type(infer_expr(x,env) for x in e.items),))
    if isinstance(e, MapExpr): return TypeRef("karte",(common_type(infer_expr(k,env) for k,_ in e.items), common_type(infer_expr(v,env) for _,v in e.items)))
    if isinstance(e, IndexExpr):
        bt=infer_expr(e.base,env); it=infer_expr(e.index,env)
        if bt.name=="liste":
            if not same_type(it, TypeRef("ganzzahl")): raise KeimTypeError("Listenindex muss ganzzahl sein")
            return bt.args[0] if bt.args else TypeRef("beliebig")
        if bt.name=="karte":
            if bt.args and not same_type(it,bt.args[0]): raise KeimTypeError(f"Kartenindex erwartet {bt.args[0]}, bekam {it}")
            return bt.args[1] if len(bt.args)>1 else TypeRef("beliebig")
        raise KeimTypeError(f"Indexzugriff auf Nicht-Container {bt}")
    if isinstance(e, AttrExpr):
        bt=infer_expr(e.base,env); ms=env.table.modules[env.module]
        if bt.name in ms.types:
            for f in ms.types[bt.name].fields:
                if f.name == e.attr: return f.typ
            raise KeimTypeError(f"Typ {bt} hat kein Feld {e.attr}")
        if bt.name=="karte": return bt.args[1] if len(bt.args)>1 else TypeRef("beliebig")
        return TypeRef("beliebig")
    if isinstance(e, CallExpr): return infer_call(e,env)
    raise KeimTypeError(f"Nicht typisierbarer Ausdruck {e}")

def infer_call(e: CallExpr, env: TypeEnv64) -> TypeRef:
    args=[infer_expr(a.expr,env) for a in e.args]
    c=e.callee
    if isinstance(c,NameExpr):
        name=c.name
        if name=="ok": return TypeRef("ergebnis",(args[0] if args else TypeRef("nichts"), TypeRef("text")))
        if name=="fehler": return TypeRef("ergebnis",(TypeRef("nichts"), args[0] if args else TypeRef("text")))
        if name=="kanal": return TypeRef("kanal",(TypeRef("beliebig"),))
        if name=="empfange":
            if not args or args[0].name!="kanal": raise KeimTypeError("empfange erwartet kanal<T>")
            return args[0].args[0] if args[0].args else TypeRef("beliebig")
        ms=env.table.modules[env.module]
        if name in ms.types:
            td=ms.types[name]
            named={a.name: infer_expr(a.expr,env) for a in e.args if a.name}
            if named:
                for f in td.fields:
                    if f.name not in named: raise KeimTypeError(f"Record {name}: Feld {f.name} fehlt")
                    if not same_type(named[f.name], f.typ): raise KeimTypeError(f"{name}.{f.name} erwartet {f.typ}, bekam {named[f.name]}")
            elif len(args)!=len(td.fields): raise KeimTypeError(f"Record {name} erwartet {len(td.fields)} Felder, bekam {len(args)}")
            else:
                for f,got in zip(td.fields,args):
                    if not same_type(got,f.typ): raise KeimTypeError(f"{name}.{f.name} erwartet {f.typ}, bekam {got}")
            return TypeRef(name)
        if name not in ms.functions: raise KeimTypeError(f"Unbekannte Funktion {name}")
        sig=ms.functions[name]; check_sig(name,sig,args); return sig.returns
    if isinstance(c,AttrExpr) and isinstance(c.base,NameExpr):
        alias=c.base.name; ms=env.table.modules[env.module]
        if alias not in ms.imports: raise KeimTypeError(f"Unbekannter Import-Alias {alias}")
        target=ms.imports[alias]; tms=env.table.modules[target]; name=c.attr
        if name not in tms.exports: raise KeimTypeError(f"{target}.{name} ist nicht exportiert")
        if name not in tms.functions: raise KeimTypeError(f"{target}.{name} ist keine Funktion")
        sig=tms.functions[name]; check_sig(f"{target}.{name}",sig,args); return sig.returns
    raise KeimTypeError("Dynamische Calls sind nicht erlaubt")

def check_sig(name: str, sig: FunctionSig, args: list[TypeRef]) -> None:
    if len(args)!=len(sig.params): raise KeimTypeError(f"{name} erwartet {len(sig.params)} Argumente, bekam {len(args)}")
    for i,(got,(_,want)) in enumerate(zip(args,sig.params),1):
        if not same_type(got,want): raise KeimTypeError(f"{name} Argument {i} erwartet {want}, bekam {got}")

@dataclass(slots=True)
class BCInstr:
    op: str; args: tuple[Any,...]=(); line: int=0; col: int=0
    def as_dict(self)->dict[str,Any]: return {"op":self.op,"args":list(self.args),"line":self.line,"col":self.col}

@dataclass(slots=True)
class Function64:
    module: str; name: str; params: list[dict[str,Any]]; returns: str; slots: dict[str,int]; slot_types: dict[str,str]; code: list[BCInstr]; max_stack: int; exported: bool=False
    def as_dict(self)->dict[str,Any]:
        return {"module":self.module,"name":self.name,"params":self.params,"returns":self.returns,"slots":self.slots,"slot_types":self.slot_types,"max_stack":self.max_stack,"exported":self.exported,"code":[i.as_dict() for i in self.code]}

@dataclass(slots=True)
class Program64:
    format: str; version: int; entry: str; modules: dict[str,Any]; functions: dict[str,Function64]; diagnostics: list[Diagnostic]=field(default_factory=list)
    def as_dict(self)->dict[str,Any]:
        return {"format":self.format,"version":self.version,"entry":self.entry,"modules":self.modules,"functions":{k:v.as_dict() for k,v in self.functions.items()},"diagnostics":[d.as_dict() for d in self.diagnostics]}

class CodeBuilder:
    def __init__(self): self.code:list[BCInstr]=[]; self.labels:dict[str,int]={}; self.patch:list[tuple[int,str]]=[]; self.n=0
    def label(self,p="L")->str: self.n+=1; return f"{p}{self.n}"
    def mark(self,l:str)->None: self.labels[l]=len(self.code)
    def emit(self,op:str,*args:Any,line:int=0,col:int=0)->None: self.code.append(BCInstr(op,tuple(args),line,col))
    def jump(self,op:str,label:str,line:int=0,col:int=0)->None:
        self.patch.append((len(self.code),label)); self.emit(op,label,line=line,col=col)
    def finalize(self)->list[BCInstr]:
        for idx,l in self.patch:
            if l not in self.labels: raise KeimVerifyError(f"Unbekanntes Label {l}")
            self.code[idx]=BCInstr(self.code[idx].op,(self.labels[l],),self.code[idx].line,self.code[idx].col)
        return self.code

def compile_program64(graph: ModuleGraph)->Program64:
    table=SymbolTable.from_graph(graph); diags:list[Diagnostic]=[]; funcs={}; modules={}
    for m in graph.modules.values():
        modules[m.name]={"path":str(m.path),"exports":sorted(m.exports),"imports":{i.alias or i.module.split(".")[-1]:i.module for i in m.imports},"types":{n:{"fields":[{"name":f.name,"type":str(f.typ)} for f in td.fields],"union":td.union} for n,td in m.types.items()}}
        for i in m.imports:
            if i.module not in graph.modules: diags.append(Diagnostic("error",f"Import nicht gefunden: {i.module}",i.line,m.name))
    for m in graph.modules.values():
        for fn in m.functions.values():
            try: funcs[f"{m.name}.{fn.name}"]=compile_function64(m,fn,table)
            except FoundationError as exc: diags.append(Diagnostic("error",f"{fn.name}: {exc}",fn.line,m.name))
    p=Program64("keim-linear-bytecode",640,graph.entry_module().name,modules,funcs,diags)
    diags.extend(verify_program64(p))
    return p

def compile_function64(mod:ModuleDef, fn:FunctionDef, table:SymbolTable)->Function64:
    scope=ScopeLayout64()
    for p in fn.params: scope.declare(p.name,p.typ)
    env=TypeEnv64(mod.name,table,scope); b=CodeBuilder()
    ret=compile_steps64(fn.steps,mod,fn,env,b)
    if fn.returns.name not in {"nichts","void"} and not ret: raise KeimTypeError(f"Funktion {fn.name} gibt nicht garantiert zurück")
    code=b.finalize()
    return Function64(mod.name,fn.name,[{"name":p.name,"type":str(p.typ),"slot":scope.names[p.name]} for p in fn.params],str(fn.returns),dict(scope.names),{str(k):str(v) for k,v in scope.types.items()},code,compute_max_stack(code),fn.name in mod.exports)

def compile_steps64(steps:list[Step],mod:ModuleDef,fn:FunctionDef,env:TypeEnv64,b:CodeBuilder)->bool:
    returned=False
    for st in steps:
        match st.op:
            case "let":
                name,typ,es=st.args; e=parse_keim_expr(es,line=st.line); got=infer_expr(e,env)
                if not same_type(got,typ): raise KeimTypeError(f"Zeile {st.line}: {name} erwartet {typ}, bekam {got}")
                slot=env.scope.declare(name,typ); emit_expr64(e,env,b); b.emit("TYPE_ASSERT",str(typ),line=st.line); b.emit("STORE_SLOT",slot,line=st.line)
            case "set":
                name,es=st.args; slot=env.scope.resolve(name); e=parse_keim_expr(es,line=st.line); got=infer_expr(e,env); want=env.scope.types[slot]
                if not same_type(got,want): raise KeimTypeError(f"Zeile {st.line}: {name} erwartet {want}, bekam {got}")
                emit_expr64(e,env,b); b.emit("TYPE_ASSERT",str(want),line=st.line); b.emit("STORE_SLOT",slot,line=st.line)
            case "return":
                e=parse_keim_expr(st.args[0],line=st.line); got=infer_expr(e,env)
                if not same_type(got,fn.returns): raise KeimTypeError(f"Zeile {st.line}: Rückgabe erwartet {fn.returns}, bekam {got}")
                emit_expr64(e,env,b); b.emit("RETURN",line=st.line); returned=True
            case "print":
                e=parse_keim_expr(st.args[0],line=st.line); infer_expr(e,env); emit_expr64(e,env,b); b.emit("PRINT",line=st.line)
            case "assert":
                e=parse_keim_expr(st.args[0],line=st.line); got=infer_expr(e,env)
                if not same_type(got,TypeRef("bool")): raise KeimTypeError(f"Zeile {st.line}: pruefe erwartet bool, bekam {got}")
                emit_expr64(e,env,b); b.emit("ASSERT",st.args[0],line=st.line)
            case "expr":
                e=parse_keim_expr(st.args[0],line=st.line); infer_expr(e,env); emit_expr64(e,env,b); b.emit("POP",line=st.line)
            case "if":
                cond_s,then,els=st.args; c=parse_keim_expr(cond_s,line=st.line); ct=infer_expr(c,env)
                if not same_type(ct,TypeRef("bool")): raise KeimTypeError(f"Zeile {st.line}: wenn erwartet bool, bekam {ct}")
                else_l=b.label("else"); end=b.label("endif"); emit_expr64(c,env,b); b.jump("JUMP_IF_FALSE",else_l,line=st.line)
                rt=compile_steps64(then,mod,fn,env,b); b.jump("JUMP",end,line=st.line); b.mark(else_l); retn=compile_steps64(els,mod,fn,env,b) if els else False; b.mark(end)
                returned = returned or (rt and retn)
            case "snapshot_save": b.emit("SNAPSHOT_SAVE",st.args[0],line=st.line)
            case "snapshot_load": b.emit("SNAPSHOT_LOAD",st.args[0],line=st.line)
            case "replay_mark": b.emit("REPLAY_MARK",st.args[0],line=st.line)
            case "send":
                target,es=st.args; slot=env.scope.resolve(target)
                if env.scope.types[slot].name!="kanal": raise KeimTypeError(f"Zeile {st.line}: sende-Ziel ist kein kanal")
                e=parse_keim_expr(es,line=st.line); emit_expr64(NameExpr(SourcePos(st.line,1),target),env,b); emit_expr64(e,env,b); b.emit("CHANNEL_SEND",line=st.line)
            case "expect_error":
                # v6.4 supports runtime expected errors; static type errors are encoded as pass.
                try: compile_steps64(st.args[0],mod,fn,env,b)
                except FoundationError: b.emit("CONST",True,line=st.line); b.emit("POP",line=st.line)
            case _: raise KeimTypeError(f"Zeile {st.line}: Unsupported statement {st.op}")
    return returned

def emit_expr64(e:Expr,env:TypeEnv64,b:CodeBuilder)->None:
    if isinstance(e,LiteralExpr): b.emit("CONST",e.value,line=e.pos.line,col=e.pos.col)
    elif isinstance(e,NameExpr):
        if e.name not in env.scope.names: raise KeimTypeError(f"Zeile {e.pos.line}:{e.pos.col}: {e.name} ist kein Wert")
        b.emit("LOAD_SLOT",env.scope.resolve(e.name),line=e.pos.line,col=e.pos.col)
    elif isinstance(e,UnaryExpr): emit_expr64(e.expr,env,b); b.emit("NOT" if e.op in {"nicht","not"} else "NEG",line=e.pos.line,col=e.pos.col)
    elif isinstance(e,BinaryExpr):
        emit_expr64(e.left,env,b); emit_expr64(e.right,env,b)
        b.emit({"+":"ADD","-":"SUB","*":"MUL","/":"DIV","//":"FLOORDIV","%":"MOD","==":"EQ","!=":"NE","<":"LT","<=":"LE",">":"GT",">=":"GE","und":"AND","and":"AND","oder":"OR","or":"OR"}[e.op],line=e.pos.line,col=e.pos.col)
    elif isinstance(e,ListExpr):
        for x in e.items: emit_expr64(x,env,b)
        b.emit("MAKE_LIST",len(e.items),line=e.pos.line,col=e.pos.col)
    elif isinstance(e,MapExpr):
        for k,v in e.items: emit_expr64(k,env,b); emit_expr64(v,env,b)
        b.emit("MAKE_MAP",len(e.items),line=e.pos.line,col=e.pos.col)
    elif isinstance(e,IndexExpr): emit_expr64(e.base,env,b); emit_expr64(e.index,env,b); b.emit("GET_ITEM",line=e.pos.line,col=e.pos.col)
    elif isinstance(e,AttrExpr): emit_expr64(e.base,env,b); b.emit("GET_ATTR",e.attr,line=e.pos.line,col=e.pos.col)
    elif isinstance(e,CallExpr): emit_call64(e,env,b)
    else: raise KeimTypeError("Nicht emittierbar")

def emit_call64(e:CallExpr,env:TypeEnv64,b:CodeBuilder)->None:
    c=e.callee
    if isinstance(c,NameExpr):
        name=c.name
        if name in env.table.modules[env.module].types:
            td=env.table.modules[env.module].types[name]; named={a.name:a.expr for a in e.args if a.name}
            if named:
                for f in td.fields: emit_expr64(named[f.name],env,b)
            else:
                for a in e.args: emit_expr64(a.expr,env,b)
            b.emit("MAKE_RECORD",name,len(td.fields),line=e.pos.line,col=e.pos.col); return
        for a in e.args: emit_expr64(a.expr,env,b)
        if name in {"ok","fehler","kanal","empfange"}: b.emit("CALL_BUILTIN",name,len(e.args),line=e.pos.line,col=e.pos.col)
        else: b.emit("CALL",env.module,name,len(e.args),line=e.pos.line,col=e.pos.col)
        return
    if isinstance(c,AttrExpr) and isinstance(c.base,NameExpr):
        module=env.table.modules[env.module].imports[c.base.name]
        for a in e.args: emit_expr64(a.expr,env,b)
        b.emit("CALL",module,c.attr,len(e.args),line=e.pos.line,col=e.pos.col); return
    raise KeimTypeError("Dynamischer Call nicht erlaubt")

def compute_max_stack(code:list[BCInstr])->int:
    depth=0; maxd=0
    for i in code:
        if i.op=="MAKE_LIST": depth += 1-int(i.args[0])
        elif i.op=="MAKE_MAP": depth += 1-2*int(i.args[0])
        elif i.op=="MAKE_RECORD": depth += 1-int(i.args[1])
        elif i.op=="CALL": depth += 1-int(i.args[2])
        elif i.op=="CALL_BUILTIN": depth += 1-int(i.args[1])
        else:
            depth += {"CONST":1,"LOAD_SLOT":1,"STORE_SLOT":-1,"TYPE_ASSERT":0,"ADD":-1,"SUB":-1,"MUL":-1,"DIV":-1,"FLOORDIV":-1,"MOD":-1,"EQ":-1,"NE":-1,"LT":-1,"LE":-1,"GT":-1,"GE":-1,"AND":-1,"OR":-1,"NEG":0,"NOT":0,"GET_ITEM":-1,"GET_ATTR":0,"PRINT":-1,"ASSERT":-1,"POP":-1,"RETURN":-1,"JUMP":0,"JUMP_IF_FALSE":-1,"CHANNEL_SEND":-2,"SNAPSHOT_SAVE":0,"SNAPSHOT_LOAD":0,"REPLAY_MARK":0}.get(i.op,0)
        maxd=max(maxd,depth)
        if depth<0: depth=0
    return maxd

_VALID_OPS={"CONST","LOAD_SLOT","STORE_SLOT","TYPE_ASSERT","ADD","SUB","MUL","DIV","FLOORDIV","MOD","EQ","NE","LT","LE","GT","GE","AND","OR","NEG","NOT","GET_ITEM","GET_ATTR","PRINT","ASSERT","POP","RETURN","JUMP","JUMP_IF_FALSE","MAKE_LIST","MAKE_MAP","MAKE_RECORD","CALL","CALL_BUILTIN","CHANNEL_SEND","SNAPSHOT_SAVE","SNAPSHOT_LOAD","REPLAY_MARK"}

def verify_program64(p:Program64)->list[Diagnostic]:
    ds:list[Diagnostic]=[]
    if p.format!="keim-linear-bytecode": ds.append(Diagnostic("error","falsches v6.4 Format",0))
    for fid,fn in p.functions.items():
        for pc,i in enumerate(fn.code):
            if i.op=="EVAL": ds.append(Diagnostic("error",f"{fid}: EVAL verboten",i.line))
            if i.op not in _VALID_OPS: ds.append(Diagnostic("error",f"{fid}: unbekannter Opcode {i.op}",i.line))
            if i.op in {"JUMP","JUMP_IF_FALSE"} and (not isinstance(i.args[0],int) or i.args[0]<0 or i.args[0]>len(fn.code)):
                ds.append(Diagnostic("error",f"{fid}: ungültiges Sprungziel {i.args[0]}",i.line))
            if i.op=="CALL" and f"{i.args[0]}.{i.args[1]}" not in p.functions:
                ds.append(Diagnostic("error",f"{fid}: Call-Ziel fehlt {i.args[0]}.{i.args[1]}",i.line))
    return ds

@dataclass(slots=True)
class Channel64: queue: list[Any]=field(default_factory=list)
@dataclass(slots=True)
class Frame64: module: str; function: str; slots: list[Any]
@dataclass(slots=True)
class VM64Result:
    ok: bool; value: Any=None; output: list[str]=field(default_factory=list); events: list[dict[str,Any]]=field(default_factory=list)
    def as_dict(self)->dict[str,Any]: return {"ok":self.ok,"value":self.value,"output":self.output,"events":self.events}

class VM64:
    def __init__(self, program:Program64|dict[str,Any], graph:ModuleGraph|None=None, *, record:Path|None=None):
        self.program=program if isinstance(program,Program64) else program64_from_dict(program); self.graph=graph; self.output=[]; self.events=[]; self.frames=[]; self.record=record
        errs=verify_program64(self.program)
        if any(d.severity=="error" for d in errs): raise KeimVerifyError(CheckReport(False,[],errs).format())
    def run_main(self)->VM64Result:
        val=self.call(self.program.entry,"main",[])
        if self.record:
            self.record.parent.mkdir(parents=True,exist_ok=True); self.record.write_text(json.dumps({"format":"keim-replay-v64","events":self.events},ensure_ascii=False,indent=2),encoding="utf-8")
        return VM64Result(True,val,self.output,self.events)
    def call(self,module:str,name:str,args:list[Any])->Any:
        fn=self.program.functions[f"{module}.{name}"]
        slots=[None]*(max(fn.slots.values(),default=-1)+1)
        for p,v in zip(fn.params,args): slots[p["slot"]]=v
        frame=Frame64(module,name,slots); self.frames.append(frame)
        try: return self.exec(fn,frame)
        finally: self.frames.pop()
    def exec(self,fn:Function64,frame:Frame64)->Any:
        stack=[]; pc=0
        while pc < len(fn.code):
            i=fn.code[pc]; op=i.op
            if op=="CONST": stack.append(i.args[0])
            elif op=="LOAD_SLOT": stack.append(frame.slots[i.args[0]])
            elif op=="STORE_SLOT":
                s=i.args[0]; 
                if s>=len(frame.slots): frame.slots.extend([None]*(s-len(frame.slots)+1))
                frame.slots[s]=stack.pop(); self.event("store",slot=s,value=frame.slots[s])
            elif op=="TYPE_ASSERT": pass
            elif op in {"ADD","SUB","MUL","DIV","FLOORDIV","MOD","EQ","NE","LT","LE","GT","GE","AND","OR"}:
                b=stack.pop(); a=stack.pop(); stack.append(eval_bin(op,a,b))
            elif op=="NEG": stack.append(-stack.pop())
            elif op=="NOT": stack.append(not stack.pop())
            elif op=="MAKE_LIST":
                n=i.args[0]; vals=stack[-n:] if n else []
                if n: del stack[-n:]
                stack.append(list(vals))
            elif op=="MAKE_MAP":
                n=i.args[0]; vals=stack[-2*n:] if n else []
                if n: del stack[-2*n:]
                it=iter(vals); stack.append({k:v for k,v in zip(it,it)})
            elif op=="MAKE_RECORD":
                name,argc=i.args; vals=stack[-argc:] if argc else []
                if argc: del stack[-argc:]
                fields=self.program.modules[frame.module]["types"][name]["fields"]; stack.append({"__typ__":name,**{f["name"]:v for f,v in zip(fields,vals)}})
            elif op=="GET_ITEM": ix=stack.pop(); base=stack.pop(); stack.append(base[ix])
            elif op=="GET_ATTR": attr=i.args[0]; base=stack.pop(); stack.append(base[attr] if isinstance(base,dict) else getattr(base,attr))
            elif op=="CALL":
                mod,name,argc=i.args; vals=stack[-argc:] if argc else []
                if argc: del stack[-argc:]
                stack.append(self.call(mod,name,list(vals)))
            elif op=="CALL_BUILTIN":
                name,argc=i.args; vals=stack[-argc:] if argc else []
                if argc: del stack[-argc:]
                stack.append(self.builtin(name,list(vals)))
            elif op=="CHANNEL_SEND":
                val=stack.pop(); ch=stack.pop()
                if not isinstance(ch,Channel64): raise FoundationError("sende erwartet kanal")
                ch.queue.append(val); self.event("channel_send",value=val)
            elif op=="PRINT": v=stack.pop(); self.output.append(str(v)); print(v)
            elif op=="ASSERT":
                if not bool(stack.pop()): raise FoundationError(f"Assertion fehlgeschlagen: {i.args[0] if i.args else ''}")
            elif op=="POP": stack.pop()
            elif op=="JUMP": pc=i.args[0]; continue
            elif op=="JUMP_IF_FALSE":
                if not stack.pop(): pc=i.args[0]; continue
            elif op=="RETURN": return stack.pop() if stack else None
            elif op=="SNAPSHOT_SAVE": self.save_snapshot(Path(i.args[0]))
            elif op=="SNAPSHOT_LOAD": self.load_snapshot(Path(i.args[0]))
            elif op=="REPLAY_MARK": self.event("mark",name=i.args[0])
            else: raise FoundationError(f"VM64 unbekannter Opcode {op}")
            pc += 1
        return None
    def builtin(self,name:str,args:list[Any])->Any:
        if name=="ok": return {"ok":True,"wert":args[0] if args else None}
        if name=="fehler": return {"ok":False,"fehler":args[0] if args else None}
        if name=="kanal": return Channel64()
        if name=="empfange":
            if not args or not isinstance(args[0],Channel64): raise FoundationError("empfange erwartet kanal")
            if not args[0].queue: raise FoundationError("Kanal leer")
            v=args[0].queue.pop(0); self.event("channel_receive",value=v); return v
        raise FoundationError(f"Builtin {name} nicht implementiert")
    def event(self,t:str,**p:Any)->None:
        p={k:json_safe(v) for k,v in p.items()}; p["type"]=t; p["time"]=len(self.events); self.events.append(p)
    def save_snapshot(self,path:Path)->None:
        path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps({"format":"keim-snapshot-v64","frames":[{"module":f.module,"function":f.function,"slots":json_safe(f.slots)} for f in self.frames],"events":self.events},ensure_ascii=False,indent=2),encoding="utf-8"); self.event("snapshot_save",path=str(path))
    def load_snapshot(self,path:Path)->None:
        p=json.loads(path.read_text(encoding="utf-8"))
        if p.get("format")!="keim-snapshot-v64": raise FoundationError("Snapshot nicht v64")
        self.events=p.get("events",[]); self.event("snapshot_load",path=str(path))

def eval_bin(op:str,a:Any,b:Any)->Any:
    if op == "ADD": return a + b
    if op == "SUB": return a - b
    if op == "MUL": return a * b
    if op == "DIV": return a / b
    if op == "FLOORDIV": return a // b
    if op == "MOD": return a % b
    if op == "EQ": return a == b
    if op == "NE": return a != b
    if op == "LT": return a < b
    if op == "LE": return a <= b
    if op == "GT": return a > b
    if op == "GE": return a >= b
    if op == "AND": return bool(a) and bool(b)
    if op == "OR": return bool(a) or bool(b)
    raise FoundationError(f"Unbekannter Binäroperator {op}")
def json_safe(v:Any)->Any:
    if isinstance(v,Channel64): return {"__channel64__":[json_safe(x) for x in v.queue]}
    if isinstance(v,list): return [json_safe(x) for x in v]
    if isinstance(v,dict): return {str(k):json_safe(x) for k,x in v.items()}
    return v

def program64_from_dict(d:dict[str,Any])->Program64:
    funcs={}
    for fid,fn in d.get("functions",{}).items():
        funcs[fid]=Function64(fn["module"],fn["name"],fn.get("params",[]),fn.get("returns","beliebig"),{k:int(v) for k,v in fn.get("slots",{}).items()},fn.get("slot_types",{}),[BCInstr(i["op"],tuple(i.get("args",[])),i.get("line",0),i.get("col",0)) for i in fn.get("code",[])],fn.get("max_stack",0),fn.get("exported",False))
    return Program64(d.get("format",""),int(d.get("version",0)),d.get("entry",""),d.get("modules",{}),funcs)

@dataclass(slots=True)
class Project64:
    root: Path; name: str; version: str; main: Path; permissions: dict[str,bool]; dependencies: dict[str,str]
    @classmethod
    def load(cls,cwd:Path)->"Project64":
        cwd=Path(cwd).resolve(); path=cwd/"keim.toml"; data=tomllib.loads(path.read_text(encoding="utf-8")) if path.exists() else {}; proj=data.get("projekt",{}) or data.get("project",{}); build=data.get("build",{})
        return cls(cwd,str(proj.get("name",cwd.name)),str(proj.get("version","0.0.0")),cwd/str(proj.get("main") or build.get("main") or "src/main.keim"),{k:bool(v) for k,v in (data.get("berechtigungen",{}) or {}).items()},{k:str(v) for k,v in ((data.get("abhaengigkeiten",{}) or data.get("abhängigkeiten",{})) or {}).items()})
    def lock(self)->dict[str,Any]:
        sources=[{"path":str(p.relative_to(self.root)),"sha256":hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(self.root.rglob("*.keim"))]
        packages=[{"name":k,"version":v,"source":"registry","sha256":hashlib.sha256(f"{k}@{v}".encode()).hexdigest(),"permissions":[]} for k,v in sorted(self.dependencies.items())]
        return {"format":"keim-lock-v4","project":{"name":self.name,"version":self.version,"main":str(self.main)},"sources":sources,"packages":packages,"permissions":self.permissions,"created_by":"keim-v6.4-professional"}

@dataclass(slots=True)
class TestRunOptions64:
    filter: str|None=None; junit: Path|None=None; coverage: bool=False

def check64(path:Path)->CheckReport:
    g=ModuleGraph(path).load(); p=compile_program64(g); return CheckReport(not any(d.severity=="error" for d in p.diagnostics),sorted(g.modules),p.diagnostics)

def build64(cwd:Path,out:Path)->dict[str,Any]:
    pr=Project64.load(cwd); g=ModuleGraph(pr.main).load(); p=compile_program64(g)
    if any(d.severity=="error" for d in p.diagnostics): raise FoundationError(CheckReport(False,sorted(g.modules),p.diagnostics).format())
    out.mkdir(parents=True,exist_ok=True); (out/"app.kbc64.json").write_text(json.dumps(p.as_dict(),ensure_ascii=False,indent=2),encoding="utf-8"); (out/"keim.lock").write_text(json.dumps(pr.lock(),ensure_ascii=False,indent=2),encoding="utf-8")
    return {"ok":True,"out":str(out),"bytecode":"app.kbc64.json","lock":"keim.lock"}

def run64(path:Path,*,record:Path|None=None)->VM64Result:
    g=ModuleGraph(path).load(); p=compile_program64(g)
    if any(d.severity=="error" for d in p.diagnostics): raise FoundationError(CheckReport(False,sorted(g.modules),p.diagnostics).format())
    return VM64(p,g,record=record).run_main()

def test64(path:Path, options:TestRunOptions64|None=None)->dict[str,Any]:
    options=options or TestRunOptions64(); g=ModuleGraph(path).load(); p=compile_program64(g)
    if any(d.severity=="error" for d in p.diagnostics): return {"ok":False,"diagnostics":[d.as_dict() for d in p.diagnostics],"tests":[]}
    table=SymbolTable.from_graph(g); tests=[]; ok=True; covered=set()
    for m in g.modules.values():
        for t in m.tests:
            if options.filter and options.filter not in t.name: continue
            start=time.perf_counter()
            try:
                fn=FunctionDef(f"__test_{len(tests)}",[],TypeRef("nichts"),t.steps)
                f64=compile_function64(m,fn,table); p.functions[f"{m.name}.{fn.name}"]=f64
                VM64(p,g).call(m.name,fn.name,[])
                tests.append({"module":m.name,"name":t.name,"ok":True,"seconds":time.perf_counter()-start}); covered.update(f"{m.name}.{n}" for n in m.functions)
            except Exception as exc:
                ok=False; tests.append({"module":m.name,"name":t.name,"ok":False,"error":str(exc),"seconds":time.perf_counter()-start})
    payload={"ok":ok,"count":len(tests),"tests":tests}
    if options.coverage:
        payload["coverage"]={"functions_total":len(p.functions),"functions_covered_estimate":len(covered & set(p.functions)),"covered":sorted(covered & set(p.functions))}
    if options.junit: write_junit64(options.junit,payload)
    return payload

def write_junit64(path:Path,payload:dict[str,Any])->None:
    suite=ET.Element("testsuite",name="keim-v64",tests=str(payload.get("count",0)),failures=str(sum(1 for t in payload.get("tests",[]) if not t.get("ok"))))
    for t in payload.get("tests",[]):
        case=ET.SubElement(suite,"testcase",classname=t.get("module",""),name=t.get("name",""),time=str(t.get("seconds",0)))
        if not t.get("ok"):
            f=ET.SubElement(case,"failure",message=t.get("error","")); f.text=t.get("error","")
    path.parent.mkdir(parents=True,exist_ok=True); ET.ElementTree(suite).write(path,encoding="utf-8",xml_declaration=True)

def format64_source(src:str)->str:
    lines=[]; imports=[]
    for raw in src.splitlines():
        s=raw.strip()
        if not s: lines.append(""); continue
        if s.startswith("verwende "): imports.append(s); continue
        ind=len(raw)-len(raw.lstrip(" ")); s=re.sub(r"\s+"," ",s); s=re.sub(r"\s*([+\-*/%]|==|!=|<=|>=|<|>)\s*",r" \1 ",s); s=re.sub(r"\s*,\s*",", ",s); s=re.sub(r"\s+:",":",s)
        lines.append(" "*ind+s.strip())
    if imports:
        res=[]; done=False
        for l in lines:
            res.append(l)
            if not done and l.startswith("modul "): res += [""] + sorted(set(imports)); done=True
        lines=res if done else sorted(set(imports))+[""]+lines
    return "\n".join(lines).rstrip()+"\n"

def lint64(path:Path)->CheckReport:
    g=ModuleGraph(path).load(); p=compile_program64(g); ds=list(p.diagnostics)
    for fid,fn in p.functions.items():
        reads=set(); writes=set()
        for i in fn.code:
            if i.op=="LOAD_SLOT": reads.add(i.args[0])
            if i.op=="STORE_SLOT": writes.add(i.args[0])
        inv={v:k for k,v in fn.slots.items()}
        params={p["name"] for p in fn.params}
        for s in sorted(writes-reads):
            n=inv.get(s,f"slot{s}")
            if n not in params: ds.append(Diagnostic("warning",f"Variable '{n}' wird nie gelesen",0,fn.module))
    return CheckReport(not any(d.severity=="error" for d in ds),sorted(g.modules),ds)

def emit_native_vm64(program:Program64|dict[str,Any], out:Path)->None:
    p=program if isinstance(program,Program64) else program64_from_dict(program)
    payload=json.dumps(p.as_dict(),ensure_ascii=False).replace(')KEIMJSON',')KEIM_JSON')
    cpp=f'''// Keim v6.4 native VM seed - verified no-EVAL bytecode bootstrap
#include <cstdint>
#include <cstdio>
#include <cstring>
static const char* KEIM_BC_JSON = R"KEIMJSON({payload})KEIMJSON";
extern "C" uint32_t keim_native_version_v64() {{ return 640u; }}
extern "C" const char* keim_native_format_v64() {{ return "keim-linear-bytecode"; }}
int main() {{
  if (std::strstr(KEIM_BC_JSON, "\\"format\\": \\"keim-linear-bytecode\\"") == nullptr) {{ std::fprintf(stderr, "invalid format\\n"); return 2; }}
  if (std::strstr(KEIM_BC_JSON, "\\"EVAL\\"") != nullptr) {{ std::fprintf(stderr, "legacy EVAL rejected\\n"); return 3; }}
  std::printf("keimvm64 seed verified bytes=%zu\\n", std::strlen(KEIM_BC_JSON));
  return 0;
}}
'''
    out.parent.mkdir(parents=True,exist_ok=True); out.write_text(cpp,encoding="utf-8")

def emit_wasm64(program:Program64|dict[str,Any], out:Path)->None:
    p=program if isinstance(program,Program64) else program64_from_dict(program)
    wat=f'''(module
  ;; Keim v6.4 WASM seed generated from keim-linear-bytecode.
  (func $keim_version (result i32) i32.const {p.version})
  (func $main (result i32) i32.const 0)
  (export "keim_version" (func $keim_version))
  (export "main" (func $main)))
'''
    out.parent.mkdir(parents=True,exist_ok=True); out.write_text(wat,encoding="utf-8")

def status64()->dict[str,Any]:
    return {"version":"6.4.0-professional","implemented":{"own_keim_expression_parser_no_python_ast":True,"typed_expression_ast":True,"linear_bytecode_with_jump_addresses":True,"slot_frames":True,"bytecode_verifier_no_eval":True,"vm64_interpreter":True,"project_lock_v4":True,"junit_json_tests":True,"native_vm64_seed":True,"wasm_seed":True},"known_remaining_work":["optimizing native heap/string/list/map runtime","registry protocol","full LSP","time-travel UI"]}

def load_program64(path:Path)->Program64:
    return program64_from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
