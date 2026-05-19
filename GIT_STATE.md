# Git State

Generated at: `2026-05-19T23:13`
Root: `D:\PROG\Warehouse_solution`
Fetch before scan: `no`

## Summary

| Repo | Branch | Upstream | Ahead | Behind | Dirty | HEAD | Last commit |
|---|---|---|---:|---:|---|---|---|
| `Warehouse_solution` | `dev` | `-` | 0 | 0 | YES | `030f138` | chore: add GIT_STATE.md to gitignore |
| `SyncServer` | `dev` | `origin/dev` | 0 | 0 | YES | `74327ab` | Clean generated artifacts and temporary files |
| `Warehouse_client_core` | `dev` | `origin/dev` | 0 | 0 | YES | `6276862` | bootstrap rust offline core workspace |
| `Warehouse_frontend` | `dev` | `origin/dev` | 1 | 0 | YES | `68d8187` | feat: operations hardening (sorting, auth context, double-submit, badges), shared style system (wh-* SCSS partials), unit tests, fix toLowerCase runtime error |
| `Warehouse_web` | `dev` | `origin/dev` | 1 | 0 | YES | `e257852` | feat: mount OperationsSPAView at /operations/, move SSR fallback to /operations/ssr/, add POST/PATCH nomenclature mutation endpoints, fix SPA template base href and asset prefix |
| `WarehouseAIWorkstation` | `main` | `origin/main` | 1 | 0 | YES | `04daeae` | Bootstrap ready |
| `WarehouseMobile` | `master` | `-` | 0 | 0 | YES | `e516d56` | First |

## Details

### Warehouse_solution

- Path: `.`
- Current branch: `dev`
- Upstream: `-`
- Ahead/behind: `0 / 0`
- Dirty: `yes`
- Staged / unstaged / untracked: `0 / 13 / 26`
- HEAD: `030f138`
- HEAD subject: chore: add GIT_STATE.md to gitignore
- HEAD author/date: `Maksim Kuzmin / 2026-05-12 15:33:02 +0900`
- Tags at HEAD: `-`

#### Remotes

- `origin`: `https://github.com/steeltalon777/warehouse_solution-.git`

#### Local branches

- `dev` ← current
- `main`
- `opencode/proud-nebula`
- `opencode/shiny-cactus`
- `opencode/shiny-comet`

#### Remote branches

- `origin/main`

#### Working tree status

```text
 M .gitignore
 M AI_CONTEXT.md
 M AI_ENTRY_POINTS.md
 M API_MAP.md
 M ARCHITECTURE.md
 M GIT_STATE.md
 M INDEX.md
 M MEMORY.md
 M README.md
 M REPOSITORY_MAP.md
 M SOLUTION_ROADMAP.md
 M docs/adr/0001-syncserver-source-of-truth.md
 M docs/adr/0005-token-auth-and-site-scoped-access.md
?? AGENTS.md
?? "Functional and WorkLogik.md"
?? VaibMastery.md
?? docs/AGENT_TZ_WORKFLOW.md
?? docs/AUDIT_FUNCTIONAL_SPEC_2026-05-19.md
?? docs/AUDIT_IV_TEMPORARY_ITEMS_2026-05-19.md
?? docs/OPENCODE_AGENT_MODES.md
?? docs/PLAN_PRE_ANGULAR_FUNCTIONAL_GAPS_2026-05-19.md
?? docs/TZ-B_OPERATIONS_DELETE_CONTRACT.md
?? docs/TZ_AUTH_CONTRACT_CLEANUP.md
?? docs/TZ_nomenclature_spec_upgrade.md
?? docs/adr/0006-mobile-bridge-strategy.md
?? docs/adr/0007-core-http-sync-contract.md
?? docs/adr/0008-outbox-push-transport.md
?? docs/adr/0009-ffi-strategy.md
?? docs/adr/0010-token-ownership.md
?? nomenclature-shared-style.png
?? operations-shared-style-error.png
?? plans/bff_api_complete_tz.md
?? plans/general_roadmap.md
?? smoke_test.py
?? stand-smoke-login-page.png
?? stand-smoke-nomenclature-page-final.png
?? stand-smoke-nomenclature-page.png
?? stand-smoke-operations-page-final.png
?? stand-smoke-operations-page.png
```

#### Recent commits

```text
030f138 | 2026-05-12 15:33:02 +0900 | Maksim Kuzmin | chore: add GIT_STATE.md to gitignore
66fa41f | 2026-05-12 14:55:43 +0900 | Maksim Kuzmin | Update repository state after release branch sync
a849d78 | 2026-05-12 14:39:43 +0900 | Maksim Kuzmin | Refine nested repositories git state report
7495282 | 2026-05-12 14:31:31 +0900 | Maksim Kuzmin | Add nested repositories git state report
b9d237a | 2026-05-12 14:16:37 +0900 | Maksim Kuzmin | Add repository map generator
```

### SyncServer

- Path: `SyncServer`
- Current branch: `dev`
- Upstream: `origin/dev`
- Ahead/behind: `0 / 0`
- Dirty: `yes`
- Staged / unstaged / untracked: `0 / 20 / 14`
- HEAD: `74327ab`
- HEAD subject: Clean generated artifacts and temporary files
- HEAD author/date: `Maksim Kuzmin / 2026-05-12 14:25:12 +0900`
- Tags at HEAD: `-`

#### Remotes

- `origin`: `git@github.com:steeltalon777/SyncServer.git`

#### Local branches

- `backup/main-before-reset-2026-04-20`
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
 M app/api/deps.py
 M app/api/routes_catalog_admin.py
 M app/api/routes_operations.py
 M app/api/routes_sync.py
 M app/models/operation.py
 M app/repos/asset_registers_repo.py
 M app/repos/operations_repo.py
 M app/services/catalog_admin_service.py
 M app/services/identity_service.py
 M app/services/operations_policy.py
 M app/services/operations_service.py
 M app/services/operations_workflow_policy.py
 M docs/API_MAP.md
 M docs/API_REFERENCE.md
 M docs/TEST_STAND_GUIDE.md
 M pytest.ini
 M tests/conftest.py
 M tests/test_operations_permissions.py
 M tests/test_operations_workflow_policy.py
 M tests/test_temporary_items_delete.py
?? AGENTS.md
?? alembic/versions/7538376fd139_add_operations_deleted_fields.py
?? check_columns.py.bak
?? docs/TZ-A_BOOTSTRAP_ROOT_TOKEN_RECOVERY.md
?? docs/TZ-C_LOST_ASSETS_CATALOG_FREEZE.md
?? scripts/bootstrap_root.py
?? scripts/rotate_tokens.py
?? scripts/verify_alembic.py
?? tests/test_alembic_migrations.py
?? tests/test_bootstrap_root.py
?? tests/test_catalog_freeze.py
?? tests/test_fast_baseline.py
?? tests/test_operations_delete_api.py
?? tests/test_operations_service_delete.py
```

#### Recent commits

```text
74327ab | 2026-05-12 14:25:12 +0900 | Maksim Kuzmin | Clean generated artifacts and temporary files
8aa9d0c | 2026-04-25 10:13:24 +0900 | Maksim Kuzmin | препатч 2.0
d52ec23 | 2026-04-23 10:05:15 +0900 | Maksim Kuzmin | Preprod 2.0
c714332 | 2026-04-22 12:27:58 +0900 | Maksim Kuzmin | TM ites phase 1
3445982 | 2026-04-15 16:18:11 +0900 | Maksim Kuzmin | updated 2.0
```

### Warehouse_client_core

- Path: `Warehouse_client_core`
- Current branch: `dev`
- Upstream: `origin/dev`
- Ahead/behind: `0 / 0`
- Dirty: `yes`
- Staged / unstaged / untracked: `0 / 2 / 2`
- HEAD: `6276862`
- HEAD subject: bootstrap rust offline core workspace
- HEAD author/date: `Maksim Kuzmin / 2026-05-18 11:20:49 +0900`
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
 M AGENTS.md
 M docs/TZ_CORE_CLIENT_READY_COMPLETION.md
?? docs/CORE_STAND_SMOKE_REPORT.md
?? docs/TZ_CORE_STAND_CONTRACT_FIXES_BEFORE_AIWORKSTATION.md
```

#### Recent commits

```text
6276862 | 2026-05-18 11:20:49 +0900 | Maksim Kuzmin | bootstrap rust offline core workspace
9eebff0 | 2026-05-16 21:16:00 +0900 | Maksim Kuzmin | first commit
```

### Warehouse_frontend

- Path: `Warehouse_frontend`
- Current branch: `dev`
- Upstream: `origin/dev`
- Ahead/behind: `1 / 0`
- Dirty: `yes`
- Staged / unstaged / untracked: `0 / 7 / 47`
- HEAD: `68d8187`
- HEAD subject: feat: operations hardening (sorting, auth context, double-submit, badges), shared style system (wh-* SCSS partials), unit tests, fix toLowerCase runtime error
- HEAD author/date: `Maksim Kuzmin / 2026-05-19 21:21:55 +0900`
- Tags at HEAD: `-`

#### Remotes

- `origin`: `https://github.com/steeltalon777/Warehouse_frontend.git`

#### Local branches

- `dev` ← current
- `main`

#### Remote branches

- `origin/dev`
- `origin/main`

#### Working tree status

```text
 D .DS_Store
 M .gitignore
 M .idea/workspace.xml
 D README.md
 M package.json
 D src/index.ts
 M tsconfig.json
?? .editorconfig
?? .prettierrc
?? .vscode/
?? AGENTS.md
?? OPERATIONS_IMPLEMENTATION.md
?? angular.json
?? docs/ARCHITECTURE_FRONTEND_SPA.md
?? docs/AUDIT_vs_TZ_2026-05-18.md
?? docs/TZ_FRONTEND_SHARED_STYLE_SYSTEM.md
?? docs/TZ_TEMPORARY_ITEMS_ANGULAR.md
?? docs/nomenclature-screen-spec.md
?? docs/nomenculature_plan.md
?? docs/screens_plan/
?? e2e/
?? nomenclature-snapshot.md
?? package-lock.json
?? public/
?? src/app/app.config.ts
?? src/app/app.html
?? src/app/app.routes.ts
?? src/app/app.scss
?? src/app/app.ts
?? src/app/core/api/
?? src/app/core/models/admin.models.ts
?? src/app/core/models/assets.models.ts
?? src/app/core/models/auth.models.ts
?? src/app/core/models/balances.models.ts
?? src/app/core/models/documents.models.ts
?? src/app/core/models/health.models.ts
?? src/app/core/models/nomenclature.models.ts
?? src/app/core/models/recipients.models.ts
?? src/app/core/models/reports.models.ts
?? src/app/core/models/temp-items.models.ts
... 14 more
```

#### Recent commits

```text
68d8187 | 2026-05-19 21:21:55 +0900 | Maksim Kuzmin | feat: operations hardening (sorting, auth context, double-submit, badges), shared style system (wh-* SCSS partials), unit tests, fix toLowerCase runtime error
a3fb5e3 | 2026-05-15 18:29:35 +0900 | Maksim Kuzmin | first commit
```

### Warehouse_web

- Path: `Warehouse_web`
- Current branch: `dev`
- Upstream: `origin/dev`
- Ahead/behind: `1 / 0`
- Dirty: `yes`
- Staged / unstaged / untracked: `0 / 40 / 12`
- HEAD: `e257852`
- HEAD subject: feat: mount OperationsSPAView at /operations/, move SSR fallback to /operations/ssr/, add POST/PATCH nomenclature mutation endpoints, fix SPA template base href and asset prefix
- HEAD author/date: `Maksim Kuzmin / 2026-05-19 21:21:55 +0900`
- Tags at HEAD: `-`

#### Remotes

- `origin`: `git@github.com:steeltalon777/Warehouse_web.git`

#### Local branches

- `backup/main-before-reset-2026-04-20`
- `dev` ← current
- `main`
- `prod`

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
 M AI_CONTEXT.md
 M AI_ENTRY_POINTS.md
 M API_MAP.md
 M ARCHITECTURE.md
 M DOMAIN_MODEL.md
 M INDEX.md
 M MEMORY.md
 M PROJECT_BRAIN.md
 M README.md
 M SYSTEM_MAP.md
 M apps/balances/views.py
 M apps/catalog/admin.py
 M apps/catalog/browse_views.py
 M apps/catalog/models.py
 M apps/client/tests.py
 M apps/client/views.py
 M apps/common/mixins.py
 M apps/common/tests.py
 M apps/documents/views.py
 M apps/operations/tests.py
 M apps/sync_client/auth_api.py
 M apps/sync_client/client.py
 M apps/sync_client/operations_api.py
 M apps/sync_client/root_admin_client.py
 M apps/sync_client/session_auth.py
 M apps/sync_client/tests.py
 M apps/temporary_items/tests.py
 M apps/users/tests.py
 M config/settings/base.py
 M docs/api_only_views.md
 M docs/catalog_api_methods.md
 M docs/operations_balances_endpoints.md
 M "docs/reports/2026-03-18_\320\260\321\203\320\264\320\270\321\202_\320\270\320\275\321\202\320\265\320\263\321\200\320\260\321\206\320\270\320\270_django_api.md"
 M docs/reports/2026-03-19_django_safe_refactor_phase1.md
 M docs/syncserver_auth_integration.md
 M static/css/app.css
 M templates/base.html
 M templates/client/dashboard.html
 M templates/includes/brand.html
 M templates/includes/navbar.html
... 12 more
```

#### Recent commits

```text
e257852 | 2026-05-19 21:21:55 +0900 | Maksim Kuzmin | feat: mount OperationsSPAView at /operations/, move SSR fallback to /operations/ssr/, add POST/PATCH nomenclature mutation endpoints, fix SPA template base href and asset prefix
d4912d1 | 2026-05-12 15:20:30 +0900 | Maksim Kuzmin | fix: temporary items pagination and bulk delete
4924deb | 2026-05-12 14:53:38 +0900 | Maksim Kuzmin | Remove generated repository map
5ade221 | 2026-05-12 14:46:27 +0900 | Maksim Kuzmin | Ignore generated repository maps
6297fbe | 2026-05-07 13:50:12 +0900 | Maksim Kuzmin | fix: remove all visibility restrictions for storekeeper role
```

### WarehouseAIWorkstation

- Path: `WarehouseAIWorkstation`
- Current branch: `main`
- Upstream: `origin/main`
- Ahead/behind: `1 / 0`
- Dirty: `yes`
- Staged / unstaged / untracked: `0 / 0 / 1`
- HEAD: `04daeae`
- HEAD subject: Bootstrap ready
- HEAD author/date: `Maksim Kuzmin / 2026-05-02 10:40:42 +0900`
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
?? docs/MIGRATION_AIWORKSTATION_TO_CORE_ANALYSIS.md
```

#### Recent commits

```text
04daeae | 2026-05-02 10:40:42 +0900 | Maksim Kuzmin | Bootstrap ready
981edf7 | 2026-04-12 22:54:27 +0900 | Maksim Kuzmin | stage5
f414330 | 2026-04-12 22:53:15 +0900 | Maksim Kuzmin | fix(stage5): close Directory workspace runtime defects and add smoke gate\n\n- Add missing theme resources (BrushTextSecondary, BrushError, BrushWarning, BrushSuccess)\n- Fix XAML command bindings to match actual ViewModel command names (NewItemCommand, SaveSelectedCommand, etc.)\n- Remove unsafe Task.Run initialization; move to Loaded event handler on UI thread\n- Complete detail panels with all business fields (Description, Code, SortOrder, IsActive)\n- Render AI flags as read-only (TextBlock with muted styling, not editable TextBox)\n- Normalize contract matrix auth format to X-User-Token (role: ...)\n- Add WPF smoke tests for Row ViewModel round-trips and flag formatting\n- Add Presentation reference to UnitTests project (net8.0-windows)\n\nBuild: 0 warnings, 0 errors. Tests: 73 passed.
2ed7442 | 2026-04-11 23:17:28 +0900 | Maksim Kuzmin | Harden bootstrap login flow and add stage 4 spec
27a9ede | 2026-04-11 22:50:11 +0900 | Maksim Kuzmin | fix(stage3): close remaining gaps — root setup visibility, logout flow, user management UI
```

### WarehouseMobile

- Path: `WarehouseMobile`
- Current branch: `master`
- Upstream: `-`
- Ahead/behind: `0 / 0`
- Dirty: `yes`
- Staged / unstaged / untracked: `0 / 0 / 13`
- HEAD: `e516d56`
- HEAD subject: First
- HEAD author/date: `Maksim Kuzmin / 2026-04-28 17:01:32 +0900`
- Tags at HEAD: `-`

#### Remotes

- `(none)`

#### Local branches

- `master` ← current

#### Remote branches

- `(none)`

#### Working tree status

```text
?? .idea/.name
?? .idea/AndroidProjectSystem.xml
?? .idea/codeStyles/
?? .idea/compiler.xml
?? .idea/deploymentTargetSelector.xml
?? .idea/gradle.xml
?? .idea/markdown.xml
?? .idea/misc.xml
?? .idea/runConfigurations.xml
?? .idea/vcs.xml
?? AGENTS.md
?? WHMobile_TZ.md
?? docs/
```

#### Recent commits

```text
e516d56 | 2026-04-28 17:01:32 +0900 | Maksim Kuzmin | First
```

## Notes for agents

- `Dirty = YES` means the repository has uncommitted changes.
- `Ahead > 0` means local branch has commits not pushed to upstream.
- `Behind > 0` means local branch is missing commits from upstream.
- This file is generated. Do not edit it manually.
