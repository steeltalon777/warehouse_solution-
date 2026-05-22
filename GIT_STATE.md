# Git State

Generated at: `2026-05-22T14:35`
Root: `/home/makc/AI_sandbox/warehouse_solution`
Fetch before scan: `no`

## Summary

| Repo | Branch | Upstream | Ahead | Behind | Dirty | HEAD | Last commit |
|---|---|---|---:|---:|---|---|---|
| `warehouse_solution` | `dev` | `origin/dev` | 0 | 0 | YES | `7bd1c21` | chore: setup dev environment — Makefile, docker-compose, .env, quickstart.sh |
| `SyncServer` | `dev` | `origin/dev` | 0 | 0 | YES | `f5936b2` | to devstand migrate |
| `Warehouse_client_core` | `dev` | `origin/dev` | 0 | 0 | no | `306a593` | to devstand migrate |
| `Warehouse_frontend` | `dev` | `origin/dev` | 0 | 0 | YES | `22ddbf8` | fix: resolve TS build errors in new Angular components |
| `Warehouse_web` | `dev` | `origin/dev` | 0 | 0 | YES | `70a8f5e` | fix: add missing imports for review_items views |
| `WarehouseAIWorkstation` | `main` | `origin/main` | 0 | 0 | no | `981edf7` | stage5 |

## Details

### warehouse_solution

- Path: `.`
- Current branch: `dev`
- Upstream: `origin/dev`
- Ahead/behind: `0 / 0`
- Dirty: `yes`
- Staged / unstaged / untracked: `0 / 19 / 5`
- HEAD: `7bd1c21`
- HEAD subject: chore: setup dev environment — Makefile, docker-compose, .env, quickstart.sh
- HEAD author/date: `makc / 2026-05-21 09:17:59 +0900`
- Tags at HEAD: `-`

#### Remotes

- `origin`: `git@github.com:steeltalon777/warehouse_solution-.git`

#### Local branches

- `dev` ← current
- `main`

#### Remote branches

- `origin/dev`
- `origin/main`

#### Working tree status

```text
 M .gitignore
 M AGENTS.md
 D Domain_model.md
 M "Functional and WorkLogik.md"
 M GIT_STATE.md
 M MEMORY.md
 M Makefile
 D PLAN_UI_TEST.md
 M "Role Matrix.md"
 D TODOlist.md
 D UI_test_reports.md
 M docs/AGENT_TZ_WORKFLOW.md
 D docs/AUDIT_FUNCTIONAL_SPEC_2026-05-19.md
 D docs/AUDIT_IV_TEMPORARY_ITEMS_2026-05-19.md
 D docs/OPENCODE_AGENT_MODES.md
 D docs/PLAN_PRE_ANGULAR_FUNCTIONAL_GAPS_2026-05-19.md
 M docs/TZ-B_OPERATIONS_DELETE_CONTRACT.md
 D plans/general_roadmap.md
 D plans/temporary_items_delete_implementation.md
?? Makefile.bak.2026-05-20_14-11-26
?? docker-compose.override.yml
?? docs/TZ-NOMENCLATURE_BATCH_CATALOG_CRUD.md
?? docs/TZ-OPERATIONS_CREATE_MODAL_CACHED_SEARCH.md
?? start_opencode_web.sh
```

#### Recent commits

```text
7bd1c21 | 2026-05-21 09:17:59 +0900 | makc | chore: setup dev environment — Makefile, docker-compose, .env, quickstart.sh
9cc34b2 | 2026-05-20 10:22:03 +0900 | Maksim Kuzmin | add ubuntu setup script
b15db14 | 2026-05-19 23:27:26 +0900 | Maksim Kuzmin | Root: AGENTS.md update, Functional and WorkLogik.md, pre-Angular plan, ADRs 0006-0010, audit reports, GIT_STATE update
030f138 | 2026-05-12 15:33:02 +0900 | Maksim Kuzmin | chore: add GIT_STATE.md to gitignore
66fa41f | 2026-05-12 14:55:43 +0900 | Maksim Kuzmin | Update repository state after release branch sync
```

### SyncServer

- Path: `SyncServer`
- Current branch: `dev`
- Upstream: `origin/dev`
- Ahead/behind: `0 / 0`
- Dirty: `yes`
- Staged / unstaged / untracked: `0 / 4 / 3`
- HEAD: `f5936b2`
- HEAD subject: to devstand migrate
- HEAD author/date: `Maksim Kuzmin / 2026-05-21 08:57:11 +0900`
- Tags at HEAD: `-`

#### Remotes

- `origin`: `https://github.com/steeltalon777/SyncServer.git`

#### Local branches

- `dev` ← current
- `main`

#### Remote branches

- `origin/backup/main-before-reset-2026-04-20`
- `origin/codex/audit-and-refine-syncserver-project`
- `origin/codex/create-ai-friendly-documentation`
- `origin/codex/create-ai-friendly-project-documentation`
- `origin/codex/create-documentation-and-api-client-specs`
- `origin/codex/document-code-and-project-structure`
- `origin/codex/find-project-in-repository`
- `origin/codex/implement-write-api-for-catalog`
- `origin/codex/improve-syncserver-backend-and-documentation`
- `origin/codex/update-documentation-for-syncserver`
- `origin/codex/update-project-documentation`
- `origin/dev`
- `origin/main`
- `origin/prod`

#### Working tree status

```text
 M Dockerfile
 M app/api/routes_catalog_admin.py
 M app/schemas/catalog.py
 M app/services/catalog_admin_service.py
?? .venv/
?? test.db
?? tests/test_catalog_batch.py
```

#### Recent commits

```text
f5936b2 | 2026-05-21 08:57:11 +0900 | Maksim Kuzmin | to devstand migrate
f1d5049 | 2026-05-20 20:00:03 +0900 | Maksim Kuzmin | fix(catalog): filter soft-deleted categories from tree
6d2f2cc | 2026-05-19 23:14:05 +0900 | Maksim Kuzmin | SyncServer: bootstrap + root-token recovery + DELETE cancelled operations + catalog freeze for lost assets
74327ab | 2026-05-12 14:25:12 +0900 | Maksim Kuzmin | Clean generated artifacts and temporary files
8aa9d0c | 2026-04-25 10:13:24 +0900 | Maksim Kuzmin | препатч 2.0
```

### Warehouse_client_core

- Path: `Warehouse_client_core`
- Current branch: `dev`
- Upstream: `origin/dev`
- Ahead/behind: `0 / 0`
- Dirty: `no`
- Staged / unstaged / untracked: `0 / 0 / 0`
- HEAD: `306a593`
- HEAD subject: to devstand migrate
- HEAD author/date: `Maksim Kuzmin / 2026-05-21 08:57:51 +0900`
- Tags at HEAD: `-`

#### Remotes

- `origin`: `https://github.com/steeltalon777/Warehouse_core.git`

#### Local branches

- `dev` ← current
- `main`

#### Remote branches

- `origin/dev`
- `origin/main`

#### Working tree status

```text
clean
```

#### Recent commits

```text
306a593 | 2026-05-21 08:57:51 +0900 | Maksim Kuzmin | to devstand migrate
6276862 | 2026-05-18 11:20:49 +0900 | Maksim Kuzmin | bootstrap rust offline core workspace
9eebff0 | 2026-05-16 21:16:00 +0900 | Maksim Kuzmin | first commit
```

### Warehouse_frontend

- Path: `Warehouse_frontend`
- Current branch: `dev`
- Upstream: `origin/dev`
- Ahead/behind: `0 / 0`
- Dirty: `yes`
- Staged / unstaged / untracked: `0 / 12 / 1`
- HEAD: `22ddbf8`
- HEAD subject: fix: resolve TS build errors in new Angular components
- HEAD author/date: `makc / 2026-05-21 09:17:59 +0900`
- Tags at HEAD: `-`

#### Remotes

- `origin`: `git@github.com:steeltalon777/Warehouse_frontend.git`

#### Local branches

- `dev` ← current
- `main`

#### Remote branches

- `origin/dev`
- `origin/main`

#### Working tree status

```text
 M package-lock.json
 M src/app/core/models/nomenclature.models.ts
 M src/app/core/models/operations.models.ts
 M src/app/core/services/catalog-search.service.ts
 M src/app/core/services/nomenclature.service.ts
 M src/app/features/nomenclature/action-buttons/action-buttons.ts
 M src/app/features/nomenclature/category-edit-form/category-edit-form.ts
 M src/app/features/nomenclature/item-edit-form/item-edit-form.ts
 M src/app/features/nomenclature/nomenclature-page/nomenclature-page.ts
 M src/app/features/nomenclature/right-panel/right-panel.ts
 M src/app/features/operations/components/item-cache-search/item-cache-search.component.ts
 M src/app/features/operations/components/operation-create-modal/operation-create-modal.component.ts
?? src/app/features/nomenclature/unit-edit-form/
```

#### Recent commits

```text
22ddbf8 | 2026-05-21 09:17:59 +0900 | makc | fix: resolve TS build errors in new Angular components
5ca526b | 2026-05-21 08:58:33 +0900 | Maksim Kuzmin | to devstand migrate
be92fce | 2026-05-20 22:18:56 +0900 | Maksim Kuzmin | fix(operations): compact filters, scrollable table, sortable headers for FHD
6c937eb | 2026-05-20 21:07:16 +0900 | Maksim Kuzmin | fix(nomenclature): ensure tree scrolls inside panel and fits FHD viewport
7dc4160 | 2026-05-20 20:00:02 +0900 | Maksim Kuzmin | fix(nomenclature): correct plural form for category API path
```

### Warehouse_web

- Path: `Warehouse_web`
- Current branch: `dev`
- Upstream: `origin/dev`
- Ahead/behind: `0 / 0`
- Dirty: `yes`
- Staged / unstaged / untracked: `0 / 15 / 1`
- HEAD: `70a8f5e`
- HEAD subject: fix: add missing imports for review_items views
- HEAD author/date: `makc / 2026-05-21 09:17:59 +0900`
- Tags at HEAD: `-`

#### Remotes

- `origin`: `git@github.com:steeltalon777/Warehouse_web.git`

#### Local branches

- `dev` ← current
- `main`

#### Remote branches

- `origin/backup/main-before-reset-2026-04-20`
- `origin/codex/create-ai-friendly-documentation-architecture`
- `origin/codex/create-ai-friendly-documentation-structure`
- `origin/codex/create-ai-friendly-documentation-structure-4tynzj`
- `origin/codex/create-ai-friendly-documentation-structure-idmjkd`
- `origin/codex/create-ai-friendly-documentation-structure-qbyfn3`
- `origin/codex/create-ai-friendly-project-documentation`
- `origin/codex/create-project-documentation-and-ai-index`
- `origin/codex/implement-ssr-pages-for-syncserver`
- `origin/codex/integrate-django-web-client-with-syncserver`
- `origin/codex/prepare-warehouse_web-for-deployment-readiness`
- `origin/codex/refactor-django-auth-to-remove-userprofile`
- `origin/codex/refactor-django-roles-and-auth-flow`
- `origin/codex/refactor-warehouse_web-for-syncserver-integration`
- `origin/dev`
- `origin/main`
- `origin/prod`

#### Working tree status

```text
 M Dockerfile
 M apps/bff_api/catalog_views.py
 M apps/bff_api/tests.py
 M apps/bff_api/urls.py
 M apps/catalog_cache/services.py
 M apps/catalog_cache/tests.py
 M apps/sync_client/auth_api.py
 M apps/sync_client/auth_integration.py
 M apps/sync_client/catalog_api.py
 M apps/sync_client/client.py
 M apps/sync_client/session_auth.py
 M apps/sync_client/test_auth_boundary.py
 M apps/sync_client/token_resolver.py
 M apps/users/simple_sync_signals.py
 M apps/users/tests.py
?? warehouse
```

#### Recent commits

```text
70a8f5e | 2026-05-21 09:17:59 +0900 | makc | fix: add missing imports for review_items views
b797603 | 2026-05-21 08:56:33 +0900 | Maksim Kuzmin | to devstand migrate
3f3d7c4 | 2026-05-20 21:53:50 +0900 | Maksim Kuzmin | fix(balances): compact filters, scrollable table, sortable headers for FHD
2a29aef | 2026-05-20 21:11:22 +0900 | Maksim Kuzmin | refactor(menu): align sidebar with Functional and WorkLogik.md VIII/4
ab52ec3 | 2026-05-19 23:17:09 +0900 | Maksim Kuzmin | Warehouse_web: auth boundary hardening (TZ-1), brand/role/dashboard UX (TZ-D), operations delete BFF, token resolver, context processors
```

### WarehouseAIWorkstation

- Path: `WarehouseAIWorkstation`
- Current branch: `main`
- Upstream: `origin/main`
- Ahead/behind: `0 / 0`
- Dirty: `no`
- Staged / unstaged / untracked: `0 / 0 / 0`
- HEAD: `981edf7`
- HEAD subject: stage5
- HEAD author/date: `Maksim Kuzmin / 2026-04-12 22:54:27 +0900`
- Tags at HEAD: `-`

#### Remotes

- `origin`: `https://github.com/steeltalon777/Warehouse_catalog_client.git`

#### Local branches

- `main` ← current

#### Remote branches

- `origin/codex/transform-wpf-client-to-warehouse-desktop`
- `origin/main`

#### Working tree status

```text
clean
```

#### Recent commits

```text
981edf7 | 2026-04-12 22:54:27 +0900 | Maksim Kuzmin | stage5
f414330 | 2026-04-12 22:53:15 +0900 | Maksim Kuzmin | fix(stage5): close Directory workspace runtime defects and add smoke gate\n\n- Add missing theme resources (BrushTextSecondary, BrushError, BrushWarning, BrushSuccess)\n- Fix XAML command bindings to match actual ViewModel command names (NewItemCommand, SaveSelectedCommand, etc.)\n- Remove unsafe Task.Run initialization; move to Loaded event handler on UI thread\n- Complete detail panels with all business fields (Description, Code, SortOrder, IsActive)\n- Render AI flags as read-only (TextBlock with muted styling, not editable TextBox)\n- Normalize contract matrix auth format to X-User-Token (role: ...)\n- Add WPF smoke tests for Row ViewModel round-trips and flag formatting\n- Add Presentation reference to UnitTests project (net8.0-windows)\n\nBuild: 0 warnings, 0 errors. Tests: 73 passed.
2ed7442 | 2026-04-11 23:17:28 +0900 | Maksim Kuzmin | Harden bootstrap login flow and add stage 4 spec
27a9ede | 2026-04-11 22:50:11 +0900 | Maksim Kuzmin | fix(stage3): close remaining gaps — root setup visibility, logout flow, user management UI
fbd1bf7 | 2026-04-11 22:34:37 +0900 | Maksim Kuzmin | fix: align bootstrap sync client with real server contract + live smoke verified
```

## Notes for agents

- `Dirty = YES` means the repository has uncommitted changes.
- `Ahead > 0` means local branch has commits not pushed to upstream.
- `Behind > 0` means local branch is missing commits from upstream.
- This file is generated. Do not edit it manually.
