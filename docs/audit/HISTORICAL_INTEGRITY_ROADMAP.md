# Historical Integrity Roadmap — SyncServer

**Дата:** 2026-07-31
**Назначение:** эшелонированный план укрепления исторической целостности
SyncServer. Каждый этап предполагает ADR + TZ перед началом работ (согласно
`docs/AGENT_TZ_WORKFLOW.md`).

**Режим:** настоящий документ — read-only research. Никаких ADR и TZ здесь не
создаётся. На каждый этап ниже указаны **возможные** ADR и TZ; их
составление рекомендуется отдельной итерацией после обсуждения с пользователем.

**Связь:** подробные риски — `HISTORICAL_RISK_REGISTER.md`; подтверждения
file:line и объяснение — `HISTORICAL_INTEGRITY_AUDIT.md`; диагностики —
`SEASON_REPORT_READINESS.md`; потоки — `HISTORICAL_DATA_FLOW.md`.

---

## 0. Общая карта

```text
            СРОЧНО                  ДО ЗАКРЫТИЯ СЕЗОНА                ПОСЛЕ СЕЗОНА                 ДОЛГОСРОЧНО
   ┌─────────────────────────┐   ┌────────────────────────┐   ┌────────────────────────┐   ┌────────────────────────┐
   │ Этап A                  │   │ Этап B                 │   │ Этап C                 │   │ Этап D                 │   │ Этап E                 │
   │ Страховочные меры без   │   │ Укрепление до сезонной │   │ Immutable original     │   │ Report snapshots       │   │ Возможный модульный    │
   │ изменения доменной      │   │ отчётности             │   │ facts + canonical       │   │ и period closing       │   │ рефакторинг            │
   │ модели                  │   │                        │   │ projections             │   │                        │   │ (event sourcing?)      │
   └─────────────────────────┘   └────────────────────────┘   └────────────────────────┘   └────────────────────────┘
   ~ 5–10 дней                 ~ 10–25 дней                  ~ 1–2 месяца                  ~ 1 квартал                   обозначен, не выполняется
```

Каждый этап **дополняет** предыдущие — отменять можно, но не расширять вниз.

---

## 1. Этап A — срочные страховочные меры без изменения доменной модели

> Цель: остановить «несанкционированные back-door» изменениями истории
> и заполнить критичные дыры в audit. Не меняет доменную модель,
> добавляет только guard / CHECK / дополнительный audit_event.

### 1.1 Что входит

| # | Действие | Риск | Файл(ы) |
|---|----------|------|---------|
| A-1 | Запретить `update_operation_effective_at` для `status='submitted'`. Только `'draft'` и `'cancelled'` (только undated confirm). | R-01 | `app/services/operations_workflow_policy.py` (новый guard); `app/api/routes_operations.py:261-290` (route-level) |
| A-2 | `restore_operation` пишет `audit_event('operation.restore', summary, changes={previous_version, restored_by, ...})` | R-03, R-12 | `app/services/operations_service.py:2778-2793` |
| A-3 | `soft_delete_item/category/unit` пишет audit_event с snapshot_before/after | R-04 | `app/services/catalog_admin_service.py:421-459` |
| A-4 | В `accept_operation_lines` для каждой per-line accept/mark_lost пишется audit_event('operation.line_accepted'/'mark_lost') с qty_delta | R-06 (observability) | `app/services/operations_service.py:2269-2406` |
| A-5 | `audit_item_effects.effective_at NOT NULL DEFAULT server_now()`; backfill UPDATE FROM operations WHERE operation_id IS NOT NULL | R-05 | новая миграция alembic |
| A-6 | Endpoint `GET /reports/item-movement` принимает `?exclude_system_effects=true` (filter `is_system_generated=False`); default true | R-21, R-38 | `app/repos/reports_repo.py`, `app/api/routes_reports.py` |
| A-7 | CLI `make integrity-check` (по запросам из `HISTORICAL_RISK_REGISTER.md §5`) | R-11, R-26 | `SyncServer/scripts/integrity_check.py` + Makefile target |

**Принцип:** всё это — точечные доработки в существующих файлах. Никакого
event-sourcing, никаких новых таблиц (кроме A-5, где миграция добавляет
только колонку `effective_at`).

### 1.2 Что НЕ входит (намеренно отложено)

- merge preview / unmerge (Этап C)
- new table `source_documents` (Этап C)
- period close (Этап D)

### 1.3 Кандидаты на ADR/TZ (после обсуждения с пользователем)

> Не создавать ADR/TZ автоматически. Только при согласовании пользователя.

- `ADR-0XXX: historical-integrity-hardening-stage-a.md`
  кратко описывает принцип «только-страховки-без-доменных-изменений».
- `TZ-HISTORICAL_INTEGRITY_STAGE_A.md` с чек-листом по уровням тестов
  (static, unit, integration, stand, UI).

### 1.4 Метрика успеха этапа A

- integrity-check запускается, diff = 0 (или явный список объяснимых дельт).
- (Q1) запрос возвращает 0 строк.
- audit API имеет `operation.restore` события в `audit_events`.
- `soft_delete_*` события имеют `snapshot_before/after`.
- `reports?exclude_system_effects=true` корректно фильтрует merge/cancel.

---

## 2. Этап B — укрепление до сезонной отчётности

> Цель: сделать исторический режим отчётности полноценным; выявить
> потерянные audit gaps; внести **минимальные** изменения доменной модели,
> не ломающие существующие операции.

### 2.1 Что входит

| # | Действие | Риск | Файл(ы) / миграция |
|---|----------|------|--------------------|
| B-1 | `OperationLine.original_item_id` (nullable) + backfill `=item_id` при миграции; merge_items пишет туда `source_item_id` | R-02 | новая миграция; `app/services/catalog_admin_service.py:678-684` |
| B-2 | merge_items в UoW создаёт per-line `audit_event_resources(relation='reassigned', snapshot_before={item_id: source}, snapshot_after={item_id: target})` для каждой затронутой строки | R-20, R-02 | `app/services/catalog_admin_service.py` |
| B-3 | Endpoint `GET /admin/items/{id}/merge-preview`: возвращает planned op_lines, balances, conflicts | R-08 | `app/api/routes_catalog_admin.py`; `app/services/catalog_admin_service.py` (новый method) |
| B-4 | Service guard: `merge_items` отвергает target с `merged_into_id != null` или обход цепочки | R-32 | `app/services/catalog_admin_service.py:511-746` |
| B-5 | Item.update/Category.update/Unit.update — snapshot_before/after в audit_event_resources | R-19 | `app/services/catalog_admin_service.py` |
| B-6 | Storekeeper-visible read endpoint `GET /audit/visible?entity_type=item&entity_id=X` (фильтр по своим сайтам + entity_type/item) | R-14 | `app/api/routes_admin_audit.py` |
| B-7 | Constraint (CHECK/EXCLUDE или unique partial index) на запрет update effective_at у submitted через DB-side trigger или блокирующий partial index `effective_at_immutable_for_submitted` | R-01 (DB обвязка) | новая миграция |
| B-8 | `make backup-test-restore` команда: восстанавливает дамп во временную схему, прогоняет integrity-check | R-17 | Makefile |

### 2.2 Что НЕ входит

- Полная коррекция V2..V8 (Этап C)
- unmerge flow (Этап C)

### 2.3 Кандидаты на ADR/TZ

- `ADR-0XXX: historical-integrity-hardening-stage-b.md` —
  что меняется в доменной модели.
- `TZ-HISTORICAL_INTEGRITY_STAGE_B_MERGE.md` — merge preview +
  per-line reassigned event.
- `TZ-HISTORICAL_INTEGRITY_STAGE_B_AUDIT.md` — storekeeper-visible audit.

### 2.4 Метрика успеха этапа B

- Каждое merge оставляет 1+N+K строк `audit_event_resources` (merge_source, merge_target, generated×N, reassigned×K).
- Item.update events всегда имеют `snapshot_before/after`.
- `merge-preview` endpoint возвращает согласованный с фактическим merge план.
- storekeeper может посмотреть историю своих ТМЦ без root.
- (Q7) merge chain depth всегда ≤16, (Q3) reassigned_count > 0 для любого merge.
- backdate effective_at через DB не проходит.

---

## 3. Этап C — Immutable original facts + canonical projections

> Цель: разделить «как было записано» (immutable) и «как сейчас
> канонически выглядит» (current projection). Это может включать
> отдельную таблицу `merge_line_map`, расширенные snapshot-поля,
> новую таблицу `source_documents` для OCR/PDF.

### 3.1 Что входит

| # | Действие | Риск |
|---|----------|------|
| C-1 | Таблица `merge_line_map (merge_event_id, operation_line_id, original_item_id, new_item_id)` — заполняется в merge_items; readable через audit_api | R-02, R-20 |
| C-2 | Расширить correction V1 до V2..V8 (EXPENSE / MOVE / ADJUSTMENT / ISSUE) | R-13, R-24 |
| C-3 | `source_documents` таблица + storage (s3-совместимый или volume) — хранение PDF/CSV/JSON, file_hash (SHA256), parser_version, page_number, line_number_in_document | R-07, R-10, R-40 |
| C-4 | `unmerge` endpoint с policy: target имеет только этот source как последний merge, иначе отказ. Только root. | R-09 |
| C-5 | Snapshot-before при `accept_operation_lines` per-line (action.type = accept/mark_lost) | R-06 (полная версия) |
| C-6 | Effective_at можно вернуть на draft, нельзя на submitted | R-01 (полная защита) |
| C-7 | Расширить source_client enum + actor_kind для LLM | R-23, R-35 |

### 3.2 Что НЕ входит

- Полный event sourcing (Этап E).
- Period close (Этап D).

### 3.3 Кандидаты на ADR/TZ

- `ADR-0XXX: immutable-original-facts-and-canonical-projections.md`
  (описывает разделение).
- `TZ-MERGE_LINE_MAP_AND_SNAPSHOTS.md`
- `TZ-SOURCE_DOCUMENTS_PERSISTENCE.md`
- `TZ-UNMERGE_FLOW.md`
- `TZ-CORRECTION_SCOPE_EXPANSION_V2_V8.md`

### 3.4 Метрика успеха этапа C

- Отчёт «исторический» (по snapshot at submit) и «канонический» (по
  текущему item_id или merge chain) дают согласованные числа после
  слияния.
- Source-document можно найти через `OperationLine.source_doc_line_id`
  → `source_documents.id` → `source_documents.stored_path`.
- unmerge транзакционно возвращает строки в нужное состояние, балансы и
  эффекты согласованы.
- correction применим к EXPENSE/MOVE/ADJUSTMENT/ISSUE (включая acceptance).

---

## 4. Этап D — Report snapshots и period closing

> Цель: формально зафиксировать сезонные результаты, чтобы можно было
> точно ответить «что было X числа» спустя любое время.

### 4.1 Что входит

| # | Действие | Риск |
|---|----------|------|
| D-1 | Таблица `periods (id, name, season, open_at, close_at, closed_by, closed_status)` | R-22 |
| D-2 | Таблица `report_snapshots (id, period_id, generated_at, generated_by, sql_query_hash, result_hash, payload, algorithm_version)` | R-22 |
| D-3 | Endpoint `POST /reports/seasonal/{period_id}/snapshot` — генерирует и сохраняет hash результата | R-22 |
| D-4 | `close_period` flow: запрет effective_at change и merge для всех operations/effective_at ≤ period.close_at | R-01, R-22 |
| D-5 | Перевод системного фикса отчёта: пред-/пост- интегрити-check требует 0 дельт | R-11, R-22 |
| D-6 | Watermark column в audit_event с периодом | R-22 |

### 4.2 Что НЕ входит

- Реализация hard-lock (Этап C/D через compensating-only).
- Полноценный data warehouse.

### 4.3 Кандидаты на ADR/TZ

- `ADR-0XXX: report-snapshots-and-period-closing.md`
- `TZ-REPORT_SNAPSHOTS.md`
- `TZ-PERIOD_CLOSE_FLOW.md`

### 4.4 Метрика успеха этапа D

- Каждый сезонный отчёт имеет snapshot с SHA256.
- Закрытый период нельзя откорректировать без compensating ADJUSTMENT.
- Аудит-trail «что было закрыто» восстанавливается через snapshot.

---

## 5. Этап E — Возможный модульный рефакторинг (обозначить, не выполнять)

> Это намеренно расплывчатый пункт. Audit модульности — отдельная задача,
> в этот research не входит.

### 5.1 Возможные направления (высокоуровневые)

| Тема | Описание | Зачем |
|------|----------|-------|
| Переход на event sourcing | Все мутации операций через append-only events в одной таблице | Устраняет необходимость `audit_item_effects` отдельно от операций |
| Snapshot стратегия (как CRM-проекции) | Snapshot таблица `item_current_view` пересчитываемая периодически | Упрощает read API |
| CQRS для отчётов | Write side и read side разнесены на уровне БД | Масштабирование, frozen read model |
| Рефакторинг services → commands + queries | Разделение write-side и read-side services | Лучшая тестируемость, меньше shared state в UoW |

### 5.2 Что нужно ДО начала этапа E

- ADR по целесообразности.
- Cost-benefit анализ (текущий код ~9000 строк pythonic services).
- Доказательство, что текущая модель не справится с ростом нагрузки.

### 5.3 Что НЕ нужно делать

- Не начинать «на всякий случай».
- Не делать совместно с текущим сезоном.

---

## 6. Зависимости между этапами

```text
       ┌──────┐
       │  A   │ (страховки)
       └──┬───┘
          │
          ▼
       ┌──────┐
       │  B   │ (доменные доработки минимум)
       └──┬───┘
          │
          ▼
       ┌──────┐
       │  C   │ (originals + canonical projections)
       └──┬───┘
          │
          ▼
       ┌──────┐
       │  D   │ (period close + snapshots)
       └──┬───┘
          │
          ▼
       ┌──────┐
       │  E   │ (только если нужен event sourcing или
       └──────┘  рефакторинг modules)
```

Этапы A → B → C → D — линейно. E — отдельный.

---

## 7. Где взять детали для каждого этапа

| Этап | Где подробности |
|------|-----------------|
| A | `HISTORICAL_RISK_REGISTER.md` (P0-таблица). Тесты — начать с unit-тестов для policy guard и audit_helper. |
| B | `HISTORICAL_INTEGRITY_AUDIT.md` §4.1, §4.4, §6.3 + risk R-02/R-19/R-14. |
| C | Audit §4.5 (merge conflicts), §5 (source-doc), §7.2. |
| D | `HISTORICAL_INTEGRITY_AUDIT.md` §9 (Закрытие периода). |
| E | Отдельный архитектурный review — не входит в данный аудит. |

---

## 8. Чем отличается от рефакторинга (отказ от не-нужного)

Все этапы A-D делают точечные доработки существующего кода или
добавление append-only таблиц. Они НЕ требуют:

- Event sourcing целиком.
- Изменения write-path для существующих операций.
- Переписывания services/repos/UI.

То есть можно безопасно внедрять в любую ветку `dev`, тестировать на
dev-стенде, катить через миграции alembic.

---

## 9. Сводка требующихся ADR/TZ (после согласования)

| Документ | Этап | Назначение |
|----------|------|------------|
| `ADR-0026` (или `0026`) | A | «historical-integrity stage-a страховки» |
| `TZ-HIST_INTEGRITY_STAGE_A` | A | Чек-лист реализации страховок |
| `ADR-0027` | B | «historical-integrity stage-B merge preview + snapshots» |
| `TZ-MERGE_PREVIEW_AND_PER_LINE_AUDIT` | B | Per-line reassigned events + preview endpoint |
| `TZ-STOREKEEPER_AUDIT_VIEW` | B | Audit endpoint для роли storekeeper |
| `ADR-0028` | C | «immutable originals + canonical projections» |
| `TZ-MERGE_LINE_MAP` | C | Долговременная персистентность line_map |
| `TZ-SOURCE_DOCUMENTS_TABLE` | C | source_documents + storage |
| `TZ-UNMERGE` | C | Endpoint для отмены merge |
| `TZ-CORRECTION_SCOPE_EXPANSION` | C | V2..V8 phases |
| `ADR-0029` | D | «report snapshots + period closing» |
| `TZ-REPORT_SNAPSHOTS` | D | Snapshot таблица + endpoint |
| `TZ-PERIOD_CLOSE` | D | Close flow + watermark |

Каждый ADR/TZ должен быть согласован с пользователем до выпуска.
Архитектор сейчас не имеет полномочий их выпускать.

---

## 10. Метрики общей готовности

Состояние **до** этапов A-D:
- P0 рисков: 12 (см. `HISTORICAL_RISK_REGISTER.md`).
- Полнота исторического отчёта: ~70% (snapshots есть, но не по всем
  операциям; merge плоский; нет source files).
- Готовность к сезонному отчёту: ❌ (требует ручных проверок Q1..Q7).

После **этапа A**:
- P0 закрыты: R-01, R-03, R-04, R-05 (через backfill), R-06 (через
  per-line audit_event), R-26 (через CLI).
- Полнота: ~80%.
- Готовность: ⚠ (некоторые условные сноски обязательны, integrity-check manual).

После **этапа B**:
- P0 закрыты: R-02 (через original_item_id + per-line resource),
  R-19 (через snapshot_before/after), R-14 (через storekeeper API).
- Полнота: ~90%.
- Готовность: ✅ для большинства отчётов, ⚠ для source-document.

После **этапа C**:
- P0 закрыты: R-07, R-09, R-10, R-40 (новые таблицы).
- Полнота: ~95%.

После **этапа D**:
- P0 закрыты: R-22.
- Полнота: ~98%.

---

## 11. Что остаётся «как есть» (после всех этапов)

- `audit_item_effects.operation_id SET NULL` (R-25, P2) — не критично,
  пока soft-delete is the only operation removal path.
- `display_number` non-idempotency (R-31, P2).
- `Item.update / Category.update` пока без DB-enforced immutability
  (R-19 закрывает observability, но не механизм).

После этапа D останутся P2 и P3 риски — это **нормально**.
