# Architecture Review — TZ v3.1 Sync Protocol & Device Management

**Date:** 2026-06-19
**Reviewer:** Architect
**Plan:** `docs/TZ-V3.1_SYNC_AND_DEVICE_MANAGEMENT.md`

## Verdict

🟡 Approved with conditions — 1 blocker resolved (G2 переквалифицирован), 2 warnings требуют внимания при реализации.

---

## 🔴 Blockers

### 1. G2 `write_operations()` ошибочно классифицирован как баг

- **Checklist item:** Data & State — source of truth
- **Issue:** TZ предписывает «Реализовать write_operations()» (Задача 3.1), но исследование кода показало, что это **осознанное архитектурное решение**: подтверждённые операции не кэшируются в SQLite, а проксируются напрямую с SyncServer API. `list_operations()` в `facade/mod.rs:424` вызывает `client.operations_list()` напрямую, минуя SQLite.
- **Impact:** Если реализовать как предписано в TZ, будет создана избыточная таблица `operations_cache` и дублирование данных без ясного offline-сценария использования.
- **Recommendation:** Заменить Задачу 3.1 на документирование текущего решения: добавить комментарий в `snapshot_writer.rs:299` с объяснением, почему это no-op, и убрать из списка критических пробелов. Если в будущем потребуется offline-просмотр операций — решать через отдельный ADR.

**Статус:** ✅ Учтено в ревизии TZ.

---

## 🟡 Warnings

### 2. Онлайн/офлайн-порог (5 минут) не обоснован

- **Checklist item:** Operability — environment differences
- **Issue:** TZ (строка 180) задаёт жёсткий порог 5 минут для определения online/offline. На практике ping-интервал клиента может быть больше (экономия батареи на мобильных), а серверные часы могут расходиться.
- **Recommendation:** Сделать порог конфигурируемым через `DeviceSyncService` (с дефолтом 5 минут) или через `SYNC_ONLINE_THRESHOLD_SECONDS` в настройках Django. Добавить в TZ.

### 3. Совместимость payload_hash между Rust и SyncServer

- **Checklist item:** Data & State — source of truth
- **Issue:** SyncServer вычисляет `payload_hash` через canonical JSON (сортировка ключей) + SHA-256 (`app/services/event_ingest.py`). Rust использует `std::hash::DefaultHasher` (SipHash) под именем `sha256_simple`. При переходе на Phase 2 (device push) хэши не совпадут.
- **Recommendation:** В Задаче 3.3 явно указать: использовать `serde_json::to_string` + сортировку ключей + SHA-256 из `sha2` crate. Добавить тест совместимости: одинаковый JSON → одинаковый хэш в Python и Rust.

### 4. N+1 риск в Django admin при вычислении статуса

- **Checklist item:** Scalability — N+1 queries
- **Issue:** Хотя TZ предписывает кэшировать статус в полях `SyncDeviceBinding`, метод `online_status_badge` в `list_display` может быть вызван для каждой строки. Если статус сохранён в БД — вызов читает локальное поле (O(1)). Если статус вычисляется на лету через `DeviceSyncService` — будет N запросов к SyncServer.
- **Recommendation:** Явно указать в TZ: `online_status_badge` должен читать кэшированное поле `sync_state_status`, а не вызывать `refresh_device_status()`. Обновление статуса — только через admin action или BFF endpoint.

---

## 🔵 Notes

### 5. `backoff_seconds` в ping — отложено

- TZ упоминает динамический backoff как «опционально, можно отложить». Для v3.1 это приемлемо — текущий хардкод `0` не блокирует базовую функциональность.

### 6. Device push Phase 2 — вне scope

- ADR-0008 определяет двухфазный подход. Phase 1 (REST) работает. Phase 2 (device push) корректно вынесен за scope v3.1.

### 7. Отсутствие circuit breaker — допустимо

- Для v3.1 с низкой нагрузкой circuit breaker не обязателен. Можно добавить в будущих итерациях.

### 8. E2E тесты на Rust CLI

- Сценарий предполагает вызов `warehouse-cli` из shell. Нужно учесть, что `cargo` может быть недоступен в некоторых средах. Альтернатива: использовать Rust test с программным вызовом `CoreHandle`.

---

## Итоговые изменения в TZ

| Изменение | Причина |
|-----------|---------|
| G2 переквалифицирован из «критический пробел» в «архитектурное решение» | Подтверждённые операции не кэшируются локально по дизайну |
| Задача 3.1 заменена на «документировать no-op» | Не нужно создавать таблицу без ясного сценария |
| Задача 3.3 дополнена требованием совместимости хэшей | Риск несовпадения при Phase 2 |
| Задача 2.2 дополнена конфигурируемым порогом online/offline | Гибкость для разных типов клиентов |
| Задача 2.3 уточнена: badge читает кэш, не вызывает refresh | Предотвращение N+1 |

---

## Пройденные чек-листы

### Complexity
- [x] Простейшее решение: sync_state — 6 полей, статус — threshold-вычисление
- [x] Офф-зе-шелф: N/A (кастомный sync-протокол)
- [x] Единая ответственность: sync_state — позиция синхронизации, DeviceSyncService — статус, SnapshotWriter — кэширование
- [x] Понятно джуниору: концептуально просто (трекинг позиции, порог online/offline)

### Coupling & Cohesion
- [x] Изолированное тестирование: sync_state repo — unit-тест с тестовой БД, DeviceSyncService — с моком SyncServerClient
- [x] Нет циклических зависимостей: SyncServer → Rust (однонаправленно), SyncServer → Django (однонаправленно)
- [x] Владение данными чётко: SyncServer — источник истины, Django — зеркало, Rust — локальный кэш
- [x] Минимальный API: 1 новый эндпоинт (GET /sync/status/{device_id}), остальное — модификация существующих

### Data & State
- [x] Источник истины: sync_state — SyncServer, статус — вычисляется из SyncServer.last_seen_at
- [x] Отказ БД: sync_state в PostgreSQL — при отказе sync-эндпоинты возвращают 500; Rust SQLite — не затронут
- [x] Нет глобального мутабельного состояния
- [x] Миграции запланированы: 0019 (SyncServer), 0006 (Django)

### Failure Modes
- [x] SyncServer недоступен → Django показывает "unknown"
- [x] Retry с backoff: Rust — max_retries=3, backoff=2s; Django — существующий retry в sync_client
- [x] Таймауты: Rust — 30s дефолт, Django — существующий таймаут
- [x] Частичный отказ: ping OK + pull FAIL → устройство online, но за ним числится отставание
- [⚠️] Circuit breaker отсутствует — допустимо для v3.1

### Security
- [x] Валидация ввода: device_id — int (FastAPI), статус — read-only
- [x] Секреты — env vars
- [x] Авторизация: status/{device_id} — своё устройство или admin/root
- [x] Параметризованные запросы (SQLAlchemy/SQLx)
- [x] Least privilege: status endpoint — read-only

### Scalability
- [x] Нагрузка через 6 месяцев: sync_state — 1 строка на устройство, при 1000 устройств — тривиально
- [x] N+1: кэширование статуса в SyncDeviceBinding полях — O(1) в list_display
- [x] Кэширование: статус в локальных полях Django-модели, инвалидация по требованию
- [x] Фоновые задачи: не требуются

### Observability
- [x] Структурированное логирование: существующее во всех проектах
- [x] Health-эндпоинты: /api/v1/health, /healthz/
- [x] Мониторинг ошибок: существующий
- [x] End-to-end трассировка: вне scope v3.1

### Operability
- [x] Деплой без даунтайма: миграции — аддитивные, эндпоинты — новые
- [x] Rollback: миграции обратимы (downgrade удаляет sync_state)
- [x] Различия сред: все через env vars
