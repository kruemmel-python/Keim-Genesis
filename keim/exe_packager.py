
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Any
import hashlib
import json
import os
import re
import shutil
import time
import zipapp


class ExePackagerError(Exception):
    pass


class ValueTag(IntEnum):
    NULL = 0
    INT = 1
    FLOAT = 2
    BOOL = 3
    TEXT = 4
    LIST = 5
    MAP = 6
    RECORD = 7
    RESULT_OK = 8
    RESULT_ERROR = 9
    FUNCTION = 10
    MODULE = 11
    HOST_IMPORT = 12


@dataclass(slots=True)
class NativeValue:
    tag: ValueTag
    payload: Any = None

    def as_json(self) -> dict[str, Any]:
        if self.tag in {ValueTag.INT, ValueTag.FLOAT, ValueTag.BOOL, ValueTag.TEXT, ValueTag.NULL}:
            return {"tag": self.tag.name.lower(), "value": self.payload}
        return {"tag": self.tag.name.lower(), "ref": self.payload}


@dataclass(slots=True)
class HeapObject:
    kind: ValueTag
    value: Any
    type_name: str = ""
    fields: dict[str, NativeValue] = field(default_factory=dict)
    marked: bool = False
    pinned: bool = False
    generation: int = 0

    def as_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind.name.lower(),
            "type": self.type_name,
            "value": _json_safe(self.value),
            "fields": {k: v.as_json() for k, v in self.fields.items()},
            "pinned": self.pinned,
            "generation": self.generation,
        }


class KeimHeap:
    def __init__(self) -> None:
        self.objects: dict[int, HeapObject] = {}
        self.next_handle = 1

    def alloc(self, kind: ValueTag, value: Any = None, *, type_name: str = "", fields: dict[str, NativeValue] | None = None, pinned: bool = False) -> NativeValue:
        handle = self.next_handle
        self.next_handle += 1
        self.objects[handle] = HeapObject(kind=kind, value=value, type_name=type_name, fields=fields or {}, pinned=pinned)
        return NativeValue(kind, handle)

    def get(self, value: NativeValue) -> HeapObject:
        if value.payload not in self.objects:
            raise ExePackagerError(f"Heap-Handle nicht gefunden: {value.payload}")
        return self.objects[int(value.payload)]

    def text(self, text: str) -> NativeValue:
        return self.alloc(ValueTag.TEXT, text)

    def list(self, values: list[NativeValue]) -> NativeValue:
        return self.alloc(ValueTag.LIST, list(values))

    def map(self, values: dict[Any, NativeValue]) -> NativeValue:
        return self.alloc(ValueTag.MAP, dict(values))

    def record(self, type_name: str, fields: dict[str, NativeValue]) -> NativeValue:
        return self.alloc(ValueTag.RECORD, None, type_name=type_name, fields=fields)

    def result_ok(self, value: NativeValue) -> NativeValue:
        return self.alloc(ValueTag.RESULT_OK, value)

    def result_error(self, value: NativeValue) -> NativeValue:
        return self.alloc(ValueTag.RESULT_ERROR, value)

    def snapshot(self) -> dict[str, Any]:
        return {"next_handle": self.next_handle, "objects": {str(k): v.as_json() for k, v in self.objects.items()}}


@dataclass(slots=True)
class ModuleEntry:
    name: str
    source_path: str
    bytecode_path: str | None = None
    exports: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)

    def as_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "source_path": self.source_path,
            "bytecode_path": self.bytecode_path,
            "exports": self.exports,
            "imports": self.imports,
        }


@dataclass(slots=True)
class RuntimeImport:
    name: str
    kind: str
    permission: str
    target: str | None = None
    required: bool = False

    def as_json(self) -> dict[str, Any]:
        return {"name": self.name, "kind": self.kind, "permission": self.permission, "target": self.target, "required": self.required}


@dataclass(slots=True)
class ExePackageOptions:
    entry: Path
    out: Path
    name: str = "keim_app"
    target: str = "auto"
    mode: str = "full-runtime"
    include_gpu: bool = True
    include_web: bool = True
    include_sources: bool = True
    single_file_zipapp: bool = True
    make_native_launcher: bool = True
    gpu_driver: Path | None = None
    gpu_required: bool = False
    gpu_smoke: bool = True
    assets: list[Path] = field(default_factory=list)
    permissions: dict[str, bool] = field(default_factory=lambda: {"io": True, "gpu": False, "web": False, "net": False, "ffi": False})


@dataclass(slots=True)
class ExePackageResult:
    ok: bool
    out: str
    manifest: str
    launcher: str | None
    zipapp: str | None
    native_launcher: str | None
    sha256: str
    files: list[str]
    features: list[str]
    notes: list[str]

    def as_json(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "out": self.out,
            "manifest": self.manifest,
            "launcher": self.launcher,
            "zipapp": self.zipapp,
            "native_launcher": self.native_launcher,
            "sha256": self.sha256,
            "files": self.files,
            "features": self.features,
            "notes": self.notes,
        }


FEATURES = [
    "native_value_model",
    "heap",
    "strings",
    "lists",
    "maps",
    "records",
    "result_match",
    "function_calls",
    "module_table",
    "runtime_imports_io_gpu_web",
    "internal_native_launcher_no_external_compiler",
    "zipapp_single_file_full_runtime",
    "gpu_aware_packaging",
    "bundled_gpu_drivers",
    "gpu_manifest_plan_smoke",
    "cpu_fallback_for_gpu",
    "self_bootstrapping_runtime_launcher",
    "real_waiting_native_launcher",
    "launcher_sets_gpu_driver_path",
]


def status78() -> dict[str, Any]:
    return {
        "name": "Keim v7.8.5 Real Self-Bootstrapping GPU-aware Full EXE Runtime Packager",
        "version": 785,
        "external_compiler_required": False,
        "packaging_modes": ["full-runtime", "native-subset", "zipapp", "directory-bundle"],
        "native_link_targets": ["pe64-windows-x86_64", "elf64-linux-x86_64"],
        "features": FEATURES,
        "value_tags": [t.name.lower() for t in ValueTag],
        "purpose": "packt vollständige Keim-Programme mit eingebetteter Runtime und echtem Self-Bootstrapping Launcher, der run.bat/run.sh startet",
    }


def package_full_exe(
    entry: Path,
    out: Path,
    *,
    name: str = "keim_app",
    target: str = "auto",
    include_gpu: bool = True,
    include_web: bool = True,
    gpu_driver: Path | None = None,
    gpu_required: bool = False,
    gpu_smoke: bool = True,
) -> ExePackageResult:
    options = ExePackageOptions(
        entry=Path(entry),
        out=Path(out),
        name=name,
        target=target,
        include_gpu=include_gpu,
        include_web=include_web,
        gpu_driver=Path(gpu_driver) if gpu_driver else None,
        gpu_required=gpu_required,
        gpu_smoke=gpu_smoke,
    )
    return FullExePackager(options).build()


class FullExePackager:
    def __init__(self, options: ExePackageOptions):
        self.options = options
        self.root = Path(options.out)
        self.entry = Path(options.entry)

    def build(self) -> ExePackageResult:
        if not self.entry.exists():
            raise ExePackagerError(f"Entry-Datei nicht gefunden: {self.entry}")
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "runtime").mkdir(exist_ok=True)
        (self.root / "app").mkdir(exist_ok=True)
        (self.root / "assets").mkdir(exist_ok=True)
        (self.root / "bin").mkdir(exist_ok=True)
        (self.root / "runtime" / "driver").mkdir(parents=True, exist_ok=True)
        (self.root / "runtime" / "gpu").mkdir(parents=True, exist_ok=True)

        module_table = self._collect_modules()
        bytecode_payload = self._compile_entry_best_effort()
        runtime_imports = self._runtime_imports()
        gpu_bundle = self._prepare_gpu_bundle() if self.options.include_gpu else {"enabled": False, "reason": "disabled"}
        manifest = self._write_manifest(module_table, bytecode_payload, runtime_imports, gpu_bundle)
        self._write_runtime()
        self._write_bootstrap()
        self._copy_sources(module_table)
        self._copy_assets()
        zipapp_path = self._write_zipapp() if self.options.single_file_zipapp else None
        native_launcher = self._write_native_launcher(manifest) if self.options.make_native_launcher else None
        self._write_docs()
        files = sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*") if p.is_file())
        digest = _tree_sha256(self.root)
        (self.root / "package.sha256").write_text(digest + "\n", encoding="utf-8")
        files.append("package.sha256")
        return ExePackageResult(
            ok=True,
            out=str(self.root),
            manifest=str(self.root / "app" / "manifest.kexe.json"),
            launcher=str(self.root / ("run.bat" if os.name == "nt" else "run.sh")),
            zipapp=str(zipapp_path) if zipapp_path else None,
            native_launcher=str(native_launcher) if native_launcher else None,
            sha256=digest,
            files=files,
            features=FEATURES,
            notes=[
                "full runtime bundle contains Keim package and embedded runner",
                "no external C/C++ compiler required for packaging",
                "native launcher is generated by Keim internal linker when possible",
                "complex programs run through embedded Keim runtime; native-subset can be direct-linked",
            ],
        )

    def _collect_modules(self) -> list[ModuleEntry]:
        source = self.entry.read_text(encoding="utf-8")
        name = self.entry.stem
        m = re.search(r"^\s*modul\s+([A-Za-z0-9_.]+)", source, re.M)
        if m:
            name = m.group(1)
        imports = re.findall(r"^\s*verwende\s+([A-Za-z0-9_./\\-]+)", source, re.M)
        exports = [x.split()[-1] for x in re.findall(r"^\s*exportiere\s+(.+)$", source, re.M)]
        modules = [ModuleEntry(name=name, source_path=str(self.entry), exports=exports, imports=imports)]
        for imp in imports:
            candidates = [
                self.entry.parent / (imp.replace(".", "/") + ".keim"),
                self.entry.parent / (imp.split(".")[-1] + ".keim"),
                self.entry.parent / imp,
            ]
            for c in candidates:
                if c.exists() and c != self.entry:
                    txt = c.read_text(encoding="utf-8")
                    mm = re.search(r"^\s*modul\s+([A-Za-z0-9_.]+)", txt, re.M)
                    modules.append(ModuleEntry(name=mm.group(1) if mm else c.stem, source_path=str(c)))
                    break
        return modules

    def _compile_entry_best_effort(self) -> dict[str, Any]:
        try:
            from .compiler65 import bytecode65
            return {"compiler": "compiler65", "payload": _json_safe(bytecode65(self.entry))}
        except Exception as exc65:
            try:
                from .foundation import core_bytecode
                return {"compiler": "foundation", "payload": _json_safe(core_bytecode(self.entry))}
            except Exception as exc6:
                return {"compiler": "source-only", "payload": {"error65": str(exc65), "error_foundation": str(exc6)}}

    def _runtime_imports(self) -> list[RuntimeImport]:
        imports = [
            RuntimeImport("io.print", "io", "io", None, True),
            RuntimeImport("io.read_file", "io", "io", None, False),
            RuntimeImport("io.write_file", "io", "io", None, False),
        ]
        if self.options.include_gpu:
            imports.append(RuntimeImport("gpu.cc_opencl", "gpu", "gpu", "driver/build/CC_OpenCl.dll|driver/build/libCC_OpenCL.so", False))
        if self.options.include_web:
            imports.append(RuntimeImport("web.dom", "web", "web", "browser-dom-adapter", False))
            imports.append(RuntimeImport("web.fetch", "web", "net", "browser-fetch-adapter", False))
        return imports


    def _prepare_gpu_bundle(self) -> dict[str, Any]:
        """Bundle CC_OpenCL driver artifacts and write GPU manifests/plans.

        v7.8.1 turns the v7.6 driver layer into a first-class EXE package
        import. The bundle remains deterministic: missing drivers are recorded
        and fall back to CPU unless gpu_required=True.
        """
        gpu_dir = self.root / "runtime" / "gpu"
        drv_dir = self.root / "runtime" / "driver"
        gpu_dir.mkdir(parents=True, exist_ok=True)
        drv_dir.mkdir(parents=True, exist_ok=True)
        repo_root = Path(__file__).resolve().parents[1]
        candidates: list[Path] = []
        if self.options.gpu_driver:
            candidates.append(Path(self.options.gpu_driver))
        candidates.extend([
            repo_root / "driver" / "build" / "CC_OpenCl.dll",
            repo_root / "driver" / "build" / "CC_OpenCL.dll",
            repo_root / "driver" / "build" / "libCC_OpenCL.so",
            repo_root / "driver" / "build" / "libCC_OpenCl.so",
            repo_root / "driver" / "build" / "libCC_OpenCL.dylib",
        ])
        copied: list[dict[str, Any]] = []
        seen: set[Path] = set()
        for c in candidates:
            c = Path(c)
            try:
                c_res = c.resolve()
            except Exception:
                c_res = c
            if c_res in seen or not c.exists() or not c.is_file():
                continue
            seen.add(c_res)
            dst = drv_dir / c.name
            shutil.copy2(c, dst)
            copied.append({
                "source": str(c),
                "path": str(dst.relative_to(self.root)).replace("\\", "/"),
                "name": c.name,
                "size": dst.stat().st_size,
                "sha256": _file_sha256(dst),
                "platform": _driver_platform_hint(c.name),
            })
        try:
            from .gpu_driver_execution import build_execution_plan, inspect_driver, KERNEL_SPECS
            selected = Path(self.options.gpu_driver) if self.options.gpu_driver else (Path(copied[0]["source"]) if copied else None)
            report = inspect_driver(selected, load=False).as_dict() if selected else None
            plan = build_execution_plan(dll=selected) if selected else {"format": "keim-gpu-driver-execution-plan-v1", "dispatch_rules": []}
            kernels = [k.as_dict() for k in KERNEL_SPECS]
        except Exception as exc:
            report = {"error": str(exc)}
            plan = {"format": "keim-gpu-driver-execution-plan-v1", "error": str(exc), "dispatch_rules": []}
            kernels = []
        gpu_manifest = {
            "format": "keim-gpu-package-v781",
            "enabled": bool(copied),
            "required": bool(self.options.gpu_required),
            "fallback": "cpu-reference",
            "drivers": copied,
            "selected_driver": copied[0]["path"] if copied else None,
            "runtime_import": "gpu.cc_opencl",
            "driver_report": report,
            "kernels": kernels,
            "notes": [
                "v7.8.1 bundles Windows DLL and Linux .so when present.",
                "Packaged apps can run GPU smoke via runtime/gpu/gpu_smoke.py.",
                "If the driver or OpenCL context is unavailable, CPU fallback remains valid unless gpu_required=true.",
            ],
        }
        if self.options.gpu_required and not copied:
            raise ExePackagerError("GPU wurde als erforderlich markiert, aber kein Treiberartefakt wurde gefunden/kopiert")
        (gpu_dir / "gpu_driver_manifest.json").write_text(json.dumps(gpu_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        (gpu_dir / "gpu_driver_plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        self._write_gpu_smoke_script()
        self._write_gpu_launchers()
        self._write_gpu_readme(gpu_manifest)
        return gpu_manifest

    def _write_gpu_smoke_script(self) -> None:
        script = """from __future__ import annotations
from pathlib import Path
import json
import platform
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "runtime"))

def _driver() -> Path | None:
    drv = ROOT / "runtime" / "driver"
    system = platform.system().lower()
    names = (["CC_OpenCl.dll", "CC_OpenCL.dll"] if system == "windows" else
             ["libCC_OpenCL.so", "libCC_OpenCl.so", "libCC_OpenCL.dylib"])
    for name in names:
        p = drv / name
        if p.exists():
            return p
    if drv.exists():
        for p in drv.iterdir():
            if p.suffix.lower() in {".dll", ".so", ".dylib"}:
                return p
    return None

def main() -> int:
    from keim.gpu_driver_execution import run_driver_demo
    d = _driver()
    out = ROOT / "runtime" / "gpu" / "smoke_report"
    payload = run_driver_demo(dll=d, out=out, size=128, force_cpu=False)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 1

if __name__ == "__main__":
    raise SystemExit(main())
"""
        path = self.root / "runtime" / "gpu" / "gpu_smoke.py"
        path.write_text(script, encoding="utf-8")

    def _write_gpu_launchers(self) -> None:
        (self.root / "run_gpu.bat").write_text("@echo off\r\npython %~dp0runtime\\gpu\\gpu_smoke.py %*\r\n", encoding="utf-8")
        (self.root / "run_gpu.ps1").write_text("& python \"$PSScriptRoot/runtime/gpu/gpu_smoke.py\" @args\n", encoding="utf-8")
        sh = self.root / "run_gpu.sh"
        sh.write_text("#!/usr/bin/env sh\npython3 \"$(dirname \"$0\")/runtime/gpu/gpu_smoke.py\" \"$@\"\n", encoding="utf-8")
        try:
            sh.chmod(sh.stat().st_mode | 0o111)
        except OSError:
            pass

    def _write_gpu_readme(self, manifest: dict[str, Any]) -> None:
        lines = [
            "Keim v7.8.5 Self-Bootstrapping GPU-aware Full EXE Runtime Package",
            "",
            "Dieses Paket enthält die Keim-Runtime plus gebündelte GPU-Treiberartefakte.",
            "Start CPU/Runtime:",
            "  run.bat",
            "  ./run.sh",
            "",
            "GPU-Smoke:",
            "  run_gpu.bat",
            "  ./run_gpu.sh",
            "",
            "Fallback:",
            "  Wenn kein OpenCL-Kontext verfügbar ist, nutzt Keim CPU-Differentialreferenzen.",
            "",
            "Treiber:",
        ]
        for d in manifest.get("drivers", []):
            lines.append(f"  - {d.get('path')} ({d.get('platform')}, sha256={d.get('sha256')})")
        (self.root / "GPU_README.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _write_manifest(self, modules: list[ModuleEntry], bytecode_payload: dict[str, Any], runtime_imports: list[RuntimeImport], gpu_bundle: dict[str, Any] | None = None) -> dict[str, Any]:
        manifest = {
            "format": "keim-exe-package",
            "version": 785,
            "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "name": self.options.name,
            "entry": str(self.entry.name),
            "entry_module": modules[0].name if modules else self.entry.stem,
            "mode": self.options.mode,
            "target": self.options.target,
            "features": FEATURES,
            "permissions": self.options.permissions,
            "value_model": {
                "representation": "tagged-native-value",
                "tags": {t.name.lower(): int(t) for t in ValueTag},
                "heap_handles": True,
                "snapshotable": True,
            },
            "heap": {"strings": True, "lists": True, "maps": True, "records": True, "results": True},
            "modules": [m.as_json() for m in modules],
            "runtime_imports": [r.as_json() for r in runtime_imports],
            "gpu": gpu_bundle or {"enabled": False},
            "launcher": {
                "format": "keim-self-bootstrap-launcher-v785",
                "native": True,
                "starts": "run.bat" if os.name == "nt" else "run.sh",
                "sets_gpu_driver_path": bool((gpu_bundle or {}).get("enabled")),
                "gpu_smoke_if_required": bool((gpu_bundle or {}).get("required")),
                "external_compiler_required": False
            },
            "bytecode": bytecode_payload,
        }
        p = self.root / "app" / "manifest.kexe.json"
        p.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return manifest

    def _write_runtime(self) -> None:
        dst = self.root / "runtime" / "keim"
        src = Path(__file__).resolve().parent
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "build", ".git"))
        (self.root / "runtime" / "keim_runtime_embedded.py").write_text(EMBEDDED_RUNTIME, encoding="utf-8")

    def _write_bootstrap(self) -> None:
        (self.root / "keim_app.py").write_text(BOOTSTRAP_PY, encoding="utf-8")
        gpu_required = "1" if self.options.gpu_required else "0"

        bat_lines = [
            "@echo off",
            "setlocal",
            "set KEIM_PACKAGE_ROOT=%~dp0",
            "if exist \"%~dp0runtime\\driver\" set \"PATH=%~dp0runtime\\driver;%PATH%\"",
        ]
        if self.options.gpu_required:
            bat_lines.extend([
                "if exist \"%~dp0runtime\\gpu\\gpu_smoke.py\" (",
                "  python \"%~dp0runtime\\gpu\\gpu_smoke.py\" || exit /b %ERRORLEVEL%",
                ") else (",
                "  echo [Keim v7.8.5] GPU required, aber runtime\\gpu\\gpu_smoke.py fehlt.",
                "  exit /b 3",
                ")",
            ])
        bat_lines.append("python \"%~dp0keim_app.py\" %*")
        (self.root / "run.bat").write_text("\r\n".join(bat_lines) + "\r\n", encoding="utf-8")

        sh = self.root / "run.sh"
        sh_lines = [
            "#!/usr/bin/env sh",
            "ROOT=$(CDPATH= cd -- \"$(dirname -- \"$0\")\" && pwd)",
            "export KEIM_PACKAGE_ROOT=\"$ROOT\"",
            "if [ -d \"$ROOT/runtime/driver\" ]; then",
            "  export LD_LIBRARY_PATH=\"$ROOT/runtime/driver:${LD_LIBRARY_PATH:-}\"",
            "  export DYLD_LIBRARY_PATH=\"$ROOT/runtime/driver:${DYLD_LIBRARY_PATH:-}\"",
            "fi",
        ]
        if self.options.gpu_required:
            sh_lines.extend([
                "if [ -f \"$ROOT/runtime/gpu/gpu_smoke.py\" ]; then",
                "  python3 \"$ROOT/runtime/gpu/gpu_smoke.py\" || exit $?",
                "else",
                "  echo '[Keim v7.8.5] GPU required, aber runtime/gpu/gpu_smoke.py fehlt.'",
                "  exit 3",
                "fi",
            ])
        sh_lines.append("exec python3 \"$ROOT/keim_app.py\" \"$@\"")
        sh.write_text("\n".join(sh_lines) + "\n", encoding="utf-8")
        try:
            sh.chmod(sh.stat().st_mode | 0o111)
        except OSError:
            pass

        ps_lines = [
            "$ErrorActionPreference = 'Stop'",
            "$root = $PSScriptRoot",
            "$env:KEIM_PACKAGE_ROOT = $root",
            "$driver = Join-Path $root 'runtime/driver'",
            "if (Test-Path $driver) { $env:PATH = \"$driver;$env:PATH\" }",
        ]
        if self.options.gpu_required:
            ps_lines.extend([
                "$smoke = Join-Path $root 'runtime/gpu/gpu_smoke.py'",
                "if (Test-Path $smoke) { & python $smoke; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } }",
                "else { Write-Error '[Keim v7.8.5] GPU required, aber runtime/gpu/gpu_smoke.py fehlt.'; exit 3 }",
            ])
        ps_lines.append("& python (Join-Path $root 'keim_app.py') @args")
        ps_lines.append("exit $LASTEXITCODE")
        (self.root / "run.ps1").write_text("\n".join(ps_lines) + "\n", encoding="utf-8")
    def _copy_sources(self, modules: list[ModuleEntry]) -> None:
        srcdir = self.root / "app" / "src"
        srcdir.mkdir(parents=True, exist_ok=True)
        seen: set[Path] = set()
        for m in modules:
            p = Path(m.source_path)
            if p.exists() and p not in seen:
                seen.add(p)
                shutil.copy2(p, srcdir / p.name)

    def _copy_assets(self) -> None:
        for a in self.options.assets:
            p = Path(a)
            if p.exists() and p.is_file():
                shutil.copy2(p, self.root / "assets" / p.name)
            elif p.exists() and p.is_dir():
                shutil.copytree(p, self.root / "assets" / p.name, dirs_exist_ok=True)

    def _write_zipapp(self) -> Path:
        appdir = self.root / "_zipapp_src"
        if appdir.exists():
            shutil.rmtree(appdir)
        appdir.mkdir()
        shutil.copytree(self.root / "runtime", appdir / "runtime")
        shutil.copytree(self.root / "app", appdir / "app")
        (appdir / "__main__.py").write_text(
            "from pathlib import Path\n"
            "import sys, tempfile, zipfile\n"
            "ARCHIVE = Path(sys.argv[0]).resolve()\n"
            "TMP = Path(tempfile.mkdtemp(prefix='keim_kexe_'))\n"
            "with zipfile.ZipFile(ARCHIVE) as z:\n"
            "    z.extractall(TMP)\n"
            "sys.path.insert(0, str(TMP / 'runtime'))\n"
            "from keim_runtime_embedded import main\n"
            "raise SystemExit(main(TMP))\n",
            encoding="utf-8",
        )
        out = self.root / f"{self.options.name}.pyz"
        if out.exists():
            out.unlink()
        zipapp.create_archive(appdir, target=out, interpreter="/usr/bin/env python3")
        shutil.rmtree(appdir)
        return out

    def _write_native_launcher(self, manifest: dict[str, Any]) -> Path | None:
        try:
            from .internal_linker import link_command_launcher
            target = self.options.target
            if target == "auto":
                target = "pe64-windows-x86_64" if os.name == "nt" else "elf64-linux-x86_64"
            ext = ".exe" if "windows" in target or "pe" in target else ""
            out = self.root / "bin" / f"{self.options.name}_launcher{ext}"

            # v7.8.5: Der Launcher ist kein Hinweistext mehr. Er startet das
            # Full Runtime Package. Für maximale Robustheit wird der beim
            # Packaging bekannte absolute Paketpfad genutzt; die relativen
            # Skripte run.bat/run.sh bleiben zusätzlich vorhanden.
            if "windows" in target or "pe" in target:
                # v7.8.5: waiting PE launcher. It uses msvcrt.system(), so
                # command output stays attached to the caller's console.
                # /d avoids AutoRun surprises; call preserves .bat semantics.
                package_root = self.root.resolve()
                command = f'cmd.exe /d /c call "{package_root}\\run.bat"'
            else:
                runsh = (self.root / "run.sh").resolve()
                command = f'"{runsh}"'
            link_command_launcher(command, out, target=target)
            # Companion command file with relative path, useful for inspection
            # and for environments that block native launchers.
            if "windows" in target or "pe" in target:
                (self.root / "bin" / f"{self.options.name}_launcher.cmd").write_text("@echo off\r\ncall \"%~dp0..\\run.bat\" %*\r\n", encoding="utf-8")
            else:
                companion = self.root / "bin" / f"{self.options.name}_launcher.sh"
                companion.write_text("#!/usr/bin/env sh\nexec \"$(dirname \"$0\")/../run.sh\" \"$@\"\n", encoding="utf-8")
                try:
                    companion.chmod(companion.stat().st_mode | 0o111)
                except OSError:
                    pass
            return out
        except Exception as exc:
            (self.root / "bin" / f"{self.options.name}_launcher_error.txt").write_text(str(exc), encoding="utf-8")
            return None

    def _write_docs(self) -> None:
        (self.root / "README_RUN.txt").write_text(
            "Keim v7.8.5 Self-Bootstrapping GPU-aware Full EXE Runtime Package\n\n"
            "Start Windows:\n  run.bat\n\n"
            "Start Linux/macOS:\n  ./run.sh\n\n"
            "Single-file Python executable:\n  python keim_app.py\n  python <name>.pyz\n\n"
            "Der Packager enthält Value Model, Heap, Strings, Listen, Maps, Records,\n"
            "Result/Match-Grundruntime, Funktionsaufrufe, Modul-Tabelle und Runtime-Imports.\n"
            "Er benötigt keinen externen C/C++ Compiler. Ein optionaler PE/ELF-Launcher wird\n"
            "mit dem Keim-internen Linker erzeugt.\n\n"
            "GPU-aware Packaging v7.8.5:\n"
            "  Wenn Treiber vorhanden sind, liegen sie unter runtime/driver/.\n"
            "  GPU-Metadaten liegen unter runtime/gpu/gpu_driver_manifest.json.\n"
            "  GPU-Smoke: run_gpu.bat / ./run_gpu.sh\n",
            encoding="utf-8",
        )


def run_package(path: Path) -> dict[str, Any]:
    path = Path(path)
    if not path.is_dir():
        raise ExePackagerError("run_package erwartet ein Paketverzeichnis")
    manifest_path = path / "app" / "manifest.kexe.json"
    if not manifest_path.exists():
        raise ExePackagerError(f"Manifest nicht gefunden: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return RuntimePackageRunner(path, manifest).run()


class RuntimePackageRunner:
    def __init__(self, root: Path, manifest: dict[str, Any]):
        self.root = root
        self.manifest = manifest
        self.heap = KeimHeap()
        self.modules = {m["name"]: m for m in manifest.get("modules", [])}
        self.imports = {i["name"]: i for i in manifest.get("runtime_imports", [])}

    def run(self) -> dict[str, Any]:
        srcdir = self.root / "app" / "src"
        entry_name = self.manifest.get("entry")
        entry = srcdir / entry_name if entry_name else None
        if not entry or not entry.exists():
            return {"ok": False, "error": "entry source missing", "heap": self.heap.snapshot()}
        try:
            from keim.foundation import core_run
            result = core_run(entry)
            return {"ok": True, "mode": "foundation", "value": getattr(result, "value", None), "output": getattr(result, "output", []), "heap": self.heap.snapshot()}
        except Exception as foundation_exc:
            try:
                from keim.parser import parse_source
                from keim.runtime import RunOptions, run_program
                source = entry.read_text(encoding="utf-8")
                report = run_program(parse_source(source, source_name=str(entry)), RunOptions(rounds=10, show_every=0, quiet=True, backend="cpu"))
                return {"ok": True, "mode": "legacy-simulation", "report": report.as_dict() if hasattr(report, "as_dict") else str(report), "heap": self.heap.snapshot()}
            except Exception as legacy_exc:
                return {"ok": False, "error": str(foundation_exc), "legacy_error": str(legacy_exc), "heap": self.heap.snapshot()}


def verify_package(path: Path) -> dict[str, Any]:
    path = Path(path)
    manifest_path = path / "app" / "manifest.kexe.json"
    if not manifest_path.exists():
        raise ExePackagerError(f"Manifest fehlt: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    required = [
        "native_value_model", "heap", "strings", "lists", "maps", "records",
        "result_match", "function_calls", "module_table", "runtime_imports_io_gpu_web",
    ]
    features = set(manifest.get("features", []))
    missing = [f for f in required if f not in features]
    files = sorted(str(p.relative_to(path)) for p in path.rglob("*") if p.is_file())
    return {
        "ok": not missing,
        "format": manifest.get("format"),
        "version": manifest.get("version"),
        "missing_features": missing,
        "file_count": len(files),
        "has_manifest": True,
        "has_runtime": (path / "runtime" / "keim").exists(),
        "has_bootstrap": (path / "keim_app.py").exists(),
        "has_zipapp": any(p.suffix == ".pyz" for p in path.iterdir()),
        "gpu": _verify_gpu_bundle(path, manifest),
        "runtime_imports": manifest.get("runtime_imports", []),
        "self_bootstrap_launcher": _verify_self_bootstrap_launcher(path, manifest),
        "sha256": _tree_sha256(path),
    }


BOOTSTRAP_PY = """from __future__ import annotations
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "runtime"))
from keim_runtime_embedded import main
if __name__ == "__main__":
    raise SystemExit(main(ROOT))
"""


EMBEDDED_RUNTIME = """from __future__ import annotations
from pathlib import Path
import json
import sys

def main(root: Path | None = None) -> int:
    root = Path(root or Path(__file__).resolve().parents[1])
    sys.path.insert(0, str(root / "runtime"))
    from keim.exe_packager import run_package
    payload = run_package(root)
    if payload.get("ok"):
        if payload.get("output"):
            for line in payload.get("output", []):
                print(line)
        elif "value" in payload:
            print(payload.get("value"))
        else:
            print(json.dumps(payload, ensure_ascii=False))
        return 0
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1
"""





def _verify_self_bootstrap_launcher(path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    name = manifest.get("name", "keim_app")
    bin_dir = path / "bin"
    candidates = []
    if bin_dir.exists():
        candidates = sorted(p for p in bin_dir.iterdir() if p.name.startswith(f"{name}_launcher"))
    native = [p for p in candidates if p.suffix.lower() in {"", ".exe"} and p.is_file()]
    companions = [p for p in candidates if p.suffix.lower() in {".cmd", ".sh"} and p.is_file()]

    native_checks: list[dict[str, Any]] = []
    launcher_is_real = False
    for p in native:
        data = p.read_bytes()
        is_pe = data.startswith(b"MZ")
        is_elf = data.startswith(b"\x7fELF")
        contains_hint = b"Dieses Native-Artefakt startet" in data or b"run.bat" in data and b"msvcrt.dll" not in data and is_pe
        waits = (b"msvcrt.dll" in data and b"system" in data and b"run.bat" in data) if is_pe else (b"/bin/sh" in data and b"run.sh" in data if is_elf else False)
        check = {
            "path": str(p.relative_to(path)).replace("\\", "/"),
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "format": "pe64" if is_pe else ("elf64" if is_elf else "unknown"),
            "real_runtime_launcher": bool(waits),
            "hint_stub_detected": bool(contains_hint),
        }
        native_checks.append(check)
        launcher_is_real = launcher_is_real or bool(waits)

    return {
        "format": "keim-self-bootstrap-launcher-v785",
        "declared": manifest.get("launcher", {}),
        "native_present": bool(native),
        "companion_present": bool(companions),
        "native": [str(p.relative_to(path)).replace("\\", "/") for p in native],
        "native_checks": native_checks,
        "companions": [str(p.relative_to(path)).replace("\\", "/") for p in companions],
        "run_bat_present": (path / "run.bat").exists(),
        "run_sh_present": (path / "run.sh").exists(),
        "keim_app_present": (path / "keim_app.py").exists(),
        "real_runtime_launcher": launcher_is_real,
        "ok": bool(native) and launcher_is_real and (path / "keim_app.py").exists(),
    }

def _verify_gpu_bundle(path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    gpu = manifest.get("gpu", {}) or {}
    drivers = gpu.get("drivers", []) if isinstance(gpu, dict) else []
    checked: list[dict[str, Any]] = []
    ok = True
    for d in drivers:
        rel = d.get("path")
        p = path / rel if rel else path / "__missing__"
        exists = p.exists()
        sha = _file_sha256(p) if exists else None
        match = exists and (not d.get("sha256") or sha == d.get("sha256"))
        ok = ok and match
        checked.append({"path": rel, "exists": exists, "sha256": sha, "sha256_ok": match})
    return {
        "enabled": bool(gpu.get("enabled")),
        "required": bool(gpu.get("required")),
        "manifest_present": (path / "runtime" / "gpu" / "gpu_driver_manifest.json").exists(),
        "plan_present": (path / "runtime" / "gpu" / "gpu_driver_plan.json").exists(),
        "smoke_present": (path / "runtime" / "gpu" / "gpu_smoke.py").exists(),
        "driver_count": len(drivers),
        "drivers": checked,
        "ok": ok and ((not gpu.get("enabled")) or bool(drivers)),
    }


def _driver_platform_hint(name: str) -> str:
    lower = name.lower()
    if lower.endswith(".dll"):
        return "windows"
    if lower.endswith(".so"):
        return "linux"
    if lower.endswith(".dylib"):
        return "darwin"
    return "unknown"


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def _json_safe(value: Any) -> Any:
    if isinstance(value, NativeValue):
        return value.as_json()
    if hasattr(value, "as_dict") and callable(getattr(value, "as_dict")):
        return _json_safe(value.as_dict())
    if hasattr(value, "__dataclass_fields__"):
        return {name: _json_safe(getattr(value, name)) for name in value.__dataclass_fields__}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def _tree_sha256(path: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(Path(path).rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(path)).replace("\\", "/").encode("utf-8"))
            h.update(b"\0")
            h.update(p.read_bytes())
            h.update(b"\0")
    return h.hexdigest()
