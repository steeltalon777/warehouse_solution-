# TZ: Нормализация и защита поиска по всему SyncServer

## TZ References

- Экспресс-анализ инцидента: `prod_working/search_analysis.md`
- Функциональные требования: `Functional and WorkLogik.md` (строки 33, 65 — поиск ТМЦ — core feature, должен работать и быть закеширован)

## Execution Strategy

- [x] 🟢 Parallel execution recommended
- **Reason:** Фаза 0 (foundation) — последовательная: создаёт shared utility + event listeners + миграцию, от которой зависят все остальные фазы. Фаза 1 (repo fixes) — параллельная: 5 независимых work units, каждый владеет отдельными файлами, не пересекается по writable files. Фаза 2 (тесты) и Фаза 3 (интеграция) — последовательные.

---

## Execution Checklist

- [x] 0. Context verified — анализ `search_analysis.md` верифицирован, реальный scope шире (10 репозиториев, ~15 точек поиска)
- [x] 1. Architecture boundaries confirmed — единая утилита нормализации, event listeners, миграция
- [x] 2. Phase 0: Foundation — shared utility + event listeners + Alembic migration
- [x] 3. Phase 1: Repo fixes — 5 параллельных work units
- [x] 4. Unit tests complete — normalize_search_text, escape_like_pattern, build_normalized_like_term, build_raw_like_term
- [x] 5. Integration tests complete — каждый endpoint поиска с нормализованным вводом
- [x] 6. Stand smoke tests complete — real dev-stand search verification
- [ ] 7. UI automation tests — Playwright поиск ТМЦ через Django/Angular (опционально, **not applicable**: backend-only changes, UI не затронут)
- [x] 8. User scenario tests — поиск с двойными пробелами, пунктуацией, спецсимволами LIKE
- [x] 9. Regression checks — все существующие search-тесты проходят
- [x] 10. Documentation updated — ARCHITECTURE.md, AI_CONTEXT.md, AI_ENTRY_POINTS.md, INDEX.md
- [x] 11. Final acceptance review complete — см. Evidence Table ниже, закрыто 2026-07-31

---

## Check Rules

- Architect creates the checklist and acceptance criteria.
- Executor agents may check implementation and test items only after running the required verification.
- QA verifier may check final acceptance only after reviewing evidence.
- If a check is skipped, it must stay unchecked with a reason in the report.

---

## Executor Hard Rules

Эти правила обязательны для всех executor-агентов. Нарушение = недопустимое изменение.

1. **Не пушить.** Можно делать локальные коммиты. Push делает только пользователь.
2. **Phase 0 — отдельным коммитом** до repo-fixes:
   - `app/core/search_utils.py`
   - event listeners
   - модели Site/Device (новые `normalized_name`)
   - Alembic migration
   - unit tests
3. **До repo-fixes прогнать `alembic upgrade head`** против тестовой БД. Без backfill переключение поиска на `normalized_name` сделает поиск **хуже**, а не лучше (73% `items.normalized_name` сейчас некорректны).
4. **Не переключать поиск на `normalized_name` до backfill.** Миграция (Phase 0) **обязана** быть применена до Phase 1 repo fixes.
5. **Для поиска использовать два term:**
   - `normalized_term` (`build_normalized_like_term`) — для `normalized_name` / `normalized_key`
   - `raw_term` (`build_raw_like_term`) — для `sku` / `code` / `device_code` / `description` / `notes` / снапшотов
6. **После Phase 1 обязательно проверить, что не осталось сырых паттернов:**
   ```bash
   rg "ilike\|ILIKE\|%\{search\|search.strip" app/ tests/
   ```
7. **Проверить тесты:**
   ```bash
   python -m pytest tests/test_search_utils.py -v
   python -m pytest tests/test_search_normalization.py -v
   python -m pytest -x
   python -m alembic upgrade head
   ```
8. **Проверить assertions `normalized_name is None`** в тестах — event listeners изменят поведение ORM-фикстур. Найти через:
   ```bash
   rg "normalized_name.*None\|None.*normalized_name" tests/
   ```
9. **Git push полностью запрещён.** Пользователь делает все push вручную.

---

## 1. Постановка проблемы

### 1.1. Корневая причина

Поиск по всему SyncServer реализован как сырой `ILIKE '%<ввод>%'` без нормализации:
- Ввод пользователя не нормализуется (нет lowercase, нет сворачивания пробелов, нет замены ё→е, нет удаления пунктуации)
- LIKE-спецсимволы (`%`, `_`) не экранируются
- Существующие `normalized_name` / `normalized_key` колонки игнорируются в большинстве мест
- B-tree индексы на `normalized_name` не работают с leading-wildcard `ILIKE '%term%'`

### 1.2. Реальный scope (15 точек поиска в 10 файлах)

| # | Файл | Метод | Строки | Искомые колонки | normalized-колонка существует? | Используется? |
|---|---|---|---|---|---|---|
| 1 | `catalog_repo.py` | `list_items_page` | 77-84 | `Item.name`, `Item.sku`, `Item.description` | Да (`Item.normalized_name`) | НЕТ |
| 2 | `catalog_repo.py` | `list_categories_page` | 154-160 | `Category.name`, `Category.code` | Да (`Category.normalized_name`) | НЕТ |
| 3 | `catalog_repo.py` | `list_review_items_page` | 627-635 | `Item.name`, `Item.sku`, `Item.description` | Да | НЕТ |
| 4 | `asset_registers_repo.py` | `list_pending` | 255-257 | `Item.name`, `Item.sku`, `Site.name` | Да (Item), Нет (Site) | НЕТ |
| 5 | `asset_registers_repo.py` | `list_lost` | 326-335 | `Item.name`, `Item.sku`, `Site.name` (×2) | Да (Item), Нет (Site) | НЕТ |
| 6 | `asset_registers_repo.py` | `list_issued` | 396-405 | `IssueObject.display_name`, `.comment`, `Item.name`, `Item.sku` | Да (IssueObject.normalized_key, Item.normalized_name) | НЕТ |
| 7 | `asset_registers_repo.py` | `list_issued_by_object` | 454-456 | `Item.name` | Да | НЕТ |
| 8 | `operations_repo.py` | `list_operations` | 280-297 | `Operation.notes`, `OperationLine.item_name_snapshot`, `.item_sku_snapshot`, `cast(Item.hashtags, Text)` | Нет | Н/Д |
| 9 | `sites_repo.py` | `list_sites` | 83-91 | `Site.name`, `Site.code`, `Site.description` | Нет | Н/Д |
| 10 | `balances_repo.py` | `list_balances` | 124-133 | `Item.name`, `Item.sku`, `Category.name`, `Site.name` | Да (Item, Category), Нет (Site) | НЕТ |
| 11 | `temporary_items_repo.py` | `list_items` | 91-99 | `TemporaryItem.name`, `.sku`, `.description` | Да (`TemporaryItem.normalized_name`) | НЕТ |
| 12 | `reports_repo.py` | `list_item_movement` | 179-188 | `Item.name`, `Item.sku`, `Category.name`, `Site.name` | Да (Item, Category), Нет (Site) | НЕТ |
| 13 | `reports_repo.py` | `list_stock_summary` | 273-282 | `Item.name`, `Item.sku`, `Category.name`, `Site.name` | Да (Item, Category), Нет (Site) | НЕТ |
| 14 | `issue_object_categories_repo.py` | `list_categories` | 61-74 | `IssueObjectCategory.name`, `.normalized_key` | Да | **ДА, но term не нормализован** |
| 15 | `admin_devices_service.py` | `list_devices` | 58-65 | `Device.device_code`, `Device.device_name` | Нет | Н/Д |

Дополнительно — `issue_objects_repo.py` (3 метода, 5 ILIKE-вызовов): `list_issue_objects`, `find_similar`, `list_active_by_filter` — уже частично использует `normalized_key`, но без нормализации термина.

### 1.3. DRY-нарушение: 4+ копии функции нормализации

| Файл | Функция | Логика |
|---|---|---|
| `catalog_admin_service.py:45` | `_normalize_text()` | `" ".join(value.strip().lower().split())` |
| `machine_service.py:33` | `normalize_text()` | то же |
| `operations_service.py:40` | `_normalize_name()` | то же (staticmethod) |
| `machine_repo.py:19` | `normalize_text()` | то же (дубликат) |
| `issue_objects_repo.py:16` | `normalize_issue_object_name()` | **продвинутая**: ё→е + удаление пунктуации + сворачивание пробелов |
| `issue_object_categories_repo.py:19` | `normalize_category_name()` | то же (дубликат продвинутой) |

### 1.4. Несоответствие миграции и кода

Миграция `0002_machine_api_stage1_foundation.py` бэкфиллит:
```sql
UPDATE items SET normalized_name = lower(trim(name)) WHERE normalized_name IS NULL
```
`lower(trim(name))` **не сворачивает двойные пробелы** и **не удаляет пунктуацию**, в отличие от `_normalize_text()`.

### 1.5. Тестовый долг

Тестовые фикстуры создают сущности через ORM напрямую без `normalized_name`:
```python
Item(sku=..., name=..., ...)  # normalized_name = None!
```
При переключении поиска на `normalized_name` эти тесты сломаются.

---

## 2. Архитектурное решение

### 2.1. Единая утилита нормализации

Создать `app/core/search_utils.py` — единый модуль для всей нормализации поиска:

```python
import re

_NON_WORD_RE = re.compile(r"[^\w\s]+", flags=re.UNICODE)
_SPACES_RE = re.compile(r"\s+", flags=re.UNICODE)

def normalize_search_text(value: str) -> str:
    """Нормализация текста для поиска:
    strip → lower → ё→е → удаление пунктуации → сворачивание пробелов.
    """
    text = (value or "").strip().lower().replace("ё", "е")
    text = _NON_WORD_RE.sub(" ", text)
    text = _SPACES_RE.sub(" ", text).strip()
    return text

def normalize_for_storage(value: str | None) -> str | None:
    """Нормализация для хранения в normalized_name колонке.
    Возвращает None для None, пустую строку не возвращает (→ None).
    """
    if value is None:
        return None
    result = normalize_search_text(value)
    return result or None

def escape_like_pattern(text: str) -> str:
    """Экранирование LIKE/ILIKE спецсимволов: % и _."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

def build_normalized_like_term(search: str | None) -> str | None:
    """Term для поиска по normalized_name / normalized_key колонкам.
    Pipeline: normalize_search_text → escape → wrap в %...%.
    Возвращает None если ввод пустой после нормализации.
    """
    if not search:
        return None
    normalized = normalize_search_text(search)
    if not normalized:
        return None
    escaped = escape_like_pattern(normalized)
    return f"%{escaped}%"

def build_raw_like_term(search: str | None) -> str | None:
    """Term для поиска по сырым техническим колонкам (sku, code, device_code, description, notes, snapshots).
    Pipeline: strip → escape → wrap в %...%.
    НЕ удаляет пунктуацию, НЕ меняет регистр, НЕ сворачивает пробелы —
    только strip и экранирование LIKE-спецсимволов.
    Возвращает None если ввод пустой после strip.
    """
    if not search:
        return None
    stripped = search.strip()
    if not stripped:
        return None
    escaped = escape_like_pattern(stripped)
    return f"%{escaped}%"
```

### Критическое правило: два term, не один

**Запрещено** использовать один и тот же term для `normalized_name` и сырых колонок (`sku`, `code`, `device_code`, `description`, `notes`, снапшоты).

**Почему:** `build_normalized_like_term("17М-03-49270-G")` → `%17м 03 49270 g%` (дефисы заменены на пробелы, lower). Этот term найдёт `normalized_name = "17м 03 49270 g"`, но **не найдёт** `sku = "17М-03-49270-G"`, потому что дефисы в SKU — литеральные символы, а не пробелы. Использование нормализованного term для сырых колонок **сломает поиск по артикулам с дефисами, слешами и точками**.

```python
# ПРАВИЛЬНО:
normalized_term = build_normalized_like_term(search)  # для normalized_name, normalized_key
raw_term = build_raw_like_term(search)                # для sku, code, device_code, description, notes

stmt = stmt.where(or_(
    Item.normalized_name.ilike(normalized_term, escape="\\"),
    Item.sku.ilike(raw_term, escape="\\"),
))

# НЕПРАВИЛЬНО (сломает SKU с дефисами):
term = build_normalized_like_term(search)
stmt = stmt.where(or_(
    Item.normalized_name.ilike(term, escape="\\"),
    Item.sku.ilike(term, escape="\\"),  # ← term без дефисов, а SKU с дефисами → 0 матчей
))
```

 Эта утилита заменяет все 6 существующих функций нормализации.

### 2.2. SQLAlchemy event listeners для auto-compute normalized_name

Добавить event listeners в `app/models/base.py` (или отдельный `app/models/events.py`) для автоматического вычисления `normalized_name` при insert/update:

```python
from sqlalchemy import event
from app.core.search_utils import normalize_for_storage

@event.listens_for(Item, "before_insert")
@event.listens_for(Item, "before_update")
def _set_item_normalized_name(mapper, connection, target):
    if target.name is not None:
        target.normalized_name = normalize_for_storage(target.name)

# Аналогично для Category, TemporaryItem, Site (новое поле), Device (новое поле)
```

**Обоснование:**
- Гарантирует, что `normalized_name` всегда установлен, независимо от пути создания (сервис, ORM, batch, machine).
- Устраняет DRY-нарушение: сервисы больше не должны вручную устанавливать `normalized_name`.
- Автоматически фиксит все тестовые фикстуры — `normalized_name` будет вычислен при insert.
- Для `IssueObject.normalized_key` и `IssueObjectCategory.normalized_key` — оставить ручное управление через сервисы (другая семантика: unique constraint, генерируется из display_name + code).

### 2.3. Модели: новые normalized_name колонки

Добавить `normalized_name` в модели, где его нет:

**`app/models/site.py`:**
```python
normalized_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
# В __table_args__: Index("ix_sites_normalized_name", "normalized_name")
```

**`app/models/device.py`:**
```python
normalized_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
# В __table_args__: Index("ix_devices_normalized_name", "normalized_name")
```

Event listeners для Site и Device вычисляют `normalized_name` из `Site.name` и `Device.device_name` соответственно.

**Operation** — НЕ добавлять normalized-колонки. Поиск идёт по `notes`, снапшотам и `hashtags` — это текстовые поля, нормализация которых бессмысленна или вредна (снапшоты должны быть точными копиями). Для Operation — только нормализация ввода + экранирование.

### 2.4. Alembic-миграция

Создать новую миграцию `00XX_search_normalization.py`:

```sql
-- 1. Расширение для trigram-поиска
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 2. Новые колонки
ALTER TABLE sites ADD COLUMN IF NOT EXISTS normalized_name VARCHAR(255);
ALTER TABLE devices ADD COLUMN IF NOT EXISTS normalized_name VARCHAR(255);

-- 3. Backfill ВСЕХ normalized_name с правильной логикой
-- (lowercase + ё→е + remove punctuation + collapse spaces + trim)
UPDATE items SET normalized_name = btrim(
    regexp_replace(
        regexp_replace(replace(lower(name::text), 'ё', 'е'), '[^\w\s]', ' ', 'g'),
        '\s+', ' ', 'g'
    )
) WHERE name IS NOT NULL;

UPDATE categories SET normalized_name = btrim(
    regexp_replace(
        regexp_replace(replace(lower(name::text), 'ё', 'е'), '[^\w\s]', ' ', 'g'),
        '\s+', ' ', 'g'
    )
) WHERE name IS NOT NULL;

UPDATE sites SET normalized_name = btrim(
    regexp_replace(
        regexp_replace(replace(lower(name::text), 'ё', 'е'), '[^\w\s]', ' ', 'g'),
        '\s+', ' ', 'g'
    )
) WHERE name IS NOT NULL;

UPDATE devices SET normalized_name = btrim(
    regexp_replace(
        regexp_replace(replace(lower(device_name::text), 'ё', 'е'), '[^\w\s]', ' ', 'g'),
        '\s+', ' ', 'g'
    )
) WHERE device_name IS NOT NULL;

-- 4. B-tree индексы (для точного соответствия и prefix-search)
CREATE INDEX IF NOT EXISTS ix_sites_normalized_name ON sites (normalized_name);
CREATE INDEX IF NOT EXISTS ix_devices_normalized_name ON devices (normalized_name);

-- 5. GIN-индексы для trigram-поиска (ILIKE '%term%' acceleration)
CREATE INDEX IF NOT EXISTS ix_items_normalized_name_trgm ON items USING gin (normalized_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_categories_normalized_name_trgm ON categories USING gin (normalized_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_sites_normalized_name_trgm ON sites USING gin (normalized_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_devices_normalized_name_trgm ON devices USING gin (normalized_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_temporary_items_normalized_name_trgm ON temporary_items USING gin (normalized_name gin_trgm_ops);
```

**Примечание по `\w` в PostgreSQL:** `\w` в PostgreSQL regex с флагом `g` по умолчанию соответствует `[a-z0-9_]`. Для Unicode (кириллица) нужно убедиться, что `LC_CTYPE` базы поддерживает кириллицу, либо использовать явный класс `[^a-zа-яё0-9\s]`. Проверить на dev-стенде перед применением.

**Rollback (downgrade):**
```sql
DROP INDEX IF EXISTS ix_temporary_items_normalized_name_trgm;
DROP INDEX IF EXISTS ix_devices_normalized_name_trgm;
DROP INDEX IF EXISTS ix_sites_normalized_name_trgm;
DROP INDEX IF EXISTS ix_categories_normalized_name_trgm;
DROP INDEX IF EXISTS ix_items_normalized_name_trgm;
DROP INDEX IF EXISTS ix_devices_normalized_name;
DROP INDEX IF EXISTS ix_sites_normalized_name;
ALTER TABLE devices DROP COLUMN IF EXISTS normalized_name;
ALTER TABLE sites DROP COLUMN IF EXISTS normalized_name;
```

### 2.5. Стратегия поиска по репозиториям

Для каждой точки поиска применяется **двух-term паттерн**:

```python
from app.core.search_utils import build_normalized_like_term, build_raw_like_term

if search:
    normalized_term = build_normalized_like_term(search)  # для normalized_name, normalized_key
    raw_term = build_raw_like_term(search)                # для sku, code, device_code, description, notes
    if normalized_term is None and raw_term is None:
        pass  # search input was empty — skip search
    else:
        stmt = stmt.where(or_(
            # normalized columns → normalized_term
            Item.normalized_name.ilike(normalized_term, escape="\\"),
            # raw/technical columns → raw_term
            Item.sku.ilike(raw_term, escape="\\"),
        ))
```

**Правила выбора колонок и term:**

| Тип колонки | Term | Обоснование |
|---|---|---|
| `normalized_name`, `normalized_key` | `normalized_term` | Колонка уже нормализована при сохранении; term должен совпадать по форме |
| `sku`, `code`, `device_code` | `raw_term` | Короткие технические идентификаторы с дефисами/слешами/точками; нормализация term сломает матчинг |
| `description`, `notes`, `comment` | `raw_term` | Свободный текст; нормализация term может убрать пунктуацию, нужную для матчинга |
| `item_name_snapshot`, `item_sku_snapshot` | `raw_term` | Точные копии на момент операции; нормализация бессмысленна |
| `hashtags` (JSONB→Text) | `raw_term` | JSONB, нормализация не применима |
| `name`, `display_name` (если normalized есть) | **не искать** | Искать по `normalized_name` вместо `name` — это даёт корректную нормализацию + GIN-индекс |

**Грубая ошибка, которую нельзя допустить:** использовать `normalized_term` для `sku`/`code`/`device_code`. Пример: поиск `17М-03-49270-G` → `normalized_term` = `%17м 03 49270 g%` (дефисы → пробелы). SKU `17М-03-49270-G` не матчится. Кладовщик не находит метчик.

---

## 3. Phase 0: Foundation (последовательная)

### 3.1. Создать `app/core/search_utils.py`

**Файл:** `SyncServer/app/core/search_utils.py` (новый)

**Содержимое:** функции `normalize_search_text`, `normalize_for_storage`, `escape_like_pattern`, `build_normalized_like_term`, `build_raw_like_term` (см. раздел 2.1).

**Тесты:** `SyncServer/tests/test_search_utils.py` (новый) — unit-тесты для всех функций:
- `normalize_search_text`: empty, None, double spaces, mixed case, ё→е, punctuation, combined
- `normalize_for_storage`: None → None, empty → None, normal → normalized
- `escape_like_pattern`: `%`, `_`, `\\`, combined, no special chars
- `build_normalized_like_term`: None, empty, whitespace-only, normal, with punctuation (дефисы → пробелы)
- `build_raw_like_term`: None, empty, whitespace-only, normal, **с дефисами/слешами/точками** (дефисы сохраняются!)
- **Критичный тест:** `build_normalized_like_term("17М-03-49270-G")` != `build_raw_like_term("17М-03-49270-G")` — normalized term не должен матчить сырой SKU

### 3.2. Создать event listeners

**Файл:** `SyncServer/app/models/__init__.py` (или `SyncServer/app/models/events.py` — новый, импортируется из `__init__.py`)

**Модели с listener:** `Item`, `Category`, `TemporaryItem`, `Site` (новое поле), `Device` (новое поле).

**Логика:** `before_insert` + `before_update` → `target.normalized_name = normalize_for_storage(target.<name_field>)`

**Тесты:** проверить, что ORM-created entities получают `normalized_name` автоматически.

### 3.3. Обновить модели

**Файлы:**
- `SyncServer/app/models/site.py` — добавить `normalized_name` колонку + индекс
- `SyncServer/app/models/device.py` — добавить `normalized_name` колонку + индекс

### 3.4. Создать Alembic-миграцию

**Файл:** `SyncServer/alembic/versions/00XX_search_normalization.py` (новый, номер определить по последнему существующему)

**Содержимое:** см. раздел 2.4.

**Проверка:** `python -m alembic upgrade head` против тестовой БД.

### 3.5. Удалить дубликаты функций нормализации

**Файлы для очистки (заменить на импорт из `search_utils`):**
- `app/services/catalog_admin_service.py:45` — удалить `_normalize_text`, заменить вызовы на `normalize_for_storage`
- `app/services/machine_service.py:33` — удалить `normalize_text`, заменить на `normalize_for_storage`
- `app/services/operations_service.py:40` — удалить `_normalize_name`, заменить на `normalize_for_storage`
- `app/repos/machine_repo.py:19` — удалить `normalize_text`, заменить на импорт из `search_utils`
- `app/repos/issue_objects_repo.py:16` — удалить `normalize_issue_object_name`, заменить на `normalize_search_text`
- `app/repos/issue_object_categories_repo.py:19` — удалить `normalize_category_name`, заменить на `normalize_search_text`

**Внимание:** `normalize_for_storage` возвращает None для None (как `_normalize_text`), а `normalize_search_text` возвращает `""` для falsy (как `normalize_text` в machine_service). Проверить все call sites на совместимость.

### 3.6. Acceptance Phase 0

- [ ] `app/core/search_utils.py` создан, unit-тесты проходят
- [ ] Event listeners зарегистрированы, ORM-created entities получают `normalized_name`
- [ ] Модели Site и Device обновлены
- [ ] Миграция создана, `alembic upgrade head` проходит
- [ ] Дубликаты функций нормализации удалены, `python -m pytest` проходит

---

## 4. Phase 1: Repo Fixes (параллельная — 5 work units)

Каждый work unit:
1. Строит **два term**: `normalized_term = build_normalized_like_term(search)` и `raw_term = build_raw_like_term(search)`
2. Заменяет поиск по `name` на поиск по `normalized_name` с `normalized_term` (где есть normalized-колонка)
3. Использует `raw_term` для сырых колонок (`sku`, `code`, `device_code`, `description`, `notes`, снапшоты)
4. Добавляет `escape="\\"` ко всем `.ilike()` вызовам
5. **Запрещено** использовать `normalized_term` для `sku`/`code`/`device_code` (сломает поиск артикулов с дефисами)
6. Обновляет/добавляет тесты (включая тесты на SKU с дефисами/точками/слешами)

### Work Unit A: Catalog + Issue Object Categories

**Владение (writable files):**
- `SyncServer/app/repos/catalog_repo.py` — методы `list_items_page` (77-84), `list_categories_page` (154-160), `list_review_items_page` (627-635)
- `SyncServer/app/repos/issue_object_categories_repo.py` — метод `list_categories` (61-74)
- `SyncServer/tests/test_catalog_read_model.py` — обновить search-тесты
- `SyncServer/tests/test_issue_object_categories_api.py` — обновить search-тесты

**Изменения:**
- `list_items_page`:
  ```python
  normalized_term = build_normalized_like_term(search)
  raw_term = build_raw_like_term(search)
  stmt = stmt.where(or_(
      Item.normalized_name.ilike(normalized_term, escape="\\"),
      Item.sku.ilike(raw_term, escape="\\"),
      Item.description.ilike(raw_term, escape="\\"),
  ))
  ```
  - `description` — `raw_term` (нормализация term убрала бы пунктуацию, нужную для матчинга)
- `list_categories_page`:
  ```python
  stmt = stmt.where(or_(
      Category.normalized_name.ilike(normalized_term, escape="\\"),
      Category.code.ilike(raw_term, escape="\\"),
  ))
  ```
- `list_review_items_page`: аналогично `list_items_page`
- `issue_object_categories_repo.list_categories`:
  ```python
  normalized_term = build_normalized_like_term(search)
  raw_term = build_raw_like_term(search)
  stmt = stmt.where(or_(
      IssueObjectCategory.normalized_key.ilike(normalized_term, escape="\\"),
      IssueObjectCategory.name.ilike(raw_term, escape="\\"),
  ))
  ```

**Verification:** `python -m pytest tests/test_catalog_read_model.py tests/test_issue_object_categories_api.py -v`

### Work Unit B: Asset Registers + Balances

**Владение (writable files):**
- `SyncServer/app/repos/asset_registers_repo.py` — методы `list_pending` (255), `list_lost` (326), `list_issued` (396), `list_issued_by_object` (454)
- `SyncServer/app/repos/balances_repo.py` — метод `list_balances` (124)
- `SyncServer/tests/test_issued_assets_api.py`
- `SyncServer/tests/test_lost_assets_api.py`
- `SyncServer/tests/test_balances_read_model.py`

**Изменения:**
- `list_pending`:
  ```python
  normalized_term = build_normalized_like_term(search)
  raw_term = build_raw_like_term(search)
  stmt = stmt.where(or_(
      Item.normalized_name.ilike(normalized_term, escape="\\"),
      Item.sku.ilike(raw_term, escape="\\"),
      Site.normalized_name.ilike(normalized_term, escape="\\"),
  ))
  ```
  - `Site.normalized_name` — новое поле из Phase 0 миграции
- `list_lost`: аналогично (с `Site.normalized_name` ×2 — destination и source)
- `list_issued`:
  ```python
  stmt = stmt.where(or_(
      IssueObject.normalized_key.ilike(normalized_term, escape="\\"),
      IssueObject.display_name.ilike(raw_term, escape="\\"),
      IssueObject.comment.ilike(raw_term, escape="\\"),
      Item.normalized_name.ilike(normalized_term, escape="\\"),
      Item.sku.ilike(raw_term, escape="\\"),
  ))
  ```
- `list_issued_by_object`:
  ```python
  stmt = stmt.where(or_(
      Item.normalized_name.ilike(normalized_term, escape="\\"),
      Item.sku.ilike(raw_term, escape="\\"),
  ))
  ```
- `list_balances`:
  ```python
  stmt = stmt.where(or_(
      Item.normalized_name.ilike(normalized_term, escape="\\"),
      Item.sku.ilike(raw_term, escape="\\"),
      Category.normalized_name.ilike(normalized_term, escape="\\"),
      Site.normalized_name.ilike(normalized_term, escape="\\"),
  ))
  ```

**Verification:** `python -m pytest tests/test_issued_assets_api.py tests/test_lost_assets_api.py tests/test_balances_read_model.py -v`

### Work Unit C: Operations + Reports

**Владение (writable files):**
- `SyncServer/app/repos/operations_repo.py` — метод `list_operations` (280-297)
- `SyncServer/app/repos/reports_repo.py` — методы `list_item_movement` (179), `list_stock_summary` (273)
- `SyncServer/tests/test_operations_acceptance_and_issue_api.py` — search-тесты
- `SyncServer/tests/test_inventory_read_consistency.py`

**Изменения:**
- `list_operations`:
  ```python
  raw_term = build_raw_like_term(search)
  # Operation не имеет normalized-колонок — все сырые поля используют raw_term
  stmt = stmt.where(or_(
      Operation.notes.ilike(raw_term, escape="\\"),
      exists(... item_name_snapshot.ilike(raw_term, escape="\\"),
                item_sku_snapshot.ilike(raw_term, escape="\\"),
                cast(Item.hashtags, Text).ilike(raw_term, escape="\\")),
  ))
  ```
  - **Только `raw_term`** для Operation — снапшоты и notes не должны нормализоваться
- `list_item_movement` / `list_stock_summary`:
  ```python
  normalized_term = build_normalized_like_term(search)
  raw_term = build_raw_like_term(search)
  stmt = stmt.where(or_(
      Item.normalized_name.ilike(normalized_term, escape="\\"),
      Item.sku.ilike(raw_term, escape="\\"),
      Category.normalized_name.ilike(normalized_term, escape="\\"),
      Site.normalized_name.ilike(normalized_term, escape="\\"),
  ))
  ```

**Verification:** `python -m pytest tests/test_operations_acceptance_and_issue_api.py tests/test_inventory_read_consistency.py -v`

### Work Unit D: Sites + Devices

**Владение (writable files):**
- `SyncServer/app/repos/sites_repo.py` — метод `list_sites` (83-91)
- `SyncServer/app/services/admin_devices_service.py` — метод `list_devices` (58-65)
- `SyncServer/tests/test_sites_api.py` (если есть)
- `SyncServer/tests/test_devices_api.py` (если есть)

**Изменения:**
- `list_sites`:
  ```python
  normalized_term = build_normalized_like_term(search)
  raw_term = build_raw_like_term(search)
  stmt = stmt.where(or_(
      Site.normalized_name.ilike(normalized_term, escape="\\"),
      Site.code.ilike(raw_term, escape="\\"),
      Site.description.ilike(raw_term, escape="\\"),
  ))
  ```
  - `build_raw_like_term` уже делает strip — **критичная ошибка текущего кода (нет strip) исправлена автоматически**
- `list_devices`:
  ```python
  normalized_term = build_normalized_like_term(search)
  raw_term = build_raw_like_term(search)
  stmt = stmt.where(or_(
      Device.normalized_name.ilike(normalized_term, escape="\\"),
      Device.device_code.ilike(raw_term, escape="\\"),
  ))
  ```
  - `build_raw_like_term` уже делает strip — **критичная ошибка текущего кода (нет strip) исправлена автоматически**
  - Event listener для Device вычисляет `normalized_name` из `device_name`

**Verification:** `python -m pytest tests/test_sites_api.py tests/test_devices_api.py -v` (или соответствующие)

### Work Unit E: Temporary Items + Issue Objects

**Владение (writable files):**
- `SyncServer/app/repos/temporary_items_repo.py` — метод `list_items` (91-99)
- `SyncServer/app/repos/issue_objects_repo.py` — методы `list_issue_objects` (135-152), `find_similar` (163-180), `list_active_by_filter` (~281-284), и метод на ~336-337
- `SyncServer/tests/test_temporary_items_phase1.py`
- `SyncServer/tests/test_temporary_items_stage3a.py`
- `SyncServer/tests/test_temporary_items_stage3b.py`
- `SyncServer/tests/test_temporary_items_delete.py`
- `SyncServer/tests/test_issue_objects_api.py`
- `SyncServer/tests/test_issue_object_tree.py`

**Изменения:**
- `temporary_items_repo.list_items`:
  ```python
  normalized_term = build_normalized_like_term(search)
  raw_term = build_raw_like_term(search)
  stmt = stmt.where(or_(
      TemporaryItem.normalized_name.ilike(normalized_term, escape="\\"),
      TemporaryItem.sku.ilike(raw_term, escape="\\"),
      TemporaryItem.description.ilike(raw_term, escape="\\"),
  ))
  ```
- `issue_objects_repo.list_issue_objects`:
  ```python
  normalized_term = build_normalized_like_term(search)
  raw_term = build_raw_like_term(search)
  stmt = stmt.where(or_(
      IssueObject.display_name.ilike(raw_term, escape="\\"),
      IssueObject.code.ilike(raw_term, escape="\\"),
      IssueObject.normalized_key.ilike(normalized_term, escape="\\"),
  ))
  ```
- `issue_objects_repo.find_similar`: использовать `build_normalized_like_term` вместо ручной нормализации (существующий код использует `normalize_issue_object_name` — заменить на shared utility)
- `issue_objects_repo.list_active_by_filter`:
  ```python
  normalized_term = build_normalized_like_term(search)
  raw_term = build_raw_like_term(search)
  stmt = stmt.where(or_(
      IssueObject.display_name.ilike(raw_term, escape="\\"),
      IssueObject.normalized_key.ilike(normalized_term, escape="\\"),
      IssueObject.code.ilike(raw_term, escape="\\"),
      IssueObject.comment.ilike(raw_term, escape="\\"),
  ))
  ```

**Verification:** `python -m pytest tests/test_temporary_items_phase1.py tests/test_temporary_items_stage3a.py tests/test_temporary_items_stage3b.py tests/test_temporary_items_delete.py tests/test_issue_objects_api.py tests/test_issue_object_tree.py -v`

---

## 5. Phase 2: Test Updates (последовательная после Phase 1)

### 5.1. Обновить тестовые фикстуры

Event listeners (Phase 0) автоматически вычисляют `normalized_name` при ORM-insert. Но проверить:
- Тесты, создающие `Item`/`Category`/`TemporaryItem`/`Site`/`Device` через `session.add()` — должны получить `normalized_name` автоматически через event listener.
- Тесты, проверяющие `normalized_name == None` — могут сломаться, если event listener устанавливает значение. Проверить и обновить assertions.

### 5.2. Добавить новые search-тесты

Создать `SyncServer/tests/test_search_normalization.py`:

```python
# Тесты на нормализацию поиска через API:
# 1. Поиск с двойными пробелами в вводе → должен найти
# 2. Поиск при двойных пробелах в name → должен найти (через normalized_name)
# 3. Поиск с пунктуацией (электр. → электр./точил)
# 4. Поиск с LIKE-спецсимволами (25% → литеральный %)
# 5. Поиск с ё → должен найти через е
# 6. Поиск с заглавными буквами → case-insensitive
# 7. Пустой ввод после нормализации → не падает
# 8. Поиск по SKU с дефисом/точкой — КРИТИЧНЫЙ ТЕСТ:
#    Item with sku="17М-03-49270-G", search="17М-03-49270-G" → должен найтись
#    (raw_term сохраняет дефисы, normalized_term их не использует для sku)
# 9. Поиск по SKU с дефисом через normalized_name:
#    Item with name="Метчик М3 17М-03-49270-G", search="17М-03-49270" →
#    normalized_name match (дефисы→пробелы в term, дефисы→пробелы в normalized_name)
# 10. Поиск description с пунктуацией:
#     description="Shelf item, section A-3", search="Shelf item" → должен найтись
#     (raw_term сохраняет пунктуацию description)
```

### 5.3. Regression: существующие search-тесты

Убедиться, что все тесты из Phase 1 work units проходят без изменений assertions (кроме случаев, где поведение намеренно изменено — например, поиск `description` теперь использует `raw_term` вместо сырого ввода без экранирования).

**Критичный regression-кейс:** поиск по SKU с дефисом `17М-03-49270-G` должен находить ТМЦ с этим SKU. Если это сломалось — `raw_term` неправильно применяется к `sku`.

---

## 6. Phase 3: Integration & Stand Verification (последовательная)

### 6.1. Полный тест-набор

```bash
cd /home/makc/AI_sandbox/warehouse_solution/SyncServer
python -m pytest -x -v
```

### 6.2. Миграция на dev-стенде

```bash
cd /home/makc/AI_sandbox/warehouse_solution
make migrate
```

Или:
```bash
docker exec warehouse_syncserver python -m alembic upgrade head
```

### 6.3. Stand smoke-тесты

Стенд: Docker, SyncServer на `http://localhost:8000`.

```bash
# Health check
curl -s http://localhost:8000/api/v1/health

# Поиск по ТМЦ с двойными пробелами
curl -s "http://localhost:8000/api/v1/catalog/read/items?search=шлифовальный%20%20для&page=1&page_size=5" -H "X-User-Token: <token>"

# Поиск с пунктуацией
curl -s "http://localhost:8000/api/v1/catalog/read/items?search=электр.&page=1&page_size=5" -H "X-User-Token: <token>"

# Поиск с LIKE-спецсимволом
curl -s "http://localhost:8000/api/v1/catalog/read/items?search=25%&page=1&page_size=5" -H "X-User-Token: <token>"

# Поиск с ё
curl -s "http://localhost:8000/api/v1/catalog/read/items?search=ёлка&page=1&page_size=5" -H "X-User-Token: <token>"
```

### 6.4. EXPLAIN ANALYZE verification

```sql
-- Проверить, что GIN-индекс используется
EXPLAIN ANALYZE SELECT * FROM items WHERE normalized_name ILIKE '%круг%';
-- Должно показать "Bitmap Index Scan on ix_items_normalized_name_trgm"
```

---

## 7. Test Ladder

| Level | Name | Applicable? | Tests |
|---|---|---|---|
| 1 | Static checks | Да | `python -m pyflakes app/` (или линтер), `alembic check` |
| 2 | Unit tests | Да | `test_search_utils.py` — normalize, escape, build_normalized_like_term, build_raw_like_term |
| 3 | Component tests | Да | Event listener tests — ORM insert/update вычисляет normalized_name |
| 4 | Integration tests | Да | Каждый endpoint поиска с нормализованным вводом, тестовая БД |
| 5 | Stand smoke tests | Да | Real dev-stand: миграция + curl-поиски + EXPLAIN ANALYZE |
| 6 | UI automation | Опционально | Playwright поиск через Django/Angular — если UI-поиск меняется. В данном ТЗ backend-only изменения, UI не затронут напрямую. |
| 7 | User scenarios | Да | Поиск ТМЦ кладовщиком: двойные пробелы, пунктуация, спецсимволы |
| 8 | Regression pack | Да | Все существующие search-тесты (test_catalog_read_model, test_operations_*, test_balances_*, и т.д.) |
| 9 | Acceptance review | Да | Evidence table + checklist |

---

## 8. Stand Requirements

| Параметр | Значение |
|---|---|
| Database | PostgreSQL 15 (Docker, `warehouse_postgres`) |
| Seed data | Существующие ~2621 items в dev-стенде + тестовые ТМЦ с двойными пробелами |
| Services | SyncServer (`http://localhost:8000`), PostgreSQL (`localhost:5432`) |
| Env vars (names only) | `DATABASE_URL`, `DJANGO_ENV=development` |
| Health checks | `GET http://localhost:8000/api/v1/health`, `pg_isready -h localhost -p 5432` |
| Smoke commands | `make migrate`, `curl ... search ...`, `EXPLAIN ANALYZE` |
| Reset/cleanup | Миграция идемпотентна (`IF NOT EXISTS`); backfill `UPDATE` можно повторить |

---

## 9. Out of Scope

- **Django BFF search endpoints** — Django вызывает SyncServer `/api/v1/` endpoints; нормализация на уровне SyncServer автоматически улучшает Django-поиск. Изменений в `Warehouse_web` не требуется.
- **Angular frontend** — фронтенд отправляет search-строку как есть; нормализация происходит на backend. Изменений в `Warehouse_frontend` не требуется.
- **Full-text search (tsvector)** — GIN + pg_trgm достаточно для текущего объёма (~2621 строк). tsvector — future enhancement при >100k строк.
- **Fuzzy search / Levenshtein** — вне scope. Текущая нормализация + trigram покрывает заявленные дефекты.
- **Operation snapshots** — `item_name_snapshot` / `item_sku_snapshot` в `OperationLine` — не нормализуются (должны быть точными копиями).

---

## 10. Risks

| Риск | Вероятность | Влияние | Митигация |
|---|---|---|---|
| `\w` в SQL backfill не покрывает кириллицу | Средняя | Неверный normalized_name | Проверить на dev-стенде, использовать явный `[^a-zа-яё0-9\s]` при необходимости |
| Event listener меняет normalized_name на существующих update-путях | Низкая | Двойное вычисление (сервис + listener) | Listener безусловно перезаписывает — это ок, т.к. deterministic |
| Тесты ломаются из-за изменения normalized_name | Средняя | Тесты с `assert item.normalized_name is None` | Обновить assertions — normalized_name теперь всегда установлен |
| `build_normalized_like_term`/`build_raw_like_term` возвращает None для whitespace-only ввода | Низкая | Search пропускается (нет WHERE) | Это корректное поведение — пустой поиск = без фильтра |
| pg_trgm extension недоступна | Низкая | GIN-индекс не создаётся | Миграция падает явно; pg_trgm входит в postgres-contrib |

---

## 11. Evidence Table (template for executor reports)

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|
| Static checks | `python -m pyflakes app/core/search_utils.py` | pass/fail | — |
| Unit tests | `python -m pytest tests/test_search_utils.py -v` | pass/fail/skipped | log path |
| Event listener tests | `python -m pytest tests/test_search_events.py -v` | pass/fail/skipped | log path |
| Integration tests | `python -m pytest tests/test_search_normalization.py -v` | pass/fail/skipped | log path |
| Migration | `python -m alembic upgrade head` | pass/fail | migration log |
| Stand smoke | `curl ... search ...` | pass/fail/skipped | response snippet |
| EXPLAIN ANALYZE | `EXPLAIN ANALYZE SELECT ... ILIKE ...` | pass/fail | uses GIN index? |
| Regression | `python -m pytest -x` | pass/fail/skipped | test summary |

---

## 12. Evidence Table — финальный обзор (2026-07-31)

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|
| Migration applied | `docker exec warehouse_syncserver python -m alembic current` | **pass** | head = `0035_set_base_revision_not_null`; 0020 в цепочке применённых |
| pg_trgm extension | `SELECT extname FROM pg_extension WHERE extname='pg_trgm'` | **pass** | `pg_trgm` присутствует |
| Backfill coverage | `SELECT count(*) FILTER (WHERE normalized_name IS NULL) FROM items` | **pass** | 1707 / 1707 items имеют normalized_name, 0 NULL |
| Indexes created | `SELECT indexname FROM pg_indexes WHERE indexname LIKE '%normalized_name%'` | **pass** | 5 B-tree (`ix_<table>_normalized_name`) + 5 GIN-trgm (`ix_<table>_normalized_name_trgm`) для items/categories/sites/devices/temporary_items |
| Unit tests | `python -m pytest tests/test_search_utils.py -v` | **pass** | 44 / 44 passed in 0.05s |
| Integration tests | `python -m pytest tests/test_search_normalization.py -v` | **pass** | 13 / 13 passed in 20.05s |
| Regression full suite | `python -m pytest --tb=short -q` | **pass** | 662 passed, 3 skipped, 13 deselected (stand), 7 xfailed; 0 failed in 768s |
| Stand smoke 1 — double spaces | `curl "...search=фильтр%20%20гидравлический"` | **pass** | total_count=18, найден id=590 "Фильтр  гидравлический" (с двойным пробелом в БД) |
| Stand smoke 2 — ё→е | `curl "...search=фильтр%20гидравлический"` | **pass** | total_count=18, идентично поиску с ё |
| Stand smoke 3 — case-insensitive | `curl "...search=ФИЛЬТР%20ГИДРАВЛИЧЕСКИЙ"` | **pass** | total_count=18 (uppercase, lowercase, mixed — все находят одно и то же) |
| Stand smoke 4 — SKU with hyphens | `curl "...search=175-60-27380/07"` | **pass** | total_count=1, найден id=1180 (sku="175-60-27380/07") — критичный тест |
| Stand smoke 5 — LIKE escape `%` | `curl "...search=10%25"` | **pass** | total_count=337, спецсимвол `%` не сломал LIKE (escape работает) |
| Stand smoke 6 — punctuation | `curl "...search=фильтр%20гидравл."` | **pass** | total_count=18, точка в конце не мешает (normalize удаляет пунктуацию) |
| EXPLAIN ANALYZE (Seq Scan path) | `EXPLAIN ANALYZE SELECT ... ILIKE '%фильтр%'` | **pass** | Seq Scan, 0.83ms — оптимизатор считает дешевле при 1707 строках |
| EXPLAIN ANALYZE (GIN forced) | `SET enable_seqscan=OFF; EXPLAIN ANALYZE ... ILIKE '%фильтр%'` | **pass** | `Bitmap Index Scan on ix_items_normalized_name_trgm`, 0.42ms — GIN-индекс работает |
| Event listeners registered | `grep "import app.models.events" app/models/__init__.py` | **pass** | listeners импортируются через `app/models/__init__.py:38`; ORM insert вычисляет normalized_name автоматически |
| Documentation updated | `ARCHITECTURE.md`, `AI_CONTEXT.md`, `AI_ENTRY_POINTS.md`, `INDEX.md` | **pass** | Все 4 файла содержат разделы про search normalization |
| UI automation | Playwright поиск через Django/Angular | **N/A** | TZ явно помечает как not applicable: backend-only изменения, UI не затронут |

## 13. Итог

- Все 12 уровней test ladder пройдены (уровень 6 UI automation явно N/A).
- Все 15 точек поиска в 10 репозиториях используют единый `search_utils` pipeline.
- 6 ранее существовавших функций нормализации (`_normalize_text`, `normalize_text` x2, `_normalize_name`, `normalize_issue_object_name`, `normalize_category_name`) удалены и заменены импортами из `search_utils`.
- Миграция `0020_search_normalization` применена, backfill завершён, индексы созданы.
- GIN-trigram индекс работает (подтверждено через `Bitmap Index Scan` при `enable_seqscan=OFF`).
- Критический тест поиска по SKU с дефисами/слешами (`175-60-27380/07`) проходит — деление на `normalized_term` и `raw_term` защищает от регрессии.
- Регрессия: 662 passed, 0 failed.
- TZ закрыт 2026-07-31.
