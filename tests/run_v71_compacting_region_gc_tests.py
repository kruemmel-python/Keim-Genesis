from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = [sys.executable, "-S"]


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(PY + ["-m", "keim", *args], cwd=ROOT, text=True, capture_output=True, check=True)


def json_from_stdout(text: str) -> dict:
    start = text.find("{")
    assert start >= 0, text
    return json.loads(text[start:])


def test_status_check_bytecode_binary() -> None:
    status = json.loads(run("v71-status", "--json").stdout)
    assert status["version"] == 710
    assert "selective_compacting_gc" in status["features"]
    assert "region_alloc" in status["features"]
    out = ROOT / "build" / "v71" / "app.kbc71.json"
    bout = ROOT / "build" / "v71" / "app.kbc71b"
    run("v71-bytecode", "examples/sprache_v71_compacting_region_gc.keim", "--out", str(out), "--binary-out", str(bout), "--json")
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["version"] == 710
    assert payload["wasm_runtime"]["gc"]["algorithm"] == "hybrid-generational-mark-compact-with-region-temporaries"
    assert {"nursery", "old", "compact_from", "compact_to", "regions"}.issubset(payload["heap_layouts"]["spaces"].keys())
    assert payload["heap_layouts"]["object_header"]["forwarding_ptr"] == "u32@28"
    assert payload["heap_layouts"]["object_header"]["region_id"] == "u32@32"
    assert bout.read_bytes().startswith(b"KBC71CMP")
    assert "EVAL" not in out.read_text(encoding="utf-8")


def test_wat_compacting_region_gc() -> None:
    bout = ROOT / "build" / "v71" / "app.kbc71b"
    wat = ROOT / "build" / "v71" / "app_compacting_region_gc.wat"
    run("v71-bytecode", "examples/sprache_v71_compacting_region_gc.keim", "--binary-out", str(bout))
    run("v71-wasm", str(bout), "--out", str(wat))
    text = wat.read_text(encoding="utf-8")
    required = [
        "$gc_compact_collect",
        "$gc_evacuate_object",
        "$gc_forwarding_ptr",
        "$gc_set_forwarding_ptr",
        "$gc_rewrite_value",
        "$gc_update_roots",
        "$gc_update_object_edges",
        "$region_begin",
        "$region_alloc",
        "$region_checkpoint",
        "$region_reset",
        "$region_end",
        "$region_escape_promote",
        "$gc_stats_compact",
        "$region_stats_escapes",
    ]
    for item in required:
        assert item in text, item
    assert "unreachable" not in text


def test_run_bin_build_and_test() -> None:
    bout = ROOT / "build" / "v71" / "run.kbc71b"
    run("v71-bytecode", "examples/sprache_v71_compacting_region_gc.keim", "--binary-out", str(bout))
    run("v71-run-bin", str(bout))
    test_payload = json.loads(run("v71-test", "examples/sprache_v71_compacting_region_gc.keim", "--json").stdout)
    assert test_payload["ok"]
    checks = test_payload["coverage"]["v71_compacting_region_gc_runtime"]
    assert all(checks.values()), checks
    build_payload = json_from_stdout(run("v71-build", "--cwd", ".", "--out", "build/v71_project").stdout)
    assert build_payload["ok"]
    assert (ROOT / "build" / "v71_project" / "app_compacting_region_gc_runtime.wat").exists()


def main() -> int:
    test_status_check_bytecode_binary()
    test_wat_compacting_region_gc()
    test_run_bin_build_and_test()
    print("[Keim v7.1] Compacting GC + Region Allocator Runtime Tests OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
