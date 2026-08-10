# Season Report Readiness — SyncServer

**Дата:** 2026-07-31
**Цель:** оценить, какие сезонные отчёты могут быть сформированы уже сейчас,
какие условно достоверны, какие достоверно недостоверны, и какой минимум
работ нужно сделать до конца сезона для повышения уровня доверия.

См. `HISTORICAL_INTEGRITY_AUDIT.md` для подтверждений file:line, и
`HISTORICAL_RISK_REGISTER.md` для детальной карты рисков.

---

## 1. Положение дел

Сейчас, на основании чтения кода SyncServer, доступны следующие
категории отчётов:

- **Балансовые отчёты (на текущий момент)** — точные.
- **Движения за период по `operation_at = coalesce(operations.effective_at, created_at)`** —
  чувствительны к `R-01` (back-date effective_at), `R-06` (late accept effects) и
  `R-21` (системные effects смешиваются с ручными).
- **Текущий каталог + история изменений** — точные через admin audit API,
  но **storekeeper** (`role=storekeeper`, `observer`) их не видит.

Что НЕ доступно безопасно на сегодня:

- **Исторический режим (snapshots на момент операции)** — snapshots есть,
  но **merge_items перезаписывает OperationLine.item_id**, что делает
  прямой SQL-запрос по историческому item невозможным без ручного walk
  через `audit_event_resources`.
- **Source-of-truth «документ → строка операции»** — нет файлов, нет хешей,
  пере-импорт идемпотентен только по `source_ref`.
- **Полная картина `merge_chain`** — есть `MAX_MERGE_DEPTH=16` в read API,
  но table-level cycle не обнаруживается.

---

## 2. Список отчётов и их статус

Условные обозначения:

| ✅ | Можно формировать достоверно уже сейчас |
| ⚠ | Можно, но условно — нужны ручные проверки |
| ❌ | Нельзя считать достоверным без доработок |
| 🔧 | Нужно доработать для достоверности |

| # | Отчёт | Источник в коде | Уровень | Риск |
|---|-------|-----------------|---------|------|
| 1 | Остатки на начало периода | `audit_item_effects` минус последующие; через `date_from..date_to` фильтр | ⚠ | R-05, R-06 |
| 2 | Остатки на конец периода | `balances` на `date_to` или фильтр по `created_at<date_to` | ⚠ | R-05, R-06 |
| 3 | Движение ТМЦ за период (turnover) | `reports_repo.list_item_movement` | ⚠ | R-01, R-05, R-21, R-36 |
| 4 | Приходы по поставщикам | объединение `operations.operation_type='RECEIVE'` JOIN `operations.notes` | ⚠ | R-19 (нет audit на changes notes) |
| 5 | Приходы по документам | `source_document_type` + `source_ref` | ⚠ | R-07, R-40 |
| 6 | Выдачи по складам и объектам | `operation_type='ISSUE'` JOIN `operation_lines`, `issued_objects` | ⚠ | R-21 |
| 7 | Перемещения между складами | `operation_type='MOVE'`, два source/destination | ⚠ | R-01, R-21 |
| 8 | Списания | `operation_type='WRITE_OFF'`, branch на issue_object vs warehouse | ✅ | — |
| 9 | Корректировки системные | ADJUSTMENT + `is_system_generated=true` filter | ⚠ | нет API фильтра; только через audit_event_resources |
| 10 | Корректировки ручные | ADJUSTMENT + `system_reason is null` | ⚠ | R-38 |
| 11 | Merge / изменения каталога | audit_event filter `event_type IN ('item.merge','category.merge','issue_object.merge','temporary_item.merge',...)` | ✅ | — |
| 12 | Непринятые операции | `operations.acceptance_state='in_progress'` | ✅ | — |
| 13 | Частично принятые | `operation_lines.accepted_qty < qty AND lost_qty = 0` | ✅ | — |
| 14 | Расхождения принятое vs заявленное | `operation_lines` (`accepted_qty`, `lost_qty`, `pending_qty`) | ✅ | — |
| 15 | Потерянные активы | `lost_asset_balances` JOIN `operation_lines` | ✅ | — |
| 16 | История изменений ТМЦ для кладовщика | аудит API только для root/chief | ❌ | R-14 |
| 17 | Restore / Cancel история | audit_event `operation.cancel` есть, **operation.restore нет** | ⚠ | R-03, R-12 |
| 18 | Source-document как PDF | `documents.payload` + `documents.payload_hash` есть, **но файл не хранится** | ❌ | R-07 |
| 19 | История по одному issue object | audit_event_resources linkится на item, не на issue_object (через merge_event) | ⚠ | покрытие частичное |
| 20 | Report snapshot (preliminary/final) | нет модели period close | ❌ | R-22 |

---

## 3. Что нужно обязательно сделать до конца сезона

### 3.1 Обязательный минимум P0 (до выпуска season_report)

| # | Действие | Что это даёт | Кто делает |
|---|----------|--------------|------------|
| 1 | Запретить `update_operation_effective_at` для `status='submitted'` (через service и guard, добавить DB CHECK на trigger или новый constraint) | R-01: исключает backdating |
| 2 | Добавить `operation.restore` audit_event в `restore_operation` | R-03, R-12: восстанавливает журнал жизненного цикла |
| 3 | Добавить `audit_event` для `soft_delete_item/category/unit` (snapshot_before/after) | R-04: объяснимый soft-delete |
| 4 | Создать `OperationLine.original_item_id` миграцией с backfill `=item_id`; использовать в merge для сохранения source-binding | R-02, R-20: line_map |
| 5 | Добавить `merge_line_map` ресурс-event-entries per-line (relation='reassigned') | R-02, R-20 |
| 6 | Добавить поле `audit_item_effects.effective_at` (server-set = operations.effective_at on insert) | R-05 |
| 7 | Backfill `effective_at` для всех существующих effect rows (UPDATE FROM operations) | R-05: историю тоже надо исправить |
| 8 | Добавить per-item фильтр `exclude_system_effects` в `reports_repo` | R-21, R-38 |
| 9 | Создать CLI `make integrity-check` с запросами из `HISTORICAL_RISK_REGISTER.md §5` | R-11, R-26 |
| 10 | Включить `audit_event` для `accept_operation_lines` per-line accepted/lost (action='accept'/'mark_lost') | R-06 observability |

Всего ~10 пунктов P0. Каждый даёт конкретную защиту от расхождения сезонной отчётности.

### 3.2 Желательно (P1, но не блокеры)

| # | Действие | Что это даёт |
|---|----------|--------------|
| A | Добавить `merge_preview` endpoint | R-08 |
| B | Расширить correction scope на V2 (EXPENSE/MOVE/ADJUSTMENT) | R-13, R-24 |
| C | Endpoint `/audit/visible?entity_type=item&entity_id=X` для storekeeper-роли | R-14 |
| D | Включить WAL archiving + ежедневный удалённый backup | R-16, R-17 |
| E | Сделать scheduled integrity check | R-26 |
| F | Расширить `actor_username_snapshot` для отличия LLM-клиента | R-23 |
| G | Late acceptance cutoff (запрет accept через N дней) | R-06 |
| H | Снимки файл + hash + parser_version в отдельной `source_documents` таблице | R-07 |

---

## 4. SQL/CLI-диагностики, которые нужно запустить прямо сейчас

Сразу же после проведения миграций P0 и перед подготовкой сезонного отчёта:

```sql
-- (Q1) back-dating check
SELECT id, status, effective_at, created_at, version,
       EXTRACT(DAY FROM created_at - effective_at) AS back_days
FROM operations
WHERE effective_at IS NOT NULL
  AND effective_at < created_at
  AND status = 'submitted'
ORDER BY back_days DESC;
-- Ожидание: 0 записей. Любое число >0 — потенциальная back-date.

-- (Q2) late acceptance
SELECT o.id, o.operation_type, o.submitted_at, MAX(a.created_at) AS last_accept_at,
       EXTRACT(DAY FROM MAX(a.created_at) - o.submitted_at) AS days_to_accept
FROM operations o
JOIN audit_events e ON e.entity_id::text = o.id::text AND e.event_type='operation.submit'
JOIN audit_item_effects a ON a.audit_event_id = e.id
WHERE o.acceptance_required = TRUE
  AND o.acceptance_state IN ('in_progress','resolved')
GROUP BY o.id, o.submitted_at, o.operation_type
HAVING EXTRACT(DAY FROM MAX(a.created_at) - o.submitted_at) > 7;

-- (Q3) merge history
SELECT id, changes->>'source_item_id' AS src, changes->>'target_item_id' AS tgt,
       (changes->>'op_lines_reassigned_count')::int AS reassigned,
       created_at
FROM audit_events
WHERE event_type = 'item.merge'
ORDER BY created_at;

-- (Q4) orphan operations без effects
SELECT o.id, o.operation_type, o.submitted_at
FROM operations o
WHERE o.status = 'submitted'
  AND NOT EXISTS (
    SELECT 1 FROM audit_item_effects e WHERE e.operation_id = o.id
  );

-- (Q5) integrity balance vs effects
SELECT b.site_id, b.inventory_subject_id, b.qty,
       (SELECT COALESCE(SUM(quantity_delta),0)
        FROM audit_item_effects e
        WHERE e.site_id = b.site_id
          AND e.inventory_subject_id = b.inventory_subject_id) AS effects_sum,
       ABS(b.qty - (SELECT COALESCE(SUM(quantity_delta),0)
                    FROM audit_item_effects e
                    WHERE e.site_id = b.site_id
                      AND e.inventory_subject_id = b.inventory_subject_id)) AS diff
FROM balances b
WHERE ABS(b.qty - (SELECT COALESCE(SUM(quantity_delta),0)
                   FROM audit_item_effects e
                   WHERE e.site_id = b.site_id
                     AND b.inventory_subject_id = e.inventory_subject_id)) > 0.001
LIMIT 100;

-- (Q6) restore без cancel audit
SELECT r.* FROM audit_events r
WHERE NOT EXISTS (
  SELECT 1 FROM audit_events c
  WHERE c.event_type='operation.cancel' AND c.entity_id = r.entity_id
);
-- (если есть operation.create без parent cancel — что-то потеряно)

-- (Q7) cycle detection в merge chain
WITH RECURSIVE chain AS (
  SELECT id, merged_into_id, 1 AS depth, ARRAY[id] AS path
  FROM items WHERE merged_into_id IS NOT NULL
  UNION ALL
  SELECT c.id, i.merged_into_id, c.depth+1, c.path || i.id
  FROM chain c
  JOIN items i ON i.id = c.merged_into_id
  WHERE NOT (i.id = ANY(c.path)) AND c.depth < 32
)
SELECT * FROM chain WHERE depth >= 32;
-- 0 строк = нет циклов.
```

Результаты этих запросов нужно сохранить в `docs/audit/INTEGRITY_RUN_<date>.md`
как часть приёмки сезонного отчёта.

---

## 5. Что заархивировать перед закрытием сезона

```text
1) backups/full_pre_close_<date>.dump      (pg_dump -Fc FULL schema+data)
2) backups/audit_events_<date>.json       (полная выгрузка аудита)
3) backups/audit_item_effects_<date>.csv  (granular journal)
4) backups/operations_<date>.csv          (все submitted за период)
5) backups/balances_<date>.csv            (текущие остатки)
6) backups/items_merge_chain_<date>.json  (snapshot merge_to chain)
7) backups/documents_<date>.tar           (накладные из documents.payload)
8) backups/integrity_check_<date>.log     (результат make integrity-check)
9) SHA256SUMS                               (хэш всех файлов)
10) INTEGRITY_RUN_<date>.md                (запросы из §4 с ответами)
```

Это позволит при будущих спорах/расследованиях точно повторить ситуацию
«в день перед закрытием» и проверить «что изменилось потом».

---

## 6. Процедура «перед выпуском сезонного отчёта»

Шаги в таком порядке:

1. **Pre-check сегодня (ночью)**:
   - запустить `make integrity-check` (после реализации §3.1)
   - сравнить с прошлыми integrity_check_*.log: дельта должна быть объяснимой.
2. **Snapshot данных**: §5 файлы, поместить в `backups/pre_close_<дата>/`.
3. **Snapshot merge chain**: убедиться, что нет активных merges с
   несогласованной цепочкой (Q7).
4. **Verify effective_at**: запустить (Q1), результат «0 строк». Если >0 —
   остановить, написать обоснование (это может быть реальная потребность
   в re-dating; нужно явное ADR).
5. **Verify late accept**: запустить (Q2), результат «0 строк» для каждого.
6. **Self-test report**: сгенерировать тестовый отчёт за прошлый
   календарный месяц, убедиться, что суммы движений согласованы с
   балансом открытия/закрытия. Сохранить под `backups/selftest_<date>/`.
7. **Generate final season report**: под наблюдением главного кладовщика
   или root. Сохранить под `backups/season_<year>_<date>/` с фиксированными
   SQL запросами и SHA256SUMS.
8. **Mark period closed**: после добавления модели `periods` — `INSERT
   INTO periods(season, snapshot_id, hash, closed_at)` (см. Этап D roadmap).

---

## 7. Что изменится в отчётности после Этапа A (срочные страховки)

Без Этапа A: движение/баланс по `effective_at` ≠ движение по `created_at`
в audit_item_effects. Любая пере-выгрузка сезонного отчёта с другим
источником дат даст разные числа.

С Этапом A:

- `audit_item_effects.effective_at` = `operations.effective_at` →
  единый источник даты и для report и для audit-trail.
- Все back-dating запрещены и видны по audit (где есть запись update).
- Late accept детектируется и помечается.

С Этапом B:

- merge snapshot в per-line resource делает «исторический» отчёт
  воспроизводимым.
- integrity-check автоматизирован.

С Этапом C (immutable original facts + canonical projections): нужны
отдельные таблицы `merge_line_map`, `original_item_id` — это уже
выходит за рамки доработок до конца сезона.

---

## 8. Краткий чеклист «можно ли закрыть сезон»

```text
[ ] 1. §3.1 пункт 1 выполнен (effective_at backdating закрыт)
[ ] 2. §3.1 пункт 2 выполнен (audit_event для restore)
[ ] 3. §3.1 пункт 3 выполнен (audit_event для soft delete)
[ ] 4. §3.1 пункт 6 выполнен (effective_at на effects)
[ ] 5. §3.1 пункт 7 выполнен (backfill effective_at)
[ ] 6. §3.1 пункт 8 выполнен (exclude_system_effects в reports)
[ ] 7. §3.1 пункт 9 выполнен (integrity-check скрипт)
[ ] 8. integrity-check запущен, diff=0 (или задокументирован)
[ ] 9. SQL §4 выполнен, все ожидаемые 0
[ ] 10. backups/pre_close_<date>.dump + files готовы
[ ] 11. self-test отчёт проходит (балансовый инвариант)
[ ] 12. season_report выпущен с фиксированными SQL и SHA256
[ ] 13. (опц.) period close запись создана
```

Если хотя бы один пункт не выполнен — сезонный отчёт можно формировать
**с указанием ограничений**, но не как «истину».

---

## 9. Какие отчёты достоверны уже сейчас (без изменений кода)

| Отчёт | Достоверность | Ограничение |
|-------|---------------|-------------|
| Текущие балансы | ✅ | моментальный снимок, не исторический |
| Движение за период на submitted операциях | ⚠ | только created_at; backdating-effective_at не виден |
| Списания | ✅ | если не было backdating |
| Непринятые и частично принятые | ✅ | если late accept не «прятался» через accept без записи |
| Merge история через audit_event | ✅ | только root/chief |
| Потерянные активы | ✅ | source documents не нужны |

---

## 10. Кому что полезно из этого документа

- Главный кладовщик / root: пункт 2 (P0 список), §3.1 — порядок доработок.
- Архитектор: §7 roadmap зависимости.
- Backend Agent: приступать к выполнению P0 (после ADR, см.
  `HISTORICAL_INTEGRITY_ROADMAP.md` Этап A).
- QA / dev-ops: §4 queries + §5 архивирование + чеклист §8.
- Менеджмент: §1, §2, §6 + итоговый verdict.
