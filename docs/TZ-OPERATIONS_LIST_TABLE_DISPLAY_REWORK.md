# TZ: Operations List Table Display Rework

## Execution Strategy

- [x] 🟢 Parallel execution recommended
- **Reason:** задача делится на независимые контракты и UI-слои: SyncServer/BFF должны дать стабильные display-поля, Angular таблица должна изменить layout/поведение. Эти части можно делать параллельно после согласования DTO, затем интегрировать на реальном стенде.

### Parallel work units

| Stage | Unit | Owner area | Writable files/areas | Required inputs | Output/evidence |
|---|---|---|---|---|---|
| 1A | Display metadata contract | `SyncServer` + optional `Warehouse_web` pass-through | `SyncServer/app/schemas/operation.py`, operations service/repo response enrichment if needed, document numbering helper, `Warehouse_web/apps/sync_client/operations_api.py`, BFF tests if normalization is in Django | Number format and fields in this TZ | Operation list/detail DTO includes display number, site labels, author FIO/label, line count/status fields needed by UI and documents |
| 1B | Angular VM mapping | `Warehouse_frontend` services/models | `src/app/core/models/operations.models.ts`, `src/app/core/services/operations.service.ts`, specs | DTO from 1A | Row VM has no UUID fallback in visible table when display fields exist; robust fallback only for debug/tooltips |
| 2 | Table layout/action UX | `Warehouse_frontend` components | `features/operations/components/operations-table/operations-table.component.ts`, `operations-page.component.ts`, related styles/specs | Row VM from 1B | Table width aligns with filters; columns/action stack match requested proportions; number opens edit modal |
| 3 | Integration/QA | Parent/orchestrator | Integration fixes only | Completed 1A/1B/2 | Build/tests/stand/Playwright evidence |

### Integration checkpoints

1. Before UI implementation, agree final DTO names. Preferred names are listed in section 6.
2. If SyncServer cannot enrich author/site names in this iteration, BFF may enrich through existing APIs, but the browser must still receive display fields from Django BFF and must not perform N+1 SyncServer calls directly.
3. Document/invoice numbering must not be frontend-only. If накладные are generated backend-side, the same display number helper/field must be available to document generation.

## Execution Checklist

- [x] 0. Context verified
- [x] 1. Architecture boundaries confirmed
- [x] 2. Implementation stage 1A complete — display metadata contract
- [x] 3. Implementation stage 1B complete — Angular row VM mapping
- [x] 4. Implementation stage 2 complete — table layout/action UX
- [x] 5. Unit/component tests complete
- [x] 6. Integration tests with real dependencies complete
- [x] 7. Stand smoke tests complete
- [x] 8. UI automation tests complete
- [ ] 9. User scenario tests complete *(Playwright smoke покрывает таблицу, фильтры, пагинацию, клик по номеру; полные end-to-end сценарии не автоматизированы)*
- [x] 10. Regression checks complete
- [x] 11. Documentation updated
- [x] 12. Final acceptance review complete

## Check Rules

- Architect creates this checklist and acceptance criteria.
- Executor agents may check implementation and test items only after running the required verification.
- QA verifier may check final acceptance only after reviewing evidence.
- If a check is skipped or unavailable, it must stay unchecked with a blocker note.
- If the real stand is unavailable, use blocker note: `стенд недоступен`.

---

## 1. User Request Summary

The operations screen at `http://127.0.0.1:8001/operations` is acceptable in its header/buttons/filter form, but the table must be reworked.

Requested changes:

1. Table currently shows dashes / incomplete fields; it must show real operation fields.
2. Table must be the same visual width as the filter form/card above it.
3. Do not show UUID as operation number in table or invoices.
4. Generate/display operation number using:

```text
{site_id}/{created time hhmm}/{created date ddmmyy}
```

Example if `site_id=5` and `created_at=2026-06-02T08:38`: `5/0838/020626`.

5. Table columns:
   - first column: max `10%`, operation number; it is a link that opens the existing create/edit modal in edit mode;
   - `10%` operation type;
   - `5-10%` status; if there are multiple status lines, display vertically up to 4 lines;
   - `15%` direction;
   - `5%` positions count;
   - flex author field, showing FIO/name, not UUID;
   - date with minimal fitting width;
   - small action buttons in a vertical stack: invoice, acceptance when applicable, delete when operation is not accepted/submitted or logged-in user is root.

---

## 2. Functional Requirements Alignment

Relevant `Functional and WorkLogik.md` requirements:

- Section II.6.7: only unconfirmed operations are editable; after confirmation edits are restricted/forbidden.
- Section II.6.8: after confirmation an operation is a business event; changing rows/warehouses/quantity is forbidden.
- Section II.6.9: cancelling confirmed operations is root-only by default; others can cancel only unconfirmed/their drafts.
- Section II.7: operations table is a required UI table; base sorting is by date-time.
- Section II.8: operation lifecycle includes draft creation, adding ТМЦ, confirmation, invoice/PDF, and acceptance for target warehouse when applicable.

This TZ does **not** redefine post-confirmation business logic. It only defines list-table display and entry points into edit/acceptance/invoice/delete actions according to current permissions/statuses.

---

## 3. Architecture Boundaries

### Must keep

- `SyncServer` is source of truth for operations, users, sites, statuses, and document/invoice numbering data.
- `Warehouse_web` is Django host/BFF and may normalize/enrich display data, but must not become a second warehouse backend.
- Browser/Angular calls only Django same-origin BFF endpoints.
- Angular must not call SyncServer directly and must not receive/store SyncServer tokens.
- Operation writes/delete/submit still go through SyncServer services via BFF.

### Runtime path

```text
Browser /operations/
  -> Angular operations page in Django shell
  -> Django BFF /bff/api/v1/operations...
  -> Warehouse_web sync_client
  -> SyncServer /api/v1/operations...
```

### In scope

- Operation list/detail DTO display fields needed by table.
- Deterministic display operation number for table and documents/invoices.
- Angular `OperationListRowVm` mapping.
- Angular operations table layout and action buttons.
- Opening edit modal by clicking operation number.
- Delete action visibility/availability for unaccepted/unsubmitted operations and root.
- Acceptance action visibility for `RECEIVE`/`MOVE` when acceptance is pending/applicable.
- Invoice action entry point; actual PDF generation may remain disabled if backend route is not ready, but button/contract must be documented.

### Out of scope

- Reworking filters/header/buttons above the table.
- Creating the actual invoice/PDF flow if no current endpoint exists.
- Implementing post-confirmation acceptance business flow beyond table action entry point.
- Changing warehouse domain rules for cancellation/submission.
- Direct database access from Django/Angular.

---

## 4. Current State / Problem Statement

Observed current frontend code:

- `OperationsTableComponent` columns are currently: number, type, status, direction, date, author, positions, actions.
- `OperationsService.mapToRowVm()` falls back to `op.id.slice(0, 8).toUpperCase()` when `op.number` is absent.
- `directionLabel` uses `source_site_name` and `destination_site_name`, but current SyncServer `OperationResponse` schema explicitly exposes IDs and not site names.
- `createdByLabel` falls back to `created_by_user_id`, causing UUID-like author display when no label is supplied.
- `OperationResponse` has `site_id`, `source_site_id`, `destination_site_id`, `created_by_user_id`, `created_at`, `lines`, but no explicit `number`, `site_name`, `source_site_name`, `destination_site_name`, `created_by_label` in the schema.
- Result: table shows UUID-derived number, dashes for direction/type where mapping is incomplete, and UUID-ish author.

Executor must verify actual API JSON before implementing. If BFF already adds fields in some branch, use those names or normalize once in `OperationsService`.

---

## 5. Display Operation Number

### Required format

```text
{site_id}/{HHmm}/{ddMMyy}
```

Where:

- `site_id` is operation `site_id` from SyncServer, not source/destination label.
- `HHmm` is created time in 24h format with zero padding.
- `ddMMyy` is created date with zero padding and 2-digit year.

Example:

```text
site_id = 12
created_at = 2026-06-02T08:38:43Z
display_number = 12/0838/020626
```

### Source of truth

Preferred implementation:

- create a small server-side helper in `SyncServer` for display operation number;
- expose `display_number` or `number` in `OperationResponse` and list/detail responses;
- use the same helper/field in document/invoice generation to avoid table/document mismatch.

Fallback if backend cannot be changed in this iteration:

- BFF may compute `display_number` from `site_id` + `created_at` for the Angular table;
- invoice/document numbering must remain a blocker and must not be marked complete, because frontend-only number does not satisfy “таблицы и накладные”.

### Collision note

The requested format can collide for multiple operations created on the same site within one minute. This TZ must not invent extra suffixes without user approval. Executor must document collision risk. If duplicate display numbers appear, table still uses hidden `id` for navigation/actions, but visible number remains in requested format.

---

## 6. Preferred DTO Contract

Preferred operation list/detail item shape after SyncServer/BFF normalization:

```json
{
  "id": "uuid",
  "number": "5/0838/020626",
  "display_number": "5/0838/020626",
  "site_id": 5,
  "site_name": "Base",
  "operation_type": "MOVE",
  "type": "MOVE",
  "type_label": "Перемещение",
  "status": "draft",
  "status_label": "Черновик",
  "acceptance_state": "pending",
  "source_site_id": 5,
  "source_site_name": "Base",
  "destination_site_id": 7,
  "destination_site_name": "Site 2",
  "issue_object_name_snapshot": null,
  "created_by_user_id": "uuid",
  "created_by_label": "Иванов Иван Иванович",
  "created_at": "2026-06-02T08:38:43Z",
  "updated_at": "2026-06-02T08:38:43Z",
  "lines_count": 3,
  "lines": []
}
```

Required field behavior:

- `id` remains internal key; do not display it as primary number.
- `number` or `display_number` must be stable for table. Angular may prefer `display_number ?? number`.
- `type`/`operation_type` must be normalized in Angular so type label is never a dash for known operation types.
- `status_label` is optional if Angular has status label map, but multi-status display needs `acceptance_state` too.
- `site_name`, `source_site_name`, `destination_site_name`, `created_by_label` should be supplied by SyncServer or BFF; Angular must not perform per-row direct lookups to SyncServer.
- `lines_count` should be supplied or derived from `lines.length` if lines are included.

---

## 7. Direction Field Rules

Column width target: `15%`.

Direction label rules:

| Operation type | Direction display |
|---|---|
| `MOVE` | `<source_site_name> → <destination_site_name>` |
| `RECEIVE` | `→ <site_name or destination_site_name>` or `<site_name>` if product prefers compact form |
| `EXPENSE` | `<site_name or source_site_name> → расход` |
| `WRITE_OFF` | `<site_name or source_site_name> → списание` or issue object if source is object flow |
| `ISSUE` | `<site_name or source_site_name> → <issue_object_name_snapshot>` |
| `ISSUE_RETURN` | `<issue_object_name_snapshot> → <site_name or source_site_name>` |
| `CORRECTION` / `ADJUSTMENT` | `<site_name or source_site_name> → корректировка` |

If a label is missing but ID exists, show compact fallback such as `Склад #5`, not `—`, and log/track that BFF display enrichment is incomplete.

---

## 8. Status Column Rules

Column width target: `5-10%`.

Display one or more status lines, vertical stack, max 4 visible lines.

Suggested status lines:

1. Operation status label: `Черновик`, `Проведена`, `Отменена`, etc.
2. Acceptance status if relevant: `Приёмка: ожидает`, `Приёмка: частично`, `Приёмка: закрыта`.
3. Optional document/invoice state if backend provides it later.

Rules:

- For now, if only one status exists, render one badge/line.
- If more than 4 statuses are ever provided, show first 4 and add tooltip/title with full list.
- Do not invent fake statuses in frontend. Use DTO fields and existing status maps.

---

## 9. Table Layout Specification

### Width alignment

- Table card left/right edges must align with the filter panel/card above it.
- Do not make table wider/narrower than filters by separate margins.
- In current page structure, this likely means using the same horizontal margin/padding values for `.filters-card` and `.table-card`, or placing both in one width-constrained container.

### Column order and widths

| Order | Column | Width target | Behavior |
|---:|---|---:|---|
| 1 | Number | max 10% | link/button opens edit modal/detail; visible text is display number, not UUID |
| 2 | Type | 10% | localized type label; no dash for known type |
| 3 | Status | 5-10% | vertical stack up to 4 lines |
| 4 | Direction | 15% | compact direction label; tooltip for overflow |
| 5 | Positions | 5% | integer line count |
| 6 | Author | flex | FIO/display name, not UUID; tooltip may contain user ID for debugging only if needed |
| 7 | Date | minimal fitting width | `dd.MM.yyyy HH:mm`, no excessive width |
| 8 | Actions | small fixed width | vertical stack of icon buttons |

Implementation may use CSS grid instead of native table if it improves fixed/flex proportions, but must preserve accessibility and keyboard/click behavior.

### Text behavior

- Use ellipsis + `title` tooltip for long number/direction/author.
- Row height should accommodate up to 4 status lines but remain compact.
- Avoid horizontal scroll at FHD unless content area is unusually narrow.

---

## 10. Row Interactions

### Number link

- The visible operation number is clickable.
- Click opens existing creation modal in edit mode for that operation.
- Opening edit must load full operation detail by `GET /bff/api/v1/operations/{id}` before rendering editable lines, not open an empty draft.
- Keep row-level click only if it does not conflict with number/action clicks; otherwise number is the primary edit entry.

### Actions column

Render small buttons vertically:

1. `Накладная` / invoice:
   - show when operation status/type can have a document;
   - if backend PDF endpoint is not implemented, keep disabled with tooltip `Накладная будет реализована отдельно` and document blocker;
   - when implemented, must use display operation number in document, not UUID.
2. `Приёмка`:
   - applicable for `MOVE` and `RECEIVE` when acceptance is required/pending/applicable;
   - opens existing/future acceptance route/modal; if acceptance UI is not ready, disabled with tooltip.
3. `Удалить`:
   - enabled if operation is not accepted/submitted/confirmed according to current domain statuses;
   - enabled for root where backend policy permits;
   - uses existing `DELETE /bff/api/v1/operations/{id}` or cancel/delete flow defined by BFF;
   - requires confirmation dialog.

Do not use UUID as visible label in any action.

---

## 11. Implementation Stages

### Stage 0 — Context verification

Executor must re-read:

- `Functional and WorkLogik.md`, section II.6-II.8;
- `Warehouse_frontend/docs/ARCHITECTURE_FRONTEND_SPA.md`, especially BFF-only browser access and content mount rules;
- `Warehouse_frontend/AGENTS.md`, `Warehouse_web/AGENTS.md`, `SyncServer/AGENTS.md` if backend/BFF touched.

Acceptance:

- Completion report explicitly states this task keeps filters/header unchanged and only reworks table/display contracts.

### Stage 1A — Display metadata contract

Tasks:

1. Verify actual JSON from `GET /bff/api/v1/operations` and `GET /bff/api/v1/operations/{id}` on stand.
2. Add/normalize display number field using requested format.
3. Add/normalize site labels:
   - `site_name`;
   - `source_site_name`;
   - `destination_site_name`.
4. Add/normalize author label:
   - `created_by_label` should be FIO/full name/username, never raw UUID as primary display.
5. Add/normalize `lines_count` if absent.
6. Ensure document/invoice generation path can access the same display number. If not implemented, document blocker.

Preferred backend tests:

- display number for known `site_id` + `created_at` equals `{site_id}/{HHmm}/{ddMMyy}`;
- operation list/detail includes display fields;
- author label falls back to username/full_name before UUID;
- site labels present for source/destination/site where IDs exist.

If implemented in BFF instead of SyncServer:

- add BFF tests that operation list response is enriched and Angular-facing JSON includes fields;
- leave invoice/document number acceptance unchecked unless backend documents also use the helper/field.

### Stage 1B — Angular VM mapping

Tasks:

1. Extend `OperationDto`/`OperationListRowVm` as needed:
   - `displayNumber`;
   - `siteId`, `siteName`;
   - `statusLines`;
   - action booleans `canInvoice`, `canAccept`, `canDelete` if clearer than existing fields.
2. Normalize `operation_type` vs `type` if backend returns only `operation_type`.
3. Map backend `ADJUSTMENT` to frontend correction label if current frontend still uses `CORRECTION`.
4. Implement display number fallback:
   - prefer `display_number`;
   - then `number`;
   - then deterministic client computed value from `site_id` + `created_at` only as temporary fallback;
   - never show UUID fallback except maybe in tooltip/debug when no required fields exist.
5. Direction builder must use labels or compact `Склад #id` fallback, not `—` when IDs exist.
6. Author builder must show `created_by_label`; if absent, show `Пользователь` or username fallback from BFF, not truncated UUID as primary text.

Unit tests:

- row VM maps display number correctly;
- row VM builds MOVE direction with source/destination names;
- row VM falls back to `Склад #id` when label missing;
- row VM does not use UUID as visible author when label missing;
- row VM maps type/status labels for current backend values.

### Stage 2 — Angular table layout/action UX

Tasks:

1. Rework `OperationsTableComponent` layout to requested columns and widths.
2. Align table card width with filter card.
3. Make first column number a link/button that emits edit/open event.
4. Keep action clicks from triggering row/number click.
5. Render action buttons vertically with clear titles/aria-labels:
   - invoice;
   - acceptance;
   - delete.
6. Preserve pagination behavior.
7. Preserve sorting behavior; date remains default base sort unless backend/page sort is introduced.
8. Keep existing filter form untouched unless only margin/wrapper alignment is needed.

Component/UI tests:

- table renders display number link and not UUID;
- clicking number emits/open edit event;
- actions are vertical and stop event propagation;
- columns render in required order;
- empty state still works;
- pagination still works.

---

## 12. Test Strategy

### Static checks

Frontend:

```bash
cd Warehouse_frontend
npm run build
```

Backend/BFF if touched:

```bash
docker exec warehouse_syncserver python -m pytest <targeted tests>
docker exec warehouse_web python manage.py test <targeted tests>
```

### Unit tests

Required:

- display number helper test (`site_id`, `created_at` -> `site/hhmm/ddmmyy`);
- Angular row mapper tests for number/type/status/direction/author/actions;
- BFF/SyncServer tests for enriched response if backend/BFF touched.

Suggested frontend command:

```bash
cd Warehouse_frontend
npx vitest run src/app/core/services/operations.service.spec.ts
```

If Vitest fails due missing optional Rollup dependency, record blocker and/or run build plus Playwright smoke; do not delete `node_modules` without approval.

### Component tests

Applicable:

- table layout order;
- number link behavior;
- action stack rendering;
- status multiline rendering up to 4 lines.

If component test infra is unavailable, leave unchecked with blocker and compensate with Playwright evidence.

### Integration tests with real dependencies

Required because this touches runtime displayed data from backend/BFF.

Verify on Docker stand:

- operation list JSON has display fields;
- Angular table shows display number, labels, author name, direction, positions count;
- no UUID visible in number/author columns for normal rows;
- edit opens full saved operation detail;
- delete action calls correct BFF endpoint and refreshes list;
- acceptance/invoice buttons are visible/disabled/enabled according to status/type.

### Stand smoke tests

Health checks if requests fail:

```bash
curl -s --max-time 5 http://localhost:8000/api/v1/health
curl -s --max-time 5 http://localhost:8001/healthz/
pg_isready -h localhost -p 5432 -t 3
curl -s --max-time 5 http://localhost:4200/
```

Smoke scenario:

1. Open `/operations/`.
2. Verify filters/header unchanged.
3. Verify table card aligns with filter card width.
4. Verify every visible row has non-UUID operation number in format `site/hhmm/ddmmyy`.
5. Verify type/status/direction/positions/author/date/action columns show real data.
6. Click operation number; edit modal opens with that operation.
7. For a MOVE/RECEIVE pending acceptance row, verify acceptance action visibility.
8. For a draft/unsubmitted row, verify delete action visibility and confirmation flow.
9. Verify invoice action is present; if disabled, tooltip explains blocker.

### UI automation

Use Playwright where possible. Evidence should include:

- screenshot of table aligned with filters;
- screenshot/trace showing operation number link opens edit modal;
- assertion that no UUID-like string is shown in number column for normal rows.

### Regression pack

Must verify no regression in:

- operations filters/search/status tabs;
- create operation button/modal entry;
- pagination;
- role-specific cancelled visibility;
- BFF-only browser access;
- previously added operation search by ТМЦ/SKU/hashtag.

---

## 13. Test Stand

### Services

| Service | Address | Health Check | Container |
|---|---|---|---|
| SyncServer API | `http://localhost:8000` | `GET /api/v1/health` | `warehouse_syncserver` |
| Django / BFF | `http://localhost:8001` | `GET /healthz/` | `warehouse_web` |
| PostgreSQL | `localhost:5432` | `pg_isready -h localhost -p 5432 -t 3` | `warehouse_postgres` |
| Angular | `http://localhost:4200` | `GET /` | `warehouse_angular` |

### Lifecycle

- Default assumption: stand is running.
- If unavailable, run from workspace root:

```bash
make up
```

- If Makefile path fails, try:

```bash
docker compose up -d
```

- Do not run destructive DB/Docker cleanup without explicit approval.

### Seed data

Need at least:

- authenticated root/chief/storekeeper user with readable operations;
- one operation of each important type if possible: draft, submitted, pending acceptance, cancelled/root-only;
- at least one MOVE/RECEIVE operation with source/destination labels;
- users with full name/username so author column can be verified;
- at least one operation with multiple lines for positions count.

### Environment variable names only

- `DJANGO_ENV`
- `SYNC_SERVER_URL`
- `SYNC_ROOT_USER_TOKEN`
- `SYNC_DEVICE_TOKEN`
- `DATABASE_URL`
- `DJANGO_SETTINGS_MODULE`
- `SECRET_KEY`

Never print or hardcode secret values.

---

## 14. Acceptance Criteria

### Data/display acceptance

- [ ] Operation number column shows `{site_id}/{HHmm}/{ddMMyy}` and not UUID.
- [ ] Same display number is available to invoice/document generation path, or blocker is explicitly documented.
- [ ] Type column shows localized operation type, not dash.
- [ ] Status column shows localized status and acceptance state where applicable.
- [ ] Direction column shows meaningful direction/site/object labels, not dash when IDs exist.
- [ ] Positions count shows actual line count.
- [ ] Author column shows FIO/full name/username, not UUID as primary text.
- [ ] Date column uses compact `dd.MM.yyyy HH:mm`.

### Layout acceptance

- [ ] Table card left/right width aligns with filters form/card.
- [ ] Columns are ordered as requested.
- [ ] Width proportions are approximately: number max 10%, type 10%, status 5-10%, direction 15%, positions 5%, author flex, date minimal, actions fixed small.
- [ ] Action buttons are vertical, compact, and accessible via title/aria-label.
- [ ] Long text uses ellipsis/tooltips without breaking row layout.

### Interaction acceptance

- [ ] Clicking number opens edit modal for the selected operation.
- [ ] Action buttons do not trigger row/number click.
- [ ] Invoice action is present and either functional or clearly disabled with blocker tooltip.
- [ ] Acceptance action appears for applicable MOVE/RECEIVE acceptance states.
- [ ] Delete action appears/enables only for allowed unaccepted/unsubmitted/root cases and calls BFF with confirmation.
- [ ] Pagination and existing filters still work.

### Architecture acceptance

- [ ] Angular calls only Django BFF.
- [ ] No SyncServer tokens in browser code/storage.
- [ ] No local Django domain write drift.
- [ ] Display fields are supplied/normalized server-side or BFF-side; Angular does not perform per-row direct SyncServer lookups.

---

## 15. Evidence Required In Executor Report

Executor final report must include:

```markdown
## Evidence

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|
| Static build | `npm run build` | pass/fail | short log/path |
| SyncServer tests | `docker exec warehouse_syncserver python -m pytest ...` | pass/fail/skipped | test names/log |
| Django BFF tests | `docker exec warehouse_web python manage.py test ...` | pass/fail/skipped | test names/log |
| Frontend unit/component | `npx vitest run ...` | pass/fail/skipped | log/blocker |
| Stand smoke | browser/curl | pass/fail/skipped | URL/screenshot/log |
| UI automation | Playwright | pass/fail/skipped | trace/screenshot path |
| Regression | manual/automated | pass/fail/skipped | affected flows note |
```

Final acceptance may be checked only after evidence confirms no UUID display in number/author columns, table/filter width alignment, number-link edit flow, and action visibility rules.
