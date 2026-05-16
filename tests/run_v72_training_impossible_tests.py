from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = [sys.executable, "-S"]


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(PY + ["-m", "keim", *args], cwd=ROOT, text=True, capture_output=True, check=True, timeout=60)


def test_training_headless() -> None:
    out = ROOT / "build" / "v72_training_test"
    res = run("training-impossible", "--steps", "32", "--out", str(out), "--json")
    payload = json.loads(res.stdout)
    assert payload["ok"] is True
    assert payload["steps"] == 32
    assert payload["best_score"] > 0
    for key in ["metrics", "bytecode", "native_plan", "replay", "dashboard", "report"]:
        p = Path(payload["artifacts"][key])
        assert p.exists(), f"missing artifact {key}: {p}"
    bc = json.loads(Path(payload["artifacts"]["bytecode"]).read_text(encoding="utf-8"))
    assert bc["format"] == "keim-training-native-policy-bytecode"
    assert bc["version"] == 720
    assert "sha256" in bc
    assert "optimizer" in bc
    html = Path(payload["artifacts"]["dashboard"]).read_text(encoding="utf-8")
    assert "selbststeuernde Simulation" in html
    native = Path(payload["artifacts"]["native_plan"]).read_text(encoding="utf-8")
    assert "keim_training_policy_score" in native


def test_training_project_policy_still_valid_keim() -> None:
    run("v71-check", "examples/training_impossible_self_optimizing_sim/src/policy.keim")


def main() -> int:
    test_training_headless()
    test_training_project_policy_still_valid_keim()
    print("[Keim v7.2] Training Impossible Project Tests OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
