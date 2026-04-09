# API Map

Practical technical map of how to talk to SyncServer.

Use this file when you need:
- real endpoint paths
- real headers
- auth expectations
- request / response shape overview
- current verification status
- TODO areas

Full client-facing examples still live in `docs/API_REFERENCE.md`.
Flat inventory of all routes lives in `docs/ENDPOINT_INVENTORY.md`.

## Base
- Base prefix: `/api/v1`
- OpenAPI docs: `/api/docs`
- OpenAPI JSON: `/api/openapi.json`

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
- `Authorization: Bearer <service_token>`
  - legacy compatibility only, used by `/business/*`
- `X-Acting-User-Id`
- `X-Acting-Site-Id`
  - legacy compatibility only, used by `/business/*`

### Common request header
- `Content-Type: application/json`

## Auth Modes

| Mode | Real Header(s) | Where Used |
|---|---|---|
| User token | `X-User-Token` | primary app/admin/catalog/operations/balances |
| Device token | `X-Device-Token` | sync and legacy catalog read |
| Service token | `Authorization: Bearer ...` | legacy `/business/*` only |

## Endpoint Groups

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
| `POST` | `/admin/devices` | `X-User-Token` | `DeviceCreate` | `DeviceResponse` |
| `PATCH` | `/admin/devices/{device_id}` | `X-User-Token` | `DeviceUpdate` | `DeviceResponse` |
| `POST` | `/admin/devices/{device_id}/rotate-token` | `X-User-Token` | no body | `{device_id, device_token, generated_at}` |

### Catalog Read API

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `GET` | `/catalog/items` | `X-User-Token` | query: `updated_after`, `limit`, `site_id` | `{items, server_time, next_updated_after}` |
| `GET` | `/catalog/categories` | `X-User-Token` | query: `updated_after`, `limit`, `site_id` | `{categories, server_time, next_updated_after}` |
| `GET` | `/catalog/categories/tree` | `X-User-Token` | query: `site_id` | `list[CategoryTreeNode]` |
| `GET` | `/catalog/units` | `X-User-Token` | query: `updated_after`, `limit`, `site_id` | `{units, server_time, next_updated_after}` |
| `GET` | `/catalog/sites` | `X-User-Token` | query: `is_active` | `{sites, server_time}` |

Notes:
- `site_id` on catalog read is currently an access-context check, not a true data partition for items/categories/units.
- `root`, `chief_storekeeper`, `storekeeper`, `observer` can read if access rules pass.

### Catalog Admin API

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `POST` | `/catalog/admin/units` | `X-User-Token` | `{name, symbol, sort_order, is_active}` | `UnitResponse` |
| `PATCH` | `/catalog/admin/units/{unit_id}` | `X-User-Token` | partial unit payload | `UnitResponse` |
| `POST` | `/catalog/admin/categories` | `X-User-Token` | `{name, code, parent_id, sort_order, is_active}` | `CategoryResponse` |
| `PATCH` | `/catalog/admin/categories/{category_id}` | `X-User-Token` | partial category payload | `CategoryResponse` |
| `POST` | `/catalog/admin/items` | `X-User-Token` | `{sku, name, category_id, unit_id, description, is_active}` | `ItemResponse` |
| `PATCH` | `/catalog/admin/items/{item_id}` | `X-User-Token` | partial item payload | `ItemResponse` |

Notes:
- `root` may call these without `X-Site-Id`.
- `chief_storekeeper` must send `X-Site-Id` and have `can_manage_catalog=true` on that site.
- `storekeeper` and `observer` cannot mutate catalog.

### Operations API

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `GET` | `/operations` | `X-User-Token` | query: `site_id`, `type`, `status`, `created_by_user_id`, `created_after`, `created_before`, `updated_after`, `updated_before`, `search`, `page`, `page_size` | `{items, total_count, page, page_size}` |
| `GET` | `/operations/{operation_id}` | `X-User-Token` | no body | `OperationResponse` |
| `POST` | `/operations` | `X-User-Token` | `OperationCreate` | `OperationResponse` |
| `PATCH` | `/operations/{operation_id}` | `X-User-Token` | `OperationUpdate` | `OperationResponse` |
| `POST` | `/operations/{operation_id}/submit` | `X-User-Token` | `{submit: true}` | `OperationResponse` |
| `POST` | `/operations/{operation_id}/cancel` | `X-User-Token` | `{cancel: true, reason}` | `OperationResponse` |

Notes:
- Read roles: `root`, `chief_storekeeper`, `storekeeper`, `observer`
- Write roles: `root`, `chief_storekeeper`, `storekeeper`
- MOVE requires both `source_site_id` and `destination_site_id`

### Balances API

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `GET` | `/balances` | `X-User-Token` | query: `site_id`, `item_id`, `category_id`, `search`, `only_positive`, `page`, `page_size` | `{items, total_count, page, page_size}` |
| `GET` | `/balances/by-site` | `X-User-Token` | query: `site_id`, `only_positive`, `page`, `page_size` | `{items, total_count, page, page_size}` |
| `GET` | `/balances/summary` | `X-User-Token` | no body | `{accessible_sites_count, summary}` |

Notes:
- Read roles: `root`, `chief_storekeeper`, `storekeeper`, `observer`
- Non-root users only see balances for accessible sites

### Device Sync API

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `POST` | `/ping` | `X-Device-Token` | `{site_id, device_id, last_server_seq, outbox_count, client_time}` | `{server_seq_upto, backoff_seconds}` |
| `POST` | `/push` | `X-Device-Token` | `{site_id, device_id, batch_id, events:[...]}` | `{accepted, duplicates, rejected, server_seq_upto?}` |
| `POST` | `/pull` | `X-Device-Token` | `{site_id, device_id, since_seq, limit}` | `{events, next_since_seq, server_seq_upto}` |

### Health API

| Method | Path | Auth | Request | Response |
|---|---|---|---|---|
| `GET` | `/health` | none | no body | health payload |
| `GET` | `/ready` | none | no body | readiness payload |

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

## Real Auth Rules
- `root` = global authority
- `chief_storekeeper` = site-level admin for catalog and device/site admin basics
- `storekeeper` = operational user
- `observer` = read-only user
- device routes do not use user roles; they use registered device token

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

## TODO

High-priority verification TODO:
- dedicated tests for `/admin/sites`
- dedicated tests for `/admin/users` CRUD
- dedicated tests for `/admin/access/scopes`
- dedicated tests for `/admin/devices` and device token rotation
- dedicated tests for primary `GET /catalog/items|categories|units|sites|categories/tree`
- dedicated tests for `/operations/*`
- dedicated tests for `/balances*`
- dedicated tests for `/health` and `/ready`
- dedicated tests for `/business/*` legacy compatibility routes

Documentation TODO:
- keep `docs/API_REFERENCE.md` and this file in sync when routes change
- keep `docs/ENDPOINT_INVENTORY.md` synchronized with actual router set

Environment TODO:
- stabilize test database setup so the endpoint verification suite can be run end-to-end without manual DB preparation
