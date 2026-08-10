# Historical Integrity Audit — SyncServer

**Дата проведения:** 2026-07-31
**Объект:** `SyncServer/` (FastAPI + PostgreSQL 15)
**Канон требований:** `../Functional and WorkLogik.md`
**Режим:** read-only research. Никаких правок кода, миграций, тестов, конфигов.
**Автор:** Architect Agent (architecture mode)

---

## 0. Как читать этот документ

Все наблюдения собраны из реальных файлов и строк. Каждая находка помечена одной из меток:

| Метка | Значение |
|-------|----------|
| **`[FACT]`** | Подтверждено прямо файлом/строкой в коде или миграции. |
| **`[INFERRED]`** | Логически следует из связного кода/схемы, но требует проверки runtime. |
| **`[GAP]`** | Требует решения вне кода (продакшен-данные, инфраструктура, политика). |

Все ссылки на код даны в формате `path:line` или `path:line-range`.
Серьёзные риски выделены в `[[RISK ID-X]]` и подробно расписаны в
`docs/audit/HISTORICAL_RISK_REGISTER.md`.

---

## 1. Архитектура истории — что хранит SyncServer и в чём он считается

SyncServer — не event-sourcing. Это классический CRUD с ограниченным добавлением
audit-журнала (`audit_events` + `audit_event_resources` + `audit_item_effects`)
и append-only immutable `operation_revisions` для коррекций (V1, см. ARCH). Источником
истины по **состоянию склада** остаётся проекционная таблица `balances`;
`operations` хранит намерение, но не доказательство.

```text
                     ┌─────────────────────────────────────────────────┐
                     │       SyncServer: персистентные слои            │
                     └─────────────────────────────────────────────────┘

  ┌──────────────────────────────────────────────────────────────────┐
  │ Append-only / immutable (после наступления события)              │
  ├──────────────────────────────────────────────────────────────────┤
  │  operations.id                (PK, UUID)        created          │
  │  operation_revisions          (N+1 revision per submitted op)     │
  │  operation_revision_lines     immutable per revision              │
  │  audit_events        (insert-only, RESTRICT при update/delete)    │
  │  audit_event_resources                                   (RESTRICT)│
  │  audit_item_effects   (insert-only, RESTRICT на event, item, subj)│
  │  documents            (через supersedes chain, не удаляются)      │
  └──────────────────────────────────────────────────────────────────┘

  ┌──────────────────────────────────────────────────────────────────┐
  │ Projection / mutable state                                        │
  ├──────────────────────────────────────────────────────────────────┤
  │  operations.effective_at / status / cancelled_*      UPDATE       │
  │  operation_lines (current mutable projection)        UPDATE       │
  │  balances         (проекция, derived from history)    UPSERT      │
  │  items / categories / units / issue_objects          UPDATE       │
  └──────────────────────────────────────────────────────────────────┘
```

### 1.1 Реляционные источники истины (что на что опирается)

| Объект | Источник истины | Зависит от |
|--------|-----------------|------------|
| Складской остаток сейчас | `balances` | производный от операций + effect-журнала |
| Движение за период | `operations` ∪ `operation_lines` (submitted) | нельзя получить из `audit_item_effects` без переписывания |
| Состав поданной операции «как есть» | только `operation_revisions` + `operation_revision_lines` | `operation_lines` мутируют при correction |
| Что происходило с ТМЦ | `items` (текущая правда) + `audit_event_resources` (было/стало) + `merge_to_id` | merge-перенаправление потеряно из строк, но есть в `audit_event_resources` |
| Кто менял что | `audit_events.actor_user_id` + `audit_event_resources` | неполное покрытие (см. §6.7) |
| Деривации остатков на дату | `audit_item_effects.created_at` ≠ `operations.effective_at` (см. §3.5) |

### 1.2 append-only и immutable — что подтверждено

- `audit_events.id INT AUTOINCREMENT`, FK на сам себя через `parent_event_id`,
  нет SQL DDL для `UPDATE`/`DELETE` строк (подтверждение — нет методов в
  `AuditEventsRepo` кроме `insert`/`list_events`/`get_by_id*`).
  См. `app/repos/audit_events_repo.py:32-218`.
- `audit_item_effects` FK policy:
  `audit_event_id RESTRICT`, `operation_id SET NULL`, `inventory_subject_id RESTRICT`,
  `item_id RESTRICT`, `site_id SET NULL`, `caused_by_event_id RESTRICT`
  (`app/models/audit_item_effect.py:38-44`).
- `operation_revisions` / `operation_revision_lines` — `append-only` per
  `docs/adr`/`ARCHITECTURE.md` (INV-C1, INV-C6); но **прямого CHECK-ограничения
  на уровне DDL нет** ([INFERRED]; см. §3.4 о practical immutability).
- `audit_event_resources` — `audit_event_id` FK RESTRICT, **нет FK на сам ресурс**
  (by design, `app/models/audit_event_resource.py:24-29`). Связь живёт «по строке
  ресурса», даже если доменная сущность удалена.

### 1.3 Мутируемые проекции

- `operations` — допускает UPDATE `effective_at`, `status`, `cancelled_*`,
  `deleted_*`, `correction_count`, `current_revision_id`. См. `app/models/operation.py:84-214`.
- `operation_lines` — мутируют полностью. Источник «что сейчас на экране». См.
  `app/models/operation.py:282-416`. **Однако** строки после submit не должны
  меняться пользователем: их меняет только:
  1. correction flow (`rebuild_operation_lines`, см. `app/repos/operations_repo.py:654-722`);
  2. merge_items (`UPDATE operation_lines SET item_id=target WHERE item_id=source`,
     `app/services/catalog_admin_service.py:678-684`).
- `balances` — UPSERT по `(site_id, inventory_subject_id)` (`app/repos/balances_repo.py:32-70`).
- `items` / `categories` / `units` / `issue_objects` / `sites` —
  full UPDATE с soft-delete (`deleted_at`, `is_active`) и merge (`merged_into_id`).

---

## 2. Карта write-path (append-only и мутируемые)

### 2.1 Жизненный цикл операции (draft → submit → effects)

```
create_operation
  └── operations.id (UUID, draft)
  └── operation_lines (catalog snapshots уже записаны; creation_source='manual')
  └── draft document (если тип поддерживается)   [FACT app/services/operations_service.py:1110-1128]
  └── audit_event: 'operation.create'            [FACT app/services/operations_service.py:1130-1143]

submit_operation   [FACT app/services/operations_service.py:1881-2266]
  ├── Lock на operations row, state='draft', expected_version check
  ├── _materialize_deferred_temporary_lines → catalog Items (auto-create, requires_review=True)
  ├── _freeze_catalog_snapshot → перезапись snapshots в operation_lines
  │    (только для creation_source in ('source_document','manual'))
  ├── _check_submit_balance_sufficiency: aggregates по (site_id, subject_id),
  │    локирует balances, проверяет InsufficientStockError
  ├── effects captured в balance_effects_capture[]
  ├── operations.status='submitted', submitted_at, submitted_by
  ├── OperationRevision (N+1 = revision_number = max(...)+1) + lines
  │    [FACT app/services/operations_service.py:2121-2155]   ← revision_number не
  │    обязательно 0/последовательный: берётся max+1, см. §6.5
  ├── operation_lines.current_revision_id = new_revision.id
  ├── DocumentService.generate_from_operation (auto_finalize, draft waybill → void)
  ├── audit_event: 'operation.submit'  [FACT app/services/operations_service.py:2199-2219]
  ├── audit_event_resources: catalog_resolved для каждой строки (если был change)
  └── OperationsService._write_captured_effects → audit_item_effects rows
       [FACT app/services/operations_service.py:2246-2253]
```

### 2.2 Accept / Lost / Resolve

```
accept_operation_lines     [FACT app/services/operations_service.py:2269-2406]
  ├── требует operation.status='submitted' + acceptance_required
  ├── для каждой строки: pending_accept bal → balance (+), lost → lost_register
  │    operation_lines.accepted_qty, lost_qty  ←  мутация OperationLine при accepted
  └── audit_event: 'operation.acceptance_complete' (только когда resolved)

resolve_lost_asset         [app/services/operations_service.py:2409-2476]
  ├── found_to_destination / return_to_source → balances +
  └── 'mark_lost' / 'write_off' → аудит-recipient, балансы не меняются
```

### 2.3 Cancel / Restore / Delete

```
cancel_operation     [FACT app/services/operations_service.py:2511-2775]
  ├── Guard: status != 'cancelled'
  ├── Если submitted — для каждой строки:
  │    ├── RECEIVE acceptance_required → rollback pending/lost/accepted
  │    ├── WRITE_OFF with issue_object → restore issued_register
  │    ├── EXPENSE/WRITE_OFF (warehouse) → balance + qty (capture effect_type='cancel_reversal')
  │    ├── ADJUSTMENT → balance - qty (cancel_reversal)
  │    ├── MOVE: -source +destination (или restore pending+accepted),
  │    │    с ОБЯЗАТЕЛЬНОЙ проверкой sufficient_destination_balance при
  │    │    MOVE без acceptance_required [FACT app/services/operations_service.py:2662-2691]
  │    └── ISSUE / ISSUE_RETURN → warehouse + qty, issued ∓qty
  ├── operations.status='cancelled', cancelled_*, version+1
  ├── _delete_temporary_items_of_operation (soft-delete для review items)
  └── audit_event: 'operation.cancel' parent_event_id=opts

restore_operation    [FACT app/services/operations_service.py:2778-2793]
  ├── Guard: status='cancelled'
  ├── operations: status='draft', cleared cancelled_*, version+1
  └── ⚠ НЕ пишет audit_event (см. §6.2)
  └── ⚠ НЕ создаёт OperationRevision N (т.к. drafts строки mutation allowed)

delete_operation     [FACT app/services/operations_service.py:2479-2508]
  ├── Guard: status='cancelled' (см. §6.2 о последствиях)
  ├── soft_delete: deleted_at, deleted_by
  └── audit_event: 'operation.delete'
```

### 2.4 Correction flow (V1, RECEIVE without acceptance_required)

```
begin_correction                  [app/services/corrections_service.py:90-159]
  ├── operation.status='submitted' required
  ├── Operates on OperationRevision N (current) baseline
  ├── Clones baseline lines → OperationCorrection (status='draft') + lines
  └── partial-unique index (одна active draft per operation)

update_correction_put/add/remove  [app/services/corrections_service.py:162-298]
  └── оптимистично version-checked; 'correction_kind' ЗАПРЕЩЁН от клиента

submit_correction                 [FACT app/services/corrections_service.py:415-700]
  ├── Lock: Correction → Operation → inventory_subjects (ASC) → balances → docs
  ├── _compute_diff серверный: unchanged / metadata / quantity / item_replaced / added / removed
  ├── _validate_deltas (per-debit проверки баланса)
  ├── Создание OperationRevision N+1 (immutable)            ← writes happen here
  ├── rebuild_operation_lines (UPDATE по line_uuid либо INSERT для added)   [FACT app/repos/operations_repo.py:654-722]
  ├── operation.current_revision_id = new_revision.id
  ├── document generation from revision_id, supersedes old doc
  └── audit_event: 'operation.correction.applied' + 'document.revision_created' + 'document.superseded'
       _write_captured_effects по audit_event_id

abandon_correction                [app/services/corrections_service.py:~393-412]
  └── audit_event: 'operation.correction.abandoned'
```

### 2.5 Catalog: create / update / merge / soft-delete

```
create_item / create_category / create_unit
  └── FK проверки
  └── audit_event: 'item.create' / 'category.create' / 'unit.create'  [FACT app/services/catalog_admin_service.py по тексту]

update_item / update_category / update_unit
  └── UPDATE домена (name, sku, unit, category, hashtags, ...)
  └── audit_event: 'item.update' / 'category.update' / 'unit.update'
  └── ⚠ НЕ before/after snapshot В Item/Category обновлениях, только в event.changes JSONB

delete_item / delete_category / delete_unit
  ├── Guard: не active (или requires_review)
  └── soft_delete_*: deleted_at, deleted_by  [FACT app/repos/catalog_repo.py:467-540]
  └── ⚠ НЕ пишет audit_event (см. §6.2)

merge_items            [FACT app/services/catalog_admin_service.py:511-746]
  ├── parent audit_event: 'item.merge'
  ├── для каждого site с non-zero balance на source_subject:
  │    ├── ADJUSTMENT write-off (system, origin='system', system_reason='item_merge')
  │    │    → effect_type='merge_write_off'
  │    └── ADJUSTMENT receipt в target_subject  → effect_type='merge_receipt'
  │         UPD OperationLine.item_id: source → target  ⚠ МУТАЦИЯ
  │              [FACT app/services/catalog_admin_service.py:678-684]
  ├── source.merged_into_id = target
  ├── source.is_active = False
  ├── archive source inventory_subject
  ├── audit_event_resources: merge_source/merge_target/generated×N
  └── ⚠ НЕТ merge plan, preview, dry-run, line_map, original_item_id  (см. §6.4)

merge_categories       [catalog_admin_service.py:748-820] — примерно та же логика
merge_issue_objects    [catalog_admin_service.py:по контексту]
temporary resolution   [app/services/temporary_items_resolution_service.py]
```

### 2.6 Source-document вход

```
POST /operations/from-source-document   [FACT app/api/routes_operations.py:175-206]
  └── payload: SourceDocumentOperationCreate (extra='forbid')
  └── idempotency по (source_ref, creation_source='source_document', created_by)
  └── item_id обязателен в каждой строке
  └── НЕТ реальных source_documents, файлов, OCR данных, hash_file, page_number,
      line_number_in_document — см. §5 (VI область)
```

### 2.7 Audit

См. §6. Главные места: `app/services/audit_helper.py:13-74`,
`app/repos/audit_events_repo.py:32-307`. `record_audit_event` пишет событие
внутри существующего UoW; commit происходит на `__aexit__` контекст-менеджера
UoW (`app/services/uow.py:75-82`).

---

## 3. Балансы и effect-журнал (III область)

### 3.1 Балансы — проекция, не источник истины

- `balances` — UPSERT по (site_id, inventory_subject_id), `qty` хранится как DECIMAL(18,3).
  Подтверждение: `app/repos/balances_repo.py:23-70`. Нет триггеров, нет version,
  нет audit_record_of_why_this_qty.
- Изменение `balances.qty` всегда сопровождается записью `audit_item_effect` в том же UoW
  (`app/services/operations_service.py:2086-2226`, `_write_captured_effects`).
- **Можно ли пересчитать balances из history?** `[INFERRED]`
  Полный пересчёт из `audit_item_effects` — да, при условии что каждый effect
  имеет `is_system_generated` правильно проставлен. Однако:
  - при cancel INSERT-ятся **новые** effect'ы с `effect_type='cancel_reversal'`, но
    первоначальный effect (например, `receipt`) **не помечается как отменённый**.
    Это означает, что «сумма всех effect_type='receipt'» ≠ «итоговый баланс»;
    нужен более сложный расчёт с учётом cancel_reversal/merge_*;
  - `_ensure_line_inventory_subject` добавляет subject в строку во время submit, что
    исторически для effection может пропустить `operation_id` для первой строки
    (см. `app/services/operations_service.py:1957-1958`).

### 3.2 Инвариант и инвариантная проверка

Ожидаемая формула (из `Functional and WorkLogik.md:42-44` и баланс-чеков):

```text
opening balance
+ receipts (RECEIVE не acceptance_required)
+ RECEIVE accepted after acceptance
+ incoming moves (MOVE in)
+ positive ADJUSTMENT
- issues (EXPENSE)
- write-offs (WRITE_OFF)
- outgoing moves (MOVE out)
- negative ADJUSTMENT
= closing balance
```

Подтверждённые проверки:

| Тип защиты | Где | Что покрывает |
|------------|-----|---------------|
| `InsufficientStockError` | `app/services/operations_service.py:319-430` (`_check_submit_balance_sufficiency`) | submit, общий случай: insufficient balance → 409 |
| `_ensure_sufficient_balance` | `app/services/operations_service.py:99-114` | submit отдельных decrements |
| Mismatched correction: `_validate_deltas` | `app/services/corrections_service.py:~497` | correction: проверка delta против balances |
| Недостаточно destination при MOVE rollback | `app/services/operations_service.py:2662-2671` | cancel without acceptance_required |

**Что НЕ покрыто:**

1. Проверка того, что `balances` = (сумма всех `audit_item_effects`,
   с учётом cancel_reversal). Такой integrity check отсутствует в репозитории
   ([GAP], см. §6.7).
2. Проверка того, что каждая submitted операция имеет ненулевое количество
   `audit_item_effects`.
3. Проверка consistency между `operations.effective_at` и `audit_item_effects.created_at`
   (см. §3.5).

### 3.3 Deduplication / idempotency эффектов

- Web idempotency: `client_request_id` + `client_request_hash` на операциях
  (partial unique index ix_operations_client_request_id). См.
  `app/models/operation.py:271-279`.
- Source-document idempotency: `(source_ref, creation_source, created_by)`
  ([FACT app/services/operations_service.py:1162-1187]).
- Correction idempotency: `idempotency_key` на `operation_corrections`.
  См. `app/services/corrections_service.py:432-452`.
- **Отсутствует** idempotency на повторный POST к `/operations/{id}/submit` с одним и тем же
  `(operation_id, user_id)`: строка 307-308 в routes включает `expected_version`,
  но идемпотентность не различает «уже submitted» от «новый submit» без version.
  В коде есть балансовые pre-check, но **повторный submit после ошибки**
  теоретически может попытаться начислить effects повторно.
  **Проверить нужно в стенде** [GAP].

### 3.4 Negative-balance защита

- Submit new operation: есть проверка.
- Submit correction: есть `_validate_deltas`.
- **Cancel of operations** (с already reversed effects): если cancel идёт после restore
  — restore обнулил cancelled_at/audit не ведёт — вторая отмена не найдёт
  parent effects для reverse.
- **System adjustment (merge balance transfer)**: написаны буквально как
  `ADJUSTMENT write-off (-qty) + ADJUSTMENT receipt (+qty)` для каждого site
  ([FACT app/services/catalog_admin_service.py:600-672]). Защиты на
  `balance < |qty|` нет — но если source balance положительный, write-off у
  него заберёт именно столько, сколько есть. Если source balance отрицательный
  (что не должно случаться, но…), merge его всё равно заберёт (см. §6.4).

### 3.5 created_at vs effective_at — критический разрыв

- `audit_item_effects.created_at` — server `now()` при INSERT (миграция 0026).
- `operations.effective_at` — поле модели, может быть произвольным при создании
  (`operations_service.py:983` — `effective_at = operation_data.effective_at or datetime.now(UTC)`).
- Отчёт `list_item_movement` использует
  `func.coalesce(Operation.effective_at, Operation.created_at)` как `operation_at`
  ([FACT app/repos/reports_repo.py:31]).
- **Это означает**: при `effective_at = май 2026`, но фактический submit
  в июле 2026, `audit_item_effects` появится в июле, а отчёт (по `operation_at`)
  поместит движение в май.
  В последствии `date_from/date_to` фильтры по `audit_item_effects.created_at`
  дадут **разные** результаты по сравнению с `operation_at`-фильтром. Это
  критично для сезонного отчёта. [FACT, см. §6.3]

### 3.6 effective_at у submitted операции можно менять задним числом

`PATCH /operations/{id}/effective-at` использует единственный guard
`OperationsWorkflowPolicy.require_not_cancelled_for_effective_at_change`
([FACT app/services/operations_workflow_policy.py:15-20]). Никаких проверок
на `status='submitted'` нет. Любой пользователь с правами edit (см.
`OperationsPolicy.require_operation_effective_at_permission`) может
перенести дату back-into past.

`update_operation_effective_at` пишет audit_event `operation.update` с
`changes.diff.effective_at.{old, new}`, но это **никак не создаёт
компенсирующих effect'ов в `audit_item_effects`**. Это означает:

1. Повторная генерация отчёта по `operation_at` даст **другой** набор эффектов.
2. Предыдущие отчёты уже содержат старые positions/categories/etc., но
   новые будут с другой датой без очевидного следа «кто и когда сменил effective_at».

Подробнее [risk ID-01].

### 3.7 Sequence и ordering эффектов

- `audit_item_effects` сортируется по `id` (auto-increment), не по
  `operation.effective_at`. Это хорошо для chronological read, но плохо для
  воспроизведения «закрытия баланса на дату».
- Неттинг-фильтры при отчётах: используется `operation_at`, который
  игнорирует этот внутренний sequence (см. `reports_repo.py:174-178`).

---

## 4. Merge каталога (IV область) — главный риск сезона

### 4.1 Что merge_items делает с operation_lines

`merge_items` — критическая находка сезона.

```python
# app/services/catalog_admin_service.py:678-684
reassign_result = await uow.session.execute(
    sa_update(OperationLine.__table__)
    .where(OperationLine.__table__.c.item_id == source_item_id)
    .values(item_id=target_item_id)
    .returning(OperationLine.__table__.c.id)
)
op_lines_count = len(list(reassign_result)) if reassign_result else 0
```

Это **физический UPDATE** без сохранения оригинального `item_id`, **до**
записи `audit_event_resources` на каждую затронутую строку. Последствия:

1. **Навсегда утрачена** возможность отличить строки исходного item от
   исходно-таргетного в любом query, который читает `OperationLine.item_id`.
2. Только в summary-части `audit_events.changes` пишется
   `op_lines_reassigned_count` — это число, не список.
3. `audit_event_resources` linkится на `merge_source`/`merge_target` Item,
   **не на каждую переназначенную строку**. Карты "id старой строки → её
   предыдущий item_id" не остаётся нигде.
4. Это мутация **уже submitted** строк, что прямо запрещено
   `Functional and WorkLogik.md:58` без отдельной операции.

Подтверждение: [FACT app/services/catalog_admin_service.py:678-684].

### 4.2 Покрытие — что сохраняется

- `items.merged_into_id`, `merged_at`, `merged_by_user_id`, `merge_comment` —
  на source Item.
- `audit_event.parent_event_id` — цепочка merge event → system ADJUSTMENT submit events.
- `audit_item_effects` с `effect_type='merge_write_off'` и `='merge_receipt'`,
  `is_system_generated=True`, `caused_by_event_id` указывает на merge event.
- Документы `Document` для system ADJUSTMENT, но **накладные сами по себе
  не несут информацию о переназначенных строках** (только итоговое
  количество).

### 4.3 Что не сохраняется / потеряно

- `original_item_id` (первоначальный id строки при её создании) — нет нигде.
- `line_map` (map id строки ↔ прежний item_id) — нет.
- per-line `audit_event_resource` с `relation='reassigned'` — нет.
- `merge plan` / `merge preview` — нет (нет endpoint, нет dry-run).
- commit signature / who-finalized-merger — нет (есть только user_id+timestamp).
- unmerge — нет.
- **partial recovery / selective unmerge** — нет.

### 4.4 Цепочка A→B→C

Логика следующая:
- merge B→C создаст system ADJUSTMENT переноса остатков B на C.
- При merge A→B (где B сам уже merged в C):
  - `merge_items` (catalo_admin_service.py:558-563) проверит,
    что target.is_active, а не сам факт merged. Если target (B) — `is_active=False, merged_into_id=C`,
    то merge упадёт с «cannot merge into inactive item».
  - Но если B был unmerged (если бы был механизм), снова активен — нет защиты от
    цикла, кроме MAX_MERGE_DEPTH=16 в `_follow_merge_chain`
    (`app/services/catalog_read_service.py:18`); этот guard срабатывает
    только на стороне read API, не в service.

`[INFERRED]` Окно гонки: если система merge A→B стартует, но обновляет B
на `active=False, merged_into_id=C` в середине — поведение не определено.
Защита — единая транзакция, но всё равно нет cycle-check перед merge.

### 4.5 Конфликты единиц/категорий/атрибутов при merge

`merge_items` не валидирует unit/category/hashtags между source и target:
можно смержить ТМЦ с разными единицами измерения, в результате чего OperationLines
получат противоречивые unit_name_snapshot (старые) vs unit на сегодня (target.unit).
Отчётность по «историческому режиму» это покажет (snapshots), но
«канонический режим» сломается.

### 4.6 Merge категорий, issue objects, временных ТМЦ

- `merge_categories` ([FACT app/services/catalog_admin_service.py:748-820])
  — аналогичная логика: переписывает `merged_into_id` на source, но НЕ
  переписывает `items.category_id` (т.к. работает на уровне справочника).
  После merge категорий у **уже submitted** операций сохранится старое
  snapshot в `category_name_snapshot`, но если кто-то сделает correction
  без `item_replaced`, новое значение снова подтянет текущую категорию target.
- merge_issue_objects и resolution `temporary_item.merge` реализованы в
  `temporary_items_resolution_service.py:39-141` — пишут системные
  ADJUSTMENT с effect_type='temporary_write_off'/'temporary_receipt', а
  переназначение строк — опосредованно через `resolved_item_id` на временной
  записи.

### 4.7 Кто видит историю merge

- Audit endpoint `GET /api/v1/audit/...` доступен только `root` или
  `chief_storekeeper` ([FACT app/api/admin_common.py:18-26,
  app/api/routes_admin_audit.py:14-71]).
- В списках операций cancelled/stale merge-операций не выделены в
  API как подтип (есть event_type='item.merge', но фильтр списочный).
- Storekeeper и observer **не получают** исторического среза по item.

---

## 5. Source documents и OCR (VI область)

### 5.1 Что есть

- Schema `SourceDocumentOperationCreate` ([FACT app/schemas/operation.py:278-380])
  с extra='forbid', обязательными `source_ref`, `source_document_type`,
  опциональным `source_document_date`.
- Поле `creation_source` = `'source_document' | 'manual' | 'system' | 'legacy'`
  ([FACT app/models/operation.py:189-203]).
- Идемпотентность по `source_ref` ([FACT app/services/operations_service.py:1162-1188]).
- Поле `OperationLine.source_item_name`, `source_item_sku`,
  `source_unit_name`, `source_category_name` — снапшоты «от документа»,
  заполняются в строке источника документа, переживают merge.
- alias `CatalogChanges` аудит ([FACT app/services/operations_service.py:2222-2241])
  — пишет `operation_line.canonical_item_id` и `previous_item_id`.

### 5.2 Чего нет

- **Нет таблицы `source_documents`** (нет model, нет alembic миграции).
- **Нет хранения файлов** (нет папки, нет S3, нет `documents_files` table,
  нет `original_filename`, `stored_path`, `mime_type`).
- **Нет `file_hash`**.
- **Нет `ocr_engine_version` / `parser_version`** (только в
  `documents.template_name` / `documents.template_version`).
- **Нет `page_number`, `line_number_in_document`** — info от OCR не
  сохраняется, либо хранится в source_item_*_snapshot как implicit «откуда».
- **Нет re-process / re-import** — чтобы повторить, надо создать новую
  операцию с тем же source_ref (idempotency key).

Это значит: даже если миграционный 0029 ввёл `client_request_hash`,
невозможно:

1. Доказать, из какого PDF/скана родилась строка.
2. Найти все операции, созданные из конкретного файла.
3. Переимпортировать файл заново без дублей.

Подробности: [risk ID-07].

### 5.3 Связь «PDF/накладная → OperationLine»

- Непрямая: `operations.source_ref` (string). Можно запросить
  `GET /operations?source_ref=...`, но это не «документ → строки», а
  «операция по source_ref».

---

## 6. Audit subsystem (VII область)

### 6.1 Что покрыто

- `audit_events` insert-only ([FACT app/repos/audit_events_repo.py:32-218]).
- `audit_event_resources` — `(event, resource, relation)` с before/after
  snapshots ([FACT app/models/audit_event_resource.py:12-49]).
- `audit_item_effects` — granular balance journal, snapshot names и unit_type
  ([FACT app/models/audit_item_effect.py:23-112]).
- `record_audit_event` в одном UoW с доменной мутацией.
- `correlation_id`, `parent_event_id`, `caused_by_event_id` доступны.
- `actor_user_id`, `actor_device_id`, `site_id`, `entity_type`, `entity_id`,
  `summary`, `changes` (JSONB), `source_client` (manual=cli/desktop/web/mobile),
  `actor_username_snapshot`, `external_event_id`.

### 6.2 Что НЕ покрыто — нет audit_event для

| Действие | Где | Подтверждение |
|----------|-----|---------------|
| `soft_delete_item` | `app/services/catalog_admin_service.py:447-459` (`delete_item`) | ❌ нет `record_audit_event` |
| `soft_delete_category` | `app/services/catalog_admin_service.py:434-445` (`delete_category`) | ❌ нет |
| `soft_delete_unit` | `app/services/catalog_admin_service.py:421-432` | ❌ нет |
| `restore_operation` | `app/services/operations_service.py:2778-2793` | ❌ нет |
| `_delete_temporary_items_of_operation` (cancel-time auto-delete) | `app/services/operations_service.py:2795-2870` | ❌ нет (по крайней мере не виден audit_event в коде метода) |
| `set_operation_acceptance_state` (non-final accept partial accept → в_progress) | `app/repos/operations_repo.py:295-316` | ❌ пишется только `operation.acceptance_complete` (resolved) |
| `_upsert_pending`/`_upsert_lost` индивидуальные изменения | внутри submit/accept; effects пишутся, но в `accept` нет per-action audit | ⚠ частично (`operation.acceptance_complete` only) |
| `items.requires_review` при создании через inline | автоматически ставится в `materialize` | ⚠ не выделено как audit_event |

Подтверждение отсутствия audit_event для soft-delete найдено через
перечисление всех `record_audit_event` вызовов: 24 уникальных `event_type=`
([FACT grep по `app/`]). Сводный список см. `HISTORICAL_RISK_REGISTER.md`
в разделе «missing audit events».

### 6.3 before / after snapshots

- `audit_event_resources.snapshot_before` / `snapshot_after` реализованы
  ([FACT app/models/audit_event_resource.py:42-43]) и заполняются для
  item.merge, versioned correction events.
- **Item.update, Category.update, Unit.update** — пишут `event.changes`
  как JSONB (что менять), но без `snapshot_before/after` ресурс-link.
  Невозможно узнать «что было» в Item до изменения, если оно потом снова
  поменяется.
- `operations.effective_at` change (через `/effective-at`) пишет
  audit_event с `changes.diff.{old,new}`, но без snapshot ресурса.
  До изменения audit_event «операция-в-январе» нет.

### 6.4 Доступность аудита для storekeeper

- `require_admin_basic(identity)` — root или chief_storekeeper
  ([FACT app/api/admin_common.py:18-26]).
- `GET /api/v1/audit` — только эти роли
  ([FACT app/api/routes_admin_audit.py:14-71]).
- Простой `storekeeper` и `observer` **не имеют API для аудита**.
  Никакого «история остатков по item», «кто менял», «почему» — нет
  ([GAP], §10).
- Roll-back audit через `audit_event_resources.resource_type='item'` —
  зарезервированная для рутов/главного кладовщика часть.

### 6.5 OperationRevision sequence и idempotency

- `revision_number` = `max(...)+1` ([FACT app/services/operations_service.py:2125]).
  Не начинается с 0, не sequential. Не критично, но мешает «report_snapshot»
  по номеру ревизии.
- OperationRevision создаётся при initial submit (номер N+1) и при correction
  apply. Не создаётся при cancel, restore, активации/деактивации товара.
- `_apply_deltas` при correction — это сама коррекция, не «новая операция».
  audit_item_effects пишутся под `audit_event_id = operation.correction.applied`,
  не под `operation.submit`. Это правильно: цепочка понятна через
  operation_id + audit_event.parent_event_id chain.

### 6.6 Целостность и orphan risks

- `audit_event_resources` — не FK на ресурс, **нет запрета orphan**
  ([FACT app/models/audit_event_resource.py:24-29]). По design.
  Плюс: сохраняется «вход в историю» даже после удаления ресурса.
  Минус: «resource_id может относиться к удалённой сущности» — без enum/allowed
  types нельзя валидировать.
- `audit_events.parent_event_id` имеет FK на `audit_events.event_id`,
  `RESTRICT` ([FACT app/models/audit_event.py:78-82]). Невозможно удалить
  parent event без удаления children → практически невозможно редактировать.
- `audit_item_effects.operation_id` SET NULL — operation может быть
  hard-deleted; effect сохраняется с `operation_id=NULL`. Это означает
  что любая отчётность «по operation» сломается для удалённых ops.
  Текущий flow делает **soft-delete** операции (только cancelled + потом
  delete, см. §2.3), но если будет hard-delete (через DB-команду) —
  effect потеряет op ref.
- Orphan audit_event без ресурсов возможен, но не критично.

### 6.7 Checks-of-checks — что не покрыто

- `audit_helper.allowed_source_clients = {"web","desktop","mobile","cli"}` —
  остальные источники становятся `'unknown'`. Это защищает от инъекций,
  но **не различает LLM-клиент от пользователя** ([GAP], см. §10).
- `audit_helper.ALLOWED_SOURCE_CLIENTS` присутствует, в коде
  ([FACT app/services/audit_helper.py:9-11]).
- `actor_username_snapshot` сохраняется, но `actor_device_id` не
  отличает клиента от LLM-токена, проксирующего пользовательский запрос.
  Подробнее — см. ADR-0025 + потенциальный будущий ADR.

---

## 7. OperationLines и snapshots (II область)

### 7.1 Snapshot поля

`OperationLine` имеет snapshots:

- `item_name_snapshot`, `item_sku_snapshot`
- `unit_name_snapshot`, `unit_symbol_snapshot`
- `category_name_snapshot`
- `source_item_name`, `source_item_sku`, `source_unit_name`, `source_category_name` — от источника документа

`OperationLine` мутируются через:

- `rebuild_operation_lines` при correction — UPDATE по line_uuid
  ([FACT app/repos/operations_repo.py:678-694]).
- merge_items — UPDATE `item_id = target` (см. §4.1).

### 7.2 Источник snapshots

Snapshot создаётся:

- В `create_operation` — на момент create draft
  ([FACT app/services/operations_service.py:1095-1100]).
- В `update_operation` — на момент update draft
  ([FACT app/services/operations_service.py:1605-1610]).
- В `submit_operation` — `_freeze_catalog_snapshot` для manual/source_document
  ([FACT app/services/operations_service.py:1949-1953]).
- При correction в `rebuild_operation_lines` — copy target state.

Для legacy-операций (creation_source='legacy') `_freeze_catalog_snapshot`
пропускается — snapshots остаются такие, какие были при submit, а
audit_event_resources через C5 report pre-state на момент submit.

### 7.3 Что произойдёт после rename Item / смены unit / merge

- rename Item: snapshot остаётся старый, текущий Item.name — новый.
  В отчётах по `OperationLine.item_name_snapshot` — старые имена,
  в отчётах через join `items` — новые.
- смена item.unit_id: snapshot `unit_name_snapshot` остаётся старый.
  Корректный исторический отчёт.
- merge: `item_id` переписан на target. Snapshot `item_name_snapshot`
  первоначальный (от submit), но `item_id` теперь — target. Если
  source.name != target.name (часто так), snapshot не совпадает с
  текущим item.name — это и есть «исторический» вид.

### 7.4 «Как было записано на дату операции»

- Возможно, если рассматривать OperationLine.item_*_snapshot И
  OperationRevisionLine.item_*_snapshot. Но:
  - OperationLine.item_id переписан при merge → «дата операции» показывает
    target без истории source.
  - OperationRevisionLine.item_id НЕ обновляется при merge (это immutable,
    и `_freeze_catalog_snapshot` не вызывается для merge-операций).
    Так что для построения **«как записано»** по линии операции
    нужно использовать либо `audit_event_resources` chain через merge event,
    либо **новую** проекцию по `(old_item_id, operation_id, transition_at)`.

### 7.5 Найденные UPDATE/DELETE для уже submitted операций

- `merge_items` UPDATE `operation_lines.item_id` после submit
  ([FACT app/services/catalog_admin_service.py:678-684]).
- `rebuild_operation_lines` UPDATE/INSERT/DELETE при correction
  ([FACT app/repos/operations_repo.py:654-722]).
- `update_operation` UPDATE для **draft** (защита в workflow_policy),
  но у него есть ветка `await uow.operations.delete_operation_lines(
  operation_id)` ([FACT app/services/operations_service.py:1511]) —
  удаляет все строки операции без проверки статуса. Защита от статуса
  стоит выше в `update_operation` через `require_draft_for_update`.
- `_materialize_deferred_temporary_lines` для source_document операций
  пропускается (см. операционную логику); manual — выполняется.

---

## 8. Отчётность (VIII область) — формулировка статуса

### 8.1 Что отчёт может показать сейчас

| Отчёт | Источник | Уверенность |
|-------|----------|-------------|
| Текущие остатки по (site, item) | `balances` | OK, кроме случаев drift (см. §3) |
| Текущие остатки на date_from/date_to (фильтр по Operation.created_at) | OK как фильтр | OK |
| Движение за период по `operation_at` (effective_at) | `reports_repo.list_item_movement` (UNION ALL) | OK если effective_at не менялся задним числом |
| Приходы за период | receive_rows в UNION | OK |
| Расходы за период | decrement_rows | OK |
| Списания за период | WRITE_OFF в decrement | OK |
| Перемещения | move_out_rows + move_in_rows | OK (split на два склада) |
| Корректировки | adjustment_rows + effect_type ∈ {merge_write_off, merge_receipt, cancel_reversal} | Частично (см. §8.2) |
| Cancel/Restore | status cancelled → не попадают в list_item_movement; но audit_item_effects хранит cancel_reversal effects | OK через audit_event_resources chain |
| Merge-история ТМЦ | `audit_event_resources[relation='merge_source'/'merge_target']` | OK только через admin-аудит API, не через магазинный report |
| Изменения каталога | `audit_events[event_type IN ('item.create','item.update','item.merge','category.merge',...)]` | OK только через admin-аудит |

### 8.2 Что отчёт НЕ различает достоверно

| Сценарий | Проблема | Воздействие |
|----------|----------|-------------|
| Поздняя приёмка (acceptance через долгое время после submit) | operation.submit в мае, accepted в июле. В отчёте по дате `accepted` `audit_item_effects.created_at` влияет на расчёт «на дату». | Движение, признанное в июле, попадёт в отчёт «с мая», если считать через `operation_at`. |
| Backdating effective_at | `update_operation_effective_at` для submitted | Отчёт переоценится по дате без следа, audit_event пишется только для `update`, без compensation effect. |
| Cascade merge (A→B→C) | `operation_lines.item_id` указывает на текущий canonical; невозможно получить «сколько пришло в январе в A, потом в C» без ручного merge-chain walk | Историческая статистика по A отдельно не существует |
| Cancel → restore → new submit | restore не пишет audit_event; вторая submit пишет новый audit_event 'operation.submit' (с новыми эффектами). Старая cancel_reversal остаётся без parent_cancel_Restore link | Отчёт по дате первой отмены теряется, отчёт по дате restore не имеет журнала. |
| Multiple corrections of same operation | В OperationRevision N+1 → есть revision number, effect может быть модифицирован несколько раз. Каждая correction пишет новый audit_event + effects. | Движения по корректировкам атрибутируются, но отчёт «движение» суммирует delta; revision как audit-step не пропагандируется в report list |
| Временные ТМЦ с active registers | При cancel operation with temp_items → soft-delete auto. Audit нет | Сложно отследить |
| Operations с пустыми lines | БАЛАНС не проверяется на пустые строки | unit-tests не покрывают |

### 8.3 Текущий «исторический» vs «канонический» режим

- **Исторический** через snapshot-поля **не существует как report mode**.
  Reports today always join `items` для актуального имени/category.
  Чтобы получить исторический, нужно писать отдельный endpoint
  или клиент собирает item_name_snapshot из OperationLine/Revision.
- **Канонический** через follow merge_chain (`_follow_merge_chain`
  в catalog_read_service) — есть, но не в reports.
- Для сезонной отчётности «по item_id=X» без merge — прямой join `items`
  вернёт текущее имя; если X — это source устаревшего merge, нужно
  идти по chain или snapshots.

### 8.4 «Кто может увидеть»

Простой storekeeper не видит (см. §6.4) audit API для:
- item.update history
- merge history
- корректировок
- cancel/Restore
- delete

То есть «объяснить остаток» для кладовщика возможно, только если он
сам присутствовал на этих этапах или запросит у chief_storekeeper/root.

---

## 9. Закрытие периода (IX область)

### 9.1 Текущая модель

- `period close`: не существует в коде (нет API, нет таблицы `periods`,
  нет `report_snapshot`/`data_watermark`/etc.).
- `Op effective_at` может двигаться back/forward для submitted операций
  (см. §3.6).
- Подтверждённые «признаки подготовки к сезону»:
  - `display_number` per operation (для human-readable ID)
  - `source_document_type`/`source_ref` в operation
  - накладные (DocumentService) — если тип waybill, draft + finalize
  - `audit_item_effects` с `created_at` (но не привязано к effective_at)

### 9.2 Три уровня закрытия (рекомендуемые варианты)

| Уровень | Что блокирует | Что разрешает | Реализация |
|---------|---------------|---------------|------------|
| **Мягкое** | effective_at change на submitted | Право читать «закрытые» данные | metadata-флаг + view, не hard-stop |
| **Предупреждение** | effective_at change | confirm dialog | Alert в API + DB-level flag |
| **Жёсткое** | effective_at change, cancel, restore, merge изменяющие <D | Compensating ADJUSTMENT operation через correction flow | DB constraint, новый endpoint `/closing/{period}/report` |

Подробности в `HISTORICAL_INTEGRITY_ROADMAP.md` Этап D.

---

## 10. Backup и consistency (X область)

### 10.1 Что есть

- Logical backup: `make backup-db` → `pg_dump`
  ([FACT Makefile:202-205]).
- Restore: `make restore-db FILE=...` ([FACT Makefile:207+]).
- Docker volume `postgres_data` для persistent state.
- Health-checks для postgres, syncserver, warehouse_web ([FACT docker-compose.yml:24-28]).

### 10.2 Чего нет

- **Нет PITR / WAL archive**: postgres image — vanilla `postgres:15-alpine`,
  не сконфигурированы `wal_level`, `archive_mode`, `archive_command`.
  Подтверждение: `docker-compose.yml:18-30`.
- **Нет scheduled backup**: `make backup-db` только manual.
- **Нет off-host backup копий**: локальная `backups/` папка, может быть удалена
  вместо с `docker volume rm`.
- **Нет integrity checks**: ни scheduled, ни по cron, ни по команде.
- **Файлы source-documents не сохраняются** (см. §5).
- **Нет тестовых restore-процедур**: `Makefile.bak.2026-05-20` указывает
  на `makefile.bak`, history есть, но test-runbook отсутствует.

### 10.3 Автоматические checks которые нужны

См. отдельный risk-list в `HISTORICAL_RISK_REGISTER.md` и процедуры в
`SEASON_REPORT_READINESS.md`.

---

## 11. Что ЗАФИКСИРОВАНО как уже сделанное / иммутабельное

Привожу явно, чтобы не вводить в заблуждение:

| Защита | Файл:строка | Что гарантирует |
|--------|-------------|-----------------|
| Operation revision append-only (INV-C1) | комментарии в ARCHITECTURE.md | revision N+1 никогда не изменяется |
| UoW transaction per request | `app/services/uow.py:75-82` | atomic operations |
| Two-phase balance check с lock-ordering | `app/services/operations_service.py:319-430` | avoid-de-deadlock submit |
| Web idempotency client_request_id+hash | `app/models/operation.py:271-279` | дубль POST → та же операция |
| Document supersedes chain | `app/models/document.py:78-87` | накладные N+1 replacement |
| Idempotency key для correction | `app/services/corrections_service.py:432-452` | дубль submit correction → тот же revision |
| Actor provenance in audit | `app/services/audit_helper.py:13-74` | user, device, source_client |
| Append-only effect journal RESTRICT FK | `app/models/audit_item_effect.py:38-44` | эффекты не потеряются |
| Exhaustive role-based guards | `app/api/admin_common.py:18-26` | root/chief_storekeeper/storekeeper/observer |
| Snapshot fields на operation_lines | `app/models/operation.py:332-344` | rename Item без потери |

---

## 12. Сводный verdict (прямые ответы)

> **Вопрос: можно ли сейчас доказуемо получить остаток любого Item на произвольную дату?**

**Условно да**, по `audit_item_effects.created_at` (с учётом cancel_reversal).
**Нет**, по `operations.effective_at` без перерасчёта, потому что:

1. effective_at менялся задним числом (§3.6).
2. effect created_at ≠ operation.effective_at (§3.5).
3. accept-late добавляет effects после submit (§3.5).
4. merge merge_balance_transfer делает дополнительные effects, которые
   неразличимы с обычными закупками без проверки `is_system_generated`.

«Доказуемо» = с гарантией того, что формула сохранится для `Items, которые
были удалены/merged/каталог переименован». Без таковой — report можно подделать.

> **Вопрос: можно ли воспроизвести отчёт после переименования или merge Item?**

**Частично**. Для merged Item:
- Если ещё есть `source_item_id` в `audit_event_resources[relation='merge_source']`
  (что сейчас пишется), можно найти все когда-либо привязанные операции
  в историческом режиме через snapshot/manual walk.
- **Но**: `OperationLine.item_id` физически переписан (`merge_items`,
  см. §4.1). Это значит, что «просто query operations where item_id=X»
  не вернёт «первоначальные строки source». Дополнительная логика нужна.

Для renamed Item — OK, snapshot item_name_snapshot остаётся.

> **Вопрос: можно ли доказать происхождение каждой строки текущего остатка?**

**Условно**. Из `audit_item_effects` с фильтром `is_system_generated=False`
можно получить цепочку events. Однако:

1. Если прошёл merge — видны послед-merge references, не source-before.
2. Если cancellation — нужен parent_event_id chain + filter effect_type='cancel_reversal'.
3. Если acceptance поздняя — actual accepted effect vs declared qty в submit.
4. Если restore без audit — потерян pre-restore submission.

> **Вопрос: можно ли безопасно отменить ошибочный merge?**

**Нет**. Механизм `unmerge` отсутствует. Любой «безопасный откат» —
это ручная цепочка:
1. Создать inverse merge (target → source) как ещё один merge event.
2. Написать compensating ADJUSTMENT.
3. manual UPDATE operation_lines.item_id (на уровне БД, не API).

Это **опасно**, потому что compensating ADJUSTMENT попадёт в отчётность
как обычная операция, раздувая обороты.

> **Вопрос: какие операции способны незаметно изменить прошлую статистику?**

1. `merge_items` — физически переписывает item_id на уже submitted строки.
2. `update_operation_effective_at` для submitted — меняет дату без compensation.
3. `cancel_operation` — создаёт cancel_reversal effect, который
   остаётся в journal, но **operation** больше не в UNION.
4. `restore_operation` — НЕ пишет audit_event, позволяет «откатить» cancel
   и сделать повторную submit с другим составом.
5. `soft_delete_item/category/unit` — не пишет audit_event; фактический
   snapshot строк сохраняется, но Item/Category могут «исчезнуть» для view.
6. inline-корректировки (correction) — изменяют OperationLine, при этом
   last_corrected_at + current_revision_id — оставляют истории (OK),
   но «движение» за период теперь содержит лишние/недостающие delta
   в зависимости от того, считаем через current line или revisioned.

> **Вопрос: какие данные уже потеряны без возможности точного восстановления?**

(при условии текущего кода, до дополнительных исправлений)

- Исходные `OperationLine.item_id` для всех строк, попавших в merge.
- Точный список «какие именно operation_lines переназначены» в merge (есть
  count, нет списка id).
- audit_event для `restore_operation`, `soft_delete_item`,
  `soft_delete_category`, `soft_delete_unit`, `_delete_temporary_items_of_operation`.
- before-snapshot для всех `item.update` / `category.update` / `unit.update`.
- Файлы source-документов (их в принципе не было).

> **Вопрос: что обязательно сделать до конца текущего сезона?**

См. `SEASON_REPORT_READINESS.md` и P0/P1 секции `HISTORICAL_INTEGRITY_ROADMAP.md`.

> **Вопрос: что можно отложить до общего модульного рефакторинга?**

См. Этап E roadmap. Главное: перенос на proper event-sourcing
**не рекомендуется до явного ADR** — текущая модель может быть
расширена в рамках incremental hardening (§3-7 roadmap).

---

## 13. Сводная таблица областей

| Область | Источник истины | Воспроизвести прошлое | Откатить | Риск сезона | Приоритет |
|---------|-----------------|----------------------|----------|-------------|-----------|
| I. Операции | operations + balances + audit_item_effects | Частично (нет restore audit, late accept effects) | Cancel+Restore есть; но без audit_event для restore | **P0** (restore без следа) | P0 |
| II. OperationLines | operation_lines (mutation) + operation_revisions/lines (immutable) | Частично (snapshots есть, но merge_items переписывает item_id) | correction flow V1 | **P0** (merge overwrite) | P0 |
| III. Balances/effects | balances (projected) + audit_item_effects | Условно (created_at vs effective_at разрыв) | Restore отменяет, через cancel_reversal | **P0** (back-dating) | P0 |
| IV. Merge | Item.merged_into_id + audit_event_resources + audit_item_effects | Частично (нет line_map, нет original_item_id) | **Нет unmerge** | **P0** | P0 |
| V. Master data | items / categories / units (UPDATE) + audit_events (без before/after) | Да (snapshots в lines) | soft-delete + restore | P1 (нет audit_event для delete) | P1 |
| VI. Source documents | operations.creation_source + source_ref | **Нет файлов** | n/a (нет файлов) | **P1** | P1 |
| VII. Audit | audit_events + audit_event_resources + audit_item_effects | Полностью — если заполнено | n/a (RESTRICT FK) | **P0** (гэпы в audit_event см. §6.2) | P0 |
| VIII. Отчётность | reports_repo UNION ALL | Частично (только current mode) | n/a | **P1** (нет historical mode) | P1 |
| IX. Закрытие периода | n/a (нет модели) | n/a | n/a | **P1** | P1 |
| X. Backup/PITR | docker volume postgres_data + pg_dump | Частично (только logical) | manual restore без PITR | P2 | P2 |

Подробности и предложения по ремонту — в `HISTORICAL_RISK_REGISTER.md`,
`HISTORICAL_INTEGRITY_ROADMAP.md` и `SEASON_REPORT_READINESS.md`.

---

## 14. Что **не вошло** в этот аудит

- Производительность, индексы, query-планы (отдельный perf-аудит).
- Все угловые случаи которые требуют stand-испытания (отметки `[GAP]`).
- Warehouse_web / Django BFF уровень — SyncServer only по явной формулировке задачи.
- Полный аудит `Warehouse_client_core` (Rust) — не запрашивалось.
- Frontend/Angular — не запрашивалось.
- Расширенный анализ security policy (auth: разделение LLM-client vs user-token).
- Полный модульный рефакторинг (см. Этап E roadmap).
