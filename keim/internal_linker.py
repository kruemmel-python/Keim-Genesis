
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json
import os
import platform
import struct
import hashlib


class NativeLinkerError(Exception):
    """Fehler des Keim-internen Native-Linkers."""


@dataclass(slots=True)
class LinkResult:
    ok: bool
    target: str
    path: str
    bytes_written: int
    sha256: str
    inferred_stdout: str
    notes: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "target": self.target,
            "path": self.path,
            "bytes": self.bytes_written,
            "sha256": self.sha256,
            "inferred_stdout": self.inferred_stdout,
            "notes": self.notes,
        }


def status_payload() -> dict[str, Any]:
    return {
        "name": "Keim Internal Native Linker",
        "version": 785,
        "external_compiler_required": False,
        "targets": ["elf64-linux-x86_64", "pe64-windows-x86_64"],
        "supported_subset": [
            "CONST", "TYPE_ASSERT", "STORE_SLOT", "LOAD_SLOT",
            "ADD", "SUB", "MUL", "DIV", "EQ", "RETURN", "PRINT",
        ],
        "purpose": "erzeugt ausführbare Minimal-Native-Artefakte und Self-Bootstrapping-Runtime-Launcher ohne g++/clang/link.exe",
        "launcher_modes": ["stdout-subset", "command-bootstrapper", "waiting-pe-system-launcher"],
    }


def link_kbc_file(kbc_path: Path, out: Path, *, target: str | None = None, stdout_text: str | None = None) -> LinkResult:
    payload = json.loads(Path(kbc_path).read_text(encoding="utf-8"))
    text = stdout_text if stdout_text is not None else infer_stdout_from_kbc(payload)
    return link_stdout_executable(text, out, target=target)


def infer_stdout_from_kbc(payload: dict[str, Any]) -> str:
    """Inferiert deterministisch die Ausgabe für den kleinen Native-MVP-Subset.

    Für Keim-v6.5 Native-MVP erzeugt `main()` typischerweise einen ganzzahligen
    Rückgabewert. Da native Konsolenbeispiele sichtbar testbar sein sollen,
    gibt der interne Linker diesen Rückgabewert als Text mit Newline aus.
    """
    entry = payload.get("entry")
    functions = payload.get("functions", {})
    fid = None
    if entry and f"{entry}.main" in functions:
        fid = f"{entry}.main"
    elif functions:
        fid = sorted(functions)[0]
    if fid is None:
        raise NativeLinkerError("Bytecode enthält keine Funktion")
    value = _eval_subset_function(functions[fid])
    if value is None:
        return ""
    return f"{value}\n"


def _eval_subset_function(fn: dict[str, Any]) -> Any:
    slots: list[Any] = [None] * max(8, (max(fn.get("slots", {}).values(), default=-1) + 1 if isinstance(fn.get("slots"), dict) else 8))
    stack: list[Any] = []
    pc = 0
    code = fn.get("code", [])
    while pc < len(code):
        instr = code[pc]
        op = instr.get("op")
        args = instr.get("args", [])
        if op == "CONST":
            stack.append(args[0] if args else None)
        elif op == "TYPE_ASSERT":
            pass
        elif op == "STORE_SLOT":
            slot = int(args[0])
            if slot >= len(slots):
                slots.extend([None] * (slot - len(slots) + 1))
            slots[slot] = stack.pop()
        elif op == "LOAD_SLOT":
            stack.append(slots[int(args[0])])
        elif op in {"ADD", "SUB", "MUL", "DIV", "FLOORDIV", "MOD", "EQ", "NE", "LT", "LE", "GT", "GE"}:
            b = stack.pop(); a = stack.pop()
            match op:
                case "ADD": stack.append(a + b)
                case "SUB": stack.append(a - b)
                case "MUL": stack.append(a * b)
                case "DIV": stack.append(a / b)
                case "FLOORDIV": stack.append(a // b)
                case "MOD": stack.append(a % b)
                case "EQ": stack.append(a == b)
                case "NE": stack.append(a != b)
                case "LT": stack.append(a < b)
                case "LE": stack.append(a <= b)
                case "GT": stack.append(a > b)
                case "GE": stack.append(a >= b)
        elif op == "PRINT":
            # Compiler64/65 can encode print as stack-print; preserve top.
            if stack:
                return str(stack[-1]) + "\n"
        elif op == "RETURN":
            return stack.pop() if stack else None
        elif op == "JUMP":
            pc = int(args[0]); continue
        elif op == "JUMP_IF_FALSE":
            target = int(args[0])
            cond = bool(stack.pop())
            if not cond:
                pc = target
                continue
        else:
            raise NativeLinkerError(f"Opcode im internen Linker-Subset nicht unterstützt: {op}")
        pc += 1
    return stack[-1] if stack else None


def link_stdout_executable(stdout_text: str, out: Path, *, target: str | None = None) -> LinkResult:
    out = Path(out)
    target = target or default_target()
    if target in {"elf", "elf64", "linux", "elf64-linux-x86_64"}:
        data = emit_elf64_stdout(stdout_text.encode("utf-8"))
        norm_target = "elf64-linux-x86_64"
    elif target in {"pe", "pe64", "windows", "pe64-windows-x86_64"}:
        data = emit_pe64_stdout(stdout_text.encode("utf-8"))
        norm_target = "pe64-windows-x86_64"
    else:
        raise NativeLinkerError(f"Unbekanntes Native-Link-Ziel: {target}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    if norm_target.startswith("elf"):
        try:
            mode = out.stat().st_mode
            out.chmod(mode | 0o111)
        except OSError:
            pass
    digest = hashlib.sha256(data).hexdigest()
    return LinkResult(True, norm_target, str(out), len(data), digest, stdout_text, ["no external compiler or linker used"])




def link_command_launcher(command: str, out: Path, *, target: str | None = None) -> LinkResult:
    """Erzeugt einen kleinen nativen Bootstrapper, der einen Runtime-Befehl startet.

    Dieser Pfad ist für v7.8.5 Full Runtime Packages gedacht. Er ersetzt nicht
    die eingebettete Keim-Runtime; er startet sie. Damit ist bin/*_launcher.exe
    kein reiner Hinweistext mehr, sondern ruft run.bat/run.sh über den
    Paketpfad auf. Es wird kein externer Compiler/Linker benötigt.
    """
    out = Path(out)
    target = target or default_target()
    if target in {"elf", "elf64", "linux", "elf64-linux-x86_64"}:
        data = emit_elf64_shell_command(command.encode("utf-8"))
        norm_target = "elf64-linux-x86_64"
    elif target in {"pe", "pe64", "windows", "pe64-windows-x86_64"}:
        data = emit_pe64_system_command(command.encode("utf-8"))
        norm_target = "pe64-windows-x86_64"
    else:
        raise NativeLinkerError(f"Unbekanntes Native-Link-Ziel: {target}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    if norm_target.startswith("elf"):
        try:
            out.chmod(out.stat().st_mode | 0o111)
        except OSError:
            pass
    digest = hashlib.sha256(data).hexdigest()
    return LinkResult(True, norm_target, str(out), len(data), digest, command, ["self-bootstrapping runtime launcher", "waiting process launcher", "no external compiler or linker used"])


def emit_elf64_shell_command(cmd: bytes) -> bytes:
    """ELF64 x86_64: execve('/bin/sh', ['sh','-c', cmd], NULL)."""
    if b"\x00" in cmd:
        raise NativeLinkerError("Launcher-Befehl enthält NUL-Byte")
    code = bytearray()
    patches: list[tuple[int, str, int]] = []
    labels: dict[str, int] = {}

    def mark(name: str) -> None:
        labels[name] = len(code)

    # mov eax,59  ; execve
    code += b"\xB8\x3B\x00\x00\x00"
    # lea rdi,[rip+path]
    off = len(code); code += b"\x48\x8D\x3D\x00\x00\x00\x00"; patches.append((off, "path", 7))
    # lea rsi,[rip+argv]
    off = len(code); code += b"\x48\x8D\x35\x00\x00\x00\x00"; patches.append((off, "argv", 7))
    # xor edx,edx
    code += b"\x31\xD2"
    # syscall
    code += b"\x0F\x05"
    # exit(127) fallback
    code += b"\xB8\x3C\x00\x00\x00"  # mov eax,60
    code += b"\xBF\x7F\x00\x00\x00"  # mov edi,127
    code += b"\x0F\x05"

    while len(code) % 8:
        code.append(0)
    mark("path"); code += b"/bin/sh\x00"
    mark("arg0"); code += b"sh\x00"
    mark("arg1"); code += b"-c\x00"
    mark("cmd"); code += cmd + b"\x00"
    while len(code) % 8:
        code.append(0)
    mark("argv")
    argv_off = len(code)
    code += b"\x00" * (8 * 4)

    ehsize = 64
    phoff = 64
    phentsize = 56
    phnum = 1
    file_off = 0x1000
    vaddr = 0x400000 + file_off
    entry = vaddr
    filesz = len(code)
    memsz = filesz

    # Patch RIP-relative displacements.
    for off, lname, instr_size in patches:
        target = labels[lname]
        rip_after = off + instr_size
        disp = target - rip_after
        struct.pack_into("<i", code, off + instr_size - 4, disp)
    # Patch argv absolute pointers.
    for i, lname in enumerate(["arg0", "arg1", "cmd"]):
        struct.pack_into("<Q", code, argv_off + i * 8, vaddr + labels[lname])
    struct.pack_into("<Q", code, argv_off + 3 * 8, 0)

    ident = b"\x7fELF" + bytes([2, 1, 1, 0]) + bytes(8)
    ehdr = struct.pack(
        "<16sHHIQQQIHHHHHH",
        ident, 2, 0x3E, 1, entry, phoff, 0, 0, ehsize, phentsize, phnum, 0, 0, 0
    )
    phdr = struct.pack(
        "<IIQQQQQQ",
        1, 5, file_off, vaddr, vaddr, filesz, memsz, 0x1000
    )
    blob = bytearray(ehdr + phdr)
    if len(blob) > file_off:
        raise NativeLinkerError("ELF header größer als code offset")
    blob += bytes(file_off - len(blob))
    blob += code
    return bytes(blob)




def emit_pe64_system_command(cmd: bytes) -> bytes:
    """PE32+ x86_64 console executable: msvcrt.system(command); ExitProcess(code).

    v7.8.5: Dieser Launcher wartet auf das Runtime-Bundle. Im Unterschied zu
    WinExec kehrt er nicht sofort zurück und zeigt dadurch die echte
    Programm-Ausgabe in der Konsole. Kein externer Compiler wird benötigt.
    """
    if b"\x00" in cmd:
        raise NativeLinkerError("Launcher-Befehl enthält NUL-Byte")
    file_align = 0x200
    sect_align = 0x1000
    image_base = 0x140000000
    text_rva = 0x1000
    text_raw = 0x400

    code = bytearray()
    patches: list[tuple[int, str, int]] = []
    labels: dict[str, int] = {}

    def label(name: str) -> None:
        labels[name] = len(code)

    # Windows x64 ABI: shadow space + 16-byte alignment before calls.
    code += b"\x48\x83\xEC\x28"  # sub rsp,40
    off = len(code); code += b"\x48\x8D\x0D\x00\x00\x00\x00"; patches.append((off, "cmd", 7))  # lea rcx,cmd
    off = len(code); code += b"\xFF\x15\x00\x00\x00\x00"; patches.append((off, "iat_system", 6))  # call [system]
    code += b"\x89\xC1"  # mov ecx,eax
    off = len(code); code += b"\xFF\x15\x00\x00\x00\x00"; patches.append((off, "iat_ExitProcess", 6))  # call [ExitProcess]
    label("cmd"); code += cmd + b"\x00"

    while len(code) % 8:
        code.append(0)
    import_desc_off = len(code)
    label("import_desc")
    # two descriptors + null descriptor
    code += b"\x00" * 60

    def add_cstr(s: bytes) -> int:
        o = len(code); code.extend(s + b"\x00"); return o

    kernel32_name_off = add_cstr(b"KERNEL32.dll")
    msvcrt_name_off = add_cstr(b"msvcrt.dll")
    while len(code) % 2:
        code.append(0)

    def hint_name(name: bytes) -> int:
        o = len(code); code.extend(b"\x00\x00" + name + b"\x00")
        if len(code) % 2:
            code.append(0)
        return o

    hn_ExitProcess = hint_name(b"ExitProcess")
    hn_system = hint_name(b"system")

    while len(code) % 8:
        code.append(0)
    ilt_kernel32_off = len(code)
    code += struct.pack("<QQ", text_rva + hn_ExitProcess, 0)
    iat_kernel32_off = len(code)
    label("iat_ExitProcess"); code += struct.pack("<Q", text_rva + hn_ExitProcess)
    code += struct.pack("<Q", 0)

    ilt_msvcrt_off = len(code)
    code += struct.pack("<QQ", text_rva + hn_system, 0)
    iat_msvcrt_off = len(code)
    label("iat_system"); code += struct.pack("<Q", text_rva + hn_system)
    code += struct.pack("<Q", 0)

    # Patch import descriptors.
    struct.pack_into("<IIIII", code, import_desc_off + 0,
                     text_rva + ilt_kernel32_off, 0, 0, text_rva + kernel32_name_off, text_rva + iat_kernel32_off)
    struct.pack_into("<IIIII", code, import_desc_off + 20,
                     text_rva + ilt_msvcrt_off, 0, 0, text_rva + msvcrt_name_off, text_rva + iat_msvcrt_off)
    # third descriptor remains zero

    # Patch RIP-relative offsets.
    for off, lname, instr_size in patches:
        target = text_rva + labels[lname]
        rip_after = text_rva + off + instr_size
        disp = target - rip_after
        struct.pack_into("<i", code, off + instr_size - 4, disp)

    virtual_size = len(code)
    raw_size = _align(virtual_size, file_align)
    size_of_image = _align(text_rva + virtual_size, sect_align)

    pe_off = 0x80
    dos = bytearray(b"MZ") + bytearray(0x3A)
    dos += struct.pack("<I", pe_off)
    dos += b"\x00" * (pe_off - len(dos))

    coff = struct.pack("<IHHIIIHH", 0x00004550, 0x8664, 1, 0, 0, 0, 0xF0, 0x0022)

    opt = bytearray()
    opt += struct.pack("<HBBIII", 0x20B, 14, 0, raw_size, 0, 0)
    opt += struct.pack("<IIQ", text_rva, text_rva, image_base)
    opt += struct.pack("<II", sect_align, file_align)
    opt += struct.pack("<HHHHHH", 6, 0, 0, 0, 6, 0)
    opt += struct.pack("<I", 0)
    opt += struct.pack("<III", size_of_image, text_raw, 0)
    opt += struct.pack("<HH", 3, 0)  # console subsystem
    opt += struct.pack("<Q", 0x100000)
    opt += struct.pack("<Q", 0x1000)
    opt += struct.pack("<Q", 0x100000)
    opt += struct.pack("<Q", 0x1000)
    opt += struct.pack("<II", 0, 16)
    dirs = [(0, 0)] * 16
    dirs[1] = (text_rva + import_desc_off, 60)
    for rva, size in dirs:
        opt += struct.pack("<II", rva, size)
    assert len(opt) == 0xF0, len(opt)

    sect = struct.pack("<8sIIIIIIHHI", b".text\x00\x00\x00",
                       virtual_size, text_rva, raw_size, text_raw, 0, 0, 0, 0, 0xE0000020)

    blob = bytearray(dos + coff + opt + sect)
    if len(blob) > text_raw:
        raise NativeLinkerError("PE header größer als text_raw")
    blob += b"\x00" * (text_raw - len(blob))
    blob += code
    blob += b"\x00" * (raw_size - len(code))
    return bytes(blob)

def emit_pe64_winexec(cmd: bytes) -> bytes:
    """PE32+ x86_64 console executable: WinExec(command, SW_SHOWNORMAL)."""
    if b"\x00" in cmd:
        raise NativeLinkerError("Launcher-Befehl enthält NUL-Byte")
    file_align = 0x200
    sect_align = 0x1000
    image_base = 0x140000000
    text_rva = 0x1000
    text_raw = 0x400

    code = bytearray()
    patches: list[tuple[int, str, int]] = []
    labels: dict[str, int] = {}

    def label(name: str) -> None:
        labels[name] = len(code)

    # Windows x64 shadow space
    code += b"\x48\x83\xEC\x28"  # sub rsp,40
    off = len(code); code += b"\x48\x8D\x0D\x00\x00\x00\x00"; patches.append((off, "cmd", 7))  # lea rcx,cmd
    code += b"\xBA\x01\x00\x00\x00"  # mov edx,1
    off = len(code); code += b"\xFF\x15\x00\x00\x00\x00"; patches.append((off, "iat_WinExec", 6))
    code += b"\x31\xC9"  # xor ecx,ecx
    off = len(code); code += b"\xFF\x15\x00\x00\x00\x00"; patches.append((off, "iat_ExitProcess", 6))
    label("cmd"); code += cmd + b"\x00"

    while len(code) % 8: code += b"\x00"
    import_desc_off = len(code)
    label("import_desc")
    code += b"\x00" * 40

    def add_cstr(s: bytes) -> int:
        o = len(code); code.extend(s + b"\x00"); return o

    dll_name_off = add_cstr(b"KERNEL32.dll")
    while len(code) % 2: code += b"\x00"

    def hint_name(name: bytes) -> int:
        o = len(code); code.extend(b"\x00\x00" + name + b"\x00")
        if len(code) % 2: code.append(0)
        return o

    hn_WinExec = hint_name(b"WinExec")
    hn_ExitProcess = hint_name(b"ExitProcess")

    while len(code) % 8: code += b"\x00"
    ilt_off = len(code)
    code += struct.pack("<QQQ", text_rva + hn_WinExec, text_rva + hn_ExitProcess, 0)

    iat_off = len(code)
    label("iat_WinExec"); code += struct.pack("<Q", text_rva + hn_WinExec)
    label("iat_ExitProcess"); code += struct.pack("<Q", text_rva + hn_ExitProcess)
    code += struct.pack("<Q", 0)

    struct.pack_into("<IIIII", code, import_desc_off, text_rva + ilt_off, 0, 0, text_rva + dll_name_off, text_rva + iat_off)

    for off, lname, instr_size in patches:
        target = text_rva + labels[lname]
        rip_after = text_rva + off + instr_size
        disp = target - rip_after
        struct.pack_into("<i", code, off + instr_size - 4, disp)

    virtual_size = len(code)
    raw_size = _align(virtual_size, file_align)
    size_of_image = _align(text_rva + virtual_size, sect_align)

    pe_off = 0x80
    dos = bytearray(b"MZ") + bytearray(0x3A)
    dos += struct.pack("<I", pe_off)
    dos += b"\x00" * (pe_off - len(dos))

    coff = struct.pack("<IHHIIIHH", 0x00004550, 0x8664, 1, 0, 0, 0, 0xF0, 0x0022)

    opt = bytearray()
    opt += struct.pack("<HBBIII", 0x20B, 14, 0, raw_size, 0, 0)
    opt += struct.pack("<IIQ", text_rva, text_rva, image_base)
    opt += struct.pack("<II", sect_align, file_align)
    opt += struct.pack("<HHHHHH", 6, 0, 0, 0, 6, 0)
    opt += struct.pack("<I", 0)
    opt += struct.pack("<III", size_of_image, text_raw, 0)
    opt += struct.pack("<HH", 3, 0)
    opt += struct.pack("<Q", 0x100000)
    opt += struct.pack("<Q", 0x1000)
    opt += struct.pack("<Q", 0x100000)
    opt += struct.pack("<Q", 0x1000)
    opt += struct.pack("<II", 0, 16)
    dirs = [(0, 0)] * 16
    dirs[1] = (text_rva + import_desc_off, 40)
    for rva, size in dirs:
        opt += struct.pack("<II", rva, size)
    assert len(opt) == 0xF0, len(opt)

    sect = struct.pack("<8sIIIIIIHHI", b".text\x00\x00\x00", virtual_size, text_rva, raw_size, text_raw, 0, 0, 0, 0, 0xE0000020)

    blob = bytearray(dos + coff + opt + sect)
    if len(blob) > text_raw:
        raise NativeLinkerError("PE header größer als text_raw")
    blob += b"\x00" * (text_raw - len(blob))
    blob += code
    blob += b"\x00" * (raw_size - len(code))
    return bytes(blob)

def default_target() -> str:
    return "pe64-windows-x86_64" if os.name == "nt" else "elf64-linux-x86_64"


def emit_elf64_stdout(msg: bytes) -> bytes:
    # ELF64 ET_EXEC, Linux x86_64, single RX segment containing code+data.
    # Code:
    #   write(1, msg, len)
    #   exit(0)
    code = bytearray()
    code += b"\xB8\x01\x00\x00\x00"          # mov eax,1
    code += b"\xBF\x01\x00\x00\x00"          # mov edi,1
    lea_pos = len(code)
    code += b"\x48\x8D\x35\x00\x00\x00\x00"  # lea rsi,[rip+disp32]
    code += b"\xBA" + struct.pack("<I", len(msg))  # mov edx,len
    code += b"\x0F\x05"                      # syscall
    code += b"\xB8\x3C\x00\x00\x00"          # mov eax,60
    code += b"\x31\xFF"                      # xor edi,edi
    code += b"\x0F\x05"                      # syscall
    msg_off = len(code)
    code += msg
    # patch lea displacement: RIP after lea points to lea_pos+7
    disp = msg_off - (lea_pos + 7)
    struct.pack_into("<i", code, lea_pos + 3, disp)

    ehsize = 64
    phoff = 64
    phentsize = 56
    phnum = 1
    file_off = 0x1000
    vaddr = 0x400000 + file_off
    entry = vaddr
    filesz = len(code)
    memsz = filesz

    ident = b"\x7fELF" + bytes([2, 1, 1, 0]) + bytes(8)
    ehdr = struct.pack(
        "<16sHHIQQQIHHHHHH",
        ident, 2, 0x3E, 1, entry, phoff, 0, 0, ehsize, phentsize, phnum, 0, 0, 0
    )
    phdr = struct.pack(
        "<IIQQQQQQ",
        1, 5, file_off, vaddr, vaddr, filesz, memsz, 0x1000
    )
    blob = bytearray(ehdr + phdr)
    if len(blob) > file_off:
        raise NativeLinkerError("ELF header größer als code offset")
    blob += bytes(file_off - len(blob))
    blob += code
    return bytes(blob)


def _align(n: int, a: int) -> int:
    return (n + a - 1) // a * a


def emit_pe64_stdout(msg: bytes) -> bytes:
    # Minimal PE32+ x86_64 console executable importing kernel32:
    # GetStdHandle, WriteFile, ExitProcess.
    file_align = 0x200
    sect_align = 0x1000
    image_base = 0x140000000
    text_rva = 0x1000
    text_raw = 0x400

    code = bytearray()
    patches: list[tuple[int, str, int]] = []  # offset, label, instr_end_adjust already inherent via offset+size

    def label(name: str) -> int:
        labels[name] = len(code)
        return labels[name]

    labels: dict[str, int] = {}

    # sub rsp, 40
    code += b"\x48\x83\xEC\x28"
    # mov rcx, -11
    code += b"\x48\xC7\xC1\xF5\xFF\xFF\xFF"
    # call [rip + iat_GetStdHandle]
    off = len(code); code += b"\xFF\x15\x00\x00\x00\x00"; patches.append((off, "iat_GetStdHandle", 6))
    # mov rcx, rax
    code += b"\x48\x89\xC1"
    # lea rdx, [rip + msg]
    off = len(code); code += b"\x48\x8D\x15\x00\x00\x00\x00"; patches.append((off, "msg", 7))
    # mov r8d, len
    code += b"\x41\xB8" + struct.pack("<I", len(msg))
    # lea r9, [rip + written]
    off = len(code); code += b"\x4C\x8D\x0D\x00\x00\x00\x00"; patches.append((off, "written", 7))
    # mov qword ptr [rsp+32], 0
    code += b"\x48\xC7\x44\x24\x20\x00\x00\x00\x00"
    # call [rip + iat_WriteFile]
    off = len(code); code += b"\xFF\x15\x00\x00\x00\x00"; patches.append((off, "iat_WriteFile", 6))
    # xor ecx, ecx
    code += b"\x31\xC9"
    # call [rip + iat_ExitProcess]
    off = len(code); code += b"\xFF\x15\x00\x00\x00\x00"; patches.append((off, "iat_ExitProcess", 6))

    label("msg"); code += msg
    while len(code) % 8: code += b"\x00"
    label("written"); code += b"\x00\x00\x00\x00\x00\x00\x00\x00"

    # Import structures aligned
    while len(code) % 8: code += b"\x00"
    import_desc_off = len(code)
    label("import_desc")
    code += b"\x00" * 40  # one descriptor + null descriptor

    def add_cstr(s: bytes) -> int:
        o = len(code); code.extend(s + b"\x00"); return o

    dll_name_off = add_cstr(b"KERNEL32.dll")
    while len(code) % 2: code += b"\x00"
    def hint_name(name: bytes) -> int:
        o = len(code); code.extend(b"\x00\x00" + name + b"\x00")
        if len(code) % 2: code.append(0)
        return o
    hn_GetStdHandle = hint_name(b"GetStdHandle")
    hn_WriteFile = hint_name(b"WriteFile")
    hn_ExitProcess = hint_name(b"ExitProcess")

    while len(code) % 8: code += b"\x00"
    ilt_off = len(code)
    code += struct.pack("<QQQQ", text_rva + hn_GetStdHandle, text_rva + hn_WriteFile, text_rva + hn_ExitProcess, 0)

    iat_off = len(code)
    label("iat_GetStdHandle"); code += struct.pack("<Q", text_rva + hn_GetStdHandle)
    label("iat_WriteFile"); code += struct.pack("<Q", text_rva + hn_WriteFile)
    label("iat_ExitProcess"); code += struct.pack("<Q", text_rva + hn_ExitProcess)
    code += struct.pack("<Q", 0)

    # Patch import descriptor
    struct.pack_into("<IIIII", code, import_desc_off, text_rva + ilt_off, 0, 0, text_rva + dll_name_off, text_rva + iat_off)

    # Patch RIP-relative offsets
    for off, lname, instr_size in patches:
        target = text_rva + labels[lname]
        rip_after = text_rva + off + instr_size
        disp = target - rip_after
        struct.pack_into("<i", code, off + instr_size - 4, disp)

    virtual_size = len(code)
    raw_size = _align(virtual_size, file_align)
    size_of_image = _align(text_rva + virtual_size, sect_align)

    # DOS header and PE offset
    pe_off = 0x80
    dos = bytearray(b"MZ") + bytearray(0x3A)
    dos += struct.pack("<I", pe_off)
    dos += b"\x00" * (pe_off - len(dos))

    coff = struct.pack(
        "<IHHIIIHH",
        0x00004550, 0x8664, 1, 0, 0, 0,
        0xF0, 0x0022  # executable, large-address-aware
    )

    # PE32+ optional header
    opt = bytearray()
    opt += struct.pack("<HBBIII", 0x20B, 14, 0, raw_size, 0, 0)
    opt += struct.pack("<IIQ", text_rva, text_rva, image_base)
    opt += struct.pack("<II", sect_align, file_align)
    opt += struct.pack("<HHHHHH", 6, 0, 0, 0, 6, 0)
    opt += struct.pack("<I", 0)
    opt += struct.pack("<III", size_of_image, text_raw, 0)
    opt += struct.pack("<HH", 3, 0)  # console subsystem
    opt += struct.pack("<Q", 0x100000)
    opt += struct.pack("<Q", 0x1000)
    opt += struct.pack("<Q", 0x100000)
    opt += struct.pack("<Q", 0x1000)
    opt += struct.pack("<II", 0, 16)
    dirs = [(0, 0)] * 16
    dirs[1] = (text_rva + import_desc_off, 40)  # import directory
    for rva, size in dirs:
        opt += struct.pack("<II", rva, size)
    assert len(opt) == 0xF0, len(opt)

    name = b".text\x00\x00\x00"
    sect = struct.pack(
        "<8sIIIIIIHHI",
        name, virtual_size, text_rva, raw_size, text_raw, 0, 0, 0, 0,
        0xE0000020  # code | execute | read | write
    )

    blob = bytearray(dos + coff + opt + sect)
    if len(blob) > text_raw:
        raise NativeLinkerError("PE header größer als text_raw")
    blob += b"\x00" * (text_raw - len(blob))
    blob += code
    blob += b"\x00" * (raw_size - len(code))
    return bytes(blob)
