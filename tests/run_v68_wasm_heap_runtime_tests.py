from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = [sys.executable, "-S"]


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(PY + ["-m", "keim", *args], cwd=ROOT, text=True, capture_output=True, check=True)


def test_status_check_run() -> None:
    status = json.loads(run("v68-status", "--json").stdout)
    assert status["version"] == 680
    assert "tagged_i64_value_abi" in status["features"]
    run("v68-check", "examples/sprache_v68_wasm_heap_runtime.keim")
    run("v68-run", "examples/sprache_v68_wasm_heap_runtime.keim")


def test_binary_heap_sections_and_roundtrip() -> None:
    out = ROOT / "build" / "v68_tests" / "app.kbc68.json"
    bout = ROOT / "build" / "v68_tests" / "app.kbc68b"
    run("v68-bytecode", "examples/sprache_v68_wasm_heap_runtime.keim", "--out", str(out), "--binary-out", str(bout))
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["version"] == 680
    assert "heap_layouts" in payload
    assert "records" in payload["heap_layouts"]
    assert bout.read_bytes().startswith(b"KBC68HASH")
    run("v68-run-bin", str(bout))


def test_wasm_heap_runtime_lowering() -> None:
    out = ROOT / "build" / "v68_tests" / "app.kbc68.json"
    bout = ROOT / "build" / "v68_tests" / "app.kbc68b"
    wat = ROOT / "build" / "v68_tests" / "app_heap_runtime.wat"
    run("v68-bytecode", "examples/sprache_v68_wasm_heap_runtime.keim", "--out", str(out), "--binary-out", str(bout))
    run("v68-wasm", str(bout), "--out", str(wat))
    text = wat.read_text(encoding="utf-8")
    assert "unreachable" not in text
    assert "$tag_int" in text and "$heap_ref" in text
    assert "$keim_text_new" in text
    assert "$keim_list_new" in text and "call $keim_list_get" in text
    assert "$keim_record_new" in text and "call $keim_record_get" in text
    assert "$keim_map_new" in text and "call $keim_map_get" in text
    assert "$keim_result_ok" in text and "$keim_result_payload" in text
    assert "KBC68B" not in text  # text backend, not a binary dump


def test_build_and_integrated_test_runner() -> None:
    build = ROOT / "build" / "v68_tests" / "project"
    run("v68-build", "--cwd", ".", "--out", str(build))
    manifest = json.loads((build / "build_manifest.json").read_text(encoding="utf-8"))
    assert manifest["format"] == "keim-build-v68"
    assert "wasm_heap_runtime" in manifest
    res = json.loads(run("v68-test", "examples/sprache_v68_wasm_heap_runtime.keim", "--json").stdout)
    assert res["ok"] is True
    checks = res["coverage"]["v68_wasm_heap_runtime"]
    assert checks["heap_runtime"] and checks["no_unreachable"] and checks["lowered_heap_ops"]


def main() -> int:
    test_status_check_run()
    test_binary_heap_sections_and_roundtrip()
    test_wasm_heap_runtime_lowering()
    test_build_and_integrated_test_runner()
    print("[Keim v6.8] WASM Heap Runtime Tests OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
