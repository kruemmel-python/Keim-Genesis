#!/usr/bin/env sh
python -m keim gpu-driver-status --json
python -m keim gpu-driver-demo --out build/gpu_driver_v76 --json --force-cpu
python -m keim run examples/minimal_v12.keim --backend gpu --stats-out build/gpu_driver_v76/runtime_stats.json --quiet
