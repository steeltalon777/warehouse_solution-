# ADR-0006: Mobile Bridge Strategy — Two-Implementation CoreHandle

## Status
Proposed

## Date
2026-05-16

## Context

`WarehouseMobile` is the Android client for the warehouse system. Per root AGENTS.md and WarehouseMobile AGENTS.md, the app must be "rebuilt around `Warehouse_client_core`" — the Rust offline-first runtime. However:

1. **Rust core is at Phase ~1-2 of 17** (per `Core_plan`). Domain DTOs, error types, and SQLite migrations exist, but there is no HTTP client, sync engine, operation draft workflow, or outbox. The facade `CoreHandle` has only placeholder stubs.
2. **WarehouseMobile is empty scaffolding** (MainActivity + Theme, no custom classes).
3. **Existing design docs contradict the Rust core directive**: `WHMobile_TZ.md` (2340 lines) and `WarehouseMobile_SPEC.md` (1751 lines) describe a pure Kotlin-native architecture (Room + Retrofit + DataStore) with no Rust integration.
4. **The user explicitly requested**: «нужно спроектировать мобильное приложение на андроид .. ядром будет Rust core» — Rust core must be the engine.
5. **Android UI development cannot realistically wait** for all 17 Rust core phases to complete. The mobile team needs a working engine API to build screens against immediately.

The core architectural question: how do we build an Android app whose engine does not yet exist?

## Decision

**Two-implementation strategy with a single normative `CoreHandle` Kotlin interface.**

1. Define a single `CoreHandle` Kotlin interface (§2 of `TZ_MOBILE_RUST_CORE_ARCHITECTURE.md`). This interface is the only API Android UI code is allowed to depend on for warehouse domain operations.

2. Implement `SurrogateCoreHandle` — a pure Kotlin development surrogate that:
   - Serves pre-canned/simulated data (in-memory)
   - Makes no real HTTP calls, manages no real SQLite
   - Throws the same `CoreError` types
   - Is explicitly `@Deprecated` (to be replaced by `RustCoreHandle`)

3. When Rust core reaches Capability Level 3+ (auth/identity HTTP client working), implement `RustCoreHandle` — a thin Kotlin wrapper around UniFFI-generated Rust bindings.

4. Switch between implementations via a single Hilt DI module swap. All ViewModels and screens continue to work unchanged because they depend on the `CoreHandle` interface, not the implementation.

5. The switch is gated at Rust Capability Level 5+ (operation drafts + outbox) for production use, or Level 3+ for early integration testing.

## Evidence

- `AGENTS.md` (root): «Future offline clients must use `Warehouse_client_core` for local storage, outbox, sync, DTO mapping, and conflict handling.»
- `AGENTS.md` (WarehouseMobile): «This app should be rebuilt around `Warehouse_client_core` for offline storage, sync, DTO mapping, and conflicts.»
- `AGENTS.md` (Warehouse_client_core): «Put local SQLite schema, outbox, sync, DTO mapping, conflict state, and a stable facade API here.»
- `TZ_MOBILE_RUST_CORE_ARCHITECTURE.md`: Full phase plan with CoreHandle contract, surrogate impl, FFI integration steps.
- `RUST_CORE_CAPABILITY_PLAN.md`: Defines 7 capability levels for Rust core. Levels 1-2 are partially done; Levels 3-7 are future.
- `WHMobile_TZ.md` (deprecated): Describes Kotlin-native architecture that this ADR explicitly overrides.

## Consequences

### Pros
- Android UI development can start immediately (Phase 0-4, no Rust dependency)
- Contract-first design ensures clean separation of concerns
- Surrogate → Real swap is a one-line Hilt module change
- Rust core team can develop independently against the same `CoreHandle` contract
- Single interface prevents Android code from taking dependencies on implementation details

### Cons
- Surrogate implementation is throwaway code (wasted effort on Kotlin-native logic)
- Behavioral divergence between surrogate and real core may cause subtle bugs at swap time
- Requires discipline to keep surrogate simple and realistic
- Two codebases to maintain during the transition period
- UniFFI integration adds build complexity (Android NDK, cross-compilation)

### Mitigations
- Surrogate is kept deliberately simple — no real sync, no real DB, pre-canned data only
- Contract tests run against BOTH implementations (when real core is available)
- Surrogate is annotated `@Deprecated("Replace with RustCoreHandle when core reaches Level 5+")`
- The CoreHandle interface is the sole dependency; ViewModels must not distinguish implementations
- All DTOs are defined once and shared via the interface contract

## Alternatives Considered

### Option 1: Wait for Rust core before starting Android
**Rejected**: Would delay Android development by months (Rust core has 12+ remaining phases). The mobile team would have nothing to build against.

### Option 2: Build pure Kotlin-native MVP, then rewrite for Rust core later
**Rejected**: Would require rewriting all ViewModels, repositories, and data layer code when Rust core arrives. The contract-first approach achieves the same goal with a clean swap instead of a rewrite.

### Option 3: Build Rust core and Android in lockstep (phase-by-phase)
**Partially adopted**: This is the target for Phase 5+. However, Phase 0-4 Android work can proceed independently via the surrogate. Lockstep development risks blocking both teams on each other's milestones.

### Option 4: Skip Rust core entirely, use Kotlin-native only
**Rejected**: Contradicts the explicit AGENTS directive and user request. Rust core provides shared offline logic for future WPF, MAUI, and iOS clients — it is a strategic investment.

## References
- `TZ_MOBILE_RUST_CORE_ARCHITECTURE.md` — Full architecture TZ
- `WHMobile_TZ.md` — Deprecated Kotlin-native TZ
- `WarehouseMobile_SPEC.md` — Spec to be updated (§3-7)
- `RUST_CORE_CAPABILITY_PLAN.md` — Rust core capability levels
- `API_MAP.md` — SyncServer endpoint inventory
