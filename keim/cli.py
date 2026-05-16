from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter
from typing import Sequence

from . import __version__
from .training_impossible import run_training_demo, launch_training_gui
from .web_ecosystem import (
    init_web_project,
    build_web_app,
    create_adapter,
    serve_web,
    web_status,
    WebEcosystemError,
)
from .analyzer import analyze_program
from .bytecode import compile_bytecode
from .compiler import compile_kernel_abi, compile_kernel_plan, compile_plan
from .contracts import run_contracts_from_file
from .errors import KeimError
from .exporter import write_standalone_runner
from .gpu_validation import validate_gpu_mapping
from .observe import observe_program
from .optimizer import analyze_optimization
from .parser import parse_file, parse_source
from .preprocessor import expand_macros
from .source_loader import load_source_file, load_raw_with_imports
from .project import build_project, new_project
from .runtime import RunOptions, run_program
from .sweep import run_sweep
from .trace import compare_final, read_trace, sha256_text, trace_final, trace_header, write_trace
from .backends.driver import DriverLoadError, DriverProbe
from .gpu_driver_execution import (
    inspect_driver as gpu76_inspect_driver,
    run_driver_demo as gpu76_run_driver_demo,
    build_execution_plan as gpu76_build_execution_plan,
    status_payload as gpu76_status_payload,
    default_driver_path as gpu76_default_driver_path,
)
from .internal_linker import link_kbc_file as internal_link_kbc_file, link_stdout_executable as internal_link_stdout_executable, status_payload as internal_linker_status
from .package_manager import KeimPackageManager
from .webui import start_web_gui
from .sandbox import SandboxPolicy
from .debugbus import DebugBus, start_debug_server
from .foundation import ModuleGraph, analyze_graph, lint_graph, core_bytecode, core_run, core_test, export_independent_bundle, build_lock, FoundationError, format_path, replay_file
from .enterprise import enterprise_analyze_graph, enterprise_lint, enterprise_format_path, enterprise_build, enterprise_test, enterprise_replay, emit_native_seed, emit_wasm_seed, enterprise_status_matrix, TestRunOptions
from .compiler64 import check64, build64, run64, test64, format64_source, lint64, emit_native_vm64, emit_wasm64, load_program64, status64, TestRunOptions64, parse_keim_expr, expr_to_dict
from .compiler65 import check65, run65, bytecode65, build65, test65, write_kbc65b, run_kbc65b, emit_native_keimvm65, load_program65, status65
from .compiler66 import check66, run66, bytecode66, build66, test66, write_kbc66b, run_kbc66b, emit_native_keimvm66, read_kbc66b, create_lock66, validate_replay66, status66
from .compiler67 import check67, run67, bytecode67, build67, test67, run_kbc67b, read_kbc67b, write_kbc67b, emit_wasm67, status67, create_lock67, registry_init67, registry_publish67, registry_resolve67, registry_install67, serve_registry67, start_registry_server67, validate_replay67, emit_time_travel_debugger67
from .compiler68 import check68, run68, bytecode68, build68, test68, run_kbc68b, read_kbc68b, write_kbc68b, emit_wasm68, status68
from .compiler69 import check69, run69, bytecode69, build69, test69, run_kbc69b, read_kbc69b, write_kbc69b, emit_wasm69, status69
from .compiler70 import check70, run70, bytecode70, build70, test70, run_kbc70b, read_kbc70b, write_kbc70b, emit_wasm70, status70
from .compiler71 import check71, run71, bytecode71, build71, test71, run_kbc71b, read_kbc71b, write_kbc71b, emit_wasm71, status71
from .compiler74 import status74, stable_spec, build74, check74, build_stable_payload, write_kbc_stable, read_kbc_stable, verify_stable, security_scan, create_sbom, parity_matrix, benchmark74, compatibility_matrix, write_lsp_bundle, run_lsp_stdio, emit_enterprise_whitepaper
from .compiler75 import status75, run_differential_matrix, run_browser_wasm_suite, compatibility75, hardening_build75, whitepaper75
from .exe_packager import status78, package_full_exe, verify_package, run_package


BACKENDS = ["cpu", "vm", "fused", "circuit", "segmented", "native", "gpu", "hybrid", "auto"]
PURE_BACKENDS = ["cpu", "vm", "fused", "circuit", "segmented"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="keim", description="Keim Genesis Prototype")
    parser.add_argument("--version", action="version", version=f"keim {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="Keim-Programm ausführen")
    run.add_argument("file", type=Path)
    run.add_argument("--rounds", type=int, default=60)
    run.add_argument("--show-every", type=int, default=10)
    run.add_argument("--seed", type=int, default=7)
    run.add_argument("--backend", choices=BACKENDS, default="cpu")
    run.add_argument("--dll", type=Path, default=None)
    run.add_argument("--gpu-index", type=int, default=0)
    run.add_argument("--driver-smoke", action="store_true")
    run.add_argument("--stats-out", type=Path, default=None)
    run.add_argument("--trace-out", type=Path, default=None)
    run.add_argument("--snapshot-out", type=Path, default=None)
    run.add_argument("--quiet", action="store_true")
    run.add_argument("--no-analyze", action="store_true")
    run.add_argument("--sandbox", choices=["permissive", "strict"], default="permissive")
    run.add_argument("--allow", action="append", default=[])

    explain = sub.add_parser("explain", help="AST und Ausführungsplan anzeigen")
    explain.add_argument("file", type=Path)
    explain.add_argument("--json", action="store_true", dest="as_json")
    explain.add_argument("--bytecode", action="store_true")

    analyze = sub.add_parser("analyze", help="statische Diagnose ohne Ausführung")
    analyze.add_argument("file", type=Path)
    analyze.add_argument("--json", action="store_true", dest="as_json")

    bytecode = sub.add_parser("bytecode", help="Keim-Programm in IR/Bytecode anzeigen")
    bytecode.add_argument("file", type=Path)
    bytecode.add_argument("--json", action="store_true", dest="as_json")

    kernel = sub.add_parser("kernel-plan", help="GPU-/Treiber-Mappingplan anzeigen")
    kernel.add_argument("file", type=Path)
    kernel.add_argument("--json", action="store_true", dest="as_json")

    abi = sub.add_parser("kernel-abi", help="v1.1 Kernel-ABI-Kontrakt erzeugen")
    abi.add_argument("file", type=Path)
    abi.add_argument("--out", type=Path, default=None)
    abi.add_argument("--json", action="store_true", dest="as_json")

    optimize = sub.add_parser("optimize", help="v2.6-Optimierungs-/Bundleplan anzeigen")
    optimize.add_argument("file", type=Path)
    optimize.add_argument("--json", action="store_true", dest="as_json")

    verify = sub.add_parser("verify", help="Backends cpu/vm/fused/circuit/segmented vergleichen")
    verify.add_argument("file", type=Path)
    verify.add_argument("--rounds", type=int, default=60)
    verify.add_argument("--seed", type=int, default=7)
    verify.add_argument("--json", action="store_true", dest="as_json")

    test = sub.add_parser("test", help="erwarte-Kontrakte ausführen")
    test.add_argument("file", type=Path)
    test.add_argument("--rounds", type=int, default=30)
    test.add_argument("--seed", type=int, default=7)
    test.add_argument("--backend", choices=PURE_BACKENDS, default="segmented")
    test.add_argument("--json", action="store_true", dest="as_json")
    test.add_argument("--out", type=Path, default=None)

    profile = sub.add_parser("profile", help="Backends gegeneinander messen")
    profile.add_argument("file", type=Path)
    profile.add_argument("--rounds", type=int, default=80)
    profile.add_argument("--seed", type=int, default=7)
    profile.add_argument("--json", action="store_true", dest="as_json")

    expand = sub.add_parser("expand", help="Bausteine/Werte/Imports expandieren")
    expand.add_argument("file", type=Path)
    expand.add_argument("--json", action="store_true", dest="as_json")

    symbols = sub.add_parser("symbols", help="v1.3/v1.4 Werte, Bausteine und Imports anzeigen")
    symbols.add_argument("file", type=Path)
    symbols.add_argument("--json", action="store_true", dest="as_json")

    gpu_validate = sub.add_parser("gpu-validate", help="GPU-Scatter-/ABI-Plan validieren")
    gpu_validate.add_argument("file", type=Path)
    gpu_validate.add_argument("--dll", type=Path, default=None)
    gpu_validate.add_argument("--gpu-index", type=int, default=0)
    gpu_validate.add_argument("--smoke", action="store_true")
    gpu_validate.add_argument("--json", action="store_true", dest="as_json")

    observe = sub.add_parser("observe", help="Beobachtungsdashboard")
    observe.add_argument("file", type=Path)
    observe.add_argument("--rounds", type=int, default=80)
    observe.add_argument("--seed", type=int, default=7)
    observe.add_argument("--backend", choices=PURE_BACKENDS, default="segmented")
    observe.add_argument("--every", type=int, default=10)
    observe.add_argument("--json", action="store_true", dest="as_json")
    observe.add_argument("--out", type=Path, default=None)

    sweep = sub.add_parser("sweep", help="Parameter-Sweep ausführen")
    sweep.add_argument("file", type=Path)
    sweep.add_argument("--rounds", type=int, default=30)
    sweep.add_argument("--seed", type=int, default=7)
    sweep.add_argument("--backend", choices=PURE_BACKENDS, default="segmented")
    sweep.add_argument("--vary", action="append", default=[], help="z.B. field:hunger=0.1,0.2 oder trail:futter.diffuse=0.12,0.18")
    sweep.add_argument("--limit", type=int, default=64)
    sweep.add_argument("--top", type=int, default=8)
    sweep.add_argument("--json", action="store_true", dest="as_json")
    sweep.add_argument("--out", type=Path, default=None)

    replay = sub.add_parser("replay", help="Trace deterministisch gegen Quelle erneut prüfen")
    replay.add_argument("file", type=Path)
    replay.add_argument("--trace", type=Path, required=True)
    replay.add_argument("--quiet", action="store_true")

    export = sub.add_parser("export", help="Keim-Datei als Python-Starter exportieren")
    export.add_argument("file", type=Path)
    export.add_argument("--out", type=Path, required=True)
    export.add_argument("--rounds", type=int, default=80)
    export.add_argument("--seed", type=int, default=7)

    build = sub.add_parser("build", help="v2.6 expandiertes Keim-Projekt mit Runner bauen")
    build.add_argument("file", type=Path)
    build.add_argument("--out", type=Path, required=True)
    build.add_argument("--name", default=None)
    build.add_argument("--rounds", type=int, default=80)
    build.add_argument("--json", action="store_true", dest="as_json")

    new = sub.add_parser("new", help="v2.6 neues Keim-Projekt anlegen")
    new.add_argument("dir", type=Path)
    new.add_argument("--name", default="mein_keim")

    bench = sub.add_parser("bench", help="kleinen Benchmark ausführen")
    bench.add_argument("--agents", type=int, default=2000)
    bench.add_argument("--width", type=int, default=100)
    bench.add_argument("--height", type=int, default=40)
    bench.add_argument("--rounds", type=int, default=100)
    bench.add_argument("--seed", type=int, default=7)
    bench.add_argument("--backend", choices=PURE_BACKENDS, default="segmented")
    bench.add_argument("--stats-out", type=Path, default=None)

    driver = sub.add_parser("driver-info", help="optionale CC_OpenCl.dll prüfen")
    driver.add_argument("--dll", type=Path, required=True)
    driver.add_argument("--gpu-index", type=int, default=0)
    driver.add_argument("--smoke", action="store_true")
    driver.add_argument("--json", action="store_true", dest="as_json")

    gpu_status = sub.add_parser("gpu-driver-status", help="v7.6 CC_OpenCl.dll Auto-Discovery und Kernel-ABI prüfen")
    gpu_status.add_argument("--dll", type=Path, default=None)
    gpu_status.add_argument("--json", action="store_true", dest="as_json")

    gpu_plan = sub.add_parser("gpu-driver-plan", help="v7.6 Keim-IR-zu-CC_OpenCl Kernel-Dispatchplan erzeugen")
    gpu_plan.add_argument("--dll", type=Path, default=None)
    gpu_plan.add_argument("--out", type=Path, default=None)
    gpu_plan.add_argument("--json", action="store_true", dest="as_json")

    gpu_demo = sub.add_parser("gpu-driver-demo", help="v7.6 GPU Driver Execution Demo/Profiling ausführen")
    gpu_demo.add_argument("--dll", type=Path, default=None)
    gpu_demo.add_argument("--out", type=Path, default=None)
    gpu_demo.add_argument("--size", type=int, default=256)
    gpu_demo.add_argument("--force-cpu", action="store_true")
    gpu_demo.add_argument("--json", action="store_true", dest="as_json")


    link_status = sub.add_parser("native-link-status", help="v7.7 interner Native-Linker ohne externen Compiler")
    link_status.add_argument("--json", action="store_true", dest="as_json")

    native_link = sub.add_parser("native-link", help="v7.7 Keim-Bytecode direkt zu PE/ELF linken, ohne g++/clang/link.exe")
    native_link.add_argument("file", type=Path)
    native_link.add_argument("--out", type=Path, required=True)
    native_link.add_argument("--target", choices=["auto", "elf64-linux-x86_64", "pe64-windows-x86_64", "linux", "windows"], default="auto")
    native_link.add_argument("--json", action="store_true", dest="as_json")

    native_link_demo = sub.add_parser("native-link-demo", help="v7.7 internes Linker-Demoartefakt erzeugen")
    native_link_demo.add_argument("--out", type=Path, required=True)
    native_link_demo.add_argument("--text", default="42\\n")
    native_link_demo.add_argument("--target", choices=["auto", "elf64-linux-x86_64", "pe64-windows-x86_64", "linux", "windows"], default="auto")
    native_link_demo.add_argument("--json", action="store_true", dest="as_json")

    repl = sub.add_parser("repl", help="interaktive Keim-REPL starten")

    doctor = sub.add_parser("doctor", help="Umgebung, CLI und Native-Pfade prüfen")

    routes = sub.add_parser("routes", help="HTTP-Routen eines Keim-Programms anzeigen")
    routes.add_argument("file", type=Path)
    routes.add_argument("--json", action="store_true", dest="as_json")

    serve = sub.add_parser("serve", help="Keim-Programm mit HTTP-Diensten dauerhaft starten")
    serve.add_argument("file", type=Path)
    serve.add_argument("--rounds", type=int, default=0, help="0 = dauerhaft")
    serve.add_argument("--seed", type=int, default=7)
    serve.add_argument("--show-every", type=int, default=0)
    serve.add_argument("--sandbox", choices=["permissive", "strict"], default="permissive")
    serve.add_argument("--allow", action="append", default=[])

    gui = sub.add_parser("gui", help="lokale Web-GUI für eine laufende Keim-API starten")
    gui.add_argument("--port", type=int, default=18081)
    gui.add_argument("--api", default="http://127.0.0.1:18080")
    gui.add_argument("--title", default="Keim Genesis GUI")
    gui.add_argument("--debug", default=None)

    pkg = sub.add_parser("get", help="Keim-Paket aus Ordner oder ZIP lokal installieren")
    pkg.add_argument("source", type=str)
    pkg.add_argument("--name", default=None)

    pkg_list = sub.add_parser("packages", help="installierte lokale Keim-Pakete anzeigen")

    init = sub.add_parser("init", help="keim.json im aktuellen Ordner anlegen")
    init.add_argument("--name", default="mein_keim_projekt")

    export_bin = sub.add_parser("export-bin", help="standalone Python-Starter als exe-fähigen Ordner erzeugen")
    export_bin.add_argument("file", type=Path)
    export_bin.add_argument("--out", type=Path, required=True)
    export_bin.add_argument("--rounds", type=int, default=60)
    export_bin.add_argument("--asset", action="append", default=[])


    export_py = sub.add_parser("export-py", help="Single-File-Python-Bundle mit eingebettetem Bytecode erzeugen")
    export_py.add_argument("file", type=Path)
    export_py.add_argument("--out", type=Path, required=True)
    export_py.add_argument("--rounds", type=int, default=60)

    debug = sub.add_parser("debug", help="Keim-Programm mit DebugBus-HTTP-Protokoll starten")
    debug.add_argument("file", type=Path)
    debug.add_argument("--port", type=int, default=18082)
    debug.add_argument("--rounds", type=int, default=60)
    debug.add_argument("--seed", type=int, default=7)
    debug.add_argument("--sandbox", choices=["permissive", "strict"], default="permissive")
    debug.add_argument("--allow", action="append", default=[])


    core_check = sub.add_parser("check", help="v5.1/v6 Foundation-Sprachkern statisch prüfen")
    core_check.add_argument("file", type=Path, nargs="?")
    core_check.add_argument("--json", action="store_true", dest="as_json")

    core_run_cmd = sub.add_parser("core-run", help="v6 Independent-Core Programm ausführen")
    core_run_cmd.add_argument("file", type=Path)
    core_run_cmd.add_argument("--record", type=Path, default=None)

    core_bc = sub.add_parser("core-bytecode", help="v6 Independent Bytecode erzeugen")
    core_bc.add_argument("file", type=Path)
    core_bc.add_argument("--out", type=Path, default=None)
    core_bc.add_argument("--json", action="store_true", dest="as_json")

    core_tests = sub.add_parser("core-test", help="v6 Independent-Core Tests ausführen")
    core_tests.add_argument("file", type=Path)
    core_tests.add_argument("--json", action="store_true", dest="as_json")

    core_export = sub.add_parser("core-export", help="v6 Independent-Core Bundle erzeugen")
    core_export.add_argument("file", type=Path)
    core_export.add_argument("--out", type=Path, required=True)

    lock_cmd = sub.add_parser("lock", help="keim.lock aus keim.toml erzeugen")
    lock_cmd.add_argument("--cwd", type=Path, default=Path("."))

    lint_cmd = sub.add_parser("lint", help="v6.2 Linter für Foundation-Core")
    lint_cmd.add_argument("file", type=Path)
    lint_cmd.add_argument("--json", action="store_true", dest="as_json")

    fmt_cmd = sub.add_parser("fmt", help="v6.2 Formatter für .keim-Dateien")
    fmt_cmd.add_argument("path", type=Path)
    fmt_cmd.add_argument("--write", action="store_true")

    core_replay = sub.add_parser("core-replay", help="v6.2 Replay-/Snapshot-Events lesen")
    core_replay.add_argument("file", type=Path)
    core_replay.add_argument("--json", action="store_true", dest="as_json")

    echeck = sub.add_parser("enterprise-check", help="v6.3 Enterprise-Analyse: Module, Typen, Bytecode-Verifier")
    echeck.add_argument("file", type=Path)
    echeck.add_argument("--json", action="store_true", dest="as_json")

    ebuild = sub.add_parser("enterprise-build", help="v6.3 Projekt-Build mit keim-lock-v3 und Manifest")
    ebuild.add_argument("--cwd", type=Path, default=Path("."))
    ebuild.add_argument("--out", type=Path, required=True)
    ebuild.add_argument("--profile", default="debug")

    etest = sub.add_parser("enterprise-test", help="v6.3 Test Discovery, Filter, JSON/JUnit/Coverage")
    etest.add_argument("path", type=Path)
    etest.add_argument("--filter", default=None)
    etest.add_argument("--json", action="store_true", dest="as_json")
    etest.add_argument("--json-out", type=Path, default=None)
    etest.add_argument("--junit-out", type=Path, default=None)
    etest.add_argument("--coverage", action="store_true")

    efmt = sub.add_parser("enterprise-fmt", help="v6.3 stabilerer Formatter mit Import-/Export-Sortierung")
    efmt.add_argument("path", type=Path)
    efmt.add_argument("--write", action="store_true")

    elint = sub.add_parser("enterprise-lint", help="v6.3 Linter mit Typ-, Scope- und Moduldiagnostik")
    elint.add_argument("file", type=Path)
    elint.add_argument("--json", action="store_true", dest="as_json")

    ereplay = sub.add_parser("enterprise-replay", help="v6.3 Replay/Snapshot validieren")
    ereplay.add_argument("file", type=Path)
    ereplay.add_argument("--strict", action="store_true")
    ereplay.add_argument("--json", action="store_true", dest="as_json")

    enative = sub.add_parser("enterprise-native", help="v6.3 Native C++ Seed aus validiertem Bytecode erzeugen")
    enative.add_argument("bytecode", type=Path)
    enative.add_argument("--out", type=Path, required=True)

    ewasm = sub.add_parser("enterprise-wasm", help="v6.3 WASM WAT Seed aus validiertem Bytecode erzeugen")
    ewasm.add_argument("bytecode", type=Path)
    ewasm.add_argument("--out", type=Path, required=True)

    estatus = sub.add_parser("enterprise-status", help="v6.3 Statusmatrix der zehn Enterprise-Bausteine")
    estatus.add_argument("--json", action="store_true", dest="as_json")


    v64_status = sub.add_parser("v64-status", help="v6.4 Professional Core Status anzeigen")
    v64_status.add_argument("--json", action="store_true", dest="as_json")

    v64_expr = sub.add_parser("v64-expr", help="v6.4 Keim-Ausdruck mit eigenem Parser analysieren")
    v64_expr.add_argument("expr")
    v64_expr.add_argument("--json", action="store_true", dest="as_json")

    v64_check = sub.add_parser("v64-check", help="v6.4 linearen Compiler/Typechecker prüfen")
    v64_check.add_argument("file", type=Path)
    v64_check.add_argument("--json", action="store_true", dest="as_json")

    v64_bc = sub.add_parser("v64-bytecode", help="v6.4 linearen Bytecode erzeugen")
    v64_bc.add_argument("file", type=Path)
    v64_bc.add_argument("--out", type=Path, default=None)
    v64_bc.add_argument("--json", action="store_true", dest="as_json")

    v64_run = sub.add_parser("v64-run", help="v6.4 VM64 ausführen")
    v64_run.add_argument("file", type=Path)
    v64_run.add_argument("--record", type=Path, default=None)

    v64_build = sub.add_parser("v64-build", help="v6.4 Projekt bauen")
    v64_build.add_argument("--cwd", type=Path, default=Path("."))
    v64_build.add_argument("--out", type=Path, required=True)

    v64_test = sub.add_parser("v64-test", help="v6.4 Tests mit VM64 ausführen")
    v64_test.add_argument("file", type=Path)
    v64_test.add_argument("--filter", default=None)
    v64_test.add_argument("--coverage", action="store_true")
    v64_test.add_argument("--junit", type=Path, default=None)
    v64_test.add_argument("--json", action="store_true", dest="as_json")

    v64_lint = sub.add_parser("v64-lint", help="v6.4 Linter")
    v64_lint.add_argument("file", type=Path)
    v64_lint.add_argument("--json", action="store_true", dest="as_json")

    v64_fmt = sub.add_parser("v64-fmt", help="v6.4 Formatter")
    v64_fmt.add_argument("file", type=Path)
    v64_fmt.add_argument("--write", action="store_true")

    v64_native = sub.add_parser("v64-native", help="v6.4 native VM Seed aus kbc64 erzeugen")
    v64_native.add_argument("bytecode", type=Path)
    v64_native.add_argument("--out", type=Path, required=True)

    v64_wasm = sub.add_parser("v64-wasm", help="v6.4 WASM Seed aus kbc64 erzeugen")
    v64_wasm.add_argument("bytecode", type=Path)
    v64_wasm.add_argument("--out", type=Path, required=True)

    v65_status = sub.add_parser("v65-status", help="v6.5 Native/Generics/Result/Match/Binary Status")
    v65_status.add_argument("--json", action="store_true", dest="as_json")

    v65_check = sub.add_parser("v65-check", help="v6.5 Typechecker inklusive Generics/Result/Match")
    v65_check.add_argument("file", type=Path)
    v65_check.add_argument("--json", action="store_true", dest="as_json")

    v65_bc = sub.add_parser("v65-bytecode", help="v6.5 Bytecode JSON/Binary erzeugen")
    v65_bc.add_argument("file", type=Path)
    v65_bc.add_argument("--out", type=Path, default=None)
    v65_bc.add_argument("--binary-out", type=Path, default=None)
    v65_bc.add_argument("--json", action="store_true", dest="as_json")

    v65_run = sub.add_parser("v65-run", help="v6.5 Python VM65 aus Source ausführen")
    v65_run.add_argument("file", type=Path)
    v65_run.add_argument("--record", type=Path, default=None)

    v65_run_bin = sub.add_parser("v65-run-bin", help="v6.5 .kbc65b ausführen")
    v65_run_bin.add_argument("file", type=Path)

    v65_build = sub.add_parser("v65-build", help="v6.5 Projekt mit JSON und Binary Bytecode bauen")
    v65_build.add_argument("--cwd", type=Path, default=Path("."))
    v65_build.add_argument("--out", type=Path, required=True)

    v65_test = sub.add_parser("v65-test", help="v6.5 Tests ausführen")
    v65_test.add_argument("file", type=Path)
    v65_test.add_argument("--junit", type=Path, default=None)
    v65_test.add_argument("--json", action="store_true", dest="as_json")

    v65_native = sub.add_parser("v65-native", help="v6.5 native C++ keimvm MVP aus Bytecode erzeugen")
    v65_native.add_argument("bytecode", type=Path)
    v65_native.add_argument("--out", type=Path, required=True)

    v66_status = sub.add_parser("v66-status", help="v6.6 Enterprise Runtime Completion Status")
    v66_status.add_argument("--json", action="store_true", dest="as_json")

    v66_check = sub.add_parser("v66-check", help="v6.6 Check mit Constant Pool/Loops/Binary-Verifier")
    v66_check.add_argument("file", type=Path)
    v66_check.add_argument("--json", action="store_true", dest="as_json")

    v66_bc = sub.add_parser("v66-bytecode", help="v6.6 Bytecode JSON/Binary mit Sektionen erzeugen")
    v66_bc.add_argument("file", type=Path)
    v66_bc.add_argument("--out", type=Path, default=None)
    v66_bc.add_argument("--binary-out", type=Path, default=None)
    v66_bc.add_argument("--json", action="store_true", dest="as_json")

    v66_run = sub.add_parser("v66-run", help="v6.6 Python VM66 aus Source ausführen")
    v66_run.add_argument("file", type=Path)
    v66_run.add_argument("--record", type=Path, default=None)

    v66_run_bin = sub.add_parser("v66-run-bin", help="v6.6 .kbc66b ausführen")
    v66_run_bin.add_argument("file", type=Path)

    v66_build = sub.add_parser("v66-build", help="v6.6 Projekt mit kbc66 JSON/Binary/Lock bauen")
    v66_build.add_argument("--cwd", type=Path, default=Path("."))
    v66_build.add_argument("--out", type=Path, required=True)

    v66_test = sub.add_parser("v66-test", help="v6.6 Tests ausführen")
    v66_test.add_argument("file", type=Path)
    v66_test.add_argument("--filter", default=None)
    v66_test.add_argument("--junit", type=Path, default=None)
    v66_test.add_argument("--json", action="store_true", dest="as_json")

    v66_native = sub.add_parser("v66-native", help="v6.6 native C++ VM aus kbc66 JSON/Binary erzeugen")
    v66_native.add_argument("bytecode", type=Path)
    v66_native.add_argument("--out", type=Path, required=True)

    v66_lock = sub.add_parser("v66-lock", help="v6.6 keim-lock-v5 erzeugen")
    v66_lock.add_argument("--cwd", type=Path, default=Path("."))
    v66_lock.add_argument("--out", type=Path, default=None)

    v66_replay = sub.add_parser("v66-replay", help="v6.6 deterministisches Replay-Eventlog validieren")
    v66_replay.add_argument("file", type=Path)
    v66_replay.add_argument("--json", action="store_true", dest="as_json")
    v67_status = sub.add_parser("v67-status", help="v6.7 Enterprise Complete Status")
    v67_status.add_argument("--json", action="store_true", dest="as_json")

    v67_check = sub.add_parser("v67-check", help="v6.7 Check mit Monomorphisierung/Registry/WASM/Replay")
    v67_check.add_argument("file", type=Path)
    v67_check.add_argument("--json", action="store_true", dest="as_json")

    v67_bc = sub.add_parser("v67-bytecode", help="v6.7 Bytecode JSON/Binary erzeugen")
    v67_bc.add_argument("file", type=Path)
    v67_bc.add_argument("--out", type=Path, default=None)
    v67_bc.add_argument("--binary-out", type=Path, default=None)
    v67_bc.add_argument("--json", action="store_true", dest="as_json")

    v67_run = sub.add_parser("v67-run", help="v6.7 VM aus Source ausführen")
    v67_run.add_argument("file", type=Path)
    v67_run.add_argument("--record", type=Path, default=None)

    v67_run_bin = sub.add_parser("v67-run-bin", help="v6.7 .kbc67b ausführen")
    v67_run_bin.add_argument("file", type=Path)

    v67_build = sub.add_parser("v67-build", help="v6.7 Projekt mit Registry/WASM/Debugger bauen")
    v67_build.add_argument("--cwd", type=Path, default=Path("."))
    v67_build.add_argument("--out", type=Path, required=True)

    v67_test = sub.add_parser("v67-test", help="v6.7 Tests ausführen")
    v67_test.add_argument("file", type=Path)
    v67_test.add_argument("--filter", default=None)
    v67_test.add_argument("--junit", type=Path, default=None)
    v67_test.add_argument("--json", action="store_true", dest="as_json")

    v67_wasm = sub.add_parser("v67-wasm", help="v6.7 WAT/WASM-Text aus kbc67 JSON/Binary erzeugen")
    v67_wasm.add_argument("bytecode", type=Path)
    v67_wasm.add_argument("--out", type=Path, required=True)

    v67_lock = sub.add_parser("v67-lock", help="v6.7 keim-lock-v6 erzeugen")
    v67_lock.add_argument("--cwd", type=Path, default=Path("."))
    v67_lock.add_argument("--out", type=Path, default=None)
    v67_lock.add_argument("--registry", type=Path, default=None)

    v67_registry = sub.add_parser("v67-registry", help="v6.7 lokale Paketregistry")
    v67_registry.add_argument("action", choices=["init", "publish", "resolve", "install", "serve"])
    v67_registry.add_argument("--registry", type=Path, default=Path(".keim/registry"))
    v67_registry.add_argument("--cwd", type=Path, default=Path("."))
    v67_registry.add_argument("--name", default=None)
    v67_registry.add_argument("--version", default=None)
    v67_registry.add_argument("--requirement", default="*")
    v67_registry.add_argument("--cache", type=Path, default=None)
    v67_registry.add_argument("--host", default="127.0.0.1")
    v67_registry.add_argument("--port", type=int, default=8767)
    v67_registry.add_argument("--json", action="store_true", dest="as_json")

    v67_replay = sub.add_parser("v67-replay", help="v6.7 Replay validieren und HTML-Time-Travel-Debugger erzeugen")
    v67_replay.add_argument("file", type=Path)
    v67_replay.add_argument("--html-out", type=Path, default=None)
    v67_replay.add_argument("--json", action="store_true", dest="as_json")

    v68_status = sub.add_parser("v68-status", help="v6.8 WASM Heap Runtime Status")
    v68_status.add_argument("--json", action="store_true", dest="as_json")

    v68_check = sub.add_parser("v68-check", help="v6.8 Check mit WASM-Heap-Layouts")
    v68_check.add_argument("file", type=Path)
    v68_check.add_argument("--json", action="store_true", dest="as_json")

    v68_bc = sub.add_parser("v68-bytecode", help="v6.8 Bytecode JSON/Binary mit HEAP/WASMRT-Sektionen erzeugen")
    v68_bc.add_argument("file", type=Path)
    v68_bc.add_argument("--out", type=Path, default=None)
    v68_bc.add_argument("--binary-out", type=Path, default=None)
    v68_bc.add_argument("--json", action="store_true", dest="as_json")

    v68_run = sub.add_parser("v68-run", help="v6.8 VM aus Source ausführen")
    v68_run.add_argument("file", type=Path)
    v68_run.add_argument("--record", type=Path, default=None)

    v68_run_bin = sub.add_parser("v68-run-bin", help="v6.8 .kbc68b ausführen")
    v68_run_bin.add_argument("file", type=Path)

    v68_build = sub.add_parser("v68-build", help="v6.8 Projekt mit WASM-Heap-Runtime bauen")
    v68_build.add_argument("--cwd", type=Path, default=Path("."))
    v68_build.add_argument("--out", type=Path, required=True)

    v68_test = sub.add_parser("v68-test", help="v6.8 Tests inkl. WASM-Heap-Lowering")
    v68_test.add_argument("file", type=Path)
    v68_test.add_argument("--filter", default=None)
    v68_test.add_argument("--junit", type=Path, default=None)
    v68_test.add_argument("--json", action="store_true", dest="as_json")

    v68_wasm = sub.add_parser("v68-wasm", help="v6.8 WAT mit Tagged-Value-Heap-Runtime erzeugen")
    v68_wasm.add_argument("bytecode", type=Path)
    v68_wasm.add_argument("--out", type=Path, required=True)

    v69_status = sub.add_parser("v69-status", help="v6.9 professioneller WASM GC/Hashmap Runtime Status")
    v69_status.add_argument("--json", action="store_true", dest="as_json")

    v69_check = sub.add_parser("v69-check", help="v6.9 Check mit GC-/Hashmap-Heap-Layouts")
    v69_check.add_argument("file", type=Path)
    v69_check.add_argument("--json", action="store_true", dest="as_json")

    v69_bc = sub.add_parser("v69-bytecode", help="v6.9 Bytecode JSON/Binary mit GC/HASHMAP-Sektionen erzeugen")
    v69_bc.add_argument("file", type=Path)
    v69_bc.add_argument("--out", type=Path, default=None)
    v69_bc.add_argument("--binary-out", type=Path, default=None)
    v69_bc.add_argument("--json", action="store_true", dest="as_json")

    v69_run = sub.add_parser("v69-run", help="v6.9 VM aus Source ausführen")
    v69_run.add_argument("file", type=Path)
    v69_run.add_argument("--record", type=Path, default=None)

    v69_run_bin = sub.add_parser("v69-run-bin", help="v6.9 .kbc69b ausführen")
    v69_run_bin.add_argument("file", type=Path)

    v69_build = sub.add_parser("v69-build", help="v6.9 Projekt mit GC/Hashmap WASM-Runtime bauen")
    v69_build.add_argument("--cwd", type=Path, default=Path("."))
    v69_build.add_argument("--out", type=Path, required=True)

    v69_test = sub.add_parser("v69-test", help="v6.9 Tests inkl. GC/Hashmap WASM-Lowering")
    v69_test.add_argument("file", type=Path)
    v69_test.add_argument("--filter", default=None)
    v69_test.add_argument("--junit", type=Path, default=None)
    v69_test.add_argument("--json", action="store_true", dest="as_json")

    v69_wasm = sub.add_parser("v69-wasm", help="v6.9 WAT mit Mark/Sweep-GC und Open-Addressing-Hashmap erzeugen")
    v69_wasm.add_argument("bytecode", type=Path)
    v69_wasm.add_argument("--out", type=Path, required=True)

    v70_status = sub.add_parser("v70-status", help="v7.0 generationsbasierter WASM GC Runtime Status")
    v70_status.add_argument("--json", action="store_true", dest="as_json")

    v70_check = sub.add_parser("v70-check", help="v7.0 Check mit Generational-GC-Layouts")
    v70_check.add_argument("file", type=Path)
    v70_check.add_argument("--json", action="store_true", dest="as_json")

    v70_bc = sub.add_parser("v70-bytecode", help="v7.0 Bytecode JSON/Binary mit GEN2GC-Sektionen erzeugen")
    v70_bc.add_argument("file", type=Path)
    v70_bc.add_argument("--out", type=Path, default=None)
    v70_bc.add_argument("--binary-out", type=Path, default=None)
    v70_bc.add_argument("--json", action="store_true", dest="as_json")

    v70_run = sub.add_parser("v70-run", help="v7.0 VM aus Source ausführen")
    v70_run.add_argument("file", type=Path)
    v70_run.add_argument("--record", type=Path, default=None)

    v70_run_bin = sub.add_parser("v70-run-bin", help="v7.0 .kbc70b ausführen")
    v70_run_bin.add_argument("file", type=Path)

    v70_build = sub.add_parser("v70-build", help="v7.0 Projekt mit generationsbasierter WASM-Runtime bauen")
    v70_build.add_argument("--cwd", type=Path, default=Path("."))
    v70_build.add_argument("--out", type=Path, required=True)

    v70_test = sub.add_parser("v70-test", help="v7.0 Tests inkl. Generational-GC WASM-Lowering")
    v70_test.add_argument("file", type=Path)
    v70_test.add_argument("--filter", default=None)
    v70_test.add_argument("--junit", type=Path, default=None)
    v70_test.add_argument("--json", action="store_true", dest="as_json")

    v70_wasm = sub.add_parser("v70-wasm", help="v7.0 WAT mit Generational-GC und Hashmap erzeugen")
    v70_wasm.add_argument("bytecode", type=Path)
    v70_wasm.add_argument("--out", type=Path, required=True)

    v71_status = sub.add_parser("v71-status", help="v7.1 kompaktierender GC + Region-Allocator Runtime Status")
    v71_status.add_argument("--json", action="store_true", dest="as_json")

    v71_check = sub.add_parser("v71-check", help="v7.1 Check mit Compacting-GC/Region-Layouts")
    v71_check.add_argument("file", type=Path)
    v71_check.add_argument("--json", action="store_true", dest="as_json")

    v71_bc = sub.add_parser("v71-bytecode", help="v7.1 Bytecode JSON/Binary mit COMPACT/REGION-Sektionen erzeugen")
    v71_bc.add_argument("file", type=Path)
    v71_bc.add_argument("--out", type=Path, default=None)
    v71_bc.add_argument("--binary-out", type=Path, default=None)
    v71_bc.add_argument("--json", action="store_true", dest="as_json")

    v71_run = sub.add_parser("v71-run", help="v7.1 VM aus Source ausführen")
    v71_run.add_argument("file", type=Path)
    v71_run.add_argument("--record", type=Path, default=None)

    v71_run_bin = sub.add_parser("v71-run-bin", help="v7.1 .kbc71b ausführen")
    v71_run_bin.add_argument("file", type=Path)

    v71_build = sub.add_parser("v71-build", help="v7.1 Projekt mit Compacting-GC/Region WASM-Runtime bauen")
    v71_build.add_argument("--cwd", type=Path, default=Path("."))
    v71_build.add_argument("--out", type=Path, required=True)

    v71_test = sub.add_parser("v71-test", help="v7.1 Tests inkl. Compacting-GC/Region WASM-Lowering")
    v71_test.add_argument("file", type=Path)
    v71_test.add_argument("--filter", default=None)
    v71_test.add_argument("--junit", type=Path, default=None)
    v71_test.add_argument("--json", action="store_true", dest="as_json")

    v71_wasm = sub.add_parser("v71-wasm", help="v7.1 WAT mit Compacting-GC und Region-Allocator erzeugen")
    v71_wasm.add_argument("bytecode", type=Path)
    v71_wasm.add_argument("--out", type=Path, required=True)

    training = sub.add_parser("training-impossible", help="v7.2 Schulungsprojekt: selbststeuernde Simulation mit Hintergrund-Bytecode-Optimizer")
    training.add_argument("--steps", type=int, default=80)
    training.add_argument("--out", type=Path, default=Path("build/training_impossible"))
    training.add_argument("--seed", type=int, default=7)
    training.add_argument("--json", action="store_true", dest="as_json")
    training.add_argument("--gui", action="store_true", help="Tk-GUI starten statt Headless-Schulungslauf")



    web_status_cmd = sub.add_parser("web-status", help="v7.8.5 Web-/Ökosystem-Fähigkeiten anzeigen")
    web_status_cmd.add_argument("--json", action="store_true", dest="as_json")

    web_new = sub.add_parser("web-new", help="v7.8.5 Keim Web-Projekt erzeugen")
    web_new.add_argument("out", type=Path)
    web_new.add_argument("--name", default="keim_web_training_app")

    web_build = sub.add_parser("web-build", help="v7.8.5 Keim Web-App bauen; übernimmt web/index.html wenn vorhanden")
    web_build.add_argument("--cwd", type=Path, default=Path("."))
    web_build.add_argument("--out", type=Path, required=True)
    web_build.add_argument("--dev", action="store_true")
    web_build.add_argument("--json", action="store_true", dest="as_json")

    web_check = sub.add_parser("web-check", help="v7.8.5 Keim Web-App validieren")
    web_check.add_argument("--cwd", type=Path, default=Path("."))
    web_check.add_argument("--out", type=Path, required=True)
    web_check.add_argument("--json", action="store_true", dest="as_json")

    web_adapter = sub.add_parser("web-adapter", help="v7.8.5 JS-Adapter-Spezifikation erzeugen")
    web_adapter.add_argument("--out", type=Path, required=True)
    web_adapter.add_argument("--alias", required=True)
    web_adapter.add_argument("--module", required=True)
    web_adapter.add_argument("--permission", action="append", default=[])

    web_serve = sub.add_parser("web-serve", help="v7.3 Web-Build lokal ausliefern")
    web_serve.add_argument("--out", type=Path, required=True)
    web_serve.add_argument("--port", type=int, default=8787)


    v75_status = sub.add_parser("v75-status", help="v7.5 Enterprise Hardening Status")
    v75_status.add_argument("--json", action="store_true", dest="as_json")

    v75_matrix = sub.add_parser("v75-matrix", help="v7.5 große Differentialtest-Matrix ausführen")
    v75_matrix.add_argument("--cwd", type=Path, default=Path("."))
    v75_matrix.add_argument("--out", type=Path, required=True)
    v75_matrix.add_argument("--max-cases", type=int, default=50)
    v75_matrix.add_argument("--synthetic-only", action="store_true")
    v75_matrix.add_argument("--json", action="store_true", dest="as_json")

    v75_wasm = sub.add_parser("v75-wasm-browser", help="v7.5 Browser-/Node-WASM-Runtime-Smoke-Harness erzeugen und Node ausführen")
    v75_wasm.add_argument("--out", type=Path, required=True)
    v75_wasm.add_argument("--json", action="store_true", dest="as_json")

    v75_compat = sub.add_parser("v75-compat", help="v7.5 Kompatibilitäts- und Regressionsmatrix erzeugen")
    v75_compat.add_argument("--cwd", type=Path, default=Path("."))
    v75_compat.add_argument("--out", type=Path, required=True)
    v75_compat.add_argument("--json", action="store_true", dest="as_json")

    v75_hardening = sub.add_parser("v75-hardening-build", help="v7.5 vollständiges Hardening-Artefaktbundle erzeugen")
    v75_hardening.add_argument("--cwd", type=Path, default=Path("."))
    v75_hardening.add_argument("--out", type=Path, required=True)
    v75_hardening.add_argument("--json", action="store_true", dest="as_json")

    v75_whitepaper = sub.add_parser("v75-whitepaper", help="v7.5 Hardening-Whitepaper schreiben")
    v75_whitepaper.add_argument("--out", type=Path, required=True)
    v75_whitepaper.add_argument("--json", action="store_true", dest="as_json")


    v74_status = sub.add_parser("v74-status", help="v7.4 Enterprise Stabilization Status")
    v74_status.add_argument("--json", action="store_true", dest="as_json")

    v74_spec = sub.add_parser("v74-spec", help="KBC-STABLE-1 Spezifikation ausgeben")
    v74_spec.add_argument("--out", type=Path, default=None)
    v74_spec.add_argument("--json", action="store_true", dest="as_json")

    v74_check = sub.add_parser("v74-check", help="v7.4 Stable/Security/Bytecode Check")
    v74_check.add_argument("file", type=Path)
    v74_check.add_argument("--json", action="store_true", dest="as_json")

    v74_build = sub.add_parser("v74-build", help="v7.4 Enterprise-Stable Build erzeugen")
    v74_build.add_argument("file", type=Path)
    v74_build.add_argument("--out", type=Path, required=True)
    v74_build.add_argument("--json", action="store_true", dest="as_json")

    v74_verify = sub.add_parser("v74-verify", help="KBC-STABLE-1 Binärdatei verifizieren")
    v74_verify.add_argument("file", type=Path)
    v74_verify.add_argument("--json", action="store_true", dest="as_json")

    v74_security = sub.add_parser("v74-security", help="Capability-/Supply-Chain-Security Scan")
    v74_security.add_argument("path", type=Path)
    v74_security.add_argument("--policy", type=Path, default=None)
    v74_security.add_argument("--json", action="store_true", dest="as_json")

    v74_sbom = sub.add_parser("v74-sbom", help="SBOM und reproduzierbares Buildmanifest erzeugen")
    v74_sbom.add_argument("--cwd", type=Path, default=Path("."))
    v74_sbom.add_argument("--out", type=Path, required=True)
    v74_sbom.add_argument("--json", action="store_true", dest="as_json")

    v74_parity = sub.add_parser("v74-parity", help="Python/Native/WASM Paritätsmanifest erzeugen")
    v74_parity.add_argument("file", type=Path)
    v74_parity.add_argument("--out", type=Path, required=True)
    v74_parity.add_argument("--json", action="store_true", dest="as_json")

    v74_bench = sub.add_parser("v74-benchmark", help="Benchmark-Harness für Keim-Compiler/VM")
    v74_bench.add_argument("file", type=Path)
    v74_bench.add_argument("--out", type=Path, required=True)
    v74_bench.add_argument("--iterations", type=int, default=5)
    v74_bench.add_argument("--json", action="store_true", dest="as_json")

    v74_compat = sub.add_parser("v74-compat", help="Kompatibilitätsmatrix für Beispiele/Versionen erzeugen")
    v74_compat.add_argument("--cwd", type=Path, default=Path("."))
    v74_compat.add_argument("--out", type=Path, required=True)
    v74_compat.add_argument("--json", action="store_true", dest="as_json")

    v74_lsp_bundle = sub.add_parser("v74-lsp-bundle", help="LSP/IDE-Artefakte erzeugen")
    v74_lsp_bundle.add_argument("--out", type=Path, required=True)
    v74_lsp_bundle.add_argument("--json", action="store_true", dest="as_json")

    sub.add_parser("v74-lsp", help="Keim JSON-lines LSP Core auf stdio starten")

    v74_whitepaper = sub.add_parser("v74-whitepaper", help="v7.4 Enterprise Whitepaper erzeugen")
    v74_whitepaper.add_argument("--out", type=Path, required=True)
    v74_whitepaper.add_argument("--json", action="store_true", dest="as_json")

    exe_status = sub.add_parser("exe-status", help="v7.8.5 Self-Bootstrapping Full EXE Runtime Packager Status")
    exe_status.add_argument("--json", action="store_true", dest="as_json")

    exe_pack = sub.add_parser("exe-pack", help="v7.8.5 vollständiges Keim-Programm als selbststartendes Runtime-/EXE-Bundle packen")
    exe_pack.add_argument("file", type=Path)
    exe_pack.add_argument("--out", type=Path, required=True)
    exe_pack.add_argument("--name", default="keim_app")
    exe_pack.add_argument("--target", choices=["auto", "pe64-windows-x86_64", "elf64-linux-x86_64", "windows", "linux"], default="auto")
    exe_pack.add_argument("--no-gpu", action="store_true")
    exe_pack.add_argument("--gpu-driver", type=Path, default=None)
    exe_pack.add_argument("--gpu-required", action="store_true")
    exe_pack.add_argument("--no-gpu-smoke", action="store_true")
    exe_pack.add_argument("--no-web", action="store_true")
    exe_pack.add_argument("--json", action="store_true", dest="as_json")

    exe_verify = sub.add_parser("exe-verify", help="v7.8.5 Keim-EXE-Bundle prüfen")
    exe_verify.add_argument("path", type=Path)
    exe_verify.add_argument("--json", action="store_true", dest="as_json")

    exe_run = sub.add_parser("exe-run", help="v7.8.5 Keim-EXE-Bundle über eingebettete Runtime starten")
    exe_run.add_argument("path", type=Path)
    exe_run.add_argument("--json", action="store_true", dest="as_json")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        match args.cmd:

            case "exe-status":
                payload = status78()
                if args.as_json:
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                else:
                    print("[Keim v7.8.5] Self-Bootstrapping GPU-aware Full EXE Runtime Packager")
                    print(f"  Externer Compiler nötig: {payload['external_compiler_required']}")
                    print("  Features: " + ", ".join(payload["features"]))
                return 0

            case "exe-pack":
                result = package_full_exe(
                    args.file,
                    args.out,
                    name=args.name,
                    target=args.target,
                    include_gpu=not args.no_gpu,
                    include_web=not args.no_web,
                    gpu_driver=args.gpu_driver,
                    gpu_required=args.gpu_required,
                    gpu_smoke=not args.no_gpu_smoke,
                )
                if args.as_json:
                    print(json.dumps(result.as_json(), ensure_ascii=False, indent=2))
                else:
                    print(f"[Keim v7.8.5] Self-Bootstrapping GPU-aware Full EXE Runtime Package erzeugt: {result.out}")
                    print(f"  Manifest: {result.manifest}")
                    print(f"  Zipapp:   {result.zipapp or '-'}")
                    print(f"  Native:   {result.native_launcher or '-'}")
                    print(f"  SHA256:   {result.sha256}")
                return 0

            case "exe-verify":
                payload = verify_package(args.path)
                if args.as_json:
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                else:
                    print("[Keim v7.8.5] EXE Package Verify " + ("OK" if payload.get("ok") else "FEHLER"))
                    print(f"  Dateien: {payload.get('file_count')}")
                    print(f"  SHA256: {payload.get('sha256')}")
                return 0 if payload.get("ok") else 1

            case "exe-run":
                payload = run_package(args.path)
                if args.as_json:
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                else:
                    print("[Keim v7.8.5] EXE Package Run " + ("OK" if payload.get("ok") else "FEHLER"))
                    if payload.get("output"):
                        for line in payload.get("output", []):
                            print(line)
                    elif "value" in payload:
                        print(payload.get("value"))
                    elif not payload.get("ok"):
                        print(payload.get("error"))
                return 0 if payload.get("ok") else 1

            case "run":
                loaded = load_source_file(args.file)
                source_text = loaded.source
                program = parse_source(source_text, source_name=str(args.file))
                if not args.no_analyze:
                    analysis = analyze_program(program)
                    if not analysis.ok:
                        print(analysis.format())
                        return 1
                report = run_program(program, RunOptions(rounds=args.rounds, show_every=args.show_every, seed=args.seed, quiet=args.quiet, backend=args.backend, dll=args.dll, gpu_index=args.gpu_index, driver_smoke=args.driver_smoke, sandbox=SandboxPolicy.from_cli(args.sandbox, args.allow)))
                if args.stats_out:
                    _write_json(args.stats_out, report.as_dict())
                if args.trace_out:
                    write_trace(args.trace_out, source_text=source_text, source_name=str(args.file), seed=args.seed, backend=report.backend, report=report.cpu)
                    print(f"[Keim] Trace geschrieben: {args.trace_out}")
                if args.snapshot_out:
                    from .backends.cpu import CpuBackend, CpuConfig
                    snap = CpuBackend(CpuConfig(seed=args.seed, show_every=0, quiet=True, collect_metrics=False))
                    snap.load(program)
                    for tick in range(1, args.rounds + 1):
                        snap.step(tick)
                    args.snapshot_out.parent.mkdir(parents=True, exist_ok=True)
                    args.snapshot_out.write_text(snap.render_ascii(args.rounds), encoding="utf-8")
                    print(f"[Keim] Snapshot geschrieben: {args.snapshot_out}")
                return 0

            case "explain":
                program = parse_file(args.file)
                plan = compile_plan(program)
                if args.as_json:
                    payload = {"source": program.source_name, "plan": [{"name": op.name, "args": op.args, "note": op.note} for op in plan.ops]}
                    if args.bytecode:
                        payload["bytecode"] = compile_bytecode(program).as_dict()
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                    return 0
                print("[Keim] AST")
                for node in program.declarations:
                    print(f"  {node!r}")
                print("\n[Keim] Plan")
                for i, op in enumerate(plan.ops, start=1):
                    print(f"  {i:02d}. {op.name}({', '.join(op.args)})")
                    print(f"      {op.note}")
                if args.bytecode:
                    bp = compile_bytecode(program)
                    print("\n[Keim] Bytecode-Statistik")
                    for k, v in bp.stats().items():
                        print(f"  {k}: {v}")
                return 0

            case "analyze":
                report = analyze_program(parse_file(args.file))
                print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2) if args.as_json else report.format())
                return 0 if report.ok else 1

            case "bytecode":
                bp = compile_bytecode(parse_file(args.file))
                if args.as_json:
                    print(json.dumps(bp.as_dict(), ensure_ascii=False, indent=2))
                else:
                    print("[Keim] Bytecode")
                    for op in bp.ops:
                        hint = f" | GPU: {op.gpu_hint}" if op.gpu_hint else ""
                        print(f"  {op.pc:03d}: {op.opcode.value} {op.args}  # Zeile {op.source_line}{hint}")
                    print("\n[Keim] Statistik")
                    for k, v in bp.stats().items():
                        print(f"  {k}: {v}")
                return 0

            case "kernel-plan":
                plan = compile_kernel_plan(parse_file(args.file))
                if args.as_json:
                    print(json.dumps(plan, ensure_ascii=False, indent=2))
                else:
                    print("[Keim] GPU-/Treiber-Mappingplan v2.0")
                    print(f"  Quelle: {plan['source']}")
                    stats = plan["stats"]
                    print(f"  Ops: {stats['op_count']} | GPU-Kandidaten: {stats['gpu_candidate_ops']}")
                    print("\n  Bündel:")
                    for b in plan["bundles"]:
                        print(f"    - pc {b['start_pc']:03d}..{b['end_pc']:03d} regime={b['regime']} ops={', '.join(b['opcodes'])}")
                    print("\n  Strategie:")
                    for item in plan["driver_strategy"]:
                        print(f"    - {item}")
                return 0

            case "kernel-abi":
                abi = compile_kernel_abi(parse_file(args.file))
                if args.out:
                    _write_json(args.out, abi)
                if args.as_json or not args.out:
                    print(json.dumps(abi, ensure_ascii=False, indent=2))
                else:
                    print("[Keim] Kernel-ABI geschrieben.")
                    print(f"  Format: {abi['format']}")
                    print(f"  Datei:  {args.out}")
                    print(f"  Launch-Gruppen: {len(abi['launch_groups'])}")
                    print(f"  Hazards: {len(abi['hazards'])}")
                return 0

            case "optimize":
                report = analyze_optimization(parse_file(args.file))
                print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2) if args.as_json else report.format())
                return 0

            case "verify":
                loaded = load_source_file(args.file)
                source_text = loaded.source
                program = parse_source(source_text, source_name=str(args.file))
                reports = {backend: run_program(program, RunOptions(rounds=args.rounds, show_every=0, seed=args.seed, quiet=True, backend=backend)) for backend in PURE_BACKENDS}
                base = reports["cpu"].cpu.as_dict()
                diffs = {backend: compare_final(base, report.cpu.as_dict())["differences"] for backend, report in reports.items() if backend != "cpu"}
                ok = all(not values for values in diffs.values())
                payload = {"ok": ok, "rounds": args.rounds, "seed": args.seed, "results": {k: v.cpu.as_dict() for k, v in reports.items()}, "differences": diffs}
                if args.as_json:
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                elif ok:
                    print("[Keim] Verify OK: CPU, VM, Fused, Circuit und Segmented erzeugen denselben finalen Zustand.")
                    print(f"  Runden: {args.rounds}")
                    print(f"  Seed:   {args.seed}")
                    for name in PURE_BACKENDS:
                        print(f"  {name:9}{reports[name].cpu.ms_per_round:9.3f} ms/Runde")
                else:
                    print("[Keim] Verify fehlgeschlagen.")
                    for backend, values in diffs.items():
                        for diff in values:
                            print(f"  {backend}:{diff['key']}: cpu={diff['expected']} backend={diff['actual']}")
                return 0 if ok else 1

            case "test":
                report = run_contracts_from_file(args.file, rounds=args.rounds, seed=args.seed, backend=args.backend)
                payload = report.as_dict()
                if args.out:
                    _write_json(args.out, payload)
                print(json.dumps(payload, ensure_ascii=False, indent=2) if args.as_json else report.format())
                return 0 if report.ok else 1

            case "profile":
                program = parse_file(args.file)
                results = {backend: run_program(program, RunOptions(rounds=args.rounds, show_every=0, seed=args.seed, quiet=True, backend=backend)).cpu.as_dict() for backend in PURE_BACKENDS}
                base = results["cpu"]["ms_per_round"] or 1e-9
                payload = {"source": str(args.file), "rounds": args.rounds, "seed": args.seed, "results": results, "speedups_vs_cpu": {name: base / max(1e-9, data["ms_per_round"]) for name, data in results.items()}}
                if args.as_json:
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                else:
                    print("[Keim] Backend-Profil v2.0")
                    print(f"  Quelle: {args.file}")
                    print(f"  Runden: {args.rounds}")
                    for name in PURE_BACKENDS:
                        data = results[name]
                        print(f"  {name:9} {data['ms_per_round']:9.3f} ms/Runde  x{payload['speedups_vs_cpu'][name]:.2f} vs CPU")
                    segmented_metrics = results["segmented"].get("metrics") or []
                    if segmented_metrics:
                        last = segmented_metrics[-1]
                        print("  Segmented-Metriken letzte Runde:")
                        for key in sorted(k for k in last if k.startswith("segmented:")):
                            print(f"    {key}: {last[key]}")
                return 0

            case "expand":
                loaded = load_source_file(args.file)
                if args.as_json:
                    print(json.dumps(loaded.as_dict(), ensure_ascii=False, indent=2))
                else:
                    print("[Keim] Expand v2.0")
                    print(f"  Datei: {args.file}")
                    print(f"  Imports: {len(loaded.imports)}")
                    print(f"  Werte: {', '.join(loaded.values) if loaded.values else '-'}")
                    print(f"  Bausteine: {', '.join(loaded.macros) if loaded.macros else '-'}")
                    print(f"  Parametrisch: {', '.join(loaded.parameterized_macros) if loaded.parameterized_macros else '-'}")
                    print(f"  Nutzungen: {loaded.expansion_count}\n")
                    print(loaded.source, end="" if loaded.source.endswith("\n") else "\n")
                return 0

            case "symbols":
                loaded = load_source_file(args.file)
                payload = loaded.as_dict()
                if args.as_json:
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                else:
                    print("[Keim] Symbole v2.0")
                    print(f"  Datei: {args.file}")
                    print("  Imports:")
                    for item in loaded.imports or ("-",):
                        print(f"    - {item}")
                    print("  Werte:")
                    for name, value in loaded.values.items():
                        print(f"    {name} = {value}")
                    if not loaded.values:
                        print("    -")
                    print("  Bausteine:")
                    for name in loaded.macros or ("-",):
                        print(f"    - {name}")
                return 0

            case "gpu-validate":
                report = validate_gpu_mapping(parse_file(args.file), dll=args.dll, gpu_index=args.gpu_index, smoke=args.smoke)
                print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2) if args.as_json else report.format())
                return 0 if report.ok or args.dll is None else 1

            case "observe":
                report = observe_program(parse_file(args.file), rounds=args.rounds, seed=args.seed, backend=args.backend, every=args.every)
                payload = report.as_dict()
                if args.out:
                    _write_json(args.out, payload)
                print(json.dumps(payload, ensure_ascii=False, indent=2) if args.as_json else report.format())
                return 0

            case "sweep":
                source, _imports = load_raw_with_imports(args.file)
                report = run_sweep(source, source_name=str(args.file), variations=args.vary, rounds=args.rounds, seed=args.seed, backend=args.backend, limit=args.limit)
                payload = report.as_dict()
                if args.out:
                    _write_json(args.out, payload)
                print(json.dumps(payload, ensure_ascii=False, indent=2) if args.as_json else report.format(top=args.top))
                return 0

            case "replay":
                loaded = load_source_file(args.file)
                source_text = loaded.source
                rows = read_trace(args.trace)
                header = trace_header(rows)
                expected = trace_final(rows)
                if header.get("source_sha256") != sha256_text(source_text):
                    print("[Keim] Replay-Warnung: Quelltext-Hash unterscheidet sich vom Trace.")
                program = parse_source(source_text, source_name=str(args.file))
                seed = int(header.get("seed", 7))
                rounds = int(header.get("rounds", expected.get("rounds", 60)))
                report = run_program(program, RunOptions(rounds=rounds, show_every=0, seed=seed, quiet=True))
                comparison = compare_final(expected, report.cpu.as_dict())
                if comparison["ok"]:
                    print("[Keim] Replay OK: finaler Zustand stimmt mit Trace überein.")
                    return 0
                print("[Keim] Replay abweichend:")
                for diff in comparison["differences"]:
                    print(f"  {diff['key']}: erwartet={diff['expected']} aktuell={diff['actual']}")
                return 1

            case "export":
                write_standalone_runner(args.file, args.out, default_rounds=args.rounds, default_seed=args.seed)
                print(f"[Keim] Export geschrieben: {args.out}")
                return 0

            case "build":
                report = build_project(args.file, args.out, name=args.name, default_rounds=args.rounds)
                print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2) if args.as_json else report.format())
                return 0

            case "new":
                files = new_project(args.dir, name=args.name)
                print("[Keim] Neues Projekt v2.0")
                print(f"  Ziel: {args.dir}")
                for f in files:
                    print(f"  + {f}")
                return 0

            case "bench":
                source = _bench_source(args.agents, args.width, args.height)
                program = parse_source(source, source_name="<benchmark>")
                t0 = perf_counter()
                report = run_program(program, RunOptions(rounds=args.rounds, show_every=0, seed=args.seed, quiet=True, collect_metrics=True, backend=args.backend))
                elapsed = perf_counter() - t0
                print("[Keim] Benchmark")
                print(f"  Backend:       {report.backend}")
                print(f"  Agenten:       {args.agents}")
                print(f"  Gitterzellen:  {args.width * args.height}")
                print(f"  Runden:        {args.rounds}")
                print(f"  Gesamtzeit:    {elapsed:.4f}s")
                print(f"  Zeit/Runde:    {elapsed / max(1, args.rounds) * 1000:.4f} ms")
                print(f"  Agent-Runden/s:{args.agents * args.rounds / max(elapsed, 1e-9):.0f}")
                if args.stats_out:
                    data = report.as_dict()
                    data["measured_cli_elapsed_seconds"] = elapsed
                    _write_json(args.stats_out, data)
                return 0

            case "driver-info":
                report = DriverProbe(args.dll, gpu_index=args.gpu_index).inspect(smoke=args.smoke)
                print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2) if args.as_json else report.format())
                return 0

            case "gpu-driver-status":
                payload = gpu76_status_payload(args.dll)
                if args.as_json:
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                else:
                    report = gpu76_inspect_driver(args.dll or gpu76_default_driver_path(), load=False)
                    print(report.format())
                return 0

            case "gpu-driver-plan":
                payload = gpu76_build_execution_plan(dll=args.dll)
                if args.out:
                    _write_json(args.out, payload)
                if args.as_json or not args.out:
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                return 0

            case "gpu-driver-demo":
                if args.as_json:
                    payload = _run_silencing_native_output(lambda: gpu76_run_driver_demo(args.dll, out=args.out, size=args.size, force_cpu=args.force_cpu))
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                else:
                    payload = gpu76_run_driver_demo(args.dll, out=args.out, size=args.size, force_cpu=args.force_cpu)
                    print("[Keim v7.6] GPU Driver Demo OK")
                    print(f"  Real Enabled: {payload.get('real_enabled')}")
                    print(f"  Profile:      {len(payload.get('profiles', []))}")
                    if args.out:
                        print(f"  Report:       {args.out}")
                return 0


            case "native-link-status":
                payload = internal_linker_status()
                if args.as_json:
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                else:
                    print("[Keim v7.7] Internal Native Linker")
                    print(f"  Version: {payload['version']}")
                    print("  Externer Compiler nötig: nein")
                    print("  Ziele: " + ", ".join(payload["targets"]))
                return 0

            case "native-link":
                target = None if args.target == "auto" else args.target
                payload = internal_link_kbc_file(args.file, args.out, target=target).as_dict()
                if args.as_json:
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                else:
                    print(f"[Keim v7.7] Native-Artefakt gelinkt: {args.out}")
                    print(f"  Target: {payload['target']}")
                    print(f"  Bytes:  {payload['bytes']}")
                    print(f"  SHA256: {payload['sha256']}")
                return 0

            case "native-link-demo":
                target = None if args.target == "auto" else args.target
                text = args.text.encode("utf-8").decode("unicode_escape")
                payload = internal_link_stdout_executable(text, args.out, target=target).as_dict()
                if args.as_json:
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                else:
                    print(f"[Keim v7.7] Native-Link-Demo erzeugt: {args.out}")
                    print(f"  Target: {payload['target']}")
                    print(f"  Bytes:  {payload['bytes']}")
                return 0

            case "doctor":
                import sys, shutil, platform
                print("[Keim] Doctor")
                print(f"  Version:       {__version__}")
                print(f"  Python:        {sys.version.split()[0]}")
                print(f"  Plattform:     {platform.platform()}")
                print(f"  Projektordner: {Path.cwd()}")
                print(f"  C++ Compiler:  {shutil.which('cl') or shutil.which('g++') or shutil.which('clang++') or '-'}")
                print(f"  Native DLL:    {'ja' if any((Path('build/native')/n).exists() for n in ['keim_vm_native.dll','keim_vm_native.so','keim_vm_native.dylib']) else 'nein'}")
                return 0

            case "routes":
                from .ast_nodes import HttpServiceDecl
                program = parse_file(args.file)
                found = []
                for decl in program.declarations:
                    if isinstance(decl, HttpServiceDecl):
                        for route in decl.routes:
                            found.append({"service": decl.name, "port": decl.port, "method": route.method, "path": route.path})
                if args.as_json:
                    print(json.dumps(found, ensure_ascii=False, indent=2))
                else:
                    print("[Keim] Routen")
                    for r in found:
                        print(f"  {r['method']:6s} http://127.0.0.1:{r['port']}{r['path']}  ({r['service']})")
                return 0

            case "serve":
                import time
                from .backends.cpu import CpuBackend, CpuConfig
                program = parse_file(args.file)
                analysis = analyze_program(program)
                if not analysis.ok:
                    print(analysis.format())
                    return 1
                backend = CpuBackend(CpuConfig(seed=args.seed, show_every=args.show_every, quiet=True, collect_metrics=True, sandbox=SandboxPolicy.from_cli(args.sandbox, args.allow)))
                backend.load(program)
                ports = sorted(backend._http_servers)
                if ports:
                    print(f"[Keim] interne HTTP-Dienste aktiv auf Port(s): {', '.join(map(str, ports))}")
                try:
                    tick = 0
                    while args.rounds == 0 or tick < args.rounds:
                        tick += 1
                        backend.step(tick)
                        time.sleep(0.02)
                except KeyboardInterrupt:
                    print("\n[Keim] Dienst beendet.")
                finally:
                    backend.shutdown_http()
                return 0

            case "gui":
                import time, webbrowser
                gui_server = start_web_gui("cli", args.port, args.title, args.api, debug_base=args.debug)
                url = f"http://127.0.0.1:{args.port}/"
                print(f"[Keim] Web-GUI aktiv: {url}")
                try:
                    webbrowser.open(url)
                except Exception:
                    pass
                try:
                    while True:
                        time.sleep(1)
                except KeyboardInterrupt:
                    print("\n[Keim] GUI beendet.")
                    gui_server.shutdown()
                return 0

            case "get":
                info = KeimPackageManager().install(args.source, name=args.name)
                print(f"[Keim] Paket installiert: {info.name} {info.version} -> {info.path}")
                return 0

            case "packages":
                infos = KeimPackageManager().list()
                if not infos:
                    print("[Keim] Keine Pakete installiert.")
                for info in infos:
                    print(f"{info.name} {info.version} {info.path} permissions={','.join(info.permissions) if info.permissions else '-'}")
                return 0

            case "init":
                manifest = KeimPackageManager().init_manifest(args.name)
                print(f"[Keim] Manifest angelegt: {manifest}")
                return 0

            case "export-bin":
                _export_bin(args.file, args.out, args.rounds, args.asset)
                print(f"[Keim] Export erzeugt: {args.out}")
                return 0

            case "export-py":
                _export_py(args.file, args.out, args.rounds)
                print(f"[Keim] Single-File Python-Bundle erzeugt: {args.out}")
                return 0

            case "debug":
                bus = DebugBus()
                server = start_debug_server(bus, args.port)
                program = parse_file(args.file)
                analysis = analyze_program(program)
                if not analysis.ok:
                    print(analysis.format())
                    server.shutdown()
                    return 1
                print(f"[Keim] DebugBus aktiv: http://127.0.0.1:{args.port}/debug/events")
                try:
                    run_program(program, RunOptions(rounds=args.rounds, show_every=0, seed=args.seed, quiet=False, debug_bus=bus, sandbox=SandboxPolicy.from_cli(args.sandbox, args.allow)))
                finally:
                    server.shutdown()
                return 0


            case "check":
                entry = args.file
                if entry is None:
                    from .foundation import load_project
                    entry, _ = load_project(None, Path.cwd())
                graph = ModuleGraph(entry).load()
                report = analyze_graph(graph)
                print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2) if args.as_json else report.format())
                return 0 if report.ok else 1

            case "core-run":
                result = core_run(args.file, record=args.record)
                return 0 if result.ok else 1

            case "core-bytecode":
                payload = core_bytecode(args.file)
                if args.out:
                    _write_json(args.out, payload)
                if args.as_json or not args.out:
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                return 0

            case "core-test":
                if args.as_json:
                    import contextlib, io
                    with contextlib.redirect_stdout(io.StringIO()):
                        payload = core_test(args.file)
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                else:
                    payload = core_test(args.file)
                    print(_format_core_tests(payload))
                return 0 if payload.get("ok") else 1

            case "core-export":
                export_independent_bundle(args.file, args.out)
                print(f"[Keim] v6 Independent-Core Bundle erzeugt: {args.out}")
                return 0

            case "lock":
                payload = build_lock(args.cwd)
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                return 0

            case "lint":
                graph = ModuleGraph(args.file).load()
                report = lint_graph(graph)
                print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2) if args.as_json else report.format())
                return 0 if report.ok else 1

            case "fmt":
                text = format_path(args.path, write=args.write)
                if args.write:
                    print(f"[Keim] formatiert: {args.path}")
                else:
                    print(text, end="")
                return 0

            case "core-replay":
                payload = replay_file(args.file)
                if args.as_json:
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                else:
                    print(f"[Keim Replay] OK, Events: {payload.get('event_count', 0)}")
                return 0

            case "enterprise-check":
                graph = ModuleGraph(args.file).load()
                diagnostics = enterprise_analyze_graph(graph)
                payload = {"ok": not any(d.severity == "error" for d in diagnostics), "diagnostics": [d.as_dict() for d in diagnostics]}
                if args.as_json:
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                else:
                    print("[Keim Enterprise] Check " + ("OK" if payload["ok"] else "FEHLER"))
                    for d in diagnostics:
                        print(f"  {d.severity.upper()} {d.module}:Zeile {d.line}: {d.message}")
                return 0 if payload["ok"] else 1

            case "enterprise-build":
                payload = enterprise_build(args.cwd, args.out, profile=args.profile)
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                return 0

            case "enterprise-test":
                payload = enterprise_test(args.path, TestRunOptions(filter=args.filter, json_report=args.json_out, junit_report=args.junit_out, coverage=args.coverage))
                if args.as_json:
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                else:
                    print("[Keim Enterprise] Tests " + ("OK" if payload.get("ok") else "FEHLER"))
                    for t in payload.get("tests", []):
                        print(f"  {'OK' if t.get('ok') else 'FEHLER':7} {t.get('full_name')}")
                    if "coverage" in payload:
                        c = payload["coverage"]
                        print(f"  Coverage Funktionen: {c.get('functions_referenced_by_tests')}/{c.get('functions_total')} ({c.get('ratio'):.2%})")
                return 0 if payload.get("ok") else 1

            case "enterprise-fmt":
                text = enterprise_format_path(args.path, write=args.write)
                if not args.write:
                    print(text, end="")
                else:
                    print(f"[Keim Enterprise] formatiert: {args.path}")
                return 0

            case "enterprise-lint":
                report = enterprise_lint(ModuleGraph(args.file).load())
                print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2) if args.as_json else report.format())
                return 0 if report.ok else 1

            case "enterprise-replay":
                payload = enterprise_replay(args.file, strict=args.strict)
                if args.as_json:
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                else:
                    print(f"[Keim Enterprise Replay] OK, Events: {payload.get('event_count', 0)}, monoton: {payload.get('monotonic')}")
                return 0

            case "enterprise-native":
                payload = emit_native_seed(args.bytecode, args.out)
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                return 0

            case "enterprise-wasm":
                payload = emit_wasm_seed(args.bytecode, args.out)
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                return 0

            case "enterprise-status":
                payload = enterprise_status_matrix()
                if args.as_json:
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                else:
                    print("[Keim Enterprise] Zehn-Bausteine-Status")
                    for row in payload:
                        print(f"  {row['baustein']}: {row['status']} — {row['artefakt']}")
                return 0


            case "v64-status":
                payload = status64()
                print(json.dumps(payload, ensure_ascii=False, indent=2) if args.as_json else "[Keim v6.4] Professional Core aktiv")
                return 0

            case "v64-expr":
                payload = expr_to_dict(parse_keim_expr(args.expr))
                print(json.dumps(payload, ensure_ascii=False, indent=2) if args.as_json else json.dumps(payload, ensure_ascii=False, indent=2))
                return 0

            case "v64-check":
                report = check64(args.file)
                print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2) if args.as_json else report.format())
                return 0 if report.ok else 1

            case "v64-bytecode":
                from .compiler64 import compile_program64
                payload = compile_program64(ModuleGraph(args.file).load()).as_dict()
                if args.out:
                    _write_json(args.out, payload)
                if args.as_json or not args.out:
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                return 0 if not any(d.get("severity") == "error" for d in payload.get("diagnostics", [])) else 1

            case "v64-run":
                result = run64(args.file, record=args.record)
                return 0 if result.ok else 1

            case "v64-build":
                payload = build64(args.cwd, args.out)
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                return 0

            case "v64-test":
                payload = test64(args.file, TestRunOptions64(filter=args.filter, junit=args.junit, coverage=args.coverage))
                print(json.dumps(payload, ensure_ascii=False, indent=2) if args.as_json else _format_core_tests(payload))
                return 0 if payload.get("ok") else 1

            case "v64-lint":
                report = lint64(args.file)
                print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2) if args.as_json else report.format())
                return 0 if report.ok else 1

            case "v64-fmt":
                text = format64_source(args.file.read_text(encoding="utf-8"))
                if args.write:
                    args.file.write_text(text, encoding="utf-8")
                    print(f"[Keim v6.4] formatiert: {args.file}")
                else:
                    print(text, end="")
                return 0

            case "v64-native":
                emit_native_vm64(load_program64(args.bytecode), args.out)
                print(f"[Keim v6.4] Native VM Seed geschrieben: {args.out}")
                return 0

            case "v64-wasm":
                emit_wasm64(load_program64(args.bytecode), args.out)
                print(f"[Keim v6.4] WASM Seed geschrieben: {args.out}")
                return 0

            case "v65-status":
                payload = status65()
                print(json.dumps(payload, ensure_ascii=False, indent=2) if args.as_json else "[Keim v6.5] Native/Generics/Result/Match/Binary aktiv")
                return 0

            case "v65-check":
                report = check65(args.file)
                print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2) if args.as_json else report.format())
                return 0 if report.ok else 1

            case "v65-bytecode":
                program = bytecode65(args.file)
                payload = program.as_dict()
                if args.out:
                    _write_json(args.out, payload)
                if args.binary_out:
                    write_kbc65b(program, args.binary_out)
                    print(f"[Keim v6.5] Binary Bytecode geschrieben: {args.binary_out}")
                if args.as_json or (not args.out and not args.binary_out):
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                return 0

            case "v65-run":
                result = run65(args.file, record=args.record)
                return 0 if result.ok else 1

            case "v65-run-bin":
                result = run_kbc65b(args.file)
                return 0 if result.ok else 1

            case "v65-build":
                payload = build65(args.cwd, args.out)
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                return 0

            case "v65-test":
                payload = test65(args.file, junit=args.junit)
                print(json.dumps(payload, ensure_ascii=False, indent=2) if args.as_json else _format_core_tests(payload))
                return 0 if payload.get("ok") else 1

            case "v65-native":
                emit_native_keimvm65(load_program65(args.bytecode), args.out)
                print(f"[Keim v6.5] Native keimvm MVP geschrieben: {args.out}")
                return 0

            case "v66-status":
                payload = status66()
                print(json.dumps(payload, ensure_ascii=False, indent=2) if args.as_json else "[Keim v6.6] Enterprise Runtime Completion OK")
                return 0

            case "v66-check":
                report = check66(args.file)
                print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2) if args.as_json else report.format())
                return 0 if report.ok else 1

            case "v66-bytecode":
                payload = bytecode66(args.file, out=args.out, binary_out=args.binary_out)
                if args.as_json or not args.out:
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                return 0

            case "v66-run":
                result = run66(args.file, record=args.record)
                return 0 if result.ok else 1

            case "v66-run-bin":
                result = run_kbc66b(args.file)
                return 0 if result.ok else 1

            case "v66-build":
                payload = build66(args.cwd, args.out)
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                return 0

            case "v66-test":
                payload = test66(args.file, filter_text=args.filter, junit=args.junit)
                print(json.dumps(payload, ensure_ascii=False, indent=2) if args.as_json else _format_core_tests(payload))
                return 0 if payload.get("ok") else 1

            case "v66-native":
                program = read_kbc66b(args.bytecode) if str(args.bytecode).endswith(".kbc66b") else json.loads(args.bytecode.read_text(encoding="utf-8"))
                emit_native_keimvm66(program, args.out)
                print(f"[Keim v6.6] Native keimvm66 geschrieben: {args.out}")
                return 0

            case "v66-lock":
                payload = create_lock66(args.cwd, args.out)
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                return 0

            case "v66-replay":
                payload = validate_replay66(args.file)
                print(json.dumps(payload, ensure_ascii=False, indent=2) if args.as_json else f"[Keim v6.6] Replay OK, Events: {payload.get('event_count', 0)}")
                return 0
            case "v67-status":
                payload = status67()
                print(json.dumps(payload, ensure_ascii=False, indent=2) if args.as_json else "[Keim v6.7] Enterprise Complete OK")
                return 0

            case "v67-check":
                report = check67(args.file)
                print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2) if args.as_json else report.format())
                return 0 if report.ok else 1

            case "v67-bytecode":
                payload = bytecode67(args.file, out=args.out, binary_out=args.binary_out)
                if args.as_json or not args.out:
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                return 0

            case "v67-run":
                result = run67(args.file, record=args.record)
                return 0 if result.ok else 1

            case "v67-run-bin":
                result = run_kbc67b(args.file)
                return 0 if result.ok else 1

            case "v67-build":
                payload = build67(args.cwd, args.out)
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                return 0

            case "v67-test":
                payload = test67(args.file, filter_text=args.filter, junit=args.junit)
                print(json.dumps(payload, ensure_ascii=False, indent=2) if args.as_json else _format_core_tests(payload))
                return 0 if payload.get("ok") else 1

            case "v67-wasm":
                program = read_kbc67b(args.bytecode) if str(args.bytecode).endswith(".kbc67b") else json.loads(args.bytecode.read_text(encoding="utf-8"))
                emit_wasm67(program, args.out)
                print(f"[Keim v6.7] WAT geschrieben: {args.out}")
                return 0

            case "v67-lock":
                payload = create_lock67(args.cwd, args.out, registry=args.registry)
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                return 0

            case "v67-registry":
                match args.action:
                    case "init":
                        payload = registry_init67(args.registry)
                    case "publish":
                        payload = registry_publish67(args.cwd, args.registry, name=args.name, version=args.version)
                    case "resolve":
                        payload = registry_resolve67(args.registry, args.name, args.requirement)
                    case "install":
                        payload = registry_install67(args.registry, args.name, args.requirement, cache=args.cache)
                    case "serve":
                        serve_registry67(args.registry, args.host, args.port)
                        return 0
                    case _:
                        payload = {"ok": False, "error": "unknown action"}
                print(json.dumps(payload, ensure_ascii=False, indent=2) if args.as_json else json.dumps(payload, ensure_ascii=False, indent=2))
                return 0

            case "v67-replay":
                payload = validate_replay67(args.file, html_out=args.html_out)
                print(json.dumps(payload, ensure_ascii=False, indent=2) if args.as_json else f"[Keim v6.7] Replay/TimeTravel OK, Events: {payload.get('event_count', 0)}")
                return 0

            case "v68-status":
                payload = status68()
                print(json.dumps(payload, ensure_ascii=False, indent=2) if args.as_json else "[Keim v6.8] WASM Heap Runtime OK")
                return 0

            case "v68-check":
                report = check68(args.file)
                print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2) if args.as_json else report.format())
                return 0 if report.ok else 1

            case "v68-bytecode":
                payload = bytecode68(args.file, out=args.out, binary_out=args.binary_out)
                if args.as_json or not args.out:
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                return 0

            case "v68-run":
                result = run68(args.file, record=args.record)
                return 0 if result.ok else 1

            case "v68-run-bin":
                result = run_kbc68b(args.file)
                return 0 if result.ok else 1

            case "v68-build":
                payload = build68(args.cwd, args.out)
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                return 0

            case "v68-test":
                payload = test68(args.file, filter_text=args.filter, junit=args.junit)
                print(json.dumps(payload, ensure_ascii=False, indent=2) if args.as_json else _format_core_tests(payload))
                return 0 if payload.get("ok") else 1

            case "v68-wasm":
                program = read_kbc68b(args.bytecode) if str(args.bytecode).endswith(".kbc68b") else json.loads(args.bytecode.read_text(encoding="utf-8"))
                emit_wasm68(program, args.out)
                print(f"[Keim v6.8] WAT Heap Runtime geschrieben: {args.out}")
                return 0

            case "v69-status":
                payload = status69()
                print(json.dumps(payload, ensure_ascii=False, indent=2) if args.as_json else "[Keim v6.9] WASM GC/Hashmap Runtime OK")
                return 0

            case "v69-check":
                report = check69(args.file)
                print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2) if args.as_json else report.format())
                return 0 if report.ok else 1

            case "v69-bytecode":
                payload = bytecode69(args.file, out=args.out, binary_out=args.binary_out)
                if args.as_json or not args.out:
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                return 0

            case "v69-run":
                result = run69(args.file, record=args.record)
                return 0 if result.ok else 1

            case "v69-run-bin":
                result = run_kbc69b(args.file)
                return 0 if result.ok else 1

            case "v69-build":
                payload = build69(args.cwd, args.out)
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                return 0

            case "v69-test":
                payload = test69(args.file, filter_text=args.filter, junit=args.junit)
                print(json.dumps(payload, ensure_ascii=False, indent=2) if args.as_json else _format_core_tests(payload))
                return 0 if payload.get("ok") else 1

            case "v69-wasm":
                program = read_kbc69b(args.bytecode) if str(args.bytecode).endswith(".kbc69b") else json.loads(args.bytecode.read_text(encoding="utf-8"))
                emit_wasm69(program, args.out)
                print(f"[Keim v6.9] WAT GC/Hashmap Runtime geschrieben: {args.out}")
                return 0

            case "v70-status":
                payload = status70()
                print(json.dumps(payload, ensure_ascii=False, indent=2) if args.as_json else "[Keim v7.0] Generational WASM GC Runtime OK")
                return 0

            case "v70-check":
                report = check70(args.file)
                print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2) if args.as_json else report.format())
                return 0 if report.ok else 1

            case "v70-bytecode":
                payload = bytecode70(args.file, out=args.out, binary_out=args.binary_out)
                if args.as_json or not args.out:
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                return 0

            case "v70-run":
                result = run70(args.file, record=args.record)
                return 0 if result.ok else 1

            case "v70-run-bin":
                result = run_kbc70b(args.file)
                return 0 if result.ok else 1

            case "v70-build":
                payload = build70(args.cwd, args.out)
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                return 0

            case "v70-test":
                payload = test70(args.file, filter_text=args.filter, junit=args.junit)
                print(json.dumps(payload, ensure_ascii=False, indent=2) if args.as_json else _format_core_tests(payload))
                return 0 if payload.get("ok") else 1

            case "v70-wasm":
                program = read_kbc70b(args.bytecode) if str(args.bytecode).endswith(".kbc70b") else json.loads(args.bytecode.read_text(encoding="utf-8"))
                emit_wasm70(program, args.out)
                print(f"[Keim v7.0] WAT Generational-GC Runtime geschrieben: {args.out}")
                return 0

            case "v71-status":
                payload = status71()
                print(json.dumps(payload, ensure_ascii=False, indent=2) if args.as_json else "[Keim v7.1] Compacting GC + Region Allocator aktiv")
                return 0

            case "v71-check":
                report = check71(args.file)
                print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2) if args.as_json else report.format())
                return 0 if report.ok else 1

            case "v71-bytecode":
                payload = bytecode71(args.file, out=args.out, binary_out=args.binary_out)
                if args.as_json or (not args.out and not args.binary_out):
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                return 0 if not any(d.get("severity") == "error" for d in payload.get("diagnostics", [])) else 1

            case "v71-run":
                result = run71(args.file, record=args.record)
                return 0 if result.ok else 1

            case "v71-run-bin":
                result = run_kbc71b(args.file)
                return 0 if result.ok else 1

            case "v71-build":
                payload = build71(args.cwd, args.out)
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                return 0 if payload.get("ok") else 1

            case "v71-test":
                payload = test71(args.file, filter_text=args.filter, junit=args.junit)
                print(json.dumps(payload, ensure_ascii=False, indent=2) if args.as_json else "[Keim v7.1] Tests " + ("OK" if payload.get("ok") else "FEHLER"))
                return 0 if payload.get("ok") else 1

            case "v71-wasm":
                program = read_kbc71b(args.bytecode) if str(args.bytecode).endswith(".kbc71b") else json.loads(args.bytecode.read_text(encoding="utf-8"))
                emit_wasm71(program, args.out)
                print(f"[Keim v7.1] WAT Compacting-GC/Region Runtime geschrieben: {args.out}")
                return 0



            case "v75-status":
                payload = status75()
                print(json.dumps(payload, ensure_ascii=False, indent=2) if args.as_json else "[Keim v7.5] Enterprise Hardening Matrix bereit")
                return 0

            case "v75-matrix":
                payload = run_differential_matrix(args.cwd, args.out, max_cases=args.max_cases, include_repository=not args.synthetic_only)
                print(json.dumps(payload, ensure_ascii=False, indent=2) if args.as_json else ("[Keim v7.5] Matrix OK" if payload.get("ok") else "[Keim v7.5] Matrix FEHLER"))
                return 0 if payload.get("ok") else 1

            case "v75-wasm-browser":
                payload = run_browser_wasm_suite(args.out)
                print(json.dumps(payload, ensure_ascii=False, indent=2) if args.as_json else ("[Keim v7.5] Browser/WASM OK" if payload.get("ok") else "[Keim v7.5] Browser/WASM FEHLER"))
                return 0 if payload.get("ok") else 1

            case "v75-compat":
                payload = compatibility75(args.cwd, args.out)
                print(json.dumps(payload, ensure_ascii=False, indent=2) if args.as_json else ("[Keim v7.5] Compat OK" if payload.get("ok") else "[Keim v7.5] Compat FEHLER"))
                return 0 if payload.get("ok") else 1

            case "v75-hardening-build":
                payload = hardening_build75(args.cwd, args.out)
                print(json.dumps(payload, ensure_ascii=False, indent=2) if args.as_json else ("[Keim v7.5] Hardening Build OK" if payload.get("ok") else "[Keim v7.5] Hardening Build FEHLER"))
                return 0 if payload.get("ok") else 1

            case "v75-whitepaper":
                payload = whitepaper75(args.out)
                print(json.dumps(payload, ensure_ascii=False, indent=2) if args.as_json else f"[Keim v7.5] Whitepaper geschrieben: {args.out}")
                return 0


            case "v74-status":
                payload = status74()
                print(json.dumps(payload, ensure_ascii=False, indent=2) if args.as_json else "[Keim v7.4] Enterprise Stabilization aktiv")
                return 0

            case "v74-spec":
                payload = stable_spec()
                if args.out:
                    args.out.parent.mkdir(parents=True, exist_ok=True)
                    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                print(json.dumps(payload, ensure_ascii=False, indent=2) if args.as_json or not args.out else f"[Keim v7.4] Spezifikation geschrieben: {args.out}")
                return 0

            case "v74-check":
                report = check74(args.file)
                print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2) if args.as_json else report.format())
                return 0 if report.ok else 1

            case "v74-build":
                payload = build74(args.file, args.out)
                print(json.dumps(payload, ensure_ascii=False, indent=2) if args.as_json else f"[Keim v7.4] Stable Build OK: {args.out}")
                return 0 if payload.get("ok") else 1

            case "v74-verify":
                report = verify_stable(args.file)
                print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2) if args.as_json else report.format())
                return 0 if report.ok else 1

            case "v74-security":
                report = security_scan(args.path, args.policy)
                print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2) if args.as_json else report.format())
                return 0 if report.ok else 1

            case "v74-sbom":
                payload = create_sbom(args.cwd, args.out)
                print(json.dumps(payload, ensure_ascii=False, indent=2) if args.as_json else f"[Keim v7.4] SBOM geschrieben: {args.out / 'sbom.keim.json'}")
                return 0

            case "v74-parity":
                payload = parity_matrix(args.file, args.out)
                print(json.dumps(payload, ensure_ascii=False, indent=2) if args.as_json else f"[Keim v7.4] Paritätsmatrix geschrieben: {args.out}")
                return 0 if payload.get("ok") else 1

            case "v74-benchmark":
                payload = benchmark74(args.file, args.out, iterations=args.iterations)
                print(json.dumps(payload, ensure_ascii=False, indent=2) if args.as_json else f"[Keim v7.4] Benchmark geschrieben: {args.out}")
                return 0

            case "v74-compat":
                payload = compatibility_matrix(args.cwd, args.out)
                print(json.dumps(payload, ensure_ascii=False, indent=2) if args.as_json else f"[Keim v7.4] Kompatibilitätsmatrix geschrieben: {args.out}")
                return 0 if payload.get("ok") else 1

            case "v74-lsp-bundle":
                payload = write_lsp_bundle(args.out)
                print(json.dumps(payload, ensure_ascii=False, indent=2) if args.as_json else f"[Keim v7.4] LSP-Artefakte geschrieben: {args.out}")
                return 0

            case "v74-lsp":
                run_lsp_stdio()
                return 0

            case "v74-whitepaper":
                payload = emit_enterprise_whitepaper(args.out)
                print(json.dumps(payload, ensure_ascii=False, indent=2) if args.as_json else f"[Keim v7.4] Whitepaper geschrieben: {args.out}")
                return 0


            case "repl":
                from .repl import repl as start_repl
                return start_repl()

            case "training-impossible":
                if args.gui:
                    launch_training_gui(out=args.out, seed=args.seed)
                    return 0
                report = run_training_demo(steps=args.steps, out=args.out, seed=args.seed, headless=True)
                if args.as_json:
                    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
                else:
                    print("[Keim Training] Unmöglicher Prototyp OK")
                    print(f"  Schritte: {report.steps}")
                    print(f"  Best: {report.best_candidate} Score={report.best_score:.4f}")
                    for name, path in report.artifacts.items():
                        print(f"  {name}: {path}")
                return 0


            case "web-status":
                payload = web_status()
                if args.as_json:
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                else:
                    print("[Keim Web] v7.3 OK")
                    for cap in payload["capabilities"]:
                        print(f"  - {cap}")
                return 0

            case "web-new":
                payload = init_web_project(args.out, name=args.name)
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                return 0

            case "web-build":
                result = build_web_app(args.cwd, args.out, production=not args.dev)
                if args.as_json:
                    print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
                else:
                    print(f"[Keim Web] Build {'OK' if result.ok else 'FEHLER'}: {result.out}")
                    for f in result.files:
                        print(f"  {f}")
                    for d in result.diagnostics:
                        print(f"  {d['severity'].upper()}: {d['message']}")
                return 0 if result.ok else 1

            case "web-check":
                result = build_web_app(args.cwd, args.out, production=False)
                payload = {"ok": result.ok, "diagnostics": result.diagnostics, "files": result.files}
                print(json.dumps(payload, ensure_ascii=False, indent=2) if args.as_json else ("[Keim Web] Check OK" if result.ok else "[Keim Web] Check FEHLER"))
                return 0 if result.ok else 1

            case "web-adapter":
                payload = create_adapter(args.out, alias=args.alias, module=args.module, permission=args.permission)
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                return 0

            case "web-serve":
                serve_web(args.out, port=args.port)
                return 0

            case _:
                parser.print_help()
                return 2

    except WebEcosystemError as exc:
        print(f"[Keim Web] Fehler: {exc}")
        return 1
    except FoundationError as exc:
        print(f"[Keim Foundation] Fehler: {exc}")
        return 1
    except KeimError as exc:
        print(f"[Keim] Fehler: {exc}")
        return 1
    except DriverLoadError as exc:
        print(f"[Keim] Driver-Fehler: {exc}")
        return 1
    except ValueError as exc:
        print(f"[Keim] Fehler: {exc}")
        return 1




def _run_silencing_native_output(fn):
    """Run a callable while suppressing noisy native stdout/stderr.

    OpenCL drivers may print directly from C/C++ before JSON is emitted.  CLI
    JSON contracts must stay machine-readable, so v7.6.4 silences file
    descriptors 1/2 around native demo calls and only emits the JSON payload.
    """
    import os
    import sys
    import ctypes
    sys.stdout.flush()
    sys.stderr.flush()
    saved_out = saved_err = devnull = None
    try:
        try:
            ctypes.CDLL(None).fflush(None)
        except Exception:
            pass
        saved_out = os.dup(1)
        saved_err = os.dup(2)
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, 1)
        os.dup2(devnull, 2)
        result = fn()
        try:
            ctypes.CDLL(None).fflush(None)
        except Exception:
            pass
        return result
    finally:
        if saved_out is not None:
            os.dup2(saved_out, 1)
            os.close(saved_out)
        if saved_err is not None:
            os.dup2(saved_err, 2)
            os.close(saved_err)
        if devnull is not None:
            os.close(devnull)


def _format_core_tests(payload: dict[str, object]) -> str:
    lines = ["[Keim Foundation] Tests " + ("OK" if payload.get("ok") else "FEHLER")]
    for t in payload.get("tests", []):
        marker = "OK" if t.get("ok") else "FEHLER"
        extra = "" if t.get("ok") else f" :: {t.get('error')}"
        lines.append(f"  {marker:6} {t.get('module')}.{t.get('name')}{extra}")
    lines.append(f"  Anzahl: {payload.get('count', 0)}")
    return "\n".join(lines)


def _export_bin(source_file: Path, out: Path, rounds: int, assets: list[str]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    source = source_file.read_text(encoding="utf-8")
    program = parse_source(source, source_name=str(source_file))
    bytecode_payload = compile_bytecode(program).as_dict()
    runtime_dir = out / "runtime"
    runtime_dir.mkdir(exist_ok=True)
    import shutil
    src_pkg = Path(__file__).resolve().parent
    dst_pkg = runtime_dir / "keim"
    if dst_pkg.exists():
        shutil.rmtree(dst_pkg)
    shutil.copytree(src_pkg, dst_pkg, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "build"))
    asset_dir = out / "assets"
    asset_dir.mkdir(exist_ok=True)
    manifest = {"source": str(source_file), "rounds": rounds, "assets": [], "format": "keim-bundle-v5"}
    for item in assets:
        src = Path(item)
        dst = asset_dir / src.name
        if src.exists() and src.is_file():
            import shutil
            shutil.copy2(src, dst)
            manifest["assets"].append({"source": str(src), "path": f"assets/{dst.name}", "size": dst.stat().st_size})
    (out / "app.kbc.json").write_text(json.dumps(bytecode_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "bundle_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "keim_app.py").write_text(
        "from pathlib import Path\n"
        "import os, sys\n"
        "ROOT = Path(__file__).resolve().parent\n"
        "os.environ.setdefault('KEIM_BUNDLE_ROOT', str(ROOT))\n"
        "sys.path.insert(0, str(ROOT / 'runtime'))\n"
        "from keim.parser import parse_source\n"
        "from keim.runtime import RunOptions, run_program\n"
        f"SOURCE = {source!r}\n"
        f"run_program(parse_source(SOURCE, source_name='embedded:{source_file.name}'), RunOptions(rounds={rounds}, show_every=0, quiet=False, backend='cpu'))\n",
        encoding="utf-8",
    )
    (out / "keim_app.bat").write_text("@echo off\r\npython %~dp0keim_app.py\r\n", encoding="utf-8")
    (out / "README_RUN.txt").write_text(
        "Keim Genesis v5 Standalone-Bundle\n\nStart:\n  python keim_app.py\n\n"
        "Assets liegen unter ./assets; KEIM_BUNDLE_ROOT zeigt auf dieses Bundle.\n"
        "Eine echte native Single-File-EXE benötigt weiterhin einen externen Packager/Linker.\n",
        encoding="utf-8",
    )

def _export_py(source_file: Path, out: Path, rounds: int) -> None:
    source = source_file.read_text(encoding="utf-8")
    program = parse_source(source, source_name=str(source_file))
    bytecode_payload = compile_bytecode(program).as_dict()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "from keim.parser import parse_source\n"
        "from keim.runtime import RunOptions, run_program\n"
        f"SOURCE = {source!r}\n"
        f"BYTECODE = {json.dumps(bytecode_payload, ensure_ascii=False)!r}\n"
        f"run_program(parse_source(SOURCE, source_name='embedded:{source_file.name}'), RunOptions(rounds={rounds}, show_every=0, quiet=False, backend='cpu'))\n",
        encoding="utf-8",
    )

def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[Keim] JSON geschrieben: {path}")


def _bench_source(agents: int, width: int, height: int) -> str:
    return f"""
welt bench mit {agents} agenten groesse {width} {height}
feld hunger startet bei 0.2
feld energie startet bei 1.0
spur futter startet bei 0.0 quellen 24 diffundiert 0.16 zerfaellt 0.012
spur gefahr startet bei 0.0 quellen 8 diffundiert 0.11 zerfaellt 0.02

jede runde:
    agent wandert 0.08
    agent verliert energie 0.003
    agent bekommt hunger 0.005
    feld energie meidet spur gefahr mit 0.006
    feld energie schreibt spur futter mit 0.003
    wenn agent riecht spur gefahr > 0.28: agent meidet spur gefahr
    wenn hunger > 0.55: agent folgt spur futter
    wenn energie < 0.12: agent ruht
    wenn agent findet futter: hunger sinkt 0.35
    wenn agent findet futter: energie waechst 0.25
    wenn agent findet futter: spur futter wird staerker 0.55
    spur futter breitet sich aus

alle 5 runden:
    spur gefahr breitet sich aus
"""

if __name__ == "__main__":
    raise SystemExit(main())
