Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = "D:\keim_genesis_prototype_v4_3"
$Example = "$Root\examples\agenten_zweige_v78_1_gpu_aware"
$Dll = "$Root\driver\build\CC_OpenCl.dll"
$Package = "$Example\build\agenten_zweige_gpu_aware"

cd $Root

python -m keim core-test "$Example\src\main.keim"
python -m keim core-test "$Example\src\gpu_mass_bench.keim"

python -m keim gpu-driver-status --json
python -m keim gpu-driver-plan --json
python -m keim gpu-driver-demo --dll "$Dll" --out "$Example\build\gpu_driver" --json

python "$Example\scripts\gpu_mass_driver_demo.py" --repo-root "$Root" --dll "$Dll" --out "$Example\gpu_reports" --count 100000

python -m keim exe-pack "$Example\src\main.keim" --out "$Package" --name agenten_zweige_gpu_aware --gpu-driver "$Dll"
python -m keim exe-verify "$Package" --json
python -m keim exe-run "$Package" --json

python "$Package\runtime\gpu\gpu_smoke.py" --json
