# ADR-0016: Offline Sync Architecture

## Status
Accepted

## Date
2026-06-19

## Context

Проект Quartermaster переходит к архитектуре offline-ready. Складские терминалы работают в зонах неустойчивой связи. Офлайн-клиенты должны создавать черновики операций без интернета, синхронизироваться при появлении связи, и никогда не принимать бизнес-решения локально.

Текущее состояние:
- SyncServer имеет sync-контур: `POST /api/v1/ping`, `POST /api/v1/push`, `POST /api/v1/pull`
- Аутентификация через `X-Device-Token` + `X-User-Token`
- `events` таблица с `server_seq` (PostgreSQL IDENTITY) — sequence-based sync
- Idempotency через `event_uuid` + `payload_hash`
- Rust `Warehouse_client_core` имеет локальную SQLite, outbox, pull/push через REST
- WPF `WarehouseWorkstation` имеет собственную SQLite и прямые HTTP-клиенты (будет мигрирован на Rust core в 3.2)

Пробел: нет per-device `sync_state` трекинга на сервере, нет стандартизированной таксономии ответов, нет документально зафиксированной архитектуры офлайн-синхронизации.

## Decision

### Принципы

1. **SyncServer — единственный источник истины.** Все бизнес-правила, проверка прав, валидация остатков, подтверждение операций — на сервере.

2. **Клиент — локальный рабочий терминал с очередью событий.** Клиент кэширует справочники и остатки, создаёт draft-операции в outbox, отправляет их при появлении связи. Клиент **не принимает бизнес-решения** (не проверяет «можно ли списать», «достаточно ли остатка», «имеет ли право»).

3. **UI-валидация разрешена, бизнес-валидация — нет.** Клиент может проверить, что все поля заполнены, количество > 0, выбран существующий склад. Но финальное решение о проведении операции принимает SyncServer.

4. **Sequence-based sync (CouchDB-style).** Каждое изменение в SyncServer получает монотонный `server_seq`. Клиент хранит `last_sequence_number` и запрашивает изменения после него.

5. **Конфликты: last-write-wins в v3.1/v3.2, merge в v3.4.**

### Схема

```
Offline Client (Rust core / WPF / Mobile)
  ├─ Local SQLite (cache + outbox)
  ├─ Outbox events
  └─ /ping  ──→  heartbeat + server_seq_upto
     /pull  ──→  изменения после last_seq
     /push  ──→  локальные изменения
           ↓
SyncServer (FastAPI + PostgreSQL)
  ├─ events (server_seq IDENTITY)
  ├─ sync_state (per-device tracking)
  └─ Business rules enforcement
```

### Таксономия ответов push

| Результат | Условие | Действие клиента |
|-----------|--------|-----------------|
| `accepted` | Событие новое, применено успешно | Удалить из outbox, обновить курсор |
| `duplicate` | Такой же event_uuid + payload_hash уже есть | Удалить из outbox (уже применено) |
| `rejected` | Бизнес-правило нарушено (нет прав, нет остатка, ТМЦ деактивирована) | Показать ошибку пользователю, удалить из outbox |
| `conflict` | Event_uuid совпал, payload отличается | Показать конфликт, пользователь решает |
| `validation_error` | Некорректный payload (отсутствуют поля, неверные типы) | Исправить данные, переотправить |
| `auth_error` | Невалидный токен, недостаточно прав | Обновить токен, переотправить |

### sync_state таблица (SyncServer)

```sql
CREATE TABLE sync_state (
    id SERIAL PRIMARY KEY,
    device_id INTEGER UNIQUE NOT NULL REFERENCES devices(id),
    last_sequence_number BIGINT DEFAULT 0,
    last_sync_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR(32) DEFAULT 'unknown',  -- online, offline, error
    last_error TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);
```

### Эндпоинт статуса

```
GET /api/v1/sync/status/{device_id}

Response:
{
  "device_id": 1,
  "last_sequence_number": 1042,
  "last_sync_at": "2026-06-19T10:30:00Z",
  "status": "online",
  "server_seq_upto": 1050,
  "behind_by": 8
}
```

## Consequences

- Офлайн-клиенты получают стандартизированный контракт синхронизации.
- Сервер знает состояние каждого устройства (позиция, отставание, статус).
- Таксономия ответов даёт клиентам детерминированное поведение для каждого исхода.
- Бизнес-логика остаётся на сервере — локальный SQLite не становится «второй истиной».
- Существующие sync-эндпоинты (`/ping`, `/push`, `/pull`) сохраняются, дополняются `sync_state`.

## Confidence
**High** — sync-контур уже работает (18 тестов), добавляется только per-device tracking и таксономия.
