# Contract Package: Operation Reliability (Stages 0–2)

**Дата заморозки:** 2026-07-15
**Источник ТЗ:** `docs/TZ-ANGULAR_OPERATION_RELIABILITY_SWARM.md`
**Архитектурное ревью:** `docs/ARCHITECTURE_REVIEW_ANGULAR_UI_DIAGNOSTICS.md` (frozen)
**Статус:** Заморожено до старта реализации. Изменения только через ADR.

---

## Содержание

1. [Глоссарий и сокращения](#1-глоссарий-и-сокращения)
2. [Идентификаторы (Identifier Lifecycle)](#2-идентификаторы-identifier-lifecycle)
3. [HTTP-заголовки](#3-http-заголовки)
4. [State Machine (фронтенд)](#4-state-machine-фронтенд)
5. [DTO и контракты данных](#5-dto-и-контракты-данных)
6. [API контракты](#6-api-контракты)
7. [Error Contracts](#7-error-contracts)
8. [HTTP Response Matrix](#8-http-response-matrix)
9. [Примеры запросов/ответов](#9-примеры-запросовответов)
10. [Out-of-band поведение и таймауты](#10-out-of-band-поведение-и-таймауты)
11. [Правила для обратной совместимости](#11-правила-для-обратной-совместимости)
12. [Verification checklist для Coordinator](#12-verification-checklist-для-coordinator)

---

## 1. Глоссарий и сокращения

| Термин | Значение |
|---|---|
| `BFF` | Django BFF layer (`Warehouse_web/apps/bff_api/`) |
| `BFF API` | URL prefix `http://<host>/bff/api/v1/...` |
| `SyncServer` | `SyncServer/app/` (FastAPI) — единственный источник истины |
| `SyncServer API` | URL prefix `http://<host>/api/v1/...` |
| `Angular` | `Warehouse_frontend/src/app/` |
| `client_request_id` | Поле в теле запроса/записи БД, служит для идемпотентности |
| `idempotency_key` | Идентификатор в Angular-черновике, передаётся как `client_request_id` |
| `draft_id` | UUID конкретной формы черновика (живёт в рамках сессии+вкладки) |
| `tab_id` | UUID текущей вкладки (только в памяти) |
| `session_id` | UUID логической сессии (`sessionStorage`) |
| `http_request_id` | UUID конкретного HTTP-запроса (`X-Client-Request-Id`) |
| `server_request_id` | UUID, проставленный сервером (`X-Request-Id` в ответе) |
| `frontend_version` | git SHA из `environment.ts` (или `'dev'` fallback) |
| `outcome_unknown` | Код ошибки, когда клиент не знает, создана ли операция |

---

## 2. Идентификаторы (Identifier Lifecycle)

| Идентификатор | Где создаётся | Где хранится | Когда уничтожается | Кто использует |
|---|---|---|---|---|
| `session_id` | `DiagnosticsSessionService.init()` при bootstrap | `sessionStorage["warehouse.session_id"]` | При закрытии всех вкладок домена (browser-managed) | HTTP-заголовки, диагностика |
| `tab_id` | `DiagnosticsSessionService.init()` при bootstrap | Память (private field сервиса) | При закрытии вкладки / перезагрузке | HTTP-заголовки, диагностика |
| `draft_id` | `OperationCreateModalComponent.ngOnInit` при открытии формы | `localDraft.draftId` в памяти | При переходе в `completed` (успешный submit + refresh) | HTTP-заголовки, DTO логов |
| `idempotency_key` | `OperationCreateModalComponent.ngOnInit` при открытии новой формы | `localDraft.idempotencyKey` в памяти | При `completed` или ручном сбросе (пользователь жмёт «Начать заново») | Поле `client_request_id` в API |
| `http_request_id` | `BffApiService` перед каждым HTTP-запросом | Только в заголовке | После получения ответа/ошибки | HTTP-заголовки, корреляция |
| `server_request_id` | SyncServer / Django | HTTP-заголовок `X-Request-Id` в ответе | После обработки ответа | DiagnosticsSessionService, toast |
| `frontend_version` | Build-time (`environment.ts`) | Константа в `environment.ts` | При следующей сборке | HTTP-заголовки, логи |

### 2.1 Важные правила по идентификаторам

- **`session_id` копируется** при дублировании вкладки (Duplicate tab в Chrome/Firefox). Это **нормально**, потому что `tab_id` в памяти будет отличаться.
- **`tab_id` — ТОЛЬКО в памяти** (private field). НЕ хранится в `sessionStorage`/`localStorage`.
- **`idempotency_key` НЕ МЕНЯЕТСЯ** между повторными `createOperation` для того же черновика. Только ручной сброс (новая форма) генерирует новый.
- **`http_request_id` ВСЕГДА новый** на каждый HTTP-вызов (включая повтор после `outcome_unknown`).
- **`server_request_id` приходит** в HTTP-заголовке `X-Request-Id` ответа. Сохраняется в `DiagnosticsSessionService` для последующего логирования.

### 2.2 Когда очищается `idempotency_key`

```text
Открытие формы → idempotency_key = crypto.randomUUID()
  │
  ├─ submit success → очищается при completed (submit ok + list refresh ok)
  ├─ submit success + list refresh fail → НЕ очищается (warning)
  ├─ submit fail → НЕ очищается (можно повторить с тем же ключом)
  ├─ outcome_unknown → НЕ очищается (используется для resolve)
  └─ user clicks "Начать заново" → idempotency_key = crypto.randomUUID()
```

---

## 3. HTTP-заголовки

### 3.1 Заголовки от Angular к BFF

| Заголовок | Источник | Формат | Обязательный | Сценарий |
|---|---|---|---|---|
| `X-Client-Session-Id` | `DiagnosticsSessionService.sessionId` | UUID v4 | Да | Все мутации (POST/PUT/PATCH/DELETE) |
| `X-Client-Tab-Id` | `DiagnosticsSessionService.tabId` | UUID v4 | Да | Все мутации |
| `X-Client-Request-Id` | `BffApiService.newRequestId()` | UUID v4 | Да | Каждый HTTP-запрос (новый на каждый) |
| `X-Client-Draft-Id` | `localDraft.draftId` | UUID v4 | Только для operations | Только endpoints `/operations*` |
| `X-Frontend-Version` | `environment.frontendVersion` | git SHA или `'dev'` | Да | Все мутации |
| `X-CSRFToken` | Django cookie `csrftoken` | строка | Да (как и сейчас) | Все мутации |
| `X-Warehouse-Client` | константа `3.2-angular` | строка | Да (как и сейчас) | Все мутации |
| `Content-Type` | `application/json` | строка | Да (как и сейчас) | Все мутации с телом |

### 3.2 Заголовки от BFF к SyncServer (forwarded)

| Заголовок | Что делает BFF | Что делает SyncServer |
|---|---|---|
| `X-Client-Session-Id` | forward as-is | логирует, опционально сохраняет в `request_id_meta` |
| `X-Client-Tab-Id` | forward as-is | логирует |
| `X-Client-Request-Id` | forward as-is | логирует, ассоциирует с `X-Request-Id` |
| `X-Client-Draft-Id` | forward as-is (только для operations) | логирует |
| `X-Frontend-Version` | forward as-is | логирует |
| `X-Request-Id` (request) | forward as-is (если есть) или генерирует | переиспользует или генерирует новый |
| `X-Request-Id` (response) | копирует из ответа SyncServer в свой response | генерирует при отсутствии |

### 3.3 Заголовки ответа от BFF/SyncServer клиенту

| Заголовок | Источник | Обязательный | Используется |
|---|---|---|---|
| `X-Request-Id` | SyncServer → BFF → Angular | Да (для мутаций) | Сохраняется в `DiagnosticsSessionService.lastServerRequestId` |
| `X-Client-Request-Id` | (echo от BFF) | Опционально | Отладка |

### 3.4 nginx (если есть в docker-compose)

Заголовки `X-Client-*` **должны** пробрасываться nginx в upstream. В TZ явно отмечено проверить `docker-compose.yml`/`nginx.conf` (см. открытый вопрос OQ-3).

---

## 4. State Machine (фронтенд)

### 4.1 Состояния

| Состояние | Описание | Кнопки | Форма |
|---|---|---|---|
| `editing` | Редактирование черновика | Save, Submit, Cancel | editable |
| `saving` | Идёт сохранение (POST/PATCH черновика) | Нет | disabled |
| `saved` | Черновик сохранён на сервере | Save, Submit, Cancel | editable |
| `save_failed` | Ошибка сохранения | Save, Submit, Cancel | editable |
| `submitting` | Идёт отправка (POST submit) | Нет | disabled |
| `submitted` | Операция проведена (сервер подтвердил) | Close | read-only |
| `submit_failed` | Ошибка отправки | Save, Submit, Cancel | editable |
| `outcome_unknown` | Результат submit неизвестен (timeout/network) | Resolve, Manual retry | disabled |
| `resolving` | Идёт поиск операции по `client_request_id` | Нет | disabled |
| `retry_allowed` | Resolve: операция не найдена, можно повторить | Retry (тот же ключ), Cancel | disabled |
| `refreshing_list` | Идёт обновление списка после submit | Close | read-only |
| `refresh_failed` | Список не обновился (warning) | Close, Retry refresh | read-only |
| `completed` | Всё завершено (submit ok + list refresh ok) | Close | read-only |

### 4.2 Разрешённые переходы

```text
[editing] ──save──▶ [saving] ──ok──▶ [saved] ──save──▶ [saving]
   │                    │                                  │
   │                    └──err──▶ [save_failed] ──save──▶ [saving]
   │                                                       │
   └───────────────────────submit──▶ [submitting] ◀───────┘
                                          │
                       ┌──────────────────┼──────────────────┐
                       │                  │                  │
                  [submitted]      [submit_failed]    [outcome_unknown]
                       │                  │                  │
                       │                  ▼                  │
                       │            [editing]               │
                       │                                     │
                       ▼                                     ▼
                [refreshing_list]                   [resolving]
                       │                                  │
              ┌────────┴────────┐              ┌──────────┴──────────┐
              │                 │              │                     │
        [completed]    [refresh_failed]   [submitted]      [retry_allowed]
                                              ▲                     │
                                              │                     │
                                              └────── retry ────────┘
                                              (с тем же idempotency_key)
```

### 4.3 Запрещённые переходы

| Откуда | Куда | Почему |
|---|---|---|
| `submitted` | `editing` | Нельзя редактировать подтверждённую операцию |
| `outcome_unknown` | `submitting` | Без resolve или явного подтверждения |
| `submitting` | `submitting` | Двойной клик блокируется (guard flag) |
| Любое состояние | новая генерация `idempotency_key` | Только ручной сброс |

### 4.4 Очистка черновика

| Состояние | `idempotency_key` | `draftId` |
|---|---|---|
| `completed` | очищается | очищается |
| `submitted` | сохраняется (для восстановления) | сохраняется |
| `refresh_failed` | сохраняется | сохраняется |
| `submit_failed` | сохраняется (можно повторить) | сохраняется |
| `outcome_unknown` | сохраняется (для resolve) | сохраняется |

---

## 5. DTO и контракты данных

### 5.1 `OperationSubmitResult` (новый, Angular)

Файл: `Warehouse_frontend/src/app/core/models/operations.models.ts`

```typescript
export interface OperationSubmitResult {
  /** UUID созданной/проведённой операции (OperationDto.id) */
  operationId: string;
  /** Отображаемый номер операции (например "ОП-2026-00123") */
  displayNumber: string;
  /** Итоговый статус операции после submit */
  status: OperationStatus;
  /** Был ли выполнен submit (а не только save черновика) */
  submitted: boolean;
  /** server_request_id из X-Request-Id (для саппорта) */
  serverRequestId?: string;
  /** http_request_id, с которым был выполнен submit */
  clientRequestId?: string;
  /** idempotency_key, использованный в submit */
  idempotencyKey?: string;
}
```

### 5.2 `IdempotencyResolution` (новый, Angular)

```typescript
export interface IdempotencyResolution {
  /** Удалось ли найти операцию по ключу */
  found: boolean;
  /** Операция, если найдена (для прямого показа пользователю) */
  operation?: OperationDto;
  /** Способ разрешения: найдена существующая, не найдена, ошибка */
  resolution: 'existing_operation' | 'no_operation_found' | 'resolution_failed';
  /** server_request_id lookup-запроса */
  serverRequestId?: string;
}
```

### 5.3 `OperationDraftVm` (дополнение существующего)

Файл: `Warehouse_frontend/src/app/core/models/operations.models.ts`

Добавить **опциональные** поля:

```typescript
export interface OperationDraftVm {
  // ... существующие поля ...

  /** UUID черновика. Создаётся при открытии формы. */
  draftId?: string;
  /** Идемпотентный ключ для createOperation. НЕ меняется при повторах. */
  idempotencyKey?: string;
}
```

**Поведение при отсутствии** (старые черновики): при загрузке существующего черновика, если поля нет — генерируется новый `idempotencyKey` (обратная совместимость, см. §11).

### 5.4 Существующие типы (не меняются, цитируются для справки)

Подтверждено в `Warehouse_frontend/src/app/core/models/operations.models.ts:1-80`:

```typescript
export type OperationType =
  | 'RECEIVE' | 'EXPENSE' | 'MOVE' | 'WRITE_OFF'
  | 'ISSUE' | 'ISSUE_RETURN' | 'CORRECTION' | 'ADJUSTMENT';

export type OperationStatus = 'draft' | 'submitted' | 'cancelled';

export interface OperationDto {
  id: string;
  number?: string;
  display_number?: string;
  type: OperationType;
  status: OperationStatus;
  version?: number;
  // ... остальные поля
  created_at: string;
  updated_at: string;
  // ...
}
```

### 5.5 SyncServer: `OperationCreate` (без изменений)

Подтверждено в `SyncServer/app/schemas/operation.py:68-86`:

```python
class OperationCreate(BaseModel):
    operation_type: OperationType
    site_id: int
    effective_at: datetime | None = None
    source_site_id: int | None = None
    destination_site_id: int | None = None
    issued_to_user_id: UUID | None = None
    issued_to_name: str | None = None
    issue_object_id: int | None = None
    issue_object_name_snapshot: str | None = None
    lines: list[OperationLineCreate]  # min_length=1
    notes: str | None = None
    client_request_id: str | None = None  # max_length=100
```

---

## 6. API контракты

### 6.1 SyncServer (FastAPI)

#### 6.1.1 Существующее (подтверждено кодом)

```text
POST /api/v1/operations
  Body: OperationCreate (см. §5.5)
  → 201 Created: OperationDto (новая операция)
  → 200 OK: OperationDto (существующая, тот же client_request_id + payload)
  → 409 Conflict: { "detail": { "code": "idempotency_payload_conflict", "message": "..." } }
  → 422 Unprocessable Entity: Pydantic ValidationError
```

**Область идемпотентности** (подтверждено `SyncServer/app/services/operations_service.py:602-620` и `app/repos/operations_repo.py:105-122`):
- `created_by_user_id` + `client_request_id`
- Если найдена существующая и `client_request_hash` совпадает → возврат существующей
- Если найдена и `client_request_hash` отличается → 409 `idempotency_payload_conflict`

#### 6.1.2 Новое: `GET /api/v1/operations?client_request_id={key}`

**Решение Coordinator:** добавить **фильтр** в существующий list endpoint, а НЕ новый path-параметр.

```text
GET /api/v1/operations?client_request_id={key}
  Query params: ... существующие + client_request_id (string, optional, max_length=100)
  → 200 OK: { "items": [OperationDto, ...], "total_count": N }
  → Стандартные ошибки (401/403/500)
```

- Без `client_request_id` — поведение не меняется (back-compat).
- С `client_request_id` — фильтр по `created_by_user_id` (из auth) + `client_request_id`.
- Возвращает массив `items`, не boolean: соответствует существующему формату list endpoint.
- Если ничего не найдено — `items: []`, `total_count: 0`.

### 6.2 Django BFF

#### 6.2.1 Существующее (подтверждено)

```text
POST /bff/api/v1/operations
  Body: { ... }
  Headers: X-CSRFToken, X-Warehouse-Client, ...
  → 200: { "ok": true, "data": OperationDto }
  → 4xx/5xx: { "ok": false, "error": { "code", "message", ... } }
```

**Поведение BFF** (подтверждено `Warehouse_web/apps/operations/views.py:207-217`): BFF **генерирует** `client_request_id` только если есть temporary items И Angular его не прислал. Для каталожных операций BFF **НЕ пробрасывает** `client_request_id` (полагаясь на Angular).

#### 6.2.2 Новое поведение (Agent B)

1. **ВСЕГДА пробрасывать** `client_request_id` от Angular в SyncServer (если есть в payload).
2. **НЕ генерировать** `client_request_id` на стороне BFF вообще (даже для temporary items) — это источник дублей.
3. **Пробрасывать** `X-Client-Session-Id`, `X-Client-Tab-Id`, `X-Client-Request-Id`, `X-Client-Draft-Id`, `X-Frontend-Version` от Angular в SyncServer.
4. **Копировать** `X-Request-Id` из ответа SyncServer в свой response.
5. **Проксировать** `GET /bff/api/v1/operations?client_request_id={key}` → `GET /api/v1/operations?client_request_id={key}`.

#### 6.2.3 Существующее: `GET /bff/api/v1/operations?client_request_id={key}`

```text
GET /bff/api/v1/operations?client_request_id={key}
  → 200: { "ok": true, "data": { "items": [...], "total_count": N } }
  → 4xx/5xx: { "ok": false, "error": {...} }
```

### 6.3 Angular BffApiService (Agent D)

**Расширить** существующий сервис `Warehouse_frontend/src/app/core/api/bff-api.service.ts`:

```typescript
// Новые/изменённые методы:

getMutationHeaders(): HttpHeaders {
  // CSRF + X-Warehouse-Client + X-Client-Session-Id + X-Client-Tab-Id
  // + X-Client-Request-Id (новый на каждый вызов)
  // + X-Frontend-Version
}

// Опционально — X-Client-Draft-Id для operations (через Context API)
setCurrentDraftId(draftId: string | null): void { ... }

// Извлечение X-Request-Id из ответа — внутри postData/patchData:
// response.headers.get('X-Request-Id') → this.diagnosticsSession.lastServerRequestId
```

**НЕ меняется:** сигнатура `postData<T>`, `patchData<T>`, `delete<T>` — изменения только в реализации.

---

## 7. Error Contracts

### 7.1 Формат ошибки BFF (существующий, подтверждено)

```json
{
  "ok": false,
  "error": {
    "code": "operation_outcome_unknown",
    "message": "Сервер не ответил вовремя. Результат операции неизвестен.",
    "fields": null,
    "request_id": "uuid-server",
    "retry_safe": true,
    "current_version": null,
    "status": null
  }
}
```

### 7.2 Стабильные коды ошибок (контракт)

| `code` | HTTP | Источник | Retry safe? | Действие на фронте |
|---|---|---|---|---|
| `idempotency_payload_conflict` | 409 | SyncServer | **No** | `submit_failed`, показать сообщение, **не** повторять с тем же ключом |
| `operation_outcome_unknown` | 0/timeout | BffApiService | **Yes** | `outcome_unknown`, запустить resolve |
| `operation_found` | 200 | BFF (resolve) | n/a | `submitted`, показать найденную операцию |
| `operation_not_found` | 200 | BFF (resolve) | **Yes** | `retry_allowed`, показать кнопку retry |
| `operation_submit_failed` | 4xx/5xx (кроме 401/403/409) | BFF | **No** | `submit_failed`, показать ошибку |
| `operation_list_refresh_failed` | 4xx/5xx (GET /operations) | Angular | **Yes** | `refresh_failed`, warning, операция уже submitted |
| `operation_save_failed` | 4xx/5xx | BFF | **No** | `save_failed`, показать ошибку |
| `operation_version_conflict` | 409 | SyncServer | **No** | `save_failed`, обновить `expected_version` и предложить retry |
| `syncserver_unavailable` | 0 | BffApiService | **No** | `submit_failed`, нет сети |
| `forbidden` | 403 | BffApiService | **No** | `submit_failed`, нет прав |
| `not_found` | 404 | BffApiService | **No** | `submit_failed`, ресурс не найден |
| `unexpected_error` | 500 | BffApiService | **No** | `submit_failed`, неизвестная ошибка |

**Источник кодов:**
- `operation_outcome_unknown`, `syncserver_unavailable`, `forbidden`, `not_found`, `unexpected_error` — уже есть в `bff-api.service.ts:152-178` (подтверждено).
- `idempotency_payload_conflict`, `operation_version_conflict` — есть в SyncServer (`operations_service.py:612-619`).
- `operation_found`, `operation_not_found`, `operation_submit_failed`, `operation_list_refresh_failed`, `operation_save_failed` — **новые**, вводятся этим контрактом (Angular-side classification).

### 7.3 Локализация

UI **НЕ привязывается** к `message` из API. Все тексты — по `code`:

```typescript
const ERROR_MESSAGES: Record<string, string> = {
  operation_outcome_unknown:
    'Результат операции неизвестен. Проверьте список или повторите попытку.',
  idempotency_payload_conflict:
    'Конфликт: этот ключ уже использован с другими данными.',
  operation_submit_failed:
    'Не удалось подтвердить операцию.',
  operation_list_refresh_failed:
    'Операция сохранена, но список не обновился. Обновите страницу.',
  operation_save_failed:
    'Не удалось сохранить черновик.',
  syncserver_unavailable:
    'Сервер недоступен. Проверьте соединение.',
  forbidden: 'Доступ запрещён.',
  not_found: 'Ресурс не найден.',
  unexpected_error: 'Произошла непредвиденная ошибка.',
  operation_version_conflict: 'Операция была изменена в другой вкладке.',
};
```

---

## 8. HTTP Response Matrix

| HTTP код | Ситуация | Код ошибки (если есть) | Состояние | Действие |
|---|---|---|---|---|
| 200 | Существующая операция (idempotent repeat) | — | `submitted`/`saved` | Показать существующую |
| 201 | Новая операция создана | — | `submitted`/`saved` | Показать результат |
| 400 | Некорректный запрос | `operation_submit_failed` | `submit_failed` | Сообщение, редактирование |
| 401 | Не авторизован | (BFF: `forbidden` или `not_found` после редиректа) | `submit_failed` | Редирект на логин |
| 403 | Нет прав | `forbidden` | `submit_failed` | Сообщение |
| 404 | Операция не найдена (при GET по id) | `not_found` | `submit_failed` | Сообщение |
| 404 | Операция не найдена (при resolve) | n/a (200 с `items: []`) | `retry_allowed` | Предложить повтор |
| 409 | Конфликт idempotency | `idempotency_payload_conflict` | `submit_failed` | Сообщение, нельзя повторить с тем же ключом |
| 409 | Конфликт версии | `operation_version_conflict` | `save_failed` | Обновить версию и retry |
| 422 | Ошибка валидации | `operation_submit_failed` + `fields` | `submit_failed` | Показать поля с ошибками |
| 500 | Ошибка сервера | `operation_submit_failed` или `unexpected_error` | `submit_failed` | Сообщение |
| 502/503/504 | Gateway/proxy недоступен | `syncserver_unavailable` | `outcome_unknown` | Запустить resolve |
| Timeout клиента (30 с) | `TimeoutError` от RxJS | `operation_outcome_unknown` | `outcome_unknown` | Запустить resolve |
| Status 0 | Сеть недоступна | `syncserver_unavailable` | `submit_failed` | Сообщение, без повтора |

---

## 9. Примеры запросов/ответов

### 9.1 Создание операции (новый idempotency_key)

```http
POST /bff/api/v1/operations HTTP/1.1
Content-Type: application/json
X-CSRFToken: <csrf>
X-Warehouse-Client: 3.2-angular
X-Client-Session-Id: 5a8b1f3e-...
X-Client-Tab-Id: 7c9d2e4a-...
X-Client-Request-Id: 9e8f7a6b-...
X-Client-Draft-Id: 1d2e3f4a-...
X-Frontend-Version: a1b2c3d4
X-Request-Id: 5a8b1f3e-...

{
  "operation_type": "EXPENSE",
  "site_id": 1,
  "lines": [{"line_number": 1, "item_id": 42, "qty": "5.000"}],
  "client_request_id": "c1d2e3f4-...",
  "notes": null
}
```

```http
HTTP/1.1 201 Created
X-Request-Id: server-uuid-from-sync
Content-Type: application/json

{
  "ok": true,
  "data": {
    "id": "op-uuid-1",
    "display_number": "ОП-2026-00123",
    "type": "EXPENSE",
    "status": "draft",
    "version": 1,
    ...
  }
}
```

### 9.2 Повтор с тем же `client_request_id` и тем же payload (idempotent)

```http
POST /bff/api/v1/operations HTTP/1.1
X-Client-Request-Id: NEW-uuid (новый!)
X-Client-Session-Id: SAME
...
{ ... тот же body с тем же client_request_id ... }
```

```http
HTTP/1.1 200 OK
X-Request-Id: server-uuid-from-sync
{ "ok": true, "data": { "id": "op-uuid-1", "status": "draft", ... } }
```

**Ожидаемо:** `200` (а не `201`), `id` совпадает с первым запросом.

### 9.3 Повтор с тем же `client_request_id` и другим payload → 409

```http
POST /bff/api/v1/operations HTTP/1.1
X-Client-Request-Id: NEW-uuid
...
{ ... тот же client_request_id, но line[0].qty = "10.000" ... }
```

```http
HTTP/1.1 409 Conflict
X-Request-Id: server-uuid-from-sync
{
  "ok": false,
  "error": {
    "code": "idempotency_payload_conflict",
    "message": "Idempotency conflict: client_request_id 'c1d2e3f4-...' was already used with a different payload"
  }
}
```

### 9.4 Поиск операции по `client_request_id` — найдена

```http
GET /bff/api/v1/operations?client_request_id=c1d2e3f4-... HTTP/1.1
X-Client-Request-Id: lookup-uuid
X-Client-Session-Id: 5a8b1f3e-...
X-Client-Tab-Id: 7c9d2e4a-...
X-Frontend-Version: a1b2c3d4
```

```http
HTTP/1.1 200 OK
X-Request-Id: server-uuid-from-sync
{
  "ok": true,
  "data": {
    "items": [{ "id": "op-uuid-1", "status": "draft", "display_number": "ОП-2026-00123", ... }],
    "total_count": 1
  }
}
```

### 9.5 Поиск операции — не найдена

```http
GET /bff/api/v1/operations?client_request_id=unknown-uuid HTTP/1.1
```

```http
HTTP/1.1 200 OK
X-Request-Id: server-uuid-from-sync
{ "ok": true, "data": { "items": [], "total_count": 0 } }
```

**Не 404!** — фронтенд интерпретирует `items.length === 0` как `not_found`.

### 9.6 Timeout клиента (30 с)

```http
POST /bff/api/v1/operations HTTP/1.1
X-Client-Request-Id: timeout-uuid
...
[no response in 30 s → TimeoutError from RxJS]
```

Angular-фронт:
```typescript
// bff-api.service.ts:152-159
return throwError(() => ({
  code: 'operation_outcome_unknown',
  message: 'Сервер не ответил вовремя. Результат операции неизвестен.',
  retry_safe: true,
}));
```

Действие: `outcome_unknown` → resolve (см. §10).

---

## 10. Out-of-band поведение и таймауты

### 10.1 Клиентский таймаут (Angular → BFF)

- **Значение:** `MUTATION_TIMEOUT_MS = 30_000` (уже есть в `bff-api.service.ts`).
- **При срабатывании:** выбрасывается `TimeoutError` → `handleError` маппит в `operation_outcome_unknown` с `retry_safe: true`.
- **Действие:** запустить `resolveByIdempotencyKey(idempotencyKey)`.

### 10.2 Resolve по `idempotency_key`

```typescript
async resolveByIdempotencyKey(key: string): Promise<IdempotencyResolution> {
  try {
    const res = await firstValueFrom(
      this.bff.getData<{ items: OperationDto[]; total_count: number }>(
        `/operations?client_request_id=${encodeURIComponent(key)}`
      )
    );
    if (res?.items && res.items.length > 0) {
      return {
        found: true,
        operation: res.items[0],
        resolution: 'existing_operation',
        serverRequestId: this.diagnosticsSession.lastServerRequestId,
      };
    }
    return { found: false, resolution: 'no_operation_found' };
  } catch (err: any) {
    return { found: false, resolution: 'resolution_failed' };
  }
}
```

### 10.3 Действие по результату resolve

| `resolution` | Новое состояние | Действие |
|---|---|---|
| `existing_operation` | `submitted` | Toast «Операция №{displayNumber} проведена» |
| `no_operation_found` | `retry_allowed` | Кнопка «Повторить с тем же ключом» (НЕ сгенерировать новый) |
| `resolution_failed` | `submit_failed` (или `outcome_unknown`?) | Сообщение «Не удалось проверить результат. Попробуйте позже.» |

**Coordinator решает:** при `resolution_failed` остаёмся в `outcome_unknown` или переходим в `submit_failed`. Решение: **остаёмся в `outcome_unknown`** (можно попробовать resolve ещё раз).

### 10.4 Запрет слепого повтора

После `outcome_unknown`:
- ❌ **Нельзя** автоматически повторять `POST /operations` с НОВЫМ `idempotency_key` — это маскирует проблему.
- ❌ **Нельзя** автоматически повторять `POST /operations` с ТЕМ ЖЕ `idempotency_key` без подтверждения пользователя.
- ✅ Можно: показать кнопку `Retry` (с тем же ключом) или `Resolve` (GET по ключу).
- ✅ Можно: пользователь сам жмёт «Начать заново» → новый `idempotency_key`.

---

## 11. Правила для обратной совместимости

### 11.1 SyncServer

- ✅ Новое поле в `GET /api/v1/operations?client_request_id=X` — опциональный query param. Без него поведение не меняется.
- ✅ POST контракт не меняется (`client_request_id` уже был опциональным).
- ✅ Старый фронт без `X-Client-*` заголовков — продолжает работать (заголовки опциональны на сервере).

### 11.2 BFF

- ⚠️ **Совместимое изменение:** убрать автогенерацию `client_request_id` для temporary items. Старый Angular **не шлёт** `client_request_id` для temporary items, но новый контракт требует, чтобы шёл. **Обратная совместимость:** BFF **оставляет fallback** на автогенерацию для temporary items, **если** Angular не прислал ключ.

Решение Coordinator: **BFF оставляет автогенерацию как fallback** для temporary items только, чтобы не ломать старый Angular. Новый Angular ВСЕГДА шлёт ключ → BFF использует его.

### 11.3 Angular

- ✅ `OperationDraftVm.draftId` и `idempotencyKey` — опциональные поля. Старые черновики (в `sessionStorage`/`localStorage`) загружаются без них; `DiagnosticsSessionService` генерирует новый `idempotencyKey` при первом `createOperation` для таких черновиков.
- ✅ `Environment.frontendVersion` — если файл `environment.ts` не имеет поля, fallback `'dev'`.

---

## 12. Verification checklist для Coordinator

Coordinator считает Contract Package валидным, если выполнены ВСЕ пункты:

- [x] Все DTO задокументированы с именами полей, типами, nullability (§5).
- [x] Все error codes перечислены с HTTP-статусами и retry_safe (§7.2).
- [x] State machine содержит все 13 состояний и 4 запрещённых перехода (§4).
- [x] Заголовки описаны с форматами, источниками, обязательностью (§3).
- [x] Контракты верифицированы grep против существующего кода:
  - [x] `OperationCreate.client_request_id` — `SyncServer/app/schemas/operation.py:86`
  - [x] `create_operation` idempotency check — `operations_service.py:598-620`
  - [x] `get_by_client_request_id` — `operations_repo.py:105-122`
  - [x] `RequestTracingMiddleware` — `Warehouse_web/config/settings/base.py:73`
  - [x] `X-Request-Id` forward — `apps/sync_client/client.py:85`
  - [x] `bff-api.service.ts` headers — `bff-api.service.ts:117-131`
  - [x] `OperationDraftVm` БЕЗ `idempotencyKey`/`draftId` — `operations.models.ts` (grep пусто)
  - [x] `diagnostics-session.service.ts` НЕ существует — `ls` подтверждает
  - [x] BFF `client_request_id` generation — `apps/operations/views.py:207-217`
- [x] Все 6 примеров запрос/ответ задокументированы (§9).
- [x] Out-of-band поведение (resolve, retry) описано (§10).
- [x] Backward compatibility правила определены (§11).
- [x] Открытые вопросы для Agent A/B выделены явно (см. §13).

---

## 13. Открытые вопросы (для Agent A/B при реализации)

### OQ-1: `UNIQUE` constraint на `client_request_id` в БД?

**Контекст:** SyncServer сейчас ищет по `created_by_user_id + client_request_id`, но UNIQUE constraint не заявлен. При гонке двух POST с одним ключом может возникнуть две записи.

**Дефолт Coordinator:** НЕ добавлять constraint в этом этапе (миграция, риск для прода). Достаточно приложения-уровневой проверки `get_by_client_request_id` + явной транзакции.

**Решение принимает Agent A** на основе реальной миграции и рисков для текущей БД.

### OQ-2: Формат endpoint поиска

**Coordinator решил:** `GET /api/v1/operations?client_request_id={key}` (фильтр в существующем endpoint). Альтернатива `GET /api/v1/operations/by-client-request/{key}` **отклонена** — больше кода, меньше единообразия.

### OQ-3: nginx проброс `X-Client-*`

**Coordinator решает:** `docker-compose.yml` нужно проверить на предмет `proxy_pass_request_headers` или аналогичной настройки. Agent B должен проверить при реализации, добавить в `nginx.conf` (если присутствует) `proxy_pass_request_headers on;` или явно перечислить `X-Client-Session-Id`, `X-Client-Tab-Id`, `X-Client-Request-Id`, `X-Client-Draft-Id`, `X-Frontend-Version`.

### OQ-4: `RequestTracingMiddleware` возврат `X-Request-Id` клиенту

**Подтверждено:** `Warehouse_web/apps/common/middleware.py:71` ставит `response["X-Request-Id"] = request_id`. Существующий код. Agent B должен только проксировать в BFF response.

### OQ-5: Старые черновики без `idempotencyKey`

**Coordinator решил:** при открытии старого черновика `DiagnosticsSessionService` генерирует новый `idempotencyKey` (если `localDraft.idempotencyKey` отсутствует). Это безопасная обратная совместимость.

---

## 14. Финальный список файлов-зон изменений (для Agent A–D)

| Файл | Agent | Описание |
|---|---|---|
| `SyncServer/app/api/routes_operations.py` | A | Добавить фильтр `client_request_id` в list endpoint |
| `SyncServer/app/services/operations_service.py` | A | (опционально) Вынести `_compute_client_request_hash` для тестов |
| `SyncServer/app/repos/operations_repo.py` | A | (опционально) Добавить `list_by_client_request_id` |
| `SyncServer/tests/test_operations_idempotency.py` | A (NEW) | 6+ тестов (см. §14.1 ТЗ) |
| `Warehouse_web/apps/operations/views.py` | B | Убрать/ослабить автогенерацию `client_request_id` для temporary (оставить fallback) |
| `Warehouse_web/apps/bff_api/operations_views.py` | B | Проброс X-Client-*; копирование X-Request-Id в response |
| `Warehouse_web/apps/sync_client/client.py` | B | (опционально) Проверить пробрасывание кастомных заголовков |
| `Warehouse_web/apps/operations/tests.py` | B | 4+ теста (см. §14.1 ТЗ) |
| `Warehouse_web/apps/bff_api/tests.py` | B | 4+ теста (см. §14.1 ТЗ) |
| `Warehouse_frontend/src/app/core/services/diagnostics-session.service.ts` | D (NEW) | SessionService с session_id, tab_id, http_request_id, draft_id, idempotency_key |
| `Warehouse_frontend/src/app/core/api/bff-api.service.ts` | D | Расширить `getMutationHeaders()`, извлекать `X-Request-Id` |
| `Warehouse_frontend/src/app/core/models/operations.models.ts` | D (первый), C (второй) | Добавить `draftId`, `idempotencyKey`; потом `OperationSubmitResult` |
| `Warehouse_frontend/src/app/features/operations/components/operation-create-modal/operation-create-modal.component.ts` | D (первый), C (второй) | Инициализация `draftId`, `idempotencyKey`; потом UX/кнопки |
| `Warehouse_frontend/src/app/core/services/operations.service.ts` | D (первый), C (второй) | Использовать `idempotencyKey` вместо `_newClientRequestId`; потом `submitWithResult` |
| `Warehouse_frontend/src/app/core/services/diagnostics-session.service.spec.ts` | D (NEW) | 5+ тестов session service |
| `Warehouse_frontend/src/environments/environment.ts` | D | Добавить `frontendVersion` |
| `Warehouse_frontend/src/app/app.config.ts` | D | Зарегистрировать `DiagnosticsSessionService` |
| `Warehouse_frontend/src/app/features/operations/pages/operations-page/operations-page.component.ts` | C | `onDraftSubmit`, `onConfirmSubmit` фиксы |
| `Warehouse_frontend/src/app/core/services/operations.service.spec.ts` | C, D | 6+ тестов для submitWithResult, idempotency |
| `Warehouse_frontend/e2e/operation-reliability.spec.ts` | E (NEW) | 9 сценариев E2E |
| `Warehouse_frontend/e2e/helpers/network-faults.ts` | E (NEW) | Хелперы для Playwright route.abort() |

---

**Конец контракта.** Никакой production-код не пишется в рамках WP-0. Реализация начинается в WP-1 (Agent A), WP-2 (Agent B), WP-4 (Agent D) — параллельно после заморозки.
