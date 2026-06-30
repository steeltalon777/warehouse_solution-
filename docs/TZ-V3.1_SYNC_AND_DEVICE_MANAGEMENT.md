# TZ: Warehouse Solution v3.1 — Sync Protocol & Device Management

**Date:** 2026-06-19
**Based on:** `.agent/SCOPE-v3.1.md`, аудит кода от 2026-06-19, архитектурное ревью от 2026-06-19
**Status:** Ready (архитектурное ревью пройдено, правки внесены)

## Execution Strategy

- [x] 🟡 Sequential execution recommended
- **Reason:** Stage 1 (SyncServer) must complete before Stage 2 (Django surfaces data from SyncServer). Stage 3 (Rust) is independent but integration tests in Stage 4 require all three. Stage 5 (docs) is last.

---

## Execution Checklist

- [ ] 0. Context verified — аудит кода выполнен, пробелы идентифицированы
- [ ] 1. Stage 1: SyncServer — sync_state + hardening
- [ ] 2. Stage 1 tests: unit + integration
- [ ] 3. Stage 2: Django — device runtime status
- [ ] 4. Stage 2 tests: unit + stand smoke
- [ ] 5. Stage 3: Warehouse_client_core — fix gaps
- [ ] 6. Stage 3 tests: cargo test + cargo clippy
- [ ] 7. Stage 4: Integration — E2E sync flow
- [ ] 8. Stage 5: Documentation update
- [ ] 9. Regression checks: SyncServer 410 tests, Django tests
- [ ] 10. Final acceptance review

---

## Результаты аудита (контекст)

Аудит 2026-06-19 выявил:

### Что уже работает
| Компонент | Статус |
|-----------|--------|
| SyncServer `push`/`pull`/`ping` API | ✅ 18 тестов, idempotency, PostgreSQL IDENTITY seq |
| SyncServer `Device` модель с `last_seen_at` | ✅ Обновляется в `identity_service` при каждом auth-запросе |
| Django `SyncDeviceBinding` — CRUD + token rotation | ✅ Админка, BFF API, repair |
| Rust sync engine — bootstrap, pull (12+ families), outbox | ✅ Через REST-эндпоинты |
| Rust SQLite-схема — 8 миграций, 22+ таблиц | ✅ |
| Rust CLI — 30+ команд | ✅ |
| Rust FFI — 48 C-экспортов | ✅ |

### Критические пробелы
| # | Пробел | Где | Серьёзность |
|---|--------|-----|-------------|
| G1 | Нет таблицы `sync_state` | SyncServer | 🔴 Блокирует per-device tracking |
| G2 | `write_operations()` — осознанный no-op | Rust `snapshot_writer.rs:299` | 🔵 Архитектурное решение: подтверждённые операции проксируются с SyncServer API, не кэшируются локально |
| G3 | Нет online/offline статуса устройств | Django admin | 🟡 Нет runtime-видимости |
| G4 | `last_seen_at` не зеркалируется в Django | Django `DeviceSyncService` | 🟡 Данные есть, но не показываются |
| G5 | Нет health-статуса устройств | Django | 🟡 Неясно, здорово ли устройство |
| G6 | `/push` и `/ping` — dead code в Rust | Rust `device_sync.rs` | 🔵 Определены, но не используются (ADR-0008 Phase 2 — вне scope v3.1) |
| G7 | Нет E2E интеграционных тестов sync | Все проекты | 🟡 Риск регрессий |
| G8 | `sha256_simple` — не SHA-256, несовместим с SyncServer `payload_hash` | Rust `outbox_service.rs` | 🟡 При переходе на Phase 2 хэши не совпадут |

---

## Stage 1: SyncServer — sync_state + hardening

### Входные данные
- `events` таблица с `server_seq` (BIGINT IDENTITY) — работает
- `devices` таблица с `last_seen_at` — обновляется в `identity_service`
- `push`/`pull`/`ping` эндпоинты — работают

### Задача 1.1: Создать таблицу `sync_state`

**Файлы:**
- `SyncServer/app/models/sync_state.py` — новая модель
- `SyncServer/alembic/versions/0019_add_sync_state.py` — новая миграция

**Модель:**
```python
class SyncState(Base):
    __tablename__ = "sync_state"

    id: Mapped[int] = primary key, autoincrement
    device_id: Mapped[int] = FK → devices.id, unique
    last_sequence_number: Mapped[int] = BigInteger, default 0
    last_sync_at: Mapped[datetime | None] = DateTime(timezone=True)
    status: Mapped[str] = String(32), default "unknown"  # unknown, online, offline, error
    last_error: Mapped[str | None] = Text
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
```

**Индексы:** `device_id` (unique), `status`

### Задача 1.2: Обновить sync-эндпоинты для работы с sync_state

**Файлы:**
- `SyncServer/app/api/routes_sync.py`
- `SyncServer/app/services/sync_service.py`
- `SyncServer/app/repos/sync_state_repo.py` — новый репозиторий

**Изменения в `ping`:**
- После получения `last_server_seq` от клиента → upsert в `sync_state`:
  - `last_sequence_number = max(текущий, client.last_server_seq)`
  - `last_sync_at = now()`
  - `status = "online"`
- Возвращать `backoff_seconds` > 0 при высокой нагрузке (опционально, можно отложить)

**Изменения в `pull`:**
- После успешного pull → обновить `sync_state.last_sequence_number = max(текущий, выданный next_since_seq)`
- Обновить `sync_state.last_sync_at = now()`

**Изменения в `push`:**
- После успешного push → обновить `sync_state.last_sync_at = now()`

### Задача 1.3: Добавить эндпоинт статуса синхронизации устройства

**Файлы:**
- `SyncServer/app/api/routes_sync.py` — новый route
- `SyncServer/app/schemas/sync.py` — новая схема

**Новый эндпоинт:**
```
GET /api/v1/sync/status/{device_id}
```
Возвращает:
```json
{
  "device_id": 1,
  "last_sequence_number": 1042,
  "last_sync_at": "2026-06-19T10:30:00Z",
  "status": "online",
  "server_seq_upto": 1050,
  "behind_by": 8
}
```

**Авторизация:** `X-Device-Token` + `X-User-Token` (admin/root для чужих устройств, своё устройство может смотреть свой статус)

### Задача 1.4: Обновить Device.last_seen_at в sync-эндпоинтах

**Текущее состояние:** `last_seen_at` обновляется в `identity_service.resolve_identity()` при каждой auth-проверке — это покрывает все sync-эндпоинты, так как все они требуют device-auth.

**Задача:** Убедиться, что `ping` явно форсирует обновление `last_seen_at` (если identity_service уже делает это — просто документировать). Проверить: при вызове `ping` без user-token (только device-token) — обновляется ли `last_seen_at`?

### Тесты Stage 1

- [ ] Unit-тесты `SyncStateRepo`: create, upsert, get by device_id
- [ ] Интеграционные тесты `ping`: после ping — sync_state создан/обновлён, last_seen_at обновлён
- [ ] Интеграционные тесты `pull`: после pull — last_sequence_number обновлён
- [ ] Интеграционные тесты `push`: после push — last_sync_at обновлён
- [ ] Интеграционные тесты `GET /sync/status/{device_id}`: корректные behind_by, status
- [ ] Миграция: `alembic upgrade head` проходит без ошибок

**Команда:** `cd SyncServer && python -m pytest tests/test_sync_state.py tests/test_http_sync.py -v`

---

## Stage 2: Django — device runtime status

### Задача 2.1: Добавить поля в SyncDeviceBinding

**Файлы:**
- `Warehouse_web/apps/users/models.py`
- `Warehouse_web/apps/users/migrations/0006_add_device_status_fields.py`

**Новые поля:**
```python
last_seen_at = models.DateTimeField(null=True, blank=True)
sync_state_status = models.CharField(max_length=32, null=True, blank=True)  # online/offline/unknown/error
sync_state_last_seq = models.BigIntegerField(null=True, blank=True)
sync_state_behind_by = models.IntegerField(null=True, blank=True)
health_status = models.CharField(max_length=32, default="unknown")  # healthy/degraded/unhealthy/unknown
```

### Задача 2.2: Обновить DeviceSyncService для получения статуса

**Файлы:**
- `Warehouse_web/apps/users/services.py`
- `Warehouse_web/apps/sync_client/admin_api.py`

**Изменения:**
- Добавить метод `fetch_device_sync_status(device_id)` — вызывает `GET /api/v1/sync/status/{device_id}` из SyncServer
- В `apply_remote_state()` — копировать `last_seen_at` из ответа SyncServer (поле уже есть в `DeviceResponse`, но не мапилось)
- Добавить `refresh_device_status()` — получает sync_state из SyncServer и вычисляет online/offline:
  - Порог online/offline: конфигурируемый через `settings.SYNC_ONLINE_THRESHOLD_SECONDS` (по умолчанию 300 = 5 минут)
  - `online`: `last_seen_at` в пределах порога
  - `offline`: `last_seen_at` старше порога или null
  - `health`: healthy (если behind_by < 50), degraded (50-200), unhealthy (>200 или error)
- Статус сохраняется в поля модели (`sync_state_status`, `last_seen_at`, `health_status`), а не вычисляется на лету в list_display

### Задача 2.3: Обновить Django Admin

**Файлы:**
- `Warehouse_web/apps/users/admin.py`

**Изменения в `SyncDeviceBindingAdmin`:**
- `list_display` добавить: `online_status_badge`, `last_seen_at`, `health_status`
- `readonly_fields` добавить: `last_seen_at`, `sync_state_status`, `sync_state_last_seq`, `sync_state_behind_by`, `health_status`
- `online_status_badge`: читает кэшированное поле `sync_state_status` (НЕ вызывает refresh). Обновление статуса — только через admin action
- Добавить action «Refresh device status» — вызывает `DeviceSyncService.refresh_device_status()` для выбранных устройств
- Добавить colour-coded badge для online/offline (зелёный/красный) на основе `sync_state_status`

### Задача 2.4: BFF — эндпоинт статуса устройства

**Файлы:**
- `Warehouse_web/apps/bff_api/admin_views.py`
- `Warehouse_web/apps/bff_api/urls.py`

**Новый эндпоинт:**
```
POST /api/bff/admin/devices/<device_id>/refresh-status
GET  /api/bff/admin/devices/<device_id>/status
```

### Тесты Stage 2

- [ ] Unit-тесты: `DeviceSyncService.refresh_device_status()` — online/offline/health-логика
- [ ] Django-тесты: миграция применяется, модель содержит новые поля
- [ ] Stand smoke: админка показывает online/offline badge для устройства
- [ ] Stand smoke: BFF `/status` возвращает корректный статус

**Команда:** `cd Warehouse_web && python manage.py test apps.users.tests`

---

## Stage 3: Warehouse_client_core — fix gaps

### Задача 3.1: Документировать архитектурное решение по write_operations

**Файл:**
- `Warehouse_client_core/crates/warehouse_core/src/storage/snapshot_writer.rs`

**Текущее состояние (строка 299-302):**
```rust
pub async fn write_operations(&self, ops: &[OperationListItem]) -> CoreResult<()> {
    let _ = ops;
    Ok(())
}
```

**Решение (подтверждено архитектурным ревью):**
- `write_operations` — осознанный **no-op**. Подтверждённые операции не кэшируются в локальной SQLite, а проксируются напрямую с SyncServer API.
- `CoreHandle::list_operations()` (facade/mod.rs) вызывает `client.operations_list()` напрямую.
- Локально хранятся только **черновики** (`operation_drafts`), которые создаются офлайн.
- Кэширование подтверждённых операций потребовало бы создания таблицы `operations_cache` и политики инвалидации без ясного offline-сценария использования.

**Действие:**
- Добавить комментарий над методом с объяснением: «Confirmed operations are proxied from SyncServer API; local SQLite stores only drafts. See ADR-0008 Phase 1.»
- Убрать G2 из списка критических пробелов.

### Задача 3.2: Wire up /push как альтернативный транспорт (опционально, Phase 2)

**Файлы:**
- `Warehouse_client_core/crates/warehouse_core/src/operations/outbox_service.rs`
- `Warehouse_client_core/crates/warehouse_core/src/syncserver/device_sync.rs`

**Согласно ADR-0008:** Phase 1 (user-token REST) — текущий подход, работает. Phase 2 (device push) — опционально.

**Решение для v3.1:** Оставить Phase 1 (REST через `/operations`) как primary транспорт. Device push (`/api/v1/push`) остаётся определённым, но не обязательным для v3.1. **Не блокирует v3.1.**

Если останется время — добавить feature-флаг `use_device_push` в конфигурацию и реализовать `DevicePushTransport`.

### Задача 3.3: Исправить sha256_simple → payload_hash (совместимость с SyncServer)

**Файл:**
- `Warehouse_client_core/crates/warehouse_core/src/operations/outbox_service.rs`

**Проблема:** 
1. Функция `sha256_simple` использует `std::hash::DefaultHasher` (SipHash), а не SHA-256.
2. SyncServer вычисляет `payload_hash` через **canonical JSON + SHA-256** (`app/services/event_ingest.py`). При переходе на Phase 2 (device push) хэши не совпадут.

**Исправление:**
- Добавить `sha2` crate в зависимости `warehouse_core`
- Реализовать `compute_payload_hash(json: &str) -> String`:
  1. Десериализовать JSON → `serde_json::Value`
  2. Ресериализовать с сортировкой ключей: `serde_json::to_string(&value)` 
  3. Вычислить SHA-256: `sha2::Sha256::digest(canonical_bytes)`
  4. Вернуть hex-строку (нижний регистр)
- **Критично:** формат должен совпадать с SyncServer: `hashlib.sha256(canonical_json).hexdigest()`
- Удалить старую функцию `sha256_simple`

**Тест совместимости:**
- Одинаковый JSON на Rust и Python → одинаковый `payload_hash`
- Эталонные значения: зафиксировать в тесте несколько известных пар (input → expected_hash)

### Задача 3.4: Добавить sync_state tracking на клиенте

**Файлы:**
- `Warehouse_client_core/crates/warehouse_core/src/sync/pull.rs`
- `Warehouse_client_core/crates/warehouse_core/src/sync/engine.rs`

**Требуется:**
- После каждого успешного pull — сохранять `server_seq_upto` в локальную `sync_cursors` таблицу (уже существует!)
- После каждого успешного push — обновлять локальный курсор
- Использовать `ping` для получения актуального `server_seq_upto` и проверки отставания

**Проверить:** `sync_cursors` таблица уже существует в SQLite-схеме и `SyncCursorRepo` реализован. Нужно убедиться, что engine реально сохраняет курсор после pull.

### Тесты Stage 3

- [ ] `cargo fmt --all -- --check`
- [ ] `cargo clippy --workspace --all-targets -- -D warnings`
- [ ] `cargo test --workspace` — все существующие тесты проходят
- [ ] Новый тест: `payload_hash` совместим с SyncServer (одинаковый хэш для одинакового JSON в Rust и Python)
- [ ] Проверка: комментарий в `snapshot_writer.rs:299` документирует причину no-op

**Команда:** `cd Warehouse_client_core && cargo test --workspace`

---

## Stage 4: Integration — E2E sync flow

### Задача 4.1: E2E тест bootstrap → push → pull

**Файл:**
- `Warehouse_client_core/tests/e2e_sync_test.rs` (новый)

**Сценарий:**
1. Запустить SyncServer (реальный или docker)
2. Создать устройство через `POST /admin/devices`
3. Bootstrap: `warehouse-cli sync bootstrap` → проверить, что catalog/balances загружены в SQLite
4. Создать черновик операции: `warehouse-cli draft create ...`
5. Push: `warehouse-cli sync push` → проверить, что операция появилась в SyncServer
6. Pull: `warehouse-cli sync pull` → проверить, что операция появилась в локальной БД
7. Проверить `sync_state` на сервере: `GET /api/v1/sync/status/{device_id}` → behind_by = 0

**Инфраструктура:**
- Использовать Docker test stand
- Или `#[cfg(feature = "e2e")]` с пропуском при отсутствии стенда

### Задача 4.2: Stand smoke test

**Стенд:** Docker compose из корня workspace

**Smoke-команды:**
```bash
# Проверить sync_state эндпоинт
curl -s http://localhost:8000/api/v1/sync/status/1

# Проверить ping с dev-устройством
curl -s -X POST http://localhost:8000/api/v1/ping \
  -H "X-Device-Token: $SYNC_DEVICE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"site_id": 1, "device_id": 1, "last_server_seq": 0}'

# Проверить Django device status
curl -s http://localhost:8001/api/bff/admin/devices/1/status
```

### Тесты Stage 4

- [ ] E2E сценарий проходит на Docker-стенде
- [ ] После push — sync_state обновлён на сервере
- [ ] После pull — behind_by = 0
- [ ] Django admin показывает online статус устройства

---

## Stage 5: Documentation update

### Задача 5.1: Обновить SOLUTION_ROADMAP.md

- Отметить выполненные пункты Этапа 5
- Обновить статус v3.1

### Задача 5.2: Обновить Functional and WorkLogik.md

- Раздел IX пункт 11: сменить статус с «на стадии продумывания (v3.1)» на «выполнено»
- Раздел X: обновить статус синхронизации

### Задача 5.3: Обновить .agent/SCOPE-v3.1.md

- Добавить отметки о выполнении

### Задача 5.4: Создать ADR-0015 (опционально)

Если изменения существенны — зафиксировать решения по sync_state и device status в ADR.

---

## Границы (Out of Scope)

- Desktop UI (WPF/Avalonia)
- Mobile UI (Android)
- Полный conflict resolution UI
- Real-time push-уведомления
- WarehouseAIWorkstation
- Device push (Phase 2 ADR-0008) — опционально, не блокирует v3.1

---

## Критерии приёмки

1. **SyncServer:** `sync_state` таблица создана, ping/pull/push обновляют её, `GET /sync/status/{device_id}` работает
2. **Django:** admin показывает online/offline badge + last_seen + health, BFF `/status` работает
3. **Rust:** `write_operations()` реализован, `payload_hash` исправлен, тесты проходят
4. **E2E:** полный цикл bootstrap → push → pull отрабатывает на стенде
5. **Документация:** ROADMAP, SCOPE, Functional and WorkLogik актуализированы
6. **Регрессия:** существующие тесты SyncServer (410+) и Django проходят без деградации

---

## Оценка трудозатрат

| Stage | Часы (оценка) | Комментарий |
|-------|---------------|-------------|
| 1. SyncServer | 3-4 | Модель + миграция + обновление 3 эндпоинтов + тесты |
| 2. Django | 2-3 | Модель + миграция + сервис + админка + BFF |
| 3. Rust | 2-3 | write_operations + payload_hash + sync_state tracking |
| 4. E2E | 2-3 | Сценарий + отладка |
| 5. Docs | 0.5-1 | Обновление markdown |
| **Итого** | **10-14** | |

---

## Риски

| Риск | Вероятность | Смягчение |
|------|-------------|-----------|
| Rust `write_operations` требует перепроектирования схемы | Средняя | Проверить существующую схему перед реализацией |
| `payload_hash` несовместим с SyncServer (разная канонизация JSON) | Средняя | Использовать `serde_json::to_string` + сортировка ключей |
| E2E тесты нестабильны на Docker-стенде | Низкая | Добавить retry и таймауты |
| Миграция SyncServer 0019 конфликтует с существующими | Низкая | Проверить `alembic history` перед созданием |
