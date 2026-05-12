# API Map

Полная техническая карта API SyncServer — все эндпоинты, аутентификация, форматы запросов/ответов.

## Base
- Base prefix: `/api/v1`
- OpenAPI docs: `/api/docs`
- OpenAPI JSON: `/api/openapi.json`
- Redoc: `/api/redoc`

---

## Real Headers

### User auth
- `X-User-Token: <uuid>`

Used by:
- `/auth/*`
- `/admin/*`
- `/catalog/*` primary read API
- `/catalog/admin/*`
- `/operations/*`
- `/balances/*`
- `/temporary-items/*`
- `/documents/*`
- `/recipients/*`
- `/pending-acceptance`, `/lost-assets/*`, `/issued-assets`
- `/reports/*`

### Device auth
- `X-Device-Token: <uuid>`

Used by:
- `/ping`
- `/push`
- `/pull`
- legacy `POST /catalog/items`
- legacy `POST /catalog/categories`
- legacy `POST /catalog/units`

### Optional auth context headers
- `X-Device-Id: <device_id>`
  - optional on `/auth/me`, `/auth/context`, `/auth/sync-user`
- `X-Site-Id: <site_id>`
  - required for `chief_storekeeper` on `/catalog/admin/*`
- `X-Client-Version: <version>`
  - optional on `/ping`, `/push`, `/pull`, `/bootstrap/sync`
- `Authorization: Bearer <service_token>`
  - legacy compatibility only, used by `/business/*`
- `X-Acting-User-Id`, `X-Acting-Site-Id`
  - legacy compatibility only, used by `/business/*`

### Common request header
- `Content-Type: application/json`

---

## Auth Modes

| Mode | Real Header(s) | Where Used |
|---|---|---|
| User token | `X-User-Token` | primary app/admin/catalog/operations/balances/temporary-items/documents/recipients/reports/assets |
| Device token | `X-Device-Token` | sync and legacy catalog read |
| Service token | `Authorization: Bearer ...` | legacy `/business/*` only |

---

## Endpoint Groups

### Root / Utility

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `GET` | `/` | none | no body | `{message, status, env, version}` |
| `GET` | `/db_check` | none | no body | `SELECT 1` result, DB connectivity test |

---

### Auth API

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `POST` | `/auth/sync-user` | root `X-User-Token` | user payload: `id`, `username`, `email`, `full_name`, `is_active`, `is_root=false`, `role`, `default_site_id` | `{status, user, synced_by}` with `user.user_token` |
| `GET` | `/auth/me` | `X-User-Token` | no body | `{user, device}` |
| `GET` | `/auth/sites` | `X-User-Token` | no body | `{is_root, available_sites}` |
| `GET` | `/auth/context` | `X-User-Token` | no body | `{user, role, is_root, default_site, available_sites, permissions_summary, device}` |

Notes:
- `sync-user` is root-only.
- `sync-user` cannot create or update root users.
- `auth/me` does not return `user_token`.

---

### Admin API

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `GET` | `/admin/roles` | `X-User-Token` | no body | `list[str]` |
| `GET` | `/admin/sites` | `X-User-Token` | query: `is_active`, `search`, `page`, `page_size` | `{sites, total_count, page, page_size}` |
| `POST` | `/admin/sites` | `X-User-Token` | `{code, name, is_active, description}` | `SiteResponse` |
| `PATCH` | `/admin/sites/{site_id}` | `X-User-Token` | partial site payload | `SiteResponse` |
| `GET` | `/admin/users` | root `X-User-Token` | query: `is_active`, `is_root`, `role`, `search`, `page`, `page_size` | `{users, total_count, page, page_size}` |
| `GET` | `/admin/users/{user_id}` | root `X-User-Token` | no body | `UserResponse` |
| `POST` | `/admin/users` | root `X-User-Token` | `UserCreate` | `UserResponse` |
| `PATCH` | `/admin/users/{user_id}` | root `X-User-Token` | `UserUpdate` | `UserResponse` |
| `DELETE` | `/admin/users/{user_id}` | root `X-User-Token` | no body | `UserResponse` (soft-deactivated) |
| `GET` | `/admin/users/{user_id}/sync-state` | root `X-User-Token` | no body | `{user, scopes}` with `user.user_token` |
| `PUT` | `/admin/users/{user_id}/scopes` | root `X-User-Token` | `{scopes:[{site_id, can_view, can_operate, can_manage_catalog}]}` | `list[UserAccessScopeResponse]` |
| `POST` | `/admin/users/{user_id}/rotate-token` | root `X-User-Token` | no body | `{user_id, username, user_token, generated_at}` |
| `GET` | `/admin/access/scopes` | root `X-User-Token` | query: `user_id`, `site_id`, `is_active`, `limit`, `offset` | `list[UserAccessScopeResponse]` |
| `POST` | `/admin/access/scopes` | root `X-User-Token` | `UserAccessScopeCreate` | `UserAccessScopeResponse` |
| `PATCH` | `/admin/access/scopes/{scope_id}` | root `X-User-Token` | `UserAccessScopeUpdate` | `UserAccessScopeResponse` |
| `GET` | `/admin/devices` | `X-User-Token` | query: `site_id`, `is_active`, `search`, `page`, `page_size` | `{devices, total_count, page, page_size}` |
| `GET` | `/admin/devices/{device_id}` | `X-User-Token` | no body | `DeviceResponse` |
| `POST` | `/admin/devices` | `X-User-Token` | `DeviceCreate` | `DeviceWithTokenResponse` (includes `device_token` in response) |
| `PATCH` | `/admin/devices/{device_id}` | `X-User-Token` | `DeviceUpdate` | `DeviceResponse` |
| `DELETE` | `/admin/devices/{device_id}` | `X-User-Token` | no body | `DeviceResponse` |
| `POST` | `/admin/devices/{device_id}/rotate-token` | `X-User-Token` | no body | `{device_id, device_code, device_token, generated_at}` |

---

### Catalog Read API

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `GET` | `/catalog/items` | `X-User-Token` | query: `updated_after`, `limit`, `site_id` | `{items, server_time, next_updated_after}` |
| `GET` | `/catalog/categories` | `X-User-Token` | query: `updated_after`, `limit`, `site_id` | `{categories, server_time, next_updated_after}` |
| `GET` | `/catalog/categories/tree` | `X-User-Token` | query: `site_id` | `list[CategoryTreeNode]` |
| `GET` | `/catalog/units` | `X-User-Token` | query: `updated_after`, `limit`, `site_id` | `{units, server_time, next_updated_after}` |
| `GET` | `/catalog/sites` | `X-User-Token` | query: `is_active` | `{sites, server_time}` |

Notes:
- `site_id` on catalog read is an access-context check, not a true data partition for items/categories/units.
- `root`, `chief_storekeeper`, `storekeeper`, `observer` can read if access rules pass.

#### Catalog Read — Browse Endpoints (paginated with search)

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `GET` | `/catalog/read/items` | `X-User-Token` | query: `search`, `category_id`, `page`, `page_size`, `site_id` | `{items, total_count, page, page_size}` |
| `GET` | `/catalog/read/categories` | `X-User-Token` | query: `search`, `parent_id`, `page`, `page_size`, `include`, `items_preview_limit`, `site_id` | `{categories, total_count, page, page_size}` |
| `GET` | `/catalog/read/categories/{category_id}/items` | `X-User-Token` | query: `search`, `page`, `page_size`, `site_id` | `{items, total_count, page, page_size}` |
| `GET` | `/catalog/read/categories/{category_id}/children` | `X-User-Token` | query: `page`, `page_size`, `include`, `items_preview_limit`, `site_id` | `{categories, total_count, page, page_size}` |
| `GET` | `/catalog/read/categories/{category_id}/parent-chain` | `X-User-Token` | query: `site_id` | `{category_id, parent_chain_summary}` |

---

### Catalog Admin API

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `GET` | `/catalog/admin/units` | `X-User-Token` | query: `include_inactive`, `include_deleted`, `page`, `page_size` | `{items, total_count, page, page_size}` |
| `GET` | `/catalog/admin/units/{unit_id}` | `X-User-Token` | no body | `UnitResponse` |
| `POST` | `/catalog/admin/units` | `X-User-Token` | `{name, symbol, sort_order, is_active}` | `UnitResponse` |
| `POST` | `/catalog/admin/units/bulk` | `X-User-Token` | `{items:[{name, symbol, sort_order, is_active}]}` | `{items:[UnitResponse]}` |
| `PATCH` | `/catalog/admin/units/{unit_id}` | `X-User-Token` | partial unit payload | `UnitResponse` |
| `DELETE` | `/catalog/admin/units/{unit_id}` | `X-User-Token` | no body | 204 No Content |
| `GET` | `/catalog/admin/categories` | `X-User-Token` | query: `include_inactive`, `include_deleted`, `page`, `page_size` | `{items, total_count, page, page_size}` |
| `GET` | `/catalog/admin/categories/{category_id}` | `X-User-Token` | no body | `CategoryResponse` |
| `POST` | `/catalog/admin/categories` | `X-User-Token` | `{name, code, parent_id, sort_order, is_active}` | `CategoryResponse` |
| `POST` | `/catalog/admin/categories/bulk` | `X-User-Token` | `{items:[{name, code, parent_id, sort_order, is_active}]}` | `{items:[CategoryResponse]}` |
| `PATCH` | `/catalog/admin/categories/{category_id}` | `X-User-Token` | partial category payload | `CategoryResponse` |
| `DELETE` | `/catalog/admin/categories/{category_id}` | `X-User-Token` | no body | 204 No Content |
| `GET` | `/catalog/admin/items` | `X-User-Token` | query: `include_inactive`, `include_deleted`, `page`, `page_size` | `{items, total_count, page, page_size}` |
| `GET` | `/catalog/admin/items/{item_id}` | `X-User-Token` | no body | `ItemResponse` |
| `POST` | `/catalog/admin/items` | `X-User-Token` | `{sku, name, category_id, unit_id, description, is_active}` | `ItemResponse` |
| `PATCH` | `/catalog/admin/items/{item_id}` | `X-User-Token` | partial item payload | `ItemResponse` |
| `DELETE` | `/catalog/admin/items/{item_id}` | `X-User-Token` | no body | 204 No Content |

Notes:
- `root` may call these without `X-Site-Id`.
- `chief_storekeeper` must send `X-Site-Id` and have `can_manage_catalog=true` on that site.
- `storekeeper` and `observer` cannot mutate catalog.

Postman examples:
- bulk units: `POST /api/v1/catalog/admin/units/bulk` with `X-User-Token`, optional `X-Site-Id`, `Content-Type: application/json`
```json
{ "items": [ { "name": "Box", "symbol": "box" }, { "name": "Pallet", "symbol": "pallet" } ] }
```
- bulk categories: `POST /api/v1/catalog/admin/categories/bulk` with `X-User-Token`, optional `X-Site-Id`, `Content-Type: application/json`
```json
{ "items": [ { "name": "Food" }, { "name": "Drinks", "parent_id": 1 } ] }
```

---

### Operations API

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `GET` | `/operations` | `X-User-Token` | query: `site_id`, `type`, `status`, `created_by_user_id`, `effective_after`, `effective_before`, `created_after`, `created_before`, `updated_after`, `updated_before`, `search`, `page`, `page_size` | `{items, total_count, page, page_size}` |
| `GET` | `/operations/{operation_id}` | `X-User-Token` | no body | `OperationResponse` |
| `POST` | `/operations` | `X-User-Token` | `OperationCreate` | `OperationResponse` |
| `PATCH` | `/operations/{operation_id}` | `X-User-Token` | `OperationUpdate` | `OperationResponse` |
| `PATCH` | `/operations/{operation_id}/effective-at` | `X-User-Token` | `{effective_at}` | `OperationResponse` |
| `POST` | `/operations/{operation_id}/submit` | `X-User-Token` | `{submit: true}` | `OperationResponse` |
| `POST` | `/operations/{operation_id}/cancel` | `X-User-Token` | `{cancel: true, reason}` | `OperationResponse` |
| `POST` | `/operations/{operation_id}/accept-lines` | `X-User-Token` | `{lines:[{operation_line_id, accepted_qty, lost_qty, note}]}` | `OperationResponse` |

Notes:
- Read roles: `root`, `chief_storekeeper`, `storekeeper`, `observer`
- Write roles: `root`, `chief_storekeeper`, `storekeeper`
- MOVE requires both `source_site_id` and `destination_site_id`
- `effective_at` must be changed via dedicated `PATCH /operations/{id}/effective-at`, not via the general `PATCH /operations/{id}`

---

### Balances API

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `GET` | `/balances` | `X-User-Token` | query: `site_id`, `item_id`, `category_id`, `search`, `only_positive`, `page`, `page_size` | `{items, total_count, page, page_size}` |
| `GET` | `/balances/by-site` | `X-User-Token` | query: `site_id` (required), `only_positive`, `page`, `page_size` | `{items, total_count, page, page_size}` |
| `GET` | `/balances/summary` | `X-User-Token` | no body | `{accessible_sites_count, summary}` |

Notes:
- Read roles: `root`, `chief_storekeeper`, `storekeeper`, `observer`
- Non-root users only see balances for accessible sites

---

### Temporary Items API

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `GET` | `/temporary-items` | `X-User-Token` | query: `status`, `search`, `created_by_user_id`, `resolved_item_id`, `created_after`, `created_before`, `page`, `page_size` | `{items, total_count, page, page_size}` |
| `GET` | `/temporary-items/{temporary_item_id}` | `X-User-Token` | no body | `TemporaryItemResponse` |
| `POST` | `/temporary-items/{temporary_item_id}/approve-as-item` | `X-User-Token` | no body | `TemporaryItemResponse` (creates a new catalog item) |
| `GET` | `/temporary-items/{temporary_item_id}/operations` | `X-User-Token` | query: `page`, `page_size` | `{items, total_count, page, page_size}` (operations referencing this temp item) |
| `POST` | `/temporary-items/{temporary_item_id}/merge` | `X-User-Token` | `{target_item_id, comment}` | `TemporaryItemResponse` (merges into existing catalog item) |
| `DELETE` | `/temporary-items/{temporary_item_id}` | `X-User-Token` | no body | `TemporaryItemResponse` (soft-delete) |

Notes:
- Requires temporary item moderation role (managed by `OperationsPolicy`).

---

### Documents API

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `POST` | `/documents/generate` | `X-User-Token` | `DocumentGenerateRequest`: `operation_id`, `document_type`, `template_name`, `auto_finalize`, `language`, `basis_type`, `basis_number`, `basis_date` | `{document, operation_id, generated_at}` |
| `GET` | `/documents/{document_id}` | `X-User-Token` | no body | `DocumentResponse` |
| `GET` | `/documents/{document_id}/render` | `X-User-Token` | query: `format` (`html` or `pdf`) | HTML or PDF binary |
| `GET` | `/documents` | `X-User-Token` | query: `site_id`, `document_type`, `status`, `created_by_user_id`, `date_from`, `date_to`, `offset`, `limit` | `{items, total, offset, limit}` |
| `PATCH` | `/documents/{document_id}/status` | `X-User-Token` | `DocumentUpdate` (`status`, `finalized_at`, `payload`, `payload_hash`) | `DocumentResponse` |
| `GET` | `/documents/operations/{operation_id}/documents` | `X-User-Token` | query: `document_type` | `list[DocumentResponse]` |
| `POST` | `/documents/operations/{operation_id}/documents` | `X-User-Token` | query: `document_type` (waybill), `template_name`, `auto_finalize`, `language` (ru), `basis_type`, `basis_number`, `basis_date` | `{document, operation_id, generated_at}` |

Notes:
- Write roles: `chief_storekeeper`, `storekeeper`
- Documents can be finalized or voided via status update
- Shortcut `POST /documents/operations/{id}/documents` allows generating documents via query params instead of JSON body

---

### Recipients API

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `GET` | `/recipients` | `X-User-Token` | query: `search`, `recipient_type`, `include_inactive`, `include_deleted`, `page`, `page_size` | `{items, total_count, page, page_size}` |
| `POST` | `/recipients` | `X-User-Token` | `{display_name, recipient_type, personnel_no}` | `RecipientResponse` |
| `POST` | `/recipients/merge` | `X-User-Token` (manager-only) | `{source_id, target_id}` | `RecipientResponse` |
| `GET` | `/recipients/{recipient_id}` | `X-User-Token` | no body | `RecipientResponse` |
| `PATCH` | `/recipients/{recipient_id}` | `X-User-Token` | partial recipient payload | `RecipientResponse` |
| `DELETE` | `/recipients/{recipient_id}` | `X-User-Token` | no body | 204 No Content |

Notes:
- Write roles: `chief_storekeeper`, `storekeeper`
- Merge requires `chief_storekeeper` or `root`

---

### Asset Registers API

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `GET` | `/pending-acceptance` | `X-User-Token` | query: `site_id`, `operation_id`, `item_id`, `search`, `page`, `page_size` | `{items, total_count, page, page_size}` |
| `GET` | `/lost-assets` | `X-User-Token` | query: `site_id`, `source_site_id`, `operation_id`, `item_id`, `search`, `updated_after`, `updated_before`, `qty_from`, `qty_to`, `page`, `page_size` | `{items, total_count, page, page_size}` |
| `GET` | `/lost-assets/{operation_line_id}` | `X-User-Token` | no body | `LostAssetRow` |
| `POST` | `/lost-assets/{operation_line_id}/resolve` | `X-User-Token` | `{action, qty, note, responsible_recipient_id}` | `{...}` (varies by action) |
| `GET` | `/issued-assets` | `X-User-Token` | query: `recipient_id`, `item_id`, `search`, `page`, `page_size` | `{items, total_count, page, page_size}` |

Notes:
- Requires `OperationsPolicy.require_assets_read_access` for read endpoints
- Resolve requires `OperationsPolicy.require_lost_resolve_access`

---

### Reports API

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `GET` | `/reports/item-movement` | `X-User-Token` | query: `site_id`, `item_id`, `category_id`, `search`, `date_from`, `date_to`, `page`, `page_size` | `{items, total_count, page, page_size, date_from, date_to}` |
| `GET` | `/reports/stock-summary` | `X-User-Token` | query: `site_id`, `category_id`, `search`, `only_positive`, `page`, `page_size` | `{items, total_count, page, page_size}` |

---

### Device Sync API

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `POST` | `/ping` | `X-Device-Token` | `{site_id, device_id, last_server_seq, outbox_count, client_time}` | `{server_time, server_seq_upto, backoff_seconds}` |
| `POST` | `/push` | `X-Device-Token` | `{site_id, device_id, batch_id, events:[...]}` | `{accepted, duplicates, rejected, server_seq_upto}` |
| `POST` | `/pull` | `X-Device-Token` | `{site_id, device_id, since_seq, limit}` | `{events, server_time, server_seq_upto, next_since_seq}` |
| `POST` | `/bootstrap/sync` | root `X-User-Token` | `{site_id, device_id}` (can be 0) | `{server_time, protocol_version, is_root, root_user, root_role, device_id, device_registered, message, bootstrap_data}` |

Notes:
- `bootstrap/sync` is root-only, X-User-Token (not device token).
- PUSH has a max event batch limit (`settings.MAX_PUSH_EVENTS`).

---

### Health API

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `GET` | `/health` | none | no body | `{status: "ok"}` |
| `GET` | `/ready` | none | no body | `{status: "ready", db: 1}` |
| `GET` | `/health/detailed` | none | no body | `{status, checks}` — comprehensive dependency check |
| `GET` | `/health/readiness` | none | no body | `{ready, details}` — for load balancers |
| `GET` | `/health/liveness` | none | no body | `{alive}` — for Kubernetes |

---

### Legacy Compatibility API

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `POST` | `/catalog/items` | `X-Device-Token` + catalog headers | `CatalogRequest` | `CatalogItemsResponse` |
| `POST` | `/catalog/categories` | `X-Device-Token` + catalog headers | `CatalogRequest` | `CatalogCategoriesResponse` |
| `POST` | `/catalog/units` | `X-Device-Token` + catalog headers | `CatalogRequest` | `CatalogUnitsResponse` |
| `POST` | `/business/catalog/items` | `Authorization: Bearer ...` + acting headers | compatibility payload | `CatalogItemsResponse` |
| `POST` | `/business/catalog/categories` | `Authorization: Bearer ...` + acting headers | compatibility payload | `CatalogCategoriesResponse` |
| `POST` | `/business/catalog/units` | `Authorization: Bearer ...` + acting headers | compatibility payload | `CatalogUnitsResponse` |
| `GET` | `/business/catalog/categories/tree` | `Authorization: Bearer ...` + acting headers | no body | `list[CategoryTreeNode]` |

---

## Real Auth Rules
- `root` = global authority
- `chief_storekeeper` = site-level admin for catalog and device/site admin basics
- `storekeeper` = operational user
- `observer` = read-only user
- device routes do not use user roles; they use registered device token

---

## Verified Endpoints

Verified in repository tests:
- `POST /api/v1/ping`
- `POST /api/v1/push`
- `POST /api/v1/pull`
- `POST /api/v1/catalog/items` (legacy device-auth read)
- `POST /api/v1/catalog/admin/units`
- `POST /api/v1/catalog/admin/categories`
- `POST /api/v1/catalog/admin/items`
- `PATCH /api/v1/catalog/admin/items/{item_id}`
- `PATCH /api/v1/catalog/admin/categories/{category_id}` including cycle validation
- `GET /api/v1/auth/me` (no token leak in normal response)
- `POST /api/v1/auth/sync-user`
- `PUT /api/v1/admin/users/{user_id}/scopes`
- `GET /api/v1/admin/users/{user_id}/sync-state`
- `POST /api/v1/admin/users/{user_id}/rotate-token`

Verification sources:
- `tests/test_http_sync.py`
- `tests/test_auth_routes.py`
- `tests/test_user_admin_flow.py`

---

## TODO

High-priority verification TODO:
- dedicated tests for `/admin/sites`
- dedicated tests for `/admin/users` CRUD
- dedicated tests for `/admin/access/scopes`
- dedicated tests for `/admin/devices` and device token rotation
- dedicated tests for primary `GET /catalog/items|categories|units|sites|categories/tree`
- dedicated tests for `/catalog/read/*`
- dedicated tests for `/operations/*`
- dedicated tests for `/balances*`
- dedicated tests for `/temporary-items/*`
- dedicated tests for `/documents/*`
- dedicated tests for `/recipients/*`
- dedicated tests for `/pending-acceptance`, `/lost-assets/*`, `/issued-assets`
- dedicated tests for `/reports/*`
- dedicated tests for `/health`, `/ready`, `/health/detailed`, `/health/readiness`, `/health/liveness`
- dedicated tests for `/bootstrap/sync`
- dedicated tests for `/business/*` legacy compatibility routes
- dedicated tests for `/` and `/db_check`

Documentation TODO:
- keep `docs/API_REFERENCE.md` and this file in sync when routes change
- keep `docs/ENDPOINT_INVENTORY.md` synchronized with actual router set

Environment TODO:
- stabilize test database setup so the endpoint verification suite can be run end-to-end without manual DB preparation
