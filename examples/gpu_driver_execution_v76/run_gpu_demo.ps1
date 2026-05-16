python -m keim gpu-driver-status --json
python -m keim gpu-driver-demo --dll driver/build/CC_OpenCl.dll --out build/gpu_driver_v76 --json
python -m keim run examples/minimal_v12.keim --backend gpu --dll driver/build/CC_OpenCl.dll --driver-smoke --stats-out build/gpu_driver_v76/runtime_stats.json
