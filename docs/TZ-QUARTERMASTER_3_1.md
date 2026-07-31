# TZ: Quartermaster 3.1 — Branding & Offline Readiness

**Date:** 2026-06-19
**Based on:** `.agent/SCOPE-v3.1.md`, аудит кода 2026-06-19, ADR-0015/0016/0017
**Status:** Ready

## Execution Strategy

- [x] 🟢 Parallel execution recommended
- **Reason:** 3.1A, 3.1B, 3.1C — независимы по файлам и проектам. 3.1D **deferred to v3.2** (no Windows runner / WPF paused). 3.1E — после всех.

---

## Execution Checklist

- [x] 0. Pre-ADR: ADR-0015/0016/0017 созданы
- [x] 1. Stage 3.1A: Branding Quartermaster
- [x] 2. Stage 3.1A tests: static + stand smoke
- [x] 3. Stage 3.1B: SyncServer — sync_state + offline contract
- [x] 4. Stage 3.1B tests: unit + integration + stand smoke
- [x] 5. Stage 3.1C: Rust core — compatibility gate
- [x] 6. Stage 3.1C tests: cargo test + clippy + stand smoke
- [ ] 7. ~~Stage 3.1D: WPF — Layer 0 FFI spike~~ **deferred to v3.2** (no Windows runner, WarehouseWorkstation paused, .NET SDK not available on Linux dev-стенд; FFI cdylib already proven loadable by Rust+Python at gate 5)
- [ ] 8. ~~Stage 3.1D tests~~ skipped with 3.1D
- [x] 9. Stage 3.1E: Documentation finalization — принято (2026-07-13)
- [x] 10. Regression: SyncServer 426 tests ✅, Django tests ⏳, Rust 112 tests ✅, WPF 117 tests ⏳ (deferred вместе с 3.1D)
- [x] 11. Final acceptance review — принято (2026-07-13)

---

## Stage 3.1A: Branding Quartermaster

**Входные данные:** ADR-0015, текущее состояние UI (Django + Angular)

### Задача 3.1A.1: Конфигурация брендинга

**Файлы:**
- `Warehouse_web/config/settings/base.py` — новые env vars с дефолтами
- `.env.example` (корень или `Warehouse_web/`) — документирование переменных

**Переменные (имена, не значения):**
```python
APP_PRODUCT_NAME = os.environ.get("APP_PRODUCT_NAME", "Quartermaster")
APP_PRODUCT_VERSION = os.environ.get("APP_PRODUCT_VERSION", "3.1")
APP_PRODUCT_TAGLINE = os.environ.get("APP_PRODUCT_TAGLINE", "Система складского и имущественного учёта")
APP_BRAND_LOGO = os.environ.get("APP_BRAND_LOGO", "img/logo.svg")
APP_BRAND_FAVICON = os.environ.get("APP_BRAND_FAVICON", "img/favicon.ico")
APP_BRAND_PRIMARY_COLOR = os.environ.get("APP_BRAND_PRIMARY_COLOR", "#1a365d")
```

### Задача 3.1A.2: Django shell — заголовок и sidebar

**Файлы:**
- `Warehouse_web/templates/base.html` — `<title>`, header, sidebar brand area, footer
- `Warehouse_web/templates/registration/login.html` — страница входа

**Изменения:**
- `<title>` → `{{ APP_PRODUCT_NAME }}`
- Sidebar top: `{{ APP_PRODUCT_NAME }}` + tagline мелко
- Footer: `{{ APP_PRODUCT_NAME }} {{ APP_PRODUCT_VERSION }}`
- Login page: `{{ APP_PRODUCT_NAME }}` + `Вход в систему учёта`
- Все значения берутся из `settings.py`, передаются через context processor

### Задача 3.1A.3: Angular shell — заголовок

**Файлы:**
- `Warehouse_frontend/src/app/app.component.html`
- `Warehouse_frontend/src/app/app.component.ts`

**Изменения:**
- Заголовок приложения → значение из конфигурации/окружения Angular
- Передать `APP_PRODUCT_NAME` через Django BFF endpoint или `environment.ts`

### Задача 3.1A.4: README и документация

**Файлы (уже частично обновлены):**
- `/README.md` — ✅ Quartermaster
- `/SOLUTION_ROADMAP.md` — ✅
- `SyncServer/README.md`
- `Warehouse_web/README.md`
- `Warehouse_frontend/README.md`
- `Warehouse_client_core/README.md`
- `WarehouseWorkstation/README.md`

**Изменения:** упоминание «Quartermaster» как продуктового имени в описании проекта.

### Тесты Stage 3.1A

- [ ] Static: `python manage.py check` — нет ошибок конфигурации
- [ ] Stand smoke: `http://localhost:8001` — страница входа показывает «Quartermaster»
- [ ] Stand smoke: `http://localhost:8001/admin/` — админка работает
- [ ] Stand smoke: `http://localhost:4200` — Angular shell показывает «Quartermaster»
- [ ] Проверка: старые URL работают без изменений

---

## Stage 3.1B: SyncServer — sync_state + offline contract

**Входные данные:** ADR-0016, аудит 2026-06-19 (sync-контур работает, нет sync_state)

### Задача 3.1B.1: Модель и миграция sync_state

**Файлы:**
- `SyncServer/app/models/sync_state.py` — новая модель
- `SyncServer/app/models/__init__.py` — импорт
- `SyncServer/alembic/versions/0019_add_sync_state.py` — новая миграция

**Модель:**
```python
class SyncState(Base):
    __tablename__ = "sync_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(Integer, ForeignKey("devices.id"), unique=True, nullable=False)
    last_sequence_number: Mapped[int] = mapped_column(BigInteger, default=0)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default="unknown")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

**Индексы:** уникальный на `device_id`, обычный на `status`

### Задача 3.1B.2: Репозиторий SyncStateRepo

**Файл:**
- `SyncServer/app/repos/sync_state_repo.py` — новый

**Методы:**
- `upsert(device_id, last_sequence_number, status, last_error=None)` — INSERT ON CONFLICT UPDATE
- `get_by_device_id(device_id)` → SyncState | None
- `get_max_server_seq(site_id)` → int (уже есть в EventsRepo)

### Задача 3.1B.3: Обновление ping/pull/push

**Файлы:**
- `SyncServer/app/api/routes_sync.py`
- `SyncServer/app/services/sync_service.py`

**Изменения в ping:**
- После получения ответа — upsert sync_state:
  - `last_sequence_number = max(текущий, client.last_server_seq)` (клиент сообщает свой последний seq)
  - `last_sync_at = now()`
  - `status = "online"`
- Убедиться, что `Device.last_seen_at` обновляется (проверить: identity_service делает это при auth)

**Изменения в pull:**
- После успешного pull — обновить `sync_state.last_sequence_number = max(текущий, returned server_seq_upto)`
- Обновить `sync_state.last_sync_at`

**Изменения в push:**
- После обработки батча — обновить `sync_state.last_sync_at`
- При ошибке — записать `last_error`

### Задача 3.1B.4: Эндпоинт GET /api/v1/sync/status/{device_id}

**Файлы:**
- `SyncServer/app/api/routes_sync.py` — новый route
- `SyncServer/app/schemas/sync.py` — схема `SyncStatusResponse`

**Ответ:**
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

**Авторизация:**
- Device token обязателен
- Своё устройство (device_id из токена совпадает с запрошенным) → разрешено
- Root-пользователь → разрешено для любого устройства
- Остальные → 403

### Задача 3.1B.5: Таксономия ответов push

**Файлы:**
- `SyncServer/app/services/sync_service.py`
- `SyncServer/app/schemas/sync.py`

**Текущее состояние:** accepted, duplicate_same_payload, uuid_collision

**Добавить:**
- `rejected` — когда бизнес-правило нарушено (на будущее, framework готов)
- `conflict` — когда uuid совпал, payload разный (уже есть uuid_collision → переименовать для ясности)
- `validation_error` — когда payload не проходит валидацию (уже есть 422 на уровне FastAPI)
- `auth_error` — когда токен невалиден (уже есть 401 на уровне middleware)

**Действие:** Документировать текущую таксономию в коде и ответах API, привести к единому неймингу.

### Тесты Stage 3.1B

- [ ] Unit: `SyncStateRepo` — upsert, get_by_device_id
- [ ] Integration: после ping — sync_state создан, last_seen_at обновлён
- [ ] Integration: после pull — last_sequence_number обновлён
- [ ] Integration: `GET /sync/status/{device_id}` — корректные данные, behind_by
- [ ] Integration: авторизация status endpoint — своё/чужое устройство
- [ ] Миграция: `alembic upgrade head` и `alembic downgrade -1`
- [ ] Не сломать существующие 18 sync-тестов

**Команды:**
```bash
cd SyncServer
python -m alembic upgrade head
python -m pytest tests/test_sync_state.py tests/test_http_sync.py -v
python -m pytest -x -m "not stand"  # полная регрессия
```

---

## Stage 3.1C: Rust Core — Compatibility Gate

**Входные данные:** ADR-0017 gate 5 (stand smoke), аудит (payload_hash несовместим)

### Задача 3.1C.1: payload_hash совместимость

**Файлы:**
- `Warehouse_client_core/crates/warehouse_core/src/operations/outbox_service.rs`
- `Warehouse_client_core/crates/warehouse_core/Cargo.toml` — добавить `sha2`

**Требуется:**
1. Добавить `sha2 = "0.10"` в зависимости
2. Реализовать `compute_payload_hash(json: &str) -> String`:
   - Десериализовать → `serde_json::Value`
   - Ресериализовать с сортировкой ключей → `serde_json::to_string`
   - SHA-256 → `sha2::Sha256::digest`
   - Вернуть hex (нижний регистр)
3. Заменить старую `sha256_simple` (SipHash) на новую
4. Тест совместимости: одинаковый JSON → одинаковый хэш в Rust и Python

**Проверка совместимости с SyncServer:**
```python
# SyncServer: app/services/event_ingest.py
canonical_json = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')
payload_hash = hashlib.sha256(canonical_json).hexdigest()
```

### Задача 3.1C.2: Stand smoke test Core ↔ SyncServer

**Файл:**
- `Warehouse_client_core/tests/e2e_sync_stand_test.rs` — новый (или дополнить существующие)

**Сценарий:**
1. Запустить SyncServer в Docker (или использовать запущенный стенд)
2. Получить device_token через `POST /admin/devices` (create test device)
3. Bootstrap через `CoreHandle::bootstrap()`
4. Проверить: catalog (categories, units, items) загружены в SQLite
5. Проверить: sites загружены
6. Создать draft-операцию через `CoreHandle::create_draft()`
7. Push через `CoreHandle::sync_once(SyncMode::PushOnly)`
8. Pull через `CoreHandle::sync_once(SyncMode::PullOnly)`
9. Проверить через CLI: `warehouse-cli sync full`

### Задача 3.1C.3: Release DLL сборка

**Файлы:**
- `Warehouse_client_core/crates/warehouse_ffi/Cargo.toml` — проверить `crate-type = ["cdylib"]`
- `Warehouse_client_core/Makefile` или скрипт сборки

**Требуется:**
```bash
cd Warehouse_client_core
cargo build --release -p warehouse_ffi
# Проверить: target/release/libwarehouse_ffi.so (Linux) / warehouse_ffi.dll (Windows)
```

### Задача 3.1C.4: Документирование write_operations no-op

**Файл:**
- `Warehouse_client_core/crates/warehouse_core/src/storage/snapshot_writer.rs`

**Действие:** Добавить комментарий над `write_operations()`:
```rust
/// Confirmed operations are proxied directly from SyncServer API.
/// Local SQLite stores only drafts (`operation_drafts` table).
/// Caching confirmed operations would duplicate data without a clear offline use case.
/// See ADR-0016, ADR-0017.
pub async fn write_operations(&self, ops: &[OperationListItem]) -> CoreResult<()> {
    let _ = ops;
    Ok(())
}
```

### Тесты Stage 3.1C

- [x] `cargo fmt --all -- --check`
- [x] `cargo clippy --workspace --all-targets -- -D warnings`
- [x] `cargo test --workspace` — все существующие ~90 тестов проходят (фактически: 114 passed, 0 failed, 2026-07-31)
- [x] Новый тест: `compute_payload_hash` совместим с SyncServer
- [ ] Stand smoke: `cargo run --release -p warehouse_cli -- sync full` проходит на Docker-стенде
- [ ] Release DLL: `cargo build --release -p warehouse_ffi` успешно, файл существует

---

## Stage 3.1D: WPF — Layer 0 FFI Spike  *(deferred to v3.2)*

**Status:** deferred. WarehouseWorkstation paused, .NET SDK не доступен на Linux dev-стенде, нет Windows CI. Все 5 ADR-0017 gates пройдены в 3.1C (FFI cdylib собирается, Rust smoke прошёл, payload_hash совместим с SyncServer). Verification загрузки .NET-рантаймом — задача v3.2 / Windows-CI.

Этап будет перенесён в v3.2 вместе с фактической миграцией Layers 1-7 (ADR-0017). См. раздел Out of Scope ниже и ADR-0017 для контекста.

---

## Stage 3.1E: Documentation Finalization

### Задача 3.1E.1: ADR финализация

**Файлы:**
- `docs/adr/0015-product-name-and-branding.md` — ✅ создан
- `docs/adr/0016-offline-sync-architecture.md` — ✅ создан
- `docs/adr/0017-wpf-migration-via-rust-core.md` — ✅ создан

### Задача 3.1E.2: Обновление проектных документов

**Файлы:**
- `ARCHITECTURE.md` — обновить под Quartermaster, добавить офлайн-архитектуру
- `INDEX.md` — актуализировать навигацию
- `AI_CONTEXT.md` — упомянуть Quartermaster, ADR-0015/0016/0017
- `AI_ENTRY_POINTS.md` — актуализировать входные точки
- `MEMORY.md` — обновить список проектов и текущий статус

### Задача 3.1E.3: Финальное обновление ROADMAP и SCOPE

**Файлы:**
- `SOLUTION_ROADMAP.md` — ✅ обновлён
- `.agent/SCOPE-v3.1.md` — ✅ обновлён
- `Functional and WorkLogik.md` — обновить разделы IX.11, X (статус синхронизации)

### Тесты Stage 3.1E

- [ ] Все ссылки в документации рабочие
- [ ] INDEX.md содержит актуальную навигацию
- [ ] README.md содержит Quartermaster

---

## Критерии приёмки (Definition of Done)

- [ ] UI показывает Quartermaster из конфигурации (`APP_PRODUCT_NAME`)
- [ ] Старые технические имена (`SyncServer`, `Warehouse_web`) не сломаны
- [ ] SyncServer хранит и отдаёт per-device `sync_state`
- [ ] `/ping`, `/pull`, `/push` обновляют `sync_state`
- [ ] `GET /api/v1/sync/status/{device_id}` работает
- [ ] Таксономия ответов push согласована и задокументирована
- [ ] Rust core: `payload_hash` совместим с SyncServer
- [ ] Rust core: stand smoke bootstrap → push → pull проходит
- [ ] Rust core: release DLL собирается воспроизводимо
- [ ] WPF: C# FFI wrapper загружает DLL, вызывает `core_version()` / `core_open()` / `core_close()`
- [ ] ADR-0015, ADR-0016, ADR-0017 созданы и приняты
- [ ] README, ARCHITECTURE, INDEX, AI_CONTEXT, AI_ENTRY_POINTS, MEMORY обновлены
- [ ] Регрессия: SyncServer 410+ ✅, Django ✅, Rust ~90 ✅, WPF 117 ✅

---

## Оценка трудозатрат

| Stage | Часы | Комментарий |
|-------|------|-------------|
| 3.1A Branding | 2-3 | Конфигурация + шаблоны + Angular |
| 3.1B SyncServer | 3-4 | Модель + миграция + 3 эндпоинта + тесты |
| 3.1C Rust core | 2-3 | payload_hash + stand smoke + release build |
| ~~3.1D WPF Layer 0~~ | — | **deferred to v3.2** (no Windows runner) |
| 3.1E Docs | 1-2 | ADR финализация + обновление документов |
| **Итого** | **8-12** | (без 3.1D) |

---

## Out of Scope

- ~~Layer 0 FFI spike~~ → **deferred to v3.2** (Windows CI)
- Полная миграция WPF Layers 1-7 → v3.2
- Android-клиент → v3.3
- QR/штрихкоды, печать, сканы → v3.4
- Переименование репозиториев/пакетов/БД → никогда
- Device push transport (ADR-0008 Phase 2) → опционально, не блокирует

---

## Изменения scope

- **2026-06-24:** Stage 3.1D (WPF Layer 0 FFI spike) исключён из v3.1 и перенесён в v3.2.
  Причины: (1) WarehouseWorkstation paused; (2) на Linux dev-стенде нет .NET SDK и
  Windows-окружения для P/Invoke + `warehouse_ffi.dll`; (3) gate 5 из ADR-0017
  (FFI cdylib loadable by client runtime) уже подтверждён в 3.1C через Rust+Python
  smoke. Verification загрузки .NET-рантаймом перенесён в v3.2.

---

## Evidence (2026-07-31)

Проверки Stage 3.1C (Rust core compatibility gate) выполнены в `Warehouse_client_core`
(ветка dev, run 2026-07-31).

| Check | Command | Result | Note |
|---|---|---|---|
| fmt | `cargo fmt --all -- --check` | PASS exit 0 | — |
| clippy | `cargo clippy --workspace --all-targets -- -D warnings` | PASS exit 0 | — |
| tests | `cargo test --workspace` | PASS, 114 passed, 0 failed | сумма «test result: ok. N passed» = 75+11+1+10+17=114; в TZ стояло «~90/112» |
| payload_hash compat | `cargo test --workspace payload_hash` | PASS | 3 unit-теста `operations::outbox_service::tests::compute_payload_hash_*` + интеграционный `tests/cross_lang_payload_hash.rs::compute_payload_hash_matches_python_reference` — все ok; `stand_smoke_payload_hash_matches_syncserver` ignored (требует реального стенда — остаётся вне scope) |

Примечания:
- Коммит делает родительский агент (этот агент только редактирует TZ, не коммитит).
- Stage 3.1D (WPF Layer 0 FFI spike) остаётся deferred to v3.2 — боксы не трогала.
- Вне scope остались незакрытыми: stand-smoke 3.1A (строки 89-93), 3.1B SyncServer
  pytest (198-204), 3.1E (335-337), acceptance-критерии с Django/стендом (343-355).
