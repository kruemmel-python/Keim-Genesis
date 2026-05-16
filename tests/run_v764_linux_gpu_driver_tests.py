from __future__ import annotations

import json
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = [sys.executable, "-S"]


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(PY + ["-m", "keim", *args], cwd=ROOT, text=True, capture_output=True, check=True)


def test_default_driver_prefers_platform_artifact() -> None:
    res = run("gpu-driver-status", "--json")
    payload = json.loads(res.stdout)
    assert payload["version"] == "7.6.4"
    dll = payload["driver"]["dll"].replace("\\", "/")
    if platform.system().lower() == "linux":
        assert dll.endswith("driver/build/libCC_OpenCL.so"), dll
    elif platform.system().lower() == "windows":
        assert dll.endswith("driver/build/CC_OpenCl.dll") or dll.endswith("driver/build/CC_OpenCL.dll"), dll
    assert payload["driver"]["exists"] is True
    assert not payload["driver"]["core_missing"], payload["driver"]["core_missing"]
    assert "fused_diffusion" in payload["driver"]["kernels_available"]


def test_explicit_linux_so_symbol_plan() -> None:
    so = ROOT / "driver" / "build" / "libCC_OpenCL.so"
    assert so.exists(), "Linux driver artifact libCC_OpenCL.so fehlt im Paket"
    res = run("gpu-driver-plan", "--dll", str(so), "--json")
    payload = json.loads(res.stdout)
    assert payload["driver"]["exists"] is True
    assert payload["driver"]["ready_for_planned_dispatch"] is True
    assert any(r["driver_symbol"] == "execute_fused_diffusion_on_gpu" and r["available"] for r in payload["dispatch_rules"])


def test_demo_with_linux_so_is_robust() -> None:
    so = ROOT / "driver" / "build" / "libCC_OpenCL.so"
    out = ROOT / "build" / "v764_linux_driver_test"
    res = run("gpu-driver-demo", "--dll", str(so), "--out", str(out), "--json", "--size", "64")
    payload = json.loads(res.stdout)
    assert payload["ok"] is True
    assert payload["profiles"]
    assert payload["profiles"][0]["ok"] is True
    assert (out / "gpu_driver_report.json").exists()


def main() -> int:
    test_default_driver_prefers_platform_artifact()
    test_explicit_linux_so_symbol_plan()
    test_demo_with_linux_so_is_robust()
    print("[Keim v7.6.4] Linux/Cross-Platform GPU Driver Tests OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
