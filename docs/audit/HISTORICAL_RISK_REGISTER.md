# Historical Risk Register — SyncServer

**Дата:** 2026-07-31
**Объект:** `SyncServer/` + интеграционные аспекты (Docker stand).
**Связанные документы:** `HISTORICAL_INTEGRITY_AUDIT.md`,
`HISTORICAL_DATA_FLOW.md`, `SEASON_REPORT_READINESS.md`,
`HISTORICAL_INTEGRITY_ROADMAP.md`.
**Режим:** read-only research.

---

## 0. Шкалы

### 0.1 Приоритет

| P0 | Необнаружимая потеря / искажение истории, может ударить сезонную отчётность |
|----|----------------------------------------------------------------------------|
| P1 | Заметное влияние на статистику текущего сезона, но видимо аудиту |
| P2 | Важное укрепление, допустимо после сезона |
| P3 | Долгосрочный архитектурный долг |

### 0.2 Вероятность

| L | Low | Маловероятно в ближайший сезон |
| M | Medium | Возможно при штатной работе пользователей |
| H | High | Возможно при рутинной эксплуатации или ошибке пользователя |

### 0.3 Ущерб

| L | Локально, один баланс, одна операция |
| M | Множество строк/операций, требует расследования |
| H | Один season-report содержит значимые ошибки |
| C | Catastrophic — данные об отчётности утрачены |

### 0.4 Обнаруживаемость

| 1 | Заметно сразу в UI/BFF |
| 2 | Заметно при подготовке сезонного отчёта |
| 3 | Заметно только при специальном аудите |
| 4 | Необнаружимо без независимого forensic-сравнения |

### 0.5 Обратимость

| full | Полностью обратимо через compensating-операции вручную |
| partial | Частично, с потерей значений некоторых полей |
| none | Необратимо без потерь (например, потеря snapshot-before для item.update) |

---

## 1. Карта рисков (таблица)

| ID | Область | Сценарий | Prio | Вер | Ущ | Обнар | Обратимость | Текущая защита | Рекомендуемая защита |
|----|---------|----------|------|-----|----|-------|-------------|----------------|---------------------|
| R-01 | III/Балансы | `effective_at` изменён у submitted операции без compensation effects | **P0** | H | H | 3 | partial | `require_not_cancelled_for_effective_at_change` (`operations_workflow_policy.py:15-20`); audit_event пишется с diff | Запрет update `effective_at` для submitted/cancelled на уровне service + DB constraint или trigger |
| R-02 | IV/merge | `merge_items` физически переписывает `operation_lines.item_id` без per-line resource и без original_item_id | **P0** | H | H | 3 | none | audit_event_resources merge_source/target/generated (без per-line reassigned) | Ввести `OperationLine.original_item_id`, persist `merge_line_map`, отчёт через original_id |
| R-03 | VII/Audit | `restore_operation` не пишет audit_event | **P0** | M | H | 3 | full | workflow `require_cancelled_for_restore`, root-only `require_root_for_restore` | Добавить `record_audit_event('operation.restore', changes)` |
| R-04 | V/Master | `soft_delete_item/category/unit` не пишет audit_event | **P0** | M | M | 3 | full | guarded: cannot delete active items; workflow защита | Добавить audit_event с snapshot_before/after |
| R-05 | III/Balances | `audit_item_effects.created_at` ≠ `operations.effective_at`, отчёты используют `effective_at` для даты | **P0** | H | M | 2 | n/a | только warning в коде, нет защиты | report: добавить `audit_item_effects.operation_at` = operation.effective_at; ввести `audit_item_effects.effective_at` |
| R-06 | III/Balances | Late acceptance (после смены сезона) переоценивает баланс «на дату submit» через смену operation_at | **P0** | M | M | 3 | full | требуется `acceptance_required=True` для RECEIVE/MOVE; pending balances | Разрешить только accept в пределах N дней от submit и явно помечать late accept events |
| R-07 | VI/Documents | Нет файлов source-documents, нет hash, нет OCR engine version | **P0** | M | M | 4 | n/a | хранятся строки; source_ref — единственный идентификатор | Добавить `source_documents` таблицу + storage + хранение файлов |
| R-08 | IV/Merge | Нет `merge_preview` / `dry_run` / `merge_plan` | **P1** | M | H | 2 | partial | ничего | Endpoint `GET /admin/items/{id}/merge-preview` с разложением: op_lines count, balances count, conflicts |
| R-09 | IV/Merge | Нет `unmerge` механизма; compensating ADJUSTMENT раздувает балансы и статистику | **P1** | L | H | 2 | none | compensating ADJUSTMENT как inverse merge | Endpoint `/admin/items/{id}/unmerge` с protection: only if target has no other merges after source |
| R-10 | VI/Documents | Нет `page_number`, `line_number_in_document` | **P1** | M | L | 3 | n/a | source_*_snapshot строк содержит manual copy | Хранить на line: `source_doc_line_id`, `page`, `row` |
| R-11 | III/Balances | Нет integrity check `balance == sum(audit_item_effects)` (с учётом cancel_reversal/merge_*) | **P0** | L | H | 4 | n/a | ничего | Добавить CLI / scheduled скрипт `integrity_check.py` |
| R-12 | VII/Audit | `restore_operation` + cancel + restore + new-submit без `audit_event` создаёт «потерянный» cycle | **P0** | M | M | 3 | full | audit_event.cancel пишется, restore — нет, submit — да, но без link к предыдущему submit | Запретить restore, если с прошлой отмены операция была модифицирована (требуется review) |
| R-13 | II/Lines | При correction V1 scope = RECEIVE без acceptance_required; многие типы операций без audit-chain для corrections | **P1** | H | M | 3 | full | correction flow хорошо работает только в V1 | Расширить V1..V8 phases (INV-C2..C8) без полного рефакторинга |
| R-14 | VII/Audit | Audit API только `root` / `chief_storekeeper` — простой кладовщик не видит историю изменений | **P1** | H | L | 1 | n/a | rbac `require_admin_basic` | Endpoint для storekeeper: `GET /audit/visible?entity_type=item&entity_id=X` |
| R-15 | III/Balances | При merge balance_transfer нет защиты от отрицательного source balance | **P1** | L | M | 3 | n/a | source must have positive balance for transfer? нет, передача идёт по non-zero | Защита: refuse merge with negative balance |
| R-16 | X/Backup | logical backup (pg_dump) + нет PITR | **P1** | M | H | 4 | partial | daily pg_dump (manual) | Включить WAL archiving, `wal_level=replica`, ежедневный скрипт archive |
| R-17 | X/Backup | Отсутствие проверенной процедуры restore | **P1** | L | H | 4 | n/a | только документированная команда | Создать `make backup-test-restore` playbook |
| R-18 | II/Lines | `_freeze_catalog_snapshot` пропускается для legacy operations; snapshot может быть устаревшим при первой submit | **P2** | M | L | 3 | n/a | только для creation_source in ('source_document', 'manual') | Backfill snapshot для legacy (миграция данных) |
| R-19 | V/Master | Item.update / Category.update не пишут snapshot_before/after; невозможно точно восстановить историю ТМЦ | **P1** | H | M | 3 | partial | audit_event пишется с `changes` JSONB (что менять) | Перейти на snapshot_before/after во всех catalog update events |
| R-20 | II/Lines | `merge_balance_transfer` audit_event_resources ссылается на operation, но не на затронутые строки | **P0** | H | H | 3 | none | `generated` relation link на ops, но не на строки | Добавить audit_event_resources link per-struck line с relation='reassigned' |
| R-21 | III/Balances | В отчёте `list_item_movement` нет `is_system_generated` фильтра по умолчанию — merge write_off/receipt, cancel_reversal, temp_* сливаются в обычное движение | **P1** | M | M | 2 | n/a | ADJUSTMENT не исключается из report (`exclude_adjustments` query param по умолчанию false) | Ввести `exclude_system_effects` query param (default false), UI flag |
| R-22 | IX/Period close | Нет модели period close / watermark / report_snapshot | **P1** | M | H | 3 | n/a | ничего | Ввести `periods` table + `report_snapshots` table + `close_period` flow |
| R-23 | VII/Audit | `actor_device_id` не отличает LLM-клиент от пользователя (проксирование через Django device) | **P2** | M | L | 3 | n/a | source_client enum | Расширить source_client enum и передавать actor_kind |
| R-24 | VII/Audit | operation.correction.applied пишет audit_event, но только для RECEIVE V1 scope; для MOVE/EXPENSE/ADJUSTMENT таких audit нет | **P2** | M | L | 3 | n/a | correction V1 ограничение | Расширить correction scope по phase C2..C8 |
| R-25 | III/Balances | Поле `audit_item_effects.operation_id SET NULL` означает, что hard-delete операций в будущем делает orphan effect | **P2** | L | M | 3 | n/a | сейчас hard-delete не выполняется через API | Запретить hard-delete операций через API, оставить только soft-delete |
| R-26 | III/Balances | Нет автоматического scheduled integrity check (нет cron, нет scheduled repo) | **P0** | H | M | 4 | n/a | ничего | Добавить `make integrity-check` команду + cron |
| R-27 | X/Backup | Нет мониторинга успешности backup (не выполнено = silent) | **P2** | M | M | 4 | n/a | manual `make backup-db` | Health-check: dump сегодняшний есть и не пустой |
| R-28 | II/Lines | В rebuild_operation_lines для correction нет гарантии, что deleted lines (status='removed') не ломают pending_acceptance_balances FK | **P2** | L | M | 3 | partial | `with cascade="all, delete-orphan"` + порядок locks | Добавить pre-check перед DELETE: balance и locked-pending строки проверить явно |
| R-29 | I/Operation | Повторный submit с тем же `client_request_id`, но другим hash → 409, но если hash тот же — silent return; возможен double-submit из-за retries | **P1** | M | L | 2 | n/a | idempotency check по hash | Возвращать оригинальную operation с status code на выбор |
| R-30 | VII/Audit | Audit events создаются в одном UoW с business mutation, но UoW может rollback'нуться после `record_audit_event` из-за IntegrityError → audit_event не пишется | **P1** | M | M | 3 | n/a | IntegrityError в `submit_operation` (line 2262-2266) rollback'нет всё | Сделать audit_event写入 всеми путями через отдельный callback |
| R-31 | I/Operation | `display_number` generation не идемпотентен при нескольких операциях в одной секунде | **P2** | M | L | 2 | n/a | на основе `site_id+timestamp` | Generation в Postgres через sequence per site/year |
| R-32 | IV/Merge | Цепочка merges A→B→C: если кто-то сделает merge A→B в момент, когда B уже merged в C, защиты нет (защита в service только на is_active) | **P1** | L | H | 4 | partial | service check target.is_active, но не «цель — уже merged» | Pre-check перед merge: target.merged_into_id == null |
| R-33 | V/Master | Изменение `Item.unit_id` не пересчитывает `inventory_subject_id` и balances — может разойтись | **P2** | M | M | 3 | n/a | unit_id FK не мешает изменению | Запретить update unit_id если item used in submitted op без merge flow |
| R-34 | V/Master | Удаление категории без merge — Items с deleted category_id могут торчать в отчётах | **P2** | M | M | 3 | n/a | guard `if not active` | Сначала merge категории в другие, потом удалять |
| R-35 | VII/Audit | `audit_helper.ALLOWED_SOURCE_CLIENTS = {web,desktop,mobile,cli}` — все остальные становятся `'unknown'`; теряется различие LLM/browser/headless | **P2** | M | L | 3 | n/a | явная normalize | Расширить enum + actor_kind |
| R-36 | VIII/Reports | `reports_repo.list_item_movement` использует только `operations.effective_at`; если оно backdated — отчёт неконсистентен с submit-real time | **P0** | H | H | 3 | partial | functional log эффективности | Прекратить приём backdating (см. R-01) + хранить separate history |
| R-37 | V/Master | `merged_into_id` на категории и issue_object без events для отдельных шагов (цепочка правок в chain_of_merge) | **P2** | L | L | 3 | n/a | audit_event `category.merge`/`issue_object.merge` (см. catalog_admin_service.py) | OK (покрыто) |
| R-38 | III/Balances | ADJUSTMENT операции могут быть системными и смешиваются с ручными в отчётах и движениях | **P1** | H | M | 2 | n/a | `exclude_adjustments` query param | UI-flag + filterable mode |
| R-39 | II/Lines | В `OperationLine.comment` и `notes` — free text; может содержать PII без контроля доступа | **P3** | M | L | 2 | n/a | нет special PII guard | PII policy / masked export |
| R-40 | VI/Documents | Source documents не версионируются (v2 import того же источника → новая операция) | **P1** | M | M | 3 | n/a | idempotency по source_ref | linking target_operation через chain, хранить import history |

---

## 2. Сводный топ по приоритетам

### 2.1 P0 (привести в порядок до конца сезона)

| ID | Заголовок | Где править |
|----|-----------|-------------|
| R-01 | effective_at back-date на submitted | `operations_service.py:1336-1382`; `routes_operations.py:261-290` |
| R-02 | merge_items переписывает operation_lines.item_id | `catalog_admin_service.py:678-684` + добавить per-line resource |
| R-03 | restore_operation без audit_event | `operations_service.py:2778-2793` |
| R-04 | soft_delete_item/category/unit без audit_event | `catalog_admin_service.py:421-459` |
| R-05 | created_at vs effective_at разрыв | добавить `audit_item_effects.effective_at` или переписать JOIN |
| R-06 | late acceptance переоценивает баланс «на дату submit» | validation в `accept_operation_lines` |
| R-07 | нет файлов source-documents | добавить `source_documents` table |
| R-11 | нет integrity check balance == effects | новый CLI/скрипт |
| R-12 | restore без audit ломает cycle | добавить `operation.restore` event |
| R-20 | merge не имеет per-line resource | добавить relation='reassigned' для каждой строки |
| R-26 | нет scheduled integrity check | CI / cron job |
| R-36 | отчёт чувствителен к back-date | см. R-01 |

### 2.2 P1 (можно сдвинуть в зимнее окно до следующего сезона)

R-08, R-09, R-10, R-13, R-14, R-15, R-16, R-17, R-19, R-21, R-22,
R-29, R-30, R-32, R-38, R-40

### 2.3 P2 (после сезона, в план hardening)

R-18, R-23, R-24, R-25, R-27, R-28, R-31, R-33, R-34, R-35

### 2.4 P3 (долгосрочный долг)

R-39

---

## 3. Mapping по областям (только P0/P1)

### III. Balances / effects
R-01, R-05, R-06, R-11, R-15, R-21, R-25, R-26, R-36, R-38

### IV. Merge каталога
R-02, R-08, R-09, R-20, R-32

### V. Master data
R-04, R-19, R-33, R-34

### VI. Source documents
R-07, R-10, R-40

### VII. Audit
R-03, R-12, R-14, R-23, R-24, R-30, R-35

### VIII. Отчётность
R-05 (частично), R-11 (частично), R-21, R-36, R-38

### IX. Закрытие периода
R-22

### X. Backup / PITR
R-16, R-17, R-26, R-27

---

## 4. Что **не требует** фикса

См. § 11 в `HISTORICAL_INTEGRITY_AUDIT.md` — это уже реализованные защиты
(append-only audit, UoW per request, locks, snapshots). Аудит этих
позиций не блокирует сезонную отчётность и не входит в roadmap.

---

## 5. Обязательные integrity checks (из R-11, R-26)

Сводка CLI/скриптов для добавления в `make` или отдельный пакет:

```text
psql queries:

-- (1) balance vs sum of audit_item_effects
SELECT b.site_id, b.inventory_subject_id, b.qty,
       (SELECT COALESCE(SUM(quantity_delta),0)
        FROM audit_item_effects e
        WHERE e.site_id = b.site_id
          AND e.inventory_subject_id = b.inventory_subject_id)
       AS effects_sum
FROM balances b
WHERE ABS(b.qty -  effects_sum) > 0.001;

-- (2) submitted operations without audit_item_effects
SELECT o.id, o.operation_type, o.submitted_at
FROM operations o
WHERE o.status = 'submitted'
  AND NOT EXISTS (SELECT 1 FROM audit_item_effects e WHERE e.operation_id = o.id);

-- (3) merge chains: cycles
WITH RECURSIVE chain AS (
  SELECT id, merged_into_id, 1 AS depth, ARRAY[id] AS path
  FROM items WHERE merged_into_id IS NOT NULL
  UNION ALL
  SELECT c.id, i.merged_into_id, c.depth+1, c.path || i.id
  FROM chain c
  JOIN items i ON i.id = c.merged_into_id
  WHERE NOT (i.id = ANY(c.path)) AND c.depth < 32
)
SELECT * FROM chain WHERE depth >= 32 OR id IN (
  SELECT id FROM chain GROUP BY id HAVING COUNT(*) > 1
);

-- (4) audit_event_resources orphan by entity_type
-- (resource may be hard-deleted, but if FK enforcement is on, this is empty)
-- Run only if FK removed — none currently.

-- (5) update_operation_effective_at history per operation
SELECT id, status, effective_at, updated_at, version, last_corrected_at
FROM operations WHERE effective_at < created_at AND status = 'submitted';

-- (6) drop rate late acceptance
SELECT e.operation_id, e.created_at, o.effective_at, EXTRACT(DAY FROM e.created_at - o.effective_at) AS late_days
FROM audit_item_effects e
JOIN operations o ON o.id = e.operation_id
WHERE o.acceptance_required = TRUE
  AND e.effect_type = 'receipt'
ORDER BY late_days DESC NULLS LAST;

-- (7) merge audit completeness
SELECT a.id, a.changes
FROM audit_events a
WHERE a.event_type = 'item.merge'
  AND (a.changes->>'op_lines_reassigned_count')::int > 0;

-- (8) orphan audit_events from cancelled-removed operations
SELECT a.id
FROM audit_events a
WHERE NOT EXISTS (SELECT 1 FROM operations o WHERE o.id::text = a.entity_id)
  AND a.entity_type = 'operation';
```

Эти запросы должны быть включены в `make integrity-check` или CI step.

---

## 6. Сводная секция для отчёта руководству

> Из 40 зарегистрированных рисков — 12 категории P0, 16 категории P1,
> 11 категории P2, 1 категории P3. Все P0 связаны либо с отсутствием
> audit_event для критичных действий (restore, soft-delete), либо с
> физическим переписыванием данных каталога (merge), либо с
> неконсистентностью дат (effective_at vs created_at). P0 могут привести
> к расхождению сезонного отчёта от реальности без очевидного следа.
