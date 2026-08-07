# Git State

Generated at: `2026-08-07T14:36`
Root: `/home/makc/AI_sandbox/warehouse_solution`
Fetch before scan: `no`

## Summary

| Repo | Branch | Upstream | Ahead | Behind | Dirty | HEAD | Last commit |
|---|---|---|---:|---:|---|---|---|
| `SyncServer` | `dev` | `origin/dev` | 0 | 0 | no | `b24bac4` | feat(roles): agent domain role (ADR-0030, TZ-AGENT-ROLE-SYNCSERVER rev.2) |
| `Warehouse_client_core` | `dev` | `origin/dev` | 0 | 0 | YES | `9b6ccbe` | TZ-V3.1_SYNC_AND_DEVICE_MANAGEMENT: Stage 3 — Rust core gaps (payload_hash SHA-256, write_operations docs, E2E tests) |
| `Warehouse_frontend` | `dev` | `origin/dev` | 0 | 0 | YES | `22d8599` | test(e2e): add poppler-utils/pdftotext to playwright image |
| `Warehouse_web` | `dev` | `origin/dev` | 0 | 0 | YES | `832745c` | test: fix root nomenclature SPA test: require is_superuser for is_root() |
| `WarehouseAIWorkstation` | `dev` | `-` | 0 | 0 | no | `981edf7` | stage5 |
| `WarehouseWorkstation` | `main` | `origin/main` | 0 | 0 | YES | `1e11a9a` | to devstand migrate |

## Details

### SyncServer

- Path: `SyncServer`
- Current branch: `dev`
- Upstream: `origin/dev`
- Ahead/behind: `0 / 0`
- Dirty: `no`
- Staged / unstaged / untracked: `0 / 0 / 0`
- HEAD: `b24bac4`
- HEAD subject: feat(roles): agent domain role (ADR-0030, TZ-AGENT-ROLE-SYNCSERVER rev.2)
- HEAD author/date: `makc / 2026-08-07 14:22:30 +0900`
- Tags at HEAD: `-`

#### Remotes

- `origin`: `git@github.com:steeltalon777/SyncServer.git`

#### Local branches

- `dev` ← current
- `feat/operation-submit-domain-errors`
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
clean
```

#### Recent commits

```text
b24bac4 | 2026-08-07 14:22:30 +0900 | makc | feat(roles): agent domain role (ADR-0030, TZ-AGENT-ROLE-SYNCSERVER rev.2)
2e41b7c | 2026-08-07 13:12:20 +0900 | makc | docs(syncserver): TZ + ADR-0030 rev.2 for agent domain role (Issue #18)
88458d6 | 2026-08-07 12:53:11 +0900 | makc | 3.3 pre ready
a8f713f | 2026-08-07 12:52:33 +0900 | makc | docs(syncserver): TZ + ADR-0030 for agent domain role (Issue #18)
e019c17 | 2026-08-06 15:31:35 +0900 | makc | TZ-V3.3: гарантированный порядок строк операции по line_number
```

### Warehouse_client_core

- Path: `Warehouse_client_core`
- Current branch: `dev`
- Upstream: `origin/dev`
- Ahead/behind: `0 / 0`
- Dirty: `yes`
- Staged / unstaged / untracked: `0 / 2 / 0`
- HEAD: `9b6ccbe`
- HEAD subject: TZ-V3.1_SYNC_AND_DEVICE_MANAGEMENT: Stage 3 — Rust core gaps (payload_hash SHA-256, write_operations docs, E2E tests)
- HEAD author/date: `makc / 2026-07-01 18:01:45 +0900`
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
 M README.md
 M crates/warehouse_ffi/src/lib.rs
```

#### Recent commits

```text
9b6ccbe | 2026-07-01 18:01:45 +0900 | makc | TZ-V3.1_SYNC_AND_DEVICE_MANAGEMENT: Stage 3 — Rust core gaps (payload_hash SHA-256, write_operations docs, E2E tests)
436d370 | 2026-06-05 15:17:24 +0900 | makc | review: accepted TZ-CORE_CATCH_UP_TO_ONLINE_CLIENT — archive completed TZ
61e4901 | 2026-06-05 13:40:27 +0900 | makc | docs: update archived TZ checklist — mark Levels 10-12 done
90c56d6 | 2026-06-05 13:40:09 +0900 | makc | docs: mark TZ CORE CATCH UP checklist complete — all 17/18 items verified
97e11fc | 2026-06-04 13:39:29 +0900 | makc | fix(core): add catalog audit fields persistence (migration v8 + snapshot_writer)
```

### Warehouse_frontend

- Path: `Warehouse_frontend`
- Current branch: `dev`
- Upstream: `origin/dev`
- Ahead/behind: `0 / 0`
- Dirty: `yes`
- Staged / unstaged / untracked: `0 / 4 / 3`
- HEAD: `22d8599`
- HEAD subject: test(e2e): add poppler-utils/pdftotext to playwright image
- HEAD author/date: `makc / 2026-08-07 10:44:37 +0900`
- Tags at HEAD: `-`

#### Remotes

- `origin`: `git@github.com:steeltalon777/Warehouse_frontend.git`

#### Local branches

- `dev` ← current
- `feat/operation-submit-domain-errors`
- `main`

#### Remote branches

- `origin/dev`
- `origin/main`

#### Working tree status

```text
 M src/app/features/operations/components/item-cache-search/item-cache-search.component.ts
 M src/app/features/operations/components/operation-create-modal/operation-create-modal.component.ts
 M src/app/features/operations/components/operation-create-modal/operation-lines-table.component.ts
 M src/app/features/operations/components/operation-create-modal/operation-lines-table.spec.ts
?? e2e/operations/operations-balances-manual.spec.ts
?? src/app/features/operations/components/item-cache-search/item-cache-search.component.spec.ts
?? src/app/features/operations/components/operation-create-modal/operation-create-modal.component.spec.ts
```

#### Recent commits

```text
22d8599 | 2026-08-07 10:44:37 +0900 | makc | test(e2e): add poppler-utils/pdftotext to playwright image
84d0066 | 2026-08-07 10:44:20 +0900 | makc | fix(operations): await auth context before mapping permissions
48c2071 | 2026-08-06 16:56:54 +0900 | makc | feat(v3.2): Stage D Extension (W1+W2) — batch-resolve + modal-stays-open
db4ea93 | 2026-08-06 16:08:58 +0900 | makc | test(v3.2): TZ §7.5 Playwright coverage — catalog refresh + save reliability
6af39d5 | 2026-07-31 17:28:24 +0900 | makc | fix(acceptance): localize 403 to Russian for structured BFF errors
```

### Warehouse_web

- Path: `Warehouse_web`
- Current branch: `dev`
- Upstream: `origin/dev`
- Ahead/behind: `0 / 0`
- Dirty: `yes`
- Staged / unstaged / untracked: `0 / 1 / 1`
- HEAD: `832745c`
- HEAD subject: test: fix root nomenclature SPA test: require is_superuser for is_root()
- HEAD author/date: `makc / 2026-07-31 17:28:16 +0900`
- Tags at HEAD: `-`

#### Remotes

- `origin`: `git@github.com:steeltalon777/Warehouse_web.git`

#### Local branches

- `dev` ← current
- `feat/operation-submit-domain-errors`
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
 M apps/bff_api/reports_views.py
?? apps/bff_api/tests_reports.py
```

#### Recent commits

```text
832745c | 2026-07-31 17:28:16 +0900 | makc | test: fix root nomenclature SPA test: require is_superuser for is_root()
36f1fec | 2026-07-31 16:37:05 +0900 | makc | feat(bff): api_error_response structured proxy for submit endpoint (WIP)
2d0dff9 | 2026-07-23 14:27:50 +0900 | makc | test(bff): add tests for /bff/api/v1/operations/from-source-document
efe500a | 2026-07-23 13:22:01 +0900 | makc | feat(bff): add POST /bff/api/v1/operations/from-source-document proxy endpoint
23db903 | 2026-07-15 15:42:30 +0900 | makc | feat(bff): UI diagnostics proxy endpoint (TZ Stage 3, WP-1)
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

### WarehouseWorkstation

- Path: `WarehouseWorkstation`
- Current branch: `main`
- Upstream: `origin/main`
- Ahead/behind: `0 / 0`
- Dirty: `yes`
- Staged / unstaged / untracked: `0 / 1 / 0`
- HEAD: `1e11a9a`
- HEAD subject: to devstand migrate
- HEAD author/date: `Maksim Kuzmin / 2026-06-19 17:28:54 +0900`
- Tags at HEAD: `-`

#### Remotes

- `origin`: `https://github.com/steeltalon777/WarehouseWorkstation.git`

#### Local branches

- `main` ← current

#### Remote branches

- `origin/main`

#### Working tree status

```text
 M README.md
```

#### Recent commits

```text
1e11a9a | 2026-06-19 17:28:54 +0900 | Maksim Kuzmin | to devstand migrate
04daeae | 2026-05-02 10:40:42 +0900 | Maksim Kuzmin | Bootstrap ready
981edf7 | 2026-04-12 22:54:27 +0900 | Maksim Kuzmin | stage5
f414330 | 2026-04-12 22:53:15 +0900 | Maksim Kuzmin | fix(stage5): close Directory workspace runtime defects and add smoke gate\n\n- Add missing theme resources (BrushTextSecondary, BrushError, BrushWarning, BrushSuccess)\n- Fix XAML command bindings to match actual ViewModel command names (NewItemCommand, SaveSelectedCommand, etc.)\n- Remove unsafe Task.Run initialization; move to Loaded event handler on UI thread\n- Complete detail panels with all business fields (Description, Code, SortOrder, IsActive)\n- Render AI flags as read-only (TextBlock with muted styling, not editable TextBox)\n- Normalize contract matrix auth format to X-User-Token (role: ...)\n- Add WPF smoke tests for Row ViewModel round-trips and flag formatting\n- Add Presentation reference to UnitTests project (net8.0-windows)\n\nBuild: 0 warnings, 0 errors. Tests: 73 passed.
2ed7442 | 2026-04-11 23:17:28 +0900 | Maksim Kuzmin | Harden bootstrap login flow and add stage 4 spec
```

## Notes for agents

- `Dirty = YES` means the repository has uncommitted changes.
- `Ahead > 0` means local branch has commits not pushed to upstream.
- `Behind > 0` means local branch is missing commits from upstream.
- This file is generated. Do not edit it manually.
