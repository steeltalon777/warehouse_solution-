# TZ: Audit Backend — Storage Foundation (Phase 1)

## Execution Checklist

- [x] 0. Context verified
- [x] 1. Модели `audit_event_resources` и `audit_item_effects` + миграции
- [x] 2. Безопасные FK и snapshots для audit-таблиц
- [x] 3. Расширение `AuditEvent` новыми полями + миграция
- [x] 4. `operation.origin` / `operation.system_reason` + миграция
- [x] 5. `operation.update` audit
- [x] 6. `category.merge` audit с resource-связями
- [x] 7. `item.merge`: эффекты до перепривязки, системная маркировка, правильный порядок INSERT
- [x] 8. Merge closure вместо `canonical_item_id`
- [x] 9. Batch audit: `catalog.batch.apply` с outcome `partial`
- [x] 10. Temporary / review / issue merge audit через inventory_subject
- [x] 11. Repository tests
- [x] 12. Service integration tests
- [x] 13. Stand smoke tests
- [x] 14. Документация + ADR
- [ ] 15. Final acceptance review

## Check Rules

- Architect создаёт чеклист и критерии приёмки.
- Coding-агент (warehouse-agent) отмечает пункты только после реализации и верификации.
- Если проверка пропущена — остаётся unchecked с причиной в отчёте.
- Auth outbox, admin/security события, read API, CLI — вынесены в Phase 2.

## Implementation Log

| # | Commit (root dev) | Commit (SyncServer dev) | Что |
|---|---|---|---|
| 1 | `ba223ac` | — | Модели `audit_event_resources`, `audit_item_effects`, расширение `AuditEvent` (v2 поля) и `Operation` (origin/system_reason/initiated_by_user_id). Миграции 0024..0027. |
| 2 | `85e0e31` | — | `record_audit_event` с v2-сигнатурой; `UoW.batch_correlation_id`; новые методы репо. |
| 3 | `891e109` | — | `operation.update` audit + `submit`/`cancel` записывают `audit_item_effects`; эффект-типинг mapping; cancel_reversal. |
| 4 | `761ca9e` | — | `item.merge` rewrite (parent first, effects before reassign, origin='system'), `category.merge` resources, `temporary_item.approve/.merge`, `review_item.confirm/.merge`, `issue_object.merge`, batch audit + correlation_id. |
| 5 | `f1fb95a` | — | 27 новых тестов: `test_audit_repo.py`, `test_audit_operations.py`, `test_audit_catalog_merge.py`, `test_audit_batch.py`, `test_audit_related_merge.py`. |
| 6 | `df715a1` | — | ADR-0018 + `audit-event-catalog.md` + коммит TZ в git. |
| 7 | — | `e40c860` | SyncServer/README.md — секция audit с helper sign, ordering invariant, ссылками на ADR + catalog. |

(На SyncServer dev — только отметка коммита README; остальные SyncServer-коммиты под `ba223ac` — `f1fb95a` лежат в submodule git истории.)

### Команды верификации

| Команда | Результат |
|---|---|
| `alembic upgrade head` | `0023 -> 0024 -> 0025 -> 0026 -> 0027` applied на стенде. |
| `python -m pytest tests/test_audit_repo.py tests/test_audit_operations.py tests/test_audit_catalog_merge.py tests/test_audit_batch.py tests/test_audit_related_merge.py` | 27 passed. |
| `python -m pytest tests/test_operations_*.py tests/test_catalog_merge.py tests/test_catalog_batch_merge.py tests/test_catalog_admin_audit.py` | 128 + 10 = 138 passed, 0 broken. |
| curl SyncServer stand — submit ADJUSTMENT op, item.merge через `POST /api/v1/catalog/admin/items/merge`, batch через `POST /api/v1/catalog/admin/batch` | Все три сценария записывают v2 события с правильными effects/resources/correlation. |
| DB inspection `SELECT event_type, count(*) FROM audit_events WHERE event_version=2 GROUP BY event_type` | 10 v2-событий распределены по `operation.submit`, `item.merge`, `operation.create`, `category.update`, `catalog.batch.apply`. |

---

## 1. Назначение

Настоящее ТЗ описывает **Storage Foundation** backend-фазы расширенного журналирования в SyncServer — модели, миграции, точки записи и базовые read-репозитории.

**Цель фазы:** все данные начинают корректно сохраняться. API-контракты чтения, auth outbox, admin/security события, CLI — в отдельном Phase 2 ТЗ.

**Frontend-фаза** (пользовательские экраны, временная шкала, фильтры, карточки событий) будет проектироваться позднее.

---

## 2. Подтверждённое текущее состояние (по коду, не по документации)

### 2.1. Что уже существует

#### Модель `AuditEvent`
**Файл:** `SyncServer/app/models/audit_event.py`

Поля: `id`, `event_id` (UUID unique), `event_type`, `actor_user_id` FK→users, `actor_device_id` FK→devices, `site_id` FK→sites, `entity_type`, `entity_id`, `summary`, `changes` (JSONB), `request_id`, `created_at`.

Индексы: `event_type`, `actor_user_id`, `entity_type+entity_id`, `site_id`, `created_at`.

#### Хелпер `record_audit_event()`
**Файл:** `SyncServer/app/services/audit_helper.py`

Fire-and-forget внутри текущей UoW-транзакции. Сигнатура из 9 параметров.

#### Репозиторий `AuditEventsRepo`
**Файл:** `SyncServer/app/repos/audit_events_repo.py`

`insert()`, `list_events()` (7 фильтров), `get_by_id()`, `get_by_id_full()`.

#### API
**Файл:** `SyncServer/app/api/routes_admin_audit.py`

`GET /admin/audit` (список), `GET /admin/audit/{id}` (детализация). Доступ: root или chief_storekeeper.

#### CLI
**Файл:** `SyncServer/scripts/query_audit.py`

`--username`, `--token`, фильтры по event_type/entity/датам, форматы markdown/json/table.

#### Django BFF
**Файлы:** `Warehouse_web/apps/bff_api/audit_views.py`, `Warehouse_web/apps/users/admin_audit_views.py`

Pass-through прокси + Django admin views.

#### Уже логируемые события

| Вызов `record_audit_event()` | Файл | Событие |
|---|---|---|
| `operations_service.py:580` | create_operation | `operation.create` |
| `operations_service.py:1184` | submit_operation | `operation.submit` |
| `operations_service.py:1334` | accept_operation_lines | `operation.acceptance_complete` |
| `operations_service.py:1435` | delete_operation | `operation.delete` |
| `operations_service.py:1649` | cancel_operation | `operation.cancel` |
| `catalog_admin_service.py:60` | create_unit | `unit.create` |
| `catalog_admin_service.py:124` | update_unit | `unit.update` |
| `catalog_admin_service.py:159` | create_category | `category.create` |
| `catalog_admin_service.py:225` | update_category | `category.update` |
| `catalog_admin_service.py:268` | create_item | `item.create` |
| `catalog_admin_service.py:332` | update_item | `item.update` |
| `catalog_admin_service.py:643` | merge_items | `item.merge` |

### 2.2. Что отсутствует (подтверждено чтением кода)

- `operation.update` — **нет аудита**. Метод `update_operation()` (строка 615-861) не вызывает `record_audit_event`
- `operation.restore` — **нет аудита**. Метод `restore_operation()` (строка 1667-1682) не вызывает `record_audit_event`
- `category.merge` — **нет аудита**. Метод `merge_categories()` (строка 664-749) не вызывает `record_audit_event`
- `item.merge` — аудит есть, но **до перепривязки OperationLine не сохраняются эффекты**
- `temporary_item.approve` / `temporary_item.merge` — **нет аудита**
- `review_item.confirm` / `review_item.merge` — **нет аудита**
- `issue_object.merge` — **нет аудита**
- Batch `catalog.batch.apply` — **нет общего audit-события**, нет correlation между дочерними событиями
- Системные ADJUSTMENT-операции не отмечены (`origin` всегда `"user"`)
- Auth в SyncServer не доставляется (локальный `LoginAttempt` в Django — есть)

### 2.3. Подтверждённая модель batch

**Код подтверждает:** `apply_batch()` (строка 753-853) **не является атомарным с точки зрения отдельных изменений.**

```python
# Псевдокод реального поведения:
for change in all_changes:
    try:
        result = await _apply_*_change(uow, change, ...)
        if result.status == "applied":
            commit_to_session()  # в рамках одного UoW
        else:
            summary["error"] += 1  # ошибка поймана, продолжаем
    except HTTPException:
        result = BatchChangeResult(status="error")
        summary["error"] += 1
        # НЕ откатываем — продолжаем обработку

# В конце UoW.commit() — все успешные изменения фиксируются
return results, summary  # status="error" для упавших, "applied" для успешных
```

**Следствия для аудита:**
- Batch может быть частично успешным.
- Успешные изменения уже создали свои audit-события (через `create_item` → `record_audit_event` и т.д.).
- Аудит должен отразить batch как целое с outcome `partial`.
- Не нужно менять транзакционную стратегию batch.

---

## 3. Критические проблемы текущего кода

| # | Проблема | Последствия |
|---|----------|-------------|
| P1 | `merge_items()` перепривязывает `OperationLine.item_id` **до** записи аудита | Историческая связь «какая карточка использовалась в операции» утеряна безвозвратно |
| P2 | Нет хранения количественных эффектов ТМЦ | История остатков невосстановима по текущим таблицам |
| P3 | `entity_type`/`entity_id` — только одна пара на событие | Недостаточно для merge (source+target), batch |
| P4 | Системные ADJUSTMENT неотличимы от ручных | Журнал кладовщика содержит шум |
| P5 | `category.merge` не пишет аудит совсем | Нет истории слияния категорий |

---

## 4. Scope Storage Foundation (ДАННЫЙ TZ)

### Включено

1. Новые таблицы: `audit_event_resources`, `audit_item_effects`
2. Новые поля в `audit_events`: `event_version`, `outcome`, `correlation_id`, `parent_event_id`, `source_client`, `actor_username_snapshot`, `external_event_id`
3. Новые поля в `operations`: `origin`, `system_reason`, `initiated_by_user_id`
4. Audit для `operation.update`
5. Audit для `category.merge` (с resource-связями)
6. Исправление `item.merge`: эффекты до перепривязки, системная маркировка, правильный порядок INSERT
7. Audit для temporary/review/issue merge
8. Audit для batch: `catalog.batch.apply` с outcome `partial`
9. Merge closure для истории ТМЦ
10. Миграции (4 новых)
11. Тесты репозитория и сервисной интеграции
12. ADR по архитектуре audit

### Исключено (выйдет в Phase 2)

- Auth outbox + endpoint приёма
- Admin/security события (user.*, device.*, access_scope.*)
- Read API: item history endpoint, batch detail endpoint
- Расширение CLI
- Django `AuditOutbox` модель и management-команды
- `credential_kind`, `credential_fingerprint` (нужны для auth audit в Phase 2, поля в модели создаём сейчас, но не заполняем)
- `external_event_id` (нужен для auth audit, поле создаём сейчас)

---

## 5. Non-goals

- Event sourcing
- Замена существующей системы `audit_events`
- Партиционирование / GIN-индексы
- Celery / тяжёлые брокеры
- Хранение полных токенов в audit
- UPDATE/DELETE существующих audit-записей
- Обязательный backfill старых данных
- Изменение frontend (Angular, Django templates, CSS)
- Изменение BFF auth flow
- Push кода

---

## 6. Архитектурное решение

### 6.1. Принципы

1. **SyncServer — источник истины** для всех audit-событий.
2. **`audit_events` — append-only**. Никаких UPDATE/DELETE.
3. **Разделение бизнес-аудита и технической телеметрии**.
4. **Атомарность успешных событий** — запись внутри UoW-транзакции.
5. **Хранение истории ТМЦ** независимо от изменяемых `OperationLine`.
6. **Один количественный эффект на одно фактическое изменение остатка**.
7. **FK audit-таблиц не каскадируют удаление доменных сущностей**.

### 6.2. Почему не `canonical_item_id`

Проблема: если при создании эффекта сохранить `canonical_item_id` «на текущий момент», то после будущего merge старые эффекты не будут найдены при поиске истории новой канонической ТМЦ.

```
Январь: эффект для Item 10, canonical_item_id = 10
Март:   Item 10 → Item 20 (merge)
Июнь:   Item 20 → Item 30 (merge)
```

Поиск «история Item 30 с follow_merges» по `canonical_item_id = 30` не найдёт январский эффект.

**Решение: merge closure.** Для поиска истории канонической ТМЦ:
1. Найти текущую каноническую ТМЦ (по цепочке `merged_into_id`).
2. Построить множество всех предшественников (merge closure): {30, 20, 10}.
3. Искать эффекты по `item_id IN (10, 20, 30)`.

`canonical_item_id` остаётся в таблице как **информационный снимок** состояния на момент события (удобно для отладки), но **не используется** как первичный ключ поиска.

### 6.3. Модель эффектов: один эффект — одно изменение остатка

В операциях merge создаются системные ADJUSTMENT-операции (write-off source, receipt target). При их submit создаются `audit_item_effects`. **Это единственный источник эффектов.** Никаких дополнительных `merge_write_off`/`merge_receipt` эффектов, дублирующих системные операции.

Связь между merge-событием и его эффектами — через `audit_event_resources`:
- `item.merge` event → resources: `generated` → operation_id (ADJUSTMENT)
- ADJUSTMENT `operation.submit` event → `audit_item_effects`

```text
item.merge (event_id = E1)
  ├── audit_event_resources: generated = operation.op_1
  ├── audit_event_resources: generated = operation.op_2
  ├── audit_event_resources: merge_source = item.42
  └── audit_event_resources: merge_target = item.57
  
operation.submit (event_id = E2, parent_event_id = E1)
  └── audit_item_effects: {item_id=42, site_id=1, delta=-10, effect_type=merge_write_off, ...}

operation.submit (event_id = E3, parent_event_id = E1)
  └── audit_item_effects: {item_id=57, site_id=1, delta=+10, effect_type=merge_receipt, ...}
```

### 6.4. Порядок INSERT при merge

Проблема: эффекты (и дочерние operation.submit) должны ссылаться на `parent_event_id` родительского `item.merge`, но родительское событие ещё не создано.

Решение:

```text
BEGIN UoW
  1. INSERT AuditEvent(item.merge) → FLUSH → получить event_id = E1
  2. Создать системные ADJUSTMENT-операции
  3. Submit ADJUSTMENT-операций (внутри submit: INSERT AuditEvent(operation.submit, parent_event_id=E1))
  4. INSERT audit_item_effects (с effect_type = merge_write_off / merge_receipt)
  5. INSERT audit_event_resources (generated, merge_source, merge_target → все ссылаются на E1)
  6. Перепривязать OperationLine.item_id (деструктивное изменение)
  7. Архивировать inventory subject
  8. Деактивировать source item
COMMIT

Если на любом шаге ошибка → UoW.rollback() → E1 тоже откатывается.
```

### 6.5. FK-политика для audit-таблиц

| Audit-таблица | FK | Действие при удалении доменной сущности |
|---------------|-----|----------------------------------------|
| `audit_events.actor_user_id` | → users.id | `SET NULL` (уже так) |
| `audit_events.actor_device_id` | → devices.id | `SET NULL` (уже так) |
| `audit_events.site_id` | → sites.id | `SET NULL` (уже так) |
| `audit_events.parent_event_id` | → audit_events.event_id | `RESTRICT` (события не удаляются) |
| `audit_event_resources.audit_event_id` | → audit_events.id | `RESTRICT` |
| `audit_item_effects.audit_event_id` | → audit_events.id | `RESTRICT` |
| `audit_item_effects.operation_id` | → operations.id | `SET NULL` |
| `audit_item_effects.item_id` | → items.id | `RESTRICT` |
| `audit_item_effects.site_id` | → sites.id | `SET NULL` |

**Важно:** `audit_item_effects.item_id` → `RESTRICT`. Если ТМЦ пытаются удалить при наличии эффектов — БД блокирует удаление. Это намеренно: история ТМЦ не должна исчезать при удалении карточки. Для деактивированных/удалённых ТМЦ эффекты содержат snapshot-поля.

---

## 7. Модель данных (конечное состояние Phase 1)

### 7.1. `audit_events` — расширенные поля

Добавляются (все nullable):

| Поле | Тип | Назначение |
|------|-----|------------|
| `event_version` | Integer, NOT NULL, default 2 | Версия схемы `changes` |
| `outcome` | String(32), nullable | `success`, `failed`, `denied`, `partial` |
| `correlation_id` | String(64), nullable | Группировка событий одного batch |
| `parent_event_id` | UUID FK→audit_events.event_id, nullable | Связь дочернего события с родительским (RESTRICT) |
| `credential_kind` | String(16), nullable | `user_token`, `device_token` — **поле создаётся, заполняется в Phase 2** |
| `credential_fingerprint` | String(128), nullable | HMAC от токена — **поле создаётся, заполняется в Phase 2** |
| `source_client` | String(32), nullable | `web`, `desktop`, `mobile`, `cli` |
| `actor_username_snapshot` | String(128), nullable | Username на момент события |
| `external_event_id` | String(128), nullable, unique | Идемпотентный ключ — **поле создаётся, используется в Phase 2** |

**Версионирование `changes`:**

- `event_version = 1` — старые события (свободный JSONB, существующие 338+ записей)
- `event_version = 2` — новые события с описанной схемой `changes`

**Backfill:** `UPDATE audit_events SET event_version = 1 WHERE event_version IS NULL`.

Для новых событий `event_version = 2` служит маркером: «changes соответствует документированной схеме». Читающий код проверяет версию и парсит `changes` соответственно.

### 7.2. `audit_event_resources`

```text
audit_event_resources
├── id: Integer PK, autoincrement
├── audit_event_id: Integer FK → audit_events.id, NOT NULL, ON DELETE RESTRICT
├── resource_type: String(64), NOT NULL        # "operation", "item", "category", "temporary_item", "issue_object", "inventory_subject"
├── resource_id: String(256), NOT NULL          # ID сущности (может быть int или UUID — храним как строку)
├── relation: String(32), NOT NULL              # primary, merge_source, merge_target, affected, generated, reparented, category_changed
├── snapshot_before: JSONB, nullable             # состояние до изменения
├── snapshot_after: JSONB, nullable              # состояние после изменения
├── created_at: DateTime TZ, server_default=now()
```

**Индексы:**
- `ix_audit_event_resources_event_id` на `audit_event_id`
- `ix_audit_event_resources_type_id` на `resource_type, resource_id`

### 7.3. `audit_item_effects`

```text
audit_item_effects
├── id: Integer PK, autoincrement
├── audit_event_id: Integer FK → audit_events.id, NOT NULL, ON DELETE RESTRICT
├── operation_id: UUID FK → operations.id, nullable, ON DELETE SET NULL
├── inventory_subject_id: Integer FK → inventory_subjects.id, NOT NULL
├── item_id: Integer FK → items.id, nullable, ON DELETE RESTRICT
├── item_name_snapshot: String(256), nullable    # имя ТМЦ на момент события
├── item_sku_snapshot: String(128), nullable     # SKU на момент события
├── subject_type: String(32), nullable           # "catalog_item", "temporary_item"
├── site_id: Integer FK → sites.id, nullable, ON DELETE SET NULL
├── quantity_before: Numeric(18, 4), nullable
├── quantity_delta: Numeric(18, 4), NOT NULL
├── quantity_after: Numeric(18, 4), nullable
├── effect_type: String(32), NOT NULL
├── is_system_generated: Boolean, default false
├── caused_by_event_id: Integer FK → audit_events.id, nullable, ON DELETE RESTRICT
├── note: String(500), nullable
├── created_at: DateTime TZ, server_default=now()
```

**Ключевое отличие от предыдущей версии ТЗ:**
- `inventory_subject_id` — обязательный. Это позволяет хранить эффекты для temporary item (у которого `item_id` может быть null до approve).
- `item_id` — nullable. Заполняется, когда эффект связан с каталожной ТМЦ. Для temporary item может быть null (если баланс был на temporary subject).
- `item_name_snapshot`, `item_sku_snapshot`, `subject_type` — snapshot-поля для сохранения контекста даже после удаления доменной сущности.
- `caused_by_event_id` — ссылка на бизнес-событие, вызвавшее эффект (например, `item.merge`). Заменяет `parent_merge_event_id`.

**Индексы:**
- `ix_audit_item_effects_event_id` на `audit_event_id`
- `ix_audit_item_effects_inventory_subject_id` на `inventory_subject_id`
- `ix_audit_item_effects_item_id` на `item_id`
- `ix_audit_item_effects_site_id` на `site_id`
- `ix_audit_item_effects_operation_id` на `operation_id`
- `ix_audit_item_effects_effect_type` на `effect_type`

### 7.4. `operations` — новые поля

```text
operations
├── origin: String(16), NOT NULL, default 'user'   # "user" | "system"
├── system_reason: String(32), nullable              # "item_merge", "temporary_merge", "review_merge"
├── initiated_by_user_id: UUID FK → users.id, nullable  # пользователь, инициировавший системную операцию
```

### 7.5. `inventory_subjects` — существующая таблица (контекст)

Уже существует. Используется в `audit_item_effects.inventory_subject_id`.

```text
inventory_subjects
├── id: Integer PK
├── subject_type: String    # "catalog_item" | "temporary_item"
├── item_id: Integer nullable
├── temporary_item_id: Integer nullable
├── archived_at: DateTime nullable
```

---

## 8. Каталог событий (Phase 1)

Для каждого события `event_version = 2`. Схема `changes` документирована.

### 8.1. Operations

| event_type | changes (v2) | resources | item_effects | outcome |
|-----------|-------------|-----------|-------------|---------|
| `operation.create` | `{operation_type, site_id, source_site_id?, destination_site_id?, lines_count, has_temporary_items}` | primary=operation | нет | success |
| `operation.update` | `{fields_changed: [...], lines_count_before, lines_count_after}` | primary=operation | нет | success |
| `operation.submit` | `{operation_type, lines_count, total_qty}` | primary=operation | да | success |
| `operation.acceptance_complete` | `{resolved_lines, accepted_qty, lost_qty}` | primary=operation | да (effect_type=acceptance) | success |
| `operation.cancel` | `{reason?, was_submitted}` | primary=operation | да (effect_type=cancel_reversal) | success |
| `operation.delete` | `{status_before_delete}` | primary=operation | нет | success |

### 8.2. Catalog

| event_type | changes (v2) | resources |
|-----------|-------------|-----------|
| `item.create` | `{name, sku?, category_id, unit_id, is_active, requires_review}` | primary=item |
| `item.update` | `{fields_changed: [...], diff: {field: {old, new}}}` | primary=item |
| `item.merge` | `{source_item_id, target_item_id, comment?, balances_transferred: [{site_id, qty}], op_lines_reassigned_count}` | primary=target; merge_source=source; generated=ADJUSTMENT_op (для каждой) |
| `unit.create` | `{name, symbol, is_active}` | primary=unit |
| `unit.update` | `{fields_changed: [...], diff}` | primary=unit |
| `category.create` | `{name, code?, parent_id?}` | primary=category |
| `category.update` | `{fields_changed: [...], diff}` | primary=category |
| `category.merge` | `{source_category_id, target_category_id, comment?, items_moved_count, subcategories_reparented_count}` | primary=target; merge_source=source; reparented=subcategory_id (для каждой); category_changed=item_id (для каждого) |

Примечание: `item.deactivate` и `category.deactivate` не создают отдельных событий — они идут через `item.update`/`category.update` с `changes.is_active: {old: true, new: false}`.

### 8.3. Related entities

| event_type | changes (v2) | resources |
|-----------|-------------|-----------|
| `temporary_item.approve` | `{temporary_item_id, new_item_id, inventory_subject_id}` | primary=new_item; merge_source=temporary_item; generated=ADJUSTMENT_op (для каждой) |
| `temporary_item.merge` | `{temporary_item_id, target_item_id, inventory_subject_id}` | primary=target; merge_source=temporary_item; generated=ADJUSTMENT_op (для каждой) |
| `review_item.confirm` | `{item_id, resolution_type}` | primary=item |
| `review_item.merge` | `{item_id, target_item_id}` | primary=target; merge_source=item; generated=ADJUSTMENT_op (для каждой) |
| `issue_object.merge` | `{source_id, target_id}` | primary=target; merge_source=source |

### 8.4. Batch

| event_type | changes (v2) | outcome |
|-----------|-------------|---------|
| `catalog.batch.apply` | `{total_changes, results: [{local_id, entity_type, action, status, entity_id?, error_code?, error_message?}]}` | success (все applied) или partial (есть error) |

**Особенность:** batch-событие создаётся ПОСЛЕ выполнения всех изменений, когда известен итоговый outcome. Дочерние события (созданные внутри `_apply_*_change`) и batch-событие связываются через `correlation_id`.

### 8.5. Системные операции

Системные ADJUSTMENT-операции (создаваемые при merge) пишут стандартное `operation.submit` событие с:
- `parent_event_id` = event_id родительского merge
- `changes` включает `system_reason`
- Операция в БД: `origin = "system"`, `system_reason = "item_merge"` (или `temporary_merge`, `review_merge`), `initiated_by_user_id` = пользователь

### 8.6. Всего типов событий в Phase 1

Operations: 6
Catalog: 8
Related: 5
Batch: 1

**Итого: 20 событий** (все обязательны для Phase 1, без admin/security/auth).

---

## 9. Merge closure для истории ТМЦ

### 9.1. Алгоритм построения merge closure

```python
async def build_merge_closure(uow, item_id: int) -> set[int]:
    """Возвращает множество всех item_id, которые были слиты в каноническую ТМЦ."""
    closure = {item_id}
    
    # Найти каноническую ТМЦ (конечную в цепочке)
    current = item_id
    while True:
        item = await uow.catalog.get_item_by_id(current)
        if item is None or item.merged_into_id is None:
            break
        current = item.merged_into_id
        closure.add(current)
    
    # Найти всех предшественников (кто был слит в любую из ТМЦ цепочки)
    # Для каждого id в closure найти все items, у которых merged_into_id = id
    to_check = set(closure)
    while to_check:
        target_id = to_check.pop()
        sources = await uow.catalog.get_items_merged_into(target_id)
        for source in sources:
            if source.id not in closure:
                closure.add(source.id)
                to_check.add(source.id)
    
    return closure
```

### 9.2. Использование при поиске истории

```sql
-- Режим exact: история конкретной карточки
SELECT * FROM audit_item_effects 
WHERE item_id = :item_id
ORDER BY created_at DESC;

-- Режим follow_merges: история канонической ТМЦ
SELECT * FROM audit_item_effects 
WHERE item_id IN (:merge_closure)
ORDER BY created_at DESC;
```

### 9.3. `canonical_item_id` в таблице

Поле `canonical_item_id` **не добавляется** в `audit_item_effects`. Информация о канонической ТМЦ на момент записи хранится в `caused_by_event_id` → `audit_event_resources.merge_target`.

---

## 10. Точки записи (конкретные изменения в коде)

### 10.1. `operation.update`

**Файл:** `SyncServer/app/services/operations_service.py`
**Метод:** `update_operation()` (после строки 861, перед `return`)

```python
await record_audit_event(
    uow,
    event_type="operation.update",
    event_version=2,
    actor_user_id=user_id,  # нужно пробросить user_id в метод
    site_id=operation.site_id,
    entity_type="operation",
    entity_id=str(operation_id),
    summary=f"Изменён черновик операции №{operation.short_id}",
    changes={
        "fields_changed": list(update_data.model_fields_set),
        "lines_count_before": old_lines_count,
        "lines_count_after": new_lines_count,
    },
    outcome="success",
    source_client=source_client,
    actor_username_snapshot=username,
)
```

**Важно:** метод `update_operation()` сейчас не принимает `user_id`. Нужно добавить параметр. Проверить точку вызова в API-роуте — `identity.user_id` доступен.

### 10.2. `category.merge`

**Файл:** `SyncServer/app/services/catalog_admin_service.py`
**Метод:** `merge_categories()` (после строки 740, до `return target`)

```python
# Собрать списки затронутых items и subcategories ДО их перемещения
items_moved = await uow.catalog.list_items_by_category(source_category_id)
subcats_moved = await uow.catalog.list_categories_by_parent(source_category_id)

# ... выполнить merge (перемещение items, subcategories, деактивация source) ...

# Записать audit
merge_event = await record_audit_event(
    uow,
    event_type="category.merge",
    event_version=2,
    actor_user_id=resolved_by_user_id,
    entity_type="category",
    entity_id=str(target_category_id),
    summary=f"Слияние категории {source_category_id} → {target_category_id}"
            + (f" ({comment})" if comment else ""),
    changes={
        "source_category_id": source_category_id,
        "target_category_id": target_category_id,
        "comment": comment,
        "items_moved_count": len(items_moved),
        "subcategories_reparented_count": len(subcats_moved),
    },
    outcome="success",
)

# Записать resource-связи
await uow.audit_events.insert_resource(
    audit_event_id=merge_event.id,
    resource_type="category", resource_id=str(source_category_id),
    relation="merge_source",
)
await uow.audit_events.insert_resource(
    audit_event_id=merge_event.id,
    resource_type="category", resource_id=str(target_category_id),
    relation="merge_target",
)
for item in items_moved:
    await uow.audit_events.insert_resource(
        audit_event_id=merge_event.id,
        resource_type="item", resource_id=str(item.id),
        relation="category_changed",
    )
for subcat in subcats_moved:
    await uow.audit_events.insert_resource(
        audit_event_id=merge_event.id,
        resource_type="category", resource_id=str(subcat.id),
        relation="reparented",
    )
```

### 10.3. `item.merge` — исправленный порядок

**Файл:** `SyncServer/app/services/catalog_admin_service.py`
**Метод:** `merge_items()` — полная переработка порядка операций

```python
async def merge_items(self, uow, *, source_item_id, target_item_id,
                      comment=None, resolved_by_user_id):
    # Валидация (без изменений)
    source = await uow.catalog.get_item_by_id(source_item_id)
    target = await uow.catalog.get_item_by_id(target_item_id)
    # ... все проверки ...

    # ─── Шаг 1: INSERT родительского audit-события ───
    merge_event = await record_audit_event(uow,
        event_type="item.merge",
        event_version=2,
        actor_user_id=resolved_by_user_id,
        entity_type="item",
        entity_id=str(target_item_id),
        summary=f"Слияние ТМЦ {source_item_id} → {target_item_id}"
                + (f" ({comment})" if comment else ""),
        changes={
            "source_item_id": source_item_id,
            "target_item_id": target_item_id,
            "comment": comment,
            "balances_transferred": [],
            "op_lines_reassigned_count": 0,
        },
        outcome="success",
    )
    # flush уже внутри record_audit_event → event_id готов

    # ─── Шаг 2: Перенос остатков через системные ADJUSTMENT ───
    source_subject = await uow.inventory_subjects.get_by_item_id(source_item_id)
    target_subject = await uow.inventory_subjects.get_or_create_for_item(item_id=target_item_id)
    
    if source_subject and not source_subject.archived_at:
        source_balances = await uow.balances.get_all_by_inventory_subject(int(source_subject.id))
        for balance_row in source_balances:
            qty = balance_row.qty
            if qty == 0:
                continue
            site_id = int(balance_row.site_id)
            note = f"[catalog merge] item={source_item_id} -> item={target_item_id}: site={site_id} qty={qty}"
            
            # Создать системные ADJUSTMENT-операции
            write_off = await uow.operations.create_operation(
                site_id=site_id, operation_type="ADJUSTMENT",
                created_by_user_id=resolved_by_user_id,
                notes=note, effective_at=datetime.now(UTC),
                origin="system",
                system_reason="item_merge",
                initiated_by_user_id=resolved_by_user_id,
            )
            # ... create line ...
            await OperationsService.submit_operation(uow, write_off.id, resolved_by_user_id)
            # Внутри submit: создаётся operation.submit audit (parent_event_id=merge_event.event_id)
            # Внутри submit: создаются audit_item_effects
            
            receipt_op = await uow.operations.create_operation(
                site_id=site_id, operation_type="ADJUSTMENT",
                created_by_user_id=resolved_by_user_id,
                notes=note, effective_at=datetime.now(UTC),
                origin="system",
                system_reason="item_merge",
                initiated_by_user_id=resolved_by_user_id,
            )
            # ... create line ...
            await OperationsService.submit_operation(uow, receipt_op.id, resolved_by_user_id)
            
            # Записать resource-связи: merge_event → generated ADJUSTMENT-операции
            await uow.audit_events.insert_resource(
                audit_event_id=merge_event.id,
                resource_type="operation", resource_id=str(write_off.id),
                relation="generated",
            )
            await uow.audit_events.insert_resource(
                audit_event_id=merge_event.id,
                resource_type="operation", resource_id=str(receipt_op.id),
                relation="generated",
            )

    # ─── Шаг 3: ТОЛЬКО ТЕПЕРЬ перепривязать OperationLine ───
    op_lines_count = await uow.operations.count_lines_by_item(source_item_id)
    await uow.session.execute(
        sa_update(OperationLine.__table__)
        .where(OperationLine.__table__.c.item_id == source_item_id)
        .values(item_id=target_item_id)
    )

    # ─── Шаг 4: Архивировать и деактивировать ───
    if source_subject and not source_subject.archived_at:
        await uow.inventory_subjects.archive(int(source_subject.id))
    
    source.is_active = False
    source.merged_into_id = target_item_id
    source.merged_at = datetime.now(UTC)
    source.merged_by_user_id = resolved_by_user_id
    source.merge_comment = comment
    await uow.catalog.update_item(source)

    # ─── Шаг 5: Дополнить changes родительского события ───
    # (merge_event уже в сессии, можно обновить changes)
    merge_event.changes["op_lines_reassigned_count"] = op_lines_count
    merge_event.changes["balances_transferred"] = [
        {"site_id": int(b.site_id), "qty": str(b.qty)}
        for b in source_balances if b.qty != 0
    ]

    # Resource-связи
    await uow.audit_events.insert_resource(
        audit_event_id=merge_event.id,
        resource_type="item", resource_id=str(source_item_id),
        relation="merge_source",
        snapshot_before={"name": source.name, "sku": source.sku, "is_active": True},
        snapshot_after={"is_active": False},
    )
    await uow.audit_events.insert_resource(
        audit_event_id=merge_event.id,
        resource_type="item", resource_id=str(target_item_id),
        relation="merge_target",
    )

    return target
```

### 10.4. `operation.submit` — запись эффектов

**Файл:** `SyncServer/app/services/operations_service.py`
**Метод:** `submit_operation()`

Добавить запись `audit_item_effects` для каждой строки операции после изменения остатков:

```python
for line in operation.lines:
    # ... существующая логика изменения остатков ...
    
    # Получить баланс после изменения
    subject = await uow.inventory_subjects.get_by_id(line.inventory_subject_id)
    
    await uow.audit_effects.insert(AuditItemEffect(
        audit_event_id=audit_event.id,  # operation.submit событие
        operation_id=operation.id,
        inventory_subject_id=line.inventory_subject_id,
        item_id=line.item_id,  # может быть null для temporary
        item_name_snapshot=subject.item.name if subject.item_id else None,
        item_sku_snapshot=subject.item.sku if subject.item_id else None,
        subject_type=subject.subject_type,
        site_id=site_id,
        quantity_before=balance_before,
        quantity_delta=delta,
        quantity_after=balance_after,
        effect_type=effect_type,  # receipt/expense/write_off/move_out/move_in/adjustment/issue/issue_return
        is_system_generated=(operation.origin == "system"),
        caused_by_event_id=parent_event_id,  # для системных — id родительского merge
        note=operation.notes,
    ))
```

### 10.5. `operation.cancel` — обратные эффекты

Аналогично `submit`, но с обратным знаком delta и `effect_type=cancel_reversal`.

### 10.6. Batch audit

**Файл:** `SyncServer/app/services/catalog_admin_service.py`
**Метод:** `apply_batch()` (после строки 853, перед `return`)

```python
# После выполнения всех изменений
correlation_id = str(uuid4())

# Дополнить correlation_id в уже созданные audit-события
# (они в той же сессии — можно обновить)
# Проще: передать correlation_id в _apply_*_change, чтобы он прокидывался в record_audit_event

# Записать batch-событие
batch_outcome = "success" if summary["error"] == 0 else "partial"

await record_audit_event(uow,
    event_type="catalog.batch.apply",
    event_version=2,
    actor_user_id=identity.user_id,
    entity_type="batch",
    entity_id=correlation_id,
    summary=f"Пакетное изменение каталога: {len(results)} операций",
    changes={
        "total_changes": len(results),
        "results": [
            {
                "local_id": r.local_id,
                "entity_type": r.entity_type,
                "action": r.action,
                "status": r.status,
                "entity_id": r.entity_id,
                "error_code": r.error_code,
                "error_message": r.error_message,
            }
            for r in results
        ],
    },
    outcome=batch_outcome,
    correlation_id=correlation_id,
)
```

Для передачи `correlation_id` в дочерние события: расширить `record_audit_event()` параметром `correlation_id`, который добавляется в `AuditEvent.correlation_id`. В `apply_batch()` сгенерировать `correlation_id` до начала обработки и передавать его в каждый вызов `record_audit_event` (через `create_item` → `record_audit_event` → нужен проброс параметра).

**Простой способ без переписывания сигнатур всех сервисов:** установить `correlation_id` в контекст UoW:

```python
uow.batch_correlation_id = str(uuid4())
```

И в `record_audit_event()`:
```python
correlation_id = correlation_id or getattr(uow, 'batch_correlation_id', None)
```

### 10.7. Temporary / review / issue merge

**Файлы:**
- `SyncServer/app/services/temporary_items_resolution_service.py`
- `SyncServer/app/services/review_items_service.py`
- `SyncServer/app/services/issue_objects_service.py`

Для каждого метода добавить `record_audit_event()` по образцу `item.merge`:

```python
# 1. INSERT родительского события (approve/merge)
event = await record_audit_event(uow,
    event_type="temporary_item.merge",  # или approve / review_item.merge / issue_object.merge
    event_version=2,
    actor_user_id=resolved_by_user_id,
    entity_type="temporary_item" if temp_item else "item",
    entity_id=str(target_item_id or new_item_id),
    summary=f"Слияние temporary_item {temp_id} → item {target_id}",
    changes={...},
    outcome="success",
)

# 2. Создать системные ADJUSTMENT (origin="system", system_reason="temporary_merge")
# 3. Submit → audit_item_effects создаются внутри submit

# 4. Resource-связи: generated → ADJUSTMENT-операции
```

---

## 11. Миграции

### Миграция 1: `audit_events` — новые поля

```python
# 0024_extend_audit_events.py
# Revises: 0023_add_operation_client_request_id

def upgrade():
    op.add_column("audit_events", sa.Column("event_version", sa.Integer(), nullable=True))
    op.add_column("audit_events", sa.Column("outcome", sa.String(32), nullable=True))
    op.add_column("audit_events", sa.Column("correlation_id", sa.String(64), nullable=True))
    op.add_column("audit_events", sa.Column("parent_event_id", PGUUID(as_uuid=True), nullable=True))
    op.add_column("audit_events", sa.Column("credential_kind", sa.String(16), nullable=True))
    op.add_column("audit_events", sa.Column("credential_fingerprint", sa.String(128), nullable=True))
    op.add_column("audit_events", sa.Column("source_client", sa.String(32), nullable=True))
    op.add_column("audit_events", sa.Column("actor_username_snapshot", sa.String(128), nullable=True))
    op.add_column("audit_events", sa.Column("external_event_id", sa.String(128), nullable=True))

    # Backfill
    op.execute("UPDATE audit_events SET event_version = 1 WHERE event_version IS NULL")
    op.alter_column("audit_events", "event_version", nullable=False, server_default="2")

    # Индексы
    op.create_index("ix_audit_events_correlation_id", "audit_events", ["correlation_id"])
    op.create_index("ix_audit_events_parent_event_id", "audit_events", ["parent_event_id"])
    op.create_index("ix_audit_events_outcome", "audit_events", ["outcome"])
    op.create_index("ix_audit_events_external_event_id", "audit_events", ["external_event_id"], unique=True)

    # FK RESTRICT
    op.create_foreign_key(
        "fk_audit_events_parent_event_id",
        "audit_events", "audit_events",
        ["parent_event_id"], ["event_id"],
        ondelete="RESTRICT",
    )

def downgrade():
    op.drop_constraint("fk_audit_events_parent_event_id", "audit_events", type_="foreignkey")
    op.drop_index("ix_audit_events_external_event_id")
    op.drop_index("ix_audit_events_outcome")
    op.drop_index("ix_audit_events_parent_event_id")
    op.drop_index("ix_audit_events_correlation_id")
    op.drop_column("audit_events", "external_event_id")
    op.drop_column("audit_events", "actor_username_snapshot")
    op.drop_column("audit_events", "source_client")
    op.drop_column("audit_events", "credential_fingerprint")
    op.drop_column("audit_events", "credential_kind")
    op.drop_column("audit_events", "parent_event_id")
    op.drop_column("audit_events", "correlation_id")
    op.drop_column("audit_events", "outcome")
    op.drop_column("audit_events", "event_version")
```

### Миграция 2: `audit_event_resources`

```python
# 0025_add_audit_event_resources.py

def upgrade():
    op.create_table("audit_event_resources",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("audit_event_id", sa.Integer(), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(256), nullable=False),
        sa.Column("relation", sa.String(32), nullable=False),
        sa.Column("snapshot_before", JSONB(), nullable=True),
        sa.Column("snapshot_after", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["audit_event_id"], ["audit_events.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_audit_event_resources_event_id", "audit_event_resources", ["audit_event_id"])
    op.create_index("ix_audit_event_resources_type_id", "audit_event_resources", ["resource_type", "resource_id"])
```

### Миграция 3: `audit_item_effects`

```python
# 0026_add_audit_item_effects.py

def upgrade():
    op.create_table("audit_item_effects",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("audit_event_id", sa.Integer(), nullable=False),
        sa.Column("operation_id", PGUUID(as_uuid=True), nullable=True),
        sa.Column("inventory_subject_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=True),
        sa.Column("item_name_snapshot", sa.String(256), nullable=True),
        sa.Column("item_sku_snapshot", sa.String(128), nullable=True),
        sa.Column("subject_type", sa.String(32), nullable=True),
        sa.Column("site_id", sa.Integer(), nullable=True),
        sa.Column("quantity_before", sa.Numeric(18, 4), nullable=True),
        sa.Column("quantity_delta", sa.Numeric(18, 4), nullable=False),
        sa.Column("quantity_after", sa.Numeric(18, 4), nullable=True),
        sa.Column("effect_type", sa.String(32), nullable=False),
        sa.Column("is_system_generated", sa.Boolean(), server_default="false"),
        sa.Column("caused_by_event_id", sa.Integer(), nullable=True),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        # FK с безопасными ON DELETE
        sa.ForeignKeyConstraint(["audit_event_id"], ["audit_events.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["operation_id"], ["operations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["inventory_subject_id"], ["inventory_subjects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["caused_by_event_id"], ["audit_events.id"], ondelete="RESTRICT"),
    )
    # Индексы
    for col in ["audit_event_id", "inventory_subject_id", "item_id", "site_id", "operation_id", "effect_type"]:
        op.create_index(f"ix_audit_item_effects_{col}", "audit_item_effects", [col])
```

### Миграция 4: `operations` — origin, system_reason, initiated_by_user_id

```python
# 0027_add_operations_origin.py

def upgrade():
    op.add_column("operations", sa.Column("origin", sa.String(16), nullable=True, server_default="user"))
    op.add_column("operations", sa.Column("system_reason", sa.String(32), nullable=True))
    op.add_column("operations", sa.Column("initiated_by_user_id", PGUUID(as_uuid=True), nullable=True))
    
    op.execute("UPDATE operations SET origin = 'user' WHERE origin IS NULL")
    op.alter_column("operations", "origin", nullable=False)
    
    op.create_foreign_key("fk_operations_initiated_by", "operations", "users", ["initiated_by_user_id"], ["id"], ondelete="SET NULL")
```

---

## 12. Изменения в хелпере `record_audit_event()`

**Файл:** `SyncServer/app/services/audit_helper.py`

Новая сигнатура:

```python
async def record_audit_event(
    uow: UnitOfWork,
    *,
    event_type: str,
    actor_user_id: UUID | None,
    actor_device_id: int | None = None,
    site_id: int | None = None,
    entity_type: str,
    entity_id: str,
    summary: str,
    changes: dict | None = None,
    request_id: str | None = None,
    # Новые параметры:
    event_version: int = 2,
    outcome: str | None = None,
    correlation_id: str | None = None,
    parent_event_id: UUID | None = None,
    source_client: str | None = None,
    actor_username_snapshot: str | None = None,
    external_event_id: str | None = None,
) -> AuditEvent:
    # Если correlation_id не передан явно, взять из UoW-контекста (batch)
    if correlation_id is None:
        correlation_id = getattr(uow, 'batch_correlation_id', None)
    
    event = AuditEvent(
        event_type=event_type,
        event_version=event_version,
        actor_user_id=actor_user_id,
        actor_device_id=actor_device_id,
        site_id=site_id,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary,
        changes=changes,
        request_id=request_id,
        outcome=outcome,
        correlation_id=correlation_id,
        parent_event_id=parent_event_id,
        source_client=source_client,
        actor_username_snapshot=actor_username_snapshot,
        external_event_id=external_event_id,
    )
    return await uow.audit_events.insert(event)
```

---

## 13. Изменения в моделях

### 13.1. `AuditEvent` (добавить поля)

**Файл:** `SyncServer/app/models/audit_event.py`

Добавить mapped_column для всех новых полей. `parent_event_id` — ForeignKey на собственную таблицу.

### 13.2. `AuditEventResource` (новая модель)

**Файл:** `SyncServer/app/models/audit_event_resource.py`

### 13.3. `AuditItemEffect` (новая модель)

**Файл:** `SyncServer/app/models/audit_item_effect.py`

### 13.4. `Operation` (добавить поля)

**Файл:** `SyncServer/app/models/operation.py`

Добавить `origin`, `system_reason`, `initiated_by_user_id`.

---

## 14. Изменения в репозитории

**Файл:** `SyncServer/app/repos/audit_events_repo.py`

Добавить методы:

```python
async def insert_resource(self, audit_event_id, resource_type, resource_id, 
                          relation, snapshot_before=None, snapshot_after=None) -> AuditEventResource

async def insert_effect(self, effect: AuditItemEffect) -> AuditItemEffect

async def list_resources(self, audit_event_id: int) -> list[AuditEventResource]

async def list_effects(self, audit_event_id: int) -> list[AuditItemEffect]

async def get_effects_by_item(self, item_id: int, *, site_id=None, 
                               effect_type=None, date_from=None, date_to=None,
                               include_system=True, page=1, page_size=50
                               ) -> tuple[list[AuditItemEffect], int]

async def get_effects_by_subject(self, inventory_subject_id: int, **filters
                                  ) -> tuple[list[AuditItemEffect], int]

async def list_by_correlation_id(self, correlation_id: str) -> list[AuditEvent]

async def list_by_parent_event_id(self, parent_event_id: UUID) -> list[AuditEvent]

async def find_by_external_event_id(self, external_event_id: str) -> AuditEvent | None
```

**Файл:** `SyncServer/app/repos/catalog_repo.py`

Добавить метод:

```python
async def get_items_merged_into(self, target_item_id: int) -> list[Item]:
    """Все ТМЦ, у которых merged_into_id == target_item_id."""
```

---

## 15. Источник `source_client`

`source_client` определяется на уровне API-роута/middleware из заголовка `X-Source-Client` или из identity-контекста.

**Валидация:** допустимые значения — `web`, `desktop`, `mobile`, `cli`. Всё остальное → `"unknown"`.

**Важно:** значение из заголовка не является доверенным (клиент может прислать что угодно). Там, где возможно, следует выводить источник из зарегистрированного устройства. Но в Phase 1 достаточно валидации допустимых значений — для informational purposes.

Django BFF должен выставлять `X-Source-Client: web` при проксировании запросов в SyncServer.

---

## 16. Тестовая стратегия

### 16.1. Repository tests

**Файл:** `SyncServer/tests/test_audit_repo.py` (новый)

- [ ] `test_insert_event_with_new_fields` — запись с event_version=2, outcome, correlation_id
- [ ] `test_insert_resource` — запись resource-связи
- [ ] `test_insert_effect` — запись эффекта с inventory_subject_id
- [ ] `test_list_events_with_outcome_filter`
- [ ] `test_list_events_with_correlation_id`
- [ ] `test_list_by_parent_event_id`
- [ ] `test_list_by_correlation_id`
- [ ] `test_get_effects_by_item`
- [ ] `test_get_effects_by_subject` — эффект для temporary item (item_id=null)
- [ ] `test_append_only_no_update`
- [ ] `test_resource_fk_restrict` — нельзя удалить audit_event с resources

### 16.2. Service integration tests

**Файлы:** `tests/test_audit_operations.py`, `tests/test_audit_catalog_merge.py`, `tests/test_audit_related_merge.py`, `tests/test_audit_batch.py` (новые или расширенные)

- [ ] `test_operation_update_creates_audit` — diff в changes
- [ ] `test_operation_submit_creates_item_effects` — эффекты для каждой строки
- [ ] `test_operation_cancel_creates_reversal_effects` — обратные эффекты
- [ ] `test_item_merge_inserts_parent_first` — **критический**: порядок INSERT (E1 до E2/E3)
- [ ] `test_item_merge_effects_before_reassignment` — **критический**: item_id в эффектах = source, не target
- [ ] `test_item_merge_system_operations_marked` — origin="system"
- [ ] `test_item_merge_resources_linked` — generated → ADJUSTMENT ops
- [ ] `test_category_merge_creates_audit_with_resources` — resource-связи
- [ ] `test_category_merge_items_reparented` — category_changed для каждого item
- [ ] `test_temporary_approve_creates_audit`
- [ ] `test_temporary_merge_creates_audit`
- [ ] `test_review_confirm_creates_audit`
- [ ] `test_review_merge_creates_audit`
- [ ] `test_issue_object_merge_creates_audit`
- [ ] `test_batch_success_creates_audit` — outcome=success
- [ ] `test_batch_partial_creates_audit` — **критический**: outcome=partial при ошибках
- [ ] `test_batch_child_events_have_correlation_id`
- [ ] `test_rollback_audit_with_business_transaction` — ошибка → нет audit
- [ ] `test_item_effects_for_temporary_item` — inventory_subject_id, item_id=null

### 16.3. Stand smoke tests

```bash
# Создать операцию → проверить audit_item_effects
curl -X POST http://localhost:8000/api/v1/.../operations -H ... -d '...'
curl http://localhost:8000/api/v1/admin/audit?page_size=5

# Слить ТМЦ → проверить item.merge + effects + resources
# Проверить, что старые OperationLine перепривязаны, 
# но audit_item_effects.item_id указывает на source
```

### 16.4. Команды проверки

```bash
# Все тесты
cd SyncServer && python -m pytest

# Конкретные файлы
python -m pytest tests/test_audit_repo.py -v
python -m pytest tests/test_audit_operations.py -v
python -m pytest tests/test_audit_catalog_merge.py -v
python -m pytest tests/test_audit_related_merge.py -v
python -m pytest tests/test_audit_batch.py -v

# Миграции
python -m alembic upgrade head
python -m alembic downgrade -1
python -m alembic upgrade head

# Stand
curl http://localhost:8000/api/v1/health
curl http://localhost:8000/api/v1/admin/audit?page_size=5
```

---

## 17. Acceptance criteria (Phase 1: Storage Foundation)

### Критерии сдачи

- [ ] Таблицы `audit_event_resources` и `audit_item_effects` созданы.
- [ ] 4 миграции применяются и откатываются.
- [ ] `audit_events` имеет все новые поля, старые записи (338+) читаются.
- [ ] `operation.update` пишет audit с diff.
- [ ] `category.merge` пишет audit с resource-связями (merge_source, merge_target, reparented, category_changed).
- [ ] `item.merge`: родительское событие создаётся ПЕРВЫМ (до ADJUSTMENT).
- [ ] `item.merge`: audit_item_effects.item_id = source_item_id (не target).
- [ ] `item.merge`: системные ADJUSTMENT имеют `origin="system"`.
- [ ] Temporary / review / issue merge пишут audit.
- [ ] Batch `catalog.batch.apply`: outcome `partial` при наличии ошибок.
- [ ] Batch: дочерние события и batch-событие связаны через `correlation_id`.
- [ ] FK audit-таблиц: `RESTRICT` на доменные сущности, `SET NULL` на users/sites.
- [ ] `inventory_subject_id` в `audit_item_effects` обязателен, `item_id` nullable.
- [ ] `item_name_snapshot`, `item_sku_snapshot`, `subject_type` заполняются.
- [ ] Все тесты проходят.
- [ ] Старые тесты не сломаны.
- [ ] ADR `docs/adr/0012-audit-architecture.md` создан.

### Критерии НЕ проверяются в Phase 1

- Auth outbox / доставка / dedup
- Admin/security события (user.*, device.*, access_scope.*)
- Read API (item history, batch detail)
- CLI-расширения
- `credential_kind`, `credential_fingerprint`, `external_event_id` — поля созданы, но не заполняются

---

## 18. Документация

| Файл | Действие |
|------|----------|
| `docs/adr/0012-audit-architecture.md` | Создать |
| `docs/audit-event-catalog.md` | Создать (таблица из секции 8) |
| `SyncServer/README.md` | Обновить секцию аудита |

ADR фиксирует:
- SyncServer как источник истины
- `audit_events` как append-only
- Разделение бизнес-аудита и телеметрии
- Атомарность успешных событий
- Модель эффектов: один эффект = одно изменение остатка
- Merge closure вместо canonical_item_id
- FK-политику RESTRICT/SET NULL
- Порядок INSERT при merge
- Механизм correlation_id для batch

---

## 19. Риски и решения

| Риск | Решение |
|------|---------|
| Merge closure не performantен при глубоких цепочках | Цепочки merge короткие (1-3 уровня). Если станет проблемой — материализовать closure в отдельную таблицу. |
| `RESTRICT` FK мешает удалению ТМЦ | Удаление деактивированной ТМЦ с историей — редкая операция. Если понадобится — `SET NULL` с сохранением snapshot-полей. |
| `item.merge` с INSERT-FLUSH-первым увеличивает окно транзакции | Окно не увеличивается — UoW и так открыт. flush только присваивает ID. |
| Batch с `correlation_id` через UoW-контекст — неявная связь | Явная, но легковесная. При рефакторинге batch в будущем легко заменить на явный параметр. |

---

## 20. Явно отложенное (Phase 2)

Всё перечисленное НЕ входит в данный scope:

- **Auth outbox:** Django `AuditOutbox` модель, `deliver_audit_outbox` команда, SyncServer `POST /system/audit-event`, retry/dedup
- **Admin/security события:** `user.create/update/deactivate/token_rotate`, `device.*`, `access_scope.*`, `site.*`
- **Read API:** `GET /admin/audit/items/{id}/history`, `GET /admin/audit/batch/{id}`, расширенные фильтры списка
- **CLI:** новые команды `item-history`, `event`, `batch`, `--token-stdin`
- **Credential fingerprinting:** заполнение `credential_kind`/`credential_fingerprint`
- **Retention cleanup:** management-команды очистки
- **Frontend:** Angular, Django templates, CSS — все экраны и визуализации

---

## 21. Решения, которые MiniMax не имеет права принимать самостоятельно

- Удаление старых audit-записей
- Хранение полных токенов
- Изменение транзакционной стратегии batch (НЕ делать savepoint-стратегию)
- Переход на event sourcing
- Замена `audit_events` на другую систему
- Изменение FK-политики (должно быть RESTRICT для audit-таблиц)
- Добавление Celery или других брокеров
- Изменение структуры `items`, `categories`, `units` (кроме оговорённых полей `operations`)
- Commit без прохождения тестов
- Push кода

---

## 22. Рекомендуемая последовательность локальных коммитов

1. `feat(audit): add audit_event_resources and audit_item_effects models with safe FKs`
2. `feat(audit): extend audit_events with new fields and event_version=2`
3. `feat(audit): add operations.origin, system_reason, initiated_by_user_id`
4. `feat(audit): add operation.update audit with diff`
5. `feat(audit): add category.merge audit with resource links`
6. `feat(audit): fix item.merge order — parent event first, effects before reassignment`
7. `feat(audit): add audit for temporary, review, issue object merge`
8. `feat(audit): add catalog.batch.apply audit with partial outcome`
9. `test(audit): repository and service integration tests`
10. `docs(audit): ADR-0012, event catalog, README update`

---

## 23. Итоговый Definition of Done (Phase 1)

- [ ] 4 миграции созданы, применяются и откатываются
- [ ] 20 типов событий записываются (operations 6 + catalog 8 + related 5 + batch 1)
- [ ] `item.merge`: эффекты записаны до перепривязки OperationLine
- [ ] Системные ADJUSTMENT-операции отмечены `origin="system"`
- [ ] Batch: outcome `partial` при ошибках, корреляция через `correlation_id`
- [ ] FK RESTRICT/SET NULL на audit-таблицах
- [ ] `inventory_subject_id` обязателен, `item_id` nullable
- [ ] Snapshot-поля заполняются для эффектов
- [ ] Все тесты проходят (≥25 тестов)
- [ ] Старые тесты не сломаны
- [ ] Stand smoke: создание операции → audit, merge → audit
- [ ] ADR + каталог событий написаны
- [ ] Все локальные коммиты сделаны (без push)
