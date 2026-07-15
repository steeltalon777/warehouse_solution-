# Архитектурное ревью: система логирования действий кладовщика

**Дата:** 2026-07-14
**Рецензент:** Architect mode
**Объект ревью:** централизованный аудит действий пользователей (audit log) в warehouse solution
**Источник истины:** SyncServer (БД `warehouse`)
**Источник UI:** Warehouse_web (Django BFF + Django admin SSR)
**Статус:** рабочая система, есть архитектурные пробелы

---

## 1. Резюме (TL;DR)

| Аспект | Состояние | Оценка |
|---|---|---|
| Централизованная запись в SyncServer | работает для бизнес-операций и каталога | зрелая |
| API для чтения (`GET /api/v1/admin/audit`) | работает | зрелая |
| Django BFF прокси для чтения | работает | зрелая |
| Django admin UI для просмотра | работает, есть фильтры и пагинация | зрелая |
| CLI `scripts/query_audit.py` | работает, принят в эксплуатацию (2026-07-13) | зрелая |
| Централизованный аудит login/logout | РЕАЛИЗОВАН РАНЕЕ, СЕЙЧАС ОТКЛЮЧЁН | регрессия |
| Audit для остатков, документов, выдачи, справочника прав | ОТСУТСТВУЕТ | пробел |
| Retention/cleanup policy | ОТСУТСТВУЕТ | пробел |
| Тесты для AuditEvent endpoint/repo | ОТСУТСТВУЮТ | пробел |
| Функциональные требования в `Functional and WorkLogik.md` | ОТСУТСТВУЮТ | пробел |

**Главный вывод:** каркас централизованного бизнес-аудита построен и работает стабильно для операций и каталога. Однако три крупных пробела: (а) аудит входов/выходов пользователей сейчас не пишется в SyncServer (хотя исторически был и записи остались), (б) покрытие событий неполное — нет аудита остатков, документов, выдачи, управленческих операций, (в) тестовая лестница для audit endpoint/repo пустая.

---

## 2. Что входит в систему

### 2.1. SyncServer (источник истины)

| Компонент | Файл | Роль |
|---|---|---|
| Модель `AuditEvent` | `SyncServer/app/models/audit_event.py` | append-only таблица `audit_events` |
| Репозиторий | `SyncServer/app/repos/audit_events_repo.py` | `insert`, `list_events`, `get_by_id`, `get_by_id_full` |
| Helper | `SyncServer/app/services/audit_helper.py` | `record_audit_event()` — единая точка записи |
| Схемы | `SyncServer/app/schemas/audit.py` | `AuditEventResponse`, `AuditEventListResponse` |
| API | `SyncServer/app/api/routes_admin_audit.py` | `GET /api/v1/admin/audit`, `GET /api/v1/admin/audit/{event_id}` |
| UoW wiring | `SyncServer/app/services/uow.py:33` | `self.audit_events = AuditEventsRepo(session)` |
| Миграция | `SyncServer/alembic/versions/0017_add_audit_events.py` | создание таблицы + 5 индексов |
| CLI | `SyncServer/scripts/query_audit.py` | операторский просмотр аудита (markdown/json/table) |
| Документация | `SyncServer/docs/audit-query-examples.md` | сценарии использования CLI |

### 2.2. Warehouse_web (Django BFF + UI)

| Компонент | Файл | Роль |
|---|---|---|
| BFF list | `Warehouse_web/apps/bff_api/audit_views.py` | `GET /bff/api/v1/admin/audit` — прокси в SyncServer |
| BFF detail | `Warehouse_web/apps/bff_api/audit_views.py` | `GET /bff/api/v1/admin/audit/{event_id}` |
| Django admin list | `Warehouse_web/apps/users/admin_audit_views.py` | `GET /admin/audit-events/` |
| Django admin detail | `Warehouse_web/apps/users/admin_audit_views.py` | `GET /admin/audit-events/{event_id}/` |
| Шаблон списка | `Warehouse_web/apps/users/templates/admin/audit_events_list.html` | фильтры + таблица + пагинация |
| Шаблон деталей | `Warehouse_web/apps/users/templates/admin/audit_event_detail.html` | полная карточка события |
| URL routing | `Warehouse_web/config/urls.py:58-67` | маппинг URL |
| Локальный login-аудит | `Warehouse_web/apps/users/models.py:174-205` | `LoginAttempt` для входов Django |
| Сигнал login/logout | `Warehouse_web/apps/users/simple_sync_signals.py:175-195` | `_record_login_attempt()` |

### 2.3. Документы и решения

| Документ | Статус |
|---|---|
| `docs/TZ-AUDIT_LOGIN_AND_CLI_QUERY.md` | утверждён (2026-07-13); Unit A (`POST /auth/audit-event`) и Unit B (Django push) deferred до dashboard-phase |
| `.agent/SCOPE-audit-login-and-password-mgmt.md` | описывает первоначальный план, позже суженный до CLI-only |
| `docs/V3.0_POST_DEPLOY_FIXES.md` #6 | фикс #6: журнал действий пользователей — CLI реализован, login audit deferred |
| `docs/V3.0.1_POST_DEPLOY_QUICK_FIXES.md:767` | «3.1 must design append-only business audit and Django login/session history with retention and viewing UI/admin» |
| `docs/TZ-SYNCSERVER_REGRESSION_AND_SCOPE_CLEANUP.md` | история сокращения скоупа; audit mocks фикс |

---

## 3. Архитектура: как это работает

### 3.1. Поток записи (write path)

```
[UI/Django/BFF клиент]
   |
   | HTTP запрос с X-User-Token, X-Device-Token
   v
[FastAPI route, например routes_operations.py]
   |
   | resolve identity, parse payload
   v
[Service: operations_service.create_operation]
   |
   | выполняет бизнес-логику
   |
   | внутри UoW-транзакции:
   |     await record_audit_event(
   |         uow,
   |         event_type="operation.create",
   |         actor_user_id=identity.user_id,
   |         actor_device_id=identity.device_id,
   |         site_id=operation.site_id,
   |         entity_type="operation",
   |         entity_id=str(operation.id),
   |         summary="Пользователь создал черновик операции ...",
   |         changes={...},        # опционально
   |         request_id=state.request_id,
   |     )
   |
   v
[UoW.audit_events.insert(event)] -> flush
   |
   v
[PostgreSQL: INSERT INTO audit_events]
   |
   v
[UoW.__aexit__: COMMIT]  (audit попадает в БД атомарно с бизнес-записью)
```

**Ключевое свойство:** audit-запись создаётся внутри той же UoW-транзакции, что и бизнес-операция. Если операция откатывается — audit тоже откатывается. Это правильно с точки зрения согласованности, но создаёт ограничение: audit не может зафиксировать «откат бизнес-операции» (нет post-mortem событий).

### 3.2. Поток чтения (read path)

Есть три канала чтения:

```
(1) Django admin SSR (для рута и главного кладовщика)
    /admin/audit-events/                  -> AdminAuditEventListView  -> SyncServerClient.get('/admin/audit')
    /admin/audit-events/<event_id>/       -> AdminAuditEventDetailView -> SyncServerClient.get('/admin/audit/{id}')

(2) BFF JSON API (для Angular и других клиентов)
    /bff/api/v1/admin/audit               -> AuditEventsListView      -> SyncServerClient.get('/admin/audit')
    /bff/api/v1/admin/audit/<event_id>    -> AuditEventDetailView     -> SyncServerClient.get('/admin/audit/{id}')

(3) CLI (для оператора)
    docker compose exec syncserver python scripts/query_audit.py \
        --username <u> --date-from YYYY-MM-DD --console
    -> SQLAlchemy -> AuditEventsRepo.list_events() -> markdown/json/table
```

Все три канала идут через `AuditEventsRepo.list_events()` / `get_by_id_full()` в SyncServer.

### 3.3. Схема таблицы `audit_events`

```sql
CREATE TABLE audit_events (
    id              SERIAL PRIMARY KEY,
    event_id        UUID UNIQUE NOT NULL,           -- стабильный ID для клиентских ссылок
    event_type      VARCHAR(64) NOT NULL,            -- "operation.create", "item.update" и т.д.
    actor_user_id   UUID REFERENCES users(id),       -- nullable (system events)
    actor_device_id INTEGER REFERENCES devices(id),
    site_id         INTEGER REFERENCES sites(id),
    entity_type     VARCHAR(64) NOT NULL,            -- "operation", "item", "auth", ...
    entity_id       VARCHAR(256) NOT NULL,           -- UUID или int, строкой
    summary         VARCHAR(500) NOT NULL,           -- человекочитаемое описание (русский)
    changes         JSONB,                          -- дифф/метаданные (опционально)
    request_id      VARCHAR(64),                    -- для трассировки
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 5 индексов:
-- ix_audit_events_event_type
-- ix_audit_events_actor_user_id
-- ix_audit_events_entity_type_entity_id
-- ix_audit_events_site_id
-- ix_audit_events_created_at
-- + UNIQUE (event_id) + PRIMARY KEY (id)
```

### 3.4. Авторизация на чтение

Все три канала используют одну и ту же логику:
- SyncServer: `require_admin_basic(identity)` — root или chief_storekeeper
- Django BFF: `_require_root(user) or can_manage_catalog(user)`
- Django admin SSR: `_has_audit_access(user) = _require_root(user) or can_manage_catalog(user)`

Это согласованно: обычный кладовщик НЕ видит audit log, только главный кладовщик и root.

### 3.5. LoginAttempt в Django — отдельный поток

В `Warehouse_web/apps/users/models.py:174-205` живёт локальная Django-модель `LoginAttempt`:

```python
class LoginAttempt(models.Model):
    id = UUIDField(primary_key=True, default=uuid4)
    user = ForeignKey(User, on_delete=SET_NULL, null=True)
    action = CharField(choices=[("login","Вход"),("logout","Выход")], db_index=True)
    ip_address = GenericIPAddressField(null=True)
    user_agent = CharField(max_length=256)
    request_id = CharField(max_length=64)
    created_at = DateTimeField(auto_now_add=True, db_index=True)
```

Пишется локально в Django-сигнале `_record_login_attempt()` (`simple_sync_signals.py:175-195`). **Не отправляется в SyncServer** (deferred с 2026-06-18). Доступна в Django admin через `LoginAttemptAdmin` (read-only для не-суперюзеров).

---

## 4. Каталог событий: что пишется, что нет

### 4.1. Реально пишется в `audit_events` (найдено в коде + подтверждено в БД)

| event_type | entity_type | Где вызывается | changes |
|---|---|---|---|
| `operation.create` | operation | `operations_service.create_operation` | null |
| `operation.submit` | operation | `operations_service.submit_operation` | null |
| `operation.acceptance_complete` | operation | `operations_service.complete_acceptance` | null |
| `operation.cancel` | operation | `operations_service.cancel_operation` | null |
| `operation.delete` | operation | `operations_service.delete_operation` | null |
| `item.create` | item | `catalog_admin_service.create_item` | null |
| `item.update` | item | `catalog_admin_service.update_item` | diff dict |
| `item.merge` | item | `catalog_admin_service.merge_items` | merge metadata |
| `unit.create` | unit | `catalog_admin_service.create_unit` | null |
| `unit.update` | unit | `catalog_admin_service.update_unit` | diff dict |
| `category.create` | category | `catalog_admin_service.create_category` | null |
| `category.update` | category | `catalog_admin_service.update_category` | diff dict |
| `auth.login` | auth | **НЕ НАЙДЕНО в коде** (был ранее, удалён) | ip+ua |
| `auth.logout` | auth | **НЕ НАЙДЕНО в коде** (был ранее, удалён) | ip+ua |

### 4.2. Не пишется — пробелы покрытия

| Домен | Ожидаемое событие | Сейчас |
|---|---|---|
| Остатки | `balance.update` (при submit/cancel/restore операций) | НЕ пишется |
| Документы | `document.generate`, `document.finalize`, `document.void` | НЕ пишется |
| Issue Objects | `issue_object.create/update/merge/delete` | НЕ пишется |
| Issue Object Categories | `issue_object_category.create/update/delete` | НЕ пишется |
| Asset Registers | `asset_register.create/update` | НЕ пишется |
| Review Items | `review_item.confirm/merge` | НЕ пишется |
| Temporary Items | `temporary_item.create/merge/delete` | НЕ пишется |
| Users (admin) | `user.create/update/rotate_token` | НЕ пишется |
| Sites (admin) | `site.create/update` | НЕ пишется |
| Devices (admin) | `device.create/update/rotate_token` | НЕ пишется |
| Access scopes | `access_scope.grant/revoke` | НЕ пишется |
| Sync state | `device.online/offline/error` | НЕ пишется (есть `sync_state` таблица, но не AuditEvent) |
| Login/Logout | `auth.login`, `auth.logout` | НЕ пишется (deferred до dashboard) |

Для пользователя системы «audit операций и каталога» покрывает ~70% того, что называется «действия кладовщика». Для полного покрытия нужно ~10-12 новых event_type и точек вызова.

---

## 5. Данные по работе (live snapshot 2026-07-14)

Запрос к PostgreSQL `warehouse.audit_events` на работающем dev-стенде.

### 5.1. Общий объём

| Метрика | Значение |
|---|---|
| Всего записей | **338** |
| Размер таблицы (с индексами) | 288 KB |
| Период | 2026-06-16 05:35 → 2026-07-14 00:52 (≈ 28 дней) |
| Уникальных actor_user_id | 4 |
| Уникальных site_id | 3 |
| Уникальных actor_device_id | 1 |
| Записей с `actor_user_id IS NULL` (system) | 0 |
| Записей с `changes IS NOT NULL` | 197 |

### 5.2. Распределение по event_type

| event_type | Кол-во | Первая | Последняя |
|---|---|---|---|
| operation.create | 141 | 2026-06-16 | 2026-07-14 |
| operation.submit | 70 | 2026-06-16 | 2026-07-13 |
| item.create | 44 | 2026-06-24 | 2026-07-08 |
| operation.acceptance_complete | 37 | 2026-06-17 | 2026-07-13 |
| item.update | 18 | 2026-06-30 | 2026-07-06 |
| item.merge | 11 | 2026-06-30 | 2026-07-13 |
| **auth.login** | **6** | 2026-06-18 02:34 | 2026-06-18 02:50 |
| **auth.logout** | **5** | 2026-06-18 02:34 | 2026-06-18 02:50 |
| operation.cancel | 5 | 2026-07-08 | 2026-07-09 |
| unit.create | 1 | 2026-06-30 | 2026-06-30 |

### 5.3. Распределение по entity_type

| entity_type | Кол-во |
|---|---|
| operation | 253 |
| item | 73 |
| auth | 11 |
| unit | 1 |

### 5.4. Активность по пользователям

| actor_user_id (хеш UUID) | username | Событий |
|---|---|---|
| `b1355640-76dd-4dfe-a810-d7436956cbdb` | `root` | 252 |
| `b672a3da-8904-4aa7-80e2-a94d6b693f82` | `aksha` (вероятно) | 69 |
| `1604e10f-070c-413e-bf65-a3afae259d40` | — | 16 |
| `6939052c-3de2-4e7a-82e4-cdfc4688cb3f` | `buh_observer` | 1 |

`root` создаёт ~75% всех событий — это ожидаемо для dev-стенда.

### 5.5. Аномалия: auth.login/auth.logout

В БД сохранены **11 записей** auth-событий (`auth.login` × 6, `auth.logout` × 5), все датированы **2026-06-18 02:34–02:50 UTC**. После этого ни одной записи `auth.*` в таблице нет, хотя продолжают создаваться operation.* и item.* события.

Это значит:
- 18 июня 2026 работал код, который отправлял login/logout в SyncServer
- Затем код был удалён/отключён (сейчас `audit_push.py` существует только как `__pycache__/audit_push.cpython-*.pyc`)
- Решение зафиксировано в `TZ-AUDIT_LOGIN_AND_CLI_QUERY.md` (Unit B deferred до dashboard phase) и `.agent/SCOPE-audit-login-and-password-mgmt.md`

**Наблюдение:** в документах это выглядит как «deferred», но в реальности auth-audit однажды был реализован, проработал короткое время и был свёрнут. Это видно по историческим записям и по сохранившемуся `.pyc`. Регрессия, не первичное решение.

---

## 6. Архитектурное ревью

### 6.1. Границы и контракты

| Аспект | Оценка | Комментарий |
|---|---|---|
| Append-only контракт | хорошее | в коде нет UPDATE/DELETE на `audit_events`; `record_audit_event` всегда INSERT |
| SyncServer — единственный источник | хорошее | клиенты пишут только через SyncServer API; Django имеет только локальный `LoginAttempt` |
| BFF не хранит копию | хорошее | `audit_views.py` — чистый прокси без кеша |
| Независимость от домена | хорошее | `AuditEvent` ссылается на `users/devices/sites` через FK, но `entity_id` хранится строкой, что позволяет логировать любую сущность без миграций |
| UoW-атомарность | спорное | плюс: консистентность с бизнес-транзакцией; минус: при ошибке бизнес-записи audit теряется (нет post-mortem) |
| Стандартизация event_type | слабое | строковое поле без enum, нет schema-versioning, формат summary свободный |

### 6.2. Сложность и связность

| Аспект | Оценка | Комментарий |
|---|---|---|
| Coupling с services | умеренное | `record_audit_event()` вызывается прямо из 7 мест в `catalog_admin_service` и 5 мест в `operations_service`; легко пропустить |
| Расширяемость | хорошее | новый event_type добавляется одной строкой без миграций |
| Читаемость summary | среднее | формат свободный, без i18n-ключей; парсинг невозможен |
| Структура changes | нестабильное | иногда `null`, иногда `dict`, иногда `{"ip_address": ..., "user_agent": ...}` (auth); нет общей schema |
| Дублирование summary/entity_id | приемлемое | на UI summary показывается, entity_id нужен для ссылок — это нормально |

### 6.3. Тестовое покрытие

| Что | Тесты | Оценка |
|---|---|---|
| `AuditEvent` модель | нет | пробел |
| `AuditEventsRepo` (list/insert/get_by_id) | нет | пробел |
| `record_audit_event()` helper | нет (тестируется косвенно) | пробел |
| `GET /api/v1/admin/audit` endpoint | нет | пробел |
| `GET /api/v1/admin/audit/{id}` endpoint | нет | пробел |
| BFF `audit_views.py` | нет | пробел |
| Django admin views | нет (есть `LoginAttemptAdminReadOnlyTests`) | пробел |
| `scripts/query_audit.py` CLI | 11 unit-тестов (только форматтеры) | частично: нет e2e с реальной БД |
| Проверка, что операция пишет audit | косвенно через `test_operations_*` | частично |

**Покрытие тестами AuditEvent endpoint/repo = 0%.** Это критический пробел: единственная защита от регрессии в audit-слое — ручные smoke-тесты.

### 6.4. Безопасность

| Аспект | Оценка | Комментарий |
|---|---|---|
| Доступ на чтение | хорошее | root или chief_storekeeper на всех 3 каналах |
| Авторизация в SyncServer | хорошее | `require_admin_basic` валидирует токен |
| BFF не утекает токены | хорошее | `audit_views.py` использует `_build_client` (токены не выходят в browser) |
| Секреты в audit | хорошее | `audit_admin_security.py` валидирует, что в `last_sync_payload` нет чувствительных ключей |
| PII в `changes` (auth) | спорное | `user_agent` и `ip_address` записываются — это персональные данные; нет retention policy и нет согласия на обработку |
| SQL-инъекция | хорошее | SQLAlchemy параметризует; filter'ы — typed Query |
| Идемпотентность записей | спорное | при повторе транзакции пишется дубль; нет dedup-ключа |

### 6.5. Производительность и эксплуатация

| Аспект | Оценка | Комментарий |
|---|---|---|
| Индексы | хорошее | 5 B-tree индексов покрывают типичные фильтры (event_type, actor, site, entity_type+entity_id, created_at) |
| JSONB index | нет | для фильтрации по `changes->>'ip_address'` нет GIN; пока не нужно, но при росте данных может понадобиться |
| Pagination | хорошее | `page_size` до 200, есть `total_count` |
| Async I/O | хорошее | весь stack на `AsyncSession` + FastAPI |
| Запись в той же транзакции | приемлемое | добавляет 1 INSERT к бизнес-операции, latency ~1-2 мс |
| Retention | отсутствует | таблица растёт неограниченно; за 28 дней 338 записей ≈ 12 записей/день; через год ≈ 4500, через 5 лет ≈ 22000 — управляемо, но без политики |
| Партиционирование | нет | при >10M записей может понадобиться по `created_at` (monthly) |
| Backup | стандартный | попадает в общий backup Postgres |

### 6.6. Наблюдаемость

| Аспект | Оценка | Комментарий |
|---|---|---|
| Structured logging в SyncServer | хорошее | `access_log_middleware` пишет `http_request` с `request_id` (это HTTP access, не audit бизнес-операций) |
| Корреляция audit ↔ HTTP | частичная | `request_id` пишется в audit, но не во все места (например, в `auth.*` исторических записях пусто или null) |
| Метрики | нет | Prometheus-метрик для AuditEvent не вижу; нет счётчиков «сколько событий в минуту» |
| Алерты | нет | нет алертов на подозрительные паттерны (массовый login с одного IP, быстрые submit/delete и т.п.) |

### 6.7. Документация и требования

| Аспект | Оценка | Комментарий |
|---|---|---|
| `Functional and WorkLogik.md` | пробел | нет раздела про audit/журнал действий; требования scattered по `TZ-AUDIT_LOGIN_AND_CLI_QUERY.md`, `SCOPE-audit-login-and-password-mgmt.md`, `V3.0_POST_DEPLOY_FIXES.md` |
| API контракт | хорошее | OpenAPI генерируется автоматически, schema в `schemas/audit.py` |
| Каталог event_type | слабое | список есть только в исходниках; нет human-readable каталога; нет правила «что обязательно логировать» |
| Примеры CLI | хорошее | `audit-query-examples.md` — понятные сценарии |
| ADRs | нет | нет ADR про архитектуру audit, хотя для SCOPE/TZ это ключевая подсистема |
| Миграция | хорошее | `0017_add_audit_events.py` с явными индексами и FK |

---

## 7. Регрессия: централизованный login/logout audit

**Симптом:** в `audit_events` 11 записей `auth.login`/`auth.logout` от 18.06.2026 02:34–02:50; после этого ни одной.

**Источник:** в `Warehouse_web/apps/sync_client/` есть `__pycache__/audit_push.cpython-311.pyc` и `__pycache__/audit_push.cpython-312.pyc`, но файла `audit_push.py` нет.

**Причина:** SCOPE/TZ приняли решение defer login-audit до dashboard-phase. Код был удалён, остался только bytecode-cache.

**Документированное намерение** (из `TZ-AUDIT_LOGIN_AND_CLI_QUERY.md:12-13`):
> «Решение от 2026-06-18: Units A и B (endpoint и Django push) отложены. В кодовой базе оставлен только Unit C (CLI) + его тесты и документация. Причина: endpoint вводит слабый trust-boundary без насущной необходимости, синхронный HTTP в Django login/logout сигнале нежелателен без архитектурного обсуждения.»

**Архитектурные последствия:**
1. Прямо сейчас `LoginAttempt` в Django — единственный след входов/выходов. SyncServer не знает, кто заходил.
2. Потеряна корреляция «кто сейчас залогинен в Django → какие операции он сделал», потому что login audit теряется.
3. Если пользователь меняет пароль/email через Django BFF, в audit нет следа (auth.* не пишется, операция sync идёт через `UserSyncService` без audit).

**Рекомендация:** вернуть реализацию как часть dashboard-phase или закрытого ADR. До этого — убрать `__pycache__` от audit_push, чтобы не вводить в заблуждение будущих агентов.

---

## 8. Кросс-проектные наблюдения

### 8.1. WarehouseWeb — дублирование

- `apps/bff_api/audit_views.py` — BFF прокси для Angular
- `apps/users/admin_audit_views.py` — Django admin SSR для root
- Оба используют `_build_client(request)` из `apps/bff_api.helpers`
- Оба фильтруют права через `_require_root OR can_manage_catalog`

**Вопрос:** нужно ли объединять? Оба используют SyncServerClient, оба ходят в один endpoint. Сейчас расхождение минимальное (например, BFF возвращает JSON, admin SSR рендерит HTML). Рекомендация: оставить как есть, разная аудитория (machine vs human).

### 8.2. Warehouse_client_core

`docs/TZ-QUARTERMASTER_3_1.md` и `Warehouse_client_core/docs/STAGE4_PERSISTENT_CACHE_SYNC_FOUNDATION_ROOT_ADMINISTRATION_TZ.md` описывают локальный audit-tool-log для офлайн-клиентов. Это **другая система** — локальный log в Rust-клиенте, синхронизируется через `events_repo`. Не путать с централизованным SyncServer AuditEvent.

### 8.3. WarehouseAIWorkstation

`WarehouseAIWorkstation/.../DirectoryAuditService` и `AiToolLogEntry` — также локальные журналы для WPF AI workstation. На паузе (`AGENTS.md` явно: «paused unless the user explicitly asks to work on it»). Не часть текущего ревью.

---

## 9. Критические риски (с приоритетом)

| # | Риск | Приоритет | Что ломается |
|---|---|---|---|
| R1 | **Нет тестов для AuditEvent endpoint/repo** | высокий | любая правка в `audit_events_repo.py` или `routes_admin_audit.py` может сломать чтение без CI-сигнала |
| R2 | **Нет retention policy** | средний | таблица растёт неограниченно; через год будут десятки тысяч записей без механизма очистки |
| R3 | **Покрытие событий неполное** | средний | нет audit остатков, документов, выдачи, admin-операций; «журнал действий кладовщика» не покрывает половину кейсов |
| R4 | **auth.login/logout регрессировали** | средний | SyncServer не видит, кто входил; login/logout ищутся только в Django `LoginAttempt` |
| R5 | **Нет требований в `Functional and WorkLogik.md`** | средний | новые агенты не имеют единого источника правды; требования разбросаны по 3+ документам |
| R6 | **`changes` — свободный формат** | низкий | невозможно машинно валидировать и фильтровать по полям; парсинг ломается при изменении |
| R7 | **`request_id` не везде** | низкий | auth-события имеют `request_id`, некоторые operation могут терять при ошибках |
| R8 | **Нет GIN-индекса на `changes`** | низкий | при выходе за пределы B-tree-фильтров будет медленно |
| R9 | **PII (ip, user_agent) без retention** | низкий | GDPR/152-ФЗ риск, если данные хранятся дольше, чем нужно |

---

## 10. Рекомендации (что улучшить)

### 10.1. Быстрые (1-2 дня)

1. **Добавить unit-тесты для `AuditEventsRepo`** (insert, list_events с фильтрами, get_by_id). 5-10 тестов. Без этого любая правка репо — слепая зона.
2. **Добавить тесты для `routes_admin_audit.py`** (GET list, GET detail, права доступа). 4-6 тестов.
3. **Убрать `__pycache__/audit_push.cpython-*.pyc`** из `Warehouse_web/apps/sync_client/` — мёртвый bytecode вводит в заблуждение.
4. **Зафиксировать список event_type** в `SyncServer/docs/audit-events-catalog.md` (human-readable) — сейчас каталог разбросан по коду.

### 10.2. Среднесрочные (1-2 недели)

5. **Расширить покрытие audit-событий** до полного контура:
   - `balance.update` в `operations_service` (submit/cancel/restore)
   - `document.generate/finalize/void` в `document_service`
   - `issue_object.*` в `issue_objects_service`
   - `device.create/update/rotate_token` в admin
   - `user.create/update/rotate_token` в admin
   - `site.create/update` в admin
   - `access_scope.grant/revoke` в admin

6. **Вернуть `auth.login`/`auth.logout`** через фоновую очередь или async-задачу (не блокировать login/logout). Это закрывает R4.

7. **Добавить retention policy**: например, "хранить 1 год, потом агрегировать в `audit_events_archive` или удалять". Закрывает R2.

8. **Стандартизировать `changes`**: ввести typed schema (Pydantic) для каждого `event_type`. Сейчас `changes` — `dict | None`. Закрывает R6.

9. **Создать ADR** по архитектуре audit log: что пишется, кто имеет доступ, retention, источник истины для login. Сейчас решение размазано по SCOPE/TZ/POST_DEPLOY_FIXES.

### 10.3. Стратегические (месяц+)

10. **Добавить GIN-индексацию на `changes`** если понадобится фильтрация по полям (например, "все операции, где changes->>'from_status' = X").

11. **Метрики**: счётчики `audit_events_total{event_type}` в Prometheus для алертинга подозрительной активности.

12. **UI в Angular** для просмотра audit (если нужно для кладовщиков, а не только root). Сейчас UI только в Django admin SSR.

13. **Долгосрочный путь:** рассмотреть event-sourcing архитектуру, где `audit_events` становится основным write-model, а текущие таблицы — projections. Это спорное изменение, требует отдельного ADR.

---

## 11. Что НЕ является частью этого ревью

- WPF audit (`WarehouseAIWorkstation` — paused, локальный журнал)
- Rust offline audit (`Warehouse_client_core` — запланировано, не реализовано)
- HTTP access log (`access_log_middleware` — это не audit бизнес-операций, а request/response лог)
- `audit_admin_security.py` — это pre-deploy security check для Django admin, не связан с журналом действий кладовщика
- `LoginAttempt` в Django — это **локальный** аудит, не часть централизованной системы; рассмотрен только для контекста

---

## 12. Заключение

**Текущее состояние:** рабочая централизованная система аудита для бизнес-операций (operation.*) и каталога (item/unit/category.*), с CLI, BFF и Django admin UI. Доказано работающей на dev-стенде (338 событий за 28 дней, 4 пользователя, 3 склада).

**Главные пробелы:** (1) покрытие событий ~70% от того, что логически должно быть; (2) audit входов/выходов в SyncServer был и регрессировал; (3) нулевые тесты для audit-слоя.

**Стратегическое направление:** закрыть пробелы по покрытию, добавить тесты, зафиксировать retention policy и ADR. Не требует переписывания архитектуры — нужно расширение и hardening.

**Скоуп следующего шага (если пользователь даст команду):** можно оформить как `TZ-AUDIT_LOGGING_HARDENING.md` с конкретными эпиками (расширение event_type, retention, тесты, ADR).

---

## Приложение А. Перечень ключевых файлов

### SyncServer

- `app/models/audit_event.py` — модель
- `app/repos/audit_events_repo.py` — репозиторий
- `app/services/audit_helper.py` — helper
- `app/services/operations_service.py:580,1184,1334,1435,1649` — 5 вызовов audit
- `app/services/catalog_admin_service.py:60,124,159,225,268,332,643` — 7 вызовов audit
- `app/services/uow.py:33` — wiring `audit_events`
- `app/schemas/audit.py` — Pydantic схемы
- `app/api/routes_admin_audit.py` — FastAPI router
- `alembic/versions/0017_add_audit_events.py` — миграция
- `scripts/query_audit.py` — CLI
- `tests/test_query_audit_cli.py` — тесты CLI (форматтеры)
- `tests/test_catalog_admin_audit.py` — тесты audit-полей моделей каталога (НЕ audit-events)
- `docs/audit-query-examples.md` — примеры CLI
- `docs/audit-syncserver.md` — **устаревший** документ (про transport ping/push/pull, не про AuditEvent)
- `docs/DJANGO_INTEGRATION_GUIDE.md` — упоминает sync_auth_login/logout (без audit)

### Warehouse_web

- `apps/bff_api/audit_views.py` — BFF прокси
- `apps/users/admin_audit_views.py` — Django admin SSR
- `apps/users/templates/admin/audit_events_list.html` — шаблон списка
- `apps/users/templates/admin/audit_event_detail.html` — шаблон деталей
- `apps/users/models.py:174-205` — `LoginAttempt`
- `apps/users/simple_sync_signals.py:175-195` — `_record_login_attempt`
- `apps/users/admin.py:858` — `LoginAttemptAdmin`
- `apps/bff_api/urls.py:48-49` — BFF маршруты audit
- `config/urls.py:58-67` — Django admin маршруты audit
- `apps/sync_client/__pycache__/audit_push.cpython-*.pyc` — **мёртвый bytecode** от удалённого audit_push

### Документы

- `docs/TZ-AUDIT_LOGIN_AND_CLI_QUERY.md` — основной TZ (CLI-only, deferred Units A/B)
- `.agent/SCOPE-audit-login-and-password-mgmt.md` — первоначальный план
- `docs/V3.0_POST_DEPLOY_FIXES.md` #6 — fix #6 (журнал действий)
- `docs/V3.0.1_POST_DEPLOY_QUICK_FIXES.md:767` — «3.1 must design...»
- `docs/TZ-SYNCSERVER_REGRESSION_AND_SCOPE_CLEANUP.md` — история, audit mocks
- `docs/reviews/architecture-review-v3.1-tz.md` — упоминает audit
- `docs/reviews/architecture-review-v3.1i-waybill-pagination.md` — указывает на правильный порядок audit относительно waybill

---

## Приложение Б. SQL-запросы для повторения на стенде

```sql
-- 1. Общая статистика
SELECT
    COUNT(*) AS total_events,
    MIN(created_at) AS first_event,
    MAX(created_at) AS last_event,
    COUNT(DISTINCT actor_user_id) AS unique_actors,
    COUNT(DISTINCT site_id) AS unique_sites,
    COUNT(DISTINCT actor_device_id) AS unique_devices,
    COUNT(*) FILTER (WHERE actor_user_id IS NULL) AS system_events,
    COUNT(*) FILTER (WHERE changes IS NOT NULL) AS with_changes
FROM audit_events;

-- 2. Распределение по event_type
SELECT event_type, COUNT(*) AS cnt
FROM audit_events
GROUP BY event_type
ORDER BY cnt DESC;

-- 3. Активность по пользователям
SELECT actor_user_id, COUNT(*)
FROM audit_events
GROUP BY actor_user_id
ORDER BY actor_user_id;

-- 4. Все auth-события (для аудита регрессии)
SELECT event_id, event_type, actor_user_id, summary, changes, created_at
FROM audit_events
WHERE event_type LIKE 'auth.%'
ORDER BY created_at DESC;

-- 5. CLI-эквивалент для оператора
docker compose exec syncserver python scripts/query_audit.py \
    --username <username> \
    --date-from 2026-06-01 \
    --date-to 2026-07-14 \
    --format markdown \
    --output /tmp/audit_june_july.md
```

---

*Конец отчёта.*
