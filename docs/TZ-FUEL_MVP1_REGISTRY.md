# TZ: Fuel MVP-1 — Централизованный реестр заправок

**Версия:** 1.0  
**Дата:** 2026-07-01  
**Продукт:** Quartermaster 3.1  
**Статус:** На утверждение

## Контекст

См. архитектурный обзор: `docs/architecture-review-fuel-module.md`.

MVP-1 — первый шаг топливного модуля. Никаких путевых листов, никаких кандидатов, никакого Excel-парсинга на бэкенде. Только:

> **«Какая техника сколько топлива получила за выбранный период, из какого источника и с каким качеством данных?»**

## Execution Strategy

- [ ] 🟡 Sequential execution recommended
- **Reason:** Жёсткая зависимость: сначала миграции и модели в SyncServer, затем API, затем BFF в Django, затем UI. Параллелить внутри SyncServer можно (vehicles API и fuel issues API), но BFF и UI ждут готовых endpoint'ов.

## Execution Checklist

- [ ] 0. Контекст verified — архитектурный обзор принят, риски задокументированы
- [ ] 1. Миграции: 6 таблиц в SyncServer (Alembic)
- [ ] 2. SyncServer: Vehicle CRUD + aliases
- [ ] 3. SyncServer: FuelImportBatch + FuelRawEntry API
- [ ] 4. SyncServer: FuelIssue CRUD + статусные переходы
- [ ] 5. SyncServer: FuelSummary endpoint (сводка)
- [ ] 6. SyncServer: AuditEvent integration для fuel-сущностей
- [ ] 7. Django BFF: зеркалирование всех fuel endpoints
- [ ] 8. Django UI: экран сводки топлива
- [ ] 9. Django UI: таблица заправок с фильтрацией
- [ ] 10. Django UI: справочник техники
- [ ] 11. Django UI: загрузка партии (JSON) + список партий
- [ ] 12. Права доступа: fuel-операции для ролей
- [ ] 13. Unit/component tests: SyncServer fuel services
- [ ] 14. Integration tests: DB-backed API tests
- [ ] 15. Stand smoke tests: все эндпоинты на реальном стенде
- [ ] 16. UI automation: Playwright smoke — сводка + создание заправки
- [ ] 17. Документация API обновлена
- [ ] 18. Final acceptance review

---

## 1. Модель данных (6 таблиц)

### 1.1. `vehicles` — Справочник техники

Основной справочник транспортного модуля. **НЕ переиспользует IssueObject напрямую.**

```text
vehicles
├── id              UUID PK
├── site_id         INT FK → sites (NOT NULL)
├── name            VARCHAR(255) (NOT NULL)
├── normalized_name VARCHAR(255) (NOT NULL)
├── plate_number    VARCHAR(50)
├── inventory_number VARCHAR(100)
├── vehicle_class   VARCHAR(64)   — car / truck / special / mixed
├── fuel_types      JSONB         — ["diesel_winter", "ai_92"]
├── accounting_modes JSONB        — ["mileage", "no_route", "route", "engine_hours"]
├── default_fuel_norm_l_per_100km   NUMERIC(8,2)
├── default_fuel_norm_l_per_motohour NUMERIC(8,2)
├── default_waybill_template VARCHAR(100)  — задел на будущее
├── issue_object_id INT FK → issue_objects (NULLABLE)  — опциональная связь со складом
├── is_active       BOOLEAN DEFAULT true
├── notes           TEXT
│
├── created_by_user_id UUID FK → users
├── created_at      TIMESTAMPTZ
├── updated_at      TIMESTAMPTZ
├── deleted_at      TIMESTAMPTZ
└── deleted_by_user_id UUID FK → users
```

### 1.2. `vehicle_aliases` — Алиасы техники

```text
vehicle_aliases
├── id              UUID PK
├── vehicle_id      UUID FK → vehicles (NOT NULL)
├── alias           VARCHAR(255) (NOT NULL)
├── source          VARCHAR(100)  — file / batch / manual
├── is_active       BOOLEAN DEFAULT true
└── created_at      TIMESTAMPTZ

INDEX: btree(lower(alias))
```

### 1.3. `fuel_import_batches` — Партия импорта

```text
fuel_import_batches
├── id              UUID PK
├── site_id         INT FK → sites (NOT NULL)
├── batch_number    VARCHAR(100)
├── period_from     DATE
├── period_to       DATE
├── source_type     VARCHAR(64)   — json_import / manual_entry
├── source_description TEXT
├── file_name       VARCHAR(500)
├── file_ref        VARCHAR(1000) — путь в Nextcloud (задел)
├── uploaded_by_user_id UUID FK → users
├── status          VARCHAR(32) DEFAULT 'received'
│                   — received / processing / needs_review / processed / failed
├── stats           JSONB DEFAULT '{}'
│                   — {"total_raw": 150, "normalized": 120, "parse_errors": 20, "skipped": 10}
├── warnings        JSONB DEFAULT '[]'
├── errors          JSONB DEFAULT '[]'
├── created_at      TIMESTAMPTZ
└── updated_at      TIMESTAMPTZ
```

### 1.4. `fuel_raw_entries` — Сырая запись (иммутабельна)

**Правило иммутабельности:** После создания НЕ редактировать `raw_data`. Менять можно только служебные поля: `parse_status`, `problems`, `normalized_fuel_issue_id`.

```text
fuel_raw_entries
├── id              UUID PK
├── batch_id        UUID FK → fuel_import_batches (NOT NULL)
├── row_index       INT (NOT NULL)
├── source_ref      VARCHAR(500)  — file!sheet!row или номер чека
├── raw_data        JSONB (NOT NULL) — как пришло, неизменяемо
├── parse_status    VARCHAR(32) DEFAULT 'raw'
│                   — raw / parsing / parse_error / normalized / skipped
├── problems        JSONB DEFAULT '[]'
│                   — [{"code": "vehicle_unknown", "raw_value": "уазик"}]
├── matched_vehicle_id UUID FK → vehicles
├── matched_fuel_type   VARCHAR(64)
├── matched_liters      NUMERIC(12,3)
├── matched_date        DATE
├── matched_person_raw  VARCHAR(255)
└── created_at      TIMESTAMPTZ
```

### 1.5. `fuel_issues` — Нормализованная заправка

**Ключевое упрощение относительно архитектурного обзора:** вместо 8 статусов — 4 статуса + `problem_codes` JSONB.

```text
fuel_issues
├── id              UUID PK
├── site_id         INT FK → sites (NOT NULL)
├── raw_entry_id    UUID FK → fuel_raw_entries UNIQUE NULLABLE  — trace back (one-to-one)
├── vehicle_id      UUID FK → vehicles
├── fuel_type       VARCHAR(64) (NOT NULL)
│                   — diesel_summer / diesel_winter / ai_92 / ai_95 / ai_98 / gas
├── liters          NUMERIC(12,3) (NOT NULL)
├── amount          NUMERIC(15,2)
├── currency        VARCHAR(3) DEFAULT 'RUB'
│
├── date_exact      TIMESTAMPTZ
├── date_from       DATE
├── date_to         DATE
├── granularity     VARCHAR(32) DEFAULT 'exact_time'
│                   — exact_time / date / shift / period_total / month_total / unknown
│
├── source_type     VARCHAR(64) (NOT NULL)
│                   — own_fuel_station / keeper_report / keeper_month_summary
│                     / gas_station_receipt / manual_entry
├── source_document_id UUID FK → fuel_source_documents
├── source_ref      VARCHAR(500)
│
├── fuel_recipient_name_raw VARCHAR(255)
│
├── status          VARCHAR(32) DEFAULT 'needs_review'
│                   — needs_review / confirmed / excluded / duplicate
├── problem_codes   JSONB DEFAULT '[]'
│                   — ["vehicle_not_matched", "period_missing", "fuel_type_unknown"]
├── comment         TEXT
│
├── created_by_user_id  UUID FK → users
├── updated_by_user_id  UUID FK → users
├── confirmed_by_user_id UUID FK → users
├── created_at      TIMESTAMPTZ
├── updated_at      TIMESTAMPTZ
├── confirmed_at    TIMESTAMPTZ
├── deleted_at      TIMESTAMPTZ
├── deleted_by_user_id UUID FK → users
│
└── version         INT DEFAULT 1  — optimistic locking

INDEX: (vehicle_id, date_from, date_to) WHERE deleted_at IS NULL
INDEX: (site_id, date_from) WHERE deleted_at IS NULL AND status = 'confirmed'
INDEX: (status) WHERE deleted_at IS NULL
```

**Инвариант дат:** `date_from` и `date_to` обязаны быть заполнены для каждой `confirmed` FuelIssue:
- `exact_time` / `date`: `date_from = date_to =` дата события;
- `month_total`: `date_from =` первый день месяца, `date_to =` последний день месяца;
- `period_total`: `date_from` / `date_to` = указанный период;
- `shift`: `date_from` / `date_to` = границы смены.
- `date_exact` — опциональная дополнительная точность.

`granularity = 'unknown'` допустимо только для `needs_review`. Перед `confirm` должна быть определена.

### 1.6. `fuel_source_documents` — Документ-основание

```text
fuel_source_documents
├── id              UUID PK
├── site_id         INT FK → sites (NOT NULL)
├── document_type   VARCHAR(64) (NOT NULL)
│                   — gas_station_receipt / keeper_journal / keeper_report / scan / manual_document
├── document_number VARCHAR(100)
├── document_date   DATE
├── issuer          VARCHAR(255)  — АЗС, кладовщик и т.п.
├── file_ref        VARCHAR(1000) — путь в Nextcloud (задел)
├── status          VARCHAR(32) DEFAULT 'active'
├── notes           TEXT
├── created_by_user_id UUID FK → users
├── created_at      TIMESTAMPTZ
└── updated_at      TIMESTAMPTZ
```

---

## 2. Статусы и жизненные циклы (упрощённые)

### 2.1. FuelImportBatch

```
received → processing → processed
                │            ↑
                ├──→ needs_review ──┘
                └──→ failed
```

| Статус | Описание | Переходы |
|--------|----------|----------|
| `received` | Загружен, сырые записи созданы | → `processing`, → `failed` |
| `processing` | Идёт разбор | → `needs_review`, → `processed`, → `failed` |
| `needs_review` | Есть проблемные записи | → `processing` (повтор), → `processed` |
| `processed` | Всё обработано | Конечный |
| `failed` | Критическая ошибка | Конечный, можно удалить |

### 2.2. FuelRawEntry

```
raw → normalized
  │       parse_error → raw (после ручной правки, пересоздаётся FuelIssue)
  └──→ skipped
```

| Статус | Описание |
|--------|----------|
| `raw` | Как загружено |
| `parsing` | В процессе разбора (промежуточный) |
| `parse_error` | Не удалось разобрать |
| `normalized` | Создан FuelIssue (определяется по наличию `fuel_issues.raw_entry_id = this.id`) |
| `skipped` | Пропущено (пустая строка, заголовок) |

### 2.3. FuelIssue

```
needs_review → confirmed → excluded
                   │          duplicate
                   ↓
         (участвует в сводках)
```

**4 статуса вместо 8.** Детализация проблем — через `problem_codes` JSONB.

```json
{
  "status": "needs_review",
  "problem_codes": ["vehicle_not_matched", "period_missing"]
}
```

| Статус | Описание | Переходы |
|--------|----------|----------|
| `needs_review` | Требует проверки (создана из raw или вручную) | → `confirmed`, → `excluded`, → `duplicate` |
| `confirmed` | Проверена, готова. **Только эти участвуют в сводках.** | → `excluded`, → `duplicate` |
| `excluded` | Исключена (не техника артели, ошибка) | → `confirmed` (восстановление) |
| `duplicate` | Дубликат | → `confirmed` (восстановление) |

`problem_codes` (справочник):
- `vehicle_not_matched` — техника не определена
- `fuel_type_unknown` — топливо не определено
- `period_missing` — дата/период не указан
- `liters_missing` — нет количества (литры)
- `amount_missing` — нет суммы (деньги, опционально)
- `suspected_duplicate` — возможно дубликат
- `needs_manual_check` — общая причина для ручной проверки

**Правило:** При создании вручную можно сразу ставить `confirmed`, если все поля заполнены и `problem_codes` пуст.

**Инвариант подтверждения:** FuelIssue может перейти в `confirmed` только если:
- `vehicle_id` заполнен (NOT NULL);
- `fuel_type` заполнен (NOT NULL);
- `liters > 0`;
- `date_from` и `date_to` заполнены (NOT NULL);
- `granularity != 'unknown'`;
- `problem_codes` не содержит блокирующих кодов (`vehicle_not_matched`, `fuel_type_unknown`, `period_missing`, `liters_missing`);
- `deleted_at IS NULL`.

Non-blocking `problem_codes` (например, `suspected_duplicate`, `needs_manual_check`) не блокируют подтверждение, но остаются в массиве для аудита.

---

## 3. API Endpoints

**SyncServer base prefix:** `/api/v1`. Fuel endpoints регистрируются под `/fuel/...`.

Примеры: `GET /api/v1/fuel/vehicles`, `GET /api/v1/fuel/issues`, `GET /api/v1/fuel/summary`.

**Django BFF base prefix:** `/bff/api/v1`. Зеркалирует: `/bff/api/v1/fuel/vehicles` и т.д.

### 3.1. Справочник техники

| Метод | Путь | Описание | Права |
|-------|------|----------|-------|
| `GET` | `/fuel/vehicles` | Список. Фильтры: `site_id`, `is_active`, `vehicle_class`, `search` (по name/plate). Пагинация. | observer+ |
| `GET` | `/fuel/vehicles/{id}` | Детали + aliases | observer+ |
| `POST` | `/fuel/vehicles` | Создать | chief_storekeeper+ |
| `PATCH` | `/fuel/vehicles/{id}` | Обновить | chief_storekeeper+ |
| `DELETE` | `/fuel/vehicles/{id}` | Soft-delete | root |
| `GET` | `/fuel/vehicles/{id}/aliases` | Алиасы | observer+ |
| `POST` | `/fuel/vehicles/{id}/aliases` | Добавить алиас. Body: `{alias, source?}` | chief_storekeeper+ |
| `DELETE` | `/fuel/vehicles/{id}/aliases/{alias_id}` | Удалить алиас | chief_storekeeper+ |

### 3.2. Партии импорта

| Метод | Путь | Описание | Права |
|-------|------|----------|-------|
| `POST` | `/fuel/import-batches` | Создать партию. Body: `{site_id, period_from?, period_to?, source_type, source_description?, entries: [...]}` | storekeeper+ |
| `GET` | `/fuel/import-batches` | Список. Фильтры: `site_id`, `period_from`, `period_to`, `status`. Пагинация. | observer+ |
| `GET` | `/fuel/import-batches/{id}` | Детали + stats | observer+ |
| `POST` | `/fuel/import-batches/{id}/process` | Запустить разбор. **Асинхронно.** Возвращает 202. | storekeeper+ |
| `DELETE` | `/fuel/import-batches/{id}` | Удалить (только `received`/`failed`) | storekeeper+ |

### 3.3. Сырые записи

| Метод | Путь | Описание | Права |
|-------|------|----------|-------|
| `GET` | `/fuel/import-batches/{batch_id}/raw-entries` | Список записей партии. Фильтр: `parse_status`. Пагинация. | observer+ |
| `GET` | `/fuel/import-batches/{batch_id}/raw-entries/{id}` | Детали | observer+ |
| `PATCH` | `/fuel/import-batches/{batch_id}/raw-entries/{id}` | Ручная коррекция: `matched_vehicle_id`, `matched_fuel_type`, `matched_liters`, `matched_date`. Только для `parse_error`. | storekeeper+ |
| `POST` | `/fuel/import-batches/{batch_id}/raw-entries/{id}/create-issue` | Создать FuelIssue из raw entry вручную (с переопределением полей) | storekeeper+ |

### 3.4. Заправки (FuelIssue)

| Метод | Путь | Описание | Права |
|-------|------|----------|-------|
| `GET` | `/fuel/issues` | Список. Фильтры: `site_id`, `vehicle_id`, `period_from`, `period_to`, `fuel_type`, `status`, `source_type`. Пагинация. | observer+ |
| `GET` | `/fuel/issues/{id}` | Детали | observer+ |
| `POST` | `/fuel/issues` | Создать вручную. Body — полный DTO. Можно сразу `status=confirmed`. | storekeeper+ |
| `PATCH` | `/fuel/issues/{id}` | Обновить (только `needs_review`). Нельзя менять после `confirmed`. | storekeeper+ |
| `POST` | `/fuel/issues/{id}/confirm` | Подтвердить. Статус → `confirmed`. | storekeeper+ |
| `POST` | `/fuel/issues/{id}/exclude` | Исключить. Статус → `excluded`. | storekeeper+ |
| `POST` | `/fuel/issues/{id}/mark-duplicate` | Пометить дубликатом. Статус → `duplicate`. | storekeeper+ |

### 3.5. Сводка топлива (ключевой отчёт MVP)

| Метод | Путь | Описание | Права |
|-------|------|----------|-------|
| `GET` | `/fuel/summary` | **Сводка топлива по технике за период.** Параметры: `site_id` (required), `period_from`, `period_to`, `vehicle_id?`, `fuel_type?`, `group_by` (vehicle / fuel_type / source_type / month). | observer+ |

**Семантика сводки:**
- `total_liters` и `issue_count` считаются **только** по `confirmed` записям.
- `needs_review_count` показывается отдельно как индикатор качества данных; литры из `needs_review` НЕ входят в `total_liters`.
- Записи в `excluded` и `duplicate` не учитываются нигде.

### 3.6. Документы-основания

| Метод | Путь | Описание | Права |
|-------|------|----------|-------|
| `GET` | `/fuel/source-documents` | Список. Фильтры: `site_id`, `document_type`. | observer+ |
| `POST` | `/fuel/source-documents` | Создать | storekeeper+ |
| `GET` | `/fuel/source-documents/{id}` | Детали | observer+ |
| `PATCH` | `/fuel/source-documents/{id}` | Обновить | storekeeper+ |

---

## 4. JSON DTO

### FuelIssue (request/response)

```json
{
  "id": "uuid",
  "site_id": 1,
  "vehicle": {"id": "uuid", "name": "УАЗ Фермер", "plate_number": "А123ВС"},
  "fuel_type": "diesel_winter",
  "liters": 45.5,
  "amount": 2850.00,
  "currency": "RUB",
  "date_exact": "2026-06-15T14:30:00+07:00",
  "date_from": null,
  "date_to": null,
  "granularity": "exact_time",
  "source_type": "gas_station_receipt",
  "source_document": {"id": "uuid", "document_type": "gas_station_receipt", "document_number": "Чек №12345"},
  "source_ref": "чек от 15.06.2026",
  "fuel_recipient_name_raw": "Иванов",
  "status": "confirmed",
  "problem_codes": [],
  "comment": null,
  "version": 2,
  "created_by_user": {"id": "uuid", "full_name": "Петров П.П."},
  "created_at": "2026-06-20T10:00:00+07:00",
  "confirmed_at": "2026-06-21T09:00:00+07:00"
}
```

### FuelSummary (response)

```json
{
  "site_id": 1,
  "period_from": "2026-06-01",
  "period_to": "2026-06-30",
  "group_by": "vehicle",
  "groups": [
    {
      "vehicle": {"id": "uuid", "name": "УАЗ Фермер", "plate_number": "А123ВС"},
      "total_liters": 345.5,
      "issue_count": 7,
      "source_breakdown": {
        "gas_station_receipt": {"liters": 200.0, "count": 4},
        "keeper_month_summary": {"liters": 145.5, "count": 3}
      },
      "fuel_type_breakdown": {
        "diesel_winter": {"liters": 200.0, "count": 4},
        "ai_92": {"liters": 145.5, "count": 3}
      },
      "confirmed_count": 5,
      "needs_review_count": 2
    }
  ],
  "totals": {
    "total_liters": 12500.0,
    "total_issues": 145,
    "total_vehicles": 12
  }
}
```

### FuelImportBatch (request)

```json
{
  "site_id": 1,
  "period_from": "2026-06-01",
  "period_to": "2026-06-30",
  "source_type": "json_import",
  "source_description": "Ведомость заправщика за июнь, участок Северный",
  "file_name": "fuel_june_2026.json",
  "entries": [
    {
      "row_index": 1,
      "source_ref": "лист 1, строка 2",
      "raw_data": {
        "date": "2026-06-15",
        "vehicle_name": "УАЗ фермер",
        "fuel_type": "дт",
        "liters": "45",
        "person": "Иванов"
      }
    }
  ]
}
```

---

## 5. Права доступа

| Роль | Просмотр | Создание/редактирование | Подтверждение | Удаление |
|------|----------|------------------------|---------------|----------|
| `root` | Всё | Всё | Всё | Всё |
| `chief_storekeeper` | Всё | Всё | Всё | Только свои `fuel_import_batches` в `received`/`failed` |
| `storekeeper` | По своим `site_id` | По своим `site_id` | По своим `site_id` | Только свои `fuel_import_batches` в `received`/`failed` |
| `observer` | По своим `site_id` | Нет | Нет | Нет |

**Семантика удаления:**
- `FuelIssue` **не удаляется физически** в MVP-1. Ошибочные записи переводятся в `excluded` или `duplicate`.
- `fuel_import_batches` можно удалить только в статусах `received` или `failed`.
- `vehicles` — soft-delete (`deleted_at`), только root.

Проверка через существующий `access_service.py`: `can_view_site()`, `can_operate_site()`.

---

## 6. Стратегия импорта (компромисс)

**Бэкенд MVP-1:** принимает только нормализованный JSON (ручной ввод или структурированный импорт через `POST /fuel/import-batches`). Никакого Excel/CSV-парсинга на сервере.

**Внешний «грязный конвертер»:** отдельный скрипт/утилита (вне Scope MVP-1, но рядом):

```
xlsx от кладовщика → скрипт-конвертер → JSON по схеме → POST /fuel/import-batches
```

Конвертер:
- не является частью SyncServer;
- может быть на Python, в виде CLI или простого веб-интерфейса;
- маппит колонки Excel на поля `raw_data.*`;
- генерирует `raw_data` как есть, без нормализации;
- опционально предзаполняет `matched_vehicle_id` если есть точное совпадение имени.

Это сохраняет бэкенд чистым, а реальные данные — загружаемыми.

---

## 7. Аудит

Все мутации — через существующую таблицу `audit_events` (`audit_helper.record_audit_event()`):

| Событие | entity_type | event_type |
|---------|-------------|------------|
| Создание техники | `vehicle` | `vehicle.created` |
| Обновление техники | `vehicle` | `vehicle.updated` |
| Загрузка партии | `fuel_import_batch` | `fuel_import_batch.uploaded` |
| Обработка партии | `fuel_import_batch` | `fuel_import_batch.processed` |
| Создание заправки | `fuel_issue` | `fuel_issue.created` |
| Обновление заправки | `fuel_issue` | `fuel_issue.updated` |
| Подтверждение заправки | `fuel_issue` | `fuel_issue.confirmed` |
| Исключение заправки | `fuel_issue` | `fuel_issue.excluded` |
| Дубликат | `fuel_issue` | `fuel_issue.marked_duplicate` |

---

## 8. Сценарии использования (MVP-1)

### Сценарий 1: Ручной ввод заправки (основной)

1. Кладовщик заходит в раздел «Топливо / Заправки».
2. Нажимает «Добавить заправку».
3. Выбирает технику из справочника, тип топлива, количество, дату, источник.
4. Если всё заполнено — заправка сохраняется со статусом `confirmed`.
5. Если чего-то не хватает — `needs_review` с соответствующими `problem_codes`.
6. Заправка появляется в сводке.

### Сценарий 2: Импорт партии через JSON

1. Ответственный собирает данные от кладовщиков.
2. Готовит JSON-файл (или использует внешний конвертер из Excel).
3. В разделе «Топливо / Импорт» загружает JSON.
4. Система создаёт `FuelImportBatch` + `FuelRawEntry` для каждой строки.
5. Запускает разбор: пытается сопоставить `raw_data.vehicle_name` с `vehicles` (точное совпадение по name или alias).
6. Для сопоставленных — создаёт `FuelIssue` в статусе `needs_review`.
7. Для несопоставленных — `FuelRawEntry.parse_status = 'parse_error'`.
8. Оператор видит статистику партии: сколько разобрано, сколько проблем.
9. Открывает проблемные записи, вручную правит сопоставление, создаёт FuelIssue.

### Сценарий 3: Сводка топлива

1. Главный кладовщик заходит в раздел «Топливо / Сводка».
2. Выбирает период (месяц) и, опционально, технику.
3. Видит таблицу: техника → всего литров → по источникам → по типам топлива.
4. Может переключить группировку: по типу топлива, по источнику.
5. Видит количество confirmed и needs_review записей — оценка качества данных.

### Сценарий 4: Проблемные записи

1. Оператор заходит в раздел «Топливо / Требует проверки».
2. Видит список FuelIssue со статусом `needs_review`, сгруппированный по `problem_codes`.
3. Фильтрует: «все записи без техники», «все записи без даты».
4. Для каждой: открывает детали, правит поля, нажимает «Подтвердить».
5. Статус меняется на `confirmed`, проблема уходит из дашборда.

---

## 9. Уточнения перед реализацией

### 9.1. API prefix
SyncServer base prefix: `/api/v1`. Fuel endpoints регистрируются под `/fuel/...`.
Примеры: `GET /api/v1/fuel/vehicles`, `GET /api/v1/fuel/issues`, `GET /api/v1/fuel/summary`.
Двойной префикс `/api/v1/fuel/fuel/...` — ошибка. Префикс `/fuel/` — один.

### 9.2. Нет циклического FK
- `fuel_issues.raw_entry_id` — nullable FK → `fuel_raw_entries.id` с UNIQUE constraint (one-to-one).
- Поле `normalized_fuel_issue_id` в `fuel_raw_entries` **отсутствует**.
- Статус `normalized` у RawEntry определяется наличием `FuelIssue`, где `raw_entry_id = raw_entry.id`.

### 9.3. Инвариант дат
`date_from` и `date_to` обязаны быть заполнены для каждой `confirmed` FuelIssue:
- `exact_time` / `date`: `date_from = date_to =` дата события;
- `month_total`: `date_from =` первый день месяца, `date_to =` последний день месяца;
- `period_total`: `date_from` / `date_to` = указанный период;
- `shift`: `date_from` / `date_to` = границы смены.

`granularity = 'unknown'` допустимо только для `needs_review`. Перед `confirm` должна быть определена.

### 9.4. Инвариант подтверждения FuelIssue
FuelIssue может перейти в `confirmed` только если:
- `vehicle_id IS NOT NULL`;
- `fuel_type IS NOT NULL`;
- `liters > 0`;
- `date_from IS NOT NULL AND date_to IS NOT NULL`;
- `granularity != 'unknown'`;
- блокирующие `problem_codes` (`vehicle_not_matched`, `fuel_type_unknown`, `period_missing`, `liters_missing`) отсутствуют;
- `deleted_at IS NULL`.

### 9.5. Переименование problem_codes
- `amount_missing` (путаница с деньгами) → `liters_missing` (нет литров).
- `amount_missing` оставлен только для отсутствующей суммы в деньгах (опционально, не блокирует `confirmed`).

### 9.6. Семантика FuelSummary
- `total_liters` и `issue_count` — **только** `confirmed` записи.
- `needs_review_count` — отдельный индикатор качества; литры из `needs_review` НЕ входят в `total_liters`.
- `excluded` и `duplicate` не учитываются.

### 9.7. Семантика удаления
- `FuelIssue` физически не удаляется. Ошибочные записи → `excluded` / `duplicate`.
- `fuel_import_batches` удаляются только в статусах `received` / `failed`.
- `vehicles` — soft-delete (`deleted_at`), только root.
- При удалении `fuel_import_batch`: каскадное удаление его `fuel_raw_entries` (если нет связанных `fuel_issues`), или orphan-защита если связи есть.

---

## 10. Что НЕ входит в MVP-1

1. ❌ Путевые листы, кандидаты, строки работы
2. ❌ Справочник людей (`fuel_persons`, `fuel_person_aliases`)
3. ❌ Автоматический fuzzy matching алиасов (только точное совпадение по name/alias)
4. ❌ Excel/CSV парсинг на бэкенде
5. ❌ Nextcloud интеграция
6. ❌ Печатные формы
7. ❌ Offline-first
8. ❌ Нормы расхода ГСМ
9. ❌ Telegram бот
10. ❌ OCR чеков

---

## 11. Структура кода (SyncServer)

```text
SyncServer/
├── app/
│   ├── models/
│   │   ├── __init__.py          # + fuel models
│   │   ├── vehicle.py           # Vehicle model
│   │   ├── vehicle_alias.py     # VehicleAlias model
│   │   ├── fuel_import_batch.py # FuelImportBatch model
│   │   ├── fuel_raw_entry.py    # FuelRawEntry model
│   │   ├── fuel_issue.py        # FuelIssue model
│   │   └── fuel_source_document.py # FuelSourceDocument model
│   │
│   ├── schemas/
│   │   ├── vehicle_schema.py
│   │   ├── fuel_import_schema.py
│   │   ├── fuel_issue_schema.py
│   │   └── fuel_summary_schema.py
│   │
│   ├── api/v1/
│   │   ├── vehicles.py          # Vehicle CRUD + aliases endpoints
│   │   ├── fuel_import.py       # Import batches + raw entries
│   │   ├── fuel_issues.py       # FuelIssue CRUD + status transitions
│   │   ├── fuel_summary.py      # Summary endpoint
│   │   └── fuel_source_docs.py  # Source documents
│   │
│   └── services/
│       ├── vehicle_service.py
│       ├── fuel_import_service.py
│       ├── fuel_issue_service.py
│       └── fuel_summary_service.py
│
├── alembic/versions/
│   └── XXXX_add_fuel_tables.py  # 6 таблиц + индексы
│
└── tests/
    ├── test_vehicle_api.py
    ├── test_fuel_import_api.py
    ├── test_fuel_issue_api.py
    └── test_fuel_summary_api.py
```

---

## 12. Backlog MVP-1 (checklist реализации)

| # | Задача | Файлы | Приоритет | Статус |
|---|--------|-------|-----------|--------|
| 1 | Alembic миграция: 6 таблиц + индексы | `alembic/versions/XXXX_fuel_mvp1.py` | P0 | [ ] |
| 2 | Модели: Vehicle, VehicleAlias | `app/models/vehicle.py`, `vehicle_alias.py` | P0 | [ ] |
| 3 | Модели: FuelImportBatch, FuelRawEntry | `app/models/fuel_import_batch.py`, `fuel_raw_entry.py` | P0 | [ ] |
| 4 | Модели: FuelIssue, FuelSourceDocument | `app/models/fuel_issue.py`, `fuel_source_document.py` | P0 | [ ] |
| 5 | Схемы Pydantic для всех моделей | `app/schemas/fuel_*.py` | P0 | [ ] |
| 6 | Vehicle API: CRUD + aliases | `app/api/v1/vehicles.py` | P0 | [ ] |
| 7 | FuelImportBatch API: create, list, get, process, delete | `app/api/v1/fuel_import.py` | P0 | [ ] |
| 8 | FuelRawEntry API: list, get, patch, create-issue | `app/api/v1/fuel_import.py` | P0 | [ ] |
| 9 | FuelIssue API: CRUD + status transitions | `app/api/v1/fuel_issues.py` | P0 | [ ] |
| 10 | FuelSummary API: group by vehicle/fuel_type/source | `app/api/v1/fuel_summary.py` | P0 | [ ] |
| 11 | FuelSourceDocument API: CRUD | `app/api/v1/fuel_source_docs.py` | P0 | [ ] |
| 12 | Сервисы: бизнес-логика | `app/services/fuel_*.py` | P0 | [ ] |
| 13 | Интеграция AuditEvent | Во всех сервисах | P1 | [ ] |
| 14 | Права доступа: проверка site_id + роль | Во всех endpoint'ах | P1 | [ ] |
| 15 | Регистрация роутов в `app/main.py` | `app/main.py` | P0 | [ ] |
| 16 | Django BFF: sync_client + views | `Warehouse_web/apps/sync_client/fuel_*.py`, `Warehouse_web/apps/bff_api/fuel_*.py` | P0 | [ ] |
| 17 | Django UI: страница сводки топлива | `Warehouse_web/templates/fuel/`, `Warehouse_web/apps/fuel/` | P1 | [ ] |
| 18 | Django UI: таблица заправок | там же | P1 | [ ] |
| 19 | Django UI: справочник техники | там же | P1 | [ ] |
| 20 | Django UI: загрузка партии + список партий | там же | P1 | [ ] |
| 21 | Django UI: экран проблемных записей | там же | P1 | [ ] |
| 22 | Unit tests: fuel services | `SyncServer/tests/test_fuel_*.py` | P1 | [ ] |
| 23 | Integration tests: DB-backed API | `SyncServer/tests/test_fuel_*_api.py` | P1 | [ ] |
| 24 | Stand smoke tests: все эндпоинты | curl / pytest against stand | P1 | [ ] |
| 25 | Playwright smoke: сводка + создание заправки | `tests/playwright/test_fuel_mvp1.py` | P2 | [ ] |
| 26 | Документация API (OpenAPI обновляется авто из FastAPI) | — | P2 | [ ] |

---

## 13. Риски MVP-1

| # | Риск | Мера |
|---|------|------|
| 1 | Неизвестен реальный формат данных от кладовщиков | MVP-1 принимает только JSON. Параллельно собираем образцы реальных таблиц. |
| 2 | Ручной ввод для 100+ записей — больно | Отдельный «грязный конвертер» (вне Scope MVP-1). |
| 3 | Дублирование Vehicle vs IssueObject | В MVP-1 IssueObject для vehicle НЕ используется. `issue_object_id` — nullable, заполняется позже при интеграции со складом. |
| 4 | Нет fuzzy matching → много ручного труда | MVP-1: точное совпадение по name или alias. Fuzzy — в MVP-2. |

---

## Appendix A: Что изменилось относительно Architecture Review

| Аспект | Было в ревью | Стало в MVP-1 |
|--------|-------------|---------------|
| Статусы FuelIssue | 8 статусов (`raw`, `needs_vehicle`, `needs_fuel_type`, ...) | 4 статуса + `problem_codes` JSONB |
| Статусы FuelRawEntry | `raw`, `parsing`, `parse_error`, `normalized`, `skipped` | Без изменений |
| Статусы FuelImportBatch | `received`, `validating`, `needs_review`, `processed`, `failed` | `validating` → `processing` |
| Таблицы | 12 таблиц (включая waybill-сущности) | 6 таблиц. Waybill-сущности — в MVP-3/4 |
| FuelPersons | Отдельная таблица | Вынесено из MVP-1. Только `fuel_recipient_name_raw` текстовое поле |
| Fuzzy matching | С MVP-2 | Подтверждено: в MVP-1 только точное совпадение |
| Excel-парсинг | MVP-6 | В MVP-1 — внешний конвертер, не на бэкенде |
| `WaybillPersonRole` | JSONB vs таблица | Не в MVP-1. В MVP-4 как `personnel` JSONB |
| API endpoints | ~35 (включая waybill) | ~25 (только fuel registry) |
