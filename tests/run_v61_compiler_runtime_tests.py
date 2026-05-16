from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = [sys.executable, "-S"]


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(PY + ["-m", "keim", *args], cwd=ROOT, text=True, capture_output=True, check=True)


def main() -> int:
    bc = run("core-bytecode", "examples/sprache_v61_compiler_runtime.keim", "--json")
    payload = json.loads(bc.stdout)
    assert payload["format"] == "keim-independent-bytecode"
    assert payload["version"] >= 610
    assert "EVAL" not in bc.stdout
    assert "DECLARE_SLOT" in bc.stdout
    assert "LOAD_SLOT" in bc.stdout

    replay = ROOT / "build" / "v61_test_replay.json"
    if replay.exists():
        replay.unlink()
    run("core-run", "examples/sprache_v61_compiler_runtime.keim", "--record", str(replay))
    assert replay.exists(), "Replay-Datei wurde nicht erzeugt"
    rp = json.loads(replay.read_text(encoding="utf-8"))
    assert rp["format"] == "keim-replay-v1"
    assert rp["events"], "Replay enthält keine Events"

    snap = ROOT / "build" / "v61_snapshot.json"
    assert snap.exists(), "Snapshot wurde nicht erzeugt"
    sp = json.loads(snap.read_text(encoding="utf-8"))
    assert sp["format"] == "keim-snapshot-v1"

    tests = run("core-test", "examples/sprache_v61_compiler_runtime.keim")
    assert "Tests OK" in tests.stdout
    replay_info = run("core-replay", str(replay))
    assert "Events:" in replay_info.stdout
    print("[Keim v6.1/v6.2] Compiler Runtime Tests OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
