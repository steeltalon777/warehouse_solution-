# ADR-0005: Token Auth And Site-Scoped Access

## Status
Accepted

## Context
The repository supports browser users, root administrators, desktop application users, and device or integration clients. The backend contains explicit identity resolution for `X-User-Token` and `X-Device-Token`, plus `UserAccessScope` for per-site permissions. A consistent auth model is needed across multiple client types.

## Evidence
- `SyncServer/app/api/deps.py` — FastAPI dependencies resolve `X-User-Token` and `X-Device-Token` headers
- `SyncServer/app/models/user.py` — User entity with `user_token` (UUID), `role` (root/chief_storekeeper/storekeeper/observer)
- `SyncServer/app/models/device.py` — Device entity with `device_token` (UUID)
- `SyncServer/app/models/user_access_scope.py` — Per-site permissions: `can_view`, `can_operate`, `can_manage_catalog`
- `SyncServer/app/services/identity_service.py` — Identity resolution, token validation, sync-user flow
- `SyncServer/app/services/access_service.py` — Access control based on role + site-scoped access records
- `SyncServer/app/api/routes_auth.py` — `/auth/sync-user` (root-only), `/auth/me`, `/auth/context` endpoints
- `SyncServer/app/repos/user_access_scopes_repo.py` — Scope management queries
- `Warehouse_web/apps/sync_client/client.py` — Base client sends `X-User-Token` header
- `Warehouse_web/apps/sync_client/session_auth.py` — Session-to-token binding
- `Warehouse_web/apps/users/models.py` — `SyncUserBinding` maps Django user to SyncServer user + token
- `Warehouse_web/.env` — `SYNC_ROOT_USER_TOKEN` for root flows, `SYNC_DEVICE_TOKEN` for device flows
- `WarehouseAIWorkstation/src/Integrations.Sync/` — `AuthContextClient` sends user token headers
- `SyncServer/app/api/routes_sync.py` — Device sync routes use `X-Device-Token`, not user tokens
- `Role Matrix.md` — Documents 4-role permission matrix
- `SyncServer/tests/test_auth_routes.py` — Tests verify auth flows and token handling
- `SyncServer/tests/test_access_service_business_access.py` — Tests verify site-scoped access rules

## Decision
`SyncServer` uses token-based authentication for both user and device contexts:
- `X-User-Token` for user-driven flows (catalog, operations, admin, balances)
- `X-Device-Token` for device sync flows (ping, push, pull)
- Root access is global (no site scoping)
- Non-root access is site-scoped through `UserAccessScope` (permission flags per site)
- `Warehouse_web` resolves root flows from environment tokens and runtime user flows from `SyncUserBinding`
- `WarehouseAIWorkstation` and other desktop clients use user tokens from their own configuration

## Consequences

### Pros
- One consistent auth model across multiple client types
- Explicit site-scoped permissions for non-root users
- Device context attachable for sync and audit without user tokens
- Clear separation: user tokens = user identity, device tokens = device identity

### Cons
- Token lifecycle and binding management add operational overhead
- Integrations must supply correct headers and acting context
- Legacy `/business/*` routes use different auth (`Authorization: Bearer`), creating dual auth models
- If sync tokens expire, device sync silently fails

## Alternatives Considered

### Option 1
Use Django session auth as the authoritative warehouse auth model.
Why not chosen: The repository clearly places authoritative identity and access control in `SyncServer`, not in Django sessions. Django is a client.

### Option 2
Use only coarse global roles without site-scoped access records.
Why not chosen: The codebase already models per-site permissions through `UserAccessScope`, and many warehouse flows depend on that granularity (e.g., storekeeper can operate at one site but not another).

## Confidence
- **Confirmed by code** — Token auth headers, UserAccessScope, and role-based access are all implemented in api/services/repos/models
