# ADR-0028 — Historical Integrity Stage A: страховки, effect-time и integrity diagnostics

- **Status:** Accepted — implementation pending
- **Date:** 2026-08-05
- **Deciders:** пользователь, Architect Agent
- **Scope:** `SyncServer/`, transparent report-param passthrough в `Warehouse_web`, операторский root `Makefile`
- **Companion TZ:** `docs/TZ-HISTORICAL_INTEGRITY_STAGE_A.md`
- **Source research:** `docs/audit/HISTORICAL_INTEGRITY_AUDIT.md`, `HISTORICAL_RISK_REGISTER.md`, `HISTORICAL_INTEGRITY_ROADMAP.md`, `HISTORICAL_DATA_FLOW.md`, `SEASON_REPORT_READINESS.md`
- **Related decisions:** ADR-0003, ADR-0004, ADR-0018
- **Supersedes:** уточняет Stage A roadmap там, где read-only аудит не совпадает с фактическим кодом; не отменяет этапы B–E

## Context

Read-only аудит от 2026-07-31 выявил P0/P1 gaps исторической целостности SyncServer и предложил Stage A из семи страховочных пакетов A-1…A-7. Пользователь 2026-08-05 явно разрешил выпуск ADR и исполнимого ТЗ.

### Подтверждённые факты кода на 2026-08-05

1. `OperationsWorkflowPolicy.require_not_cancelled_for_effective_at_change()` запрещает изменение `effective_at` только для `cancelled`. `submitted` проходит guard (`app/services/operations_workflow_policy.py:15-20`, `operations_service.py:1336-1381`).
2. `restore_operation()` переводит cancelled → draft и очищает cancel metadata, но не пишет `audit_event` (`operations_service.py:2777-2793`, `operations_repo.py:278-293`).
3. `CatalogAdminService.delete_unit/delete_category/delete_item()` вызывает repo soft-delete без audit event (`catalog_admin_service.py:421-459`).
4. `accept_operation_lines()` создаёт `OperationAcceptanceAction`, но пишет только aggregate `operation.acceptance_complete` при полном resolve. Per-action события отсутствуют (`operations_service.py:2268-2406`).
5. В accepted branch `accept_operation_lines()` напрямую вызывает `balances.update_balance_quantity(+accepted_delta)`, но не создаёт `audit_item_effects`.
6. `resolve_lost_asset()` также напрямую увеличивает складской баланс для `found_to_destination`/`return_to_source`, но не создаёт ни audit event, ни `audit_item_effects` (`operations_service.py:2408-2476`).
7. Следовательно, утверждение исходного аудита «каждое изменение `balances.qty` сопровождается `audit_item_effect`» и текущий `docs/audit-event-catalog.md` contract для `operation.acceptance_complete` не соответствуют коду. Без устранения этих gaps проверка `balances == SUM(audit_item_effects)` принципиально не может стать зелёной.
8. `AuditItemEffect` хранит только physical `created_at=server now`; business/effect timestamp отсутствует (`app/models/audit_item_effect.py:23-112`).
9. `ReportsRepo.list_item_movement()` строится не из `audit_item_effects`, а из `operations UNION ALL operation_lines`. Поэтому roadmap-предложение «filter `AuditItemEffect.is_system_generated=False`» нельзя применить к этому endpoint без полной замены read model (`app/repos/reports_repo.py:23-224`). Текущий DB-backed test помечен xfail из-за отсутствующего `TemporaryItem.name` в GROUP BY (`tests/test_reports_read_model.py:260`), значит A-6 обязан сначала вернуть endpoint в зелёное состояние.
10. В текущем report source системная природа операции уже хранится в `Operation.origin='system'`; merge/review/temporary transfers создают system ADJUSTMENT operations.
11. `balances.qty` имеет `NUMERIC(18,3)`, `audit_item_effects.quantity_delta` — `NUMERIC(18,4)`. Проверка должна использовать decimal/SQL NUMERIC и явную нормализацию масштаба, не float tolerance.
12. Текущий Alembic head в исследованной ветке — `0036_operation_revision_lines_composite_pk`; номер новой revision исполнитель обязан повторно проверить перед реализацией.

### Конфликты внутри исходных документов

- Risk register предлагает `exclude_system_effects` default `false`, roadmap — default `true`.
- Roadmap предлагает backfill всех effects из `operations.effective_at`, но это ошибочно датирует cancel reversal и позднюю приёмку исходной датой операции.
- Risk register и Season Readiness используют разные ordinal labels Q1…Q7 для разных SQL checks.
- Roadmap считает R-26 закрытым одной Make-командой, хотя R-26 описывает scheduled execution.

ADR обязан снять эти неоднозначности до реализации.

## Decision

### 1. Stage A остаётся точечным hardening без новой доменной модели

Stage A изменяет guards, audit capture, одну существующую effect table, report filtering и operator diagnostics. Не вводятся новые domain tables, event sourcing, period close, source-document storage, merge line map или unmerge.

Все мутации остаются в SyncServer service + UnitOfWork. Route-only guards, прямые DB writes из клиентов и отдельный audit datastore запрещены.

### 2. `effective_at` операции становится draft-only mutable

Dedicated `PATCH /api/v1/operations/{id}/effective-at` разрешён только при `operation.status == 'draft'`.

| Status | Результат |
|---|---|
| `draft` | существующий authz и update flow |
| `submitted` | HTTP 409, mutation отсутствует |
| `cancelled` | HTTP 409, mutation отсутствует |
| иной/legacy | HTTP 409, fail closed |

Guard располагается в workflow/service boundary и вызывается до чтения `previous_effective_at`/mutation. Route остаётся thin. DB trigger в Stage A не вводится: immutable-on-update правило нельзя корректно выразить обычным CHECK, а trigger — отдельная DB policy, запланированная Stage B.

Restore не является исключением: restored operation уже получает статус `draft`, после чего дату можно изменить обычным draft-only flow.

### 3. Жизненный цикл и soft-delete получают атомарные audit events

#### 3.1. Restore

Успешный cancelled → draft пишет ровно одно `operation.restore` событие в том же UoW. `changes` v2 содержит:

- `previous_status='cancelled'`, `new_status='draft'`;
- `previous_version`, `new_version`;
- `cancelled_at_before`, `cancelled_by_user_id_before`, `cancel_reason_before`;
- `restored_by_user_id`.

Если найден последний successful `operation.cancel` этой операции, `operation.restore.parent_event_id` указывает на его public `event_id`. Отсутствие legacy cancel event не блокирует restore: parent остаётся `null`, а `changes.cancel_event_missing=true` делает gap наблюдаемым.

Мы не запрещаем restore «если операция была изменена после отмены»: это противоречило бы `Functional and WorkLogik.md` §II.6.10 и требует отдельного продуктового решения. R-12 закрывается наблюдаемостью цикла, не новым запретом.

#### 3.2. Catalog soft-delete

Вводятся события:

- `item.delete`;
- `category.delete`;
- `unit.delete`.

Каждое событие имеет `entity_type/entity_id`, `outcome='success'`, minimal `changes` (`deleted_at`, `deleted_by_user_id`) и `audit_event_resources(relation='primary')` со snapshot before/after.

Snapshot allow-list:

| Entity | Snapshot fields |
|---|---|
| item | `id`, `sku`, `name`, `category_id`, `unit_id`, `is_active`, `requires_review`, `review_status`, `merged_into_id`, `deleted_at`, `deleted_by_user_id` |
| category | `id`, `name`, `code`, `parent_id`, `sort_order`, `is_active`, `merged_into_id`, `deleted_at`, `deleted_by_user_id` |
| unit | `id`, `name`, `code`, `symbol`, `sort_order`, `is_active`, `deleted_at`, `deleted_by_user_id` |

Free text (`description`, `notes`), hashtags, source refs, credentials и relationship graphs не копируются. Guard failure не создаёт событие.

### 4. Acceptance audit completeness расширяется до всех warehouse balance mutations

Исходный A-4 недостаточен. Stage A фиксирует per-action observability **и** отсутствующие warehouse effects.

#### 4.1. `accept_operation_lines`

На каждое non-zero действие:

| Action | Audit event | Warehouse effect |
|---|---|---|
| `accept` | `operation.line_accepted` | `effect_type='acceptance'`, `quantity_delta=+accepted_delta`, destination site |
| `mark_lost` | `operation.line_mark_lost` | нет: warehouse balance не меняется |

Если один payload для одной строки содержит accepted и lost quantity, создаются два события. Каждое ссылается на созданный `OperationAcceptanceAction.id`; line progress snapshot before/after фиксируется через primary `operation_line` resource. `operation.acceptance_complete` остаётся aggregate lifecycle event и **не владеет** per-line effects.

#### 4.2. `resolve_lost_asset`

Каждое действие пишет `operation.line_lost_resolved` с `changes.action_type`:

| Action type | Balance mutation | Warehouse effect |
|---|---|---|
| `found_to_destination` | destination `+qty` | `acceptance` |
| `return_to_source` | source `+qty` | `acceptance` |
| `write_off` | warehouse balance не меняется | нет |

Event/effect/action/register update выполняются атомарно. Это минимальное расширение не меняет acceptance math или state machine.

#### 4.3. Effect ownership

Effect всегда ссылается на audit event, непосредственно вызвавший balance mutation. Нельзя прикреплять позднюю приёмку к старому `operation.submit` или aggregate completion event.

`_write_captured_effects` становится fail-closed: если `capture` непуст, отсутствие `uow.audit_events.insert_effect` является invariant violation и прерывает UoW. Текущий silent return допустим только для empty capture; unit test doubles обязаны реализовать audit repo contract. Иначе runtime misconfiguration может зафиксировать balance mutation без journal proof.

### 5. `AuditItemEffect.effective_at` означает время действия конкретного эффекта

Добавляется `effective_at TIMESTAMPTZ NOT NULL DEFAULT now()`.

`created_at` остаётся временем физической INSERT-записи. `effective_at` — immutable business timestamp, в который **конкретная balance mutation** должна учитываться в истории.

| Producer/cause | Новый effect `effective_at` |
|---|---|
| forward effect при submit | `Operation.effective_at` |
| system ADJUSTMENT submit (merge/review/temporary) | effective_at generated operation |
| per-line acceptance | `OperationAcceptanceAction.performed_at` |
| lost resolution | `OperationAcceptanceAction.performed_at` |
| cancel reversal | `Operation.cancelled_at` |
| correction delta | timestamp применения correction / `operation.correction.applied.created_at` |
| unknown future producer | explicit cause timestamp; server default только safety net |

Это намеренно отличается от простого `UPDATE FROM operations`: отмена в июле не должна стирать майский эффект «с мая», а июльская приёмка не должна появляться в майском closing balance.

`_write_captured_effects` получает обязательный cause timestamp (или каждый captured row несёт его). Три текущих call sites — submit, cancel, correction — и новые acceptance/lost paths обязаны быть обновлены. Полагаться только на server default запрещено тестами.

### 6. Backfill является event-aware и детерминированным

Ожидаемая новая Alembic revision при текущем head: `0037_audit_item_effects_effective_at`; executor сначала повторно проверяет head.

Migration algorithm:

1. Add nullable `effective_at` **без server default**, чтобы existing rows не получили ложное migration-time значение.
2. Backfill **все pre-existing rows** через `audit_events` и, где применимо, `operations`:
   - `operation.submit` → `COALESCE(operations.effective_at, audit_events.created_at, effects.created_at)`;
   - `operation.cancel` → `COALESCE(operations.cancelled_at, audit_events.created_at, effects.created_at)`;
   - `operation.correction.applied` → `COALESCE(audit_events.created_at, effects.created_at)`;
   - остальные producers → `COALESCE(audit_events.created_at, effects.created_at)`.
3. Abort, если после backfill есть NULL.
4. Установить `server_default=now()` для safety compatibility новых inserts, затем Set NOT NULL.
5. Добавить индекс `ix_audit_item_effects_effective_at`; composite index допускается только после `EXPLAIN` реального query.

Backfill не использует время запуска migration как исторический факт и не меняет `created_at`.

Downgrade удаляет только новый index/column. До shared/prod-like upgrade обязателен backup и dry-run на disposable clone.

### 7. `item-movement` фильтрует системные операции без переписывания read model

Публичный параметр:

```text
GET /api/v1/reports/item-movement?exclude_system_effects=true|false
default: true
```

Решение default `true` выбирается как safety-first для сезонной отчётности. Клиент, которому нужна техническая история вместе с merge/review transfers, передаёт `false` явно.

Текущий report строится из operations/lines, поэтому фильтр применяется в каждой UNION-ветке до aggregation как:

```text
COALESCE(operations.origin, 'user') != 'system'
```

Имя query parameter описывает пользовательскую семантику, не физический join. Мы **не** join-им `audit_item_effects`: такой join создаст 1:N duplication, потребует полного пересмотра report projection и выйдет за Stage A.

Следствия:

- system ADJUSTMENT от merge/review/temporary flow исключается;
- manual ADJUSTMENT (`origin='user'` или legacy NULL) сохраняется;
- cancelled operations уже исключены `status='submitted'`, поэтому cancel reversal этим report не отображается и фильтровать его здесь нечего;
- pagination/count/aggregates выполняются после system filter.

В том же пакете A-6 исправляется подтверждённый prerequisite: `TemporaryItem.name` добавляется в GROUP BY, existing xfail снимается и обязан стать pass до добавления filter assertions. Это не отдельный report refactor, а минимальное восстановление исполнимости затрагиваемого endpoint.

Default change документируется как API behavior change и покрывается explicit true/false regression tests.

Django BFF (`Warehouse_web/apps/bff_api/reports_views.py`) добавляет `exclude_system_effects` в существующий query allow-list без UI-логики и без локальной интерпретации. Иначе browser/BFF consumer не сможет запросить explicit `false`, хотя архитектура запрещает browser direct-to-SyncServer calls. BFF только прозрачно форвардит параметр; default остаётся собственностью SyncServer.

### 8. Integrity checks получают стабильные символьные коды

Из-за конфликта ordinal Q1…Q7 в audit docs CLI не использует номера как contract. Вводятся коды:

| Code | Назначение | Default severity |
|---|---|---|
| `BALANCE_EFFECT_DRIFT` | FULL OUTER JOIN balances и summed effects по `(site_id, inventory_subject_id)`; `ROUND(sum,3) == balance.qty`; видит и balance-only, и effect-only keys | critical |
| `EXPECTED_EFFECT_GAP` | operation-type-aware проверка ожидаемых forward warehouse effects | critical |
| `ACCEPTANCE_EFFECT_GAP` | accepted progress/lost resolutions с warehouse mutation без per-action event/effect | critical |
| `EFFECT_DATE_NULL` | `audit_item_effects.effective_at IS NULL` после migration | critical |
| `EFFECT_CHAIN_BROKEN` | `quantity_before + quantity_delta != quantity_after` или разрыв running chain для ключа | critical/warning по legacy classification |
| `MERGE_CHAIN_CYCLE` | cycle/depth overflow в item merge chain | critical |
| `BACKDATED_SUBMITTED` | legacy submitted operations with `effective_at < created_at`; A-1 предотвращает новые, но не переписывает старые | warning requiring review |
| `LATE_ACCEPTANCE` | days between submit and acceptance action above configurable report threshold; diagnostic only | warning |
| `MERGE_AUDIT_GAP` | incomplete merge audit/resources; до Stage B часть findings ожидаема | warning |
| `AUDIT_ENTITY_ORPHAN` | audit entity/resource without resolvable domain entity where policy expects one | warning/critical by entity policy |

`EXPECTED_EFFECT_GAP` не считает ошибкой операции, которые не меняют warehouse balance: unresolved acceptance-required RECEIVE, `mark_lost`, lost `write_off`, WRITE_OFF against issue object. MOVE with acceptance всё равно требует source-side effect; accepted quantity требует separate destination acceptance effect.

CLI:

- `SyncServer/scripts/integrity_check.py` + root `make integrity-check`;
- выполняет `SET TRANSACTION READ ONLY` и только SELECT;
- поддерживает text и `--format json`, bounded `--sample-limit`;
- не печатает DSN, tokens, free-text notes и credentials;
- deterministic order by check code + stable keys;
- exit `0`: нет findings выше `--fail-on` (default `critical`); exit `1`: threshold findings; exit `2`: usage/config/DB execution error.

Legacy/pre-journal drift не подавляется silent allow-list. CLI оставляет finding critical; оператор классифицирует его в Evidence с owner/rationale/reconciliation plan. Stage A tooling может быть принято с обнаруженными legacy findings, но season-report/data acceptance остаётся заблокированным до reconciliation или письменного risk acceptance владельцем данных.

### 9. R-26 закрывается только частично

Stage A поставляет безопасный CLI и Make target. Cron/systemd/Kubernetes/CI schedule не вводится без отдельного operational owner, alert destination, concurrency policy и secret/runtime design.

Поэтому:

- R-11: diagnostic capability реализуема в Stage A;
- R-26: `partial` после Stage A, `closed` только после отдельного scheduled-run deployment и evidence первого успешного запуска.

### 10. Documentation truthfulness

После реализации обновляются:

- `docs/audit-event-catalog.md`: новые event types/resources/effect ownership; убрать ложное утверждение, что `operation.acceptance_complete` владеет acceptance effects;
- operator docs/SyncServer README для `make integrity-check`;
- root navigation/status docs;
- risk status отмечается `closed/partial/deferred` по факту evidence, не по наличию ТЗ.

До реализации active status обязан говорить «ADR/TZ выпущены, implementation not started».

## Data flow after Stage A

```text
draft effective_at PATCH
  -> workflow guard(status == draft)
  -> operation.update + audit event

accept line
  -> pending -qty
  -> balance +qty captured before/after
  -> OperationAcceptanceAction(performed_at)
  -> operation.line_accepted audit event
  -> AuditItemEffect(effect_type=acceptance,
                     effective_at=action.performed_at)

mark lost
  -> pending -qty -> lost register +qty
  -> OperationAcceptanceAction
  -> operation.line_mark_lost event (no warehouse effect)

resolve lost(found/return)
  -> lost register -qty -> balance +qty captured
  -> OperationAcceptanceAction
  -> operation.line_lost_resolved event
  -> AuditItemEffect(effect_type=acceptance,
                     effective_at=action.performed_at)

cancel submitted
  -> inverse balance mutation
  -> operation.cancel event
  -> cancel_reversal effects(effective_at=cancelled_at)
```

## Rollout and migration order

1. Baseline read-only integrity run on a backup/disposable clone.
2. Measure row count, backfill and index time on the clone. If one transactional revision exceeds the agreed deployment window, split expand/backfill/contract and update ADR/TZ before shared deployment.
3. Deploy code that understands/explicitly populates `effective_at` together with migration-compatible model.
4. Run expand/backfill/NOT NULL migration on safe DB; validate NULL=0 and one Alembic head.
5. Run focused + full test suite.
6. Stand smoke A-1…A-7.
7. Run integrity CLI; classify findings.
8. Production/season report gate remains NO-GO on unexplained critical findings.

Rollback:

- application rollback must remain compatible with extra DB column;
- schema downgrade only after old application image is active and backup exists;
- audit events/effects written during Stage A are never deleted as rollback cleanup;
- behavior rollback of report default uses explicit client `exclude_system_effects=false`, not data rewrite.

## Consequences

### Positive

- Submitted history cannot be silently re-dated through service/API.
- Cancel/restore and catalog deletion become reconstructable.
- Acceptance and lost-resolution warehouse mutations finally satisfy the balance-effect invariant for new writes.
- Effect history distinguishes business occurrence from physical insert time.
- System merge transfers stop polluting default turnover report without a risky projection rewrite.
- Operators get deterministic read-only diagnostics suitable for later scheduling.

### Negative / trade-offs

- Per-line actions add audit rows and effects; large acceptance batches produce O(number of actions) inserts.
- `exclude_system_effects=true` changes default report totals compared with legacy behavior.
- Existing historical drift is detected but not auto-repaired.
- Service-level effective_at guard does not block privileged direct SQL; DB trigger is deferred.
- R-06 late-accept cutoff and R-26 scheduling remain open by design.

## Alternatives considered

### A. Только реализовать буквальные A-1…A-7 из roadmap

Отклонено. Per-action event без acceptance/lost effects оставляет `balances == sum(effects)` заведомо ложным, а simple operation-effective_at backfill искажает reversals.

### B. Переписать `item-movement` целиком на `audit_item_effects`

Отклонено для Stage A. Потребуются historical/canonical naming policy, acceptance/cancel netting, item merge closure и новый response contract — это Stage B/C.

### C. Датировать все effects `operations.effective_at`

Отклонено. Cancel и late acceptance задним числом меняли бы закрытые периоды.

### D. Датировать все effects только `created_at`

Отклонено. Backdated draft операции — допустимый бизнес-сценарий до submit; forward movement должно сохранять утверждённую business date.

### E. Автоматически исправлять drift из integrity CLI

Отклонено. Причина расхождения может быть исторической, merge/cancel/acceptance-related или ручной; auto-repair создаст недоказуемую историю. Исправления только штатной compensating operation после человеческого review.

### F. Включить cron сразу

Отклонено. Без owner/alerts/concurrency/runtime secret policy расписание создаёт silent job, а не operational control.

## Risk disposition after successful implementation

| Risk | Disposition |
|---|---|
| R-01, R-36 | closed для service/API новых writes; DB-direct hardening deferred Stage B |
| R-03 | closed |
| R-04 | closed |
| R-05 | partial: effect timestamp storage/new writes/backfill delivered; текущий `item-movement` остаётся operation-based и не является полноценным effect-time report |
| R-06 | partial: observability/effect dating closed; N-day cutoff deferred |
| R-11 | diagnostic closed; discovered data drift may remain an operational blocker |
| R-12 | closed for lifecycle visibility; no new restore prohibition |
| R-21, R-38 | closed for `item-movement` system-operation filter; broader UI/report modes deferred |
| R-26 | partial: CLI exists, schedule deferred |

## Compliance

- `Functional and WorkLogik.md` §II.6.8: submitted operation is a business event and cannot be edited — draft-only date guard restores compliance.
- §II.6.10: root restore remains available and returns operation to draft.
- §II.4: acceptance behavior/math remains unchanged; only audit completeness is added.
- ADR-0003: all writes remain inside UnitOfWork.
- ADR-0004: balances remain derived; the effect journal proves their warehouse mutations.
- ADR-0018: audit remains append-only; resources/snapshots and causal parent links are reused.

## Acceptance of this decision

ADR is accepted as an architecture decision by explicit user authorization. Runtime completion is governed by `docs/TZ-HISTORICAL_INTEGRITY_STAGE_A.md`; no risk may be marked closed before implementation evidence and QA review.

## References

- `Functional and WorkLogik.md` §§II.4, II.6.7–6.10.
- `docs/TZ-HISTORICAL_INTEGRITY_STAGE_A.md`.
- `docs/reviews/architecture-review-historical-integrity-stage-a.md`.
- `docs/audit/HISTORICAL_INTEGRITY_AUDIT.md`.
- `docs/audit/HISTORICAL_RISK_REGISTER.md`.
- `docs/audit/HISTORICAL_INTEGRITY_ROADMAP.md`.
- `docs/audit/HISTORICAL_DATA_FLOW.md`.
- `docs/audit/SEASON_REPORT_READINESS.md`.
- `docs/adr/0003-layered-backend-with-unit-of-work.md`.
- `docs/adr/0004-operation-driven-inventory-and-derived-balances.md`.
- `docs/adr/0018-audit-architecture.md`.
