# Keim Genesis Prototype v4.1

## Native Bridge & C++ Hotspot

- Native VM auf ABI-Version `410` gehoben.
- `native/keim_vm_native.cpp` enthält jetzt nicht nur Einzelkernel, sondern:
  - flaches Agentenlayout als `KeimAgentSoA`
  - `x`, `y`, `energy`, `class_id`, `alive`, `scratch_mask` als getrennte Arrays
  - C-ABI für Create/Resize/Import/Export/Destroy
  - C++-Opcode-Dispatcher `keim_run_agent_program`
  - numerischen Dispatcher `keim_run_numeric_program`
- Neue native Agent-Ops:
  - `KEIM_OP_AGENT_X_ADD_WRAP`
  - `KEIM_OP_AGENT_Y_ADD_WRAP`
  - `KEIM_OP_AGENT_ENERGY_ADD_CLAMP`
  - `KEIM_OP_AGENT_ALIVE_MASK_GT`
  - `KEIM_OP_AGENT_APPLY_MASK_ENERGY`

## system/sim Batteries auf Native-Ebene

- Native `sim.mathe`-Kerne:
  - `keim_noise2`
  - `keim_noise2_array`
  - `keim_vec2_add`
  - `keim_astar_grid`
- Bestehende Python-Standardbibliothek bleibt Referenzsemantik.
- Native Kerne sind über `keim.native_vm.NativeNumericVm` direkt aufrufbar.

## JIT-Haken

- Neue Handle-basierte JIT-ABI:
  - `keim_jit_compile_affine2`
  - `keim_jit_execute_affine2`
  - `keim_jit_destroy`
- Aktueller Lowering-Typ: `affine2_clamp`.
- Die ABI ist absichtlich handle-basiert, damit später LLVM, Cranelift, DynASM oder ein eigener Maschinen-Code-Emitter darunter gelegt werden kann, ohne Python-/Keim-API zu brechen.

## GPU-Residenz ohne Treibereinbettung

- Neuer optionaler externer GPU-Treiberloader:
  - `keim_gpu_driver_load`
  - `keim_gpu_driver_ready`
  - `keim_gpu_shadow_init`
  - `keim_gpu_shadow_cycle`
  - `keim_gpu_upload_multifield`
  - `keim_gpu_driver_unload`
- Der C-/OpenCL-Treiber wird nicht benötigt und nicht statisch gelinkt.
- Keim lädt Symbole per `LoadLibrary`/`dlopen`, wenn der Nutzer den Treiberpfad bereitstellt.
- Unterstützte Symbolpfade:
  - Somnia Shadow: `shadow_init`, `shadow_cycle`
  - SymBio MultiField: `subqg_set_multifield_state`

## Kernel ABI v1.2

- `compile_kernel_abi` meldet jetzt:
  - `format_version: "1.2"`
  - SoA-Agentenlayout
  - `kernel_bundles_v12`
  - Parallelisierbarkeitsmarker pro Opcode
  - JIT-Marker für `FIELD_COMPUTE`
  - externe Treiber-ABI-Spezifikation

## Qualität und Validierung

- Neuer Test:
  - `tests/run_v41_native_tests.py`
- Erweiterte Haupttests:
  - Kernel-ABI-v1.2-Marker
- Neuer Benchmark:
  - `scripts/benchmark_v41_native.py`
  - schreibt nach `build/benchmarks/v41_native_agent_throughput.json`

## Ehrliche Grenze

Die vollständige Sprache läuft weiterhin über die deterministische Python-Referenzsemantik. v4.1 implementiert jedoch echte native Hotspot-Ausführung mit eigenem Speicherlayout und Dispatcher. Die GPU-Residenz ist als reale C-ABI-Treiberbrücke manifestiert; die konkrete VRAM-Ausführung hängt vom extern bereitgestellten Treiber ab.
