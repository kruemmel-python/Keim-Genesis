// Keim Native VM v6.2
// VRAM-ready SoA state, bytecode dispatcher, math battery, JIT hooks,
// and optional external GPU driver bridge.  The external driver is loaded
// at runtime and is intentionally not embedded in Keim's ZIP.
//
// Build Linux/macOS: c++ -O3 -std=c++20 -shared -fPIC keim_vm_native.cpp -o libkeim_vm_native.so
// Build Windows:    cl /O2 /std:c++20 /LD keim_vm_native.cpp /Fe:keim_vm_native.dll

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <vector>
#include <queue>
#include <limits>
#include <unordered_map>
#include <memory>
#include <string>

#if defined(_WIN32)
  #ifndef NOMINMAX
    #define NOMINMAX
  #endif
  #include <windows.h>
#else
  #include <dlfcn.h>
#endif

extern "C" {

enum KeimNativeOp : uint32_t {
    KEIM_OP_FIELD_ADD_CLAMP = 1,
    KEIM_OP_MEMORY_ADD_CLAMP = 2,
    KEIM_OP_MASK_GT = 3,
    KEIM_OP_MASK_LT = 4,
    KEIM_OP_APPLY_MASKED_ADD_CLAMP = 5,

    // v4.1 SoA/Agent dispatcher ops.
    KEIM_OP_AGENT_X_ADD_WRAP = 16,
    KEIM_OP_AGENT_Y_ADD_WRAP = 17,
    KEIM_OP_AGENT_ENERGY_ADD_CLAMP = 18,
    KEIM_OP_AGENT_ALIVE_MASK_GT = 19,
    KEIM_OP_AGENT_APPLY_MASK_ENERGY = 20,
    KEIM_OP_HALT = 255
};

struct KeimNativeStatus {
    uint32_t ok;
    uint32_t pc;
    char message[128];
};

struct KeimAgentSoA {
    uint32_t capacity;
    uint32_t count;
    int32_t width;
    int32_t height;
    int32_t* x;
    int32_t* y;
    float* energy;
    uint32_t* class_id;
    uint8_t* alive;
    uint8_t* scratch_mask;
};

struct KeimNativeProgramView {
    const uint32_t* words; // 4 words per op: op,a,b,imm_bits
    uint32_t op_count;
};

struct KeimJitPlan {
    uint32_t kind; // 1 = affine2 clamp: a*x+b*y+c
    float a;
    float b;
    float c;
};

struct KeimGpuDriver {
#if defined(_WIN32)
    HMODULE handle;
#else
    void* handle;
#endif
    int (*shadow_init)(int,int,int,int,int,int);
    int (*shadow_cycle)(int,int,int);
    int (*subqg_set_multifield_state)(int,int,const float*,const float*,const float*,const float*,const float*,const float*,const float*,const float*);
    int loaded;
};

static inline float clamp01(float v) {
    return v < 0.0f ? 0.0f : (v > 1.0f ? 1.0f : v);
}

static inline int32_t wrap_i32(int32_t v, int32_t limit) {
    if (limit <= 0) return 0;
    v %= limit;
    if (v < 0) v += limit;
    return v;
}

static void set_status(KeimNativeStatus* st, uint32_t ok, uint32_t pc, const char* msg) {
    if (!st) return;
    st->ok = ok;
    st->pc = pc;
    std::snprintf(st->message, sizeof(st->message), "%s", msg ? msg : "");
}

static uint32_t float_bits(float v) {
    uint32_t u;
    std::memcpy(&u, &v, sizeof(float));
    return u;
}

static float bits_float(uint32_t u) {
    float f;
    std::memcpy(&f, &u, sizeof(float));
    return f;
}

uint32_t keim_native_version() { return 620; }

// Direkt nutzbarer Kernel: field[i] = clamp01(field[i] + delta)
uint32_t keim_field_add_clamp(float* field, uint32_t n, float delta) {
    if (!field) return 0;
    for (uint32_t i = 0; i < n; ++i) field[i] = clamp01(field[i] + delta);
    return 1;
}

// Maskierter Kernel: wenn mask[i] != 0, field[i] = clamp01(field[i] + delta)
uint32_t keim_field_add_clamp_masked(float* field, const uint8_t* mask, uint32_t n, float delta) {
    if (!field || !mask) return 0;
    for (uint32_t i = 0; i < n; ++i) if (mask[i]) field[i] = clamp01(field[i] + delta);
    return 1;
}

// Numerisches Register-VM-Format:
// program ist ein Array aus 4 x uint32 pro Op: [op, a, b, imm_bits].
// a/b sind Indizes in fields[], memories[] oder masks[] je nach op.
uint32_t keim_run_numeric_program(
    const uint32_t* program,
    uint32_t op_count,
    float** fields,
    uint32_t* field_lengths,
    uint32_t field_count,
    float* memories,
    uint32_t memory_count,
    uint8_t** masks,
    uint32_t mask_count,
    KeimNativeStatus* status
) {
    if (!program) { set_status(status, 0, 0, "program=null"); return 0; }
    for (uint32_t pc = 0; pc < op_count; ++pc) {
        const uint32_t op = program[pc * 4 + 0];
        const uint32_t a = program[pc * 4 + 1];
        const uint32_t b = program[pc * 4 + 2];
        const float imm = bits_float(program[pc * 4 + 3]);

        switch (op) {
            case KEIM_OP_FIELD_ADD_CLAMP:
                if (a >= field_count || !fields[a]) { set_status(status, 0, pc, "bad field"); return 0; }
                for (uint32_t i = 0; i < field_lengths[a]; ++i) fields[a][i] = clamp01(fields[a][i] + imm);
                break;
            case KEIM_OP_MEMORY_ADD_CLAMP:
                if (a >= memory_count || !memories) { set_status(status, 0, pc, "bad memory"); return 0; }
                memories[a] = clamp01(memories[a] + imm);
                break;
            case KEIM_OP_MASK_GT:
            case KEIM_OP_MASK_LT:
                if (a >= field_count || b >= mask_count || !fields[a] || !masks[b]) { set_status(status, 0, pc, "bad mask args"); return 0; }
                for (uint32_t i = 0; i < field_lengths[a]; ++i) {
                    masks[b][i] = (op == KEIM_OP_MASK_GT) ? (fields[a][i] > imm) : (fields[a][i] < imm);
                }
                break;
            case KEIM_OP_APPLY_MASKED_ADD_CLAMP:
                if (a >= field_count || b >= mask_count || !fields[a] || !masks[b]) { set_status(status, 0, pc, "bad masked add args"); return 0; }
                for (uint32_t i = 0; i < field_lengths[a]; ++i) if (masks[b][i]) fields[a][i] = clamp01(fields[a][i] + imm);
                break;
            case KEIM_OP_HALT:
                set_status(status, 1, pc, "halt");
                return 1;
            default:
                set_status(status, 0, pc, "unknown opcode");
                return 0;
        }
    }
    set_status(status, 1, op_count, "ok");
    return 1;
}

// v4.0: Ganzzahl-Hotspot für Adressarithmetik / integer fields.
uint32_t keim_int_field_add(int32_t* field, uint32_t n, int32_t delta, int32_t min_value, int32_t max_value) {
    if (!field) return 0;
    for (uint32_t i = 0; i < n; ++i) {
        int64_t v = static_cast<int64_t>(field[i]) + static_cast<int64_t>(delta);
        if (v < min_value) v = min_value;
        if (v > max_value) v = max_value;
        field[i] = static_cast<int32_t>(v);
    }
    return 1;
}

// v4.0: kleiner JIT-artiger Ausdruckskern: out[i] = clamp01(a*x[i] + b*y[i] + c)
uint32_t keim_affine2_clamp(const float* x, const float* y, float* out, uint32_t n, float a, float b, float c) {
    if (!x || !y || !out) return 0;
    for (uint32_t i = 0; i < n; ++i) out[i] = clamp01(a * x[i] + b * y[i] + c);
    return 1;
}

// ---------------- v4.1 Agent SoA ----------------

KeimAgentSoA* keim_agent_soa_create(uint32_t capacity, int32_t width, int32_t height) {
    KeimAgentSoA* s = new (std::nothrow) KeimAgentSoA{};
    if (!s) return nullptr;
    s->capacity = capacity;
    s->count = capacity;
    s->width = width;
    s->height = height;
    s->x = new (std::nothrow) int32_t[capacity]();
    s->y = new (std::nothrow) int32_t[capacity]();
    s->energy = new (std::nothrow) float[capacity]();
    s->class_id = new (std::nothrow) uint32_t[capacity]();
    s->alive = new (std::nothrow) uint8_t[capacity]();
    s->scratch_mask = new (std::nothrow) uint8_t[capacity]();
    if (!s->x || !s->y || !s->energy || !s->class_id || !s->alive || !s->scratch_mask) {
        delete[] s->x; delete[] s->y; delete[] s->energy; delete[] s->class_id; delete[] s->alive; delete[] s->scratch_mask; delete s;
        return nullptr;
    }
    for (uint32_t i = 0; i < capacity; ++i) {
        s->x[i] = width > 0 ? static_cast<int32_t>(i % static_cast<uint32_t>(width)) : 0;
        s->y[i] = (width > 0 && height > 0) ? static_cast<int32_t>((i / static_cast<uint32_t>(width)) % static_cast<uint32_t>(height)) : 0;
        s->energy[i] = 1.0f;
        s->alive[i] = 1;
    }
    return s;
}

void keim_agent_soa_destroy(KeimAgentSoA* s) {
    if (!s) return;
    delete[] s->x; delete[] s->y; delete[] s->energy; delete[] s->class_id; delete[] s->alive; delete[] s->scratch_mask;
    delete s;
}

uint32_t keim_agent_soa_resize(KeimAgentSoA* s, uint32_t count) {
    if (!s || count > s->capacity) return 0;
    uint32_t old = s->count;
    s->count = count;
    for (uint32_t i = old; i < count; ++i) {
        s->x[i] = s->width > 0 ? static_cast<int32_t>(i % static_cast<uint32_t>(s->width)) : 0;
        s->y[i] = (s->width > 0 && s->height > 0) ? static_cast<int32_t>((i / static_cast<uint32_t>(s->width)) % static_cast<uint32_t>(s->height)) : 0;
        s->energy[i] = 1.0f;
        s->alive[i] = 1;
    }
    return 1;
}

uint32_t keim_agent_soa_export(const KeimAgentSoA* s, int32_t* x, int32_t* y, float* energy, uint8_t* alive, uint32_t max_count) {
    if (!s) return 0;
    uint32_t n = (std::min)(s->count, max_count);
    for (uint32_t i = 0; i < n; ++i) {
        if (x) x[i] = s->x[i];
        if (y) y[i] = s->y[i];
        if (energy) energy[i] = s->energy[i];
        if (alive) alive[i] = s->alive[i];
    }
    return n;
}

uint32_t keim_agent_soa_import(KeimAgentSoA* s, const int32_t* x, const int32_t* y, const float* energy, const uint8_t* alive, uint32_t count) {
    if (!s || count > s->capacity) return 0;
    s->count = count;
    for (uint32_t i = 0; i < count; ++i) {
        if (x) s->x[i] = wrap_i32(x[i], s->width);
        if (y) s->y[i] = wrap_i32(y[i], s->height);
        if (energy) s->energy[i] = clamp01(energy[i]);
        if (alive) s->alive[i] = alive[i] ? 1 : 0;
    }
    return 1;
}

uint32_t keim_run_agent_program(KeimAgentSoA* s, const uint32_t* program, uint32_t op_count, KeimNativeStatus* status) {
    if (!s) { set_status(status, 0, 0, "agent_soa=null"); return 0; }
    if (!program) { set_status(status, 0, 0, "program=null"); return 0; }

    for (uint32_t pc = 0; pc < op_count; ++pc) {
        const uint32_t op = program[pc * 4 + 0];
        const uint32_t a = program[pc * 4 + 1];
        const uint32_t b = program[pc * 4 + 2];
        const float imm = bits_float(program[pc * 4 + 3]);

        switch (op) {
            case KEIM_OP_AGENT_X_ADD_WRAP: {
                int32_t delta = static_cast<int32_t>(a);
                if (b) delta = -delta;
                for (uint32_t i = 0; i < s->count; ++i) if (s->alive[i]) s->x[i] = wrap_i32(s->x[i] + delta, s->width);
                break;
            }
            case KEIM_OP_AGENT_Y_ADD_WRAP: {
                int32_t delta = static_cast<int32_t>(a);
                if (b) delta = -delta;
                for (uint32_t i = 0; i < s->count; ++i) if (s->alive[i]) s->y[i] = wrap_i32(s->y[i] + delta, s->height);
                break;
            }
            case KEIM_OP_AGENT_ENERGY_ADD_CLAMP:
                for (uint32_t i = 0; i < s->count; ++i) if (s->alive[i]) s->energy[i] = clamp01(s->energy[i] + imm);
                break;
            case KEIM_OP_AGENT_ALIVE_MASK_GT:
                for (uint32_t i = 0; i < s->count; ++i) s->scratch_mask[i] = (s->alive[i] && s->energy[i] > imm) ? 1 : 0;
                break;
            case KEIM_OP_AGENT_APPLY_MASK_ENERGY:
                for (uint32_t i = 0; i < s->count; ++i) if (s->scratch_mask[i]) s->energy[i] = clamp01(s->energy[i] + imm);
                break;
            case KEIM_OP_HALT:
                set_status(status, 1, pc, "halt");
                return 1;
            default:
                set_status(status, 0, pc, "unknown agent opcode");
                return 0;
        }
    }
    set_status(status, 1, op_count, "ok");
    return 1;
}

// ---------------- sim.mathe native battery ----------------

static inline uint32_t hash_u32(uint32_t x) {
    x ^= x >> 16; x *= 0x7feb352du; x ^= x >> 15; x *= 0x846ca68bu; x ^= x >> 16;
    return x;
}

float keim_noise2(float x, float y, uint32_t seed) {
    int32_t xi = static_cast<int32_t>(std::floor(x));
    int32_t yi = static_cast<int32_t>(std::floor(y));
    float xf = x - std::floor(x);
    float yf = y - std::floor(y);
    auto rnd = [&](int32_t ix, int32_t iy) {
        uint32_t h = hash_u32(static_cast<uint32_t>(ix) * 374761393u ^ static_cast<uint32_t>(iy) * 668265263u ^ seed);
        return (h & 0x00ffffffu) / 16777215.0f;
    };
    auto smooth = [](float t) { return t * t * (3.0f - 2.0f * t); };
    float a = rnd(xi, yi), b = rnd(xi+1, yi), c = rnd(xi, yi+1), d = rnd(xi+1, yi+1);
    float u = smooth(xf), v = smooth(yf);
    float ab = a + (b - a) * u;
    float cd = c + (d - c) * u;
    return cd + (ab - cd) * (1.0f - v);
}

uint32_t keim_noise2_array(const float* x, const float* y, float* out, uint32_t n, uint32_t seed) {
    if (!x || !y || !out) return 0;
    for (uint32_t i = 0; i < n; ++i) out[i] = keim_noise2(x[i], y[i], seed);
    return 1;
}

uint32_t keim_vec2_add(const float* ax, const float* ay, const float* bx, const float* by, float* ox, float* oy, uint32_t n) {
    if (!ax || !ay || !bx || !by || !ox || !oy) return 0;
    for (uint32_t i = 0; i < n; ++i) { ox[i] = ax[i] + bx[i]; oy[i] = ay[i] + by[i]; }
    return 1;
}

uint32_t keim_astar_grid(
    int32_t width,
    int32_t height,
    int32_t sx,
    int32_t sy,
    int32_t gx,
    int32_t gy,
    const float* cost,
    int32_t* out_x,
    int32_t* out_y,
    uint32_t max_path
) {
    if (width <= 0 || height <= 0 || !out_x || !out_y || max_path == 0) return 0;
    auto inside = [&](int32_t x, int32_t y){ return x >= 0 && y >= 0 && x < width && y < height; };
    if (!inside(sx, sy) || !inside(gx, gy)) return 0;
    const int32_t cells = width * height;
    const int32_t start = sy * width + sx;
    const int32_t goal = gy * width + gx;
    std::vector<float> dist(cells, std::numeric_limits<float>::infinity());
    std::vector<int32_t> prev(cells, -1);
    struct Node { float f; int32_t idx; };
    struct Cmp { bool operator()(const Node& a, const Node& b) const { return a.f > b.f; } };
    std::priority_queue<Node, std::vector<Node>, Cmp> pq;
    auto h = [&](int32_t idx){ int32_t x = idx % width, y = idx / width; return static_cast<float>(std::abs(x-gx) + std::abs(y-gy)); };
    dist[start] = 0.0f;
    pq.push({h(start), start});
    const int dx[4] = {1,-1,0,0};
    const int dy[4] = {0,0,1,-1};
    while (!pq.empty()) {
        Node cur = pq.top(); pq.pop();
        if (cur.idx == goal) break;
        int32_t cx = cur.idx % width, cy = cur.idx / width;
        for (int k=0; k<4; ++k) {
            int32_t nx = cx + dx[k], ny = cy + dy[k];
            if (!inside(nx, ny)) continue;
            int32_t ni = ny * width + nx;
            float step_cost = 1.0f + (cost ? (std::max)(0.0f, cost[ni]) : 0.0f);
            float nd = dist[cur.idx] + step_cost;
            if (nd < dist[ni]) {
                dist[ni] = nd; prev[ni] = cur.idx; pq.push({nd + h(ni), ni});
            }
        }
    }
    if (start != goal && prev[goal] < 0) return 0;
    std::vector<int32_t> rev;
    for (int32_t at = goal; at >= 0; at = prev[at]) {
        rev.push_back(at);
        if (at == start) break;
    }
    std::reverse(rev.begin(), rev.end());
    uint32_t n = static_cast<uint32_t>(std::min<size_t>(rev.size(), max_path));
    for (uint32_t i = 0; i < n; ++i) {
        out_x[i] = rev[i] % width;
        out_y[i] = rev[i] / width;
    }
    return n;
}

// ---------------- JIT ABI hook ----------------
// This is not a general machine-code emitter. It is a stable handle ABI for
// expression-specialized native kernels. The first implementation recognizes
// affine2 clamp plans and lets higher levels substitute a future LLVM/asm backend
// without changing the C ABI.

KeimJitPlan* keim_jit_compile_affine2(float a, float b, float c) {
    KeimJitPlan* p = new (std::nothrow) KeimJitPlan{};
    if (!p) return nullptr;
    p->kind = 1; p->a = a; p->b = b; p->c = c;
    return p;
}

void keim_jit_destroy(KeimJitPlan* p) {
    delete p;
}

uint32_t keim_jit_execute_affine2(const KeimJitPlan* p, const float* x, const float* y, float* out, uint32_t n) {
    if (!p || p->kind != 1) return 0;
    return keim_affine2_clamp(x, y, out, n, p->a, p->b, p->c);
}

// ---------------- Optional external GPU driver bridge ----------------
// The driver path is supplied by the embedding application/user. Keim only
// loads symbols if present; missing symbols degrade gracefully to "not ready".

static void* keim_sym_lookup(
#if defined(_WIN32)
    HMODULE h,
#else
    void* h,
#endif
    const char* name
) {
#if defined(_WIN32)
    return h ? reinterpret_cast<void*>(GetProcAddress(h, name)) : nullptr;
#else
    return h ? dlsym(h, name) : nullptr;
#endif
}

KeimGpuDriver* keim_gpu_driver_load(const char* path) {
    if (!path || !*path) return nullptr;
    KeimGpuDriver* d = new (std::nothrow) KeimGpuDriver{};
    if (!d) return nullptr;
#if defined(_WIN32)
    d->handle = LoadLibraryA(path);
#else
    d->handle = dlopen(path, RTLD_NOW | RTLD_LOCAL);
#endif
    if (!d->handle) { delete d; return nullptr; }
    d->shadow_init = reinterpret_cast<int(*)(int,int,int,int,int,int)>(keim_sym_lookup(d->handle, "shadow_init"));
    d->shadow_cycle = reinterpret_cast<int(*)(int,int,int)>(keim_sym_lookup(d->handle, "shadow_cycle"));
    d->subqg_set_multifield_state = reinterpret_cast<int(*)(int,int,const float*,const float*,const float*,const float*,const float*,const float*,const float*,const float*)>(keim_sym_lookup(d->handle, "subqg_set_multifield_state"));
    d->loaded = 1;
    return d;
}

void keim_gpu_driver_unload(KeimGpuDriver* d) {
    if (!d) return;
#if defined(_WIN32)
    if (d->handle) FreeLibrary(d->handle);
#else
    if (d->handle) dlclose(d->handle);
#endif
    delete d;
}

uint32_t keim_gpu_driver_ready(const KeimGpuDriver* d) {
    return (d && d->loaded) ? 1u : 0u;
}

uint32_t keim_gpu_shadow_init(KeimGpuDriver* d, int gpu_index, int cells, int channels, int neighbors, int dreams, int action_vector_len) {
    if (!d || !d->shadow_init) return 0;
    return d->shadow_init(gpu_index, cells, channels, neighbors, dreams, action_vector_len) == 0 ? 1u : 0u;
}

uint32_t keim_gpu_shadow_cycle(KeimGpuDriver* d, int gpu_index, int cycles, int mode) {
    if (!d || !d->shadow_cycle) return 0;
    return d->shadow_cycle(gpu_index, cycles, mode) == 0 ? 1u : 0u;
}

uint32_t keim_gpu_upload_multifield(
    KeimGpuDriver* d,
    int gpu_index,
    int cell_count,
    const float* energy,
    const float* pressure,
    const float* gravity,
    const float* magnetism,
    const float* temperature,
    const float* potential,
    const float* drift_x,
    const float* drift_y
) {
    if (!d || !d->subqg_set_multifield_state) return 0;
    return d->subqg_set_multifield_state(gpu_index, cell_count, energy, pressure, gravity, magnetism, temperature, potential, drift_x, drift_y) == 0 ? 1u : 0u;
}

// v4.4 ABI: GUI/Shader/FFI-Metadaten. Keine Fremd-DLL wird eingebettet.
// Host-Programme können damit prüfen, ob die Native-VM die v4.4-Hooks kennt.
uint32_t keim_abi_version_v44() {
    return 440u;
}

uint32_t keim_shader_bundle_supported(const char* backend_name) {
    if (!backend_name) return 0u;
    // Keim-Kern bleibt API-neutral: echte Vulkan/DirectX/OpenCL-Compiler werden extern geladen.
    // "external" bedeutet: Der vorhandene C/GPU-Treiber übernimmt Kompilierung/Dispatch.
    return (std::strcmp(backend_name, "external") == 0 ||
            std::strcmp(backend_name, "opencl") == 0 ||
            std::strcmp(backend_name, "vulkan") == 0) ? 1u : 0u;
}

uint32_t keim_gui_backend_supported(const char* backend_name) {
    if (!backend_name) return 0u;
    // "web" ist vollständig hostseitig implementiert; "sdl2"/"raylib" sind ABI-Erweiterungspunkte.
    return (std::strcmp(backend_name, "web") == 0 ||
            std::strcmp(backend_name, "sdl2") == 0 ||
            std::strcmp(backend_name, "raylib") == 0) ? 1u : 0u;
}


// v5.0 Sovereign Edition: optionale Host-Sinks ohne Link-Zwang.
typedef void (*keim_debug_event_sink_t)(const char* kind, const char* name, const char* payload);
typedef void (*keim_grafik_command_sink_t)(const char* command, const char* payload);
typedef void (*keim_audio_event_sink_t)(const char* command, const char* payload);
typedef uint32_t (*keim_permission_callback_t)(const char* permission);

static keim_debug_event_sink_t g_debug_sink = nullptr;
static keim_grafik_command_sink_t g_grafik_sink = nullptr;
static keim_audio_event_sink_t g_audio_sink = nullptr;
static keim_permission_callback_t g_permission_cb = nullptr;

uint32_t keim_abi_version_v50() { return 500u; }

void keim_set_debug_event_sink(keim_debug_event_sink_t sink) { g_debug_sink = sink; }
void keim_set_grafik_command_sink(keim_grafik_command_sink_t sink) { g_grafik_sink = sink; }
void keim_set_audio_event_sink(keim_audio_event_sink_t sink) { g_audio_sink = sink; }
void keim_set_permission_callback(keim_permission_callback_t cb) { g_permission_cb = cb; }

uint32_t keim_emit_debug_event(const char* kind, const char* name, const char* payload) {
    if (g_debug_sink) g_debug_sink(kind, name, payload);
    return 1u;
}

uint32_t keim_emit_grafik_command(const char* command, const char* payload) {
    if (g_grafik_sink) g_grafik_sink(command, payload);
    return 1u;
}

uint32_t keim_emit_audio_event(const char* command, const char* payload) {
    if (g_audio_sink) g_audio_sink(command, payload);
    return 1u;
}

uint32_t keim_check_permission(const char* permission) {
    return g_permission_cb ? g_permission_cb(permission) : 1u;
}


} // extern "C"


extern "C" const char* keim_v6_bytecode_entry() { return "keim-independent-bytecode"; }

extern "C" uint32_t keim_native_version_v61() { return 610u; }
extern "C" uint32_t keim_native_version_v62() { return 620u; }
extern "C" const char* keim_native_bytecode_format_v61() { return "keim-independent-bytecode:610:no-eval"; }

extern "C" uint32_t keim_native_version_v66() { return 660u; }
extern "C" const char* keim_native_bytecode_format_v66() { return "keim-linear-bytecode:kbc66b:sections:const-pool"; }
