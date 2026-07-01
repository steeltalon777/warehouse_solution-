# TZ: Angular readonly catalog alias and SSR legacy migration

## Execution Strategy

- [ ] 🟢 Parallel execution recommended
- **Reason:** работа естественно делится на независимые зоны владения: Django маршруты/меню, Angular режим readonly/editable, BFF/permission hardening и интеграционная проверка. В первой стадии эти зоны можно выполнять параллельно без записи в одни и те же файлы; общий интеграционный шаг обязателен после параллельной стадии, потому что итог зависит от согласованности URL, меню, Angular route data и прав.

### Parallel work units

#### Stage 0 — shared context gate, sequential

Выполняет родитель/orchestrator до старта параллельных исполнителей.

- Перечитать `Functional and WorkLogik.md`, секция VIII, пункты 4.3.1-4.3.3.
- Перечитать `Warehouse_frontend/docs/ARCHITECTURE_FRONTEND_SPA.md`, особенно Business URL Contract, Django SPA Host Contract, BFF-Only Data Contract и Route Migration Matrix.
- Зафиксировать, что целевое решение не меняет ownership: `SyncServer` владеет каталогом, `Warehouse_web` остаётся Django shell/BFF, `Warehouse_frontend` рендерит только content area.

#### Stage 1A — Django routes, SPA host, sidebar

- **Owner files/areas:**
  - `Warehouse_web/config/urls.py`
  - `Warehouse_web/apps/catalog/urls.py`
  - `Warehouse_web/apps/catalog/views.py`
  - `Warehouse_web/templates/includes/sidebar.html`
  - `Warehouse_web/templates/catalog/nomenclature_spa.html` or a new reusable SPA template under `Warehouse_web/templates/catalog/`
  - `Warehouse_web/templates/catalog/browse_home.html`, `browse_item_list.html`, `browse_category_list.html` only if a visible legacy banner is needed
  - Django route/menu tests in `Warehouse_web/apps/catalog/tests.py` or another existing Django test module
- **Required inputs:** URL target table from this TZ; current route order in `config/urls.py`; existing `NomenclatureSPAView` and `_AngularSpaServeMixin`.
- **Expected output:** `/catalog/` and `/catalog/<path>` render Angular in readonly mode; old SSR catalog is reachable under `/catalog/ssr/...`; sidebar has primary Angular `Каталог`, manager-only `Номенклатура`, and an explicit `SSR / Legacy` section.
- **Verification evidence:** Django URL tests, sidebar rendering tests for manager and non-manager, direct GET checks for `/catalog/`, `/catalog/items/`, `/catalog/ssr/`, `/nomenclature/`.

#### Stage 1B — Angular shared nomenclature screen modes

- **Owner files/areas:**
  - `Warehouse_frontend/src/app/app.routes.ts`
  - `Warehouse_frontend/src/app/features/nomenclature/nomenclature-page/nomenclature-page.ts`
  - `Warehouse_frontend/src/app/features/nomenclature/page-header/page-header.ts`
  - `Warehouse_frontend/src/app/features/nomenclature/action-buttons/action-buttons.ts`
  - `Warehouse_frontend/src/app/features/nomenclature/right-panel/right-panel.ts`
  - `Warehouse_frontend/src/app/features/nomenclature/pending-changes-bar/pending-changes-bar.ts`
  - edit form components under `Warehouse_frontend/src/app/features/nomenclature/*-edit-form/`
  - `Warehouse_frontend/src/app/core/services/nomenclature.service.ts`
  - `Warehouse_frontend/src/app/core/services/catalog-change-buffer.service.ts` if the buffer needs an explicit disabled/readonly guard
  - Angular unit/component tests and Playwright specs under `Warehouse_frontend/src/app/**` and `Warehouse_frontend/e2e/`
- **Required inputs:** route mode from Angular route data or a safe Django-injected non-secret context; user capability from authenticated BFF/bootstrap context; readonly contract from this TZ.
- **Expected output:** the same nomenclature component works in two modes: `/nomenclature/` editable for catalog managers, `/catalog/...` readonly for all client users. In readonly mode no create/update/delete/merge/apply/reset actions are visible or executable.
- **Verification evidence:** `npm run build`, Angular tests for mode computation and component rendering, Playwright screenshots/network evidence for readonly and editable routes.

#### Stage 1C — BFF and legacy mutation permission hardening

- **Owner files/areas:**
  - `Warehouse_web/apps/bff_api/catalog_views.py`
  - `Warehouse_web/apps/catalog/api_views.py`
  - `Warehouse_web/apps/common/permissions.py` only if existing permission helpers are insufficient
  - `Warehouse_web/apps/bff_api/tests.py`
  - `Warehouse_web/apps/catalog/tests.py`
- **Required inputs:** current `can_manage_catalog`/role rules, `API_MAP.md` catalog read/admin contract, current Angular API calls.
- **Expected output:** read endpoints remain available to client users; every mutation endpoint reachable from browser/BFF denies non-managers server-side. The readonly UX is not treated as a security boundary.
- **Verification evidence:** Django tests proving non-manager receives 403 for catalog admin batch and legacy `/nomenclature/api/*` POST/PATCH/DELETE, while root/chief_storekeeper succeeds where applicable.

#### Stage 2 — parent integration and acceptance, sequential

- Merge Stage 1A/1B/1C after checking file ownership conflicts.
- Run the combined test ladder.
- Verify browser behavior on the real stand.
- Update active docs only after implementation is proven: at minimum the route matrix in `Warehouse_frontend/docs/ARCHITECTURE_FRONTEND_SPA.md`; update root index/entry docs only if entry points or verification commands changed.

## Execution Checklist

- [x] 0. Context verified
- [x] 1. Architecture boundaries confirmed
- [x] 2. Implementation stage 1A complete: Django routes, SPA host, sidebar, legacy catalog SSR path
- [x] 3. Implementation stage 1B complete: Angular readonly/editable modes in one nomenclature screen
- [x] 4. Implementation stage 1C complete: BFF and legacy mutation permission hardening
- [x] 5. Implementation stage 2 complete: integration, route matrix/doc updates, conflict review
- [x] 6. Static checks complete
- [x] 7. Unit/component tests complete
- [x] 8. Integration tests with real dependencies complete
- [x] 9. Stand smoke tests complete
- [ ] 10. UI automation tests complete
- [ ] 11. User scenario tests complete
- [ ] 12. Regression checks complete
- [x] 13. Documentation updated
- [ ] 14. Final acceptance review complete

### Executor blocker notes

- UI automation and user scenarios remain partially blocked on the real stand because the prepared non-manager browser fixture (`observer` / `observer123`) is unavailable there; root/manual browser smoke for `/catalog/`, `/catalog/items/`, `/catalog/ssr/`, and `/nomenclature/` was completed.
- Regression checks remain partially blocked because the full frontend unit suite still fails outside this shard in `Warehouse_frontend/src/app/core/services/operations.service.spec.ts` (`mapToRowVm returns correct flags for observer role`), while the targeted nomenclature/auth tests for this TZ passed.

## Check Rules

- Architect creates this checklist and acceptance criteria.
- Executor agents may check implementation and test items only after the relevant implementation and verification are both complete.
- Parent/orchestrator checks Stage 0 and Stage 2 only after reviewing evidence from all parallel units.
- QA verifier checks final acceptance only after reviewing the evidence table, screenshots/traces where applicable, and unchecked blocker notes.
- Failed, unavailable, or intentionally skipped checks stay unchecked with a blocker note in this file and in the executor report.

---

## 1. Context and authority

### Canonical requirements

`Functional and WorkLogik.md`, section VIII, defines the target navigation:

- `4.3.1 каталог` — readonly reference screen for everyone.
- `4.3.2 нуменкулатора` — SPA screen for catalog work, visible only to chief storekeepers and root.
- `4.3.3 Номенкулатура SSR` — collapsible SSR menu with legacy SSR screens.

### Architecture constraints

- `SyncServer` is the source of truth for catalog data and business rules.
- `Warehouse_web` is the Django authenticated shell and BFF. It must not reintroduce local catalog-domain ORM ownership.
- `Warehouse_frontend` renders only the Angular content area inside the Django shell.
- Angular must call same-origin Django endpoints only. Direct browser calls to `SyncServer /api/v1/*` and token exposure in Angular/browser storage are forbidden.
- Replaced Django SSR screens must move under explicit SSR fallback routes.
- Django sidebar/topbar remain Django-owned; Angular must not create another global shell.

### Current observed state before implementation

- `/nomenclature/` is already a Django-hosted Angular nomenclature screen.
- `/catalog/` is an SSR readonly catalog implemented by `Warehouse_web/apps/catalog/browse_views.py` and `Warehouse_web/templates/catalog/browse_*.html`.
- `Warehouse_web/config/urls.py` currently includes `path("catalog/", include("apps.catalog.urls"))` before `path("nomenclature/", include("apps.catalog.nomenclature_urls"))`.
- `Warehouse_web/apps/catalog/nomenclature_urls.py` already keeps editable nomenclature SSR fallback routes under `/nomenclature/ssr/...` and BFF-like legacy endpoints under `/nomenclature/api/...`.
- `Warehouse_frontend/src/app/app.routes.ts` has an Angular route for `nomenclature` but no `catalog` route.
- `Warehouse_frontend/src/app/features/nomenclature/nomenclature-page/nomenclature-page.ts` currently emits create/update/delete/merge/apply actions unconditionally from UI components.
- `Warehouse_frontend/src/app/core/services/nomenclature.service.ts` reads bootstrap data through `ApiService` at `/nomenclature/api/bootstrap/` and applies catalog changes through BFF `POST /bff/api/v1/catalog/admin/batch`.

---

## 2. Target decision

Implement `/catalog/...` as a readonly Angular alias of the existing nomenclature tree screen, while preserving the old SSR catalog as explicit legacy fallback.

### Target URL registry

| Purpose | URL | Renderer | Mode | Access |
|---|---|---|---|---|
| Primary readonly catalog | `/catalog/` | Angular nomenclature screen inside Django shell | `readonly` | all authenticated client users with catalog view access |
| Readonly catalog compatibility paths | `/catalog/items/`, `/catalog/categories/`, `/catalog/<path>` | same Angular screen | `readonly` | same as `/catalog/` |
| Legacy readonly catalog SSR | `/catalog/ssr/`, `/catalog/ssr/items/`, `/catalog/ssr/categories/` | Django SSR legacy templates | readonly legacy | all authenticated client users with catalog view access |
| Primary editable nomenclature | `/nomenclature/` | same Angular nomenclature screen inside Django shell | `editable` | root and chief_storekeeper/catalog managers only |
| Editable nomenclature SSR fallback | `/nomenclature/ssr/...` | Django SSR legacy management screens | editable legacy | root and chief_storekeeper/catalog managers only |
| Nomenclature read bootstrap | `/nomenclature/api/bootstrap/` for now, or `/bff/api/v1/catalog/...` if migrated during implementation | Django same-origin endpoint | read | all client users |
| Catalog mutations | `/bff/api/v1/catalog/admin/batch` and other `/bff/api/v1/catalog/admin/*` | Django BFF -> SyncServer | write | root and chief_storekeeper/catalog managers only |

**Decision:** use `/catalog/ssr/...` as the canonical fallback path for the old readonly catalog. Do not introduce a new root-level `/ssr/catalog/...` namespace unless a separate ADR/TZ approves a global SSR namespace. This aligns with the existing pattern `/operations/ssr/`, `/temporary-items/ssr/`, and `/nomenclature/ssr/`.

### Mode rule

All write affordances must be controlled by a single computed capability:

```text
canWriteCatalog = routeMode == "editable" AND userCanManageCatalog == true
```

Where:

- `routeMode` is determined by the business URL/Angular route data, not by button state.
- `userCanManageCatalog` comes from authenticated Django/BFF/SyncServer-backed permissions or role context.
- Unknown or failed permission loading must resolve to `false` for write capability.
- `/catalog/...` must force `routeMode="readonly"` even for root/chief_storekeeper.
- `/nomenclature/...` may request `routeMode="editable"`, but non-managers must not receive write capability; direct access should show an in-content permission message or redirect to `/catalog/` according to the implementation choice documented by the executor.

Readonly mode is a UX and routing contract, not a security boundary. Server-side permission checks are mandatory.

---

## 3. Scope

### In scope

- Django route migration for `/catalog/` from SSR primary to Angular primary readonly.
- Django fallback route for old readonly SSR catalog under `/catalog/ssr/...`.
- Sidebar restructuring in `Warehouse_web/templates/includes/sidebar.html`:
  - primary `Каталог` -> `/catalog/`;
  - manager-only `Номенклатура` -> `/nomenclature/`;
  - explicit collapsible `SSR / Legacy` area with old SSR links.
- One shared Angular nomenclature screen with two modes: `readonly` and `editable`.
- Hiding/disabling all write UI in readonly mode.
- Preventing readonly mode from creating local pending changes or calling mutation endpoints.
- Server-side denial of catalog mutations for non-managers, including legacy browser-reachable `/nomenclature/api/*` mutation endpoints.
- Django, Angular, Playwright, and real-stand verification.
- Route matrix/documentation updates after implementation.

### Out of scope

- Rewriting SyncServer catalog APIs or database schema.
- Adding local Django ORM catalog entities.
- Moving the global Django sidebar/topbar into Angular.
- Removing SSR fallback routes entirely.
- Redesigning the nomenclature tree beyond changes required for readonly mode labels/states.
- Changing role semantics beyond the existing root/chief_storekeeper/catalog-manager rule.
- Exposing SyncServer tokens or using direct browser-to-SyncServer requests.
- Building a dynamic menu BFF endpoint; sidebar remains Django-rendered in this task.

---

## 4. Implementation requirements

### 4.1 Django routes and SPA host

1. Preserve existing SSR browse views by mounting `apps.catalog.urls` under `/catalog/ssr/`.
2. Add a Django SPA host for `/catalog/` and `/catalog/<path>` that reuses the same Angular build/template machinery as `/nomenclature/`.
3. Route order must place `/catalog/ssr/...` before `/catalog/<path>` catch-all.
4. Keep `/nomenclature/ssr/...` unchanged as editable SSR fallback.
5. Ensure direct navigation and browser refresh work for:
   - `/catalog/`
   - `/catalog/items/`
   - `/catalog/categories/`
   - `/catalog/ssr/`
   - `/nomenclature/`
6. SPA host context may inject non-secret metadata such as screen title or mode. It must not inject `X-User-Token`, `X-Device-Token`, root token, device token, or raw SyncServer credentials.
7. If a reusable generic SPA template is introduced, it must keep `<base href="/">` and the Django shell content mount contract.

### 4.2 Sidebar/menu

Target menu under `Справочники`:

```text
Справочники
  Каталог                  -> /catalog/              (Angular readonly, visible to client users)
  Номенклатура             -> /nomenclature/         (Angular editable, visible only to can_manage_catalog)
  SSR / Legacy             -> collapsible
    Каталог SSR legacy     -> /catalog/ssr/          (readonly fallback, visible to client users)
    Дерево SSR             -> /nomenclature/ssr/tree/       (manager-only)
    ТМЦ SSR                -> /nomenclature/ssr/items/      (manager-only)
    Категории SSR          -> /nomenclature/ssr/categories/ (manager-only)
    Единицы изм. SSR       -> /nomenclature/ssr/units/      (manager-only)
```

Requirements:

- The primary `Каталог` menu item must no longer open the old SSR view.
- SSR links must be visibly marked as legacy/fallback by label or helper text.
- Active menu state must correctly highlight `Каталог` for `/catalog/...` except `/catalog/ssr/...`, and SSR/Legacy for fallback routes.
- Do not restore the old top-level `Администрирование` menu; root/admin can use direct admin URLs as required by `Functional and WorkLogik.md`.

### 4.3 Angular routing

1. Add Angular route(s) for `/catalog/...` that load the same `NomenclaturePageComponent` in readonly mode.
2. Keep `/nomenclature/` loading the same component in editable mode.
3. Avoid duplicating the nomenclature feature or copy-pasting components.
4. Ensure the wildcard route does not redirect `/catalog/...` to `/nomenclature/`.
5. If using route data, use explicit values, for example:

```text
path: "catalog" -> data: { catalogMode: "readonly" }
path: "nomenclature" -> data: { catalogMode: "editable" }
```

6. If supporting nested compatibility paths such as `/catalog/items/`, the implementation must either:
   - route those paths to the same component in readonly mode, or
   - keep the Django URL but normalize inside Angular without changing the visible URL.

### 4.4 Angular readonly behavior

Readonly mode must allow:

- loading the catalog tree/items/units;
- search/filter inside the tree;
- expanding/collapsing tree nodes;
- selecting category, item, or unit;
- viewing details in the right panel;
- navigation through legacy-compatible `/catalog/items/` and `/catalog/categories/` paths.

Readonly mode must not allow:

- `+ Категория`, `+ ТМЦ`, `+ Ед. изм.`;
- edit forms that emit save events;
- delete/deactivate actions;
- merge actions;
- pending change bar;
- `Применить`, `Применить все`, `Сбросить`;
- mutation HTTP calls: `POST`, `PATCH`, `DELETE` to `/nomenclature/api/*` or `/bff/api/v1/catalog/admin/*`.

Recommended UI behavior:

- Header title for `/catalog/...`: `Каталог`.
- Header subtitle for `/catalog/...`: explain that this is readonly browsing of categories, TMC, SKU, units, and keywords.
- Right panel in readonly mode should show disabled/read-only fields or a detail card, not editable form controls pretending changes can be saved.
- If the same form components are reused, pass `readonly=true` and make them suppress all output events that would create changes.
- Clear any local pending change buffer when entering readonly route.

### 4.5 Editable nomenclature behavior

- `/nomenclature/` remains the editable catalog workspace for root/chief_storekeeper/catalog managers.
- For managers, current batch behavior remains: local changes accumulate and are sent through `POST /bff/api/v1/catalog/admin/batch` only after explicit apply.
- For non-managers directly opening `/nomenclature/`, no write UI may be available. The executor must choose and document one of:
  - in-content permission-denied state with a link to `/catalog/`, or
  - safe downgrade to readonly with visible explanation.
- The sidebar must not show `Номенклатура` to users without catalog management permission.

### 4.6 BFF and server-side permission hardening

1. Existing BFF catalog admin endpoints must continue to enforce root/chief_storekeeper/catalog-manager permission.
2. Add or keep tests for `POST /bff/api/v1/catalog/admin/batch`:
   - unauthenticated -> login redirect or 401/403 according to existing Django behavior;
   - storekeeper/observer/non-manager -> 403;
   - root/chief_storekeeper -> accepted and delegated to `CatalogAPI.apply_catalog_batch`.
3. Legacy `/nomenclature/api/*` endpoints are browser-reachable and currently part of the Angular data path. They must be hardened:
   - `GET /nomenclature/api/bootstrap/`, `GET /categories/`, `GET /items/`, `GET /units/` remain readable to client users;
   - `POST /categories/`, `PATCH/DELETE /categories/<id>/`, `POST /items/`, `PATCH/DELETE /items/<id>/`, `POST /units/`, `PATCH/DELETE /units/<id>/` require catalog management permission;
   - non-manager mutation attempts return 403 and must not call `CatalogAPI` mutation methods.
4. Browser responses must not include SyncServer tokens.

---

## 5. Acceptance criteria

### 5.1 Functional acceptance

- `/catalog/` opens inside the Django shell and renders the Angular tree, not the old SSR catalog.
- `/catalog/items/` and `/catalog/categories/` do not 404 and do not redirect users into editable nomenclature.
- `/catalog/...` is readonly even when opened by root/chief_storekeeper.
- `/nomenclature/` remains editable for root/chief_storekeeper/catalog managers.
- Users without catalog management permission can see the primary `Каталог` menu item but do not see the primary `Номенклатура` item.
- Old SSR readonly catalog is still available under `/catalog/ssr/...` and is labelled legacy/fallback in navigation or page text.
- Old editable SSR nomenclature links stay under `/nomenclature/ssr/...` and remain manager-only.

### 5.2 Security and boundary acceptance

- Angular network traffic for `/catalog/...` contains only same-origin Django requests.
- No browser request goes directly to SyncServer `/api/v1/*`.
- No SyncServer token appears in HTML, JS, localStorage, sessionStorage, or browser-visible JSON payloads.
- Readonly route never sends catalog mutation requests during normal user interactions.
- Manual or test mutation attempts from non-manager sessions receive 403 server-side.
- Django does not reintroduce local catalog-domain ORM models.

### 5.3 UX acceptance

- The Django topbar/sidebar remain visible on `/catalog/` and `/nomenclature/`.
- Angular occupies only the content area.
- Readonly catalog has no visible create/edit/delete/merge/apply/reset controls.
- Expand/collapse/search/select/view details still work in readonly mode.
- Editable nomenclature still shows action buttons and pending batch controls for catalog managers.
- Loading, empty, error, and permission-denied states are visible inside the Angular content area.

---

## 6. Test strategy

### 6.1 Static checks

Required:

```bash
cd /home/makc/AI_sandbox/warehouse_solution/Warehouse_web
python manage.py check

cd /home/makc/AI_sandbox/warehouse_solution/Warehouse_frontend
npm run build
```

Applicable because both Django route/template code and Angular route/component code change.

### 6.2 Unit/component tests

Required Django tests:

- URL routing tests for `/catalog/`, `/catalog/items/`, `/catalog/categories/`, `/catalog/ssr/`, `/catalog/ssr/items/`, `/nomenclature/`.
- Sidebar rendering tests for:
  - non-manager: `Каталог` visible, `Номенклатура` hidden, `Каталог SSR legacy` visible if SSR/Legacy section is visible to all client users;
  - manager: both `Каталог` and `Номенклатура` visible, manager-only SSR links visible.
- Permission tests for legacy `/nomenclature/api/*` mutations.
- Existing BFF batch permission tests must remain green.

Required Angular tests:

- Route-mode computation: `/catalog/...` -> readonly, `/nomenclature/...` -> editable.
- `canWriteCatalog` computation: route mode and user permission both required.
- Readonly component rendering: no create/apply/delete/merge/pending controls.
- Editable manager rendering: action buttons and pending bar remain available.
- Form components suppress write output events when `readonly=true`.

Suggested commands after tests are added/updated:

```bash
cd /home/makc/AI_sandbox/warehouse_solution/Warehouse_web
python manage.py test apps.catalog apps.bff_api

cd /home/makc/AI_sandbox/warehouse_solution/Warehouse_frontend
npm run build
# If Angular unit test runner is configured for CI in this repo, run the smallest non-watch command documented by the executor.
```

### 6.3 Integration tests with real dependencies

Required for Django/BFF behavior:

- Django tests using test DB and patched or test SyncServer clients for route/permission behavior.
- If mutation permission is tested against real SyncServer client, use safe test data and do not rely on production credentials.
- Verify that BFF/admin endpoints call `Warehouse_web/apps/sync_client/`/`CatalogAPI`, not direct DB or direct browser SyncServer calls.

Minimum command:

```bash
cd /home/makc/AI_sandbox/warehouse_solution/Warehouse_web
python manage.py test
```

If the full suite is too slow or blocked, executor must run the targeted suites above and document the blocker for the full suite.

### 6.4 Real stand smoke tests

Applicable because user-facing runtime routes and browser behavior change.

Use the workspace Docker dev stand:

| Service | Address | Health check |
|---|---|---|
| SyncServer API | `http://localhost:8000` | `GET /api/v1/health` |
| Django | `http://localhost:8001` | `GET /healthz/` |
| PostgreSQL | `localhost:5432` | `pg_isready -h localhost -p 5432 -t 3` |
| Angular assets/dev container | `http://localhost:4200` when used | `GET /` |

Stand lifecycle:

- Assume the dev stand is running by default.
- If a request fails with connection error, run health checks.
- If down, run `make up` from `/home/makc/AI_sandbox/warehouse_solution`.
- If images/routes changed and stale assets are suspected, run the smallest needed rebuild, usually `make build-web` and/or `make build-angular`, then `make up` or `make restart`.
- Do not run destructive cleanup such as volume deletion for this task.

Environment variable names only:

- `DJANGO_ENV`
- `SYNC_SERVER_URL`
- `SYNC_ROOT_USER_TOKEN`
- `SYNC_DEVICE_TOKEN`
- `DATABASE_URL`
- `DJANGO_SETTINGS_MODULE`
- `SECRET_KEY`

Smoke URLs:

```text
http://localhost:8001/catalog/
http://localhost:8001/catalog/items/
http://localhost:8001/catalog/categories/
http://localhost:8001/catalog/ssr/
http://localhost:8001/nomenclature/
http://localhost:8001/nomenclature/ssr/tree/
```

Expected smoke results:

- unauthenticated browser is redirected to Django login;
- authenticated client user sees `/catalog/` Angular readonly tree;
- `/catalog/ssr/` shows legacy SSR readonly catalog;
- authenticated manager sees `/nomenclature/` editable Angular tree;
- all pages keep Django topbar/sidebar.

### 6.5 UI automation

Required because menu and browser UI behavior change.

Use Playwright through Django base URL, not direct Angular dev URL, unless the executor documents a temporary local-only reason.

Suggested command:

```bash
cd /home/makc/AI_sandbox/warehouse_solution/Warehouse_frontend
E2E_BASE_URL=http://localhost:8001 npm run test:e2e -- catalog-readonly.spec.ts
```

Required Playwright scenarios:

1. Login as a non-manager/client user prepared by the test fixture.
2. Open `/catalog/`.
3. Assert Django sidebar/topbar are visible.
4. Assert Angular tree/content is visible.
5. Assert no buttons/text controls for create, delete, merge, apply, reset are visible.
6. Expand/collapse/search/select a node and verify details display.
7. Capture network requests and assert no direct SyncServer `/api/v1/*` and no mutation requests to catalog admin endpoints.
8. Open `/catalog/ssr/` and assert legacy SSR route is reachable and marked legacy/fallback.
9. Login as manager/root fixture.
10. Open `/catalog/` and assert it is still readonly.
11. Open `/nomenclature/` and assert editable controls are visible.

If non-manager fixture credentials are not available on the stand, executor must create a safe test fixture through Django test setup or document the blocker; do not hardcode production credentials.

### 6.6 User scenario tests

Required scenarios:

| Scenario | Steps | Expected result |
|---|---|---|
| Readonly catalog for ordinary user | Login as storekeeper/observer -> sidebar `Справочники` -> `Каталог` -> search/select item | User can browse but cannot mutate anything. |
| Manager readonly alias | Login as root/chief -> open `/catalog/` | Manager still sees readonly catalog, proving URL mode overrides write permission. |
| Manager editable nomenclature | Login as root/chief -> open `/nomenclature/` -> stage a harmless test change or verify controls without applying if stand data must stay unchanged | Editable controls and batch workflow are available only on editable route. |
| Legacy fallback | Open `SSR / Legacy` -> `Каталог SSR legacy` | Old SSR readonly catalog remains available under `/catalog/ssr/`. |
| Direct URL protection | Non-manager opens `/nomenclature/` and attempts mutation endpoint manually/test client | No write capability in UI; server returns 403 for mutation. |

### 6.7 Regression pack

Run or verify:

- existing Django auth/login/logout flow;
- existing `/nomenclature/` Angular manager flow;
- existing `/nomenclature/ssr/...` manager fallback routes;
- existing BFF catalog admin batch tests;
- existing operations/temporary-items/issued-assets SPA routes are not swallowed by new catalog catch-all;
- browser refresh on `/operations/`, `/temporary-items/`, `/issued-assets/`, `/nomenclature/`, `/catalog/` still loads assets with `<base href="/">`.

---

## 7. Evidence table required in executor report

Executors must include this table in their completion report and link logs/screenshots/traces where available.

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|
| Context verification | Read `Functional and WorkLogik.md` + SPA architecture | pass/fail | notes with sections |
| Django static | `python manage.py check` | pass/fail/skipped | log path or output summary |
| Django tests | `python manage.py test apps.catalog apps.bff_api` and/or `python manage.py test` | pass/fail/skipped | log path |
| Angular build | `npm run build` | pass/fail/skipped | log path |
| Angular unit/component | documented non-watch command | pass/fail/skipped | log path or blocker |
| Stand health | SyncServer/Django/PostgreSQL health checks if needed | pass/fail/skipped | URLs/output |
| Stand smoke | Browser/curl smoke URLs from section 6.4 | pass/fail/skipped | screenshot/log |
| UI automation | Playwright through `http://localhost:8001` | pass/fail/skipped | report path/trace |
| Security regression | Network capture + server 403 tests | pass/fail/skipped | test names/log |
| Docs | route matrix/index updates | pass/fail/skipped | changed files |

---

## 8. Risks and mitigations

| Risk | Mitigation |
|---|---|
| `/catalog/<path>` catch-all swallows `/catalog/ssr/...` | Route `/catalog/ssr/` before SPA catch-all and cover with URL tests. |
| Same Angular component accidentally keeps write buttons in readonly route | Centralize `canWriteCatalog`; child components receive readonly/canWrite inputs; add component and Playwright tests. |
| UI hiding is mistaken for security | Add server-side 403 tests for all mutation endpoints, including legacy `/nomenclature/api/*`. |
| Manager opens `/catalog/` and accidentally edits | Route mode must force readonly regardless of role. |
| Non-manager direct `/nomenclature/` access | Sidebar hides route; Angular/Django shows permission-denied or readonly downgrade; BFF denies writes. |
| Old bookmarks to `/catalog/items/` break | Django and Angular compatibility routing must render readonly Angular instead of 404. Legacy SSR is available at `/catalog/ssr/items/`. |
| Asset paths break on multi-route SPA mount | Preserve `<base href="/">`, root asset serving, and refresh tests. |
| Parallel agents edit same tests | Parent/orchestrator assigns exact test modules before work; if overlap appears, stop and split ownership. |

---

## 9. Documentation updates after implementation

Required after code and tests pass:

- Update `Warehouse_frontend/docs/ARCHITECTURE_FRONTEND_SPA.md` Route Migration Matrix:
  - `Catalog` or `Catalog readonly` -> `/catalog/` -> `Angular primary`;
  - SSR fallback -> `/catalog/ssr/`.
- If entry points changed materially, update active docs such as `INDEX.md`, `AI_ENTRY_POINTS.md`, or project-specific docs according to repository documentation rules.
- Historical reports/screenshots do not need rewriting.

---

## 10. Final acceptance review

QA may check final acceptance only when:

- every checked checklist item has evidence;
- unchecked items have explicit blocker notes;
- `/catalog/` is demonstrably Angular readonly;
- `/nomenclature/` remains manager-editable;
- old catalog SSR is only under `/catalog/ssr/...` and marked legacy/fallback;
- non-manager mutation attempts fail server-side;
- Playwright evidence covers both readonly alias and editable route;
- no architecture boundary is violated.
