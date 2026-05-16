from __future__ import annotations

import json
import subprocess
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = [sys.executable, "-S"]


def run(*args: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(PY + ["-m", "keim", *args], cwd=ROOT, text=True, capture_output=True, check=True, timeout=timeout)


def test_status_reports_v781_gpu_packager() -> None:
    res = run("exe-status", "--json")
    payload = json.loads(res.stdout)
    assert payload["version"] >= 781
    assert "gpu_aware_packaging" in payload["features"]
    assert payload["external_compiler_required"] is False


def test_gpu_aware_package_contains_drivers_and_manifests() -> None:
    out = ROOT / "build" / "v781_gpu_packager_test"
    if out.exists():
        shutil.rmtree(out)
    entry = ROOT / "examples" / "exe_runtime_packager_v78" / "main.keim"
    res = run("exe-pack", str(entry), "--out", str(out), "--name", "v781_gpu_packager_test", "--json")
    payload = json.loads(res.stdout)
    assert payload["ok"] is True
    assert (out / "runtime" / "gpu" / "gpu_driver_manifest.json").exists()
    assert (out / "runtime" / "gpu" / "gpu_driver_plan.json").exists()
    assert (out / "runtime" / "gpu" / "gpu_smoke.py").exists()
    assert (out / "GPU_README.txt").exists()
    assert (out / "run_gpu.bat").exists()
    assert (out / "run_gpu.ps1").exists()
    assert (out / "run_gpu.sh").exists()
    drivers = sorted(p.name for p in (out / "runtime" / "driver").glob("*"))
    assert "CC_OpenCl.dll" in drivers
    assert "libCC_OpenCL.so" in drivers
    manifest = json.loads((out / "app" / "manifest.kexe.json").read_text(encoding="utf-8"))
    assert manifest["version"] >= 781
    assert manifest["gpu"]["enabled"] is True
    assert manifest["gpu"]["driver_count"] if "driver_count" in manifest["gpu"] else len(manifest["gpu"]["drivers"]) >= 1


def test_verify_and_run_gpu_aware_package() -> None:
    out = ROOT / "build" / "v781_gpu_packager_test"
    verify = json.loads(run("exe-verify", str(out), "--json").stdout)
    assert verify["ok"] is True
    assert verify["gpu"]["enabled"] is True
    assert verify["gpu"]["ok"] is True
    assert verify["gpu"]["driver_count"] >= 1
    run_payload = json.loads(run("exe-run", str(out), "--json").stdout)
    assert run_payload["ok"] is True
    assert run_payload.get("value") == 42


def main() -> int:
    test_status_reports_v781_gpu_packager()
    test_gpu_aware_package_contains_drivers_and_manifests()
    test_verify_and_run_gpu_aware_package()
    print("[Keim v7.8.1+] GPU-aware Full EXE Runtime Packager Tests OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
