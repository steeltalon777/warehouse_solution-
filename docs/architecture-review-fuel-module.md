# Architecture Review — Quartermaster Transport/Fuel Module

**Date:** 2026-07-01  
**Reviewer:** Architect  
**Context:** Проект Quartermaster (ERP/учёт для золотодобывающей артели). Существующий контур: SyncServer (FastAPI + PostgreSQL), Django Web Client (BFF), будущий WPF offline client. Добавляется новый домен: транспорт, ГСМ и путевые листы.

## TZ

None (исследовательская архитектурная ревизия)

## Verdict

**Approved with conditions.** Предложенная модель в целом корректна. Ниже — детальные замечания, уточнённая схема БД, API, жизненные циклы, roadmap и риски.

### Architecture Stress-Test Gate

Пройден. 🔴 Blockers: 0. 🟡 Warnings: 4 (все документированы). 🔵 Notes: 2. Подробнее — в [Appendix C](#appendix-c-architecture-stress-test-results).

---

## 1. Executive Summary

Предложенная концепция делит топливный контур на два чётких слоя:
- **Сырой слой** (`FuelImportBatch` → `FuelRawEntry`) — неизменяемое хранилище исходных данных «как пришло».
- **Нормализованный слой** (`FuelIssue`) — чистые записи заправок, привязанные к технике и топливу.
- **Путевой слой** (`WaybillCandidate` → `Waybill`) — надстройка над топливом, группировка и оформление путевых листов.

Главное архитектурное решение — **не смешивать FuelIssue и Waybill** — абсолютно правильное. Заправка и путевой лист — разные бизнес-события с разными источниками истины.

MVP фокусируется на вопросе: **«Какая техника сколько топлива получила за период, из какого источника и с каким качеством данных?»** — и это правильный приоритет.

**Ключевые улучшения относительно исходной модели:**
1. Явное разделение Vehicle (техника) и Person (люди) на уровне таблиц.
2. Связь Vehicle ↔ IssueObject через `issue_object_id` для будущей интеграции со складом (выдача запчастей на машину).
3. Использование существующих паттернов: AuditEvent, MachineBatch-подобный статусный lifecycle, версионирование.
4. `WaybillFuelLink` как отдельная таблица (правильно), плюс `link_type` для спорных/частичных случаев.
5. Материализованные сводки для быстрых отчётов (MVP-1).

---

## 2. Архитектурные замечания

### 2.1. Связь с существующим складским контуром

| Аспект | Решение | Обоснование |
|--------|---------|-------------|
| Справочник техники | Отдельная таблица `vehicles`, но с `issue_object_id` → `issue_objects` | IssueObject уже имеет тип `vehicle`. Связь через FK позволяет в будущем выдавать запчасти/масла на конкретную машину через штатный механизм ISSUE. |
| Справочник людей | Отдельная таблица `fuel_persons`, с `sync_user_id` → `users` и `issue_object_id` → `issue_objects` | Не все получатели топлива — пользователи системы. Не все пользователи — водители. Разделение чище. |
| Batch-импорт | Новая таблица `fuel_import_batches`, но lifecycle по образцу `machine_batches` | MachineBatch уже реализует статусную машину (received → validating → preview_ready → applying → applied → failed). Переиспользовать модель, а не код. |
| Аудит | Стандартная таблица `audit_events` с расширением `entity_type` | Не плодить отдельный audit для fuel. AuditEvent уже имеет `entity_type`, `entity_id`, `changes` JSONB, `actor_user_id`. |
| Документы | Новая таблица `fuel_source_documents` с `file_ref` для Nextcloud. Отдельно от `documents` (накладные). | `documents` заточены под PDF-накладные операций. Чеки АЗС и ведомости имеют другую природу. Можно будет позже унифицировать. |
| Offline/sync | Все новые таблицы получают `site_id`, UUID PK. Мутации — через Events в рамках UoW. | Совместимо с sequence-based sync (ADR-0016). `FuelIssue` и `Waybill` — это по сути «операции» топливного контура. |

### 2.2. Нормализация грязных данных

**Проблема:** «УАЗ», «уазик», «УАЗ фермер», «фермер» → одна машина.

**Решение:**
- `vehicle_aliases` — managed-алиасы (создаются вручную или полуавтоматически).
- `raw_entry.raw_data` JSONB — всегда хранит исходную строку.
- `raw_entry.problems` JSONB — диагностические сообщения («не удалось сопоставить технику 'уазик'»).
- Алгоритм матчинга: точное совпадение → совпадение по алиасу → fuzzy (trigram/Levenshtein) → ручной выбор.
- Fuzzy matching **не** должен автоматически назначать связь без confidence > порога.

**Риск:** Даже с алиасами будут несопоставленные записи. UI для ручного review — обязателен с MVP-1.

### 2.3. Гранулярность дат

**Проблема:** Месячные итоги от кладовщиков vs точные чеки АЗС.

**Решение:**
- `fuel_issues.granularity` — enum: `exact_time`, `date`, `shift`, `period_total`, `month_total`, `unknown`.
- `fuel_issues.date_exact` — для точных чеков.
- `fuel_issues.date_from` / `fuel_issues.date_to` — для периодов.
- При группировке для путевых листов: period_total записи распределяются пропорционально дням (или равномерно, в зависимости от конфигурации).

**Замечание к исходной модели:** поле `granularity` было предложено верно. Добавить `shift` как отдельный тип (смена: день/ночь).

### 2.4. Режимы учёта техники

**Проблема:** Одна и та же машина может в разное время работать в разных режимах.

**Решение (подтверждаю исходное):**
- Режим (`line_type`: `no_route`, `route`, `engine_hours`, `mixed`) — атрибут `WaybillWorkLine`, не `Vehicle`.
- `Vehicle.accounting_modes` — JSONB массив доступных режимов (подсказка для UI, но не ограничение).
- `Vehicle.default_fuel_norm_l_per_100km` и `default_fuel_norm_l_per_motohour` — значения по умолчанию, переопределяемые в `WaybillWorkLine`.

### 2.5. Разделение ролей людей в путевом листе

**Проблема:** Получатель топлива ≠ водитель в путевом листе ≠ фактический оператор.

**Решение (подтверждаю исходное):**
- `FuelIssue.fuel_recipient_person_id` — кто фактически получил/залил топливо.
- `Waybill.assigned_driver_id` — кто назначен водителем в путевом листе (для отчётности).
- `WaybillWorkLine` может в будущем иметь поле `actual_operator_id` — кто фактически работал на технике.
- Атрибут роли (`WaybillPersonRole`) — на уровне `Waybill` как JSONB `personnel: [{person_id, role}]`, а не отдельная таблица. Для MVP этого достаточно. Отдельную таблицу — в MVP-4 если потребуется.

### 2.6. Архитектурный паттерн: мутации через SyncServer

Все изменения топливных данных должны проходить через SyncServer API:
```
Client → Django BFF → SyncServer API (/api/v1/fuel/*) → SyncServer services → DB
```

Прямой доступ клиентов к БД — запрещён (как и для складского контура).

---

## 3. Модель данных (PostgreSQL)

### 3.1. Перечень таблиц

| # | Таблица | Назначение | Ключевые поля |
|---|---------|------------|---------------|
| 1 | `vehicles` | Справочник техники | `id` UUID PK, `site_id`, `name`, `normalized_name`, `plate_number`, `inventory_number`, `vehicle_class`, `fuel_types` JSONB, `accounting_modes` JSONB, `default_fuel_norm_l_per_100km`, `default_fuel_norm_l_per_motohour`, `default_waybill_template`, `issue_object_id`, `is_active` |
| 2 | `vehicle_aliases` | Алиасы техники | `id` UUID PK, `vehicle_id` FK, `alias`, `source`, `is_active` |
| 3 | `fuel_persons` | Справочник людей | `id` UUID PK, `site_id`, `full_name`, `normalized_name`, `role`, `sync_user_id` FK→users, `issue_object_id` FK→issue_objects, `is_active` |
| 4 | `fuel_person_aliases` | Алиасы людей | `id` UUID PK, `person_id` FK, `alias`, `source`, `is_active` |
| 5 | `fuel_import_batches` | Партия импорта топливных данных | `id` UUID PK, `site_id`, `batch_number`, `period_from`, `period_to`, `source_type`, `file_ref`, `uploaded_by_user_id`, `status`, `stats` JSONB, `warnings` JSONB, `errors` JSONB |
| 6 | `fuel_raw_entries` | Сырая запись (неизменяемая) | `id` UUID PK, `batch_id` FK, `row_index`, `source_ref`, `raw_data` JSONB, `parse_status`, `problems` JSONB, `matched_vehicle_id`, `matched_fuel_type`, `matched_liters`, `normalized_fuel_issue_id` FK |
| 7 | `fuel_issues` | Нормализованная заправка | `id` UUID PK, `site_id`, `raw_entry_id` FK, `vehicle_id` FK, `fuel_type`, `liters`, `amount`, `date_exact`, `date_from`, `date_to`, `granularity`, `source_type`, `source_document_id` FK, `fuel_recipient_person_id` FK, `fuel_recipient_name_raw`, `status`, `version` |
| 8 | `fuel_source_documents` | Документ-основание (чек/ведомость/скан) | `id` UUID PK, `site_id`, `document_type`, `document_number`, `document_date`, `issuer`, `file_ref`, `status` |
| 9 | `waybill_candidates` | Кандидат путевого листа | `id` UUID PK, `site_id`, `vehicle_id` FK, `period_from`, `period_to`, `suggested_template`, `suggested_work_mode`, `fuel_total_liters`, `fuel_issue_count`, `data_quality`, `assigned_driver_id` FK→fuel_persons, `fuel_summary` JSONB, `status`, `converted_to_waybill_id` FK |
| 10 | `waybills` | Путевой лист | `id` UUID PK, `site_id`, `vehicle_id` FK, `waybill_number`, `period_from`, `period_to`, `assigned_driver_id` FK→fuel_persons, `assigned_driver_name`, `transportation_type`, `communication_type`, `template_name`, `status`, `odo_start`, `odo_end`, `engine_hours_start`, `engine_hours_end`, `linked_fuel_total_liters`, `personnel` JSONB, `version` |
| 11 | `waybill_work_lines` | Строки работы путевого листа | `id` UUID PK, `waybill_id` FK, `line_number`, `line_type`, `date_from`, `date_to`, `purpose`, `origin`, `destination`, `work_site`, `mileage_km`, `engine_hours`, `fuel_norm_l_per_100km`, `fuel_norm_l_per_motohour`, `calculated_fuel_liters`, `actual_fuel_liters`, `fuel_deviation_liters` |
| 12 | `waybill_fuel_links` | Связь путевого листа с заправками | `id` UUID PK, `waybill_id` FK, `fuel_issue_id` FK, `linked_liters`, `link_type`, `comment` |

### 3.2. Ключевые индексы

```sql
-- Поиск алиасов (fuzzy matching)
CREATE INDEX idx_vehicle_aliases_alias ON vehicle_aliases USING btree(lower(alias));
CREATE INDEX idx_fuel_person_aliases_alias ON fuel_person_aliases USING btree(lower(alias));

-- Поиск заправок по технике и периоду (основной запрос MVP)
CREATE INDEX idx_fuel_issues_vehicle_period ON fuel_issues(vehicle_id, date_from, date_to)
    WHERE deleted_at IS NULL;

-- Сводка по периодам
CREATE INDEX idx_fuel_issues_site_period ON fuel_issues(site_id, date_from)
    WHERE deleted_at IS NULL AND status = 'confirmed';

-- Поиск проблемных записей
CREATE INDEX idx_fuel_issues_status ON fuel_issues(status) WHERE deleted_at IS NULL;

-- Поиск сырых записей по batch
CREATE INDEX idx_fuel_raw_entries_batch ON fuel_raw_entries(batch_id, parse_status);

-- Кандидаты по технике и периоду
CREATE INDEX idx_waybill_candidates_vehicle_period ON waybill_candidates(vehicle_id, period_from, period_to);

-- Связи заправок (поиск от fuel_issue)
CREATE INDEX idx_waybill_fuel_links_issue ON waybill_fuel_links(fuel_issue_id);

-- Полнотекстовый поиск по названиям техники
CREATE INDEX idx_vehicles_normalized_name ON vehicles USING btree(lower(normalized_name));
```

### 3.3. Аудит-поля (стандартный набор)

Каждая таблица, допускающая редактирование, содержит:
- `created_by_user_id` UUID FK → users
- `created_at` TIMESTAMPTZ DEFAULT now()
- `updated_by_user_id` UUID FK → users (nullable)
- `updated_at` TIMESTAMPTZ DEFAULT now()
- `deleted_at` TIMESTAMPTZ (nullable, soft-delete)
- `deleted_by_user_id` UUID FK → users (nullable)

Плюс `version INTEGER DEFAULT 1` на `fuel_issues` и `waybills` (optimistic locking).

### 3.4. Связь с существующей схемой

```
vehicles.issue_object_id → issue_objects.id (nullable, soft link)
fuel_persons.sync_user_id → users.id (nullable)
fuel_persons.issue_object_id → issue_objects.id (nullable, soft link)
fuel_issues.source_document_id → fuel_source_documents.id
waybill_candidates.converted_to_waybill_id → waybills.id
```

---

## 4. API Endpoints (минимальный MVP)

Базовый префикс: `/api/v1/fuel/` в SyncServer. BFF в Django зеркалирует с префиксом `/bff/api/v1/fuel/`.

### 4.1. Партии импорта

| Метод | Путь | Описание |
|-------|------|----------|
| `POST` | `/fuel/import-batches` | Создать партию (multipart: JSON metadata + файл) |
| `GET` | `/fuel/import-batches` | Список партий (пагинация, фильтры: `site_id`, `period_from`, `period_to`, `status`) |
| `GET` | `/fuel/import-batches/{batch_id}` | Детали партии + статистика |
| `POST` | `/fuel/import-batches/{batch_id}/process` | Запустить разбор/нормализацию |
| `DELETE` | `/fuel/import-batches/{batch_id}` | Удалить партию (только `received`/`failed`) |

### 4.2. Сырые записи

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/fuel/import-batches/{batch_id}/raw-entries` | Список сырых записей партии |
| `GET` | `/fuel/import-batches/{batch_id}/raw-entries/{entry_id}` | Детали сырой записи |
| `PATCH` | `/fuel/import-batches/{batch_id}/raw-entries/{entry_id}` | Ручная коррекция (match vehicle, fuel_type, liters) |
| `GET` | `/fuel/raw-entries/problems` | Все проблемные записи (фильтр: `site_id`, `batch_id`) |

### 4.3. Заправки (FuelIssue)

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/fuel/issues` | Список заправок (пагинация, фильтры: `site_id`, `vehicle_id`, `period_from`, `period_to`, `fuel_type`, `status`, `source_type`) |
| `GET` | `/fuel/issues/{issue_id}` | Детали заправки |
| `POST` | `/fuel/issues` | Создать заправку вручную |
| `PATCH` | `/fuel/issues/{issue_id}` | Обновить заправку (только `raw`/`needs_*`) |
| `POST` | `/fuel/issues/{issue_id}/confirm` | Подтвердить (статус → `confirmed`) |
| `POST` | `/fuel/issues/{issue_id}/exclude` | Исключить (статус → `excluded`) |
| `POST` | `/fuel/issues/{issue_id}/mark-duplicate` | Пометить дубликатом (статус → `duplicate`) |

### 4.4. Сводка топлива (ключевой отчёт MVP)

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/fuel/summary` | **Сводка топлива по технике за период.** Параметры: `site_id`, `period_from`, `period_to`, `vehicle_id?`, `fuel_type?`, `group_by` (vehicle / fuel_type / source_type / month). Возвращает массив групп с `total_liters`, `issue_count`, `status_breakdown`, `source_breakdown`. |

### 4.5. Справочник техники

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/fuel/vehicles` | Список техники (фильтры: `site_id`, `is_active`, `vehicle_class`) |
| `GET` | `/fuel/vehicles/{vehicle_id}` | Детали |
| `POST` | `/fuel/vehicles` | Создать |
| `PATCH` | `/fuel/vehicles/{vehicle_id}` | Обновить |
| `DELETE` | `/fuel/vehicles/{vehicle_id}` | Soft-delete |
| `GET` | `/fuel/vehicles/{vehicle_id}/aliases` | Алиасы |
| `POST` | `/fuel/vehicles/{vehicle_id}/aliases` | Добавить алиас |
| `DELETE` | `/fuel/vehicles/{vehicle_id}/aliases/{alias_id}` | Удалить алиас |

### 4.6. Справочник людей

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/fuel/persons` | Список людей (фильтры: `site_id`, `role`, `is_active`) |
| `GET` | `/fuel/persons/{person_id}` | Детали |
| `POST` | `/fuel/persons` | Создать |
| `PATCH` | `/fuel/persons/{person_id}` | Обновить |
| `GET` | `/fuel/persons/{person_id}/aliases` | Алиасы |
| `POST` | `/fuel/persons/{person_id}/aliases` | Добавить алиас |
| `DELETE` | `/fuel/persons/{person_id}/aliases/{alias_id}` | Удалить алиас |

### 4.7. Матчинг алиасов (utility)

| Метод | Путь | Описание |
|-------|------|----------|
| `POST` | `/fuel/aliases/match-vehicle` | Предложить варианты техники для сырого названия. Body: `{raw_name, site_id}`. Response: `[{vehicle_id, name, confidence, source}]` |
| `POST` | `/fuel/aliases/match-person` | Аналогично для людей |

### 4.8. Кандидаты путевых листов

| Метод | Путь | Описание |
|-------|------|----------|
| `POST` | `/fuel/waybill-candidates/generate` | Сгенерировать кандидатов за период. Body: `{site_id, period_from, period_to}` |
| `GET` | `/fuel/waybill-candidates` | Список кандидатов (фильтры: `site_id`, `period_from`, `period_to`, `status`) |
| `GET` | `/fuel/waybill-candidates/{candidate_id}` | Детали кандидата (включая fuel_summary) |
| `PATCH` | `/fuel/waybill-candidates/{candidate_id}` | Обновить (назначить водителя, изменить шаблон) |
| `POST` | `/fuel/waybill-candidates/{candidate_id}/confirm` | Подтвердить |
| `POST` | `/fuel/waybill-candidates/{candidate_id}/reject` | Отклонить |
| `POST` | `/fuel/waybill-candidates/{candidate_id}/convert` | Конвертировать в Waybill |

### 4.9. Путевые листы

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/fuel/waybills` | Список (фильтры: `vehicle_id`, `period_from`, `period_to`, `status`) |
| `GET` | `/fuel/waybills/{waybill_id}` | Детали (+ work_lines, fuel_links) |
| `POST` | `/fuel/waybills` | Создать вручную |
| `PATCH` | `/fuel/waybills/{waybill_id}` | Обновить (только `draft`) |
| `POST` | `/fuel/waybills/{waybill_id}/submit` | Подтвердить |
| `POST` | `/fuel/waybills/{waybill_id}/cancel` | Отменить |
| `POST` | `/fuel/waybills/{waybill_id}/work-lines` | Добавить строку работы |
| `PATCH` | `/fuel/waybills/{waybill_id}/work-lines/{line_id}` | Обновить строку |
| `DELETE` | `/fuel/waybills/{waybill_id}/work-lines/{line_id}` | Удалить строку |
| `POST` | `/fuel/waybills/{waybill_id}/fuel-links` | Связать заправку |
| `DELETE` | `/fuel/waybills/{waybill_id}/fuel-links/{link_id}` | Отвязать заправку |

### 4.10. JSON DTO (ключевые структуры)

**FuelIssue (response):**
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
  "fuel_recipient_person": {"id": "uuid", "full_name": "Иванов И.И."},
  "fuel_recipient_name_raw": "Иванов",
  "status": "confirmed",
  "comment": null,
  "version": 2,
  "created_at": "2026-06-20T10:00:00+07:00",
  "confirmed_at": "2026-06-21T09:00:00+07:00"
}
```

**FuelSummary (response):**
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
      "status_breakdown": {"confirmed": 5, "needs_review": 2},
      "source_breakdown": {
        "gas_station_receipt": {"liters": 200.0, "count": 4},
        "keeper_month_summary": {"liters": 145.5, "count": 3}
      },
      "fuel_type_breakdown": {
        "diesel_winter": {"liters": 200.0, "count": 4},
        "ai_92": {"liters": 145.5, "count": 3}
      },
      "data_quality": "partial",
      "problem_count": 2
    }
  ],
  "totals": {
    "total_liters": 12500.0,
    "total_issues": 145,
    "total_vehicles": 12
  }
}
```

**WaybillCandidate (response):**
```json
{
  "id": "uuid",
  "site_id": 1,
  "vehicle": {"id": "uuid", "name": "УАЗ Фермер"},
  "period_from": "2026-06-01",
  "period_to": "2026-06-30",
  "suggested_template": "monthly_no_route",
  "suggested_work_mode": "no_route",
  "fuel_total_liters": 345.5,
  "fuel_issue_count": 7,
  "data_quality": "partial",
  "assigned_driver": null,
  "fuel_summary": {
    "diesel_winter": {"liters": 200.0, "count": 4},
    "ai_92": {"liters": 145.5, "count": 3}
  },
  "status": "generated",
  "created_at": "2026-07-01T08:00:00+07:00"
}
```

---

## 5. Жизненные циклы и статусы

### 5.1. FuelImportBatch

```
received ──→ validating ──→ needs_review ──→ processed
                  │                              │
                  └──────────→ failed ←──────────┘
```

| Статус | Описание | Допустимые переходы |
|--------|----------|---------------------|
| `received` | Партия загружена, сырые записи созданы | → `validating`, → `failed` |
| `validating` | Идёт автоматический разбор (NER, матчинг) | → `needs_review`, → `failed` |
| `needs_review` | Есть проблемные записи, ждёт ручной проверки | → `validating` (повторный разбор), → `processed` |
| `processed` | Все записи обработаны (все FuelRawEntry → normalized/skipped) | Конечный |
| `failed` | Критическая ошибка (файл не читается, формат не распознан) | Конечный, можно удалить |

### 5.2. FuelRawEntry

```
raw ──→ parsing ──→ parse_error ──→ raw (после ручной правки)
  │         │
  │         └──→ normalized (создан FuelIssue)
  │
  └──→ skipped
```

| Статус | Описание |
|--------|----------|
| `raw` | Как загружено |
| `parsing` | В процессе автоматического разбора |
| `parse_error` | Не удалось разобрать автоматически, нужна ручная правка |
| `normalized` | Успешно разобрано, создан FuelIssue (ссылка в `normalized_fuel_issue_id`) |
| `skipped` | Пропущено (пустая строка, заголовок таблицы, нерелевантная запись) |

### 5.3. FuelIssue

```
raw ──┐
      ├──→ needs_vehicle ──┐
      ├──→ needs_fuel_type─┤
      ├──→ needs_period ───┤
      └──→ needs_review ───┤
                            ↓
                         confirmed ──→ excluded
                            │            duplicate
                            ↓
                    (используется в WaybillFuelLink)
```

| Статус | Описание | Допустимые переходы |
|--------|----------|---------------------|
| `raw` | Только создана из RawEntry или вручную | → любой `needs_*`, → `confirmed` |
| `needs_vehicle` | Техника не определена | → `raw`, → `needs_*`, → `confirmed` |
| `needs_fuel_type` | Тип топлива не определён | → `raw`, → `needs_*`, → `confirmed` |
| `needs_period` | Дата/период не ясны | → `raw`, → `needs_*`, → `confirmed` |
| `needs_review` | Требует ручной проверки (любая причина) | → `confirmed`, → `excluded`, → `duplicate` |
| `confirmed` | Проверена, готова к использованию | → `excluded` (отмена), → `duplicate` |
| `excluded` | Исключена из учёта (не техника артели, ошибочная) | → `confirmed` (восстановление) |
| `duplicate` | Дубликат другой записи | → `confirmed` (восстановление) |

**Правило:** Только `confirmed` записи участвуют в сводках и кандидатах путевых листов. `needs_*` записи подсвечиваются в problem dashboard.

### 5.4. WaybillCandidate

```
generated ──→ needs_driver ──→ needs_review ──→ confirmed ──→ converted_to_waybill
                                                rejected
```

| Статус | Описание | Допустимые переходы |
|--------|----------|---------------------|
| `generated` | Автоматически создан из группировки топлива | → `needs_driver`, → `needs_review`, → `confirmed` |
| `needs_driver` | Не назначен водитель | → `generated`, → `confirmed` |
| `needs_review` | Требует ручной проверки (например, data_quality=poor) | → `confirmed`, → `rejected` |
| `confirmed` | Подтверждён ответственным | → `converted_to_waybill`, → `rejected` |
| `rejected` | Отклонён (не будет путевого листа) | → `confirmed` (восстановление) |

### 5.5. Waybill

По образу существующего `Operation` lifecycle:

```
draft ──→ submitted ──→ cancelled
              │
              └──→ void (в будущем)
```

| Статус | Описание | Допустимые переходы |
|--------|----------|---------------------|
| `draft` | Черновик. Можно редактировать строки, менять связи с заправками. | → `submitted`, → `cancelled` |
| `submitted` | Подтверждён. Неизменяем. | → `cancelled` (root only) |
| `cancelled` | Отменён. Связи с заправками разорваны (или помечены). | Конечный |

**Правило:** После submit — строки работы, связи с заправками и одометр/моточасы заморожены. Отмена — только root.

---

## 6. Аудит

### 6.1. Использование существующего AuditEvent

Все мутации топливных сущностей пишут события в `audit_events` через стандартный `audit_helper.record_audit_event()`:

| Entity Type | Пример события |
|-------------|----------------|
| `fuel_issue` | `fuel_issue.created`, `fuel_issue.confirmed`, `fuel_issue.excluded`, `fuel_issue.updated` |
| `fuel_import_batch` | `fuel_import_batch.uploaded`, `fuel_import_batch.processed` |
| `vehicle` | `vehicle.created`, `vehicle.updated` |
| `waybill` | `waybill.created`, `waybill.submitted`, `waybill.cancelled` |
| `waybill_fuel_link` | `waybill_fuel_link.created`, `waybill_fuel_link.removed` |

### 6.2. Что хранить

- `entity_type` + `entity_id` — идентификация сущности.
- `changes` JSONB — diff (старое/новое значение изменённых полей).
- `actor_user_id` — кто совершил действие.
- `site_id` — контекст.
- `summary` — человекочитаемое описание.

### 6.3. Исходные документы (чеки, сканы)

- `fuel_source_documents.file_ref` — путь/ссылка в Nextcloud.
- `fuel_raw_entries.raw_data` — точная копия исходных данных (не удаляется).
- `fuel_import_batches.file_ref` — оригинальный загруженный файл.
- Сами файлы хранятся в Nextcloud; SyncServer хранит только ссылки и метаданные.

**Аудит-след:** Сырой слой (`fuel_raw_entries`) не очищается и не редактируется после импорта. Это неизменяемый журнал исходных данных.

### 6.4. Неизменяемость

- `fuel_raw_entries` — иммутабельны после создания (кроме поля `parse_status` и `problems` в процессе разбора).
- `fuel_issues` после `confirmed` — изменяемы только для перехода в `excluded`/`duplicate`; поля данных (liters, vehicle_id, etc.) заморожены.
- `waybills` после `submitted` — полностью заморожены (кроме отмены).
- Все изменения audit- trail через `audit_events`.

---

## 7. Этапы разработки (Roadmap)

### MVP-1: Централизованный реестр заправок (оценка: 2-3 недели)

**Цель:** ответ на вопрос «какая техника сколько топлива получила за месяц?»

**Что входит:**
- Таблицы: `vehicles`, `fuel_import_batches`, `fuel_raw_entries`, `fuel_issues`, `fuel_source_documents`.
- API: создание партии, загрузка сырых записей, создание/редактирование FuelIssue вручную, сводка топлива.
- Ручной ввод заправок через API (без партии, напрямую в FuelIssue).
- Простой импорт через JSON (структура заранее известна).
- Базовый справочник техники (CRUD).
- Отчёт-сводка по технике за период.
- Базовый UI в Django: таблица заправок с фильтрацией по технике/периоду, экран сводки.

**Что НЕ входит:**
- Автоматическая нормализация (алиасы, fuzzy matching).
- Путевые листы.
- Загрузка файлов Excel/CSV.

### MVP-2: Нормализация и алиасы (оценка: 2-3 недели)

**Цель:** автоматизировать разбор грязных данных.

**Что входит:**
- Таблицы: `vehicle_aliases`, `fuel_person_aliases`, `fuel_persons`.
- API: матчинг алиасов, ручная коррекция RawEntry, создание/управление алиасами.
- Алгоритм: точное совпадение → алиас → fuzzy (trigram) с порогом → ручной выбор.
- Problem dashboard: экран со списком записей в статусах `needs_*`.
- Review flow: оператор просматривает проблемные записи и вручную подтверждает/исправляет связи.
- FuelSourceDocument management.

**Что НЕ входит:**
- Парсинг Excel/CSV произвольной структуры.
- Путевые листы.

### MVP-3: Кандидаты путевых листов (оценка: 2-3 недели)

**Цель:** группировка топлива по технике и периоду, подготовка к путевым листам.

**Что входит:**
- Таблицы: `waybill_candidates`.
- Генерация кандидатов: группировка confirmed FuelIssue по `(site_id, vehicle_id, year_month)`.
- Расчёт `data_quality` на основе `source_type` и `granularity`:
  - `good`: все записи из чеков АЗС / точные даты.
  - `partial`: смесь точных и итоговых.
  - `poor`: только месячные итоги.
- Назначение водителя.
- Подтверждение/отклонение кандидата.
- Простой UI для просмотра и управления кандидатами.

**Что НЕ входит:**
- Конвертация в Waybill (только в MVP-4).
- Строки работы (work lines).

### MVP-4: Путевые листы (оценка: 3-4 недели)

**Цель:** полноценные путевые листы со строками работы и связями заправок.

**Что входит:**
- Таблицы: `waybills`, `waybill_work_lines`, `waybill_fuel_links`.
- Конвертация `WaybillCandidate` → `Waybill`.
- Ручное создание путевого листа.
- Управление строками работы (CRUD).
- Привязка/отвязка заправок.
- Draft → submit → cancel lifecycle.
- Одометр, моточасы, нормы расхода.
- UI для работы с путевыми листами.

**Что НЕ входит:**
- Печатные формы (MVP-5).
- Экспорт (MVP-5).

### MVP-5: Документы и отчёты (оценка: 2-3 недели)

**Цель:** печатные формы, экспорт, Nextcloud.

**Что входит:**
- Интеграция с Nextcloud: загрузка сканов чеков, привязка к `fuel_source_documents`.
- Генерация PDF путевого листа (шаблон).
- Экспорт сводок в Excel.
- Аналитические отчёты: топливо по месяцам, сравнение с нормами, перерасход.
- Архивация документов.

### MVP-6: Оптимизация ввода (оценка: 3-4 недели)

**Цель:** снизить трудозатраты на ввод данных.

**Что входит:**
- Парсинг Excel: загрузка реальных таблиц кладовщиков с маппингом колонок.
- Парсинг CSV из топливных карт (если используются).
- Telegram/мессенджер-бот для быстрого внесения заправки с мобильного.
- Сканирование чеков АЗС с OCR (опционально, высокая сложность).

---

## 8. Риски

### 🔴 Блокеры (требуют решения до старта MVP-1)

| # | Риск | Влияние | Рекомендация |
|---|------|---------|--------------|
| 1 | **Дублирование справочника техники.** Vehicle создаётся отдельно от IssueObject (vehicle). Если параллельно вести две таблицы — рассинхрон. | Высокое | Явно решить: либо Vehicle — единственный справочник, а `issue_object_id` только для связи, НО IssueObject используется только для выдачи запчастей (issue). В MVP IssueObject для vehicle не используется совсем. |
| 2 | **Неизвестный реальный формат данных.** Если кладовщики ведут учёт в произвольных Excel-таблицах с разной структурой — автоматический парсинг в MVP-1 невозможен. | Высокое | В MVP-1 принимать только JSON со строгой схемой. Перед MVP-2 получить реальные образцы таблиц. |

### 🟡 Предупреждения (допустимо, требует внимания)

| # | Риск | Влияние | Рекомендация |
|---|------|---------|--------------|
| 3 | **Качество алиасов.** Алиасы никогда не покроют 100% вариантов. Всегда будет ручной труд. | Среднее | UI для ручного review — с MVP-1. Дашборд проблемных записей — сразу. |
| 4 | **Гранулярность period_total.** Как распределять месячный итог по дням для путевого листа? | Среднее | По умолчанию — равномерно по рабочим дням. В будущем — настраиваемое правило. |
| 5 | **Юридические требования к путевым листам.** Модель может не покрывать обязательные реквизиты. | Среднее | Выделить в отдельный research до MVP-4. Не блокирует MVP-1/2/3. |
| 6 | **Производительность сводок.** При 100k+ записей запрос `GROUP BY vehicle, period` без материализации будет медленным. | Низкое (MVP) | В MVP-1 данных мало (< 10k). Для будущего: материализованное представление или кэш. |
| 7 | **Offline-first конфликты.** Если два кладовщика в офлайне запишут заправку на одну машину за один день, при синхронизации нужна дедупликация. | Низкое (MVP) | В MVP-1 все данные вводятся через веб. Offline сценарий — v3.x. |

### 🔵 Заметки

| # | Риск | Рекомендация |
|---|------|--------------|
| 8 | Нет учёта остатков топлива в баках. | Осознанное решение для MVP. Добавить позже, если потребуется. |
| 9 | Нет интеграции с GPS/тахографами. | Не для MVP. Позже — как источник пробега. |
| 10 | Нет связи с нормами расхода ГСМ (утверждённые нормы). | Заложить поле `default_fuel_norm` в Vehicle. Полноценный справочник норм — позже. |

---

## 9. Вопросы к заказчику / пользователю

Эти вопросы необходимо прояснить до или во время MVP-1:

1. **Сколько единиц техники в артели?** 10-20 или 100+? Это влияет на UI и стратегию индексов.

2. **Сколько записей о заправках в месяц?** 100 или 10 000? Влияет на необходимость batch-импорта vs ручной ввод.

3. **Как сейчас выглядят реальные документы от кладовщиков?** Нужны образцы (скриншоты, файлы). Без этого автоматический парсинг невозможен.

4. **Есть ли стационарные заправочные станции (свои ёмкости) на территории?** Это влияет на модель: своя заправка = `own_fuel_station`, нужен учёт остатков в ёмкостях?

5. **Все ли топливо покупается на внешних АЗС?** Или есть своя цистерна/склад ГСМ?

6. **Кто будет вносить данные?** Один ответственный в офисе или несколько кладовщиков на участках? Нужен ли разный уровень доступа?

7. **Какие виды топлива используются?** Только дизель (летний/зимний) и бензин (АИ-92/95)? Газ? Масла?

8. **Есть ли существующие списки техники в электронном виде?** В каком формате? Можно ли их импортировать?

9. **Нужна ли интеграция с 1С или другой бухгалтерией?** Если да — нужен экспорт в согласованном формате.

10. **Используются ли топливные карты с электронными отчётами?** Если да — можно автоматизировать импорт.

11. **Как часто меняется парк техники?** Продажа, покупка, списание. Это влияет на управление `is_active`.

12. **Требуется ли учёт топлива по подразделениям/участкам?** Или достаточно общего котла по артели?

13. **Как выглядит процесс утверждения путевого листа?** Кто подписывает, какие реквизиты обязательны?

---

## 10. Backlog MVP

Приоритизированный список задач для первого этапа:

| # | Задача | Приоритет | MVP |
|---|--------|-----------|-----|
| 1 | Миграция: таблицы `vehicles`, `vehicle_aliases` | P0 | 1 |
| 2 | Миграция: таблицы `fuel_import_batches`, `fuel_raw_entries` | P0 | 1 |
| 3 | Миграция: таблицы `fuel_issues`, `fuel_source_documents` | P0 | 1 |
| 4 | SyncServer: Vehicle CRUD endpoints + aliases | P0 | 1 |
| 5 | SyncServer: FuelImportBatch + RawEntry endpoints | P0 | 1 |
| 6 | SyncServer: FuelIssue CRUD + ручной ввод | P0 | 1 |
| 7 | SyncServer: FuelSummary endpoint (сводка) | P0 | 1 |
| 8 | SyncServer: AuditEvent integration для fuel-сущностей | P1 | 1 |
| 9 | Django BFF: зеркалирование всех fuel endpoints | P0 | 1 |
| 10 | Django UI: экран сводки топлива | P1 | 1 |
| 11 | Django UI: таблица заправок с фильтрацией | P1 | 1 |
| 12 | Django UI: справочник техники | P1 | 1 |
| 13 | Django UI: загрузка партии (JSON) | P1 | 1 |
| 14 | Права доступа: fuel-операции для ролей | P1 | 1 |
| 15 | Тесты: unit + интеграционные для fuel API | P1 | 1 |
| 16 | Playwright smoke-тесты: сводка, создание заправки | P2 | 1 |
| 17 | Миграция: `fuel_persons`, `fuel_person_aliases` | P0 | 2 |
| 18 | Алгоритм матчинга алиасов (точный + fuzzy) | P0 | 2 |
| 19 | Problem dashboard UI | P1 | 2 |
| 20 | Review flow UI (исправление проблемных записей) | P1 | 2 |
| 21 | Миграция: `waybill_candidates` | P0 | 3 |
| 22 | Генерация кандидатов из FuelIssue | P0 | 3 |
| 23 | UI для кандидатов путевых листов | P1 | 3 |
| 24 | Миграция: `waybills`, `waybill_work_lines`, `waybill_fuel_links` | P0 | 4 |
| 25 | Конвертация Candidate → Waybill | P0 | 4 |
| 26 | Waybill CRUD + work lines | P0 | 4 |

---

## Appendix A: Сравнение с существующими паттернами

| Существующий паттерн | Аналог в Fuel-модуле | Статус |
|----------------------|---------------------|--------|
| `Operation` (draft→submitted→cancelled) | `Waybill` | Переиспользовать lifecycle |
| `MachineBatch` (received→validating→preview→applied) | `FuelImportBatch` | Переиспользовать статусную модель |
| `IssueObject` + `IssueObjectAlias` | `Vehicle` + `VehicleAlias` | Аналогичная модель, отдельные таблицы |
| `AuditEvent` | `AuditEvent` с entity_type=fuel_* | Переиспользовать как есть |
| `Document` (накладные) | `FuelSourceDocument` | Отдельно, разная природа |
| `OperationLine` (строки операций) | `WaybillWorkLine` | Аналогичный паттерн |
| `InventorySubject` (каноническая ссылка) | Не требуется | Fuel не имеет аналога временных ТМЦ |
| `Events` (sequence-based sync) | Events для fuel-сущностей | Добавить `event_type` для fuel |
| `balances` (derived read-model) | `fuel_summary` (отчёт, не таблица) | Для MVP — вычисляется на лету |

## Appendix B: Что НЕ делаем в MVP

1. ❌ Учёт остатков топлива в баках техники.
2. ❌ Учёт топлива в собственных ёмкостях/цистернах.
3. ❌ Интеграция с GPS/тахографами.
4. ❌ Электронные путевые листы с ЭП (электронной подписью).
5. ❌ Полноценный парсинг произвольных Excel-файлов (только JSON-импорт + ручной ввод).
6. ❌ Полноценный offline-first для топливного контура (только через веб).
7. ❌ Печатные формы путевых листов (MVP-5).
8. ❌ Справочник утверждённых норм расхода ГСМ (только default-значения на технике).
9. ❌ Учёт масел и технических жидкостей.
10. ❌ Маршрутные листы с геоточками.
11. ❌ Мобильное приложение (MVP-6).

## Appendix C: Architecture Stress-Test Results

**Date:** 2026-07-01  
**Gate:** Passed (0 🔴 Blockers)

### 🔴 Blockers: 0

Блокеров не выявлено. План архитектурно состоятелен.

### 🟡 Warnings: 4

| # | Warning | Checklist | Resolution |
|---|---------|-----------|------------|
| W1 | **Nextcloud circuit breaker.** При недоступности Nextcloud в MVP-5 нет плана деградации. | Failure Modes — external services | Добавить research-задачу в MVP-5: circuit breaker + retry + graceful degradation (файлы не загружены → метка `pending_upload`). |
| W2 | **Синхронность batch-обработки.** Не указано, что `POST .../process` должен быть асинхронным. | Failure Modes — blocking requests | Уточнить в реализации MVP-1: `POST /fuel/import-batches/{id}/process` возвращает 202 Accepted, обработка в background task, статус — через `GET /fuel/import-batches/{id}`. |
| W3 | **N+1 в сводке топлива.** При JOIN с vehicles, fuel_source_documents возможен N+1. | Scalability — N+1 queries | Документировать в API-сервисе: summary query использует `joinedload(vehicle)`, `joinedload(source_document)` — один запрос с JOIN, а не N+1. |
| W4 | **Порог fuzzy matching.** Не указан confidence threshold для автоматического матчинга алиасов. | Coupling — undefined behavior | Уточнить в MVP-2: порог по умолчанию = 0.8 (trigram similarity), конфигурируется. Ниже порога → `needs_review`. |

### 🔵 Notes: 2

| # | Note | Checklist | Recommendation |
|---|------|-----------|----------------|
| N1 | **Fuel health endpoint.** Отсутствует `/api/v1/fuel/health` для мониторинга. | Observability — health endpoints | Добавить в MVP-2: возвращает DB connectivity + количество проблемных записей. |
| N2 | **Логирование ошибок.** AuditEvent покрывает бизнес-события, но не runtime-ошибки (ошибки парсинга, таймауты). | Observability — error surfacing | Добавить структурированные error-события в лог (structured logging) для ошибок batch-обработки и fuzzy matching.
