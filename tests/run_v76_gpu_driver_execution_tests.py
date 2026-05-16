from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = [sys.executable, "-S"]


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(PY + ["-m", "keim", *args], cwd=ROOT, text=True, capture_output=True, check=True)


def test_status_detects_cc_opencl() -> None:
    res = run("gpu-driver-status", "--json")
    payload = json.loads(res.stdout)
    assert payload["version"] == "7.6.4"
    driver = payload["driver"]
    assert driver["exists"], "driver/build/CC_OpenCl.dll oder driver/build/libCC_OpenCL.so muss vorhanden sein"
    assert not driver["core_missing"], driver["core_missing"]
    assert "fused_diffusion" in driver["kernels_available"]
    assert "energy_gated_scheduler" in driver["kernels_available"]
    assert driver["ready_for_planned_dispatch"] is True


def test_plan_contains_dispatch_rules() -> None:
    res = run("gpu-driver-plan", "--json")
    payload = json.loads(res.stdout)
    assert payload["format"] == "keim-gpu-driver-execution-plan-v1"
    rules = payload["dispatch_rules"]
    assert len(rules) >= 6
    assert any(r["driver_symbol"] == "execute_fused_diffusion_on_gpu" for r in rules)
    assert any(r["driver_symbol"] == "subqg_simulation_step_host_fields" for r in rules)


def test_demo_generates_reports() -> None:
    out = ROOT / "build" / "v76_gpu_driver_test"
    res = run("gpu-driver-demo", "--out", str(out), "--json", "--force-cpu", "--size", "128")
    payload = json.loads(res.stdout)
    assert payload["ok"] is True
    assert payload["profiles"]
    assert (out / "gpu_driver_report.json").exists()
    assert (out / "gpu_execution_plan.json").exists()


def test_gpu_backend_integrates_with_runtime() -> None:
    stats = ROOT / "build" / "v76_gpu_runtime_stats.json"
    run("run", "examples/minimal_v12.keim", "--rounds", "2", "--backend", "gpu", "--quiet", "--stats-out", str(stats))
    payload = json.loads(stats.read_text(encoding="utf-8"))
    assert payload["backend"] == "gpu"
    assert payload["driver"]["ready_for_planned_dispatch"] is True
    assert payload["metrics"][0]["gpu:driver_backend_active"] == 1


def main() -> int:
    test_status_detects_cc_opencl()
    test_plan_contains_dispatch_rules()
    test_demo_generates_reports()
    test_gpu_backend_integrates_with_runtime()
    print("[Keim v7.6] GPU Driver Execution Tests OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
