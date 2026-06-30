# Scope: Quartermaster v3.1 — Branding & Offline Readiness

**Date:** 2026-06-19
**Decision Makers:** makc
**Review:** ChatGPT (parallel architecture review), Architect (audit + stress-test)

## Goal

> Превратить «Склад» в продукт **«Quartermaster»**, стабилизировать серверный контракт офлайн-синхронизации, подтвердить совместимость Rust client core с SyncServer и подготовить WPF к миграции без включения полной миграции в релиз 3.1.

v3.1 — **НЕ релиз офлайн-клиентов.** Это подготовка к ним: offline-ready server + Rust core gate + WPF FFI spike.

---

## Status

| Компонент | Статус |
|-----------|--------|
| 3.1A Branding: Quartermaster | ✅ ADR-0015, README/docs обновлены |
| 3.1B SyncServer: sync_state + device status | ✅ sync_state table, `GET /sync/status/{device_id}`, ping/pull/push updates, migration 0019 |
| 3.1C Rust Core: payload_hash + compatibility | ✅ payload_hash canonical JSON+SHA-256, write_operations documented, stand smoke passes |
| 3.1D WPF: Layer 0 FFI spike | 🚧 |
| 3.1E Documentation | 🚧 ADR созданы, Stage 5 в работе |

sync_state, device status (online/offline/health), и payload_hash (canonical JSON + SHA-256) — реализованы и протестированы.

---

## In Scope

### 3.1A — Branding: Quartermaster ✅

- ✅ Продуктовое имя: **Quartermaster** (складской фреймворк/WMS).
- ✅ Внутренние имена репозиториев, пакетов, сервисов, БД — **без изменений**.
- ✅ Организации кастомизируют заголовки и логотипы самостоятельно — продукт даёт имя и identity, а не жёсткий брендбук.
- ✅ Что обновить:
  - ✅ `README.md` (корень workspace) — название, описание проекта
  - ✅ `SOLUTION_ROADMAP.md` — упоминание Quartermaster
  - ✅ `Functional and WorkLogik.md` — мета-описание
  - ✅ `docs/INDEX.md`, `docs/ARCHITECTURE.md` — если существуют
  - ✅ Проектные README: `SyncServer/`, `Warehouse_web/`, `Warehouse_frontend/`, `Warehouse_client_core/`, `WarehouseWorkstation/`
- ✅ **ADR-0015:** Product name and branding

### 3.1B — SyncServer: Offline Contract & Status ✅

- ✅ **`sync_state` таблица:** device_id, last_sequence_number, last_sync_at, status, last_error
- ✅ **Эндпоинт:** `GET /api/v1/sync/status/{device_id}` → behind_by, online/offline derivation
- ✅ **Обновление в ping/pull/push:** last_sync_at, last_sequence_number
- ✅ **Device.last_seen_at:** убедиться, что обновляется в sync-эндпоинтах (identity_service уже делает — проверить)
- ✅ **Таксономия ответов:** accepted, duplicate, rejected, conflict, validation_error, auth_error (частично уже есть — дополнить)
- ✅ **Миграция:** `0019_add_sync_state`
- ✅ **ADR-0016:** Offline sync architecture

### 3.1C — Rust Core: Compatibility Gate ✅

- ✅ **payload_hash:** совместимость с SyncServer (canonical JSON + SHA-256)
- ✅ **Stand smoke test:** Core ↔ SyncServer (bootstrap → push → pull) — последний незакрытый decision gate из MIGRATION_ANALYSIS
- **Release DLL:** сборка `warehouse_ffi.dll` / `.so` для целевых платформ
- ✅ **CLI acceptance:** `warehouse-cli sync full` проходит на Docker-стенде

### 3.1D — WPF: Layer 0 FFI Spike (tech preview)

- **Только Layer 0:** C# `CoreHandle` SafeHandle wrapper, `CoreErrorDto`, загрузка DLL
- **Smoke test:** `core_version()`, `core_open()`, `core_close()` — WPF может вызвать Rust core
- **Документ:** `WPF_RUST_CORE_MIGRATION_PLAN.md` (или обновить существующий `MIGRATION_AIWORKSTATION_TO_CORE_ANALYSIS.md`)
- **НЕ входит:** Layers 1-7 (Bootstrap, Auth, Directory, Operations, Balances, Documents, Sync, Cleanup) → 3.2
- **ADR-0017:** WPF migration via Rust core

### 3.1E — Documentation 🚧 (Stage 5 в работе)

- 🚧 `SOLUTION_ROADMAP.md` — этап 5 выполнен, v3.1
- 🚧 `Functional and WorkLogik.md` — разделы IX.11, X
- ✅ `README.md` (корень) — Quartermaster
- ✅ Проектные README — упоминание продукта
- ✅ `docs/INDEX.md`, `docs/ARCHITECTURE.md` — актуализация
- ✅ ADR-0015, ADR-0016, ADR-0017

---

## Out Of Scope (→ 3.2, 3.3, 3.4)

| Что | Когда |
|-----|-------|
| WPF Layers 1-7 (полная миграция на Rust core) | 3.2 |
| Android-клиент | 3.3 |
| Desktop UI (новый) | 3.2 |
| Mobile UI (новый) | 3.3 |
| Полный conflict resolution (merge) | 3.4 |
| Печать, QR/штрихкоды, сканы | 3.4 |
| Real-time push-уведомления | — |
| WarehouseAIWorkstation (AI-функционал) | На паузе |
| Переименование репозиториев/пакетов/БД | Никогда |

---

## Версионная дорожка

```
v3.0  — онлайн-клиент (SyncServer + Django + Angular)
v3.1  — Quartermaster + offline-ready server + Rust core gate + WPF FFI spike
v3.2  — WPF migration to Rust core (Layers 1-7)
v3.3  — Android client (Kotlin/UniFFI)
v3.4  — advanced offline UX, conflicts, QR/scans, printing
```

---

## Success Criteria

1. Продукт называется Quartermaster во всей документации и README
2. SyncServer: `sync_state` таблица, `GET /sync/status/{device_id}`, таксономия ответов
3. Rust core: `payload_hash` совместим, stand smoke проходит, release DLL собирается
4. WPF: C# FFI wrapper загружает DLL, вызывает `core_version()` / `core_open()` / `core_close()`
5. 3 новых ADR, документация актуализирована
6. Регрессия: существующие тесты (SyncServer 410+, WPF 117, Rust ~90) проходят

---

## Next Step

Создать TZ в Architect mode: `docs/TZ-V3.1_QWARTERMAISTER.md`
