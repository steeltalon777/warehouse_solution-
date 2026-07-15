# TZ: Надёжность складской операции — Этапы 0–2 (SWARM)

**Дата:** 2026-07-15  
**Источник:** замороженное ревью `docs/ARCHITECTURE_REVIEW_ANGULAR_UI_DIAGNOSTICS.md`  
**Статус:** ТЗ — без реализации  
**Режим:** SWARM (6 агентов + Coordinator)

---

## Содержание

- [1. Executive Summary](#1-executive-summary)
- [2. Scope / Out of Scope](#2-scope--out-of-scope)
- [3. Подтверждённая текущая архитектура](#3-подтверждённая-текущая-архитектура)
- [4. Target Architecture](#4-target-architecture)
- [5. Contract Package (заморозка до старта)](#5-contract-package-заморозка-до-старта)
- [6. State Machine](#6-state-machine)
- [7. API Contracts](#7-api-contracts)
- [8. Error Contracts](#8-error-contracts)
- [9. Identifier Lifecycle](#9-identifier-lifecycle)
- [10. SWARM Topology](#10-swarm-topology)
- [11. Dependency Graph](#11-dependency-graph)
- [12. Work Packages](#12-work-packages)
- [13. File Ownership Matrix](#13-file-ownership-matrix)
- [14. Test Strategy](#14-test-strategy)
- [15. Deployment and Rollback](#15-deployment-and-rollback)
- [16. Risks and Open Questions](#16-risks-and-open-questions)
- [17. Acceptance Criteria](#17-acceptance-criteria)
- [18. Definition of Done](#18-definition-of-done)
- [19. Рекомендуемый порядок запуска агентов](#19-рекомендуемый-порядок-запуска-агентов)
- [20. Промпты для SWARM-агентов](#20-промпты-для-swarm-агентов)

---

## 1. Executive Summary

### Проблема

Кладовщик сообщает: «операция пропала», «ничего не забилось», «нажал подтвердить — результата нет», «попробовал ещё раз — получил дубль».

Архитектурное ревью подтвердило три реальных дефекта:

1. **Нет подтверждения с `operation_id`** — после submit пользователь не знает, создана ли операция, пока не обновится список.
2. **Нет идемпотентности** — каждый вызов `createOperation` генерирует новый `client_request_id`, повтор после таймаута создаёт дубликат.
3. **Нет сквозных идентификаторов** — невозможно связать действие в Angular с запросом в SyncServer.

### Решение (Этапы 0–2)

| Этап | Что делаем | Результат |
|------|-----------|-----------|
| **0** | Контракт результата | Пользователь видит `operation_id` после submit, ошибка списка ≠ ошибка submit |
| **1** | Идемпотентность + outcome_unknown | Повтор не создаёт дубль, после таймаута можно найти результат |
| **2** | Correlation identifiers | Сквозная трассировка от Angular до SyncServer |

### Ключевое архитектурное решение

**НЕ ждать `loadList()` для признания submit успешным.** Сервер дал `operation_id` — показываем успех. Список обновляется отдельно.

### Режим выполнения

**SWARM:** 6 агентов работают параллельно после заморозки контрактов. Никаких конфликтов по файлам.

---

## 2. Scope / Out of Scope

### In Scope

| Этап | Что входит |
|------|-----------|
| 0 | Исправление `onDraftSubmit`, `onConfirmSubmit`, разделение submit-result и list-refresh, показ `operation_id`, блокировка повторов |
| 1 | `idempotency_key` в черновике, неизменность при повторах, поиск по ключу после `outcome_unknown`, запрет слепого повтора |
| 2 | `session_id`, `tab_id`, `draft_id`, `idempotency_key`, `http_request_id`, `server_request_id`, `frontend_version`, заголовки, сквозная передача через BFF → nginx → SyncServer |

### Out of Scope (явно исключено)

- UI-диагностика (события, batch-отправка, diagnostics endpoint) — **Этап 3, не сейчас**
- Автосохранение черновика, CanDeactivate, beforeunload — **Этап 4, не сейчас**
- Session Replay — **Этап 5+, не сейчас**
- Redis, Celery, Kafka, отдельные workers
- Feature flags (оцениваются, но не обязательны)
- Фантомные ТМЦ (zombie items) — **отдельное ТЗ**
- Изменение SyncServer business logic (кроме контракта idempotency)
- Полноценный audit logging на фронтенде

---

## 3. Подтверждённая текущая архитектура

### 3.1 Angular Frontend

| Файл | Роль | Ключевые методы |
|------|------|----------------|
| `Warehouse_frontend/src/app/core/services/operations.service.ts` | Сервис операций | `createOperation()`, `submitOperation()`, `buildPayload()`, `_newClientRequestId()` |
| `Warehouse_frontend/src/app/core/services/operations.service.ts:133-139` | Генерация ключа | `crypto.randomUUID()` — **новый при каждом вызове** |
| `Warehouse_frontend/src/app/core/services/operations.service.ts:814` | `buildPayload` | `payload['client_request_id'] = this._newClientRequestId()` для `isCreate: true` |
| `Warehouse_frontend/src/app/core/api/bff-api.service.ts` | BFF HTTP клиент | `postData()`, `post()`, `handleError()`, `MUTATION_TIMEOUT_MS=30_000` |
| `Warehouse_frontend/src/app/core/api/bff-api.service.ts:127-131` | Заголовки | `getMutationHeaders()` → `X-CSRFToken`, `X-Warehouse-Client: 3.2-angular` |
| `Warehouse_frontend/src/app/features/operations/pages/operations-page/operations-page.component.ts:696-714` | `onDraftSubmit` | create/update → submit → **безусловно закрывает модал** (стр. 703-704) |
| `Warehouse_frontend/src/app/features/operations/pages/operations-page/operations-page.component.ts:823-841` | `onConfirmSubmit` | **закрывает confirm до проверки** (стр. 829) |
| `Warehouse_frontend/src/app/features/operations/components/operation-create-modal/operation-create-modal.component.ts` | Модал | `onSubmit()`, `onSave()`, `localDraft` signal |
| `Warehouse_frontend/src/app/core/models/operations.models.ts` | Модели | `OperationDraftVm`, `OperationDto` — **нет поля `idempotencyKey`** |
| `Warehouse_frontend/src/app/core/logging/http-error.interceptor.ts` | HTTP interceptor | Только `console.error`, не извлекает request_id |
| `Warehouse_frontend/src/app/core/logging/global-error-handler.ts` | ErrorHandler | `console.error` + re-throw |
| `Warehouse_frontend/src/app/app.config.ts` | Конфиг | `provideHttpClient(withXsrfConfiguration(...), withInterceptors([httpErrorInterceptor]))` |

**Факт:** Angular 21.2.0, standalone, signals. Zone.js. ChangeDetectionStrategy.Default.

### 3.2 Django BFF (Warehouse_web)

| Файл | Роль | Ключевые методы |
|------|------|----------------|
| `Warehouse_web/apps/operations/views.py:207-217` | Создание операции | `client_request_id` генерируется **только для temporary items** |
| `Warehouse_web/apps/bff_api/operations_views.py` | BFF операции | Проксирование в SyncServer |
| `Warehouse_web/apps/sync_client/transport.py` | Транспорт | `httpx.Client`, `RequestTracingMiddleware` пробрасывает `X-Request-Id` |

**Факт:** Django BFF **не генерирует** `client_request_id` для операций без временных ТМЦ. Angular всегда посылает его в теле, но BFF не всегда пробрасывает.

### 3.3 SyncServer

| Файл | Роль | Ключевые методы |
|------|------|----------------|
| `SyncServer/app/services/operations_service.py:588-669` | `create_operation` | Идемпотентность: `get_by_client_request_id` → тот же hash → возврат существующей; другой hash → 409 |
| `SyncServer/app/services/operations_service.py:494-530` | `_compute_client_request_hash` | SHA-256 нормализованного payload |
| `SyncServer/app/repos/operations_repo.py:105-109` | `get_by_client_request_id` | Поиск по `created_by_user_id` + `client_request_id` |
| `SyncServer/app/schemas/operation.py:68` | `OperationCreate` | Поле `client_request_id: Optional[str]` |

**Факт:** SyncServer **уже поддерживает** идемпотентность:
- Тот же `client_request_id` + тот же payload → 200, возвращает существующую операцию
- Тот же `client_request_id` + другой payload → 409 `idempotency_payload_conflict`
- Область: `created_by_user_id` + `client_request_id`
- Нет эндпоинта поиска операции по `client_request_id` через GET

### 3.4 Поток создания (текущий, проблемный)

```text
Angular: createOperation(draft)
  → buildPayload → _newClientRequestId()          ← НОВЫЙ ключ каждый раз!
  → POST /bff/api/v1/operations {client_request_id}
  → Django BFF → SyncServer POST /api/v1/operations
  → SyncServer: get_by_client_request_id → создаёт операцию
  → ответ: {id: "uuid"}

Angular: submitOperation(id)
  → POST /bff/api/v1/operations/{id}/submit
  → ответ: успех

Angular: onDraftSubmit()
  → showCreateModal.set(false)                     ← ЗАКРЫТ ДО loadList!
  → editingDraft.set(null)                         ← ЧЕРНОВИК ПОТЕРЯН
  → void loadList()                                ← БЕЗ AWAIT
```

### 3.5 Что уже есть на сервере

SyncServer уже делает:
- ✅ Принимает `client_request_id`
- ✅ Хранит `client_request_hash`
- ✅ Возвращает существующую операцию при повторе с тем же ключом и payload
- ✅ Возвращает 409 при конфликте payload

**Нет:**
- ❌ GET-эндпоинта для поиска операции по `client_request_id`
- ❌ Angular не сохраняет ключ между вызовами
- ❌ BFF не пробрасывает ключ для нетemporary операций

---

## 4. Target Architecture

### 4.1 Целевой поток

```text
Пользователь открывает форму
→ draft_id = crypto.randomUUID()
→ idempotency_key = crypto.randomUUID()    ← ОДИН раз

Пользователь нажимает «Сохранить» или «Подтвердить»
→ http_request_id = crypto.randomUUID()    ← НОВЫЙ на каждый HTTP
→ POST /operations {client_request_id: idempotency_key, ...}
→ Заголовки: X-Client-Request-Id, X-Client-Session-Id, X-Client-Tab-Id, X-Client-Draft-Id

Сервер отвечает:
→ 201/200 {id: "op-uuid", ...}
→ Заголовок: X-Request-Id

Angular получает ответ:
→ Показывает «Операция №... проведена»
→ Закрывает / read-only форму
→ Обновляет список (отдельно)
→ Ошибка списка → warning, не ошибка submit

Таймаут / outcome_unknown:
→ GET /operations?client_request_id={idempotency_key}
→ Если найдена → показать результат
→ Если не найдена → повторить POST с ТЕМ ЖЕ idempotency_key
→ Запретить слепой повтор
```

### 4.2 Разделение результата и обновления списка

```text
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Submit     │────▶│  Результат   │────▶│  Обновление │
│  Operation  │     │  (operation  │     │  списка     │
│             │     │   _id, toast)│     │  (отдельно) │
└─────────────┘     └──────────────┘     └─────────────┘
                           │                      │
                           │ ошибка?               │ ошибка?
                           ▼                      ▼
                    «Операция               «Операция №...
                     НЕ создана»             создана, но
                                             список не
                                             обновился»
```

### 4.3 Идентификаторы

```text
session_id       — sessionStorage, логическая сессия приложения
tab_id           — память, уникален для вкладки
draft_id         — создаётся при открытии формы
idempotency_key  — один на черновик, = client_request_id в API
http_request_id  — новый на каждый HTTP-запрос (X-Client-Request-Id)
server_request_id — из X-Request-Id ответа сервера
frontend_version — git SHA из environment.ts
```

---

## 5. Contract Package (заморозка до старта)

**Должен быть создан Coordinator-ом до начала любой реализации.**

### 5.1 DTO результата операции

```typescript
// operations.models.ts — добавить
export interface OperationSubmitResult {
  operationId: string;
  displayNumber: string;      // отображаемый номер операции
  status: OperationStatus;    // итоговый статус
  submitted: boolean;         // был ли submit (а не только save)
}
```

### 5.2 DTO для outcome resolution

```typescript
export interface IdempotencyResolution {
  found: boolean;
  operation?: OperationDto;
  resolution: 'existing_operation' | 'no_operation_found' | 'resolution_failed';
}
```

### 5.3 Endpoint для поиска по idempotency key

```text
GET /bff/api/v1/operations/by-client-request/{client_request_id}

Response 200:
{
  "found": true,
  "operation": { ... OperationDto ... }
}

Response 200:
{
  "found": false,
  "operation": null
}
```

Либо:

```text
GET /bff/api/v1/operations?client_request_id={key}

Возвращает стандартный список с фильтром по client_request_id.
```

**Решение принимает Coordinator на основе возможностей SyncServer API.**

### 5.4 Заголовки

| Заголовок | Источник | Формат | Обязательный |
|-----------|----------|--------|--------------|
| `X-Client-Session-Id` | Angular | UUID | Да |
| `X-Client-Tab-Id` | Angular | UUID | Да |
| `X-Client-Request-Id` | Angular (на каждый HTTP) | UUID | Да |
| `X-Client-Draft-Id` | Angular | UUID | Только для operations |
| `X-Frontend-Version` | Angular | git SHA | Да |
| `X-Request-Id` | SyncServer/Django | UUID | Да (ответ) |
| `X-Warehouse-Client` | Angular | `3.2-angular` | Уже есть |

### 5.5 State Machine Diagram (текстовый)

```text
[editing] ──save──▶ [saving] ──success──▶ [saved]
  │                    │                     │
  │                    └──error──▶ [save_failed] → [editing]
  │
  └──submit──▶ [submitting] ──success──▶ [submitted]
                   │                          │
                   ├──timeout──▶ [outcome_unknown]
                   │                │
                   │                ├──resolve──▶ [resolving]
                   │                │                │
                   │                │      ┌─found──▶ [submitted]
                   │                │      └─not_found──▶ [retry_allowed]
                   │                │
                   │                └──retry──▶ [submitting] (тот же idempotency_key)
                   │
                   └──error──▶ [submit_failed] → [editing]

[submitted] ──refresh_list──▶ [refreshing_list]
                   │
                   ├──success──▶ [completed]
                   └──error──▶ [refresh_failed] (warning, operation всё ещё submitted)
```

### 5.6 Матрица HTTP-ответов

| Код | Ситуация | Состояние | Действие |
|-----|----------|-----------|----------|
| 200 | Существующая операция (idempotent repeat) | `submitted` / `saved` | Показать существующую |
| 201 | Новая операция создана | `submitted` / `saved` | Показать результат |
| 400 | Некорректный запрос | `submit_failed` | Сообщение, редактирование |
| 401 | Не авторизован | `submit_failed` | Редирект на логин |
| 403 | Нет прав | `submit_failed` | Сообщение |
| 404 | Не найден (при поиске по ключу) | `retry_allowed` | Предложить повтор |
| 409 | Конфликт idempotency (разный payload) | `submit_failed` | Сообщение, нельзя повторить с тем же ключом |
| 422 | Ошибка валидации | `submit_failed` | Показать поля с ошибками |
| 500 | Ошибка сервера | `submit_failed` | Сообщение |
| 502/503/504 | Gateway/proxy недоступен | `outcome_unknown` | Запустить разрешение |
| Timeout | Таймаут клиента (30 с) | `outcome_unknown` | Запустить разрешение |
| Status 0 | Сеть недоступна | `submit_failed` | Сообщение, без повтора |

### 5.7 Error Codes

```typescript
export const OPERATION_ERROR_CODES = {
  IDEMPOTENCY_KEY_REUSED_DIFFERENT_PAYLOAD: 'idempotency_payload_conflict',
  OPERATION_OUTCOME_UNKNOWN: 'operation_outcome_unknown',
  OPERATION_FOUND_BY_IDEMPOTENCY_KEY: 'operation_found',
  OPERATION_NOT_FOUND_BY_IDEMPOTENCY_KEY: 'operation_not_found',
  OPERATION_SUBMIT_FAILED: 'operation_submit_failed',
  OPERATION_LIST_REFRESH_FAILED: 'operation_list_refresh_failed',
  OPERATION_SAVE_FAILED: 'operation_save_failed',
} as const;
```

---

## 6. State Machine

### 6.1 Состояния

| Состояние | Описание | Кнопки активны | Форма |
|-----------|----------|---------------|-------|
| `editing` | Редактирование черновика | Save, Submit, Cancel | editable |
| `saving` | Идёт сохранение | Нет | disabled |
| `saved` | Черновик сохранён | Save, Submit, Cancel | editable |
| `save_failed` | Ошибка сохранения | Save, Submit, Cancel | editable |
| `submitting` | Идёт отправка | Нет | disabled |
| `submitted` | Операция проведена | Close | read-only |
| `submit_failed` | Ошибка отправки | Save, Submit, Cancel | editable |
| `outcome_unknown` | Результат неизвестен | Resolve, Manual retry | disabled |
| `resolving` | Поиск результата | Нет | disabled |
| `retry_allowed` | Можно повторить | Retry (с тем же ключом), Cancel | disabled |
| `refreshing_list` | Обновление списка | Close | read-only |
| `refresh_failed` | Список не обновился | Close, Retry refresh | read-only |
| `completed` | Всё завершено | Close | read-only |

### 6.2 Запрещённые переходы

- `submitted` → `editing` (нельзя редактировать подтверждённую)
- `outcome_unknown` → `submitting` без resolve или явного подтверждения пользователя
- `submitting` → `submitting` (двойной клик)
- Любое состояние → создание нового `idempotency_key`

### 6.3 Когда очищается черновик

- Только при переходе в `completed` (успешный submit + успешный list refresh)
- При переходе в `submitted` черновик сохраняется для возможности восстановления
- При `refresh_failed` черновик НЕ очищается

---

## 7. API Contracts

### 7.1 SyncServer (существующее + необходимое)

#### Существующее (подтверждено кодом)

```text
POST /api/v1/operations
  body: { ..., client_request_id?: string }
  → 201: { id: "uuid", ... }  (новая операция)
  → 200: { id: "uuid", ... }  (существующая, тот же client_request_id + payload)
  → 409: { detail: { code: "idempotency_payload_conflict", message: "..." } }
```

Область идемпотентности: `created_by_user_id` + `client_request_id`.

#### Необходимое (Agent A)

```text
GET /api/v1/operations?client_request_id={key}
  → 200: { items: [...], total_count: N }
  Фильтр по client_request_id. Без клиентского request_id — возвращает
  все операции (существующее поведение).

GET /api/v1/operations/{id}
  → 200: { id, status, ... }
  Уже существует, используется для проверки статуса после разрешения outcome.
```

### 7.2 Django BFF (необходимое, Agent B)

```text
POST /bff/api/v1/operations
  body: { ..., client_request_id: string }
  Заголовки: X-Client-Request-Id, X-Client-Session-Id, X-Client-Tab-Id,
             X-Client-Draft-Id, X-Frontend-Version
  → Проксирует в SyncServer, добавляет X-Request-Id из ответа
  → Возвращает: { ok: true, data: { ...OperationDto, client_request_id } }

GET /bff/api/v1/operations?client_request_id={key}
  → Проксирует фильтр в SyncServer
  → Возвращает: { items: [...], total_count: N }

Все ответы BFF должны включать X-Request-Id в заголовках.
```

### 7.3 Angular BffApiService (необходимое, Agent C/D)

```typescript
// Добавить методы:
getOperationByClientRequestId(key: string): Observable<OperationDto | null>
// Вызывает GET /bff/api/v1/operations?client_request_id={key}

// Модифицировать существующие:
postData<T>(path, body): Observable<T>
// Добавить заголовки X-Client-Request-Id, X-Client-Session-Id,
// X-Client-Tab-Id, X-Client-Draft-Id (опционально), X-Frontend-Version

// Извлечение X-Request-Id из ответа:
// В HttpResponseheaders — сохранять в DiagnosticsSessionService
```

---

## 8. Error Contracts

### 8.1 Структура ошибки BFF

```json
{
  "ok": false,
  "error": {
    "code": "operation_outcome_unknown",
    "message": "Сервер не ответил вовремя. Результат операции неизвестен.",
    "fields": null,
    "request_id": "uuid-server",
    "retry_safe": true
  }
}
```

### 8.2 Коды ошибок (стабильные)

| Код | HTTP | Источник | Действие |
|-----|------|----------|----------|
| `idempotency_payload_conflict` | 409 | SyncServer | Не повторять с тем же ключом |
| `operation_outcome_unknown` | 0/timeout | BffApiService | Запустить resolve |
| `operation_found` | 200 | BFF (resolve) | Показать существующую |
| `operation_not_found` | 200 | BFF (resolve) | Предложить повтор |
| `operation_submit_failed` | 4xx/5xx | BFF | Показать ошибку |
| `operation_list_refresh_failed` | * | Angular | Warning, не ошибка submit |
| `operation_save_failed` | 4xx/5xx | BFF | Показать ошибку |
| `syncserver_unavailable` | 0 | BffApiService | Нет сети |
| `forbidden` | 403 | BffApiService | Нет прав |
| `unexpected_error` | 500 | BffApiService | Неизвестная ошибка |

### 8.3 Локализация

UI **не привязывается** к тексту сообщения из API. Все сообщения — по `code`:

```typescript
const ERROR_MESSAGES: Record<string, string> = {
  operation_outcome_unknown: 'Результат операции неизвестен. Проверьте список или повторите попытку.',
  idempotency_payload_conflict: 'Конфликт: этот ключ уже использован с другими данными.',
  operation_submit_failed: 'Не удалось подтвердить операцию.',
  operation_list_refresh_failed: 'Операция сохранена, но список не обновился. Обновите страницу.',
  // ...
};
```

---

## 9. Identifier Lifecycle

### 9.1 Создание и хранение

| Идентификатор | Создаётся | Где хранится | Когда уничтожается |
|---------------|-----------|-------------|-------------------|
| `session_id` | `DiagnosticsSessionService.init()` при bootstrap | `sessionStorage` | При закрытии всех вкладок домена (brauser-managed) |
| `tab_id` | `DiagnosticsSessionService.init()` при bootstrap | Память (private field) | При закрытии вкладки |
| `draft_id` | `OperationCreateModalComponent` при `ngOnInit` / открытии | `localDraft.draftId` | При `completed` |
| `idempotency_key` | `OperationCreateModalComponent` при открытии новой формы | `localDraft.idempotencyKey` | При `completed` или ручном сбросе |
| `http_request_id` | `BffApiService` перед каждым HTTP-запросом | Заголовок `X-Client-Request-Id` | После получения ответа |
| `server_request_id` | SyncServer/Django | Заголовок `X-Request-Id` в ответе | После обработки |
| `frontend_version` | Сборка (`environment.ts`) | Константа | До следующей сборки |

### 9.2 `session_id` vs `tab_id`

Важное различие: `sessionStorage` **копируется** браузером при дублировании вкладки (Duplicate tab). Поэтому `session_id`, хранимый в `sessionStorage`, будет одинаковым для исходной и продублированной вкладки.

`tab_id` должен храниться **только в памяти** (private field сервиса) и генерироваться при каждом `bootstrapApplication`. Это гарантирует уникальность даже при дублировании вкладки.

### 9.3 Переиспользование idempotency_key

```text
Создание черновика:
  draft.idempotencyKey = crypto.randomUUID()  ← ОДИН раз

Вызов createOperation (первый):
  payload.client_request_id = draft.idempotencyKey
  http_request_id = crypto.randomUUID()

Вызов createOperation (повтор после timeout):
  payload.client_request_id = draft.idempotencyKey  ← ТОТ ЖЕ
  http_request_id = crypto.randomUUID()             ← НОВЫЙ

Ручной сброс:
  Пользователь явно жмёт «Начать заново»
  → draft.idempotencyKey = crypto.randomUUID()
```

---

## 10. SWARM Topology

```text
┌─────────────────────────────────────────────────────────────┐
│                  SWARM Coordinator / Architect              │
│  Фиксация контрактов, граф зависимостей, приёмка WP        │
└─────────────────────────────────────────────────────────────┘
        │                │                │                │
        ▼                ▼                ▼                ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│   Agent A    │ │   Agent B    │ │   Agent C    │ │   Agent D    │
│  SyncServer  │ │  Django BFF  │ │ Angular UX   │ │ Angular IDs  │
│ Idempotency  │ │  Contracts   │ │   Result     │ │ Correlation  │
└──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘
        │                │                │                │
        └────────────────┼────────────────┼────────────────┘
                         │                │
                         ▼                ▼
                  ┌──────────────────────────────┐
                  │     Integration Agent        │
                  │  Слияние, сквозные тесты     │
                  └──────────────────────────────┘
                         │
                         ▼
                  ┌──────────────────────────────┐
                  │       Agent E: QA            │
                  │  E2E, adversarial testing    │
                  └──────────────────────────────┘
```

### Роли

| Роль | Кто | Ответственность |
|------|-----|----------------|
| Coordinator | 1 агент | Контракты, граф, приёмка, решение конфликтов |
| Agent A | 1 агент | SyncServer: idempotency, поиск по ключу, тесты |
| Agent B | 1 агент | Django BFF: прокси, заголовки, DTO |
| Agent C | 1 агент | Angular: result contract, state machine, UX |
| Agent D | 1 агент | Angular: identifiers, correlation headers, session service |
| Integration | 1 агент | Слияние WP, сквозная сборка, миграции |
| Agent E | 1 агент | E2E, network fault injection, adversarial |

---

## 11. Dependency Graph

```text
                    Contract Freeze (Coordinator)
                              │
            ┌─────────────────┼─────────────────┐
            │                 │                 │
            ▼                 ▼                 ▼
     ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
     │   Agent A   │  │   Agent B   │  │   Agent D   │
     │ SyncServer  │  │  BFF        │  │ Angular IDs │
     │ idempotency │  │ contracts   │  │ correlation │
     └─────────────┘  └─────────────┘  └─────────────┘
            │                 │                 │
            │    ┌────────────┘                 │
            │    │                              │
            ▼    ▼                              │
     ┌─────────────┐                            │
     │   Agent C   │ ◄──────────────────────────┘
     │ Angular UX  │  (ждёт Agent D для
     │   Result    │   DiagnosticsSessionService)
     └─────────────┘
            │
            │ (Agent C зависит от Agent D только
            │  для сервиса идентификаторов, но может
            │  начать с мока)
            │
            ▼
     ┌─────────────────┐
     │ Integration Agent│
     └─────────────────┘
            │
            ▼
     ┌─────────────┐
     │   Agent E   │
     │  E2E / QA   │
     └─────────────┘
```

**Критические зависимости:**

- Agent C **зависит** от Agent D для `DiagnosticsSessionService` (получение `draft_id`, `tab_id`)
- Agent C **может начать** с заглушкой `draft_id = 'mock'`, пока Agent D не готов
- Agent C и Agent D **не конфликтуют по файлам** (разные методы в `operations.service.ts`)
- Agent A и Agent B **независимы** друг от друга
- Все агенты зависят от **Contract Freeze**

---

## 12. Work Packages

### WP-0: Contract Freeze (Coordinator)

```text
ID:            WP-0
Название:      Contract Freeze
Исполнитель:   Coordinator
Репозиторий:   docs/ (только)
Цель:          Заморозить контракты до начала реализации
Зависимости:   Architecture Review (заморожен)
Запрещённые:   Любой production-код
Результат:     Файл docs/contracts/OPERATION_RELIABILITY_CONTRACTS.md
               со всеми DTO, error codes, заголовками, state machine,
               матрицей HTTP-ответов
Definition of Done:
  - Все DTO задокументированы с именами полей и типами
  - Все error codes перечислены с HTTP-статусами
  - State machine содержит все состояния и переходы
  - Заголовки описаны с форматами и источниками
  - Контракты согласованы с существующим кодом (подтверждены grep)
```

### WP-1: SyncServer Idempotency Hardening (Agent A)

```text
ID:            WP-1
Название:      SyncServer Operation Idempotency & Lookup
Исполнитель:   Agent A
Репозиторий:   SyncServer/
Цель:          Добавить GET-эндпоинт поиска по client_request_id,
               проверить транзакционность и уникальность
Зависимости:   WP-0 (контракты)
Входные:       Contract Package §5.3, §7.1
Выходные:      Новый/модифицированный endpoint + тесты
Файлы (+):     SyncServer/app/api/routes_operations.py
               SyncServer/app/services/operations_service.py
               SyncServer/app/repos/operations_repo.py
               SyncServer/app/schemas/operation.py
               SyncServer/tests/test_operations_idempotency.py (новый)
Файлы (-):     Никакие файлы за пределами SyncServer/
Изменения API:
  GET /api/v1/operations?client_request_id={key}
  → 200: { items: [OperationDto], total_count: N }
Изменения БД:  Нет (поле client_request_id уже существует)
Миграции:      Нет
Unit tests:
  - create_operation с тем же ключом + payload → 200
  - create_operation с тем же ключом + другой payload → 409
  - Параллельные POST с одним ключом → одна операция
  - GET /operations?client_request_id=X → находит операцию
  - GET /operations?client_request_id=X → пустой список если нет
Integration tests:
  - Полный цикл: POST → GET lookup → подтверждение
Acceptance criteria:
  1. Повторный POST с тем же ключом не создаёт дубль
  2. GET-поиск находит операцию по client_request_id
  3. 409 при конфликте payload
  4. Все тесты проходят (pytest)
Рекомендуемый commit:
  feat(syncserver): add operation lookup by client_request_id
Риски:
  - На проде могут быть дубли client_request_id от старого фронтенда
  - Уникальность client_request_id не гарантирована на уровне БД
```

### WP-2: Django BFF Correlation & Contracts (Agent B)

```text
ID:            WP-2
Название:      Django BFF: Correlation Headers & Idempotency Proxy
Исполнитель:   Agent B
Репозиторий:   Warehouse_web/
Цель:          Пробросить correlation headers и client_request_id
               для ВСЕХ операций (не только temporary), добавить
               endpoint поиска по ключу
Зависимости:   WP-0, WP-1 (для тестов, не для кода)
Входные:       Contract Package §5.4, §7.2
Выходные:      Обновлённые BFF views + тесты
Файлы (+):     Warehouse_web/apps/operations/views.py
               Warehouse_web/apps/bff_api/operations_views.py
               Warehouse_web/apps/sync_client/client.py
               Warehouse_web/apps/operations/tests.py
               Warehouse_web/apps/bff_api/tests.py
Файлы (-):     Angular/, SyncServer/app/services/
Изменения API:
  - Проброс X-Client-* → X-Forwarded-* → SyncServer
  - Проброс X-Request-Id из ответа SyncServer → клиент
  - GET /bff/api/v1/operations?client_request_id=X → proxy к SyncServer
  - client_request_id НЕ генерируется BFF — всегда приходит от Angular
Изменения БД:  Нет
Миграции:      Нет
Unit tests:
  - BFF пробрасывает X-Client-Session-Id в SyncServer
  - BFF возвращает X-Request-Id из ответа SyncServer
  - client_request_id из Angular доходит до SyncServer
  - GET-поиск по client_request_id работает
Acceptance criteria:
  1. Все заголовки проходят от Angular до SyncServer
  2. X-Request-Id возвращается клиенту
  3. client_request_id из Angular НЕ перезаписывается BFF
  4. Все тесты проходят (python manage.py test)
Рекомендуемый commit:
  feat(bff): proxy correlation headers and idempotency key
Риски:
  - Старый Angular шлёт client_request_id только для temporary
  - Нужна обратная совместимость: BFF не требует поле
```

### WP-3: Angular Result Contract & UX (Agent C)

```text
ID:            WP-3
Название:      Angular: Operation Result Contract & State Machine
Исполнитель:   Agent C
Репозиторий:   Warehouse_frontend/
Цель:          Разделить submit result и list refresh, показывать
               operation_id, запретить двойной submit
Зависимости:   WP-0, WP-3-dep (DiagnosticsSessionService от Agent D —
               мок на старте)
Входные:       Contract Package §5.1, §5.2, §6
Выходные:      Обновлённые компоненты + тесты
Файлы (+):     Warehouse_frontend/src/app/features/operations/pages/operations-page/operations-page.component.ts
               Warehouse_frontend/src/app/features/operations/components/operation-create-modal/operation-create-modal.component.ts
               Warehouse_frontend/src/app/core/services/operations.service.ts (методы result)
               Warehouse_frontend/src/app/core/models/operations.models.ts (OperationSubmitResult)
               Warehouse_frontend/src/app/core/services/operations.service.spec.ts
Файлы (-):     SyncServer/, Warehouse_web/, bff-api.service.ts (заголовки — Agent D)
Изменения API: Только внутренние Angular
Изменения БД:  Нет
Unit tests:
  - Успешный submit возвращает OperationSubmitResult с operationId
  - Ошибка submit выбрасывает исключение с error code
  - loadList failure не меняет статус submit на failed
  - Двойной клик блокируется (isSubmitting + локальный guard)
  - onConfirmSubmit не закрывает модал до показа результата
Acceptance criteria:
  1. Пользователь видит «Операция №X проведена» после submit
  2. Ошибка списка показывает warning «...но журнал не обновился»
  3. Кнопка Submit блокируется на всё время обработки
  4. onConfirmSubmit показывает результат до закрытия
  5. Все существующие unit-тесты проходят
Рекомендуемый commit:
  fix(frontend): separate operation submit result from list refresh
Риски:
  - Agent D может изменить сигнатуры общих методов
  - Нужна координация через Coordinator
```

### WP-4: Angular Identity & Correlation (Agent D)

```text
ID:            WP-4
Название:      Angular: Correlation Identifiers & Session Service
Исполнитель:   Agent D
Репозиторий:   Warehouse_frontend/
Цель:          Создать DiagnosticsSessionService, добавить заголовки,
               управлять idempotency_key в черновике
Зависимости:   WP-0
Входные:       Contract Package §5.4, §9
Выходные:      Новый сервис + обновлённый BffApiService + модели
Файлы (+):     Warehouse_frontend/src/app/core/services/diagnostics-session.service.ts (новый)
               Warehouse_frontend/src/app/core/api/bff-api.service.ts
               Warehouse_frontend/src/app/core/models/operations.models.ts (idempotencyKey, draftId)
               Warehouse_frontend/src/app/features/operations/components/operation-create-modal/operation-create-modal.component.ts (draft_id, idempotency_key)
               Warehouse_frontend/src/app/core/services/operations.service.ts (_newClientRequestId → idempotency_key)
               Warehouse_frontend/src/app/app.config.ts
               Warehouse_frontend/src/environments/environment.ts (новый, frontendVersion)
               Warehouse_frontend/src/app/core/services/diagnostics-session.service.spec.ts (новый)
Файлы (-):     SyncServer/, Warehouse_web/
Изменения API: Заголовки HTTP, поле idempotencyKey в draft
Изменения БД:  Нет
Unit tests:
  - session_id создаётся один раз и хранится в sessionStorage
  - tab_id уникален для каждой вкладки
  - idempotency_key не меняется при повторном createOperation
  - http_request_id новый для каждого HTTP-запроса
  - Заголовки добавляются ко всем мутациям
Acceptance criteria:
  1. idempotency_key создаётся при открытии формы и НЕ меняется
  2. http_request_id новый при каждом вызове
  3. Все заголовки присутствуют в запросах
  4. frontend_version передаётся из environment
  5. Существующие тесты проходят
Рекомендуемый commit:
  feat(frontend): add stable operation identifiers and correlation headers
Риски:
  - environment.ts нужно генерировать при сборке
  - git SHA может быть недоступен в dev-режиме
```

### WP-5: Integration & Cross-Repo Tests (Integration Agent)

```text
ID:            WP-5
Название:      Cross-Repo Integration & Conflict Resolution
Исполнитель:   Integration Agent
Репозиторий:   Все три
Цель:          Слить WP-1..4, разрешить конфликты, запустить все тесты
Зависимости:   WP-1, WP-2, WP-3, WP-4 (все завершены)
Входные:       Все WP
Выходные:      Сквозная сборка, проходящие тесты
Файлы (+):     Любые конфликтующие файлы (минимальные правки)
               docker-compose.yml (если нужны переменные)
               Makefile (если нужны новые цели)
               .github/workflows/ (CI)
Файлы (-):     Бизнес-логика (только интеграционные склейки)
Изменения API: Нет новых
Изменения БД:  Проверить миграции, применить
Acceptance criteria:
  1. npm run build проходит
  2. python manage.py test проходит
  3. python -m pytest (SyncServer) проходит
  4. Сквозной запрос Angular → BFF → SyncServer успешен
  5. Нет конфликтов в общих файлах
Рекомендуемый commit:
  chore: integrate operation reliability stage 0-2
```

### WP-6: E2E & Adversarial Testing (Agent E)

```text
ID:            WP-6
Название:      E2E: Network Faults, Timeouts, Duplicate Prevention
Исполнитель:   Agent E
Репозиторий:   Warehouse_frontend/e2e/
Цель:          Проверить все сценарии из матрицы HTTP-ответов
Зависимости:   WP-5 (интеграция)
Входные:       Contract Package §5.6, §8, §12
Выходные:      E2E тесты + отчёт
Файлы (+):     Warehouse_frontend/e2e/operation-reliability.spec.ts (новый)
               Warehouse_frontend/e2e/helpers/network-faults.ts (новый)
Файлы (-):     Production-код
Тестовые сценарии:
  - Успешное создание + submit → виден operation_id
  - Submit + ошибка loadList → warning, не ошибка submit
  - Таймаут после обработки сервером → outcome_unknown → resolve → найден
  - Таймаут до обработки → outcome_unknown → resolve → не найден → повтор
  - Двойной клик → одна операция
  - Обрыв сети → сообщение
  - Две вкладки → разные tab_id
  - Старый черновик без idempotencyKey → обратная совместимость
Acceptance criteria:
  1. Все сценарии проходят
  2. Дублей нет ни в одном сценарии
  3. Все состояния state machine покрыты
  4. Отчёт приложен
Рекомендуемый commit:
  test(e2e): add operation reliability adversarial scenarios
```

---

## 13. File Ownership Matrix

| Файл | Agent A | Agent B | Agent C | Agent D | Integration | Conflict? |
|------|---------|---------|---------|---------|-------------|-----------|
| `SyncServer/app/api/routes_operations.py` | ✅ | - | - | - | - | No |
| `SyncServer/app/services/operations_service.py` | ✅ | - | - | - | - | No |
| `SyncServer/app/repos/operations_repo.py` | ✅ | - | - | - | - | No |
| `Warehouse_web/apps/operations/views.py` | - | ✅ | - | - | - | No |
| `Warehouse_web/apps/bff_api/operations_views.py` | - | ✅ | - | - | - | No |
| `Warehouse_web/apps/sync_client/client.py` | - | ✅ | - | - | - | No |
| `Warehouse_frontend/src/app/core/api/bff-api.service.ts` | - | - | - | ✅ | 🔶 | **SHARED** |
| `Warehouse_frontend/src/app/core/services/operations.service.ts` | - | - | ✅ | ✅ | 🔶 | **SHARED** |
| `Warehouse_frontend/src/app/core/models/operations.models.ts` | - | - | ✅ | ✅ | 🔶 | **SHARED** |
| `Warehouse_frontend/src/app/features/operations/pages/operations-page/operations-page.component.ts` | - | - | ✅ | - | 🔶 | No (Agent C) |
| `Warehouse_frontend/src/app/features/operations/components/operation-create-modal/operation-create-modal.component.ts` | - | - | ✅ | ✅ | 🔶 | **SHARED** |
| `Warehouse_frontend/src/app/core/services/diagnostics-session.service.ts` | - | - | - | ✅ | - | No (Agent D) |
| `Warehouse_frontend/src/app/app.config.ts` | - | - | - | ✅ | - | No (Agent D) |
| `Warehouse_frontend/src/environments/environment.ts` | - | - | - | ✅ | - | No (Agent D) |

### Стратегия для SHARED файлов

**Файлы с общим доступом (🔶):**

1. **`bff-api.service.ts`** — правит только Agent D (заголовки). Agent C использует существующие методы без изменений этого файла.
2. **`operations.service.ts`** — Agent C: методы result (`submitWithResult`). Agent D: `_newClientRequestId` → `idempotency_key`. **Последовательная работа:** Agent D первый, Agent C второй.
3. **`operations.models.ts`** — Agent D: добавляет `idempotencyKey`, `draftId`. Agent C: добавляет `OperationSubmitResult`. **Последовательная работа:** Agent D первый, Agent C второй.
4. **`operation-create-modal.component.ts`** — Agent D: инициализация `draft_id`, `idempotency_key` при открытии. Agent C: кнопки, состояния. **Последовательная работа:** Agent D первый, Agent C второй.

**Порядок для SHARED:** Agent D → Integration Agent (проверка) → Agent C.

---

## 14. Test Strategy

### 14.1 Unit Tests

| Уровень | Пакет | Команда | Минимум тестов |
|---------|-------|---------|---------------|
| Angular | WP-3, WP-4 | `npx vitest --run` | 12+ новых |
| Django | WP-2 | `python manage.py test apps.operations apps.bff_api` | 8+ новых |
| SyncServer | WP-1 | `python -m pytest tests/test_operations_idempotency.py` | 6+ новых |

### 14.2 Integration Tests

| Тест | Пакет | Описание |
|------|-------|----------|
| Сквозной idempotency | WP-5 | Angular → BFF → SyncServer: повторный POST с тем же ключом |
| Сквозной outcome | WP-5 | Таймаут → поиск → нахождение |
| Сквозные заголовки | WP-5 | X-Client-* → BFF → SyncServer → X-Request-Id → Angular |

### 14.3 E2E Tests (Playwright)

| Сценарий | Эмуляция | Ожидаемый результат |
|----------|----------|-------------------|
| Успешный submit | Обычный | Toast «Операция №... проведена» |
| Submit + ошибка loadList | Playwright route.abort() для GET /operations | Warning «список не обновился» |
| Timeout после обработки | Playwright route.abort() для ответа POST | Outcome unknown → resolve → найден |
| Timeout до обработки | Playwright route.abort() для запроса POST | Outcome unknown → resolve → не найден → повтор |
| Двойной клик | Два быстрых click() | Только одна операция в списке |
| Обрыв сети | Playwright route.abort() | Сообщение об ошибке |
| Две вкладки | Два контекста Playwright | Разные tab_id, независимые черновики |
| Старый черновик | Мок без idempotencyKey | Генерируется новый ключ |

### 14.4 Сетевая эмуляция

```typescript
// Playwright route interception для таймаутов
await page.route('**/bff/api/v1/operations', async (route) => {
  // Симуляция: запрос уходит, ответ не приходит
  await route.abort('timedout');
});

// Для ситуации «сервер обработал, но ответ потерян»:
await page.route('**/bff/api/v1/operations', async (route) => {
  await route.continue(); // запрос уходит
  // ответ не возвращается — abort после continue
});
```

---

## 15. Deployment and Rollback

### 15.1 Порядок деплоя

```text
1. SyncServer (WP-1): миграции + новый код
   → Обратная совместимость: старый фронтенд продолжает работать
   → client_request_id опционален, GET-поиск — новый эндпоинт

2. Django BFF (WP-2):
   → Проброс заголовков, client_request_id для всех операций
   → Обратная совместимость: старый фронтенд без client_request_id

3. Angular (WP-3 + WP-4):
   → Новый UX, correlation headers
   → Старый BFF принимает (client_request_id опционален)
```

### 15.2 Обратная совместимость

| Компонент | Старая версия | Новая версия | Совместимость |
|-----------|--------------|--------------|---------------|
| SyncServer | Без GET-поиска | С GET-поиском | Старый BFF не использует новый эндпоинт ✅ |
| BFF | Без client_request_id для catalog | С client_request_id для всех | Старый Angular: BFF добавит client_request_id сам (если нет) ⚠️ |
| Angular | Без idempotency_key | С idempotency_key | Старый BFF: заголовки — новые, но поле в теле опционально ✅ |

### 15.3 Rollback

- **SyncServer**: откатить код, GET-эндпоинт исчезнет → BFF получит 404 → fallback
- **BFF**: откатить код → старый Angular потеряет correlation headers, но операции продолжат создаваться
- **Angular**: откатить сборку → старый UX без operation_id, но без ошибок

### 15.4 Нужен ли feature flag?

**Не обязателен.** Изменения обратно совместимы. Добавлять feature flag только если есть риск нарушения прода.

---

## 16. Risks and Open Questions

| # | Риск | Вероятность | Влияние | Митигация |
|---|------|-------------|---------|-----------|
| R1 | `client_request_id` не уникален в БД SyncServer | Средняя | Высокое | Проверить Agent A: нужен ли UNIQUE constraint |
| R2 | Старый Angular не шлёт `client_request_id` для catalog items | Высокая | Низкое | BFF обрабатывает отсутствие поля |
| R3 | `sessionStorage` копируется при дублировании вкладки | Высокая | Низкое | `tab_id` в памяти решает проблему |
| R4 | nginx не пробрасывает кастомные заголовки | Низкая | Среднее | Проверить nginx.conf в Docker |
| R5 | `git SHA` недоступен при dev-сборке | Средняя | Низкое | Fallback: `'dev'` |
| R6 | Конфликт при последовательном изменении SHARED файлов | Средняя | Среднее | Integration Agent разрешает |

### Открытые вопросы

1. **Нужен ли UNIQUE constraint на `client_request_id`?** Сейчас поиск по `created_by_user_id + client_request_id`. Если constraint не нужен — параллельные вставки могут создать две операции с одним ключом. Нужен ли БД-уровень?
2. **Формат endpoint поиска:** `GET /operations?client_request_id=X` или `GET /operations/by-client-request/X`? Решение за Agent A + Coordinator.
3. **nginx.conf:** Пробрасывает ли nginx `X-Client-*` заголовки? Проверить в `docker-compose` конфигурации.
4. **Django middleware:** Есть ли уже `X-Request-Id` middleware? Подтверждено для `RequestTracingMiddleware`, проверить возврат клиенту.
5. **Старые черновики:** Что делать с существующими `OperationDraftVm` без `idempotencyKey`? Генерировать при загрузке.

---

## 17. Acceptance Criteria

Реализация считается завершённой, если:

1. ✅ Повтор одной логической команды не создаёт дубль
2. ✅ `idempotency_key` не меняется при повторных попытках
3. ✅ Каждый HTTP-запрос получает отдельный `http_request_id`
4. ✅ Пользователь получает подтверждение с `operation_id`
5. ✅ Ошибка обновления списка не маскируется под ошибку submit
6. ✅ После timeout фронтенд способен определить существование операции
7. ✅ Двойной клик не создаёт две операции
8. ✅ Сквозные идентификаторы видны в Angular, Django BFF и SyncServer
9. ✅ Все unit, integration и E2E тесты проходят
10. ✅ Старый фронтенд продолжает работать во время постепенного деплоя
11. ✅ Redis, Celery и отдельные workers не добавлены
12. ✅ UI diagnostics, autosave и Session Replay не реализованы

---

## 18. Definition of Done

Для каждого Work Package:

1. Код написан и проходит линтер/форматтер
2. Unit-тесты написаны и проходят
3. Интеграционные тесты (если применимо) проходят
4. E2E тесты (если применимо) проходят
5. Документация обновлена (если применимо)
6. Коммит подготовлен (но не выполнен — по команде)
7. Отчёт о выполнении WP с evidence table

Для всего ТЗ:

1. Все WP приняты Coordinator
2. Integration Agent подтвердил сквозную сборку
3. Agent E подтвердил прохождение E2E
4. Все acceptance criteria выполнены
5. Coordinator выпустил финальный отчёт

---

## 19. Рекомендуемый порядок запуска агентов

```text
Шаг 1: Coordinator создаёт Contract Package (WP-0)
       Время: ~30 мин

Шаг 2: PARALLEL — Agent A, Agent B, Agent D
       Agent A: SyncServer idempotency (WP-1)
       Agent B: Django BFF correlation (WP-2)
       Agent D: Angular correlation identifiers (WP-4)
       Время: ~1–2 часа

Шаг 3: Agent C: Angular result UX (WP-3)
       (ждёт Agent D для DiagnosticsSessionService,
        может начать с мока)
       Время: ~1–2 часа

Шаг 4: Integration Agent: слияние, тесты (WP-5)
       Время: ~30–60 мин

Шаг 5: Agent E: E2E adversarial (WP-6)
       Время: ~1–2 часа

Шаг 6: Coordinator: финальная приёмка
       Время: ~30 мин
```

**Общее время:** 4–8 часов при параллельной работе.

---

## 20. Промпты для SWARM-агентов

### 20.1 Coordinator Prompt

```text
You are the SWARM Coordinator for TZ-ANGULAR_OPERATION_RELIABILITY.

Your ONLY job: create the Contract Package (WP-0).

Read docs/ARCHITECTURE_REVIEW_ANGULAR_UI_DIAGNOSTICS.md (frozen).
Read docs/TZ-ANGULAR_OPERATION_RELIABILITY_SWARM.md §5 (Contract Package).

Create file: docs/contracts/OPERATION_RELIABILITY_CONTRACTS.md

This file MUST contain:
1. All DTOs with field names, types, and nullability
2. All error codes with HTTP status mappings
3. State machine (all states, allowed transitions, forbidden transitions)
4. HTTP header specifications (name, format, source, required/optional)
5. HTTP response matrix (status → state → action → message)
6. Identifier lifecycle table
7. Example request/response pairs for:
   - POST /operations (create with idempotency_key)
   - POST /operations (repeat with same key → 200)
   - POST /operations (repeat with same key + different payload → 409)
   - GET /operations?client_request_id=X (found)
   - GET /operations?client_request_id=X (not found)

VERIFY every field against the actual code using grep. Do not invent fields.

DO NOT:
- Write any production code
- Modify any source files
- Start implementation
- Create commits

Output: docs/contracts/OPERATION_RELIABILITY_CONTRACTS.md
```

### 20.2 Agent A Prompt

```text
You are Agent A: SyncServer Idempotency Hardening (WP-1).

Repository: SyncServer/
Scope: operation idempotency and lookup by client_request_id.

READ BEFORE STARTING:
- docs/contracts/OPERATION_RELIABILITY_CONTRACTS.md (Contract Package)
- SyncServer/app/services/operations_service.py (lines 588-669 — create_operation)
- SyncServer/app/repos/operations_repo.py (lines 105-109 — get_by_client_request_id)

TASKS:
1. Add GET /api/v1/operations?client_request_id={key} endpoint
   - Filter by client_request_id in existing list endpoint
   - Return standard paginated response

2. Verify idempotency behavior:
   - Same key + same payload → 200, returns existing operation
   - Same key + different payload → 409, code "idempotency_payload_conflict"
   - Parallel POSTs with same key → only ONE operation created

3. Add tests (SyncServer/tests/test_operations_idempotency.py):
   - test_repeat_same_key_same_payload_returns_existing
   - test_repeat_same_key_different_payload_returns_409
   - test_lookup_by_client_request_id_finds_operation
   - test_lookup_by_client_request_id_not_found
   - test_parallel_create_same_key_no_duplicate
   - test_idempotency_scoped_to_user

ALLOWED FILES:
- SyncServer/app/api/routes_operations.py
- SyncServer/app/services/operations_service.py
- SyncServer/app/repos/operations_repo.py
- SyncServer/app/schemas/operation.py
- SyncServer/tests/test_operations_idempotency.py (NEW)

FORBIDDEN:
- Any files outside SyncServer/
- Django BFF, Angular, nginx
- Database migrations (field already exists)
- Business logic changes beyond idempotency

VERIFICATION: python -m pytest tests/test_operations_idempotency.py -v

REPORT FORMAT:
- List of changed files with line ranges
- Test results (pass/fail count)
- Any assumptions made
- Open questions for Coordinator
```

### 20.3 Agent B Prompt

```text
You are Agent B: Django BFF Correlation & Contracts (WP-2).

Repository: Warehouse_web/
Scope: proxy correlation headers, client_request_id for ALL operations.

READ BEFORE STARTING:
- docs/contracts/OPERATION_RELIABILITY_CONTRACTS.md
- Warehouse_web/apps/operations/views.py (lines 200-250 — create operation payload)
- Warehouse_web/apps/sync_client/transport.py

TASKS:
1. Ensure client_request_id from Angular reaches SyncServer for ALL operations
   (currently only for temporary items — lines 207-217)
   - If Angular sends client_request_id → pass through
   - If Angular does NOT send it → pass through (don't generate)
   - Remove BFF-side generation of client_request_id

2. Add correlation header forwarding:
   - X-Client-Session-Id → forward to SyncServer
   - X-Client-Tab-Id → forward to SyncServer
   - X-Client-Request-Id → forward to SyncServer
   - X-Client-Draft-Id → forward to SyncServer
   - X-Frontend-Version → forward to SyncServer

3. Extract X-Request-Id from SyncServer response and return to Angular
   - Read from response headers
   - Add to BFF response headers

4. Add BFF endpoint:
   GET /bff/api/v1/operations?client_request_id={key}
   → proxy to SyncServer GET /api/v1/operations?client_request_id={key}

5. Add tests:
   - test_client_request_id_forwarded_for_catalog_operations
   - test_correlation_headers_forwarded
   - test_x_request_id_returned_to_client
   - test_client_request_id_lookup_endpoint

ALLOWED FILES:
- Warehouse_web/apps/operations/views.py
- Warehouse_web/apps/bff_api/operations_views.py
- Warehouse_web/apps/sync_client/client.py
- Warehouse_web/apps/operations/tests.py
- Warehouse_web/apps/bff_api/tests.py

FORBIDDEN:
- Angular/ frontend code
- SyncServer business logic
- Database migrations

VERIFICATION: python manage.py test apps.operations apps.bff_api

REPORT FORMAT:
- List of changed files
- Test results
- Header forwarding verified (yes/no for each)
```

### 20.4 Agent C Prompt

```text
You are Agent C: Angular Operation Result Contract & UX (WP-3).

Repository: Warehouse_frontend/
Scope: separate submit result from list refresh, show operation_id.

READ BEFORE STARTING:
- docs/contracts/OPERATION_RELIABILITY_CONTRACTS.md (§5.1, §5.2, §6)
- docs/ARCHITECTURE_REVIEW_ANGULAR_UI_DIAGNOSTICS.md (RISK-001a, RISK-003)
- Warehouse_frontend/src/app/features/operations/pages/operations-page/operations-page.component.ts (lines 672-714, 823-841)
- Warehouse_frontend/src/app/features/operations/components/operation-create-modal/operation-create-modal.component.ts

TASKS:
1. Fix onDraftSubmit (operations-page.component.ts:696-714):
   - After successful submit: set operationResult with operationId
   - Show toast/banner: "Операция №{displayNumber} проведена"
   - Close modal or switch to read-only
   - Start loadList separately
   - If loadList fails: show warning banner, do NOT clear operationResult

2. Fix onConfirmSubmit (operations-page.component.ts:823-841):
   - Show result BEFORE closing modal
   - Remove duplicate set(false) on line 839
   - After closing confirm, attempt list refresh

3. Add state machine states:
   - submitted → show result, close/readonly form
   - refresh_failed → warning banner, operation still submitted
   - submit_failed → error message, form stays editable

4. Block double submit:
   - isSubmitting + local guard flag
   - Button disabled until full cycle complete

5. Add OperationSubmitResult type to operations.models.ts

6. Handle empty catch blocks in onDraftDelete, onRowCancel, onRowEdit, onDraftRestore:
   - Show error message, don't silently swallow

ALLOWED FILES:
- Warehouse_frontend/src/app/features/operations/pages/operations-page/operations-page.component.ts
- Warehouse_frontend/src/app/features/operations/components/operation-create-modal/operation-create-modal.component.ts
- Warehouse_frontend/src/app/core/services/operations.service.ts (add submitWithResult method)
- Warehouse_frontend/src/app/core/models/operations.models.ts (add OperationSubmitResult)
- Warehouse_frontend/src/app/core/services/operations.service.spec.ts

DO NOT TOUCH:
- bff-api.service.ts (Agent D's file)
- diagnostics-session.service.ts (Agent D's file)
- SyncServer/ or Warehouse_web/

NOTE: DiagnosticsSessionService may not be ready. Use a temporary mock:
  const draft_id = 'mock-draft-id';
Replace with real service after Agent D completes.

VERIFICATION: npx vitest --run src/app/core/services/operations.service.spec.ts

REPORT FORMAT:
- List of changed files with line ranges
- State machine transitions verified
- Toast/banner behavior described
```

### 20.5 Agent D Prompt

```text
You are Agent D: Angular Identity & Correlation (WP-4).

Repository: Warehouse_frontend/
Scope: create DiagnosticsSessionService, idempotency_key, correlation headers.

READ BEFORE STARTING:
- docs/contracts/OPERATION_RELIABILITY_CONTRACTS.md (§5.4, §9)
- Warehouse_frontend/src/app/core/api/bff-api.service.ts (current headers)
- Warehouse_frontend/src/app/core/services/operations.service.ts (lines 133-139, 814)

TASKS:
1. Create DiagnosticsSessionService:
   File: Warehouse_frontend/src/app/core/services/diagnostics-session.service.ts
   - session_id: generate UUID, store in sessionStorage, load on init
   - tab_id: generate UUID, store in memory ONLY (private field)
   - newRequestId(): generate new UUID for each HTTP request
   - newDraftId(): generate UUID for new operation form
   - newIdempotencyKey(): generate UUID for new operation command
   - frontendVersion: read from environment

2. Modify BffApiService (bff-api.service.ts):
   - getMutationHeaders(): add X-Client-Session-Id, X-Client-Tab-Id,
     X-Client-Request-Id (new per request), X-Frontend-Version
   - Optionally add X-Client-Draft-Id for operation-specific requests
   - Extract X-Request-Id from response headers → store in session service

3. Modify operations.models.ts:
   - Add idempotencyKey?: string to OperationDraftVm
   - Add draftId?: string to OperationDraftVm

4. Modify operation-create-modal.component.ts:
   - On form open: generate draftId and idempotencyKey
   - Store in localDraft

5. Modify operations.service.ts:
   - createOperation: use draft.idempotencyKey as client_request_id
     (DO NOT generate new one each time!)
   - buildPayload: accept idempotencyKey parameter, don't auto-generate

6. Create environment.ts with frontendVersion

7. Register DiagnosticsSessionService in app.config.ts

ALLOWED FILES:
- Warehouse_frontend/src/app/core/services/diagnostics-session.service.ts (NEW)
- Warehouse_frontend/src/app/core/api/bff-api.service.ts
- Warehouse_frontend/src/app/core/models/operations.models.ts
- Warehouse_frontend/src/app/features/operations/components/operation-create-modal/operation-create-modal.component.ts
- Warehouse_frontend/src/app/core/services/operations.service.ts
- Warehouse_frontend/src/app/app.config.ts
- Warehouse_frontend/src/environments/environment.ts (NEW, or modify existing)
- Warehouse_frontend/src/app/core/services/diagnostics-session.service.spec.ts (NEW)

FORBIDDEN:
- SyncServer/ or Warehouse_web/
- Operation page component (Agent C's file)
- E2E tests
- UI/UX changes (Agent C's scope)

VERIFICATION: npx vitest --run

REPORT FORMAT:
- List of changed files
- Header presence verified in browser devtools (screenshot or log)
- idempotency_key stability verified
```

### 20.6 Integration Agent Prompt

```text
You are the Integration Agent for TZ-ANGULAR_OPERATION_RELIABILITY (WP-5).

Your job: merge WP-1 through WP-4, resolve conflicts, run all tests.

READ:
- docs/contracts/OPERATION_RELIABILITY_CONTRACTS.md
- All four WP reports from Agents A-D

TASKS:
1. Review all changes for conflicts
2. Pay special attention to SHARED files:
   - operations.service.ts (Agent C + Agent D)
   - operations.models.ts (Agent C + Agent D)
   - operation-create-modal.component.ts (Agent C + Agent D)
   - bff-api.service.ts (Agent D only — verify Agent C didn't touch)
3. Resolve merge conflicts
4. Run full test suites:
   - SyncServer: python -m pytest
   - Django: python manage.py test
   - Angular: npx vitest --run && npm run build
5. Verify end-to-end:
   - curl POST /bff/api/v1/operations with client_request_id
   - curl GET /bff/api/v1/operations?client_request_id=X
   - Check X-Request-Id in response headers
6. Apply any pending migrations

DO NOT:
- Add new features
- Change business logic
- Modify contracts

OUTPUT:
- Integration report with test results
- List of resolved conflicts
- Ready-to-commit state (but do NOT commit)
```

### 20.7 Agent E Prompt

```text
You are Agent E: E2E & Adversarial QA (WP-6).

Repository: Warehouse_frontend/e2e/
Scope: Playwright E2E tests for all edge cases.

READ:
- docs/contracts/OPERATION_RELIABILITY_CONTRACTS.md (§5.6, §8, §12)
- docs/TZ-ANGULAR_OPERATION_RELIABILITY_SWARM.md §14.3

PREREQUISITE: WP-5 must be complete (integration working).

TASKS:
Create file: Warehouse_frontend/e2e/operation-reliability.spec.ts

Test scenarios:
1. happy_path_submit: create → submit → see operation_id
2. submit_with_list_refresh_failure: abort GET /operations after submit → warning
3. timeout_after_server_processing: abort POST response → resolve → found
4. timeout_before_server_processing: abort POST request → resolve → not found → retry
5. double_click_prevention: rapid click ×2 → only one operation
6. network_loss: abort all requests → error message → recovery
7. two_tabs_different_ids: two browser contexts → different tab_ids
8. old_draft_without_idempotency_key: mock old draft → new key generated
9. idempotent_repeat: same key → existing operation returned

Use Playwright route interception for network fault simulation.

VERIFICATION:
  cd Warehouse_frontend && npx playwright test e2e/operation-reliability.spec.ts

DO NOT:
- Modify production code
- Fix bugs found (report them)

OUTPUT:
- Test file
- Test results (pass/fail/skipped per scenario)
- Bugs found (separate list)
```

---

## Заключение

Документ готов к запуску SWARM. Порядок действий:

1. **Coordinator** создаёт Contract Package (WP-0)
2. **Параллельно:** Agents A, B, D
3. **Последовательно:** Agent C (ждёт Agent D)
4. **Integration Agent** сливает и проверяет
5. **Agent E** проводит E2E
6. **Coordinator** принимает результат

Расчётное время: **4–8 часов** при параллельной работе.
