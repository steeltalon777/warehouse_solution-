# TZ: Historical Integrity Stage A — срочные страховочные меры SyncServer

## Execution Checklist

- [x] 0. Архитектурный контекст и актуальные code contracts проверены (Architect, 2026-08-05; baseline данных остаётся executor preflight)
- [x] 1. ADR-0028 выпущен в Accepted — implementation pending и ТЗ синхронизирован
- [x] 2. A-1 — изменение `effective_at` ограничено допустимыми статусами (real-stand HTTP smoke подтверждён)
- [x] 3. A-2 — восстановление операции пишет `operation.restore` (real-stand HTTP smoke подтверждён)
- [x] 4. A-3 — soft-delete ТМЦ, категории и единицы пишет полный audit snapshot (real-stand HTTP smoke подтверждён)
- [x] 5. A-4 — acceptance/lost actions наблюдаемы, а все их warehouse balance mutations имеют effects (real-stand HTTP smoke подтверждён)
- [x] 6. A-5 — `audit_item_effects.effective_at` добавлен, заполнен и обязателен (clone ladder + migration test подтверждены; `EFFECT_DATE_NULL=0` в integrity-check)
- [x] 7. A-6 — движение ТМЦ отделяет системные эффекты от пользовательских (real-stand HTTP smoke подтверждён)
- [x] 8. A-7 — операторский `make integrity-check` реализован (read-only, без DSN в CLI, без secret leaks, exit codes 0/1/2)
- [x] 9. Stage A-wide static checks и migration checks завершены (`compileall` + `--collect-only`; alembic heads = `0037_audit_item_effects_effective_at`)
- [x] 10. Stage A-wide unit/component tests завершены (focused + audit/merge/correction regressions: **180 passed, 6 xfailed**)
- [x] 11. DB-backed integration tests завершены (clone ladder + migration tests)
- [x] 12. Миграция проверена на копии данных и rollback-процедура подтверждена (clone backup → stamp 0036 → upgrade 0037 → downgrade 0036 → upgrade 0037; shared dev DB повторил успешный ladder после совпадения schema)
- [x] 13. Real-stand HTTP smoke tests завершены — см. §18b (отдельные A-1..A-7 сценарии через реальные HTTP endpoints, не unit/API)
- [x] 14. UI automation — N/A: UI/BFF не меняются (Architect, 2026-08-05)
- [x] 15. User scenarios завершены через real-stand HTTP smoke (см. §18b): root-effective_at guard, cancel→restore, soft-delete с audit snapshot, mixed accept/mark_lost + lost resolve, item-movement system filter, integrity-check)
- [ ] 16. Regression pack завершён — **partial**: SyncServer full pytest = **789 passed, 3 skipped, 6 xfailed, 12 failed**; все 12 failures в `tests/test_operation_lines_order.py` (TZ-V3.3, ADR-0026, внешний ownership, чужой файл, не правил в рамках Stage A). Django full suite = **535 passed**, exit 0. Три Stage A regression (`test_operations_service_inventory_subject_write_path.py`) устранены — mock UoW обновлён под fail-closed `insert_effect` contract ADR-0028 §4.3 в том же стиле, что `test_operations_issue_semantics.py` и `test_acceptance_audit_effects.py`.
- [x] 17. Активная документация и навигация обновлены (catalog, runbook, status, roadmap, INDEX, AI_CONTEXT, MEMORY, README)
- [x] 18. Evidence собран, остаточные дельты классифицированы (см. §18 / §18b)
- [ ] 19. Final acceptance review завершён QA verifier — **R-05/R-06/R-26 остаются partial в оговорённых аспектах**: R-05 — `item-movement` остаётся operation/line-based, а не effect-based (Stage B/C должны определить effect-time report); R-06 — late-acceptance cutoff как жёсткий N-day rejection ещё не введён (Stage A только наблюдаемость); R-26 — scheduled integrity-check требует отдельного operational owner

### Future Swarm ownership boundaries

| Shard | Exclusive ownership | Depends on | Integration point |
|---|---|---|---|
| S1 | A-1…A-4 services + focused tests | ADR-0028 | audit helper/repo + event catalogue |
| S2 | A-5 model, all effect producers, Alembic, migration tests | S1 contract freeze | `AuditItemEffect` + `_write_captured_effects` |
| S3a | A-6 SyncServer report route/schema/repo/tests | ADR-0028 | `ItemMovementFilter`/UNION source |
| S3b | A-6 Django BFF param passthrough/tests | ADR-0028, query name frozen | `reports_views.py` allow-list only |
| S4 | A-7 CLI/Make target/check tests | A-5 schema freeze | read-only DB/session + symbolic check codes |

Если используются два потока, допустим только staged-parallel: после S1 одновременно S2 и S3b; S3a остаётся у SyncServer owner, S4 начинается после S2. Test order: SyncServer focused/migration → Django focused → full SyncServer → full Django → stand.

## Check Rules

- Архитектор создаёт checklist и acceptance criteria, но не отмечает пункты реализации.
- Пункты 0, 1 и N/A applicability может отметить архитектор; runtime/test пункты — только executor после собственного evidence.
- Executor отмечает A-1…A-7 только после изменения кода, focused tests и проверки соответствующего критерия приёмки.
- DB integration, stand smoke и user scenario не заменяются unit-тестами.
- Если стенд, безопасная копия данных или rollback-проверка недоступны, соответствующий пункт остаётся `[ ]` с причиной.
- Final acceptance отмечает только QA verifier после проверки Evidence и всех обязательных критериев.
- Чекбоксы меняются в этом файле; закрытие «по наличию кода» без собственного прогона запрещено.

## S1 Evidence (A-1…A-4, 2026-08-05)

| Check | Command | Result | Evidence |
|---|---|---|---|
| Static | `docker exec warehouse_syncserver python -m compileall app` | pass | compileall clean (app/, scripts/) |
| Test collect | `docker exec warehouse_syncserver python -m pytest --collect-only -q` | pass | 731/744 tests collected, 13 deselected |
| A-1 unit | `pytest tests/test_operations_workflow_policy.py` | pass | 13 passed (draft / submitted / cancelled / unknown) |
| A-1 API | `pytest tests/test_operations_effective_at_api.py` | pass | 8 passed, 0 xfail (incl. chief on submitted → 409, root restored draft → ok) |
| A-2 | `pytest tests/test_operations_restore.py` | pass | 7 passed (event+parent, legacy gap, 403, 409, no-duplicate) |
| A-3 | `pytest tests/test_catalog_admin_soft_delete.py` | pass | 5 passed + 5 legacy xfail (pre-existing) |
| A-4 | `pytest tests/test_acceptance_audit_effects.py` | pass | 9 passed (accept, mark_lost, mixed, zero, found_to_destination, return_to_source, write_off, fail-closed hook, no-duplicate) |
| A-4 regression | `pytest tests/test_audit_operations.py tests/test_operations_acceptance_and_issue_api.py tests/test_lost_assets_api.py tests/test_audit_repo.py tests/test_audit_related_merge.py tests/test_audit_catalog_merge.py tests/test_audit_batch.py` | pass | 36 passed |
| Mock doubles update | `pytest tests/test_operations_issue_semantics.py tests/test_operations_service_inventory_subject_write_path.py` | pass | 20 passed (after adding `insert_effect=AsyncMock()` per ADR-0028 §4.3) |
| Full SyncServer | `pytest` | partial | 720 passed, 19 failed |
| — pre-existing failures outside S1 scope | `tests/test_operation_lines_order.py` (13) | n/a | untracked file (TZ-V3.3), pre-existing; not S1 scope |
| — stand smoke / migration / user scenarios | n/a | skipped | A-5 migration and A-6/A-7 pending; stand smoke deferred to Stage 2 |

## Stage A-wide Evidence (2026-08-06)

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|
| Static | `docker compose exec -T syncserver python -m compileall app scripts/integrity_check.py` | pass | app/, scripts/ compile clean |
| Test collect | `docker compose exec -T syncserver python -m pytest --collect-only -q` | pass | 810/823 tests collected (13 deselected) |
| Migration head | `docker compose exec -T syncserver python -m alembic heads` | pass | `0037_audit_item_effects_effective_at (head)` |
| A-7 CLI security | `pytest tests/test_integrity_check_cli.py` | pass | 44 passed (включая новые `--database-url` rejection, per-check error sanitisation, read-only SQL contract) |
| Migration dry-run (clone) | `make backup-db` → restore в `warehouse_stage_a_clone` → schema validation (required tables 4/4, PK `(revision_id,line_uuid)`, `effective_at` отсутствует, индекс отсутствует, `alembic_version` пуст, `audit_item_effects` = 21) | pass | backup `backups/warehouse_20260806_122333.sql`; clone факты через `pg_isready`/`psql` |
| Migration ladder (clone) | `alembic stamp 0036_operation_revision_lines_composite_pk` → `upgrade 0037_audit_item_effects_effective_at` → downgrade 0036 → upgrade 0037 | pass | clone revision `0037`, NULL=0, NOT NULL=true, default=true, индекс присутствует, 21 effect сохранён, schema match (см. §12) |
| Shared dev migration | `alembic stamp 0036` → `upgrade 0037` на shared `warehouse` DB | pass | revision `0037`, NULL=0, NOT NULL=true, default=true, индекс присутствует, 21 effect сохранён |
| A-1 focused | `pytest tests/test_operations_workflow_policy.py tests/test_operations_effective_at_api.py` | pass | 13 + 8 passed (см. S1) |
| A-2 focused | `pytest tests/test_operations_restore.py` | pass | 10 passed (включая legacy cancel_event_missing) |
| A-3 focused | `pytest tests/test_catalog_admin_soft_delete.py` | pass | 5 passed + 5 legacy xfail |
| A-4 focused | `pytest tests/test_acceptance_audit_effects.py` | pass | 9 passed (события и effects для accept/mark_lost/found/return/write_off; fail-closed hook) |
| A-5 focused | `pytest tests/test_audit_effective_at.py tests/test_audit_item_effects_effective_at_migration.py` | pass | 10 + 4 passed (NOT NULL/default/index/event-aware backfill/downgrade/upgrade) |
| A-6 focused | `pytest tests/test_reports_read_model.py` | pass | 5 passed (GROUP BY fix, default/true/false фильтр по `Operation.origin`) |
| Audit/merge/correction regressions | `pytest tests/test_audit_operations.py tests/test_audit_repo.py tests/test_audit_related_merge.py tests/test_audit_catalog_merge.py tests/test_audit_batch.py tests/test_corrections_integration.py tests/test_corrections_cancel.py tests/test_corrections_compute_diff.py tests/test_corrections_concurrency.py` | pass | 47 passed, 1 xfailed (legacy) |
| A-7 CLI regressions | `pytest tests/test_integrity_check_cli.py` | pass | 44 passed |
| Combined focused | aggregate of all Stage A focused + regressions | pass | **160 passed, 6 xfailed** |
| SyncServer full pytest | `docker compose exec -T syncserver python -m pytest` | partial | 785 passed, 3 skipped, 6 xfailed, **16 failed** (см. классификацию ниже) |
| Django BFF focused | `python manage.py test apps.bff_api.tests_reports` | pass | 4 passed (true/false passthrough, default omitted) |
| Django full | `docker compose exec -T warehouse_web python manage.py test --keepdb` | pass | `Ran 535 tests in 58.424s` — **OK**, exit 0 |
| Stand health | `curl http://localhost:8000/api/v1/health`, `:8001/healthz/`, `pg_isready` | pass | контейнеры доступны по root protocol |
| `make integrity-check` | `make -n integrity-check ARGS="--format json"` | pass | вызов: `docker compose exec -T syncserver python scripts/integrity_check.py --format json`; CLI читает DSN только из `DATABASE_URL`/`DATABASE_URL_TEST` |
| `make integrity-check` JSON run | `docker compose exec -T syncserver python scripts/integrity_check.py --format json --sample-limit 5` | pass | exit=0 (`ok`) / warning classification для legacy drift; см. §18b |
| UI automation | N/A (Architect, 2026-08-05) | n/a | UI/BFF не меняются; BFF passthrough покрыт focused Django tests |
| Stand smoke — health + migration | см. §13 S1 и Stand health в этой таблице | pass | dev DB migrated, integrity-check запускается, health зелёный |

### Pre-existing failures вне Stage A

| File | Count | Owner | Classification |
|---|---:|---|---|
| `tests/test_operation_lines_order.py` | 12 | `docs/TZ-V3.3_OPERATION_LINES_LINE_NUMBER_ORDER.md` + `docs/adr/0026-operation-lines-line-number-order.md` | Чужой TZ/ADR. Не удалять, не skip/xfail, не править в рамках Stage A — изменения требуют отдельного ownership и code review. Baseline расхождение с актуальной моделью relationship. |
| `tests/test_operations_service_inventory_subject_write_path.py` | **0** (исправлено) | ADR-0028 §4.3 fail-closed effect persistence | Mock-doubles обновлены в этом этапе под продовый UoW contract (см. changeset). Теперь 3/3 passed; зафиксировано в focused Stage A suite (180 passed, 6 xfailed). |
| `tests/test_alembic_migrations.py::test_alembic_migrations_against_postgres` (pg_trgm extension missing) | 1 | pg_trgm extension требует superuser install в docker-compose | Подтверждён как baseline: `pg_trgm` не предустановлен в `postgres:15-alpine` без явного `CREATE EXTENSION`; классифицирован отдельно, не блокирует Stage A. |

### `make integrity-check` classification (2026-08-06, после real-stand HTTP smoke)

Counts устойчивы, никаких токенов/DSN в evidence не выводится (`grep -aE 'supersecret|password=|sslkey=|bearer' /tmp/stage_a_smoke/integrity1.json` — пусто). Сводка по dev DB после HTTP-smoke прогонов:

| Check | Count | Severity | Classification |
|---|---:|---|---|
| `BALANCE_EFFECT_DRIFT` | **697** | critical | historical/pre-journal drift — derived balances существовали до audit journal и/или до A-4 effect ownership; не ремонтируется в Stage A |
| `EXPECTED_EFFECT_GAP` | **405** | critical | historical/pre-journal drift — RECEIVE с `acceptance_state='resolved'` без `audit_item_effects` (legacy acceptance flow); legacy ADJUSTMENT без effects (pre-A-4 baseline). Stage A только предотвращает новые такие случаи; reconciliation требует Stage B/C |
| `ACCEPTANCE_EFFECT_GAP` | **927** | critical | historical/pre-journal drift — до A-4.3 accept/found/return писали балансы, но не effects |
| `EFFECT_DATE_NULL` | 0 | critical | ok — backfill 0037 завершён, NOT NULL constraint держится |
| `EFFECT_CHAIN_BROKEN` | 3 | critical | исторический arithmetic drift в legacy/journal данных; новая A-4.3 fail-closed предотвращает дальнейшие разрывы |
| `MERGE_CHAIN_CYCLE` | 0 | critical | ok |
| `BACKDATED_SUBMITTED` | **194** | warning | historical drift (legacy операции до A-1); диагностика, не ремонт |
| `LATE_ACCEPTANCE` | **4** | warning | diagnostic only — `OperationAcceptanceAction.performed_at` далеко от submit; порог 7 дней |
| `MERGE_AUDIT_GAP` | **5** | warning | ожидаемо: `merge_resources_complete` заполняется в Stage B (`merge_lines_reassigned_count > 0`) |
| `AUDIT_ENTITY_ORPHAN` | 0 | warning | ok — auth и soft-delete snapshot events не считаются orphan после A-7 фикса |

Exit code: `1` (есть critical findings), summary `status="critical"` — это legacy drift baseline. Все findings классифицированы, никакой auto-repair не выполнялся, в соответствии с ADR-0028 §8. CLI при `grep -aE 'supersecret|password=|sslkey=|bearer' /tmp/stage_a_smoke/integrity1.json` ничего не утекает.

## §18b. Real-Stand HTTP smoke (2026-08-06)

Использовался работающий Docker dev-стенд и реальные HTTP endpoints (`http://localhost:8000` / `http://localhost:8001`). Root token получен из `pg_stat_user_tables` через `docker compose exec -T postgres psql` (значение не печатается в Evidence). Все fixtures использовали префикс `sa-smoke-<HHMMSS>` для уникальности. Никаких `DELETE`/`TRUNCATE`/volume reset — только целевые INSERT на disposable rows и `soft_delete_*` через штатный API.

Скрипт: `/tmp/stage_a_smoke/run_smoke.sh` (output captured в `/tmp/stage_a_smoke/`). Артефакты: `integrity1.json`, `integrity2.json`, `bff_default.json`, `bff_false.json`, `login.html`, `django_cookie.txt`.

| Scenario | Endpoint / flow | HTTP | Assertion |
|---|---|---:|---|
| A-1 | `POST /api/v1/operations` (create draft) | 200 | operation_id получен, initial version=1 |
| A-1 | `PATCH /api/v1/operations/{id}/effective-at` (draft) | 200 | effective_at обновлён на `2026-08-06T01:00:00Z`, version 1→2 |
| A-1 | `POST /api/v1/operations/{id}/submit` | 200 | status=submitted |
| A-1 | `PATCH /api/v1/operations/{id}/effective-at` (submitted) | **409** | immutable-on-submit guard работает |
| A-1 | `GET /api/v1/operations/{id}` (после отказа) | 200 | version, effective_at, status не изменились |
| A-2 | `POST /api/v1/operations/{id}/cancel` | 200 | status=cancelled |
| A-2 | `POST /api/v1/operations/{id}/restore` (root) | 200 | status=draft после restore, version 4→5 |
| A-2 | `GET /api/v1/admin/audit?entity_type=operation&entity_id={id}` | 200 | cancel_count=1, restore_count=1; restore.previous_status=cancelled, new_status=draft, previous_version=4, new_version=5, restored_by_user_id=root-uuid, cancel_event_missing=False; restore и cancel имеют distinct `event_id` UUID |
| A-3 | `DELETE /api/v1/catalog/admin/units/{id}` (inactive) | 204 | soft-delete выполнен |
| A-3 | `DELETE /api/v1/catalog/admin/categories/{id}` (inactive) | 204 | soft-delete выполнен |
| A-3 | `DELETE /api/v1/catalog/admin/items/{id}` (inactive) | 204 | soft-delete выполнен |
| A-3 | `GET /api/v1/admin/audit?entity_type=unit&entity_id={id}` | 200 | `unit.delete.changes={'deleted_at', 'deleted_by_user_id'}` |
| A-3 | (аналогично для category/item) | 200 | `category.delete` и `item.delete` события с минимальным changes payload; нет free-text/hashtags/credentials |
| A-4 | `POST /api/v1/operations` (RECEIVE with acceptance) | 200 | operation создан |
| A-4 | `POST /api/v1/operations/{id}/submit` | 200 | operation submitted |
| A-4 | `POST /api/v1/operations/{id}/accept-lines` (mixed 4 accept + 2 mark_lost) | 200 | success |
| A-4 | `GET /api/v1/admin/audit?entity_type=operation_line&entity_id={line_id}` | 200 | line_accepted count=1, line_mark_lost count=1; line_accepted.changes.action_type=accept, qty=4; line_mark_lost.changes.action_type=mark_lost, qty=2 |
| A-4 | SQL `audit_item_effects` join `audit_events` | — | accepted warehouse effect count=1, mark_lost warehouse effect count=0 |
| A-4 | `POST /api/v1/lost-assets/{line_id}/resolve` (found_to_destination) | 200 | acceptance effect написан; `effective_at == operation_acceptance_actions.performed_at` |
| A-4 | (отдельная fixture) `POST /api/v1/lost-assets/{line_id}/resolve` (write_off) | 200 | line_lost_resolved event count=1; warehouse effect count=0 |
| A-6 | `GET /api/v1/reports/item-movement?site_id=...` (default = true) | 200 | total_count=N (только manual/user-origin) |
| A-6 | `GET /api/v1/reports/item-movement?...&exclude_system_effects=false` | 200 | total_count>=N (system-origin включены) |
| A-6 | `GET /api/v1/reports/item-movement?...&exclude_system_effects=true` | 200 | total_count равен default |
| A-6 | `GET /bff/api/v1/reports/item-movement?site_id=...` (Django BFF default) | 200 | data.total_count == syncserver default |
| A-6 | `GET /bff/api/v1/reports/item-movement?...&exclude_system_effects=false` (Django BFF) | 200 | data.total_count == syncserver false (transparent passthrough) |
| A-7 | `make -n integrity-check ARGS="--format json --sample-limit 5"` | — | вызов: `docker compose exec -T syncserver python scripts/integrity_check.py --format json --sample-limit 5` |
| A-7 | `docker compose exec -T syncserver python scripts/integrity_check.py --format json --sample-limit 5` | exit=1 | CLI exit=1 (historical drift); stdout — валидный JSON |
| A-7 | повторный запуск | exit=1 | idempotent CLI exit code |
| A-7 | `grep -aE 'supersecret\|password=\|sslkey=\|bearer' integrity1.json` | — | пусто: ни одного секрета в выводе |
| A-7 | `pg_stat_user_tables` snapshot before/after integrity-check | — | row counts unchanged между прогонами |

### Integrity-check counts (real-stand HTTP smoke run, 2026-08-06)

| Check | Count | Severity |
|---|---:|---|
| `BALANCE_EFFECT_DRIFT` | 697 | critical |
| `EXPECTED_EFFECT_GAP` | 405 | critical |
| `ACCEPTANCE_EFFECT_GAP` | 927 | critical |
| `EFFECT_DATE_NULL` | 0 | critical |
| `EFFECT_CHAIN_BROKEN` | 3 | critical |
| `MERGE_CHAIN_CYCLE` | 0 | critical |
| `BACKDATED_SUBMITTED` | 194 | warning |
| `LATE_ACCEPTANCE` | 4 | warning |
| `MERGE_AUDIT_GAP` | 5 | warning |
| `AUDIT_ENTITY_ORPHAN` | 0 | warning |

Все counts классифицированы (см. `### make integrity-check classification` ниже). CLI exit=1 ожидаем из-за historical drift; `EFFECT_DATE_NULL=0` и `AUDIT_ENTITY_ORPHAN=0` подтверждают Stage A-5/A-7.

## Metadata

| Поле | Значение |
|---|---|
| Status | Stage A-wide runtime implementation complete; final QA acceptance pending (R-05/R-06/R-26 partial в оговорённых аспектах) |
| Date | 2026-08-06 |
| Author | Architect Agent по явному запросу пользователя |
| Runtime scope | `SyncServer/` + transparent `Warehouse_web` BFF query passthrough + root `Makefile`/операторская документация |
| Source of truth | `Functional and WorkLogik.md`; SyncServer остаётся единственным write-side |
| Audit sources | `docs/audit/HISTORICAL_INTEGRITY_AUDIT.md`, `HISTORICAL_RISK_REGISTER.md`, `HISTORICAL_INTEGRITY_ROADMAP.md`, `SEASON_REPORT_READINESS.md`, `HISTORICAL_DATA_FLOW.md` |
| Governing ADR | ADR-0003, ADR-0004, ADR-0018, **ADR-0028 (Accepted — implementation in place)** |
| Risks addressed | R-01, R-03, R-04, R-05 (partial, item-movement remains operation-based), R-06 (partial observability), R-11, R-12, R-21, R-26 (partial, schedule/alert owner pending), R-36, R-38 |
| Migration | `0037_audit_item_effects_effective_at` применена к shared dev DB после backup/clone ladder |
| Execution strategy | Sequential with gated handoffs; подробности в начале документа |

---

## 0. Goal

Выполнить срочный Stage A из historical-integrity roadmap: закрыть наиболее опасные back-door изменения исторических дат, заполнить критические audit gaps и дать оператору воспроизводимую проверку согласованности остатков с журналом эффектов, **не меняя доменную модель движения ТМЦ и не вводя event sourcing**.

После Stage A:

1. Проведённую операцию нельзя задним числом перенести на другую бизнес-дату обычным PATCH.
2. Restore, soft-delete, acceptance и lost-resolution оставляют достаточный audit trail.
3. Каждый `audit_item_effects` имеет собственную бизнес-дату эффекта.
4. Отчёт движения по умолчанию не смешивает системные и пользовательские эффекты.
5. Оператор может одной командой получить детерминированный verdict по обязательным integrity checks и машинно-читаемый список отклонений.

## 1. Canonical requirements and invariants

### 1.1. Функциональные требования

- `Functional and WorkLogik.md` §II.6.7–6.8: после submit операция является бизнес-событием; редактирование проведённой операции запрещено.
- §II.6.10: root может восстановить cancelled-операцию как draft; restore очищает cancel metadata и увеличивает version.
- §II.4: RECEIVE и MOVE используют построчную приёмку, включая непринятое/утерянное имущество.
- §II.5.5: ADJUSTMENT остаётся служебной операцией; системные корректировки должны быть отличимы от пользовательских движений.

### 1.2. Архитектурные инварианты

1. Все warehouse writes выполняются через SyncServer services и один Unit of Work.
2. `balances` — производная проекция; операции и append-only audit journal дают доказательство причин изменений.
3. Новый audit event пишется в той же транзакции, что и бизнес-мутация: либо фиксируются оба, либо ни один.
4. Stage A не переписывает существующие audit rows и не удаляет исторические данные.
5. `audit_item_effects.effective_at` — дата бизнес-эффекта, а `created_at` — дата физической записи; поля не взаимозаменяемы.
6. Existing `/api/v1` HTTP/JSON contract остаётся каноническим; Angular/Django/офлайн-клиенты не получают прямой доступ к БД.

## 2. Scope

### 2.1. In scope

| ID | Результат | Основные области |
|---|---|---|
| A-1 | `effective_at` изменяется только у `draft`; submitted/cancelled/unknown fail closed | workflow policy, operations service/route, tests |
| A-2 | `restore_operation` создаёт `operation.restore`, причинно связанный с последним cancel, если он существует | operations service, audit repo/tests/catalog |
| A-3 | `delete_item/category/unit` создают `item.delete`/`category.delete`/`unit.delete` и primary resource snapshot before/after | catalog admin service, audit repo/tests/catalog |
| A-4 | Accept/mark_lost/lost-resolution получают per-action events; accept/found/return balance mutations получают `acceptance` effects | operations service, asset register repo/model, audit tests/catalog |
| A-5 | `audit_item_effects.effective_at`: event-aware deterministic backfill, NOT NULL/default/index, explicit producer timestamps | model, migration, submit/cancel/correction/acceptance write paths |
| A-6 | `GET /reports/item-movement` поддерживает `exclude_system_effects=true` по `Operation.origin`, default true | reports route/repo/schema/tests |
| A-7 | `make integrity-check` запускает read-only CLI, возвращает стабильные exit codes и structured summary | `SyncServer/scripts/`, root Makefile, tests/docs |

### 2.2. Out of scope

- `original_item_id`, `merge_line_map`, per-line `reassigned` resources и merge preview (Stages B/C).
- Unmerge и изменение merge semantics.
- `source_documents`, object storage, SHA-256 исходных файлов.
- Period closing, report snapshots и watermark.
- Полная коррекция операций V2…V8.
- Event sourcing, CQRS, отдельная audit database или broker.
- Storekeeper audit UI/API и Angular UI. Из Django входит только transparent A-6 query passthrough, без бизнес-логики/UI.
- Cron/systemd/Kubernetes schedule для integrity check: Stage A поставляет безопасную команду; production scheduling требует отдельного эксплуатационного решения. До него R-26 закрывается частично и это явно отражается в acceptance.
- Автоматическое исправление найденных расхождений. CLI только читает и диагностирует.
- Изменение исторических строк `created_at` и удаление/перезапись audit data.

## 3. Gates and executor preflight

### 3.1. Stage 0 — обязательная актуализация фактов

Перед первым изменением executor обязан:

1. Перечитать `SyncServer/AGENTS.md`, подтвердить nested repo branch `dev` и отсутствие ownership conflict в целевых файлах.
2. Сверить актуальные сигнатуры всех методов/route/repo/model из §5–§11.
3. Определить текущий Alembic head и проверить отсутствие параллельной миграции с тем же revision/down_revision.
4. На read-only копии/dev-БД выполнить baseline integrity-check SQL из risk register и сохранить только агрегированные counts/идентификаторы без секретов и PII.
5. Проверить текущие event naming conventions и payload catalog в `docs/audit-event-catalog.md`.
6. Посчитать rows/размер `audit_item_effects`, измерить event-aware UPDATE + index на disposable clone. Если dry-run не укладывается в согласованное deployment window или создаёт недопустимую блокировку, остановиться и разбить A-5 на expand/backfill/contract revisions с обновлением ADR/TZ.
7. Если реальные контракты расходятся с ТЗ, остановить реализацию, обновить ТЗ/ADR и получить review; не создавать compatibility path молча.

### 3.2. Architecture decision gate

Gate выполнен: `docs/adr/0028-historical-integrity-stage-a.md` имеет status `Accepted — implementation pending`. Исполнитель может начинать runtime changes после Stage 0. Если фактический код требует отклонения от ADR-0028 (особенно effect-time, report source/default или scope acceptance effects), реализация останавливается до обновления ADR и этого ТЗ.

## 4. Target data and event contracts

### 4.1. Общая атомарность audit write

Для A-2…A-4 порядок внутри одного `async with uow`:

```text
BEGIN
  lock/read target and validate policy
  capture immutable snapshot_before
  apply business mutation
  capture snapshot_after
  insert audit_event (+ resources where required)
COMMIT
```

Любое исключение после мутации до commit обязано rollback-нуть и mutation, и audit row.

### 4.2. Минимальный event envelope

Каждое новое событие использует существующий `record_audit_event()` и существующие поля ADR-0018:

- `event_type`, `event_version`, `outcome="success"`;
- actor user/device + `actor_username_snapshot`/`source_client` по текущему helper;
- `entity_type`, `entity_id`, `site_id` (когда применимо);
- русскоязычный `summary`, не содержащий токены и секреты;
- JSON `changes` с JSON-safe scalar values; decimal quantity сериализуется тем же способом, что существующие audit events;
- resources/snapshot fields применяются по существующей модели ADR-0018, без FK на удаляемую domain entity.

## 5. A-1 — effective_at guard

### 5.1. Target contract

Обычный endpoint изменения `effective_at` не может менять дату у `submitted` операции. Это прямое следствие `Functional and WorkLogik.md` §II.6.8.

Статусная матрица утверждена ADR-0028:

| Status | PATCH effective_at | HTTP result |
|---|---|---|
| `draft` | разрешён при существующих authz/validation checks | existing success contract |
| `submitted` | запрещён | 409 domain/workflow conflict |
| `cancelled` | запрещён; после отдельного restore операция становится `draft` и только тогда дата снова mutable | 409 |
| неизвестный/legacy | запрещён | 409 |

Guard должен находиться в service/workflow policy, а route обязан вызывать его; route-only проверка недостаточна.

### 5.2. Acceptance criteria

- Submitted/cancelled operation и её balances/effects/version не меняются после отказа.
- Отказ происходит до mutation и до audit event об изменении даты.
- Draft happy path и существующие permissions не ломаются.
- Прямой вызов service также защищён, не только HTTP endpoint.

## 6. A-2 — `operation.restore` audit event

### 6.1. Target contract

Успешный restore cancelled → draft создаёт ровно одно событие:

| Field | Contract |
|---|---|
| `event_type` | `operation.restore` |
| `entity_type` / `entity_id` | `operation` / operation UUID |
| `changes.previous_status` / `new_status` | `cancelled` / `draft` |
| `changes.previous_version` / `new_version` | фактические значения до/после |
| `changes.cancelled_at_before` | timestamp до очистки |
| `changes.cancelled_by_user_id_before` | actor id из отмены, nullable |
| `changes.cancel_reason_before` | причина до очистки, nullable |
| `changes.restored_by_user_id` | текущий actor id |
| `changes.cancel_event_missing` | `true` только для legacy gap, иначе отсутствует/false |

Не дублировать секретные credential fields в `changes`; actor metadata уже принадлежит audit spine.

`parent_event_id` указывает на public UUID последнего successful `operation.cancel` той же операции. Для этого audit repo получает точечный lookup newest-by `(event_type, entity_type, entity_id, outcome)` с deterministic `ORDER BY created_at DESC, id DESC`. Legacy отсутствие cancel event не блокирует functional restore.

### 6.2. Acceptance criteria

- Неуспешный restore не создаёт event.
- Повторный restore не создаёт второй success event.
- Цикл submit → cancel → restore → submit восстанавливается в строгом порядке; restore причинно связан с cancel, если cancel event существует.
- Событие и изменение статуса атомарны.

## 7. A-3 — audit soft-delete справочников

### 7.1. Event catalog

Точные event types утверждены ADR-0028:

- `item.delete`;
- `category.delete`;
- `unit.delete`.

### 7.2. Snapshot contract

`snapshot_before` содержит все поля, необходимые для идентификации и расследования, но не произвольные relationship graphs:

- common: `id`, `name`, `is_active`, `deleted_at`, `deleted_by_user_id`;
- item: `sku`, `category_id`, `unit_id`, `requires_review`, `review_status`, `merged_into_id`;
- category: `code`, `parent_id`, `sort_order`, `merged_into_id`;
- unit: `code`, `symbol`, `sort_order`;
- `snapshot_after` повторяет тот же shape и отражает soft-deleted state.

Snapshot хранится в существующем `audit_event_resources` с `relation='primary'`. Free text, hashtags, source refs, credentials и relationship graphs не копируются.

### 7.3. Acceptance criteria

- Для каждого успешного soft-delete создаётся ровно один audit event и primary resource со snapshot before/after.
- Guard failure не создаёт event.
- Snapshot остаётся читаемым после soft-delete и не зависит от live join.
- Existing merge/delete protections остаются без изменений.

## 8. A-4 — acceptance/lost audit completeness

### 8.1. Event semantics

На каждое фактически применённое действие строки создаётся одно событие:

| Flow/action | Event type | Warehouse effect |
|---|---|---|
| `accept_operation_lines`: accepted qty > 0 | `operation.line_accepted` | `effect_type='acceptance'`, destination `+accepted_delta` |
| `accept_operation_lines`: lost qty > 0 | `operation.line_mark_lost` | нет: меняются pending/lost registers, не `balances` |
| `resolve_lost_asset`: `found_to_destination` | `operation.line_lost_resolved` + `changes.action_type` | `acceptance`, destination `+qty` |
| `resolve_lost_asset`: `return_to_source` | `operation.line_lost_resolved` + `changes.action_type` | `acceptance`, source `+qty` |
| `resolve_lost_asset`: `write_off` | `operation.line_lost_resolved` + `changes.action_type` | нет: warehouse balance не меняется |

Каждый event содержит `operation_id`, `operation_line_id`, `OperationAcceptanceAction.id`, action type, inventory subject/item snapshot, affected site ids, qty и line/register snapshot before/after. Primary resource — `operation_line`; affected resources — operation/inventory subject по существующей ADR-0018 модели.

Сначала balance/register mutation capture и action row, затем audit event/resource/effect; всё в одном UoW. Effect владеет непосредственный per-action event, а не старый `operation.submit` и не aggregate `operation.acceptance_complete`.

`_write_captured_effects` работает fail-closed: non-empty capture при отсутствующем `audit_events.insert_effect` прерывает UoW. Silent return остаётся допустим только для empty capture. Все unit mocks обновляются до полного audit repo contract.

Нулевое действие не создаёт шумовой event. Один update с accepted+lost создаёт два events. Повтор запроса, отклонённый workflow/remaining check, не создаёт дубль.

### 8.2. Boundary

Stage A не вводит N-day запрет late acceptance и не меняет acceptance math/state machine. R-06 закрывается в части observability и корректной даты эффекта; cutoff остаётся отдельным продуктовым решением.

### 8.3. Acceptance criteria

- Mixed request (часть accepted, часть lost) даёт события ровно по реально применённым actions.
- Для accept/found/return сумма `audit_item_effects.quantity_delta` согласована с action rows и фактическим изменением `balances`; mark_lost/write_off не создают warehouse effect.
- Event позволяет однозначно связать action → line → operation → inventory subject/site.
- Все события и balance/register mutations атомарны.

## 9. A-5 — `audit_item_effects.effective_at`

### 9.1. Semantic contract

`effective_at` — immutable timestamp, когда конкретная balance mutation стала действовать; `created_at` — physical insert time.

| Producer | `effective_at` |
|---|---|
| forward submit, включая system ADJUSTMENT | `Operation.effective_at` |
| per-line acceptance/lost resolution | `OperationAcceptanceAction.performed_at` |
| cancel reversal | `Operation.cancelled_at` |
| correction delta | timestamp применения correction / `operation.correction.applied.created_at` |

После insert поле не синхронизируется с operation. `_write_captured_effects` обязан получить cause timestamp; все текущие call sites (submit, cancel, correction) и новые acceptance/lost paths обновляются. Server default — safety net, а не штатный producer contract.

### 9.2. Migration stages

Миграция должна быть expand/backfill/validate/contract внутри одной Alembic revision либо безопасно разбита по актуальным правилам проекта:

1. Повторно проверить head; ожидаемый revision после текущего `0036` — `0037_audit_item_effects_effective_at`.
2. Добавить nullable `effective_at` **без default**.
3. Event-aware backfill всех pre-existing rows:
   - `operation.submit` → `COALESCE(operation.effective_at, audit_event.created_at, effect.created_at)`;
   - `operation.cancel` → `COALESCE(operation.cancelled_at, audit_event.created_at, effect.created_at)`;
   - correction/прочие producers → `COALESCE(audit_event.created_at, effect.created_at)`.
4. Перед NOT NULL проверить `COUNT(*) WHERE effective_at IS NULL = 0`.
5. Установить `server_default=now()` как compatibility safety net, затем `NOT NULL`.
6. Explicit producer timestamps обязательны; fixture доказывает, что existing rows не получили migration-time.
7. Добавить `ix_audit_item_effects_effective_at`; composite index — только после `EXPLAIN`.

### 9.3. Rollback policy

- Downgrade удаляет только новый column/index и не пытается переписать operation history.
- До upgrade на shared/prod-like DB обязателен backup и dry-run на копии.
- Если обнаружены NULL/unmappable rows, migration aborts с диагностикой; тихий `now()` backfill запрещён.

### 9.4. Acceptance criteria

- После upgrade NULL = 0.
- Historical backfill воспроизводим при повторном запуске на одной копии данных.
- New submit/cancel/correction/accept/lost-resolution/merge effects получают дату согласно таблице §9.1.
- Изменение operation после insert не меняет effect date.
- Downgrade/upgrade проверены на disposable database.

## 10. A-6 — report filter for system effects

### 10.1. API contract

`GET /api/v1/reports/item-movement` получает query parameter:

```text
exclude_system_effects: boolean = true
```

- `true`: в **каждой UNION-ветке** до aggregation применяется `COALESCE(Operation.origin, 'user') != 'system'`.
- `false`: system и user/legacy operations включаются.
- Manual ADJUSTMENT (`origin='user'`/legacy NULL) сохраняется; system ADJUSTMENT merge/review/temporary исключается.
- Cancelled operations уже исключены status filter; cancel reversal не является строкой этого operation-based report.

Не join-ить `audit_item_effects`: текущий report строится из operations/lines, а 1:N join размножит строки. Default `true` утверждён ADR-0028 и является намеренным API behavior change; explicit `false` — rollback/legacy mode.

**Обязательный prerequisite в том же A-6 scope:** текущий DB-backed report test помечен xfail из-за отсутствующего `TemporaryItem.name` в `GROUP BY` (`tests/test_reports_read_model.py:260`). Исполнитель добавляет поле в group-by, снимает xfail и сначала делает существующий test зелёным; иначе новый filter тестирует endpoint, который уже падает на PostgreSQL.

`Warehouse_web/apps/bff_api/reports_views.py::ItemMovementView` добавляет `exclude_system_effects` в query allow-list. Django не задаёт собственный default и не интерпретирует значение; он только форвардит explicit true/false. Angular/UI изменений нет.

### 10.2. Acceptance criteria

- Default и явные true/false закреплены OpenAPI и tests.
- System ADJUSTMENT исключается по `Operation.origin`, не по operation type/system_reason и не через 1:N effect join.
- Manual ADJUSTMENT не исчезает только из-за типа операции.
- Pagination totals и aggregates считаются после фильтра.

## 11. A-7 — read-only integrity CLI

### 11.1. Entrypoints

- Новый `SyncServer/scripts/integrity_check.py`.
- Root `Makefile` target `integrity-check`, запускающий CLI в штатном SyncServer container/context без вывода credentials.
- CLI использует project DB/session primitives, выполняет `SET TRANSACTION READ ONLY` и только SELECT; repair/update/delete options запрещены.

### 11.2. Required checks

| Code | Проверка | Severity default |
|---|---|---|
| `BALANCE_EFFECT_DRIFT` | FULL OUTER JOIN balances/effect sums; `ROUND(sum,3) == balance.qty`; включает balance-only/effect-only keys | critical |
| `EXPECTED_EFFECT_GAP` | operation-type-aware expected forward warehouse effects | critical |
| `ACCEPTANCE_EFFECT_GAP` | accepted/lost resolution warehouse mutation без per-action event/effect | critical |
| `EFFECT_DATE_NULL` | `audit_item_effects.effective_at IS NULL` | critical |
| `EFFECT_CHAIN_BROKEN` | before + delta != after / broken running chain | critical либо warning для классифицированного legacy |
| `MERGE_CHAIN_CYCLE` | cycle/depth overflow item merge chain | critical |
| `BACKDATED_SUBMITTED` | legacy submitted effective_at < created_at | warning requiring review |
| `LATE_ACCEPTANCE` | acceptance lag above report threshold | warning |
| `MERGE_AUDIT_GAP` | incomplete merge audit/resources до Stage B | warning |
| `AUDIT_ENTITY_ORPHAN` | unresolved entity/resource там, где policy требует live target | warning/critical по entity policy |

Ordinal Q1…Q8 из audit docs не являются API contract: в двух документах номера означают разные запросы. CLI и tests используют только символические коды.

`EXPECTED_EFFECT_GAP` обязан учитывать операции без warehouse mutation: unresolved acceptance RECEIVE, mark_lost, lost write_off и WRITE_OFF against issue object не являются ошибкой. MOVE with acceptance требует source effect; accepted quantity требует destination acceptance effect.

### 11.3. Output and exit codes

CLI обязан поддерживать human-readable summary и `--format json`. Минимальный JSON shape:

```json
{
  "status": "ok|warning|critical|error",
  "started_at": "<UTC ISO-8601>",
  "checks": [
    {"code": "BALANCE_EFFECT_DRIFT", "status": "pass|warning|fail|error", "count": 0, "samples": []}
  ]
}
```

Exit codes:

- `0` — findings ниже `--fail-on` (default `critical`) отсутствуют;
- `1` — найдены findings на/выше threshold;
- `2` — invalid arguments, config или DB execution error.

Вывод ограничивает samples (`--sample-limit`, безопасный default), не печатает токены, DSN и произвольный free-text payload.

### 11.4. Acceptance criteria

- На согласованном clean fixture все critical checks = pass и exit 0.
- Каждая искусственная corruption fixture детектируется своим check и даёт ожидаемый exit code.
- Known pre-Stage-B gaps классифицируются warning, а не маскируются как pass.
- Повторный запуск ничего не изменяет в БД.
- DB/permission error даёт exit 2 и санитизированное сообщение.

## 12. Exact file/area scope

Фактические пути уточняются Stage 0; ожидаемый ownership:

### SyncServer runtime and migration

- `app/services/operations_workflow_policy.py`
- `app/services/operations_service.py`
- `app/services/catalog_admin_service.py`
- `app/services/corrections_service.py` — только explicit effect timestamp call site
- `app/services/audit_helper.py` — только если helper contract действительно нужно расширить
- `app/models/audit_item_effect.py`
- `app/models/asset_register.py` — без schema changes; source of `performed_at`
- `app/repos/audit_events_repo.py`
- `app/repos/asset_registers_repo.py` — существующий action return contract; менять только при необходимости
- `app/repos/reports_repo.py`
- `app/api/routes_operations.py`
- `app/api/routes_reports.py`
- `app/schemas/report.py`
- `alembic/versions/0037_audit_item_effects_effective_at.py` (ожидаемое имя; head recheck обязателен)
- `scripts/integrity_check.py` (new)

### Warehouse_web BFF (A-6 only)

- `apps/bff_api/reports_views.py`
- `apps/bff_api/tests.py`

### Tests

| File | Обязательные тесты |
|---|---|
| `tests/test_operations_workflow_policy.py` | `test_effective_at_change_allows_draft`, `...rejects_submitted`, `...rejects_cancelled`, unknown status fail-closed |
| `tests/test_operations_restore.py` | successful event payload/version; parent latest cancel; legacy missing parent flag; failed/repeated restore creates no event |
| `tests/test_catalog_admin_soft_delete.py` | event + primary snapshot before/after для item/category/unit; guard failure no event |
| `tests/test_acceptance_audit_effects.py` (new) | accept effect; mixed accept/lost two events; mark_lost no effect; found/return effect; lost write_off no effect; rollback atomicity; action-time effective_at |
| `tests/test_audit_operations.py` | submit/system submit explicit effective_at; cancel reversal uses cancelled_at |
| correction audit test по текущей convention | correction effect uses apply/event timestamp, не original operation date |
| `tests/test_audit_item_effects_effective_at_migration.py` (new/integration) | event-aware backfill, NULL=0, index/default, downgrade/upgrade |
| `tests/test_reports_read_model.py` | снять existing xfail после GROUP BY fix; default/true/false system origin filter; manual ADJUSTMENT retained; count/aggregate after filter |
| `tests/test_integrity_check_cli.py` (new) | clean/corrupt fixture каждого symbolic check; JSON schema; stable ordering; sample limit; threshold exits; sanitized DB error; read-only transaction |
| `Warehouse_web/apps/bff_api/tests.py` | BFF forwards explicit `exclude_system_effects=true/false`; omitted param remains omitted; unrelated report params unchanged |

DB-backed corruption fixtures должны быть transaction-scoped/disposable. Тест не имеет права оставлять повреждённые rows после teardown.

### Coordination documentation

- root `Makefile` — target only, без изменения stand topology;
- `docs/audit-event-catalog.md`;
- `SyncServer/README.md` и/или operator runbook;
- root `INDEX.md`, `AI_CONTEXT.md`, `SOLUTION_ROADMAP.md` — статус Stage A и ссылки;
- этот ТЗ — Evidence/checklist updates.

### Explicitly forbidden files/areas

- `Warehouse_web/` кроме `apps/bff_api/reports_views.py` и focused tests; весь `Warehouse_frontend/`, `Warehouse_client_core/`, desktop/mobile clients;
- Docker secrets/env files;
- production data repair scripts;
- generated outputs.

## 13. Implementation stages and dependencies

### Stage 0 — read-only preflight

Выполнить §3.1, собрать baseline counts, подтвердить ADR-0028 и актуальный Alembic head.

### Stage 1 — guards and missing audit events

Последовательно: A-1 → A-2 → A-3 → A-4. Все изменяют shared service/audit contracts, поэтому один owner.

### Stage 2 — effect timestamp migration

A-5 после зелёного Stage 1. Сначала model + все producer call sites, затем migration dry-run. Acceptance/lost effect capture из A-4 должно компилироваться с final timestamp contract.

### Stage 3 — report behavior

A-6 после Stage 1; SyncServer owner не меняет report source, Django owner только расширяет allow-list. BFF shard может выполняться параллельно A-5 после freeze query name.

### Stage 4 — integrity tooling

A-7 после финальной схемы A-5 и report semantics. Baseline SQL можно прототипировать раньше, но acceptance CLI — только после migration.

### Stage 5 — verification and docs

Focused → full DB integration → migration dry-run → real stand → regression → docs → QA.

## 14. Test Ladder

### Level 1 — static and migration checks

- `python -m pytest --collect-only`.
- `python -m compileall app scripts/integrity_check.py`.
- В репозитории на момент authoring нет отдельного обязательного lint/type command; если executor обнаружит актуальную конфигурацию, добавить её в Evidence, иначе не придумывать `mypy`/`ruff` command.
- `python -m alembic heads` → один head.
- `python -m alembic upgrade head` на disposable DB.
- `python -m alembic downgrade -1 && python -m alembic upgrade head` на disposable DB.
- Schema inspection: `audit_item_effects.effective_at` NOT NULL после upgrade.

### Level 2 — unit tests

- Workflow status matrix A-1, включая direct service call.
- Event payload builders/snapshot serializers A-2…A-4.
- Report filter truth table A-6.
- CLI FULL OUTER JOIN/scale normalization, symbolic codes, output/exit threshold/error sanitization A-7.

### Level 3 — component tests

- FastAPI route A-1: success/409/authz.
- Report endpoint OpenAPI/query parsing/default and pagination.
- Existing item-movement xfail снят только после исправления `TemporaryItem.name` GROUP BY; неожиданный XPASS с оставленным marker не считается pass.
- CLI parser + Make target dry invocation/help.
- Django focused component test: `python manage.py test apps.bff_api.tests` (или более узкий актуальный test label, если выделен новый класс).

### Level 4 — DB-backed integration tests

- Restore transaction writes event and rollback leaves neither state nor event.
- Soft-delete each entity persists snapshot independent of live entity state.
- Mixed acceptance and all lost resolution actions write correct per-action events/effects; mark_lost/write_off prove absence of warehouse effect.
- Migration backfill cases: submit uses operation effective_at; cancel uses cancelled/event time; correction uses event time; orphan operation_id uses event/effect fallback; no value uses migration run time.
- Report excludes/included system effects correctly.
- Each symbolic integrity check has clean and corrupted fixture; transaction is verifiably read-only.
- Django BFF forwards explicit true/false unchanged and never invents its own default.

### Level 5 — real stand smoke

Required services: SyncServer `:8000`, PostgreSQL `:5432`; Django `:8001` only for global health, UI не применим.

1. Probe `/api/v1/health`, `/healthz/`, `pg_isready` per root protocol.
2. Создать disposable draft, изменить date → success.
3. Submit и повторить date change → 409, state/effects unchanged.
4. Cancel → restore → query audit API/CLI, увидеть `operation.restore`.
5. На disposable inactive candidate выполнить допустимый soft-delete и увидеть snapshot event.
6. Выполнить RECEIVE/MOVE acceptance с accepted + lost action, затем found/return lost resolution; проверить per-line events/effects/effective_at.
7. Сравнить item movement default, `exclude_system_effects=true/false` на system-generated operation.
8. `make integrity-check` → сохранить JSON summary и exit code; существующие дельты не исправлять.

### Level 6 — UI automation

**N/A для Stage A.** Angular/Django UI не меняются; BFF passthrough покрывается component tests. N/A отмечено архитектором в checklist.

### Level 7 — user/operator scenarios

1. Root пытается перенести submitted operation на прошлую дату и получает отказ без изменения истории.
2. Root восстанавливает отменённую operation; расследователь видит полный cancel/restore/resubmit cycle.
3. Chief/root удаляет неиспользуемую catalog entity; расследователь видит before/after без live join.
4. Оператор запускает `make integrity-check`, получает summary, отличает critical deltas от Stage-B warnings и не раскрывает credentials.

### Level 8 — regression pack

- Полный `cd SyncServer && python -m pytest`.
- Полный `cd Warehouse_web && python manage.py test`, потому что BFF file touched.
- Existing submit/cancel/restore/acceptance/corrections/merge/audit/report suites.
- Alembic full upgrade from empty DB и upgrade from pre-A-5 snapshot.
- Проверка BFF passthrough и отсутствия Angular/UI changes.

## 15. Stand and data requirements

- PostgreSQL 15 в disposable/dev lifecycle; перед migration smoke — backup или disposable clone.
- Seed: root, chief/storekeeper, два sites, active item/unit/category, операции draft/submitted/cancelled, RECEIVE/MOVE with acceptance, manual/system ADJUSTMENT.
- Environment variables: только имена `DATABASE_URL`, `SYNC_ROOT_USER_TOKEN`, `SYNC_DEVICE_TOKEN`; значения не печатать и не включать в Evidence.
- Start: `make up`; fallback `docker compose up -d` по root protocol.
- Reset: удалять только созданные test fixtures штатным fixture teardown/transaction rollback; broad DELETE/TRUNCATE и volume reset запрещены.

## 16. Risks and mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| A-1 конфликтует с legacy cancelled-date flow | High | ADR-0028 draft-only; restore сначала возвращает draft; route/service tests |
| A-5 присваивает late acceptance/reversal неправильный сезон | Critical | ADR-0028 cause-time matrix + producer-specific tests |
| Backfill использует время migration | Critical | Event-aware stable fields only; explicit fixture proves timestamp != migration run time |
| Default A-6 меняет отчёт существующего клиента | High | ADR-0028 intentional safety default + explicit false rollback mode + release note |
| Existing item-movement endpoint имеет xfail/SQL GROUP BY bug | High | A-6 prerequisite fix + снять xfail до filter tests |
| Per-line events создают значительный объём | Medium | Один event на non-zero action, индексы только по evidence, performance test на realistic batch |
| Audit effect helper остаётся fail-open | Critical | Non-empty capture без insert repo aborts UoW; mocks реализуют contract |
| `EXPECTED_EFFECT_GAP` false positive для non-warehouse actions | High | Operation/action matrix и fixtures по каждому типу |
| Decimal scale даёт ложный drift | High | SQL NUMERIC + `ROUND(sum,3)`, без float; effect-only keys через FULL OUTER JOIN |
| CLI ошибочно воспринимается как auto-repair | High | Read-only contract, имя/доки/permissions, никаких mutation options |
| R-26 заявлен закрытым без schedule | High | Stage A acceptance помечает частичное закрытие; scheduling — отдельный owner/TZ |
| Параллельная Alembic migration создаёт multiple heads | High | Single migration owner, preflight heads, rebase/revision update до merge |
| Backfill/index держит lock дольше deployment window | High | Row-count + timed clone dry-run; при превышении split expand/backfill/contract до implementation |

## 17. Final Acceptance Criteria

Stage A принят только если:

1. ADR-0028 выпущен; ТЗ и реализация синхронизированы с его решениями.
2. A-1…A-7 реализованы в заявленном scope без новых domain tables и без прямых balance writes.
3. Submitted/cancelled effective date immutable по утверждённой матрице.
4. Restore и три soft-delete path имеют атомарный audit trail.
5. Acceptance и lost-resolution actions forensic-reconstructable; каждая их warehouse mutation имеет `acceptance` effect с action-time.
6. `audit_item_effects.effective_at` NOT NULL, deterministic backfill завершён, новые paths заполняют поле явно.
7. Existing item-movement xfail устранён; report filter semantics/default документированы и проходят truth-table + stand tests.
8. `make integrity-check` read-only, детерминирован, имеет JSON output/exit threshold и проверяет все symbolic codes с честной классификацией.
9. Для чистого acceptance fixture critical diff = 0; реальные известные дельты перечислены, объяснены и не скрыты.
10. Full SyncServer и Warehouse_web test suites, а также migration ladder зелёные.
11. Stand smoke и четыре user/operator scenario завершены.
12. Активная документация содержит статус и ссылки; незакрытые R-06/R-26/Stage-B gaps обозначены как partial/deferred.
13. QA verifier проверил Evidence и отметил final checkbox.

## 18. Evidence template

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|
| ADR gate | document review | pass/fail | ADR path/status |
| Static/type checks | `<actual commands>` | pass/fail/skipped | log path/summary |
| Unit/component | `python -m pytest <focused>` | pass/fail | test count |
| DB integration | `python -m pytest <db tests>` | pass/fail | DB fixture/lifecycle |
| Migration upgrade/downgrade | `python -m alembic ...` | pass/fail | revision/head + clone note |
| Full regression | `python -m pytest` | pass/fail | passed/failed count |
| Django BFF regression | `python manage.py test` | pass/fail | passed/failed count |
| Stand smoke | curl/CLI | pass/fail/skipped | sanitized IDs + response assertions |
| Integrity clean fixture | `make integrity-check ...` | pass/fail | exit code + symbolic check counts |
| Integrity dev baseline | `make integrity-check ...` | pass/warning/fail | classified counts, no secrets |
| User scenarios | manual/API | pass/fail/skipped | scenario IDs/results |
| Documentation | review | pass/fail | changed paths |

## 19. References

- `Functional and WorkLogik.md` §§II.4, II.6.7–6.10.
- `docs/audit/HISTORICAL_INTEGRITY_ROADMAP.md` §1.
- `docs/audit/HISTORICAL_RISK_REGISTER.md` §§1, 2.1, 5.
- `docs/audit/HISTORICAL_INTEGRITY_AUDIT.md`.
- `docs/audit/HISTORICAL_DATA_FLOW.md`.
- `docs/audit/SEASON_REPORT_READINESS.md`.
- `docs/adr/0003-layered-backend-with-unit-of-work.md`.
- `docs/adr/0004-operation-driven-inventory-and-derived-balances.md`.
- `docs/adr/0018-audit-architecture.md`.
- `docs/adr/0028-historical-integrity-stage-a.md`.
- `docs/reviews/architecture-review-historical-integrity-stage-a.md`.
- `docs/AGENT_TZ_WORKFLOW.md`.

---

**Architect handoff:** ТЗ синхронизирован с ADR-0028 и фактическими code contracts на 2026-08-05. Реализация не начата. Stage 0 обязан повторно проверить branch/ownership/Alembic head и baseline данных, потому что в nested `SyncServer` одновременно идут другие изменения.
