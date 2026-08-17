# TZ: SyncServer — фикс MissingGreenlet на PATCH/POST /api/v1/admin/sites

- **Issue:** [#20](https://github.com/steeltalon777/warehouse_solution-/issues/20) — «SyncServer: PATCH/POST /api/v1/admin/sites возвращает 500 (MissingGreenlet) — нет refresh после flush в SitesRepo»
- **Репозиторий:** `SyncServer/` (control-tower issue в `steeltalon777/warehouse_solution-`)
- **Дата:** 2026-08-17
- **Автор:** Architect
- **Статус:** In Progress (задача на доске), TZ готов к исполнению

## Execution strategy

- **🟡 Sequential**
- **Reason:** один репозиторий, один прод-файл (`app/repos/sites_repo.py`), один тестовый файл-фикстура паттерна, сильная связка «фикс → регрессионный тест». Параллелизм не нужен; объём — один исполнитель, один коммит.

## Execution checklist

- [x] 0. Context verified (issue #20 прочитан, корневая причина подтверждена по исходникам)
- [x] 1. Architecture boundaries confirmed (фикс только в `app/repos/`, контракт API не меняется)
- [x] 2. Новый регрессионный интеграционный тест добавлен и запущен на pre-fix коде: suite RED из-за PATCH → 500; POST guard остаётся GREEN; evidence сохранён
- [x] 3. Implementation: `refresh()` после `flush()` в `SitesRepo.update_site()` (bug fix) и `SitesRepo.create_site()` (consistency hardening)
- [x] 4. Ослабленная ассерция в `test_site_mutation_allows_root` ужесточена до `== 200`, workaround-комментарий удалён
- [x] 5. Integration tests с реальной БД complete после фикса (`python -m pytest` в контейнере стенда)
- [x] 6. Stand smoke: PATCH /api/v1/admin/sites/{id} → 200 на dev-стенде
- [x] 7. User scenario: переименование склада через Django-админку без `SyncServerInternalError`
- [x] 8. Regression: полный `python -m pytest` SyncServer зелёный
- [ ] 9. Issue #20 updated: комментарий с результатом, evidence и ссылкой на TZ публикует **архитектор или ревьюер** (исполнителям комментировать issues запрещено правилами GitHub Project); исполнитель передаёт текст evidence в отчёте; отдельные постоянные docs не меняются, если контракт/архитектура не изменились
- [ ] 10. Final acceptance review complete (таблица Evidence заполнена)

## Check rules

- Architect создаёт чек-лист и критерии приёмки.
- Executor отмечает пункты 2–8 только после фактического выполнения соответствующего пункта и прогона проверок. Пункт 2 (RED-прогон на pre-fix коде) выполняется ДО фикса из пункта 3 — это корректный порядок RED → FIX → GREEN.
- QA/верификатор отмечает пункт 10 только после сверки Evidence.
- Пропущенная проверка остаётся unchecked с указанием причины.

## Контекст и подтверждённая корневая причина

Проверено по исходникам 2026-08-17 (SyncServer, SQLAlchemy 2.0.47):

1. `app/models/site.py:24-34` — `created_at` и `updated_at` имеют серверные
   `server_default=func.now()`; `updated_at` дополнительно `onupdate=func.now()`.
2. `app/repos/sites_repo.py:26-64` — `create_site()` и `update_site()` делают только
   `await self.session.flush()` и возвращают ORM-объект. Это единственный репозиторий
   мутаций без `refresh()`: в `catalog_repo.py` (6 мест), `devices_repo.py:72`,
   `users_repo.py:91,130,138`, `user_access_scopes_repo.py:156,186,275` паттерн
   `flush() → refresh()` уже используется.
3. `app/api/routes_admin_sites.py:50,63` — `SiteResponse.model_validate(...)` вызывается
   ПОСЛЕ выхода из `async with uow`. `app/services/uow.py:78-82` коммитит в `__aexit__`,
   поэтому 500 возникает уже после коммита — данные сохраняются, клиент получает ошибку.
4. `app/core/db.py:27-30` — `SessionFactory(..., expire_on_commit=False)`: уже загруженные
   атрибуты переживают коммит, поэтому GET/list-эндпоинты работают.

### Уточнение к тексту issue (эмпирически проверено)

- **PATCH падает всегда**: после UPDATE значение `updated_at` от `onupdate=func.now()`
  не возвращается без RETURNING/refresh — атрибут expired, ленивая подгрузка вне
  greenlet-контекста даёт `MissingGreenlet` → `pydantic ValidationError` → 500.
  Существующий тест `tests/test_admin_root_permissions.py::test_site_mutation_allows_root`
  это документирует: ассерция PATCH ослаблена до `!= 403` с комментарием
  «500 is a pre-existing bug ... out of scope for this task».
- **POST фактически работает** (возвращает 200, проверено прогоном 2026-08-17):
  SQLAlchemy 2.0 для INSERT автоматически использует `INSERT ... RETURNING`
  для серверных дефолтов, поэтому `created_at`/`updated_at` оказываются загружены
  сразу после flush. Утверждение issue о падении POST не подтвердилось.
  `refresh()` в `create_site()` добавляется всё равно — как выравнивание по
  общему паттерну репозиториев и защита от смены поведения драйвера/ORM.

## Scope

### В объёме

| Файл | Изменение |
|---|---|
| `SyncServer/app/repos/sites_repo.py` | `update_site()`: `await self.session.refresh(site)` после `flush()` как bug fix; `create_site()`: такой же `refresh()` как consistency hardening |
| `SyncServer/tests/test_admin_sites_greenlet_regression.py` (новый) | Регрессионный интеграционный тест: PATCH → 200 с корректным `updated_at`, POST → 200 с `created_at`/`updated_at` |
| `SyncServer/tests/test_admin_root_permissions.py` | Ужесточить ассерцию PATCH в `test_site_mutation_allows_root` до `== 200`, удалить workaround-комментарий |

### Вне объёма

- Другие admin-роуты (`routes_admin_devices`, `routes_admin_users`, `routes_admin_access`,
  `routes_admin_audit`) — их репозитории уже используют `refresh()` (проверено),
  системный аудит паттерна «`model_validate` вне `uow`» — отдельный follow-up.
- Django-сторона (`Warehouse_web`) — баг целиком внутри SyncServer.
- Изменение контракта `SiteResponse` / схемы БД / миграции — не требуются.
- Деплой на прод — отдельное решение пользователя после фикса.

## Реализация

`SyncServer/app/repos/sites_repo.py`:

```python
# create_site(): consistency hardening после self.session.add(site) / await self.session.flush()
await self.session.refresh(site)
return site

# update_site(): bug fix после await self.session.flush() внутри if site:
await self.session.refresh(site)
return site
```

Никаких других изменений в сервисном слое (`AdminSitesService`) и роутах не требуется.

## Test ladder

| # | Уровень | Применимо | Что именно |
|---|---|---|---|
| 1 | Static checks | ✅ | `python -m compileall app/repos/sites_repo.py` (ruff в контейнере не установлен); миграции не затрагиваются |
| 2 | Unit tests | ❌ | Логика тривиальна, изолированный unit-тест не нужен |
| 3 | Component tests | ❌ | Покрыто интеграционным тестом через HTTP-клиент |
| 4 | Integration tests (реальная БД) | ✅ | RED → FIX → GREEN: сначала добавить новый регрессионный тест и запустить его на pre-fix коде (suite RED из-за PATCH → 500; POST guard GREEN), сохранить evidence, затем внести фикс и повторить прогон; также ужесточить `test_site_mutation_allows_root` |
| 5 | Stand smoke | ✅ | PATCH `/api/v1/admin/sites/{id}` → 200 на dev-стенде |
| 6 | UI automation | ⚠️ опционально | Playwright-сценарий переименования склада через Django-админку, если стенд и e2e-инфраструктура доступны; иначе — ручной user scenario (п. 7) |
| 7 | User scenarios | ✅ | Переименование склада в Django-админке (`/admin/users/site/{id}/change/`) сохраняется без `SyncServerInternalError` |
| 8 | Regression | ✅ | Полный `python -m pytest` в SyncServer |
| 9 | Acceptance review | ✅ | Evidence-таблица ниже |

### Команды проверок

```bash
# Шаг RED — выполнить ПОСЛЕ добавления regression test, но ДО изменения SitesRepo:
docker exec warehouse_syncserver python -m pytest tests/test_admin_sites_greenlet_regression.py -q
# Ожидание: suite RED из-за PATCH → 500; POST guard должен оставаться GREEN.
# Результат сохранить в Evidence до внесения фикса.

# Шаг GREEN — после изменения SitesRepo:
docker exec warehouse_syncserver python -m pytest tests/test_admin_sites_greenlet_regression.py tests/test_admin_root_permissions.py -q
docker exec warehouse_syncserver python -m pytest -q   # полный прогон

# Stand smoke должен быть обратимым.
# 1) Получить текущее имя выбранного dev-site и сохранить как <original_name>.
# 2) Временно переименовать site и проверить 200:
docker exec warehouse_syncserver sh -c 'curl -s -o /dev/null -w "%{http_code}" -X PATCH \
  http://localhost:8000/api/v1/admin/sites/<id> \
  -H "X-User-Token: $SYNC_ROOT_USER_TOKEN" -H "Content-Type: application/json" \
  -d "{\"name\": \"__smoke_sites_refresh__\"}"'
# Ожидание: 200

# 3) Сразу вернуть исходное имя и снова проверить 200:
docker exec warehouse_syncserver sh -c 'curl -s -o /dev/null -w "%{http_code}" -X PATCH \
  http://localhost:8000/api/v1/admin/sites/<id> \
  -H "X-User-Token: $SYNC_ROOT_USER_TOKEN" -H "Content-Type: application/json" \
  -d "{\"name\": \"<original_name>\"}"'
# Ожидание: 200. После smoke данные dev-стенда должны быть восстановлены.
```

Проверено 2026-08-17: `SYNC_ROOT_USER_TOKEN` задан в контейнере `warehouse_syncserver`
(значение не печатать). Fallback, если токен отозван: smoke выполняется через
Django-админку (user scenario, пункт 7), а прямой curl-шаг помечается skipped.

## Stand

- Docker-стенд из корня `/home/makc/AI_sandbox/warehouse_solution` (`make up`):
  `warehouse_syncserver` (:8000), `warehouse_web` (:8001), `warehouse_postgres` (:5432).
- Health checks: `GET http://localhost:8000/api/v1/health`, `GET http://localhost:8001/healthz/`.
- Интеграционные тесты используют изолированную схему `test_sync_*` в БД стенда
  (создаётся и удаляется фикстурой `session_factory`), seed — фикстуры `conftest.py`.
- Env-переменные (только имена): `DATABASE_URL`, `SYNC_ROOT_USER_TOKEN`, `DJANGO_SETTINGS_MODULE`, `SECRET_KEY`.
- Reset: `make restart`; при проблемах — `make build-sync`.

## Acceptance criteria

1. `PATCH /api/v1/admin/sites/{id}` возвращает 200 и тело `SiteResponse` с обновлёнными
   полями и валидным `updated_at` (>= значения до обновления).
2. `POST /api/v1/admin/sites` возвращает 200 с заполненными `created_at`/`updated_at` (регрессионный guard; до фикса POST уже работает).
3. Зафиксирован RED → FIX → GREEN: новый интеграционный suite до изменения `SitesRepo` красный из-за PATCH → 500, после фикса зелёный; POST guard остаётся зелёным на обоих этапах.
4. `update_site().refresh()` рассматривается как bug fix; `create_site().refresh()` — как consistency hardening для единого repository mutation pattern.
5. Полный `python -m pytest` SyncServer зелёный.
6. Stand smoke обратим: после временного rename исходное имя dev-site восстановлено.
7. Переименование склада через Django-админку проходит без ошибки (user scenario).
8. Контракт `SiteResponse` и схема БД не изменены.
9. Коммит только в `dev`, только файлы из Scope, после зелёных тестов; постоянные docs не меняются без отдельной причины.

## Architecture review (self stress-test, 2026-08-17)

**Verdict: Approved**

- 🔴 Blockers: нет. Фикс — минимально возможное изменение (2 строки), повторяющее
  устоявшийся в codebase паттерн; контракт API и данные не меняются; откат тривиален (revert).
- 🟡 Warnings:
  1. Паттерн «`model_validate` вне `async with uow`» потенциально хрупок для любых
     будущих сущностей с серверными `onupdate`-колонками. Рекомендован follow-up аудит
     admin-роутов (вне объёма этого TZ).
  2. Issue утверждает падение POST — не подтвердилось (SQLAlchemy 2.0 implicit
     INSERT..RETURNING). В issue будет оставлен комментарий с уточнением.
- 🔵 Notes: `refresh()` добавляет один SELECT на мутацию — пренебрежимо для
     админских операций низкой частоты.

## Evidence (заполняет исполнитель)

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|
| Regression test (pre-fix RED) | `docker exec warehouse_syncserver python -m pytest tests/test_admin_sites_greenlet_regression.py -v` до изменения `SitesRepo` | 1 failed, 1 passed | PATCH → 500 MissingGreenlet; POST guard GREEN |
| Integration tests (post-fix) | `docker exec warehouse_syncserver python -m pytest tests/test_admin_sites_greenlet_regression.py tests/test_admin_root_permissions.py -v` | 13 passed | All green, assertion tightened to == 200 |
| Full pytest | `docker exec warehouse_syncserver python -m pytest -q --tb=line` | 947 passed, 3 skipped, 6 xfailed | 759s, no failures |
| Stand smoke PATCH | reversible rename + restore через Python httpx из контейнера | RENAME → 200; RESTORE → 200 | name restored: sa-smoke-847 site |
| User scenario (Django admin) | `SyncServerRootAdminClient.list_sites/patch` из warehouse_web контейнера | rename → 200, restore → 200 | name restored: sa-smoke-847 site |

## Риски и follow-ups

- **Follow-up (отдельная задача):** аудит остальных admin-роутов на паттерн
  «ORM-объект с серверными дефолтами сериализуется вне `uow`».
- **Деплой:** фикс безопасен для данных (поведение записи не меняется, меняется только
  ответ); деплой на прод — после подтверждения пользователя (на проде данные уже
  переименованы корректно, чинится только код ответа).
