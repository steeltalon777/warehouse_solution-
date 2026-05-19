# ADR-0009: FFI Strategy

## Status
Proposed

## Date
2026-05-16

## Context

`Warehouse_client_core` must be callable from:
- **Kotlin** (WarehouseMobile, Android)
- **C#** (WarehouseDesktop, WPF)

Rust FFI options:

| Option | Kotlin | C# | Notes |
|---|---|---|---|
| **UniFFI** | ✅ Native (`.kt` generation) | ⚠️ Via C ABI or experimental C# export | Mature for Kotlin; C# path less proven |
| **C ABI (`extern "C"`)** | ✅ Via JNI wrapper | ✅ Via P/Invoke | Manual bindings, no codegen |
| **CBindgen + manual** | ✅ Via JNI | ✅ Via P/Invoke | Full control, more boilerplate |

## Decision

**Primary: UniFFI for Kotlin. Secondary: C ABI/PInvoke for C#.**

- Android Kotlin bindings use UniFFI with `.udl` definitions in `warehouse_ffi/src/`.
- WPF C# bindings use a C ABI wrapper exported from `warehouse_ffi`. The C exports are thin wrappers that convert Rust types to C-compatible flat structs and error envelopes.
- If UniFFI matures its C# export path, migrate C# from manual PInvoke to UniFFI.

### FFI boundary rules

1. **No borrowed references** across FFI — all arguments are owned or `Arc`.
2. **No Rust generics** in exported types.
3. **No `Result` type** in signatures — use `CoreErrorDto` output parameter.
4. **All strings** are UTF-8 C strings (`*const c_char`), freed by an explicit `core_free_string()`.
5. **All complex returns** are opaque handle IDs, with explicit `core_free_*()` destructors.
6. **Async** is handled by the host platform (Kotlin coroutines / C# `Task`). Rust synchronous methods run on a blocking threadpool. Long-running sync operations expose progress through a polling handle or callback.

### Error envelope

```c
typedef struct {
    int32_t code;           // 0=success, >0 = error code
    char* message;          // UTF-8, nullable
    char* details;          // UTF-8, nullable, free with core_free_string
} CoreErrorDto;
```

### Build outputs (Level 6)

| Target | Output |
|---|---|
| `aarch64-linux-android` | `libwarehouse_core.so` |
| `x86_64-linux-android` | `libwarehouse_core.so` (emulator) |
| `x86_64-pc-windows-msvc` | `warehouse_core.dll` |
| `x86_64-pc-windows-msvc` | `warehouse_core.lib` (C# PInvoke) |

## Consequences

- Two binding paths to maintain until UniFFI C# matures.
- UniFFI Kotlin bindings are nearly zero-boilerplate for simple methods.
- C# PInvoke requires manual `[DllImport]` declarations, tested by a C# smoke project.
- Handle/memory ownership model must be strictly documented and tested.

## Confidence
**High** for UniFFI Kotlin (proven in production). **Medium** for C# PInvoke (manual, needs dedicated testing).
