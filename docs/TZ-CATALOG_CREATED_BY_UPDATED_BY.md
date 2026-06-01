# TZ: Поля created_by_user_id / updated_by_user_id в справочниках каталога

## Execution Strategy

- [x] 🟢 Parallel execution recommended
- **Reason:** Три уровня изменений независимы после миграции: модели/миграция (Stage 0), сервисы (Stage 1-A), API + схемы (Stage 1-B). Тесты (Stage 2) можно вести параллельно по файлам.

## Execution Checklist

- [ ] 0. Context verified
- [ ] 1. Stage 0: Модели + миграция Alembic
- [ ] 2. Stage 1-A: Сервис `CatalogAdminService` — параметры `created_by_user_id` / `updated_by_user_id`
- [ ] 3. Stage 1-B: API-роуты + Pydantic-схемы ответов
- [ ] 4. Stage 2-A: Unit/component tests (модели + сервисы)
- [ ] 5. Stage 2-B: Integration tests (DB-backed, catalog CRUD)
- [ ] 6. Stand smoke tests (SyncServer + PostgreSQL)
- [ ] 7. Regression checks
- [ ] 8. Documentation updated
- [ ] 9. Final acceptance review complete

---

## 1. Цель

Добавить в модели справочников каталога (`Item`, `Category`, `Unit`) поля аудита:
- `created_by_user_id` — кто создал запись
- `updated_by_user_id` — кто последним изменил запись

При миграции существующие записи должны получить `created_by_user_id = root_user.id` и `updated_by_user_id = root_user.id`.

---

## 2. Область изменений

### 2.1. Входит в scope

| Файл | Что меняется |
|---|---|
| `SyncServer/app/models/item.py` | +2 колонки: `created_by_user_id`, `updated_by_user_id` |
| `SyncServer/app/models/category.py` | +2 колонки: `created_by_user_id`, `updated_by_user_id` |
| `SyncServer/app/models/unit.py` | +2 колонки: `created_by_user_id`, `updated_by_user_id` |
| `SyncServer/alembic/versions/` | Новая миграция `0011_add_catalog_created_by_updated_by.py` |
| `SyncServer/app/services/catalog_admin_service.py` | Параметры `created_by_user_id` / `updated_by_user_id` в методах `create_*` и `update_*` |
| `SyncServer/app/api/routes_catalog_admin.py` | Передача `identity.user_id` в create/update-эндпоинты |
| `SyncServer/app/schemas/catalog.py` | Поля в `UnitResponse`, `CategoryResponse`, `ItemResponse` |

### 2.2. Не входит в scope

- `TemporaryItem` — уже имеет `created_by_user_id` (review-трекинг), не трогаем.
- `InventorySubject` — служебная связка, не трогаем.
- Изменение клиентских проектов (`Warehouse_web`, `Warehouse_frontend`) — только если сломаются тесты.
- `deleted_by_user_id` — уже есть, не трогаем.

---

## 3. Детали реализации

### 3.0. Параллельная декомпозиция

```
Stage 0 (один исполнитель, блокирует Stage 1):
  └── Модели + миграция Alembic
       ├── item.py (+2 поля)
       ├── category.py (+2 поля)
       ├── unit.py (+2 поля)
       └── alembic/versions/0011_*.py (новая миграция)

Stage 1 (два исполнителя, параллельно):
  ├── 1-A: CatalogAdminService (параметры методов)
  └── 1-B: API роуты + Pydantic-схемы

Stage 2 (два исполнителя, параллельно):
  ├── 2-A: Unit/component tests
  └── 2-B: Stand smoke + regression
```

**Правило:** Stage 1-A и 1-B не конфликтуют по файлам. Stage 0 должен быть завершён до Stage 1.

---

### 3.1. Stage 0 — Модели

#### Item (`SyncServer/app/models/item.py`)

Добавить **после** `deleted_by_user_id` (строка 79):

```python
created_by_user_id: Mapped[UUID | None] = mapped_column(
    PGUUID(as_uuid=True),
    ForeignKey("users.id"),
    nullable=True,
)
updated_by_user_id: Mapped[UUID | None] = mapped_column(
    PGUUID(as_uuid=True),
    ForeignKey("users.id"),
    nullable=True,
)
```

#### Category (`SyncServer/app/models/category.py`)

Добавить **после** `deleted_by_user_id` (строка 53):

```python
created_by_user_id: Mapped[UUID | None] = mapped_column(
    PGUUID(as_uuid=True),
    ForeignKey("users.id"),
    nullable=True,
)
updated_by_user_id: Mapped[UUID | None] = mapped_column(
    PGUUID(as_uuid=True),
    ForeignKey("users.id"),
    nullable=True,
)
```

#### Unit (`SyncServer/app/models/unit.py`)

Добавить **после** `deleted_by_user_id` (строка 39):

```python
created_by_user_id: Mapped[UUID | None] = mapped_column(
    PGUUID(as_uuid=True),
    ForeignKey("users.id"),
    nullable=True,
)
updated_by_user_id: Mapped[UUID | None] = mapped_column(
    PGUUID(as_uuid=True),
    ForeignKey("users.id"),
    nullable=True,
)
```

**Почему nullable:** системные категории (например, «Без категории») и машинный импорт (batch без пользователя) не имеют идентификатора пользователя-создателя. При миграции существующие записи заполняются root-пользователем явно.

---

### 3.2. Stage 0 — Миграция Alembic

**Новый файл:** `SyncServer/alembic/versions/0011_add_catalog_created_by_updated_by.py`

**Revises:** `0010_add_item_review_fields`

**Шаги `upgrade()`:**

1. `op.add_column("items", sa.Column("created_by_user_id", sa.UUID(), nullable=True))`
2. `op.add_column("items", sa.Column("updated_by_user_id", sa.UUID(), nullable=True))`
3. Аналогично для `categories` и `units` (6 колонок total).

4. **Data migration** — найти root-пользователя и заполнить:
```python
conn = op.get_bind()
# Найти первого root-пользователя (is_root=true)
root_user = conn.execute(
    sa.text("SELECT id FROM users WHERE is_root = true ORDER BY created_at ASC LIMIT 1")
).fetchone()

if root_user is not None:
    root_id = root_user[0]
    for table in ("items", "categories", "units"):
        conn.execute(
            sa.text(f"UPDATE {table} SET created_by_user_id = :uid, updated_by_user_id = :uid WHERE created_by_user_id IS NULL"),
            {"uid": root_id},
        )
```

5. **Foreign Keys:**
```python
op.create_foreign_key("fk_items_created_by_user", "items", "users", ["created_by_user_id"], ["id"])
op.create_foreign_key("fk_items_updated_by_user", "items", "users", ["updated_by_user_id"], ["id"])
op.create_foreign_key("fk_categories_created_by_user", "categories", "users", ["created_by_user_id"], ["id"])
op.create_foreign_key("fk_categories_updated_by_user", "categories", "users", ["updated_by_user_id"], ["id"])
op.create_foreign_key("fk_units_created_by_user", "units", "users", ["created_by_user_id"], ["id"])
op.create_foreign_key("fk_units_updated_by_user", "units", "users", ["updated_by_user_id"], ["id"])
```

6. **Индексы** (опционально, для ускорения фильтрации):
```python
op.create_index("ix_items_created_by_user_id", "items", ["created_by_user_id"])
op.create_index("ix_categories_created_by_user_id", "categories", ["created_by_user_id"])
op.create_index("ix_units_created_by_user_id", "units", ["created_by_user_id"])
```

**Шаги `downgrade()`:** обратный порядок — дропнуть FK, индексы, колонки.

---

### 3.3. Stage 1-A — Сервис `CatalogAdminService`

**Файл:** `SyncServer/app/services/catalog_admin_service.py`

#### Сигнатуры методов — добавить параметры:

| Метод | Добавить параметр | Куда пишется |
|---|---|---|
| `create_unit(uow, payload)` | `+ created_by_user_id: UUID \| None = None` | `unit.created_by_user_id` |
| `update_unit(uow, unit_id, payload)` | `+ updated_by_user_id: UUID \| None = None` | `unit.updated_by_user_id` **перед** `uow.catalog.update_unit(unit)` |
| `create_category(uow, payload)` | `+ created_by_user_id: UUID \| None = None` | `category.created_by_user_id` |
| `update_category(uow, category_id, payload)` | `+ updated_by_user_id: UUID \| None = None` | `category.updated_by_user_id` |
| `create_item(uow, payload)` | Уже есть `created_by_user_id` — **переиспользовать** для аудита (не только review) | `item.created_by_user_id` |
| `update_item(uow, item_id, payload)` | `+ updated_by_user_id: UUID \| None = None` | `item.updated_by_user_id` |

**Важно для `create_item`:** сейчас параметр `created_by_user_id` используется **только** для `review_created_by_user_id` (строка 204). Нужно разделить:
- `item.created_by_user_id = created_by_user_id` — всегда, для аудита
- `item.review_created_by_user_id = created_by_user_id if payload.requires_review else None` — только для review

**Паттерн вставки в update-методах** (единый для всех трёх сущностей):
```python
# В update_unit / update_category / update_item — после всех проверок, перед вызовом repo:
if updated_by_user_id is not None:
    unit.updated_by_user_id = updated_by_user_id  # (или category/item)
```

**Метод `_get_or_create_uncategorized_category`** (строка 274): создаёт системную категорию без пользователя. Оставить `created_by_user_id = None` — это системная запись.

---

### 3.4. Stage 1-B — API роуты

**Файл:** `SyncServer/app/api/routes_catalog_admin.py`

Во все create/update эндпоинты добавить передачу `identity.user_id`:

| Эндпоинт | Текущий вызов | Новый вызов |
|---|---|---|
| `create_unit` (строка 58) | `service.create_unit(uow, payload)` | `service.create_unit(uow, payload, created_by_user_id=identity.user_id)` |
| `update_unit` (строка 91) | `service.update_unit(uow, unit_id, payload)` | `service.update_unit(uow, unit_id, payload, updated_by_user_id=identity.user_id)` |
| `create_category` (строка 107) | `service.create_category(uow, payload)` | `service.create_category(uow, payload, created_by_user_id=identity.user_id)` |
| `update_category` (строка 150) | `service.update_category(uow, category_id, payload)` | `service.update_category(uow, category_id, payload, updated_by_user_id=identity.user_id)` |
| `create_item` (строка 171) | `service.create_item(uow, payload)` | `service.create_item(uow, payload, created_by_user_id=identity.user_id)` |
| `update_item` (строка ~185) | `service.update_item(uow, item_id, payload)` | `service.update_item(uow, item_id, payload, updated_by_user_id=identity.user_id)` |

**Bulk-эндпоинты** (`bulk_create_units`, `bulk_create_categories`): они вызывают `create_unit`/`create_category` в цикле — нужно прокинуть `created_by_user_id` через `bulk_create_units`/`bulk_create_categories`.

**Batch-эндпоинт** (`apply_catalog_batch`): уже передаёт `identity` в `service.apply_batch()`. Внутри `_apply_unit_change`, `_apply_category_change`, `_apply_item_change` уже получают `user_id` — нужно использовать его для `created_by_user_id`/`updated_by_user_id` в вызовах create/update.

---

### 3.5. Схемы ответов (Pydantic)

**Файл:** `SyncServer/app/schemas/catalog.py`

Добавить в каждый Response:

| Класс | Добавить поля |
|---|---|
| `UnitResponse` | `created_by_user_id: UUID \| None = None`<br>`updated_by_user_id: UUID \| None = None` |
| `CategoryResponse` | `created_by_user_id: UUID \| None = None`<br>`updated_by_user_id: UUID \| None = None` |
| `ItemResponse` | `created_by_user_id: UUID \| None = None`<br>`updated_by_user_id: UUID \| None = None` |

**Важно:** `ItemResponse` уже имеет `review_created_by_user_id` — это другое поле, не путать.

**Порядок полей:** группировать audit-поля вместе с `created_at`, `updated_at`, `deleted_at`, `deleted_by_user_id`.

---

## 4. Тестовая стратегия

### 4.1. Static checks (уровень 1)

```bash
cd SyncServer && python -m pytest --collect-only  # проверка, что импорты не сломаны
```

### 4.2. Unit tests (уровень 2)

Проверить, что:
- Модели принимают `created_by_user_id` / `updated_by_user_id` при создании экземпляра
- Сервисные методы записывают поля при вызове с `user_id` и не падают при `None`

### 4.3. Integration tests (уровень 4)

**Файлы тестов (если существуют):**
- `SyncServer/tests/test_catalog_admin_service.py`
- `SyncServer/tests/test_catalog_api.py`

**Проверить:**
1. `create_unit` с `created_by_user_id` → поле сохранено в БД
2. `create_category` с `created_by_user_id` → поле сохранено
3. `create_item` с `created_by_user_id` → поле сохранено (и review-поля не затираются)
4. `update_unit` с `updated_by_user_id` → поле обновлено
5. `update_category` с `updated_by_user_id` → поле обновлено
6. `update_item` с `updated_by_user_id` → поле обновлено
7. Создание/обновление **без** `user_id` → поля остаются `None`, ошибок нет

### 4.4. Stand smoke tests (уровень 5)

**Стенд:** Docker, `SyncServer` + PostgreSQL.

**Сценарий:**
1. `POST /api/v1/catalog/admin/units` с X-User-Token root → в ответе есть `created_by_user_id = root.id`
2. `PATCH /api/v1/catalog/admin/units/{id}` → в ответе есть `updated_by_user_id = root.id`
3. Аналогично для categories и items
4. `GET /api/v1/catalog/admin/units` → список содержит поля

### 4.5. Regression (уровень 8)

- `python -m pytest` — полный прогон существующих тестов
- Проверить, что batch-операции не сломаны
- Проверить, что bulk-операции не сломаны

### 4.6. UI automation (уровень 6)

Не применимо — изменения на бэкенде, UI не затрагивается (поля API-ответов обратно совместимы — новые nullable поля).

---

## 5. Acceptance criteria

- [ ] В таблицах `items`, `categories`, `units` есть колонки `created_by_user_id` и `updated_by_user_id` с FK на `users.id`
- [ ] Все существующие записи (до миграции) имеют `created_by_user_id = root_user.id`
- [ ] API create-эндпоинты возвращают `created_by_user_id` в ответе
- [ ] API update-эндпоинты возвращают `updated_by_user_id` в ответе
- [ ] Существующие тесты проходят без изменений (кроме ожидаемых обновлений фикстур)
- [ ] Миграция проходит `upgrade` → `downgrade` → `upgrade` без ошибок

---

## 6. Риски

| Риск | Вероятность | Митигация |
|---|---|---|
| Сломаются тесты, ожидающие старую схему ответа | Средняя | Поля nullable — `model_validate` не требует их наличия |
| Конфликт имён `created_by_user_id` в Item (review vs audit) | Низкая | Явно разделить: `item.created_by_user_id` (аудит) vs `item.review_created_by_user_id` (review) |
| Batch/bulk не передают user_id | Средняя | Проверить цепочку вызовов, добавить параметры в bulk-методы |
| Root-пользователь не найден при миграции | Низкая | Миграция проверяет `if root_user is not None`; если нет — колонки остаются NULL |
| Машинный импорт (machine batches) создаёт записи без пользователя | Низкая | Поля nullable, системные/машинные создания оставляют NULL |

---

## 7. Порядок выполнения (Sequential stages)

```
Stage 0: Модели + миграция     [1 исполнитель, блокирует Stage 1]
    ↓
Stage 1-A: Сервис              ─┐
Stage 1-B: API + схемы         ─┤ параллельно
    ↓                           ↓
Stage 2-A: Unit/component tests ─┐
Stage 2-B: Stand smoke           ─┤ параллельно
    ↓
Regression + Acceptance
```
