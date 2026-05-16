from __future__ import annotations

from pathlib import Path
import json
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from keim.native_vm import NativeNumericVm, default_native_library


def python_agent_kernel(n: int, rounds: int) -> float:
    x = [i % 256 for i in range(n)]
    y = [(i // 256) % 256 for i in range(n)]
    energy = [1.0 for _ in range(n)]
    alive = [True for _ in range(n)]
    t0 = time.perf_counter()
    for _ in range(rounds):
        for i in range(n):
            if alive[i]:
                x[i] = (x[i] + 1) % 256
                y[i] = (y[i] - 1) % 256
                energy[i] = max(0.0, min(1.0, energy[i] - 0.01))
        for i in range(n):
            if alive[i] and energy[i] > 0.5:
                energy[i] = max(0.0, min(1.0, energy[i] + 0.02))
    dt = time.perf_counter() - t0
    return (n * rounds) / max(dt, 1e-9)


def native_agent_kernel(vm: NativeNumericVm, n: int, rounds: int) -> float:
    with vm.agent_store(n, 256, 256) as agents:
        agents.import_state(
            [i % 256 for i in range(n)],
            [(i // 256) % 256 for i in range(n)],
            [1.0 for _ in range(n)],
            [True for _ in range(n)],
        )
        ops = [
            (NativeNumericVm.OP_AGENT_X_ADD_WRAP, 1, 0, 0.0),
            (NativeNumericVm.OP_AGENT_Y_ADD_WRAP, 1, 1, 0.0),
            (NativeNumericVm.OP_AGENT_ENERGY_ADD_CLAMP, 0, 0, -0.01),
            (NativeNumericVm.OP_AGENT_ALIVE_MASK_GT, 0, 0, 0.5),
            (NativeNumericVm.OP_AGENT_APPLY_MASK_ENERGY, 0, 0, 0.02),
        ]
        t0 = time.perf_counter()
        for _ in range(rounds):
            agents.run(ops)
        dt = time.perf_counter() - t0
    return (n * rounds) / max(dt, 1e-9)


def main() -> int:
    lib = default_native_library()
    if not lib.exists():
        subprocess.check_call([sys.executable, str(ROOT / "scripts" / "build_native_vm.py")], cwd=ROOT)
    vm = NativeNumericVm(lib)

    sizes = [1024, 4096, 16384]
    rounds = 80
    rows = []
    for n in sizes:
        py_rates = [python_agent_kernel(n, rounds) for _ in range(3)]
        native_rates = [native_agent_kernel(vm, n, rounds) for _ in range(3)]
        rows.append({
            "agents": n,
            "rounds": rounds,
            "python_updates_per_s": statistics.median(py_rates),
            "native_updates_per_s": statistics.median(native_rates),
            "speedup": statistics.median(native_rates) / max(statistics.median(py_rates), 1e-9),
        })

    out = ROOT / "build" / "benchmarks"
    out.mkdir(parents=True, exist_ok=True)
    path = out / "v41_native_agent_throughput.json"
    path.write_text(json.dumps({"version": vm.info().version, "rows": rows}, indent=2), encoding="utf-8")
    for row in rows:
        print(
            f"N={row['agents']:>6} python={row['python_updates_per_s']:>12.0f}/s "
            f"native={row['native_updates_per_s']:>12.0f}/s speedup={row['speedup']:.2f}x"
        )
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
