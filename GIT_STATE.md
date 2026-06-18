# Git State

Generated at: `2026-06-18T13:51`
Root: `/home/makc/AI_sandbox/warehouse_solution`
Fetch before scan: `no`

## Summary

| Repo | Branch | Upstream | Ahead | Behind | Dirty | HEAD | Last commit |
|---|---|---|---:|---:|---|---|---|
| `SyncServer` | `dev` | `origin/dev` | 0 | 0 | YES | `889f40b` | feat: add CLI audit query script (query_audit.py) |
| `Warehouse_client_core` | `dev` | `origin/dev` | 0 | 0 | no | `436d370` | review: accepted TZ-CORE_CATCH_UP_TO_ONLINE_CLIENT — archive completed TZ |
| `Warehouse_frontend` | `dev` | `origin/dev` | 0 | 0 | YES | `60a875e` | V3.1: angular — add line numbers (# col) and total quantity to operation create modal |
| `Warehouse_web` | `dev` | `origin/dev` | 0 | 0 | YES | `0d21415` | feat: password self-service page with profile view, navbar link, admin clean_password |
| `WarehouseAIWorkstation` | `dev` | `-` | 0 | 0 | no | `981edf7` | stage5 |

## Details

### SyncServer

- Path: `SyncServer`
- Current branch: `dev`
- Upstream: `origin/dev`
- Ahead/behind: `0 / 0`
- Dirty: `yes`
- Staged / unstaged / untracked: `0 / 6 / 0`
- HEAD: `889f40b`
- HEAD subject: feat: add CLI audit query script (query_audit.py)
- HEAD author/date: `makc / 2026-06-18 13:46:59 +0900`
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
 M docs/API_REFERENCE.md
 M tests/test_lost_assets_api.py
 M tests/test_operations_issue_semantics.py
 M tests/test_operations_service_delete.py
 M tests/test_operations_service_inventory_subject_write_path.py
 M tests/test_reports_read_model.py
```

#### Recent commits

```text
889f40b | 2026-06-18 13:46:59 +0900 | makc | feat: add CLI audit query script (query_audit.py)
df325e5 | 2026-06-18 12:16:39 +0900 | makc | fix(SyncServer): migration 0018 — make item_id nullable in issued_asset_balances and balances
0a24899 | 2026-06-16 15:20:29 +0900 | makc | V3.1: sync — remove read scope, add observer create draft, add CREATE_DRAFT_ROLES
a97f5db | 2026-06-16 14:51:41 +0900 | makc | review: accepted TZs V3.1 — logging (A) + audit journal (V)
ea13de7 | 2026-06-16 10:59:33 +0900 | makc | 3.0.1: SyncServer logging + stale-balance regression
```

### Warehouse_client_core

- Path: `Warehouse_client_core`
- Current branch: `dev`
- Upstream: `origin/dev`
- Ahead/behind: `0 / 0`
- Dirty: `no`
- Staged / unstaged / untracked: `0 / 0 / 0`
- HEAD: `436d370`
- HEAD subject: review: accepted TZ-CORE_CATCH_UP_TO_ONLINE_CLIENT — archive completed TZ
- HEAD author/date: `makc / 2026-06-05 15:17:24 +0900`
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
436d370 | 2026-06-05 15:17:24 +0900 | makc | review: accepted TZ-CORE_CATCH_UP_TO_ONLINE_CLIENT — archive completed TZ
61e4901 | 2026-06-05 13:40:27 +0900 | makc | docs: update archived TZ checklist — mark Levels 10-12 done
90c56d6 | 2026-06-05 13:40:09 +0900 | makc | docs: mark TZ CORE CATCH UP checklist complete — all 17/18 items verified
97e11fc | 2026-06-04 13:39:29 +0900 | makc | fix(core): add catalog audit fields persistence (migration v8 + snapshot_writer)
54a6836 | 2026-06-04 13:35:41 +0900 | makc | feat(core): add documents_create_for_operation POST method
```

### Warehouse_frontend

- Path: `Warehouse_frontend`
- Current branch: `dev`
- Upstream: `origin/dev`
- Ahead/behind: `0 / 0`
- Dirty: `yes`
- Staged / unstaged / untracked: `0 / 0 / 1`
- HEAD: `60a875e`
- HEAD subject: V3.1: angular — add line numbers (# col) and total quantity to operation create modal
- HEAD author/date: `makc / 2026-06-18 10:40:02 +0900`
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
?? test-results-old/
```

#### Recent commits

```text
60a875e | 2026-06-18 10:40:02 +0900 | makc | V3.1: angular — add line numbers (# col) and total quantity to operation create modal
5b602dc | 2026-06-16 15:20:31 +0900 | makc | V3.1: angular — add catalog write guard, update observer can edit draft, canWriteCatalog from role
27befc2 | 2026-06-16 14:51:44 +0900 | makc | review: accepted TZ-V3.1_LOGGING — Angular error infrastructure
7ad29fb | 2026-06-16 10:59:24 +0900 | makc | 3.0.1: Angular UI quick fixes
e7b05fe | 2026-06-12 13:33:23 +0900 | makc | fix(operations): exclude adjustments by default, tighten table layout, fallback comment from notes
```

### Warehouse_web

- Path: `Warehouse_web`
- Current branch: `dev`
- Upstream: `origin/dev`
- Ahead/behind: `0 / 0`
- Dirty: `yes`
- Staged / unstaged / untracked: `0 / 3 / 2`
- HEAD: `0d21415`
- HEAD subject: feat: password self-service page with profile view, navbar link, admin clean_password
- HEAD author/date: `makc / 2026-06-18 11:31:19 +0900`
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
 M static/css/app.css
 M templates/base.html
 M templates/registration/login.html
?? media/documents/pdf/nakladnaya_2_1453_110626.pdf
?? media/documents/pdf/nakladnaya_4_0820_040626.pdf
```

#### Recent commits

```text
0d21415 | 2026-06-18 11:31:19 +0900 | makc | feat: password self-service page with profile view, navbar link, admin clean_password
2425148 | 2026-06-17 13:25:20 +0900 | makc | V3.1: django — unblock observer in legacy SSR views (dashboard, balances, operations, catalog)
96145ed | 2026-06-16 15:20:30 +0900 | makc | V3.1: django — remove storekeeper forced balance site filter
25fa643 | 2026-06-16 14:51:43 +0900 | makc | review: accepted TZs V3.1 — logging (A) + audit journal (V)
143bb29 | 2026-06-16 10:59:29 +0900 | makc | 3.0.1: Django SyncServer users import
```

### WarehouseAIWorkstation

- Path: `WarehouseAIWorkstation`
- Current branch: `dev`
- Upstream: `-`
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

- `dev` ← current
- `main`

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
