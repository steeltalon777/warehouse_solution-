# Contract Package: Diagnostics Stage 3 (UI Events)

**Дата заморозки:** 2026-07-15
**Источник ТЗ:** `docs/TZ-DIAGNOSTICS_STAGE3_SWARM.md`
**Архитектурное ревью:** `docs/archive/ARCHITECTURE_REVIEW_ANGULAR_UI_DIAGNOSTICS.md` §9–12 (frozen)
**Статус:** Заморожено до старта реализации. Изменения только через ADR.

---

## Содержание

1. [Глоссарий](#1-глоссарий)
2. [Event Types (10 событий)](#2-event-types-10-событий)
3. [DTO событий](#3-dto-событий)
4. [Приоритеты и flush-поведение](#4-приоритеты-и-flush-поведение)
5. [Backend контракты](#5-backend-контракты)
6. [SQL DDL](#6-sql-ddl)
7. [Очередь и batch-отправка](#7-очередь-и-batch-отправка)
8. [Точки интеграции в Angular](#8-точки-интеграции-в-angular)
9. [Что НЕ логировать (PII guard)](#9-что-не-логировать-pii-guard)
10. [TTL и очистка](#10-ttl-и-очистка)
11. [Обратная совместимость](#11-обратная-совместимость)
12. [Verification checklist](#12-verification-checklist)
13. [Файлы-зоны WP-1..4](#13-файлы-зоны-wp-14)

---

## 1. Глоссарий

| Термин | Значение |
|---|---|
| `event` | Один запись диагностического события |
| `batch` | Массив событий, отправляемых одним HTTP POST |
| `queue` | In-memory массив событий в браузере (max 200) |
| `flush` | Отправка batch через `fetch()` |
| `sendBeacon` | Браузерный API для отправки при unload |
| `critical` | Severity, требующий немедленной отправки (250–500 мс) |
| `track()` | Публичный API `DiagnosticsService` для записи события |
| `bypass-interceptor` | Использование `fetch()` вместо Angular `HttpClient` |

---

## 2. Event Types (10 событий)

Базовый набор. Никаких кликов мыши, клавиатуры, контента форм. Только контрольные точки бизнес-процесса.

| # | event_type | Severity | Где создаётся | Когда | Источник TZ |
|---|-----------|----------|---------------|-------|-------------|
| 1 | `form_opened` | info | `OperationCreateModalComponent.effect(draft received)` | Открытие модала | TZ §5.1 row 1 |
| 2 | `form_closed` | info | `OperationCreateModalComponent.ngOnDestroy()` | Закрытие модала | TZ §5.1 row 2 |
| 3 | `submit_clicked` | info | `OperationCreateModalComponent.onSubmit()` (before emit) | Нажатие «Подтвердить» | TZ §5.1 row 3 |
| 4 | `validation_failed` | warning | `OperationCreateModalComponent.onSubmit()` (если `saveDisabledReason()`) | Клиентская валидация | TZ §5.1 row 4 |
| 5 | `request_started` | info | `OperationsService.createOperation/submitOperation` (перед HTTP) | Начало запроса | TZ §5.1 row 5 |
| 6 | `request_succeeded` | info | `OperationsService.createOperation/submitOperation` (после успеха) | Успешный HTTP | TZ §5.1 row 6 |
| 7 | `request_failed` | error | `HttpErrorInterceptor` / `OperationsService` catch | Ошибка HTTP | TZ §5.1 row 7 |
| 8 | `outcome_unknown` | warning | `OperationsService` (при `err.code === 'operation_outcome_unknown'`) | Таймаут | TZ §5.1 row 8 |
| 9 | `response_processing_failed` | error | `OperationsPageComponent.onDraftSubmit` (catch после HTTP success) | Обработка упала | TZ §5.1 row 9 |
| 10 | `unexpected_error` | critical | `GlobalErrorHandler.handleError()` | Неперехваченная ошибка | TZ §5.1 row 10 |
| 11 | `navigation_away_with_unsaved` | warning | `OperationsPageComponent.ngOnDestroy` (если `hasUnsavedChanges`) | Уход со страницы | TZ §5.1 row 10 (в DTO 11-й тип) |

> ⚠️ В TZ DTO `DiagnosticEventType` (TZ §5.2) перечисляет **11** строк (включая `navigation_away_with_unsaved`). Список в §5.1 — **10** событий. `navigation_away_with_unsaved` упомянут в §7.2 как точка интеграции. **Coordinator решение:** включаем в базовый набор. Итого **11 событий**.

---

## 3. DTO событий

### 3.1 `DiagnosticEventType` (union string)

```typescript
export type DiagnosticEventType =
  | 'form_opened'
  | 'form_closed'
  | 'submit_clicked'
  | 'validation_failed'
  | 'request_started'
  | 'request_succeeded'
  | 'request_failed'
  | 'outcome_unknown'
  | 'response_processing_failed'
  | 'navigation_away_with_unsaved'
  | 'unexpected_error';
```

Файл: `Warehouse_frontend/src/app/core/diagnostics/diagnostics.models.ts` (NEW).

### 3.2 `DiagnosticSeverity`

```typescript
export type DiagnosticSeverity = 'debug' | 'info' | 'warning' | 'error' | 'critical';
```

### 3.3 `DiagnosticEventVm`

```typescript
export interface DiagnosticEventVm {
  /** UUID per event, generated on creation. */
  event_id: string;
  /** Type from DiagnosticEventType. */
  event_type: DiagnosticEventType;
  /** ISO 8601, generated on creation. */
  occurred_at: string;

  // Correlation (from DiagnosticsSessionService — Этап 0)
  session_id: string;
  tab_id: string;
  frontend_version: string;

  // Context (nullable)
  route?: string;
  operation_type?: string;
  draft_id?: string;
  idempotency_key?: string;
  http_request_id?: string;
  server_request_id?: string;
  user_id?: string;
  device_id?: string;
  site_id?: string;

  severity: DiagnosticSeverity;
  details?: DiagnosticEventDetails;
}
```

### 3.4 `DiagnosticEventDetails`

```typescript
export interface DiagnosticEventDetails {
  // Counts
  items_count?: number;
  invalid_items_count?: number;

  // Timing
  duration_ms?: number;

  // HTTP
  http_method?: string;
  http_url?: string;
  http_status?: number;
  error_code?: string;
  /** Max 200 chars, PII-scrubbed. */
  error_message?: string;

  // Draft state
  draft_status?: string;
  has_unsaved_changes?: boolean;

  // Failure
  /** Max 500 chars. */
  reason?: string;
  /** Max 300 chars, ONLY for unexpected_error. */
  stack_trace_snippet?: string;
}
```

### 3.5 `DiagnosticEventBatchVm`

```typescript
export interface DiagnosticEventBatchVm {
  events: DiagnosticEventVm[];
  /** ISO 8601 of batch creation. */
  sent_at: string;
  /** Monotonic counter, increments per batch. */
  sequence: number;
}
```

---

## 4. Приоритеты и flush-поведение

| Severity | Flush delay | Что делаем | Источник |
|----------|-------------|------------|----------|
| `debug` | 15 000 мс (regular) | Удалять первыми при overflow | TZ §6.2 |
| `info` | 15 000 мс (regular) | Стандартная отправка | TZ §6.2 |
| `warning` | 15 000 мс (regular) | Стандартная отправка | TZ §6.2 |
| `error` | 15 000 мс (regular) + sendBeacon при unload | Должен дойти | TZ §6.2 |
| `critical` | 250–500 мс (force flush) | Немедленная отправка | TZ §6.1 |

**Правила overflow (TZ §6.2, §4.3):**
- Queue max: **200 событий**
- При переполнении: удалить старые `debug`, потом `info`, сохранить `warning`/`error`/`critical`
- Critical никогда не удаляется
- Досрочная отправка при накоплении **20 событий**

**Backoff (TZ §6.2):**
- 1s, 2s, 4s, max 30s
- Max 3 retry на один batch
- При исчерпании: `console.error`, остановка (не бесконечный цикл)

---

## 5. Backend контракты

### 5.1 Endpoint

```text
POST /bff/api/v1/diagnostics/ui-events/batch
Content-Type: application/json
X-CSRFToken: <required>
X-Client-Session-Id: <UUID, optional but recommended>
X-Client-Request-Id: <UUID, optional>

Request body: DiagnosticEventBatchVm
  {
    "events": DiagnosticEventVm[],
    "sent_at": "ISO 8601",
    "sequence": 1
  }

Response:
  204 No Content — успех
  400 Bad Request — пустой events, невалидный event_type
  403 Forbidden — нет CSRF
  413 Payload Too Large — body > 100 KB
  429 Too Many Requests — > 10 req/min/session
```

Файл: `Warehouse_web/apps/bff_api/diagnostics_views.py` (NEW).
URL-маршрут: `Warehouse_web/apps/bff_api/urls.py` (модифицировать).

### 5.2 Валидация (на стороне BFF)

| Проверка | Ошибка | Источник |
|----------|--------|----------|
| `events` — массив, не пустой | 400 | TZ §8.2 |
| Каждый `event.event_type` ∈ enum | 400 | TZ §8.2 |
| Размер batch ≤ 100 KB | 413 | TZ §8.2 |
| Rate limit: 10 req/min/session | 429 | TZ §8.2 |

**Scope rate limit:** per `X-Client-Session-Id` (если есть) ИЛИ per Django session. Если ни одного нет — отклоняем с 401/400.

### 5.3 Идемпотентность batch

Каждое событие имеет уникальный `event_id` (UUID v4). Backend пишет в БД с `INSERT ... ON CONFLICT (event_id) DO NOTHING` — повтор одного и того же batch не создаст дублей. Это критично для retry-логики на клиенте.

Файл: `SyncServer/app/services/diagnostics_service.py` (NEW) + endpoint.

### 5.4 Обработка ошибок клиента

- Любой 4xx/5xx от BFF/SyncServer → клиент НЕ повторяет автоматически (события теряются).
- Это осознанный trade-off: стабильность работы важнее полноты логов.
- 429 → backoff 30s.
- Сетевая ошибка → backoff по §4.

---

## 6. SQL DDL

```sql
-- Миграция: SyncServer/alembic/versions/XXXX_diagnostics_ui_events.py

CREATE TABLE diagnostics_ui_events (
    id BIGSERIAL PRIMARY KEY,
    event_id UUID NOT NULL UNIQUE,
    event_type VARCHAR(50) NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    session_id UUID NOT NULL,
    tab_id UUID,
    frontend_version VARCHAR(50),
    route VARCHAR(200),
    operation_type VARCHAR(20),
    draft_id UUID,
    idempotency_key UUID,
    http_request_id UUID,
    server_request_id UUID,
    user_id VARCHAR(50),
    device_id VARCHAR(50),
    site_id VARCHAR(50),
    severity VARCHAR(20) NOT NULL,
    details JSONB,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    batch_sequence INTEGER,
    schema_version INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX idx_diag_events_session_time ON diagnostics_ui_events (session_id, occurred_at);
CREATE INDEX idx_diag_events_type_time ON diagnostics_ui_events (event_type, occurred_at);
CREATE INDEX idx_diag_events_draft ON diagnostics_ui_events (draft_id) WHERE draft_id IS NOT NULL;
CREATE INDEX idx_diag_received_at ON diagnostics_ui_events (received_at);
```

**Источник:** TZ §8.3 (без изменений).

**SQLAlchemy model:** `SyncServer/app/models/diagnostics.py` (NEW) — наследник `Base` (см. существующий `app/models/audit_event.py`).

---

## 7. Очередь и batch-отправка

### 7.1 Параметры

| Параметр | Значение | Источник |
|----------|----------|----------|
| Max queue size | 200 | TZ §6.2 |
| Flush interval | 15 000 мс | TZ §6.2 |
| Early flush threshold | 20 событий | TZ §6.2 |
| Critical flush delay | 250–500 мс | TZ §6.2 |
| Regular batch size | до 100 KB | TZ §6.2 |
| Unload batch size | до 60 KB | TZ §6.2 |
| Backoff | 1s, 2s, 4s, max 30s | TZ §6.2 |
| Max retries | 3 | TZ §6.2 |

### 7.2 Защита от рекурсии

**Правило:** запросы идут через нативный `fetch()`, **НЕ** через Angular `HttpClient`. Иначе:

```text
interceptor ловит 4xx/5xx → track('request_failed')
  → queue.enqueue → flush
    → fetch() (если через HttpClient) → interceptor опять
      → 4xx → track → enqueue → рекурсия
```

`HttpErrorInterceptor` (TZ §7.3) должен:
- В начале: если `req.url.includes('/diagnostics/ui-events')` → `return next(req)` (без логирования).
- В catch: добавить `track('request_failed', {http_method, http_url, http_status, error_code, duration_ms})`.

### 7.3 CSRF handling

`fetch()` не использует Angular XSRF механизм. CSRF-токен читается напрямую из `document.cookie`:

```typescript
private readCsrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : '';
}
```

Если токена нет — события **не отправляются** (нельзя слать без CSRF, иначе BFF вернёт 403).

### 7.4 sendBeacon для unload

```typescript
private flushOnUnload(): void {
  if (this.queue.length === 0) return;
  const critical = this.queue.filter(e => e.severity === 'critical' || e.severity === 'error');
  if (critical.length === 0) return;

  const payload = JSON.stringify({
    events: critical.slice(-50), // max 50 events ≈ 60 KB
    sent_at: new Date().toISOString(),
    sequence: ++this.sequence,
  });

  if (navigator.sendBeacon && payload.length < 60 * 1024) {
    const blob = new Blob([payload], { type: 'application/json' });
    navigator.sendBeacon('/bff/api/v1/diagnostics/ui-events/batch', blob);
  }
  // Если payload > 60 KB или sendBeacon недоступен — теряем
}
```

---

## 8. Точки интеграции в Angular

### 8.1 Карта интеграции (из TZ §7.2)

| Файл | Метод / место | Событие | details |
|------|---------------|---------|---------|
| `operation-create-modal.component.ts` | effect (draft получен) | `form_opened` | `{ draft, operationType: draft.type }` |
| `operation-create-modal.component.ts` | `ngOnDestroy()` | `form_closed` | `{ draft, has_unsaved_changes }` |
| `operation-create-modal.component.ts` | `onSubmit()` (before emit) | `submit_clicked` | `{ draft, items_count: draft.lines.length }` |
| `operation-create-modal.component.ts` | `onSubmit()` guard | `validation_failed` | `{ draft, reason: saveDisabledReason() }` |
| `operations.service.ts` | `createOperation/submitOperation` перед `firstValueFrom` | `request_started` | `{ http_method, http_url, draft }` |
| `operations.service.ts` | после успешного `firstValueFrom` | `request_succeeded` | `{ duration_ms, draft, server_request_id }` |
| `operations.service.ts` | catch (`operation_outcome_unknown`) | `outcome_unknown` | `{ draft, error_code, http_status }` |
| `operations.service.ts` | catch (other) | `request_failed` | `{ http_status, error_code, draft }` |
| `http-error.interceptor.ts` | top of interceptor | guard (skip diagnostics URL) | — |
| `http-error.interceptor.ts` | `catchError` | `request_failed` | `{ http_method, http_url, http_status, error_code, duration_ms }` |
| `global-error-handler.ts` | `handleError` | `unexpected_error` | `{ stack_trace_snippet, route }` |
| `operations-page.component.ts` | `onDraftSubmit` catch (после HTTP success) | `response_processing_failed` | `{ draft, error_code }` |
| `operations-page.component.ts` | `ngOnDestroy` (если `hasUnsavedChanges`) | `navigation_away_with_unsaved` | `{ draft }` |

### 8.2 PII guard (что НЕ передавать)

`details.error_message` — максимум 200 символов. Если сообщение содержит чувствительные паттерны (email, токен, имя), **обрезать** или заменить на `[redacted]`.

Что НЕ логируется (TZ §5.3):
- Содержимое формы (названия ТМЦ, количества, цены)
- Полные тела запросов/ответов
- Токены, пароли, куки
- `personName` и персональные данные
- Клавиши, мышь

**Реализация:** в `DiagnosticsService.track()` не принимать `draft.lines`/`draft.notes` в details. Только агрегаты: `items_count`, `draft_status`.

---

## 9. Что НЕ логировать (PII guard)

| Категория | Примеры | Действие |
|-----------|---------|----------|
| Содержимое формы | названия ТМЦ, quantities, notes, comments | НЕ принимать в `details` |
| Персональные данные | `personName`, email, телефон | НЕ логировать |
| Auth | токены, пароли, cookies | НЕ логировать (только `user_id`) |
| HTTP body/response | полные payload | НЕ логировать (только URL, status, error_code) |
| События ввода | keydown, mousemove, focus, blur | НЕ логировать (out of scope) |

**Максимальные длины:**
- `error_message`: 200 символов
- `reason`: 500 символов
- `stack_trace_snippet`: 300 символов (только для `unexpected_error`)

---

## 10. TTL и очистка

**TTL:** 30 дней.

**Стратегия очистки** (TZ §8.4):

```sql
-- pg_cron / cron, раз в сутки
DELETE FROM diagnostics_ui_events
WHERE id IN (
    SELECT id FROM diagnostics_ui_events
    WHERE received_at < NOW() - INTERVAL '30 days'
    ORDER BY received_at
    LIMIT 20000
);
```

**Coordinator решение:** очистку задокументировать в `SyncServer/docs/diagnostics_ttl.md` (NEW), но НЕ реализовывать pg_cron в рамках этого ТЗ. Очистка — operational concern, не код.

---

## 11. Обратная совместимость

| Компонент | Старая версия | Новая версия | Совместимость |
|-----------|---------------|--------------|---------------|
| SyncServer | Без `diagnostics_ui_events` | С таблицей | Миграция additive ✅ |
| Django BFF | Без endpoint | С `POST /diagnostics/ui-events/batch` | Старый фронт не шлёт ✅ |
| Angular | Без `DiagnosticsService` | С сервисом | Lazy import, не ломает существующее ✅ |

**Самозащита DiagnosticsService:** если `fetch` падает (offline), события **не теряются немедленно** — остаются в очереди до следующей попытки. При исчерпании backoff — `console.error`, остановка. Это явный trade-off: стабильность важнее полноты.

---

## 12. Verification checklist

Coordinator считает контракты валидными, если:

- [x] Все 11 событий задокументированы с severity, файлом, методом.
- [x] DTO `DiagnosticEventVm` имеет все поля с типами и nullability.
- [x] Endpoint спецификация (URL, headers, request, response, ошибки).
- [x] SQL DDL с индексами.
- [x] Параметры очереди (200, 15s, 20 events, critical 250-500ms).
- [x] Backoff стратегия (1s, 2s, 4s, 30s, max 3 retry).
- [x] Карта интеграции (13 точек в 5 файлах).
- [x] PII guard с максимальными длинами.
- [x] TTL стратегия с интервалом.
- [x] Обратная совместимость.
- [x] Все файлы-зоны перечислены в §13.
- [x] Существующий код верифицирован grep:
  - `SyncServer/app/models/audit_event.py` — структура SQLAlchemy модели
  - `Warehouse_web/apps/bff_api/urls.py` — паттерн URL registration
  - `Warehouse_frontend/src/app/core/logging/http-error.interceptor.ts` — точка интеграции
  - `Warehouse_frontend/src/app/core/logging/global-error-handler.ts` — точка интеграции
  - `Warehouse_frontend/src/app/core/diagnostics/` — НЕ существует (verified)

---

## 13. Файлы-зоны WP-1..4

### WP-1: Backend (Agent A)
**Создать:**
- `SyncServer/app/models/diagnostics.py` (NEW)
- `SyncServer/app/services/diagnostics_service.py` (NEW)
- `SyncServer/app/api/routes_diagnostics.py` (NEW)
- `SyncServer/alembic/versions/XXXX_diagnostics_ui_events.py` (NEW)
- `Warehouse_web/apps/bff_api/diagnostics_views.py` (NEW)
- `SyncServer/tests/test_diagnostics.py` (NEW)
- `Warehouse_web/apps/bff_api/tests.py` (дополнить)
- `SyncServer/docs/diagnostics_ttl.md` (NEW, документация по TTL)

**Модифицировать:**
- `SyncServer/app/api/__init__.py` или `routes.py` — зарегистрировать router
- `Warehouse_web/apps/bff_api/urls.py` — добавить URL

### WP-2: Angular DiagnosticsService (Agent B)
**Создать:**
- `Warehouse_frontend/src/app/core/diagnostics/diagnostics.models.ts` (NEW)
- `Warehouse_frontend/src/app/core/diagnostics/diagnostics.service.ts` (NEW)
- `Warehouse_frontend/src/app/core/diagnostics/diagnostics.service.spec.ts` (NEW)

**Не трогать:** queue, integration points, backend.

### WP-3: Angular QueueService (Agent C)
**Создать:**
- `Warehouse_frontend/src/app/core/diagnostics/diagnostics-queue.service.ts` (NEW)
- `Warehouse_frontend/src/app/core/diagnostics/diagnostics-queue.service.spec.ts` (NEW)

**Модифицировать:**
- `Warehouse_frontend/src/app/app.config.ts` — если требуется явная регистрация (проверить).

**Не трогать:** HttpClient, HttpInterceptor, integration points, backend.

### WP-4: Angular Integration Points (Agent D)
**Модифицировать (только добавить вызовы `diagnostics.track()`):**
- `Warehouse_frontend/src/app/features/operations/components/operation-create-modal/operation-create-modal.component.ts`
- `Warehouse_frontend/src/app/features/operations/pages/operations-page/operations-page.component.ts`
- `Warehouse_frontend/src/app/core/services/operations.service.ts`
- `Warehouse_frontend/src/app/core/logging/http-error.interceptor.ts`
- `Warehouse_frontend/src/app/core/logging/global-error-handler.ts`

**Не трогать:** queue, service logic, backend.

### WP-5: Integration (Integration Agent)
- Review изменений
- Сквозные тесты (build, pytest, manage.py test, vitest)
- Smoke: `curl POST /bff/api/v1/diagnostics/ui-events/batch`
- Применить миграции

### WP-6: E2E QA (Agent E)
**Создать:**
- `Warehouse_frontend/e2e/diagnostics-events.spec.ts` (NEW)

**Использовать существующие хелперы:**
- `Warehouse_frontend/e2e/helpers/login.ts` — login
- `Warehouse_frontend/e2e/helpers/operation-reliability.ts` — loginAsAdmin

**Не трогать:** production code.

---

**Конец контракта.** Никакой production-код в WP-0. Реализация начинается в WP-1 (Agent A), WP-2 (Agent B), WP-3 (Agent C) — параллельно после заморозки.
