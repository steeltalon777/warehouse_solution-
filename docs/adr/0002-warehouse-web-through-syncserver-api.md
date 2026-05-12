# ADR-0002: Warehouse_web Through SyncServer API

## Status
Accepted

## Context
`Warehouse_web` provides browser pages, admin tooling, and user interaction flows, but warehouse domain ownership stays in `SyncServer`. The Django project needs a stable way to read and mutate remote warehouse data without coupling itself to backend storage internals.

## Evidence
- `Warehouse_web/apps/sync_client/` — 16 typed HTTP client modules (`client.py`, `auth_api.py`, `admin_api.py`, `catalog_api.py`, `operations_api.py`, `balances_api.py`, `recipients_api.py`, `assets_api.py`, `temporary_items_api.py`, `access_api.py`, `auth_integration.py`, `session_auth.py`, `root_admin_client.py`, `simple_client.py`)
- `Warehouse_web/config/settings/base.py` — Configures `SYNC_SERVER_URL` (must include `/api/v1`), `SYNC_ROOT_USER_TOKEN`, `SYNC_DEVICE_TOKEN` as environment variables
- `Warehouse_web/.env` — Contains actual SyncServer URL and tokens
- `Warehouse_web/apps/users/services.py` — User synchronization uses sync_client, not direct DB
- `Warehouse_web/apps/catalog/services.py`, `operations/services.py` — UI orchestration services use sync_client wrappers
- `ADR-0001` — Establishes SyncServer as source of truth

## Decision
`Warehouse_web` communicates with warehouse domain functionality only through `SyncServer` APIs. HTTP integration is centralized in `Warehouse_web/apps/sync_client/`, and views use that client layer directly or through local service classes.

## Consequences

### Pros
- Clear boundary between UI and domain ownership
- One canonical place for remote calls, headers, and error mapping
- Easier refactoring of views without spreading raw HTTP logic

### Cons
- UI flows depend on backend API availability and compatibility
- Some page flows require extra translation between Django forms and API payloads
- Token management: if `.env` tokens expire, all integration breaks

## Alternatives Considered

### Option 1
Give Django direct database access to warehouse tables.
Why not chosen: Would create tighter coupling and make Django responsible for rules that belong in `SyncServer`.

### Option 2
Allow ad-hoc `httpx` usage directly inside views and admin actions.
Why not chosen: The repository already centralizes remote access in `apps/sync_client`, which is easier to maintain and reason about.

## Confidence
- **Confirmed by code** — All SyncServer HTTP access flows through sync_client modules
