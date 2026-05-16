from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = [sys.executable, "-S"]


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(PY + ["-m", "keim", *args], cwd=ROOT, text=True, capture_output=True, check=True)


def test_status() -> None:
    payload = json.loads(run("exe-status", "--json").stdout)
    assert payload["version"] >= 780
    assert payload["external_compiler_required"] is False
    for feature in [
        "native_value_model", "heap", "strings", "lists", "maps", "records",
        "result_match", "function_calls", "module_table", "runtime_imports_io_gpu_web",
    ]:
        assert feature in payload["features"], feature


def test_pack_verify_run_zipapp() -> None:
    out = ROOT / "build" / "v78_tests" / "package"
    if out.exists():
        import shutil
        shutil.rmtree(out)
    res = run(
        "exe-pack",
        "examples/exe_runtime_packager_v78/main.keim",
        "--out", str(out),
        "--name", "keim_v78_test",
        "--target", "elf64-linux-x86_64",
        "--json",
    )
    package = json.loads(res.stdout)
    assert package["ok"] is True
    assert Path(package["manifest"]).exists()
    assert Path(package["zipapp"]).exists()
    assert Path(package["native_launcher"]).exists()

    verify = json.loads(run("exe-verify", str(out), "--json").stdout)
    assert verify["ok"] is True
    assert verify["has_runtime"] is True
    assert verify["has_zipapp"] is True
    assert verify["missing_features"] == []

    executed = json.loads(run("exe-run", str(out), "--json").stdout)
    assert executed["ok"] is True
    assert executed["value"] == 42

    zipapp = subprocess.run([sys.executable, str(out / "keim_v78_test.pyz")], cwd=ROOT, text=True, capture_output=True, check=True)
    assert "42" in zipapp.stdout


def main() -> int:
    test_status()
    test_pack_verify_run_zipapp()
    print("[Keim v7.8+] Full EXE Runtime Packager Tests OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
