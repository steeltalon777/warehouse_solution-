# TZ: Nomenclature Batch Catalog CRUD

## Execution Strategy

- [ ] 🟢 Parallel execution recommended
- **Reason:** работа делится на независимые владельческие области: `SyncServer` владеет атомарным применением справочников, `Warehouse_web` владеет same-origin BFF/CSRF/session proxy, `Warehouse_frontend` владеет локальным Angular buffer/UI. После фиксации общего API-контракта эти области можно делать параллельно, а затем выполнить общий integration checkpoint.

### Parallel work units

#### Stage 0 — shared contract checkpoint, sequential

- Owner: parent/orchestrator or first executor.
- Inputs:
  - this TZ;
  - `Functional and WorkLogik.md`, lines 11-16 and 91-105;
  - `Warehouse_frontend/docs/ARCHITECTURE_FRONTEND_SPA.md`;
  - `Warehouse_frontend/docs/screens_plan/nomenclature-screen-spec.md`.
- Output: confirm final JSON contract for `POST /api/v1/catalog/admin/batch` and `POST /bff/api/v1/catalog/admin/batch` before code edits in Stage 1.

#### Stage 1A — SyncServer atomic catalog batch

- Writable area: `SyncServer/app/schemas/catalog.py`, `SyncServer/app/services/catalog_admin_service.py`, `SyncServer/app/api/routes_catalog_admin.py`, relevant SyncServer tests/docs.
- Do not edit: Django or Angular files.
- Required output: one atomic mixed batch endpoint for units, categories, and items/TMC.
- Verification: SyncServer unit/service/API/integration tests.

#### Stage 1B — Django BFF catalog batch proxy

- Writable area: `Warehouse_web/apps/sync_client/catalog_api.py`, `Warehouse_web/apps/bff_api/catalog_views.py`, `Warehouse_web/apps/bff_api/urls.py`, relevant Django tests/docs.
- Do not edit: SyncServer domain logic or Angular UI.
- Required output: browser-facing same-origin BFF endpoint that forwards one batch to SyncServer and never exposes SyncServer tokens.
- Verification: Django tests with mocked sync client plus BFF error mapping tests.

#### Stage 1C — Angular local staged CRUD UI

- Writable area: `Warehouse_frontend/src/app/core/models/`, `Warehouse_frontend/src/app/core/services/`, `Warehouse_frontend/src/app/features/nomenclature/`, relevant Angular tests/docs.
- Do not edit: Django or SyncServer files.
- Required output: enabled creation/editing for category, TMC, and unit of measure, with changes visible only in Angular until “Применить все”.
- Verification: Angular build/component tests and Playwright smoke through Django after integration.

#### Stage 2 — integration and verification, sequential

- Owner: parent/orchestrator or final executor.
- Required output: end-to-end proof that Angular sends exactly one BFF batch on apply, Django forwards exactly one SyncServer batch, SyncServer commits atomically, and failed batches leave DB unchanged.

## Execution Checklist

- [x] 0. Context verified
- [x] 1. Architecture boundaries confirmed
- [x] 2. Implementation stage 1 complete — SyncServer atomic batch endpoint
- [x] 3. Implementation stage 2 complete — Django BFF batch proxy
- [x] 4. Implementation stage 3 complete — Angular local CRUD and unit UI
- [x] 5. Unit/component tests complete
- [x] 6. Integration tests with real dependencies complete
- [x] 7. Stand smoke tests complete
- [x] 8. UI automation tests complete (Playwright: 4 сценария)
- [x] 9. User scenario tests complete
- [x] 10. Regression checks complete
- [x] 11. Documentation updated — TZ serves as spec; no separate doc changes required
- [x] 12. Final acceptance review complete — accepted 2026-06-10

## Check Rules

- Architect creates this checklist and acceptance criteria.
- Executor agents may check implementation/test items only after implementation and required verification evidence are complete.
- QA verifier may check final acceptance only after reviewing evidence.
- Failed, skipped, or unavailable checks stay unchecked with a blocker note.
- Real-stand checks must follow the repository Stand Availability Protocol: probe health endpoints first, do not start the stand automatically, and leave the item unchecked with `стенд недоступен` if unavailable.

---

## 1. Problem Statement

User-reported current problem:

- Category creation in Angular nomenclature is blocked.
- TMC/item creation in Angular nomenclature is blocked.
- Unit-of-measure creation is absent from Angular nomenclature.
- Required workflow: the user creates/edits all reference/catalog types in Angular, sees changes only in Angular, then presses “Применить все”; only then a batch reaches SyncServer and the DB is changed.

Current code findings:

- `Warehouse_frontend/src/app/features/nomenclature/action-buttons/action-buttons.ts` hard-disables `+ Категория` and `+ ТМЦ`.
- `Warehouse_frontend/src/app/features/nomenclature/nomenclature-page/nomenclature-page.ts` has update/deactivate/delete buffering, but no create handlers.
- `Warehouse_frontend/src/app/features/nomenclature/right-panel/right-panel.ts` supports item/category forms only; no unit-management UI.
- `Warehouse_frontend/src/app/core/services/nomenclature.service.ts` has `applyBatch(changes)`, but it sends sequential per-entity requests to legacy `/nomenclature/api/*`, not one SyncServer batch.
- `Warehouse_web/apps/bff_api/catalog_views.py` already has admin CRUD endpoints for units/categories/items and bulk create for units/categories, but no mixed catalog batch endpoint.
- `Warehouse_web/apps/catalog/api_views.py` is a legacy `/nomenclature/api/*` path with only `LoginRequiredMixin`; new Angular writes must move to `/bff/api/v1/*` and explicit catalog-admin checks.
- `SyncServer/app/api/routes_catalog_admin.py` has per-entity CRUD plus bulk create for units/categories, but no mixed atomic batch endpoint for units + categories + items.

---

## 2. Source Requirements

### Canonical functional requirements

From `Functional and WorkLogik.md`:

- SyncServer validates write permissions (`I.2`, `I.2.1.*`).
- Chief storekeeper can edit catalogs; root has chief capabilities plus administration (`I.2.1.3`, `I.2.1.4`).
- Nomenclature is the SPA screen for catalog work and is visible to chief storekeepers/root, not regular users (`VIII.4.3.2`).
- Catalog readonly screen remains separate for all users (`VIII.4.3.1`).
- Angular is hosted through Django and server/client requests go through Django with user/device token headers on the server side (`IX.3`, `IX.6`).

### Architecture requirements

- SyncServer is the source of truth for warehouse domain data and catalog writes.
- Django stores only technical web state and acts as shell/BFF; it must not become a second catalog backend.
- Angular/browser code calls same-origin Django BFF only.
- Angular must not receive or store SyncServer user/device tokens.
- Django-hosted Angular content must keep the Django shell and business URL `/nomenclature/`.

### Existing UI specification

`Warehouse_frontend/docs/screens_plan/nomenclature-screen-spec.md` already requires:

- local change buffer;
- dirty/error states;
- “Применить”/“Применить все” behavior;
- category and item/TMC editing;
- pending changes kept on failure.

This TZ upgrades the old MVP idea of sequential requests to the user-required server-side batch apply.

---

## 3. Architecture Decision

### Target flow

```text
Browser /nomenclature/
  -> Angular local state and pending catalog change buffer
  -> user clicks “Применить все”
  -> POST /bff/api/v1/catalog/admin/batch
  -> Warehouse_web sync_client CatalogAPI.apply_catalog_batch(...)
  -> POST /api/v1/catalog/admin/batch
  -> SyncServer CatalogAdminService.apply_batch(...)
  -> one UnitOfWork transaction
  -> DB commit only if the whole batch succeeds
```

### Core behavior

- Create/edit/deactivate actions for categories, items/TMC, and units are staged in Angular only.
- Staged creates are visible immediately in Angular tree/forms/selects using local temporary IDs.
- No catalog write request is sent while the user edits fields or clicks “Добавить в изменения”.
- “Применить все” sends exactly one browser request to Django BFF.
- Django sends exactly one request to SyncServer.
- SyncServer applies the mixed batch atomically in one transaction.
- On success Angular clears the pending buffer, reloads authoritative data, and replaces local IDs with server IDs.
- On failure Angular keeps the pending buffer and marks failed rows/forms with errors; DB must remain unchanged.

### API surface

SyncServer primary API:

```http
POST /api/v1/catalog/admin/batch
```

Django browser-facing BFF API:

```http
POST /bff/api/v1/catalog/admin/batch
```

Angular must use the BFF path. New Angular mutation code must not call legacy `/nomenclature/api/*` mutation endpoints.

---

## 4. Batch Contract

### Request

```json
{
  "client_batch_id": "catalog-ui-2026-05-22T12:00:00.000Z-abc123",
  "mode": "atomic",
  "changes": [
    {
      "local_id": "unit:tmp-1",
      "entity_type": "unit",
      "action": "create",
      "payload": {
        "name": "Штука",
        "symbol": "шт",
        "sort_order": 10,
        "is_active": true
      }
    },
    {
      "local_id": "category:tmp-1",
      "entity_type": "category",
      "action": "create",
      "payload": {
        "name": "Кабельная продукция",
        "code": "CABLE",
        "parent_id": null,
        "sort_order": 10,
        "is_active": true
      }
    },
    {
      "local_id": "category:tmp-2",
      "entity_type": "category",
      "action": "create",
      "payload": {
        "name": "Витая пара",
        "parent_local_id": "category:tmp-1",
        "sort_order": 20,
        "is_active": true
      }
    },
    {
      "local_id": "item:tmp-1",
      "entity_type": "item",
      "action": "create",
      "payload": {
        "name": "UTP Cat5e 305м",
        "sku": "CBL-UTP-5E-305",
        "category_local_id": "category:tmp-2",
        "unit_local_id": "unit:tmp-1",
        "description": "Бухта кабеля UTP Cat5e 305м",
        "hashtags": ["кабель", "витая пара", "cat5e", "utp"],
        "is_active": true
      }
    },
    {
      "local_id": "item:42",
      "entity_type": "item",
      "entity_id": 42,
      "action": "update",
      "payload": {
        "name": "Обновлённое название",
        "unit_id": 1,
        "category_id": 2,
        "hashtags": ["обновлено"]
      }
    }
  ]
}
```

### Request rules

- `mode` supports only `atomic` in this TZ.
- `changes` must contain at least one change.
- `local_id` is required and unique inside the batch.
- `entity_type` values: `unit`, `category`, `item`.
- `action` values: `create`, `update`, `deactivate`, `delete`.
- `entity_id` is required for `update`, `deactivate`, and `delete`.
- `entity_id` is forbidden for `create`.
- Creates may reference previously staged creates using:
  - `parent_local_id` for category parent;
  - `category_local_id` for item category;
  - `unit_local_id` for item unit.
- A payload must not include both existing and local reference for the same field, for example both `unit_id` and `unit_local_id`.
- Physical `delete` is lower priority than create/update/deactivate. If delete behavior is not fully covered, Angular must disable delete and use deactivate only.

### Response success

```json
{
  "client_batch_id": "catalog-ui-2026-05-22T12:00:00.000Z-abc123",
  "mode": "atomic",
  "status": "applied",
  "summary": {
    "create": 4,
    "update": 1,
    "deactivate": 0,
    "delete": 0,
    "error": 0
  },
  "records": [
    {
      "local_id": "unit:tmp-1",
      "entity_type": "unit",
      "action": "create",
      "status": "applied",
      "entity_id": 11
    },
    {
      "local_id": "category:tmp-1",
      "entity_type": "category",
      "action": "create",
      "status": "applied",
      "entity_id": 101
    }
  ],
  "server_time": "2026-05-22T12:00:01Z"
}
```

### Response error

Use controlled JSON errors with no token data:

```json
{
  "detail": "catalog batch validation failed",
  "errors": [
    {
      "local_id": "item:tmp-1",
      "entity_type": "item",
      "action": "create",
      "code": "unit_not_found",
      "message": "unit_local_id unit:tmp-404 was not found in batch result"
    }
  ]
}
```

HTTP status guidance:

- `400` invalid shape, duplicate local IDs, unresolved local references, category create cycle.
- `403` insufficient catalog-admin permission.
- `404` referenced existing entity is missing.
- `409` domain conflict: duplicate SKU/name/symbol, frozen item, active entity delete, reserved category code.
- `422` Pydantic/schema validation errors.

---

## 5. SyncServer Implementation Requirements

### Files in scope

- `SyncServer/app/schemas/catalog.py`
- `SyncServer/app/services/catalog_admin_service.py`
- `SyncServer/app/api/routes_catalog_admin.py`
- SyncServer tests under the existing test layout.

### Required changes

1. Add Pydantic schemas for the mixed batch request/response.
2. Add route `POST /catalog/admin/batch` under existing `router = APIRouter(prefix="/catalog/admin")`.
3. Route remains thin:
   - depends on `require_user_identity`;
   - opens `async with uow`;
   - calls existing `_require_catalog_admin(identity)`;
   - delegates to `CatalogAdminService.apply_batch(...)`;
   - maps response to schema.
4. Add `CatalogAdminService.apply_batch(uow, payload, identity)` or equivalent.
5. Reuse existing service methods where possible:
   - `create_unit`, `update_unit`, `delete_unit`;
   - `create_category`, `update_category`, `delete_category`;
   - `create_item`, `update_item`, `delete_item`.
6. Keep all DB mutation inside the same `UnitOfWork`. Any exception must rollback the whole batch.
7. Resolve local references after successful creates and before dependent changes.
8. Validate new category parent graph before applying:
   - no missing local parent;
   - no cycles among newly-created categories;
   - no self-parent.
9. Apply deterministic dependency order:
   - units create/update/deactivate;
   - categories create in topological parent order, then category update/deactivate;
   - items create/update/deactivate;
   - optional physical delete last in safe order: items, categories, units.
10. Preserve existing business rules:
    - chief/root only;
    - unit name/symbol uniqueness;
    - reserved uncategorized category code protection;
    - sibling category name uniqueness;
    - item SKU uniqueness;
    - item freeze protection from active lost assets;
    - delete only when existing service rules allow it.

### Acceptance criteria

- A mixed batch creating unit + parent category + child category + item succeeds in one request.
- The created item may reference the newly-created category/unit by local IDs.
- A failing item create rolls back the unit/category creates in the same batch.
- A category cycle through local IDs is rejected before DB mutation.
- A duplicate unit symbol or item SKU returns controlled conflict and rolls back all changes.
- Storekeeper/observer tokens are rejected with `403`.
- Existing per-entity CRUD endpoints keep working.

---

## 6. Django BFF Implementation Requirements

### Files in scope

- `Warehouse_web/apps/sync_client/catalog_api.py`
- `Warehouse_web/apps/bff_api/catalog_views.py`
- `Warehouse_web/apps/bff_api/urls.py`
- Relevant Django tests.

### Required changes

1. Add sync client method:

```python
CatalogAPI.apply_catalog_batch(payload: dict[str, Any], *, acting_user_id=None, acting_site_id=None) -> dict[str, Any]
```

It must call SyncServer:

```http
POST /catalog/admin/batch
```

2. Add BFF route:

```python
path("catalog/admin/batch", catalog_views.AdminCatalogBatchView.as_view(), name="catalog_admin_batch")
```

3. Add `AdminCatalogBatchView.post`:
   - `LoginRequiredMixin`;
   - explicit `_require_chief_or_root(request.user)` before proxying;
   - parse JSON with `json.JSONDecodeError` handling;
   - call `api.apply_catalog_batch(payload)` through `_catalog(request)`;
   - wrap success in existing `_ok(data)` envelope;
   - map `SyncServerAPIError` through `_handle_sync_error`;
   - do not log payload values that may contain sensitive descriptions/comments beyond safe IDs/counts.
4. Harden or retire legacy Angular mutation paths:
   - Angular must stop using `/nomenclature/api/{categories|items|units}/` for writes.
   - If legacy mutation endpoints remain, they must enforce chief/root or be documented as SSR-only fallback with equivalent permission checks.
5. Ensure BFF responses never expose `X-User-Token`, `X-Device-Token`, root token, or device token.

### Acceptance criteria

- Django test proves `POST /bff/api/v1/catalog/admin/batch` calls `CatalogAPI.apply_catalog_batch` once with the request payload.
- Non-authenticated request returns login/401 behavior according to existing BFF conventions.
- Non-chief/non-root authenticated user receives `403` before SyncServer call.
- SyncServer `409/422/403` errors are preserved in the BFF error envelope.
- Existing read endpoints used by the nomenclature screen still work.

---

## 7. Angular Implementation Requirements

### Files/areas in scope

- `Warehouse_frontend/src/app/core/models/nomenclature.models.ts`
- `Warehouse_frontend/src/app/core/services/nomenclature.service.ts`
- `Warehouse_frontend/src/app/core/services/catalog-change-buffer.service.ts`
- `Warehouse_frontend/src/app/features/nomenclature/`
- Angular tests/specs for changed components/services.

### Required UI behavior

1. Enable create controls for users with catalog-admin permission:
   - `+ Категория`;
   - `+ ТМЦ`;
   - add `+ Ед. изм.` or an equivalent visible unit-management entry.
2. Category creation:
   - default parent is selected category if any;
   - if selected item, default parent is the item category;
   - user can change parent;
   - new category appears in the tree immediately with dirty/local-only state.
3. TMC/item creation:
   - default category is selected/current category;
   - user must choose unit;
   - newly-created local units and categories are selectable before apply;
   - new item appears in the tree immediately with dirty/local-only state.
4. Unit creation/editing:
   - provide unit list/search or clear unit-management mode in the right panel;
   - user can create and edit `name`, `symbol`, `sort_order`, `is_active`;
   - new/edited units are visible in item forms immediately;
   - no server call is made until “Применить все”.
5. Editing existing categories/items/units:
   - form edits remain local until user adds them to changes;
   - dirty badges/states show staged updates;
   - reset draft resets selected form only;
   - reset all clears full pending buffer and local-only entities.
6. Apply:
   - build one mixed batch request matching this TZ contract;
   - send one `POST /bff/api/v1/catalog/admin/batch` request;
   - disable apply while saving;
   - on success clear buffer and reload authoritative bootstrap/read data;
   - on failure keep buffer and show row/form errors.
7. Permissions:
   - if current user cannot manage catalog, create/edit/apply controls are hidden or disabled with a clear message;
   - Angular must not rely on UI permission only; BFF/SyncServer remain authoritative.

### Suggested component additions

- `unit-edit-form` for unit create/update.
- `unit-list` or `unit-management-panel` so users can select existing units for edit.
- Extend `right-panel` selection mode to include `unit` and create modes.
- Extend tree node/VM state with `localOnly`, `pendingAction`, and `error` if not already sufficient.

### Local ID rules

- Use stable local IDs during one page session, for example:
  - `unit:tmp-<uuid>`;
  - `category:tmp-<uuid>`;
  - `item:tmp-<uuid>`.
- Local IDs must be stored in `CatalogPendingChange.localId` and referenced from dependent payload fields.
- Existing server IDs remain numeric/string server IDs and must not be confused with local IDs.
- The UI must be able to display a local item whose category or unit is also local-only.

### Acceptance criteria

- Category creation is no longer disabled for chief/root and creates a local dirty category without a network write.
- TMC creation is no longer disabled for chief/root and creates a local dirty item without a network write.
- Unit creation/editing exists in Angular and updates item unit selects locally.
- Editing existing category/item/unit does not call backend until apply.
- One apply click sends one BFF batch, not N sequential per-entity requests.
- Failed apply keeps local changes visible and actionable.
- Successful apply reloads server data and clears dirty/local-only states.

---

## 8. Out of Scope

- Direct browser calls to SyncServer.
- Direct Django DB access to SyncServer catalog tables.
- Moving Django shell/navigation into Angular.
- Offline/mobile/desktop client synchronization.
- Merge/split of items/categories unless already required by existing buttons.
- Full persisted idempotency for retry-after-timeout unless the executor explicitly reuses an existing batch table safely. `client_batch_id` is required for traceability but not accepted as proof of idempotent replay unless implemented and tested.
- Physical delete UX unless all backend delete rules and tests are completed. Deactivation is sufficient for this TZ MVP.

---

## 9. Test Strategy

### Static checks

Required:

```bash
cd SyncServer && python -m pytest --collect-only
cd Warehouse_web && python manage.py check
cd Warehouse_frontend && npm run build
```

If frontend unit-test tooling is configured and stable, also run:

```bash
cd Warehouse_frontend && npm run test -- --watch=false
```

### Unit tests

SyncServer:

- Batch schema validation: duplicate local IDs, missing local refs, forbidden `entity_id` on create.
- Category local parent topological sort and cycle rejection.
- Batch service rollback on conflict.
- Permission rejection for non catalog-admin identity.

Django:

- BFF parses valid JSON and calls sync client once.
- Invalid JSON returns controlled `400`.
- Non-chief/non-root does not call sync client.
- SyncServer errors map to BFF error envelope.

Angular:

- Change buffer stores create/update/deactivate for all three entity types.
- Local category/item/unit projection updates tree/forms/selects without HTTP.
- Newly staged categories and units are immediately available in parent/category/unit selectors before apply.
- Batch payload maps local IDs/references correctly.
- Apply success clears buffer; apply failure preserves buffer.

### Component tests

Angular component tests for:

- action buttons emit create category/item/unit events;
- category create/edit form validation;
- item create/edit form requires name, unit, category, while SKU stays optional;
- unit create/edit form requires name and symbol;
- pending changes bar disables apply while saving.

Django component/view tests:

- BFF view permission and error behavior.

### Integration tests with real dependencies

SyncServer DB-backed tests:

- PostgreSQL or the project’s real integration DB fixture, migrated schema.
- Create unit + category + child category + item in one batch and verify persisted rows.
- Force duplicate SKU after earlier valid changes in the same batch and verify none persisted.
- Update frozen item and verify `409` with rollback.

Django integration tests:

- Django test client authenticated as chief/root posts BFF batch with mocked or test SyncServer client.
- If local SyncServer test service is available, run through real `SyncServerClient` against the migrated test DB.

### Real stand smoke tests

Follow the Stand Availability Protocol before these checks.

Health probes:

```bash
curl -fsS http://localhost:8000/api/v1/health
curl -fsS http://localhost:8001/healthz/
```

Smoke goals:

- Open `http://localhost:8001/nomenclature/` as chief/root.
- Load bootstrap/read data successfully.
- Create local unit/category/TMC and verify no write request before apply.
- Click “Применить все” and verify one BFF batch request succeeds.
- Reload page and verify created data comes from server.

### UI automation

Use Playwright for web UI through Django business URL `/nomenclature/`.

Required Playwright scenarios:

1. Chief/root creates unit + category + TMC locally; dirty states appear; no network write until apply.
2. Apply sends exactly one `POST /bff/api/v1/catalog/admin/batch` and no legacy sequential `/nomenclature/api/*` mutation calls.
3. Server validation error keeps pending changes and displays error state.
4. Non-chief/non-root user cannot access or cannot use catalog write controls.

### User scenarios

- “Новый справочник с нуля”: create unit, parent category, child category, TMC using the newly-created unit/category, apply, reload, verify all visible.
- “Редактирование существующего”: change unit symbol/name, move category, update item SKU/hashtags, apply, verify server values.
- “Ошибка без частичного сохранения”: create valid unit/category and invalid duplicate item SKU in same batch; apply fails; reload server data and verify unit/category were not created.

### Regression pack

- Existing catalog readonly browse/search still works.
- Existing SSR fallback under `/nomenclature/ssr/` still works if retained.
- Operation item search still sees committed catalog data after apply.
- Temporary item convert/merge flows still receive category/unit lists.
- Existing SyncServer per-entity catalog admin CRUD tests still pass.

---

## 10. Real Test Stand Requirement

### Database

- SyncServer PostgreSQL test DB, migrated with Alembic to head.
- Django test DB for BFF/session tests.
- PostgreSQL runs locally in Docker at `localhost:5432`; legacy VM database tunnel is obsolete.
- No destructive DB reset without user approval and backup recommendation.

### Seed data

- Root user.
- Chief storekeeper user.
- Storekeeper or observer without catalog-admin rights.
- Django device token/user binding configured through environment.
- Existing active unit, category, and item.
- One item with active lost asset balance to verify freeze protection if the test suite can seed it safely.

### Services to start

- SyncServer API at `http://localhost:8000`.
- Django at `http://localhost:8001` hosting Angular build/assets.
- Angular dev server at `http://localhost:4200` when the Docker stand runs frontend separately.
- PostgreSQL reachable at `localhost:5432` through the configured safe test DB connection.

### Environment variable names only

- `DJANGO_ENV`
- `SYNC_SERVER_URL`
- `SYNC_ROOT_USER_TOKEN`
- `SYNC_DEVICE_TOKEN`
- `DATABASE_URL`
- `DJANGO_SETTINGS_MODULE`
- `SECRET_KEY`

### Health checks

- `GET http://localhost:8000/api/v1/health`
- `GET http://localhost:8001/healthz/`
- `GET http://localhost:4200/` when Angular dev server is used.
- `pg_isready -h localhost -p 5432 -t 3`
- `GET http://localhost:8001/nomenclature/`
- `GET http://localhost:8001/bff/api/v1/catalog/categories/tree` or existing authenticated equivalent.

### Reset/cleanup procedure

- Prefer isolated test DB or test-specific seed prefix/SKU values.
- If a real shared stand is used, create unique names/SKUs with a test run prefix and clean them through approved catalog admin endpoints only.
- Do not run broad `DROP`, `TRUNCATE`, or `DELETE` without explicit user approval.

---

## 11. Evidence Required From Executors

Every completion report must include this table:

```markdown
## Evidence

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|
| SyncServer tests | `python -m pytest ...` | pass/fail/skipped | log path or summary |
| Django tests | `python manage.py test ...` | pass/fail/skipped | log path or summary |
| Angular build/tests | `npm run build`, `npm run test -- --watch=false` | pass/fail/skipped | log path or summary |
| DB integration | `<command>` | pass/fail/skipped | DB/fixture note |
| Stand smoke | `curl`/browser | pass/fail/skipped | URL/log/screenshot |
| UI automation | Playwright | pass/fail/skipped | report path |
```

---

## 12. Final Acceptance Criteria

- Categories, TMC/items, and units can all be created and edited from Angular nomenclature by chief/root users.
- Until apply, catalog changes are visible only in Angular local state and do not mutate SyncServer DB.
- “Применить все” sends one BFF batch and one SyncServer batch.
- SyncServer applies the batch atomically or rolls back all changes.
- Angular handles server-created IDs and reloads authoritative data after success.
- Permission checks are enforced in UI, Django BFF, and SyncServer.
- No SyncServer tokens are exposed to browser code, templates, logs, or responses.
- Required static, unit/component, integration, stand, UI automation, user scenario, and regression checks have evidence or explicit blocker notes.
