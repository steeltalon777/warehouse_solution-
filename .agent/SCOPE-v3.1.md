# Scope: Warehouse Solution v3.1

**Date:** 2026-06-18
**Decision Makers:** makc

## Problem

После стабилизации онлайн-клиента (v3.0) необходимо заложить foundation для офлайн-клиентов. 
Склады находятся в зоне неустойчивой связи — кладовщики должны работать без интернета, 
создавать операции и синхронизироваться при появлении связи. 
SyncServer должен отслеживать состояние синхронизации каждого клиента.

Параллельно: доработать админку Django для полноценного управления устройствами (CRUD + статус).

## In Scope

### 1. Sync Log & Protocol (SyncServer)
- Таблица `sync_state` (device_id, last_sequence_number, last_sync_at, status)
- Sequence-based sync: каждый mutation в SyncServer получает монотонный sequence number
- API: `POST /api/v1/sync/push` — клиент отправляет локальные изменения
- API: `POST /api/v1/sync/pull` — клиент запрашивает изменения после своего sequence
- Outbox на клиенте: локальные изменения копятся и отправляются пачкой

### 2. Device Management (Django Admin)
- CRUD устройств в Django admin (code, name, site, тип: online/offline)
- Статус устройства: online/offline, last_seen, last_sync, health
- Синхронизация устройств с SyncServer (создание/обновление)
- Отображение токена устройства для копирования в offline-клиент

### 3. Warehouse Client Core (Rust)
- Локальная SQLite-схема: catalog, operations (drafts), balances snapshot
- Sync client: pull (sequence-based) + push (outbox)
- DTO-маппинг: SyncServer JSON ↔ локальные Rust-структуры
- CLI для smoke-проверок sync

### 4. Roadmap & Docs Update
- `SOLUTION_ROADMAP.md` — отметить выполненные этапы, добавить 3.1
- `Functional and WorkLogik.md` — актуализировать статусы

## Out Of Scope

- Desktop UI (WPF/Avalonia) — решается после v3.1
- Mobile UI (Android) — решается после v3.1
- Полный conflict resolution UI — фокус на протоколе, не на интерфейсе
- Отчёты по логам синхронизации — возможно позже, не блокирует v3.1
- Real-time push-уведомления
- WarehouseAIWorkstation

## Success Criteria

1. SyncServer: sequence-based sync работает, offline-клиент получает изменения после своего last_seq
2. SyncServer: клиент может запушить локально созданную операцию, она применяется
3. Django admin: CRUD устройств работает, статус отображается
4. Rust core: SQLite-схема создаётся, pull/push через CLI smoke-test проходит

## Assumptions

| Assumption | Status | Validation |
|---|---|---|
| Sequence number — единый глобальный счётчик на все таблицы | Reasonable | Прототип покажет, нужен ли per-table sequence |
| SQLite в Rust покрывает catalog + operations + balances без проблем | Reasonable | Схема < 20 таблиц, SQLite справляется |
| Конфликты (два клиента изменили одно и то же) — last-write-wins в v3.1 | Reasonable | Спроектировать так, чтобы позже добавить merge |
| SyncServer и так хранит все данные — sync_state это лёгкая таблица | Validated | Все CRUD уже есть, нужен только sequence + sync_state |

## Selected Approach

**Sequence-based sync (CouchDB-style):**
- Каждый INSERT/UPDATE/DELETE в SyncServer получает глобальный `sequence_number`
- Клиент хранит `last_sequence_number` — последний seq, который он получил
- Pull: `GET /sync/pull?since={seq}` → JSON с изменениями + новый seq
- Push: `POST /sync/push` → JSON с локальными изменениями → сервер валидирует и применяет
- Конфликты: last-write-wins (позже добавим merge)

## First Slice

1. **SyncServer:** `sync_state` таблица + `sequence_number` в основных таблицах + pull API (только чтение)
2. **Django admin:** CRUD устройств
3. **Rust core:** SQLite-схема + pull-клиент + CLI smoke (`warehouse-cli sync pull`)

## Next Step

Создать TZ в Architect mode после утверждения scope.
