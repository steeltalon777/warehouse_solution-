# TZ: Минимальная UI-диагностика складских операций — Этап 3 (SWARM)

**Дата:** 2026-07-15  
**Источник:** замороженное ревью `docs/archive/ARCHITECTURE_REVIEW_ANGULAR_UI_DIAGNOSTICS.md`, §9–12  
**Статус:** ТЗ — без реализации  
**Режим:** SWARM (5 агентов Minimax M3 + Coordinator)

---

## Содержание

- [1. Executive Summary](#1-executive-summary)
- [2. Scope / Out of Scope](#2-scope--out-of-scope)
- [3. Существующая инфраструктура (Этапы 0–2)](#3-существующая-инфраструктура-этапы-02)
- [4. Target Architecture](#4-target-architecture)
- [5. Модель событий](#5-модель-событий)
- [6. Очередь и batch-отправка](#6-очередь-и-batch-отправка)
- [7. Точки интеграции](#7-точки-интеграции)
- [8. Backend контракты](#8-backend-контракты)
- [9. Режимы диагностики](#9-режимы-диагностики)
- [10. SWARM Topology](#10-swarm-topology)
- [11. Dependency Graph](#11-dependency-graph)
- [12. Work Packages](#12-work-packages)
- [13. File Ownership Matrix](#13-file-ownership-matrix)
- [14. Test Strategy](#14-test-strategy)
- [15. Deployment and Rollback](#15-deployment-and-rollback)
- [16. Acceptance Criteria](#16-acceptance-criteria)
- [17. Промпты для SWARM-агентов](#17-промпты-для-swarm-агентов)

---

## 1. Executive Summary

### Проблема

После Этапов 0–2 кладовщик больше не теряет операции и не создаёт дубли. Но когда он говорит «всё пропало», мы всё ещё не можем восстановить цепочку: открыл ли он форму? Добавил ли позиции? Дошёл ли запрос до сервера? Какой был ответ? Ошибка на фронтенде или на бэкенде?

### Решение

**10 семантических событий** в критических точках бизнес-процесса. Никакой записи кликов, движений мыши или содержимого форм. Только контрольные точки:

```text
form_opened → submit_clicked → request_started → request_succeeded/failed
→ outcome_unknown → navigation_away_with_unsaved → unexpected_error
```

События собираются в очереди в памяти (до 200), отправляются batch-ом каждые 15 секунд через отдельный `fetch()`-клиент (в обход Angular interceptors), пишутся в легковесную таблицу PostgreSQL с TTL 30 дней.

### Ключевые архитектурные решения

- **Отдельный `fetch()`-клиент** — не через Angular `HttpClient`, чтобы избежать рекурсии interceptor→ошибка→interceptor
- **Вне Angular Zone** — очередь и таймеры работают через `runOutsideAngular()`, не вызывая change detection
- **Пакетная отправка** — 1 запрос в 15 секунд, а не 1 запрос на событие
- **Только память** — без IndexedDB на первом этапе
- **Базовый режим всегда включён** — 10 событий, нулевая конфигурация

### Нагрузка

- ~100–500 KB памяти на 200 событий
- 1 сетевой запрос каждые 15 секунд (~10–40 KB)
- <0.1% CPU (пакетная обработка вне зоны)

---

## 2. Scope / Out of Scope

### In Scope (Этап 3)

| Компонент | Что делаем |
|-----------|-----------|
| Angular DiagnosticsService | `track(eventType, details?)` — единая точка входа |
| Angular DiagnosticsQueueService | Очередь в памяти, batch-отправка, sendBeacon |
| BffApiService / HttpErrorInterceptor | Интеграция: события `request_started/failed` |
| GlobalErrorHandler | Интеграция: событие `unexpected_error` |
| OperationCreateModalComponent | `form_opened`, `submit_clicked`, `validation_failed` |
| OperationsPageComponent | `submit_succeeded`, `submit_failed`, `navigation_away_with_unsaved` |
| OperationsService | `request_succeeded`, `outcome_unknown`, `response_processing_failed` |
| Django BFF endpoint | `POST /bff/api/v1/diagnostics/ui-events/batch` |
| SyncServer / DB | Таблица `diagnostics_ui_events`, валидация, TTL-очистка |
| Базовый режим | Всегда включён, 10 событий |

### Out of Scope

- Расширенный режим (`items_changed`, `search_performed`, `draft_autosaved`) — Этап 5
- Feature flags / конфигурация диагностики — Этап 5
- IndexedDB fallback — Этап 5 (если понадобится)
- Session Replay — Этап 6
- Автосохранение черновика — Этап 4
- Фантомные ТМЦ — отдельное ТЗ
- Дашборд / аналитика по событиям
- Алертинг на основе событий

---

## 3. Существующая инфраструктура (Этапы 0–2)

### Что уже есть в Angular

| Сервис/Файл | Что предоставляет | Как используется |
|-------------|------------------|------------------|
| `DiagnosticsSessionService` | `sessionId`, `tabId`, `newRequestId()`, `newDraftId()`, `newIdempotencyKey()`, `frontendVersion`, `lastServerRequestId` | Источник всех идентификаторов |
| `BffApiService.getMutationHeaders()` | `X-Client-Session-Id`, `X-Client-Tab-Id`, `X-Client-Request-Id`, `X-Frontend-Version`, `X-Client-Draft-Id` | Уже пробрасываются в каждом запросе |
| `BffApiService._storeServerRequestId()` | Извлекает `X-Request-Id` из ответа → `diagnostics.lastServerRequestId` | Серверный request_id доступен |
| `OperationDraftVm` | Поля `draftId`, `idempotencyKey` | Идентификаторы черновика |
| `OperationSubmitResult` | Поля `operationId`, `displayNumber`, `status`, `submitted` | Результат submit |
| `AuthContextService` | `userId`, `role`, `defaultSiteId` | Контекст пользователя |
| `OperationsService.persistState` | `PersistStatus`: `saving`, `saved`, `rejected`, `outcome_unknown` | Статус сохранения |

### Что уже есть на бэкенде

| Компонент | Что предоставляет |
|-----------|------------------|
| Django BFF | Проксирует все `X-Client-*` заголовки в SyncServer |
| Django BFF | Возвращает `X-Request-Id` клиенту |
| SyncServer | `client_request_id` с идемпотентностью |
| PostgreSQL | Работает, есть миграции Alembic |

---

## 4. Target Architecture

```text
┌──────────────────────────────────────────────────────────────┐
│                     Angular Application                      │
│                                                              │
│  ┌──────────────────────┐   ┌─────────────────────────────┐ │
│  │ Components/Services  │──▶│    DiagnosticsService        │ │
│  │ (emit events via     │   │    .track(type, details?)    │ │
│  │  diagnostics.track())│   │                             │ │
│  └──────────────────────┘   │  ┌───────────────────────┐  │ │
│                              │  │  DiagnosticsQueue     │  │ │
│  ┌──────────────────────┐   │  │  ┌─────────────────┐  │  │ │
│  │ HttpErrorInterceptor │──▶│  │  │ Memory Queue    │  │  │ │
│  │ GlobalErrorHandler   │   │  │  │ (max 200)       │  │  │ │
│  └──────────────────────┘   │  │  └─────────────────┘  │  │ │
│                              │  │  ┌─────────────────┐  │  │ │
│                              │  │  │ Batch Sender    │  │  │ │
│                              │  │  │ (fetch, 15s)    │  │  │ │
│                              │  │  └─────────────────┘  │  │ │
│                              │  └───────────────────────┘  │ │
│                              └─────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
                                    │
                          fetch() (обход HttpClient)
                                    │
                                    ▼
                  POST /bff/api/v1/diagnostics/ui-events/batch
                                    │
                                    ▼
              ┌──────────────────────────────────────────┐
              │           Django BFF                      │
              │  Валидация → bulk insert → 204           │
              └──────────────────────────────────────────┘
                                    │
                                    ▼
              ┌──────────────────────────────────────────┐
              │        PostgreSQL                         │
              │  diagnostics_ui_events                    │
              │  TTL 30 дней, порционная очистка          │
              └──────────────────────────────────────────┘
```

---

## 5. Модель событий

### 5.1 Базовый набор (10 событий)

| # | event_type | Severity | Где создаётся | Когда |
|---|-----------|----------|---------------|-------|
| 1 | `form_opened` | info | `OperationCreateModalComponent.ngOnInit()` | При открытии модала создания |
| 2 | `form_closed` | info | `OperationCreateModalComponent.ngOnDestroy()` | При закрытии модала |
| 3 | `submit_clicked` | info | `OperationCreateModalComponent.onSubmit()` | Нажатие «Подтвердить» |
| 4 | `validation_failed` | warning | `OperationCreateModalComponent.onSubmit()` (если `saveDisabledReason()`) | Клиентская валидация не прошла |
| 5 | `request_started` | info | `OperationsService.createOperation/submitOperation` — перед HTTP | Начало запроса |
| 6 | `request_succeeded` | info | `OperationsService.createOperation/submitOperation` — после успеха | Успешный HTTP-ответ |
| 7 | `request_failed` | error | `HttpErrorInterceptor` / `OperationsService` catch | Ошибка HTTP |
| 8 | `outcome_unknown` | warning | `OperationsService` — при `err.code === 'operation_outcome_unknown'` | Таймаут |
| 9 | `response_processing_failed` | error | `OperationsPageComponent.onDraftSubmit` — ошибка после успешного HTTP | Ответ получен, но обработка упала |
| 10 | `unexpected_error` | critical | `GlobalErrorHandler.handleError()` | Неперехваченная ошибка |

### 5.2 DTO (из замороженного ревью)

```typescript
// Warehouse_frontend/src/app/core/diagnostics/diagnostics.models.ts (NEW)

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

export type DiagnosticSeverity = 'debug' | 'info' | 'warning' | 'error' | 'critical';

export interface DiagnosticEventVm {
  event_id: string;            // crypto.randomUUID()
  event_type: DiagnosticEventType;
  occurred_at: string;         // ISO 8601
  session_id: string;
  frontend_version: string;

  // Контекст (nullable)
  route?: string;
  operation_type?: string;
  draft_id?: string;
  idempotency_key?: string;
  http_request_id?: string;
  server_request_id?: string;
  user_id?: string;
  device_id?: string;
  site_id?: string;
  tab_id?: string;

  severity: DiagnosticSeverity;
  details?: DiagnosticEventDetails;
}

export interface DiagnosticEventDetails {
  items_count?: number;
  invalid_items_count?: number;
  duration_ms?: number;

  http_method?: string;
  http_url?: string;
  http_status?: number;
  error_code?: string;
  error_message?: string;      // до 200 символов

  draft_status?: string;
  has_unsaved_changes?: boolean;

  reason?: string;             // до 500 символов
  stack_trace_snippet?: string; // до 300 символов (только unexpected_error)
}

export interface DiagnosticEventBatchVm {
  events: DiagnosticEventVm[];
  sent_at: string;
  sequence: number;
}
```

### 5.3 Что НЕ логировать

- Содержимое формы (названия ТМЦ, количества, цены)
- Полные тела запросов/ответов
- Токены, пароли, куки
- `personName`, персональные данные
- Каждое нажатие клавиши, движение мыши

---

## 6. Очередь и batch-отправка

### 6.1 DiagnosticsQueueService

```typescript
// Warehouse_frontend/src/app/core/diagnostics/diagnostics-queue.service.ts (NEW)

@Injectable({ providedIn: 'root' })
export class DiagnosticsQueueService implements OnDestroy {
  private queue: DiagnosticEventVm[] = [];
  private maxQueueSize = 200;
  private flushIntervalMs = 15_000;
  private maxBatchSize = 20;
  private sequence = 0;
  private flushTimer: ReturnType<typeof setInterval> | null = null;
  private sending = false;

  constructor(
    private zone: NgZone,
    private session: DiagnosticsSessionService,
  ) {
    this.zone.runOutsideAngular(() => {
      this.flushTimer = setInterval(() => this.flush(), this.flushIntervalMs);
    });
  }

  enqueue(event: DiagnosticEventVm): void {
    // Critical → принудительный flush через 300 мс
    // При переполнении → удалить старые debug
    // Максимум 200 событий
  }

  private async flush(): Promise<void> {
    // Отправить batch через fetch() (не HttpClient!)
    // CSRF-токен из кук
    // При ошибке: exponential backoff, макс 3 попытки
  }

  private flushOnUnload(): void {
    // sendBeacon() для critical/error
    // Обрезать до ~60 KB
  }

  ngOnDestroy(): void {
    if (this.flushTimer) clearInterval(this.flushTimer);
    this.flushOnUnload();
  }
}
```

### 6.2 Параметры

| Параметр | Значение |
|----------|----------|
| Макс. очередь в памяти | 200 событий |
| Batch-интервал | 15 000 мс |
| Досрочная отправка | При накоплении 20 событий |
| Critical flush | Через 250–500 мс |
| Размер batch (обычный) | До 100 KB (fetch без keepalive) |
| Размер batch (unload) | До 60 KB (sendBeacon с keepalive) |
| Backoff при ошибках | 1с, 2с, 4с, макс 30с |
| Максимум retry | 3 попытки на batch |
| При переполнении | Удалить старые debug, сохранить critical |
| Защита логгера | При ошибке отправки → console.error, остановка |

### 6.3 Отправка в обход interceptors

```typescript
// diagnostics-queue.service.ts
private async sendBatch(events: DiagnosticEventVm[]): Promise<void> {
  const payload: DiagnosticEventBatchVm = {
    events,
    sent_at: new Date().toISOString(),
    sequence: ++this.sequence,
  };
  const response = await fetch('/bff/api/v1/diagnostics/ui-events/batch', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': this.readCsrfToken(),
    },
    credentials: 'same-origin',
    body: JSON.stringify(payload),
    // БЕЗ keepalive — размер может превысить лимит ~64 KiB
  });
  if (!response.ok) throw new Error(`Diagnostics: ${response.status}`);
}
```

**Критично:** `fetch()` используется вместо `HttpClient`, чтобы запросы НЕ проходили через `httpErrorInterceptor`. Иначе: ошибка логов → interceptor → `request_failed` → попытка логирования → ошибка → рекурсия.

---

## 7. Точки интеграции

### 7.1 DiagnosticsService — единая точка входа

```typescript
// Warehouse_frontend/src/app/core/diagnostics/diagnostics.service.ts (NEW)

@Injectable({ providedIn: 'root' })
export class DiagnosticsService {
  constructor(
    private queue: DiagnosticsQueueService,
    private session: DiagnosticsSessionService,
    private auth: AuthContextService,
    private router: Router,         // для route
  ) {}

  track(
    type: DiagnosticEventType,
    details?: Partial<DiagnosticEventDetails> & {
      draft?: OperationDraftVm;
      operationType?: string;
      errorCode?: string;
      httpStatus?: number;
      httpMethod?: string;
      httpUrl?: string;
      durationMs?: number;
    }
  ): void {
    const event: DiagnosticEventVm = {
      event_id: this.session.newDraftId(),
      event_type: type,
      occurred_at: new Date().toISOString(),
      session_id: this.session.sessionId,
      frontend_version: this.session.frontendVersion,
      tab_id: this.session.tabId,
      route: this.router.url,
      severity: this.severityFor(type),
      user_id: this.auth.authContext()?.userId,
      site_id: this.auth.authContext()?.defaultSiteId ?? undefined,
      // Контекст заполняется из details
      operation_type: details?.operationType,
      draft_id: details?.draft?.draftId,
      idempotency_key: details?.draft?.idempotencyKey,
      server_request_id: this.session.lastServerRequestId ?? undefined,
      details: { /* только указанные поля */ },
    };
    this.queue.enqueue(event);
  }

  private severityFor(type: DiagnosticEventType): DiagnosticSeverity {
    switch (type) {
      case 'unexpected_error': return 'critical';
      case 'request_failed':
      case 'response_processing_failed': return 'error';
      case 'validation_failed':
      case 'outcome_unknown':
      case 'navigation_away_with_unsaved': return 'warning';
      default: return 'info';
    }
  }
}
```

### 7.2 Карта интеграции

| Файл | Где | Событие | Что передать в details |
|------|-----|---------|----------------------|
| `operation-create-modal.component.ts` | `constructor` effect (draft получен) | `form_opened` | `draft`, `operation_type` |
| `operation-create-modal.component.ts` | `ngOnDestroy()` | `form_closed` | `draft`, `has_unsaved_changes` |
| `operation-create-modal.component.ts` | `onSubmit()` (до emit) | `submit_clicked` | `draft`, `items_count` |
| `operation-create-modal.component.ts` | `onSubmit()` (если `saveDisabledReason()`) | `validation_failed` | `draft`, `reason` |
| `operations.service.ts` | `createOperation/submitOperation` (перед HTTP) | `request_started` | `http_method`, `http_url`, `draft` |
| `operations.service.ts` | `createOperation/submitOperation` (после успеха) | `request_succeeded` | `duration_ms`, `draft`, `server_request_id` |
| `operations.service.ts` | `createOperation/submitOperation` (catch) | `outcome_unknown` / `request_failed` | `error_code`, `http_status`, `draft` |
| `http-error.interceptor.ts` | `catchError` | `request_failed` | `http_method`, `http_url`, `http_status`, `error_code`, `duration_ms` |
| `global-error-handler.ts` | `handleError` | `unexpected_error` | `stack_trace_snippet`, `route` |
| `operations-page.component.ts` | `onDraftSubmit` catch (после успешного HTTP) | `response_processing_failed` | `draft`, `error_code` |
| `operations-page.component.ts` | `ngOnDestroy` (если `hasUnsavedChanges`) | `navigation_away_with_unsaved` | `draft` |

### 7.3 HttpErrorInterceptor — исключение diagnostic endpoint

```typescript
// http-error.interceptor.ts
export const httpErrorInterceptor: HttpInterceptorFn = (req, next) => {
  // НЕ логировать ошибки diagnostic-запросов
  if (req.url.includes('/diagnostics/ui-events')) {
    return next(req);
  }
  // ... существующая логика + track(request_failed)
};
```

---

## 8. Backend контракты

### 8.1 Endpoint

```text
POST /bff/api/v1/diagnostics/ui-events/batch
Content-Type: application/json

Request: DiagnosticEventBatchVm
Response: 204 No Content
```

### 8.2 Валидация на стороне BFF

| Проверка | Ошибка |
|----------|--------|
| `events` — массив, не пустой | 400 |
| Каждый `event.event_type` — из enum | 400 |
| Размер batch ≤ 100 KB | 413 |
| Rate limit: 10 запросов/мин/сессия | 429 |

### 8.3 Таблица PostgreSQL

```sql
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

### 8.4 TTL-очистка

```sql
-- cron/pg_cron, раз в сутки
DELETE FROM diagnostics_ui_events
WHERE id IN (
    SELECT id FROM diagnostics_ui_events
    WHERE received_at < NOW() - INTERVAL '30 days'
    ORDER BY received_at
    LIMIT 20000
);
```

---

## 9. Режимы диагностики

### Базовый режим (Этап 3)

Всегда включён. 10 событий. Никакой конфигурации не требуется.

### Расширенный режим (Этап 5, не сейчас)

Будет включаться через `/bff/api/v1/diagnostics/config`. Дополнительные события: `items_changed`, `request_started` + `request_succeeded` для всех запросов (не только operations), `search_performed`, `balance_load_failed`.

### Что делаем сейчас для будущей совместимости

- `DiagnosticsService` принимает `DiagnosticEventType` — enum легко расширить
- `DiagnosticsQueueService` поддерживает приоритеты — debug-события можно будет добавлять без изменения очереди
- Конфигурационный endpoint проектируем, но **не реализуем** в этом ТЗ

---

## 10. SWARM Topology

```text
┌─────────────────────────────────────────────┐
│     SWARM Coordinator (Minimax M3)          │
│     Контракты, приёмка WP                   │
└─────────────────────────────────────────────┘
        │          │          │          │
        ▼          ▼          ▼          ▼
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│ Agent A  │ │ Agent B  │ │ Agent C  │ │ Agent D  │
│ Backend  │ │ Angular  │ │ Angular  │ │ Angular  │
│ DB+Ep    │ │ DiagSvc  │ │ Queue    │ │ Integr   │
└──────────┘ └──────────┘ └──────────┘ └──────────┘
        │          │          │          │
        └──────────┼──────────┼──────────┘
                   │          │
                   ▼          ▼
            ┌──────────────────────┐
            │  Integration Agent   │
            └──────────────────────┘
                   │
                   ▼
            ┌──────────────────────┐
            │  Agent E: E2E QA     │
            └──────────────────────┘
```

| Роль | Ответственность |
|------|----------------|
| **Coordinator** | Contract Package, приёмка |
| **Agent A** | Backend: таблица, endpoint, валидация, TTL |
| **Agent B** | Angular: DiagnosticsService + модели |
| **Agent C** | Angular: DiagnosticsQueueService + fetch-клиент |
| **Agent D** | Angular: точки интеграции (components, services, interceptors) |
| **Integration** | Слияние, сквозные тесты |
| **Agent E** | E2E + проверка событий в БД |

---

## 11. Dependency Graph

```text
              Contract Freeze (Coordinator)
                        │
        ┌───────────────┼───────────────┐
        │               │               │
        ▼               ▼               ▼
   ┌─────────┐    ┌─────────┐    ┌─────────┐
   │ Agent A │    │ Agent B │    │ Agent C │
   │ Backend │    │ DiagSvc │    │ Queue   │
   └─────────┘    └─────────┘    └─────────┘
        │               │               │
        │               └───────┬───────┘
        │                       │
        │                       ▼
        │               ┌─────────────┐
        │               │   Agent D   │
        │               │ Integration │
        │               │   Points    │
        │               └─────────────┘
        │                       │
        └───────────────────────┼────────────────
                                │
                                ▼
                       ┌──────────────────┐
                       │ Integration Agent │
                       └──────────────────┘
                                │
                                ▼
                       ┌──────────────────┐
                       │  Agent E: E2E    │
                       └──────────────────┘
```

**Зависимости:**
- Agent D ждёт Agent B (DiagnosticsService) и Agent C (QueueService)
- Agent B и Agent C независимы
- Agent A полностью независим
- Все ждут Contract Freeze

---

## 12. Work Packages

### WP-0: Contract Freeze (Coordinator)

```text
ID:            WP-0
Исполнитель:   Coordinator
Цель:          Заморозить DTO, endpoint, таблицу, точки интеграции
Зависимости:   Архитектурное ревью (заморожено)
Результат:     docs/contracts/DIAGNOSTICS_CONTRACTS.md
Содержание:
  - Полный DiagnosticEventVm DTO
  - Список из 10 событий с точными местами в коде
  - Endpoint спецификация
  - SQL DDL
  - Приоритеты событий
  - Формат batch
```

### WP-1: Backend — таблица и endpoint (Agent A)

```text
ID:            WP-1
Исполнитель:   Agent A
Репозиторий:   SyncServer/ + Warehouse_web/
Цель:          Таблица diagnostics_ui_events, BFF endpoint, TTL
Зависимости:   WP-0

Файлы (+):
  SyncServer/app/models/diagnostics.py (NEW)
  SyncServer/alembic/versions/XXXX_diagnostics_ui_events.py (NEW)
  Warehouse_web/apps/bff_api/diagnostics_views.py (NEW)
  Warehouse_web/apps/bff_api/urls.py
  Warehouse_web/apps/bff_api/tests.py (дополнить)

Изменения БД:   CREATE TABLE diagnostics_ui_events
Миграции:       Alembic (SyncServer)

Тесты:
  - POST batch → 204
  - Пустой batch → 400
  - Невалидный event_type → 400
  - Слишком большой batch → 413
  - Rate limit → 429
  - TTL-очистка
```

### WP-2: Angular — DiagnosticsService + модели (Agent B)

```text
ID:            WP-2
Исполнитель:   Agent B
Репозиторий:   Warehouse_frontend/
Цель:          DiagnosticsService с методом track(), модели событий
Зависимости:   WP-0

Файлы (+):
  Warehouse_frontend/src/app/core/diagnostics/diagnostics.models.ts (NEW)
  Warehouse_frontend/src/app/core/diagnostics/diagnostics.service.ts (NEW)
  Warehouse_frontend/src/app/core/diagnostics/diagnostics.service.spec.ts (NEW)

Интеграция:
  - Принимает DiagnosticsSessionService, AuthContextService, Router
  - Метод track(type, details?) формирует DiagnosticEventVm
  - severityFor() — маппинг type → severity
  - Не отправляет — только формирует события, передаёт в Queue

Тесты:
  - track() создаёт событие со всеми полями
  - severityFor возвращает правильный severity
  - null-safety для опционального auth-контекста
```

### WP-3: Angular — DiagnosticsQueueService (Agent C)

```text
ID:            WP-3
Исполнитель:   Agent C
Репозиторий:   Warehouse_frontend/
Цель:          Очередь в памяти, batch-отправка через fetch()
Зависимости:   WP-0 (Agent B не обязателен — можно с мок-событиями)

Файлы (+):
  Warehouse_frontend/src/app/core/diagnostics/diagnostics-queue.service.ts (NEW)
  Warehouse_frontend/src/app/core/diagnostics/diagnostics-queue.service.spec.ts (NEW)
  Warehouse_frontend/src/app/app.config.ts (register provider)

Реализация:
  - enqueue(event): добавить в очередь, проверить лимиты
  - flush(): отправить batch через fetch()
  - flushOnUnload(): sendBeacon() для critical
  - runOutsideAngular() для таймеров
  - Exponential backoff при ошибках
  - readCsrfToken() из document.cookie
  - Защита: при ошибке логгера → остановка

Тесты:
  - enqueue добавляет событие
  - При 200 событиях → overflow, debug удаляются
  - flush отправляет batch
  - flushOnUnload вызывает sendBeacon
  - Backoff после ошибки
```

### WP-4: Angular — точки интеграции (Agent D)

```text
ID:            WP-4
Исполнитель:   Agent D
Репозиторий:   Warehouse_frontend/
Цель:          Встроить diagnostics.track() во все точки
Зависимости:   WP-2 (DiagnosticsService) + WP-3 (QueueService)

Файлы (+):
  Warehouse_frontend/src/app/features/operations/components/operation-create-modal/operation-create-modal.component.ts
  Warehouse_frontend/src/app/features/operations/pages/operations-page/operations-page.component.ts
  Warehouse_frontend/src/app/core/services/operations.service.ts
  Warehouse_frontend/src/app/core/logging/http-error.interceptor.ts
  Warehouse_frontend/src/app/core/logging/global-error-handler.ts

Изменения (по файлам):
  operation-create-modal.component.ts:
    - constructor: inject DiagnosticsService
    - effect (draft получен): track('form_opened', {draft, operationType})
    - ngOnDestroy: track('form_closed', {draft, has_unsaved_changes})
    - onSubmit(): track('submit_clicked', {draft, items_count})
    - onSubmit() guard: track('validation_failed', {draft, reason})

  operations-page.component.ts:
    - ngOnDestroy: если hasUnsavedChanges → track('navigation_away_with_unsaved')
    - onDraftSubmit catch (после HTTP): track('response_processing_failed')

  operations.service.ts:
    - createOperation/submitOperation: перед HTTP → track('request_started')
    - после успеха → track('request_succeeded', {duration_ms})
    - catch outcome_unknown → track('outcome_unknown')
    - catch другие → track('request_failed')

  http-error.interceptor.ts:
    - Исключить /diagnostics/ui-events
    - Добавить track('request_failed', {...})

  global-error-handler.ts:
    - Добавить track('unexpected_error', {stack_trace_snippet})

Тесты:
  - Каждая точка генерирует правильный event_type
  - Interceptor исключает diagnostic URL
```

### WP-5: Integration (Integration Agent)

```text
ID:            WP-5
Исполнитель:   Integration Agent
Цель:          Слить WP-1..4, сквозные тесты
Зависимости:   Все WP завершены

Проверки:
  - npm run build проходит
  - python manage.py test проходит
  - python -m pytest (SyncServer) проходит
  - Миграции применяются
  - Сквозной тест: track → queue → fetch → BFF → DB
```

### WP-6: E2E QA (Agent E)

```text
ID:            WP-6
Исполнитель:   Agent E
Цель:          Проверить события в БД после пользовательских сценариев
Зависимости:   WP-5

Сценарии:
  - Открыть модал → form_opened в БД
  - Нажать Submit с ошибкой валидации → validation_failed в БД
  - Успешный submit → submit_clicked + request_succeeded в БД
  - Таймаут → outcome_unknown в БД
  - Ошибка сети → request_failed в БД
  - Закрыть модал → form_closed в БД
  - Перейти на другую страницу с несохранённым → navigation_away_with_unsaved
```

---

## 13. File Ownership Matrix

| Файл | Agent A | Agent B | Agent C | Agent D | Conflict? |
|------|---------|---------|---------|---------|-----------|
| `SyncServer/app/models/diagnostics.py` | ✅ | - | - | - | No |
| `SyncServer/alembic/versions/*.py` | ✅ | - | - | - | No |
| `Warehouse_web/apps/bff_api/diagnostics_views.py` | ✅ | - | - | - | No |
| `Warehouse_web/apps/bff_api/urls.py` | ✅ | - | - | - | No |
| `frontend/.../diagnostics/diagnostics.models.ts` | - | ✅ | - | - | No |
| `frontend/.../diagnostics/diagnostics.service.ts` | - | ✅ | - | 🔶 | Agent B первым |
| `frontend/.../diagnostics/diagnostics-queue.service.ts` | - | - | ✅ | - | No |
| `frontend/.../app.config.ts` | - | - | ✅ | - | No |
| `frontend/.../operation-create-modal.component.ts` | - | - | - | ✅ | No |
| `frontend/.../operations-page.component.ts` | - | - | - | ✅ | No |
| `frontend/.../operations.service.ts` | - | - | - | ✅ | No |
| `frontend/.../http-error.interceptor.ts` | - | - | - | ✅ | No |
| `frontend/.../global-error-handler.ts` | - | - | - | ✅ | No |

**Конфликтов нет.** Все агенты работают в разных файлах.

---

## 14. Test Strategy

### Unit

| Тест | WP | Описание |
|------|----|--------- |
| DiagnosticsService.track создаёт событие | WP-2 | Все поля заполнены |
| DiagnosticsQueueService.enqueue при переполнении | WP-3 | debug удаляются, critical сохраняются |
| DiagnosticsQueueService.flush отправляет fetch | WP-3 | Корректный URL, заголовки, тело |
| HttpErrorInterceptor исключает diagnostic URL | WP-4 | Запрос проходит без track |
| GlobalErrorHandler.track при ошибке | WP-4 | Событие с stack trace |

### Backend Integration

| Тест | WP | Описание |
|------|----|--------- |
| POST batch → 204 | WP-1 | Валидный batch принят |
| Пустой batch → 400 | WP-1 | Валидация |
| Невалидный event_type → 400 | WP-1 | Enum validation |

### E2E

| Сценарий | WP | Проверка |
|----------|----|--------- |
| form_opened | WP-6 | Событие в БД после открытия модала |
| validation_failed | WP-6 | Событие при невалидной форме |
| submit_clicked + request_succeeded | WP-6 | Пара событий при успешном submit |
| outcome_unknown | WP-6 | Событие при таймауте |
| request_failed | WP-6 | Событие при ошибке сети |
| navigation_away_with_unsaved | WP-6 | Событие при переходе |

---

## 15. Deployment and Rollback

### Порядок

```text
1. SyncServer миграция (таблица diagnostics_ui_events)
2. Django BFF (новый endpoint)
3. Angular ( diagnostics infrastructure + integration points)
```

### Обратная совместимость

- Таблица новая — старый код её не использует ✅
- Endpoint новый — старый Angular не шлёт запросы ✅
- DiagnosticsService новый — при ошибке инициализации молча отключается ✅

### Rollback

- Откатить миграцию (DROP TABLE)
- Убрать endpoint из BFF url
- Откатить Angular сборку

---

## 16. Acceptance Criteria

1. ✅ Все 10 событий генерируются в правильных точках кода
2. ✅ События накапливаются в очереди (макс. 200)
3. ✅ Batch отправляется каждые 15 секунд
4. ✅ Critical flush через 250–500 мс
5. ✅ sendBeacon при закрытии вкладки
6. ✅ Запросы идут через `fetch()`, минуя HttpClient
7. ✅ Interceptor исключает diagnostic URL
8. ✅ Endpoint принимает batch и пишет в БД
9. ✅ Транзакционная вставка (bulk insert)
10. ✅ Таблица создана, индексы работают
11. ✅ TTL-очистка настроена
12. ✅ При ошибке логгера нет рекурсии
13. ✅ При недоступности эндпоинта приложение работает
14. ✅ Все тесты проходят
15. ✅ Redis/Celery/workers не добавлены

---

## 17. Промпты для SWARM-агентов

### Coordinator Prompt

```text
You are the SWARM Coordinator for TZ-DIAGNOSTICS_STAGE3.

READ:
- docs/archive/ARCHITECTURE_REVIEW_ANGULAR_UI_DIAGNOSTICS.md (§9-12)
- docs/TZ-DIAGNOSTICS_STAGE3_SWARM.md (this file)

Create file: docs/contracts/DIAGNOSTICS_CONTRACTS.md

MUST CONTAIN:
1. Full DiagnosticEventVm DTO with all field types
2. Complete list of 10 event types with severity, trigger location, and details payload
3. Endpoint: POST /bff/api/v1/diagnostics/ui-events/batch — request/response format
4. SQL DDL for diagnostics_ui_events table
5. Integration point map: file → method → event → details
6. Priority table: severity → flush behavior

VERIFY each file path and field against the actual codebase using grep.
DO NOT write any production code.
```

### Agent A Prompt

```text
You are Agent A: Backend Diagnostics Infrastructure (WP-1).

Repositories: SyncServer/ + Warehouse_web/

READ: docs/contracts/DIAGNOSTICS_CONTRACTS.md

TASKS:
1. Create SyncServer/app/models/diagnostics.py — DiagnosticEvent SQLAlchemy model
2. Create Alembic migration for diagnostics_ui_events table
   (DDL from contracts, indices included)
3. Create Warehouse_web/apps/bff_api/diagnostics_views.py:
   - POST /bff/api/v1/diagnostics/ui-events/batch
   - Validate event_type enum
   - Bulk insert
   - Return 204 No Content
   - Rate limit: 10 req/min/session
4. Add URL route in Warehouse_web/apps/bff_api/urls.py
5. Add tests to Warehouse_web/apps/bff_api/tests.py
6. TTL cleanup: document cron/pg_cron script

FILES (+):
- SyncServer/app/models/diagnostics.py (NEW)
- SyncServer/alembic/versions/XXXX_diagnostics_ui_events.py (NEW)
- Warehouse_web/apps/bff_api/diagnostics_views.py (NEW)
- Warehouse_web/apps/bff_api/urls.py
- Warehouse_web/apps/bff_api/tests.py

FORBIDDEN:
- Angular/ code
- Session replay, alerting, analytics
- Redis/Celery

VERIFICATION: python -m pytest + python manage.py test
```

### Agent B Prompt

```text
You are Agent B: Angular DiagnosticsService + Models (WP-2).

Repository: Warehouse_frontend/

READ: docs/contracts/DIAGNOSTICS_CONTRACTS.md

TASKS:
1. Create diagnostics.models.ts — DiagnosticEventType, DiagnosticSeverity,
   DiagnosticEventVm, DiagnosticEventDetails, DiagnosticEventBatchVm
2. Create diagnostics.service.ts:
   - @Injectable({providedIn: 'root'})
   - track(type, details?) → forms DiagnosticEventVm → passes to queue
   - severityFor(type) → DiagnosticSeverity
   - Injects: DiagnosticsQueueService (mocked for now), DiagnosticsSessionService,
     AuthContextService, Router
3. Create diagnostics.service.spec.ts:
   - test track creates event with all fields
   - test severity mapping
   - test null-safety for auth context
4. Do NOT implement queue logic — Agent C does that

EXISTING INFRASTRUCTURE (use directly):
  - DiagnosticsSessionService: sessionId, tabId, newDraftId(), frontendVersion, lastServerRequestId
  - AuthContextService.authContext(): {userId, role, defaultSiteId}
  - Router.url → current route

FILES (+):
- Warehouse_frontend/src/app/core/diagnostics/diagnostics.models.ts (NEW)
- Warehouse_frontend/src/app/core/diagnostics/diagnostics.service.ts (NEW)
- Warehouse_frontend/src/app/core/diagnostics/diagnostics.service.spec.ts (NEW)

FORBIDDEN:
- HTTP calls, fetch, HttpClient
- Queue implementation
- Integration into components (Agent D's job)

VERIFICATION: npx vitest --run src/app/core/diagnostics/diagnostics.service.spec.ts
```

### Agent C Prompt

```text
You are Agent C: Angular DiagnosticsQueueService (WP-3).

Repository: Warehouse_frontend/

READ: docs/contracts/DIAGNOSTICS_CONTRACTS.md

TASKS:
1. Create diagnostics-queue.service.ts:
   - @Injectable({providedIn: 'root'})
   - enqueue(event): add to queue, check limits
   - Max 200 events, overflow → remove old debug first
   - flush(): send batch via fetch() (NOT HttpClient)
   - fetch() with CSRF token, credentials: 'same-origin'
   - flush every 15s OR when 20 events accumulated
   - Critical events → force flush after 250-500ms
   - flushOnUnload(): sendBeacon for critical/error, max 60KB
   - All timers via NgZone.runOutsideAngular()
   - Exponential backoff: 1s, 2s, 4s, max 30s, max 3 retries
   - Self-protection: on internal error → console.error, stop

2. Create diagnostics-queue.service.spec.ts

3. Register in app.config.ts if needed

CRITICAL RULES:
  - Use fetch(), NOT HttpClient — avoids interceptor recursion
  - URL: /bff/api/v1/diagnostics/ui-events/batch
  - CSRF: read from document.cookie
  - NO keepalive on regular flush (size may exceed 64KB limit)

FILES (+):
- Warehouse_frontend/src/app/core/diagnostics/diagnostics-queue.service.ts (NEW)
- Warehouse_frontend/src/app/core/diagnostics/diagnostics-queue.service.spec.ts (NEW)
- Warehouse_frontend/src/app/app.config.ts (if registration needed)

FORBIDDEN:
- HttpClient, HttpInterceptor
- Integration into components
- IndexedDB

VERIFICATION: npx vitest --run
```

### Agent D Prompt

```text
You are Agent D: Angular Integration Points (WP-4).

Repository: Warehouse_frontend/

READ: docs/contracts/DIAGNOSTICS_CONTRACTS.md
PREREQUISITE: Agent B (DiagnosticsService) + Agent C (QueueService) complete.

TASKS:
Wire diagnostics.track() into these exact locations:

1. operation-create-modal.component.ts:
   - constructor(): inject DiagnosticsService
   - In effect where draft is received: track('form_opened', {draft, operationType: draft.type})
   - In onNgDestroy(): track('form_closed', {draft, has_unsaved_changes})
   - In onSubmit() (before emit): track('submit_clicked', {draft, items_count: draft.lines.length})
   - In onSubmit() guard: if saveDisabledReason() → track('validation_failed', {draft, reason: saveDisabledReason()})

2. operations-page.component.ts:
   - In ngOnDestroy(): if editingDraft && hasUnsavedChanges → track('navigation_away_with_unsaved', {draft: editingDraft()})
   - In onDraftSubmit catch (after successful HTTP but processing failed) → track('response_processing_failed', {draft, error_code: err.code})

3. operations.service.ts:
   - In createOperation/submitOperation: before firstValueFrom → track('request_started', {http_method: 'POST', http_url: '/operations'})
   - After successful firstValueFrom → track('request_succeeded', {duration_ms, draft})
   - In catch (operation_outcome_unknown) → track('outcome_unknown', {draft, error_code})
   - In catch (other errors) → track('request_failed', {http_status, error_code, draft})

4. http-error.interceptor.ts:
   - At TOP of interceptor: if (req.url.includes('/diagnostics/ui-events')) return next(req)
   - In catchError: track('request_failed', {http_method, http_url, http_status: error.status, error_code, duration_ms})

5. global-error-handler.ts:
   - In handleError: track('unexpected_error', {stack_trace_snippet: error.stack?.slice(0, 300), route})

FILES (+):
All 5 files listed above.

FORBIDDEN:
- Changing queue or service logic
- Backend code
- E2E tests

VERIFICATION: npx vitest --run + npm run build
```

### Integration Agent Prompt

```text
You are the Integration Agent for TZ-DIAGNOSTICS_STAGE3 (WP-5).

PREREQUISITE: WP-1, WP-2, WP-3, WP-4 complete.

TASKS:
1. Review all changes, check for conflicts
2. Run full test suites:
   - SyncServer: python -m pytest
   - Django: python manage.py test
   - Angular: npx vitest --run && npm run build
3. Apply migrations
4. Verify end-to-end: curl POST /bff/api/v1/diagnostics/ui-events/batch
5. Check that batch endpoint returns 204

DO NOT add new features or change contracts.

OUTPUT: Integration report
```

### Agent E Prompt

```text
You are Agent E: E2E QA for Diagnostics (WP-6).

PREREQUISITE: WP-5 complete.

TASKS:
Create Warehouse_frontend/e2e/diagnostics-events.spec.ts

Test scenarios:
1. form_opened: open create modal → query DB for form_opened event
2. validation_failed: submit empty form → query DB for validation_failed
3. submit_clicked + request_succeeded: successful submit → query for both events
4. outcome_unknown: simulate timeout → query for outcome_unknown
5. request_failed: simulate network error → query for request_failed
6. navigation_away_with_unsaved: add items, navigate away → query
7. form_closed: close modal → query for form_closed

For DB queries: use Django test client or direct API to check diagnostics_ui_events table.

DO NOT modify production code.

OUTPUT: Test file + results report
```

---

## Заключение

ТЗ готово к запуску SWARM. Порядок:

1. **Coordinator** — Contract Package (30 мин)
2. **Параллельно:** Agent A (backend), Agent B (DiagnosticsService), Agent C (Queue)
3. **Agent D** — точки интеграции (ждёт B и C)
4. **Integration Agent** — слияние
5. **Agent E** — E2E QA

Оценка: **3–5 часов** при параллельной работе. Конфликтов по файлам нет.
