# SyncServer API Map

Полная карта API SyncServer для клиентских команд.

> **Frozen:** single snapshot, 2026-05-18. Derives from `SyncServer/main.py`, `app/api/routes_*.py`, actual route code.

---

## Base

| Item | Path |
|---|---|
| API prefix | `/api/v1` |
| OpenAPI docs | `/api/docs` |
| OpenAPI JSON | `/api/openapi.json` |
| Redoc | `/api/redoc` |

---

## Auth Contract

SyncServer uses exactly two transport headers for authentication. No optional auth context headers remain.

| Header | Format | Meaning | Required for |
|---|---|---|---|
| `X-User-Token` | `<uuid>` | User identity and authorization context | `/auth/*`, `/admin/*`, `/catalog/*`, `/catalog/admin/*`, `/operations/*`, `/balances/*`, `/temporary-items/*`, `/documents/*`, `/recipients/*`, `/assets/*`, `/reports/*`, `/bootstrap/sync` |
| `X-Device-Token` | `<uuid>` | Device identity and sync context | `/ping`, `/push`, `/pull` |

Common request header: `Content-Type: application/json`.

**Forbidden:** `Authorization: Bearer`, JWT, access_token, refresh_token, service tokens, `X-Device-Id`, `X-Site-Id`, `X-Client-Version`, `X-Acting-User-Id`, `X-Acting-Site-Id`.

---

## Auth Modes

| Mode | Header | Used by |
|---|---|---|
| User token | `X-User-Token` | Primary: auth, admin, catalog, operations, balances, temp items, documents, recipients, assets, reports, bootstrap |
| Device token | `X-Device-Token` | Sync: `/ping`, `/push`, `/pull` |

---

## Roles

| Role | Scope | Permissions |
|---|---|---|
| `root` | Global | Full authority: all reads, writes, admin operations, user/device/token management |
| `chief_storekeeper` | Global business access | Catalog admin, device/site admin basics, operations write, recipients merge, asset resolution |
| `storekeeper` | Site-scoped via access scopes | Operations write, catalog/balance read, document generate, temporary item moderation |
| `observer` | Site-scoped via access scopes | Read-only: catalog, balances, operations, documents, reports, assets |

---

## /api/v1 — Root / Utility

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `GET` | `/` | none | — | `{message, status, env, version}` |
| `GET` | `/db_check` | none | — | `{db_status, result}` |

---

## /api/v1/auth — Auth API

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `POST` | `/auth/sync-user` | `X-User-Token` (root) | `{id?, username, email, full_name, is_active, is_root, role, default_site_id?}` | `{status, user: {…user_token}, synced_by}` |
| `GET` | `/auth/me` | `X-User-Token` | — | `{user, device}` |
| `GET` | `/auth/sites` | `X-User-Token` | — | `{is_root, available_sites}` |
| `GET` | `/auth/context` | `X-User-Token` | — | `{user, role, is_root, default_site, available_sites, permissions_summary, device}` |

Notes:
- `sync-user` is root-only. Cannot create/update root users.
- `auth/me` never returns `user_token`.
- Device info included in `me` and `context` responses when a device token is also provided.

---

## /api/v1/admin — Admin API

Client teams: this group is for administrative tooling (staff dashboard, admin CLI). Most client-facing apps should use `/auth/*` and domain endpoints instead.

### Roles

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `GET` | `/admin/roles` | `X-User-Token` | — | `list[str]` |

### Sites

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `GET` | `/admin/sites` | `X-User-Token` | query: `is_active`, `search`, `page`, `page_size` | `{sites, total_count, page, page_size}` |
| `POST` | `/admin/sites` | `X-User-Token` | `{code, name, is_active, description}` | `SiteResponse` |
| `PATCH` | `/admin/sites/{site_id}` | `X-User-Token` | partial site | `SiteResponse` |

### Users (root only)

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `GET` | `/admin/users` | `X-User-Token` (root) | query: `is_active`, `is_root`, `role`, `search`, `page`, `page_size` | `{users, total_count, page, page_size}` |
| `GET` | `/admin/users/{user_id}` | `X-User-Token` (root) | — | `UserResponse` |
| `POST` | `/admin/users` | `X-User-Token` (root) | `UserCreate` | `UserResponse` |
| `PATCH` | `/admin/users/{user_id}` | `X-User-Token` (root) | `UserUpdate` | `UserResponse` |
| `DELETE` | `/admin/users/{user_id}` | `X-User-Token` (root) | — | `UserResponse` (soft-deactivated) |
| `GET` | `/admin/users/{user_id}/sync-state` | `X-User-Token` (root) | — | `{user: {…user_token}, scopes}` |
| `PUT` | `/admin/users/{user_id}/scopes` | `X-User-Token` (root) | `{scopes: [{site_id, can_view, can_operate, can_manage_catalog}]}` | `list[UserAccessScopeResponse]` |
| `POST` | `/admin/users/{user_id}/rotate-token` | `X-User-Token` (root) | — | `{user_id, username, user_token, generated_at}` |

### Access Scopes (root only)

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `GET` | `/admin/access/scopes` | `X-User-Token` (root) | query: `user_id`, `site_id`, `is_active`, `limit`, `offset` | `list[UserAccessScopeResponse]` |
| `POST` | `/admin/access/scopes` | `X-User-Token` (root) | `UserAccessScopeCreate` | `UserAccessScopeResponse` |
| `PATCH` | `/admin/access/scopes/{scope_id}` | `X-User-Token` (root) | `UserAccessScopeUpdate` | `UserAccessScopeResponse` |

### Devices

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `GET` | `/admin/devices` | `X-User-Token` | query: `site_id`, `is_active`, `search`, `page`, `page_size` | `{devices, total_count, page, page_size}` |
| `GET` | `/admin/devices/{device_id}` | `X-User-Token` | — | `DeviceResponse` |
| `POST` | `/admin/devices` | `X-User-Token` | `DeviceCreate` | `DeviceWithTokenResponse` (includes `device_token`) |
| `PATCH` | `/admin/devices/{device_id}` | `X-User-Token` | `DeviceUpdate` | `DeviceResponse` |
| `DELETE` | `/admin/devices/{device_id}` | `X-User-Token` | — | `DeviceResponse` |
| `POST` | `/admin/devices/{device_id}/rotate-token` | `X-User-Token` | — | `{device_id, device_code, device_token, generated_at}` |

---

## /api/v1/catalog — Catalog Read API

All read endpoints use `X-User-Token`. Access is user-scoped; `site_id` query param filters to accessible sites.

### Primary read (sync-optimized, `updated_after` cursor)

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `GET` | `/catalog/items` | `X-User-Token` | query: `updated_after`, `limit` (100, max 1000), `site_id` | `{items, server_time, next_updated_after}` |
| `GET` | `/catalog/categories` | `X-User-Token` | query: `updated_after`, `limit` (100, max 1000), `site_id` | `{categories, server_time, next_updated_after}` |
| `GET` | `/catalog/categories/tree` | `X-User-Token` | query: `site_id` | `list[CategoryTreeNode]` |
| `GET` | `/catalog/units` | `X-User-Token` | query: `updated_after`, `limit` (100, max 1000), `site_id` | `{units, server_time, next_updated_after}` |
| `GET` | `/catalog/sites` | `X-User-Token` | query: `is_active` | `{sites, server_time}` |

Notes:
- `updated_after` cursor is ISO 8601 datetime; response includes `next_updated_after` for incremental sync.
- `site_id` is an access filter, not a data partition. `root` and `chief_storekeeper` see all items regardless of site_id.
- Roles: `root`, `chief_storekeeper`, `storekeeper`, `observer`.

### Browse read (paginated, search)

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `GET` | `/catalog/read/items` | `X-User-Token` | query: `search`, `category_id`, `page`, `page_size`, `site_id` | `{items, total_count, page, page_size}` |
| `GET` | `/catalog/read/categories` | `X-User-Token` | query: `search`, `parent_id`, `page`, `page_size`, `include`, `items_preview_limit`, `site_id` | `{categories, total_count, page, page_size}` |
| `GET` | `/catalog/read/categories/{category_id}/items` | `X-User-Token` | query: `search`, `page`, `page_size`, `site_id` | `{items, total_count, page, page_size}` |
| `GET` | `/catalog/read/categories/{category_id}/children` | `X-User-Token` | query: `page`, `page_size`, `include`, `items_preview_limit`, `site_id` | `{categories, total_count, page, page_size}` |
| `GET` | `/catalog/read/categories/{category_id}/parent-chain` | `X-User-Token` | query: `site_id` | `{category_id, parent_chain_summary}` |

---

## /api/v1/catalog/admin — Catalog Admin API

Mutation endpoints for units, categories, items. Requires `X-User-Token`. Authorization is role-based (no site header).
- `root`: full access.
- `chief_storekeeper`: full access (global business access).
- `storekeeper`, `observer`: denied.

### Units

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `GET` | `/catalog/admin/units` | `X-User-Token` | query: `include_inactive`, `include_deleted`, `page`, `page_size` | `{items, total_count, page, page_size}` |
| `GET` | `/catalog/admin/units/{unit_id}` | `X-User-Token` | — | `UnitResponse` |
| `POST` | `/catalog/admin/units` | `X-User-Token` | `{name, symbol, sort_order, is_active}` | `UnitResponse` |
| `POST` | `/catalog/admin/units/bulk` | `X-User-Token` | `{items: [{name, symbol, sort_order, is_active}]}` | `{items: [UnitResponse]}` |
| `PATCH` | `/catalog/admin/units/{unit_id}` | `X-User-Token` | partial unit | `UnitResponse` |
| `DELETE` | `/catalog/admin/units/{unit_id}` | `X-User-Token` | — | 204 |

### Categories

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `GET` | `/catalog/admin/categories` | `X-User-Token` | query: `include_inactive`, `include_deleted`, `page`, `page_size` | `{items, total_count, page, page_size}` |
| `GET` | `/catalog/admin/categories/{category_id}` | `X-User-Token` | — | `CategoryResponse` |
| `POST` | `/catalog/admin/categories` | `X-User-Token` | `{name, code, parent_id?, sort_order, is_active}` | `CategoryResponse` |
| `POST` | `/catalog/admin/categories/bulk` | `X-User-Token` | `{items: [{name, code, parent_id?, sort_order, is_active}]}` | `{items: [CategoryResponse]}` |
| `PATCH` | `/catalog/admin/categories/{category_id}` | `X-User-Token` | partial category | `CategoryResponse` |
| `DELETE` | `/catalog/admin/categories/{category_id}` | `X-User-Token` | — | 204 |

### Items

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `GET` | `/catalog/admin/items` | `X-User-Token` | query: `include_inactive`, `include_deleted`, `page`, `page_size` | `{items, total_count, page, page_size}` |
| `GET` | `/catalog/admin/items/{item_id}` | `X-User-Token` | — | `ItemResponse` |
| `POST` | `/catalog/admin/items` | `X-User-Token` | `{sku, name, category_id, unit_id, description, is_active}` | `ItemResponse` |
| `PATCH` | `/catalog/admin/items/{item_id}` | `X-User-Token` | partial item | `ItemResponse` |
| `DELETE` | `/catalog/admin/items/{item_id}` | `X-User-Token` | — | 204 |

---

## /api/v1/operations — Operations API

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `GET` | `/operations` | `X-User-Token` | query: `site_id`, `type`, `status`, `created_by_user_id`, `effective_after`, `effective_before`, `created_after`, `created_before`, `updated_after`, `updated_before`, `search`, `page`, `page_size` | `{items, total_count, page, page_size}` |
| `GET` | `/operations/{operation_id}` | `X-User-Token` | — | `OperationResponse` |
| `POST` | `/operations` | `X-User-Token` | `OperationCreate` | `OperationResponse` |
| `PATCH` | `/operations/{operation_id}` | `X-User-Token` | `OperationUpdate` | `OperationResponse` |
| `PATCH` | `/operations/{operation_id}/effective-at` | `X-User-Token` | `{effective_at}` | `OperationResponse` |
| `POST` | `/operations/{operation_id}/submit` | `X-User-Token` | `{submit: true}` | `OperationResponse` |
| `POST` | `/operations/{operation_id}/cancel` | `X-User-Token` | `{cancel: true, reason?}` | `OperationResponse` |
| `POST` | `/operations/{operation_id}/accept-lines` | `X-User-Token` | `{lines: [{operation_line_id, accepted_qty, lost_qty, note?}]}` | `OperationResponse` |

Notes:
- Read roles: `root`, `chief_storekeeper`, `storekeeper`, `observer`.
- Write roles: `root`, `chief_storekeeper`, `storekeeper`.
- MOVE operations require `source_site_id` + `destination_site_id` in create/update payloads and corresponding site access.
- `effective_at` must be changed via the dedicated `PATCH /operations/{id}/effective-at`, not through generic `PATCH /operations/{id}`.

---

## /api/v1/balances — Balances API

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `GET` | `/balances` | `X-User-Token` | query: `site_id`, `item_id`, `category_id`, `search`, `only_positive`, `page`, `page_size` | `{items, total_count, page, page_size}` |
| `GET` | `/balances/by-site` | `X-User-Token` | query: `site_id` (required), `only_positive`, `page`, `page_size` | `{items, total_count, page, page_size}` |
| `GET` | `/balances/summary` | `X-User-Token` | — | `{accessible_sites_count, summary}` |

Notes:
- Read roles: `root`, `chief_storekeeper`, `storekeeper`, `observer`.
- Non-root users only see balances for sites they have `can_view` access to.

---

## /api/v1/temporary-items — Temporary Items API

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `GET` | `/temporary-items` | `X-User-Token` | query: `status`, `search`, `created_by_user_id`, `resolved_item_id`, `created_after`, `created_before`, `page`, `page_size` | `{items, total_count, page, page_size}` |
| `GET` | `/temporary-items/{temporary_item_id}` | `X-User-Token` | — | `TemporaryItemResponse` |
| `GET` | `/temporary-items/{temporary_item_id}/operations` | `X-User-Token` | query: `page`, `page_size` | `{items, total_count, page, page_size}` |
| `POST` | `/temporary-items/{temporary_item_id}/approve-as-item` | `X-User-Token` | — | `TemporaryItemResponse` (creates catalog item) |
| `POST` | `/temporary-items/{temporary_item_id}/merge` | `X-User-Token` | `{target_item_id, comment?}` | `TemporaryItemResponse` (merges into existing catalog item) |
| `DELETE` | `/temporary-items/{temporary_item_id}` | `X-User-Token` | — | `TemporaryItemResponse` (soft-delete) |

Notes:
- Requires temporary item moderation role (via `OperationsPolicy.require_temporary_item_moderation`).
- `approve-as-item` creates a new catalog item from the temporary one; approval is server-authoritative.

---

## /api/v1/documents — Documents API

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `POST` | `/documents/generate` | `X-User-Token` | `{operation_id, document_type, template_name?, auto_finalize?, language?, basis_type?, basis_number?, basis_date?}` | `{document, operation_id, generated_at}` |
| `GET` | `/documents` | `X-User-Token` | query: `site_id`, `document_type`, `status`, `created_by_user_id`, `date_from`, `date_to`, `offset`, `limit` | `{items, total, offset, limit}` |
| `GET` | `/documents/{document_id}` | `X-User-Token` | — | `DocumentResponse` |
| `GET` | `/documents/{document_id}/render` | `X-User-Token` | query: `format` (html/pdf) | HTML or PDF binary |
| `PATCH` | `/documents/{document_id}/status` | `X-User-Token` | `{status, finalized_at?, payload?, payload_hash?}` | `DocumentResponse` |
| `GET` | `/documents/operations/{operation_id}/documents` | `X-User-Token` | query: `document_type` | `list[DocumentResponse]` |
| `POST` | `/documents/operations/{operation_id}/documents` | `X-User-Token` | query: `document_type` (waybill), `template_name?`, `auto_finalize?`, `language?` (ru), `basis_type?`, `basis_number?`, `basis_date?` | `{document, operation_id, generated_at}` |

Notes:
- Write roles: `chief_storekeeper`, `storekeeper`.
- Documents can be finalized or voided via status PATCH.
- Shortcut `POST /documents/operations/{id}/documents` accepts query params instead of JSON body.

---

## /api/v1/recipients — Recipients API

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `GET` | `/recipients` | `X-User-Token` | query: `search`, `recipient_type`, `include_inactive`, `include_deleted`, `page`, `page_size` | `{items, total_count, page, page_size}` |
| `POST` | `/recipients` | `X-User-Token` | `{display_name, recipient_type, personnel_no?}` | `RecipientResponse` |
| `POST` | `/recipients/merge` | `X-User-Token` | `{source_id, target_id}` | `RecipientResponse` |
| `GET` | `/recipients/{recipient_id}` | `X-User-Token` | — | `RecipientResponse` |
| `PATCH` | `/recipients/{recipient_id}` | `X-User-Token` | partial recipient | `RecipientResponse` |
| `DELETE` | `/recipients/{recipient_id}` | `X-User-Token` | — | 204 |

Notes:
- Write roles: `chief_storekeeper`, `storekeeper`.
- Merge requires `chief_storekeeper` or `root`.

---

## /api/v1 — Asset Registers API

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `GET` | `/pending-acceptance` | `X-User-Token` | query: `site_id`, `operation_id`, `item_id`, `search`, `page`, `page_size` | `{items, total_count, page, page_size}` |
| `GET` | `/lost-assets` | `X-User-Token` | query: `site_id`, `source_site_id`, `operation_id`, `item_id`, `search`, `updated_after`, `updated_before`, `qty_from`, `qty_to`, `page`, `page_size` | `{items, total_count, page, page_size}` |
| `GET` | `/lost-assets/{operation_line_id}` | `X-User-Token` | — | `LostAssetRow` |
| `POST` | `/lost-assets/{operation_line_id}/resolve` | `X-User-Token` | `{action, qty, note?, responsible_recipient_id?}` | `{...}` (varies by action) |
| `GET` | `/issued-assets` | `X-User-Token` | query: `recipient_id`, `item_id`, `search`, `page`, `page_size` | `{items, total_count, page, page_size}` |

Notes:
- Read requires `OperationsPolicy.require_assets_read_access`.
- Resolve requires `OperationsPolicy.require_lost_resolve_access`.
- Site filtering is access-scoped; users only see their accessible sites.

---

## /api/v1/reports — Reports API

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `GET` | `/reports/item-movement` | `X-User-Token` | query: `site_id`, `item_id`, `category_id`, `search`, `date_from`, `date_to`, `page`, `page_size` | `{items, total_count, page, page_size, date_from, date_to}` |
| `GET` | `/reports/stock-summary` | `X-User-Token` | query: `site_id`, `category_id`, `search`, `only_positive`, `page`, `page_size` | `{items, total_count, page, page_size}` |

---

## /api/v1 — Device Sync API

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `POST` | `/ping` | `X-Device-Token` | `{site_id, device_id, last_server_seq, outbox_count, client_time}` | `{server_time, server_seq_upto, backoff_seconds}` |
| `POST` | `/push` | `X-Device-Token` | `{site_id, device_id, batch_id, events: [...]}` | `{accepted, duplicates, rejected, server_seq_upto}` |
| `POST` | `/pull` | `X-Device-Token` | `{site_id, device_id, since_seq, limit}` | `{events, server_time, server_seq_upto, next_since_seq}` |
| `POST` | `/bootstrap/sync` | `X-User-Token` (root) | `{site_id, device_id}` (can be 0) | `{server_time, protocol_version, is_root, root_user, root_role, device_id, device_registered, message, bootstrap_data}` |

Notes:
- Device sync (`/ping`, `/push`, `/pull`) uses `X-Device-Token` only.
- Bootstrap uses `X-User-Token` (root), with optional `X-Device-Token` for device binding.
- PUSH has a max event batch limit from server config.
- PULL returns events with `server_seq` cursor, monotonic per site.
- Push idempotency is per-event UUID; duplicate-same-payload is classified separately from UUID collision.

---

## /api/v1/health — Health API

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `GET` | `/health` | none | — | `{status: "ok"}` |
| `GET` | `/ready` | none | — | `{status: "ready", db: 1}` |
| `GET` | `/health/detailed` | none | — | `{status, checks: {db, config, cache?}}` |
| `GET` | `/health/readiness` | none | — | `{ready, details}` |
| `GET` | `/health/liveness` | none | — | `{alive}` |

---

## Client Integration Notes

### For `Warehouse_client_core` (Rust)

Core already has typed HTTP clients for all endpoint groups above. The two-token contract matches core's `FfiTokenProvider` / `warehouse_set_user_token` / `warehouse_set_device_token`. API map should be cross-referenced with `crates/warehouse_core/src/syncserver/*.rs` modules.

### For `Warehouse_web` (Django BFF)

All calls to SyncServer must go through `apps/sync_client/client.py` (`SyncServerClient`) or `apps/sync_client/root_admin_client.py` (`SyncServerRootAdminClient`). Browser-facing BFF endpoints must never expose SyncServer tokens. The Django client sends `X-User-Token` (from user binding/session) and optionally `X-Device-Token` (audit context).

### For Android (Kotlin/JNA)

Use `warehouse_ffi` exports for warehouse domain operations. The FFI communicates with SyncServer through core's HTTP client internally. Platform owns secure token storage; tokens are injected via `warehouse_set_user_token` and `warehouse_set_device_token`. See `Warehouse_client_core/docs/ANDROID_BINDINGS.md`.

### For WPF (C#/P/Invoke)

Use `warehouse_ffi.dll` via P/Invoke for domain operations. The core manages SyncServer HTTP internally. Platform injects tokens from secure storage. See `Warehouse_client_core/docs/WPF_BINDINGS.md`.
