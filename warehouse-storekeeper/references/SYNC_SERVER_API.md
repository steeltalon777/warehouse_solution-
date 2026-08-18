# Карта SyncServer API (фактическая, по коду)

Источник истины: код `SyncServer/` (`main.py`, `app/api/routes_*.py`,
`app/schemas/*.py`, `app/services/*`). Собрано 2026-08-03. openapi.json в репо
нет — схема генерируется на лету: `GET /api/openapi.json` (docs: `/api/docs`).

## Базовые факты

- Префикс API: **`/api/v1`** (`main.py:165`).
- Аутентификация: заголовки **`X-User-Token`** и/или **`X-Device-Token`**
  (UUID-токены из БД; НЕ Bearer, НЕ Authorization). Подробно — `AUTH.md`.
- Request-ID: заголовок `X-Request-Id` принимается и всегда возвращается
  в ответе (middleware `main.py:63-100`).
- Идемпотентность: заголовка `Idempotency-Key` НЕТ. Используются поля тела
  `client_request_id` (операции) и `source_ref` (операции из документа).
- Роли: `root`, `chief_storekeeper`, `storekeeper`, `observer`.

## Эндпоинты, используемые скиллом

### Health

| Метод | Путь | Auth | Ответ 200 |
|---|---|---|---|
| GET | `/api/v1/health` | нет | `{"status": "ok"}` |

Дополнительно существуют `/health/detailed`, `/health/readiness`,
`/health/liveness`, `/ready` (скиллом не используются).

### Идентичность и права (prefix `/auth`, везде `X-User-Token`)

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/api/v1/auth/me` | Текущий пользователь + устройство. Ответ: `{"user": {"id", "username", "email", "full_name", "is_active", "is_root", "role", "default_site_id"}, "device": {...}\|null}` |
| GET | `/api/v1/auth/context` | Полный контекст: `{"user", "role", "is_root", "default_site", "available_sites": [{"site_id","code","name","is_active","permissions":{"can_view","can_operate","can_manage_catalog"}}], "permissions_summary": {"can_read_operations","can_create_operations","can_read_balances","can_manage_catalog","can_manage_root_admin","is_root"}, "device"}` |
| GET | `/api/v1/auth/sites` | Доступные площадки с учётом скоупов: `{"is_root": bool, "available_sites": [...]}` |

Отдельных эндпоинтов «whoami»/«capabilities» нет — их роль выполняют
`/auth/me` и `/auth/context`.

### Справочники (prefix `/catalog`, роли chief_storekeeper/storekeeper/observer)

| Метод | Путь | Query | Ответ 200 |
|---|---|---|---|
| GET | `/api/v1/catalog/sites` | `is_active=true` | `{"sites": [{"site_id","code","name","is_active","permissions":{...}}], "server_time"}` |
| GET | `/api/v1/catalog/units` | `updated_after?`, `limit=100 (1..1000)` | `{"units": [{"id","name","symbol","is_active","updated_at"}], "server_time", "next_updated_after"}` |
| GET | `/api/v1/catalog/read/items` | `search?`, `category_id?`, `page=1`, `page_size=20 (1..1000)`, `site_id?` | `{"items": [{"id","sku","name","category_id","category_name","unit_id","unit_symbol","description","is_active","hashtags","requires_review","review_status","updated_at"}], "total_count", "page", "page_size"}` |
| GET | `/api/v1/catalog/read/items/{item_id}` | — | карточка ТМЦ (тот же DTO); 404 `{"detail": "item not found"}` |

Прочее (скиллом не используется, существует): `/catalog/items|categories`
(инкрементальный pull с `updated_after`), `/catalog/categories/tree`,
`/catalog/read/categories*`, `POST /catalog/read/items/resolve`.

### Остатки (prefix `/balances`, те же read-роли)

| Метод | Путь | Query | Ответ 200 |
|---|---|---|---|
| GET | `/api/v1/balances` | `site_id?`, `item_id?` *(deprecated, но работает)*, `category_id?`, `search?`, `only_positive=false`, `page=1`, `page_size=100 (1..200)` | `{"items": [{"site_id","site_name","inventory_subject_id","subject_type","item_id","temporary_item_id","resolved_item_id","resolved_item_name","display_name","item_name","sku","unit_id","unit_symbol","category_id","category_name","qty"(строка-Decimal),"updated_at"}], "total_count", "page", "page_size"}` |
| GET | `/api/v1/balances/by-site` | `site_id` (обязателен), `only_positive`, `page`, `page_size` | тот же `BalanceListResponse` |
| GET | `/api/v1/balances/summary` | — | `{"accessible_sites_count", "summary": {"rows_count","sites_count","total_quantity"}}` |

### Операции (prefix `/operations`, `X-User-Token`)

Статусы: `draft`, `submitted`, `cancelled`. Типы (verbatim):
`RECEIVE`, `EXPENSE`, `WRITE_OFF`, `MOVE`, `ADJUSTMENT`, `ISSUE`, `ISSUE_RETURN`.
Скилл разрешает все, кроме `ADJUSTMENT`, и работает ТОЛЬКО со статусом `draft`.

| Метод | Путь | Назначение | Доступ скилла |
|---|---|---|---|
| GET | `/api/v1/operations` | Список. Query: `site_id`, `type`, `status`, `acceptance_state`, `created_by_user_id`, `search`, `item_ids` (CSV), `client_request_id`, `page=1`, `page_size=50 (1..100)`, даты-фильтры | ✅ |
| GET | `/api/v1/operations/{id}` | Карточка операции (404, если cancelled и не root) | ✅ |
| POST | `/api/v1/operations` | Создать draft (`OperationCreate`) | ✅ |
| POST | `/api/v1/operations/from-source-document` | Создать draft из исходного документа (`SourceDocumentOperationCreate`), дедуп по `source_ref` | ✅ |
| PATCH | `/api/v1/operations/{id}` | Изменить draft; `lines` **заменяют все строки целиком** | ✅ (только свой draft) |
| PATCH | `/api/v1/operations/{id}/effective-at` | Смена даты | ⛔ не используется в MVP |
| POST | `/api/v1/operations/{id}/submit` | Проведение | ⛔ **ЗАПРЕЩЕНО** |
| POST | `/api/v1/operations/{id}/accept-lines` | Приёмка | ⛔ **ЗАПРЕЩЕНО** |
| POST | `/api/v1/operations/{id}/cancel` | Отмена | ⛔ **ЗАПРЕЩЕНО** |
| POST | `/api/v1/operations/{id}/restore` | Восстановление (root) | ⛔ **ЗАПРЕЩЕНО** |
| DELETE | `/api/v1/operations/{id}` | Удаление cancelled | ⛔ **ЗАПРЕЩЕНО** |

#### `OperationCreate` (тело POST /operations)

```jsonc
{
  "operation_type": "RECEIVE",           // обязателен; alias "type"
  "site_id": 1,                          // обязателен
  "effective_at": null,
  "source_site_id": null,                // MOVE: обязателен, == site_id
  "destination_site_id": null,           // MOVE: обязателен; alias "target_site_id"
  "issued_to_user_id": null,
  "issued_to_name": null,                // max 255
  "issue_object_id": null,
  "issue_object_name_snapshot": null,
  "lines": [                             // min 1
    {"line_number": 1, "item_id": 10, "qty": 5, "batch": null, "comment": null}
    // qty: Decimal != 0 (>0 для всех типов, кроме ADJUSTMENT); alias "quantity"
    // item_id XOR temporary_item (temporary_item только для RECEIVE + требует client_request_id)
  ],
  "acceptance_required": false,
  "notes": null,                         // max 1000
  "client_request_id": null              // max 100; ключ идемпотентности (скоуп — пользователь)
}
```

Идемпотентность: повтор с тем же `client_request_id` и тем же payload
(hash) → возврат существующей операции; с другим payload →
`409 {"detail": {"code": "idempotency_payload_conflict", ...}}`.

#### `SourceDocumentOperationCreate` (тело POST /operations/from-source-document)

`extra="forbid"` — только перечисленные поля:

```jsonc
{
  "operation_type": "RECEIVE",           // обязателен
  "site_id": 1,                          // обязателен, ge=1
  "source_ref": "sha256:...",            // ОБЯЗАТЕЛЕН, 1..255 — ключ дедупликации
  "source_document_type": "ocr_scan",    // invoice|ocr_scan|csv_import|json_import|external_api
  "source_document_date": null,
  "effective_at": null, "source_site_id": null, "destination_site_id": null,
  "issued_to_user_id": null, "issued_to_name": null,
  "issue_object_id": null, "issue_object_name_snapshot": null,
  "lines": [                             // min 1; КАЖДАЯ строка обязана иметь item_id (int, ge=1)
    {"line_number": 1, "item_id": 10, "qty": 5, "batch": null, "comment": null,
     "source_item_name": "Подшипник 6205",   // max 255 — raw-имя из документа
     "source_item_sku": null,                // max 100
     "source_unit_name": "шт",               // max 100
     "source_category_name": null}           // max 255
  ],
  "notes": null, "client_request_id": null
}
```

Дедуп: `(source_ref, creation_source="source_document", created_by_user_id)`.
Тот же payload → существующая операция; другой payload →
`409 {"detail": {"code": "source_document_idempotency_conflict", ...}}`.
Ошибки строк: `422 {"detail": {"code": "source_document_line_unresolvable"|
"source_document_line_inactive"|"source_document_line_deleted", "line_number", "item_id", "reason"}}`.

#### `OperationUpdate` (PATCH /operations/{id})

Все поля optional: `notes`, `effective_at`, `source_site_id`,
`destination_site_id`, `issued_to_*`, `issue_object_*`,
`lines` (полная замена всех строк: delete + create, id перевыпускаются,
`source_*`-снимки НЕ принимаются), `operation_type`,
`expected_version` (int >= 1, optimistic locking; конфликт → доменный
`stale_version` через submit-конвой/409).

Роли PATCH: только создатель, `chief_storekeeper` или `root`
(`require_operation_owner_or_supervisor`). Не-draft → `409 "cannot update
operation with status {status}"`.

#### `OperationResponse` (ответ операций)

```jsonc
{
  "id": "uuid", "site_id": 1, "operation_type": "RECEIVE",
  "status": "draft", "version": 1,
  "effective_at": null, "source_site_id": null, "destination_site_id": null,
  "issued_to_user_id": null, "issued_to_name": null,
  "issue_object_id": null, "issue_object_name_snapshot": null,
  "acceptance_required": false, "acceptance_state": "not_required",
  "acceptance_resolved_at": null, "acceptance_resolved_by_user_id": null,
  "created_by_user_id": "uuid", "created_at": "...", "updated_at": "...",
  "submitted_at": null, "submitted_by_user_id": null,
  "cancelled_at": null, "cancelled_by_user_id": null,
  "notes": null, "display_number": "D-184",
  "creation_source": "manual|source_document|legacy",
  "source_ref": null,
  "lines": [{
    "id": 11, "line_number": 1, "inventory_subject_id": 101, "subject_type": "item",
    "item_id": 10, "temporary_item_id": null, "temporary_item_status": null,
    "resolved_item_id": 10, "resolved_item_name": "...",
    "source_item_name": "...", "source_item_sku": null,
    "source_unit_name": "...", "source_category_name": null,
    "item_name_snapshot": "...", "item_sku_snapshot": "...",
    "unit_name_snapshot": "...", "unit_symbol_snapshot": "...",
    "category_name_snapshot": "...",
    "qty": 5, "accepted_qty": 0, "lost_qty": 0,
    "batch": null, "comment": null,
    "is_draft_temporary": false, "temporary_draft_payload": null
  }]
}
```

### Документы (prefix `/documents`)

Эндпоинты генерации/рендера документов из операций существуют
(`POST /documents/generate`, `GET /documents/{id}`, `/render?format=html|pdf`,
список, смена статуса), **но загрузки исходных файлов (multipart upload)
НЕТ** — grep `UploadFile|File(|multipart|upload` по всему `app/` даёт 0.
См. `API_GAPS.md`.

## Матрица ролей (операции)

| Действие | root | chief_storekeeper | storekeeper | observer |
|---|---|---|---|---|
| Создать draft | ✅ | ✅ | ✅ | ✅ |
| Читать операции | ✅ | ✅ | ✅ | ✅ |
| Видеть cancelled | ✅ | ❌ (404) | ❌ (404) | ❌ (404) |
| Изменять draft | ✅ | ✅ | ✅ только свой | ❌ |
| submit | ✅ | ✅ | ✅ если сайт в scope | ❌ |
| cancel draft | ✅ | ✅ | ✅ только свой | ❌ |
| cancel submitted | ✅ | ❌ | ❌ | ❌ |
| delete cancelled | ✅ | ✅ | ✅ только свой | ❌ |
| restore | ✅ | ❌ | ❌ | ❌ |
| accept-lines | ✅ | ✅ | ✅ operate к destination | ❌ |

## Не используется скиллом (существует в API)

`/api/v1/push|pull|ping|bootstrap/sync|sync/status` (device sync),
`/api/v1/corrections`, `/api/v1/temporary-items` (модерация),
`/api/v1/admin/*`, `/api/v1/catalog/admin/*` (в т.ч. merge),
`/api/v1/documents/*` (генерация), `/api/v1/reports`, `/api/v1/assets`,
`/api/v1/review-items`, `/api/v1/issue-objects*`, `/api/v1/diagnostics`.
