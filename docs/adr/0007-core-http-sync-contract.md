# ADR-0007: Core HTTP/Sync Contract Source

## Status
Proposed

## Date
2026-05-16

## Context

`Warehouse_client_core` needs a stable contract for HTTP communication with SyncServer. The source for DTO shapes, endpoint paths, headers, and error patterns lives across:

- `SyncServer` FastAPI Pydantic schemas (source of truth)
- `SyncServer/docs/API_MAP.md` (endpoint inventory, 97 paths)
- `SyncServer` OpenAPI JSON at `/api/openapi.json`
- Existing `warehouse_core` domain DTOs (manual Rust translations)

Without a drift rule, Rust DTOs silently diverge from SyncServer, causing serialization errors at runtime.

## Decision

### Contract source

1. **Canonical source**: SyncServer Pydantic schemas in `SyncServer/app/schemas/`.
2. **Endpoint inventory**: `SyncServer/docs/API_MAP.md`.
3. **Active Rust DTOs**: `warehouse_core/src/domain/` are manual translations with serde annotation parity.
4. **No OpenAPI codegen** for now — manual translation gives control over Rust idioms (`Unknown(String)` fallbacks, optional handling). If drift becomes costly, add a CI schema-diff check.

### DTO drift rules

| Rule | When |
|---|---|
| A new required field in SyncServer must be added to the Rust DTO | CI contract test fails |
| An optional field added in SyncServer should be added | Next pull-sync patch |
| A field renamed or removed in SyncServer | Update Rust DTO, mark old name as `#[serde(alias)]` for 1 release |
| A new enum variant added in SyncServer | `Unknown(String)` catch-all handles it; add explicit variant in next release |
| Response shape changes incompatibly | Update Rust DTO + mapping; document in CHANGELOG |

### Endpoint coverage for client

Required endpoint groups (see `CLIENT_READY_API_MATRIX.md`):

- Health, Auth, Catalog Read, Operations, Balances, Temporary Items, Documents, Recipients, Asset Registers, Reports, Device Sync.
- Catalog Admin and Admin endpoints are feature-gated (`allow_admin` / `allow_catalog_admin`).
- Compatibility `/business/*` endpoints are not used.

### Error mapping

| HTTP / Server response | CoreError category |
|---|---|
| `401` | `Unauthenticated` |
| `403` | `Forbidden` |
| `404` | `NotFound` |
| `409` | `Conflict` |
| `422` | `Validation` |
| `408` / `503` / timeout | `Unavailable` |
| Rate-limit / `Retry-After` | `Unavailable` with backoff hint |
| Serialization failure | `ProtocolMismatch` |

## Consequences

- Manual DTO translation is acceptable at the current pace. If 5+ drift incidents occur per release, adopt schema-diff CI.
- `Unknown(String)` enum catch-all prevents deserialization failures on server-side enum additions.
- Contract tests (Level 11) will detect drift before release.

## Confidence
**High** — pattern proven by existing Phase 1 DTO modules.
