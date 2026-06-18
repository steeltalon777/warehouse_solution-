# Дорожная карта решения

> Последнее обновление: 2026-06-18 (v3.1 planning)

## ✅ Этап 1: Контракты агентов и документации (выполнено)

- Корневой `AGENTS.md` + проектные `AGENTS.md` во всех активных проектах.
- Активная документация в соответствии с текущими ролями проектов.
- `docs/DEPLOYMENT.md` — правила деплоя.
- Сгенерированные артефакты в `temp/`, не в git.

## ✅ Этап 2: Стабильность backend-контракта (выполнено)

- SyncServer: 410 тестов, 0 failed, 2 skipped, 7 xfailed.
- Миграции Alembic до 0018, явные и проверенные.
- ADR'ы: 0011 (transport), 0013 (migration hardening), 0014 (read visibility).
- API-контракты в `API_REFERENCE.md`.

## ✅ Этап 3: Django как активный web-клиент и BFF (выполнено)

- Django BFF: `/bff/api/v1/*` проксирует все доменные endpoint'ы.
- Транспорт: persistent HTTPX, retry, error mapping, токены не раскрываются.
- Каталог: локальные ORM-модели удалены, всё через `apps/sync_client/`.
- Аудит: login/logout события из Django в SyncServer.

## ✅ Этап 4: Angular SPA shell (выполнено)

- Angular workspace в `Warehouse_frontend/`.
- SPA-экраны: номенклатура, операции, выданное имущество, временные ТМЦ.
- Хостинг через Django: `FRONTEND_MODE=build`, Angular-статика в `Warehouse_web/angular_static/`.
- Django shell (topbar, sidebar, login) постоянный, Angular — в content area.

## 🚧 Этап 5: Warehouse Client Core (v3.1 — в работе)

- [x] Rust workspace создан (`crates/warehouse_core`, `warehouse_ffi`, `warehouse_cli`).
- [ ] Sync-протокол: sequence-based (CouchDB-style) — `sync_state` таблица, pull/push API.
- [ ] Локальная SQLite-схема: catalog, operations, balances.
- [ ] DTO-маппинг: SyncServer JSON ↔ Rust-структуры.
- [ ] CLI smoke-test: pull/push через `warehouse-cli`.
- [ ] Outbox-паттерн для локальных изменений.
- См. `.agent/SCOPE-v3.1.md`.

### v3.1: Sync Log (SyncServer)
- Таблица `sync_state` (device_id, last_seq, last_sync_at, status).
- `sequence_number` в основных таблицах — монотонный счётчик изменений.
- API: `POST /sync/push`, `POST /sync/pull`.

### v3.1: Device Management (Django Admin)
- CRUD устройств + статус (online/offline, last_seen, health).
- Синхронизация устройств с SyncServer.

## ⏳ Этап 6: Пересборка offline-клиентов (после v3.1)

- Пересобрать UI `WarehouseDesktop` вокруг `Warehouse_client_core`.
- Пересобрать UI `WarehouseMobile` вокруг `Warehouse_client_core`.
- Платформенно-специфичные части вне core: UI, secure storage, scanner/camera, scheduling.

## На паузе

- `WarehouseAIWorkstation` — до явного возобновления.
