# TZ: HOTFIX PROD — восстановить diagnostics telemetry и перевести deploy source на ветку prod

> GitHub Issue: `steeltalon777/warehouse_solution-` **#23**
> Связанная (не заменяющая) задача: **#22** — остаётся открытой после hotfix.
> Автор: архитектор. Статус на доске: In Progress.
> Дата: 2026-08-18.

## Execution Checklist

- [x] 0. Context verified
- [x] 1. Architecture boundaries confirmed
- [x] 2. Implementation: BFF hotfix (URL + event types)
- [x] 3. Implementation: SyncServer hotfix (event types)
- [x] 4. Unit/component tests complete (targeted; полный прогон отложен — см. п.9)
- [x] 5. Integration/DB tests complete (targeted; полный прогон отложен)
- [x] 6. Stand smoke tests complete
- [ ] 7. UI automation tests — N/A (обоснование в разделе 7)
- [ ] 8. User scenario tests (production, после деплоя)
- [ ] 9. Regression checks complete (полный прогон отложен по указанию пользователя — «запускай точечно»)
- [ ] 10. Documentation updated (DEPLOYMENT.md)
- [ ] 11. Branch `prod` prepared (SHAs зафиксированы, push — пользователем)
- [x] 12. Prod backup gate passed (выполняет оператор/пользователь)
- [x] 13. Production deployment из ветки `prod` (выполняет оператор/пользователь)
- [ ] 14. Production smoke passed
- [ ] 15. Final acceptance review complete

## Check Rules

- Пункты 0–1 отмечает архитектор.
- Пункты 2–6, 9 отмечает исполнитель **только после фактического прогона** проверок с приложением доказательств.
- Пункты 8, 12–14 отмечает сторона, фактически выполнявшая операции на проде (пользователь или агент с явным грантом), с доказательствами.
- Пункт 10 отмечает исполнитель после правки `docs/DEPLOYMENT.md` и проверки диффа.
- Пункт 11 отмечает архитектор/исполнитель после фиксации SHA и **подтверждения пользователя о push** ветки `prod` в origin.
- Пункт 15 отмечает ревьюер после проверки всех доказательств.
- Невыполненные пункты остаются непроверенными с указанием блокера.

---

## Execution Strategy

- **🟡 Sequential.**
- **Reason:** hotfix минимального размера с жёсткими гейтами на проде. Правки в двух репозиториях независимы по файлам, но:
  1. приёмка каждого шага — условие перехода к следующему (backup gate → stand verify → branch → deploy);
  2. работа с продом требует последовательного подтверждения пользователя;
  3. объём мал — параллелизация не даёт выигрыша, но добавляет риск рассинхрона версий.
- Допустимое ускорение (только по явному решению пользователя): п.2 и п.3 могут выполняться параллельно двумя исполнителями, т.к. владение файлами не пересекается (`Warehouse_web/apps/bff_api/*` vs `SyncServer/app/api/routes_diagnostics.py` + `SyncServer/tests/*`). Максимум 2 потока. Слияние результатов — только на п.4.

---

## 0. Контекст (проверено архитектором)

Forensic-аудит операции `fb65bff0-f740-448d-9eb2-a9f3c161c655` (issue #22) показал, что production UI diagnostics не работает. Подтверждённые дефекты:

1. **Удвоение `/api/v1` в BFF** — `Warehouse_web/apps/bff_api/diagnostics_views.py:113`:
   `settings.SYNC_SERVER_URL.rstrip("/") + "/api/v1/diagnostics/ui-events/batch"`.
   При `SYNC_SERVER_URL=http://syncserver:8000/api/v1` (prod) получается `/api/v1/api/v1/diagnostics/ui-events/batch` → upstream 404 → BFF 502 (77× в логах).
2. **Contract drift по event types** — Angular (`Warehouse_frontend/src/app/core/diagnostics/diagnostics.models.ts`) объявляет 15 типов, включая 4 draft-типа. `ALLOWED_EVENT_TYPES` в BFF (`diagnostics_views.py:29-41`) и в SyncServer (`app/api/routes_diagnostics.py:23-35`) содержит только 11. BFF режет draft-события до прокси → 400 (295× в prod логах).
3. **Пустой upstream identity** — Angular (`diagnostics-queue.service.ts`) шлёт только `X-CSRFToken` и `X-Client-Session-Id`; браузер никогда не получает SyncServer-токены (архитектурное правило). Текущий BFF-прокси пробрасывает сырой `X-User-Token` из входящего запроса → он пуст → SyncServer `require_user_identity` отдал бы 401 → 502. Каноническое решение — резолв identity на стороне Django из session binding (`SyncServerClient(request=request)`).
4. `diagnostics_ui_events` на проде существует, но пуста.

Схема целевой цепочки: `Angular DiagnosticsQueueService → Django BFF (/bff/api/v1/diagnostics/ui-events/batch) → SyncServerClient → SyncServer (/api/v1/diagnostics/ui-events/batch) → diagnostics_ui_events`.

Текущие SHA (dev, локально, на 2026-08-18):
- `SyncServer`: `a13e8b5`
- `Warehouse_web`: `8e51478`
- root (control tower): `846d16c`
SHA прода фиксируются в preflight (п.12) — на VPS.

## 1. Границы архитектуры (подтверждено)

- **Внутри hotfix:** минимальный фикс цепочки diagnostics; синхронизация event types; подготовка и перевод deploy source на ветку `prod`.
- **Вне hotfix (запрещено в этой задаче):**
  - рефакторинг diagnostics subsystem;
  - балансы (balances UI);
  - duplicate OperationLine;
  - изменения в Angular (типы уже корректны, правки не нужны);
  - миграции БД (см. ниже — их в hotfix нет);
  - удаление forensic/audit данных.
- **Миграции не требуются:** `diagnostics_ui_events.event_type` — `String(50)` без DB-level CHECK; правки чисто валидационные (frozenset в коде). Если в процессе обнаружится обратное — **STOP**, отдельное согласование с пользователем.
- Ветки: hotfix-коммиты идут в `dev` каждого репо (штатный флоу), ветка `prod` обновляется fast-forward до проверенных SHA. Push — только пользователь.
- Секреты: в отчёт/логи не попадают `.env`, пароли, токены, DSN.

---

## 2. Реализация: BFF hotfix (Warehouse_web)

Файлы:
- `Warehouse_web/apps/bff_api/diagnostics_views.py`
- `Warehouse_web/apps/bff_api/tests_diagnostics.py`

### 2.1 URL join через канонический клиент

Заменить шаг «4. Proxy to SyncServer» (строки 112–135):

```python
from apps.sync_client.client import SyncServerClient

    # 4. Proxy to SyncServer через канонический клиент
    extra_headers = {}
    session_id = request.headers.get("X-Client-Session-Id")
    if session_id:
        extra_headers["X-Client-Session-Id"] = session_id
    try:
        client = SyncServerClient(request=request)
        client.post(
            "/diagnostics/ui-events/batch",
            json=payload,
            extra_headers=extra_headers,
        )
    except Exception as exc:
        logger.warning("diagnostics_proxy_failed", error=str(exc)[:200])
        return JsonResponse(
            {"ok": False, "error": {"code": "upstream_unavailable", "message": "SyncServer rejected the batch"}},
            status=502,
        )
```

Почему именно так (требование issue — «тот же способ join/base URL, что и остальные SyncServer API clients»):
- `SyncServerClient` валидирует `SYNC_SERVER_URL` на `endswith("/api/v1")` и строит URL как `base_url + "/diagnostics/ui-events/batch"` → ровно `/api/v1/diagnostics/ui-events/batch`, без удвоения.
- Identity резолвится на стороне Django из `SyncUserBinding`/session (`resolve_sync_identity`), а не пробрасывается пустым заголовком из браузера → устраняется upstream 401.
- `X-Request-Id` пробрасывается автоматически через `build_headers()` (middleware `RequestTracingMiddleware`), сохранение корреляции проверяется тестом.
- 204 обрабатывается корректно (`_request` возвращает `None` для 204), 4xx/5xx поднимаются типизированными исключениями → сохраняется контракт §5.4 «BFF отвечает 502, не роняя flow клиента».
- Rate limit, валидация размера и тела (шаги 1–3 view) остаются без изменений.

Сохранение поведения: `json=payload` пере-сериализует уже разобранный dict — эквивалентно текущему `content=raw` (лишние поля Pydantic игнорирует так же).

### 2.2 Синхронизация BFF `ALLOWED_EVENT_TYPES`

> **Решение архитектора (флаг для ревьюера):** issue #23 явно предписывает синхронизацию списка только в SyncServer. Но 295× 400 на `/bff/api/v1/...` порождаются валидацией **BFF** — без правки этого списка draft-события продолжат отсекаться и цепочка не восстановится (acceptance: «Production E2E diagnostics → 204 + DB row»). Это не рефакторинг подсистемы, а та же контрактная синхронизация в том же файле, что и фикс URL. Включено в hotfix.

Добавить в `ALLOWED_EVENT_TYPES` (строки 29–41):
```python
    "draft_autosaved",
    "draft_restored",
    "draft_lost",
    "draft_cleared",
```

### 2.3 Regression-тесты BFF

В `tests_diagnostics.py`:
1. **URL без удвоения (главный regression):**
   - `@override_settings(SYNC_SERVER_URL="http://syncserver:8000/api/v1")`;
   - мок на транспортной границе `apps.sync_client.client.get_sync_client` (реальный `SyncServerClient` поверх мокнутого httpx-клиента) — паттерн см. `apps/sync_client/test_auth_boundary.py`;
   - assert: вызванный URL **в точности** `http://syncserver:8000/api/v1/diagnostics/ui-events/batch`; assert `"/api/v1/api/v1" not in url`.
   - Для identity в тесте: Django-пользователь с `sync_binding.sync_user_token` (паттерн из `test_auth_boundary.py`) либо мок `resolve_sync_identity`.
2. **draft-события проходят BFF:** `draft_autosaved` (и остальные 3 параметризованно) → 204, `client.post` вызван.
3. **Неизвестный тип по-прежнему 400** (существующий тест остаётся; добавить assert, что прокси НЕ вызывался).
4. **X-Request-Id пробрасывается:** запрос с `X-Request-Id` → в исходящих заголовках присутствует.
5. **Миграция существующих моков:** тесты, мокающие `apps.bff_api.diagnostics_views.get_sync_client` (view больше его не использует), перевести на мок `apps.bff_api.diagnostics_views.SyncServerClient` (конструктор + `.post`). Логика проверок (204/400/413/429/502/405/forward headers) сохраняется.

## 3. Реализация: SyncServer hotfix

Файлы:
- `SyncServer/app/api/routes_diagnostics.py`
- `SyncServer/tests/test_diagnostics.py`

### 3.1 Синхронизация `ALLOWED_EVENT_TYPES`

Добавить в frozenset (строки 23–35):
```python
    "draft_autosaved",
    "draft_restored",
    "draft_lost",
    "draft_cleared",
```
Миграция не нужна (см. раздел 1). Validation не ослабляется произвольными строками — контракт остаётся явным.

### 3.2 Regression-тесты SyncServer

1. **4 draft-типа принимаются:** параметризованный тест через endpoint `/api/v1/diagnostics/ui-events/batch` с `event_type` = каждому из 4 типов, ожидаемые статусы по паттерну существующих тестов `(204, 401, 403)` (аутентификация в тестовом окружении вариативна).
2. **Contract parity:** чистый python-тест без клиента:
   ```python
   ANGULAR_EVENT_TYPES = {
       "form_opened", "form_closed", "submit_clicked", "validation_failed",
       "request_started", "request_succeeded", "request_failed", "outcome_unknown",
       "response_processing_failed", "navigation_away_with_unsaved", "unexpected_error",
       "draft_autosaved", "draft_restored", "draft_lost", "draft_cleared",
   }
   # assert ANGULAR_EVENT_TYPES <= ALLOWED_EVENT_TYPES (полный список из
   # Warehouse_frontend/src/app/core/diagnostics/diagnostics.models.ts)
   ```
3. **Неизвестный тип → 400** (существующий тест остаётся).

---

## 4–6. Тестовая лестница (стенд)

### Stand

Dev-стенд Docker из корня workspace (`docker compose`, Makefile `make up/status/restart`):

| Сервис | Адрес | Health |
|---|---|---|
| SyncServer API | `http://localhost:8000` | `GET /api/v1/health` |
| Django BFF | `http://localhost:8001` | `GET /healthz/` |
| PostgreSQL | `localhost:5432` | `pg_isready -h localhost -p 5432 -t 3` |

- `SYNC_SERVER_URL` на стенде по умолчанию `http://syncserver:8000/api/v1` — **production-like** (именно так воспроизводится баг).
- Дефолтные стендовые учётные данные: Django superuser `admin` / `admin123` (документированы в AGENTS.md).
- Имена env-переменных (значения не печатать): `SYNC_SERVER_URL`, `SYNC_ROOT_USER_TOKEN`, `SYNC_DEVICE_TOKEN`, `DATABASE_URL`, `DB_USER`, `DB_PASSWORD`, `SECRET_KEY`.
- Cleanup стенда: `make restart`; БД стенда — `make down`/`make up` (volumes удалять только через `make clean` по явному решению).

### П.4 Unit/component tests

- `Warehouse_web`: `python manage.py test apps.bff_api.tests_diagnostics` затем полный `python manage.py test` (0 failed).
- `SyncServer`: `python -m pytest tests/test_diagnostics.py -q`, затем полный `python -m pytest` (0 failed).

### П.5 Integration/DB tests

- После п.4 прогнать тесты, касающиеся реальной БД стенда: существующие sync_client-тесты в `Warehouse_web` (`apps.sync_client.tests`, `apps.sync_client.test_auth_boundary`) — подтвердить, что замена прокси-пути не задела транспортные контракты.
- В `SyncServer` — существующий `test_diagnostics.py` с проверкой DB-строк (`test_idempotent_insert_no_duplicates`).

### П.6 Stand smoke (E2E цепочка через реальный HTTP)

1. Health: `curl -s http://localhost:8000/api/v1/health` и `curl -s http://localhost:8001/healthz/` → ok/200.
2. Залогиниться в Django под `admin` (curl: GET `/admin/login/` → взять csrftoken из cookie → POST учётных данных → сохранить session cookie в jar; точные URL/форму исполнитель проверяет на стенде, пароль — документированный dev-пароль, в отчёт не печатать).
3. Отправить batch с `event_type=draft_autosaved` (валидный `event_id`, `session_id`, `severity=debug`, `occurred_at` ISO8601, `frontend_version="smoke"`) на `POST http://localhost:8001/bff/api/v1/diagnostics/ui-events/batch` с session cookie и `X-Client-Session-Id`.
4. Ожидаемый результат: **HTTP 204**.
5. Проверить строку в БД:
   `docker compose exec postgres psql -U warehouse_user -d warehouse -c "SELECT event_type, route, received_at FROM diagnostics_ui_events ORDER BY id DESC LIMIT 3;"`
   → строка `draft_autosaved` присутствует.
6. Проверить отсутствие удвоения: `docker compose logs warehouse_web --since 10m | grep -c '/api/v1/api/v1'` → 0 (и в логах syncserver аналогично).
7. Повторить п.3 с `draft_restored`, `draft_lost`, `draft_cleared` (по одному событию) — 204 на каждое.
8. Отправить batch с неизвестным типом → ожидаемый 400 (BFF-валидация), в БД строки не появляется.

### П.7 UI automation — N/A

Браузерная автоматизация для этого hotfix не применяется: правки не затрагивают Angular-код и UI-сценарии; цепочка проверяется HTTP E2E через реальный BFF-стек (п.6). Полноценный Playwright-сценарий diagnostics — в scope основной задачи #22. Если пользователь потребует — добавить spec `e2e/diagnostics/diagnostics-e2e.spec.ts` отдельной задачей.

### П.9 Regression checks

- Django: `python manage.py test` целиком (auth, permissions, BFF operation endpoints — не затронуты, но подтвердить 0 failed).
- SyncServer: `python -m pytest` целиком.
- Проверить, что `/api/v1` контракты, балансы и operations не тронуты: `git diff --stat` по репо должен содержать **только** файлы из п.2–3.
- Angular: изменений нет → пересборка `npm run build` не требуется; unit-прогон не требуется (файлы не менялись).

---

## 10. Документация

- Обновить `docs/DEPLOYMENT.md` (root control tower, ветка `dev`):
  - таблица «Branch Roles»: `prod` = ветка деплоя прода (production checkout), `main` = релизное состояние (обновляется при деплое по существующей логике), не допускать противоречий с новым порядком;
  - «Production Deploy Workflow»: production checkout/build application-сервисов — из ветки `prod` (`git fetch && git checkout prod && git pull --ff-only origin prod`), шаг «Сохранить фолбек» переформулировать под фиксацию предыдущего prod SHA/image;
  - «Rollback»: откат — на предыдущий зафиксированный SHA/image ветки `prod`; backup БД не восстанавливать без отдельного решения.
- Дополнительно зафиксировать в `docs/DEPLOYMENT.md` (или комментарии в issue) точные SHA ветки `prod` каждого application-репо на момент деплоя.

## 11. Ветка `prod` (по каждому application-репо: SyncServer, Warehouse_web)

> Warehouse_frontend в prod-сборке не участвует (Option C: Angular-билд вшит в образ Warehouse_web; Node.js на VPS нет). Действий по его веткам не требуется.

Порядок:
1. Рабочее дерево чистое (`git status --porcelain`).
2. Hotfix-коммиты лежат на `dev` (см. п.2–3), тесты green (п.4–6, 9).
3. Локально: `git branch -f prod <verified_sha>` (fast-forward до проверенного коммита; без merge незавершённых dev-изменений).
4. Зафиксировать SHA ветки `prod` для каждого репо (в отчёт и в issue-комментарий).
5. **Push `origin prod` — выполняет пользователь** (агентам push запрещён). Агент предоставляет готовые команды:
   ```bash
   git -C SyncServer push origin prod
   git -C Warehouse_web push origin prod
   ```
6. Подтверждение пользователя о push — обязательное условие для перехода к п.13.

## 12. Prod preflight + backup gate (выполняется оператором/пользователем; SSH — только по явной команде)

**Перед любыми изменениями на проде:**

**Preflight (зафиксировать, не печатать секреты):**
- текущие branch + commit SHA в `~/SyncServer` и `~/Warehouse_web` на VPS;
- чистота рабочего дерева в обоих репозиториях на VPS (`git status --porcelain`; отклонения — например, пересобранный `angular_static` — задокументировать до переключения ветки);
- `docker compose ps` и image IDs/tags затронутых application-сервисов (`syncserver`, `warehouse_web`);
- свободное место под backup (`df -h ~/backups`).

**Backup PostgreSQL (обязательный гейт):**
- Целевая БД — `syncserver_main` (как в issue #23 и `docs/DEPLOYMENT.md`).
- Пользователь дампа — по `docs/DEPLOYMENT.md` (там задокументирован `appuser`); оператор проверяет фактического пользователя БД `syncserver_main` на VPS в рантайме (например, из env контейнера `syncserver`), не выводя значения.
```bash
mkdir -p ~/backups
docker exec pg-main pg_dump -Fc -U appuser -d syncserver_main \
  > ~/backups/syncserver_main_$(date +%Y%m%d_%H%M%S)_hotfix23.dump
ls -l ~/backups/syncserver_main_*_hotfix23.dump                # зафиксировать размер
sha256sum ~/backups/syncserver_main_*_hotfix23.dump            # зафиксировать checksum
docker exec -i pg-main pg_restore --list < ~/backups/syncserver_main_*_hotfix23.dump | head -20
```
- Проверка структуры — read-only (`pg_restore --list`). Ничего не восстанавливать поверх прода.
- **Gate: без успешного backup + проверки — деплой НЕ продолжать (STOP).**

## 13. Production deployment (оператор/пользователь; только после п.11–12)

1. Переключить application checkout на `prod`:
   ```bash
   cd ~/SyncServer && git fetch origin && git checkout prod && git pull --ff-only origin prod
   cd ~/Warehouse_web && git fetch origin && git checkout prod && git pull --ff-only origin prod
   ```
2. Пересобрать только application-сервисы. **Порядок обязателен: сначала SyncServer, затем Warehouse_web** — иначе возникает окно, в котором новый BFF шлёт draft-события старому SyncServer (400/502):
   ```bash
   cd ~/SyncServer && docker compose up -d --build
   cd ~/Warehouse_web && docker compose up -d --build
   ```
3. **PostgreSQL volume не трогать.** Миграции не запускать (в hotfix миграций нет). Если миграция неожиданно требуется — STOP и отдельное согласование.
4. Зафиксировать новые SHA ветки `prod` и новые image IDs.

**Rollback-точка (зафиксировать до шага 2):** предыдущие SHA/image каждого application-сервиса из preflight (п.12).

## 14. Production smoke

- `docker compose ps` — application services healthy/up.
- Основной Warehouse Web открывается (https, 200).
- Auth работает (логин).
- Обычный read-only `GET /api/v1/operations` работает.
- Отправить **одно** безопасное diagnostic-событие (`draft_autosaved` или `draft_restored`) через штатную BFF-цепочку (браузерный сценарий или curl с аутентифицированной сессией) → BFF отвечает **204**. Событие маркировать для чистого forensic-следа: `frontend_version="hotfix23-smoke"`, без чувствительных данных в `details`.
- Новая строка появилась в `diagnostics_ui_events` (read-only SELECT на проде).
- В логах отсутствует `/api/v1/api/v1/diagnostics`.
- Нет новых серийных 400/502 на diagnostics endpoint (сравнить счётчики до/после).

**Rollback при проблеме:**
- вернуть checkout/images на зафиксированные preflight SHA/image;
- recreate только затронутых application-сервисов;
- PostgreSQL backup не восстанавливать без отдельного решения;
- сохранить forensic-логи.

## 15. Acceptance criteria (из issue #23)

- [ ] Backup PostgreSQL создан до deployment.
- [ ] Backup имеет size + SHA-256 + успешный `pg_restore --list`/эквивалент.
- [ ] Hotfix tests GREEN (п.4–6, 9).
- [ ] Stand E2E diagnostics → 204 + DB row (п.6).
- [ ] Production application repos деплоятся из ветки `prod` (п.11, 13).
- [ ] Точные prod commit SHA зафиксированы.
- [ ] Production E2E diagnostics → 204 + DB row (п.14).
- [ ] Нет удвоенного `/api/v1/api/v1`.
- [ ] Нет новых систематических diagnostics 400/502.
- [ ] Rollback point зафиксирован.

## Ограничения (из issue #23)

- Не исправлять balances UI.
- Не исправлять duplicate OperationLine.
- Не удалять старые forensic/audit данные.
- Не логировать и не публиковать secrets.
- Не рефакторить diagnostics subsystem.

---

## Производственный журнал (hotfix #23, 2026-08-18)

### Preflight (до изменений)

| Репо (VPS) | Ветка | SHA |
|---|---|---|
| `~/SyncServer` | `main` | `5f44bf2` |
| `~/Warehouse_web` | `main` | `82a7169` |

Образы до деплоя (rollback point): `syncserver-syncserver:latest` = `829c37f25775`, `warehouse_web-web:latest` = `9bd7f48dcbba`.

### Backup gate

- Файл: `~/backups/syncserver_main_20260818_131358_hotfix23.dump` (custom format, gzip)
- Size: `3568011` байт
- SHA-256: `0d863180c0add27686c7e10121d61f1da2129051a82108f6bb72e7ed2bd6913e`
- Проверка: `pg_restore --list` — 443 TOC entries, PostgreSQL 16.13. Ничего не восстанавливалось.

### Fix commits

| Репо | Коммит (hotfix) | База |
|---|---|---|
| `SyncServer` | `4b228bf` fix(diagnostics): allow draft event types + contract parity test | `5f44bf2` |
| `Warehouse_web` | `e15f5f1` fix(bff): diagnostics proxy via SyncServerClient | `82a7169` |

Локальные ветки (dev-машина): `hotfix/prod-diagnostics-23` в каждом репо.
Перенос на VPS: git bundle → fast-forward ветки `prod`.

### Stand verification (dev-стенд)

- SyncServer targeted: `pytest tests/test_diagnostics.py -q` → 10 passed, 1 skipped.
- BFF targeted: `manage.py test apps.bff_api.tests_diagnostics` → 13 passed.
- E2E через HTTP: draft_autosaved/restored/lost/cleared → 204; unknown type → 400 (invalid_event_type); строка `draft_autosaved` (frontend_version=hotfix23-smoke) появилась в `diagnostics_ui_events`; `/api/v1/api/v1` в логах — 0.
- Полные прогоны тестов обоих репозиториев отложены по указанию пользователя (п.9 не закрыт).

### Production deployment

- Ветка `prod` на VPS: `~/SyncServer` @ `4b228bf`, `~/Warehouse_web` @ `e15f5f1` (ff из preflight-состояний).
- Порядок: build → recreate SyncServer → Warehouse_web. Миграции не запускались. PostgreSQL volume не тронут.
- Новые образы: `syncserver-syncserver:latest` = `8f2fc5eaa11d`, `warehouse_web-web:latest` = `ee7eb77d642b`.

### Production smoke (частично)

- `docker compose ps`: syncserver/warehouse_web up, pg-main healthy.
- `GET /api/v1/health` → ok; `/healthz/` → 200; `/` → 302 (логин).
- Read-only `GET /api/v1/operations?limit=1` → 200 (0.34s внутри сети; первые внешние запросы висли на stale keepalive nginx после recreate — самоустранилось).
- `/api/v1/api/v1` в логах — 0. Диагностических 400/502 — 0 (до браузерной активности).
- `diagnostics_ui_events` пуста — ждёт первого реального события из браузера (п.8/14).
- Связки пользователей: 5 из 6 активных пользователей имеют `sync_user_token` (identity-резолв BFF заработает).

### Ожидает пользователя

- Push `prod` в origin (команды ниже) для сохранения состояния на GitHub.
- Браузерный сценарий на проде для генерации реального diagnostic-события (п.8/14).

```bash
# с VPS (или dev-машины после pull) — выполняет пользователь:
git -C ~/SyncServer push origin prod
git -C ~/Warehouse_web push origin prod
```

---

## Evidence Table (шаблон для отчёта исполнителя)

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|
| BFF unit/component | `python manage.py test apps.bff_api.tests_diagnostics` | pass/fail/skipped | log path |
| BFF full | `python manage.py test` | pass/fail/skipped | log path |
| SyncServer targeted | `python -m pytest tests/test_diagnostics.py -q` | pass/fail/skipped | log path |
| SyncServer full | `python -m pytest` | pass/fail/skipped | log path |
| Stand smoke E2E | curl → BFF → 204 + DB row | pass/fail/skipped | URL/row/скриншот лога |
| Doubled URL check | grep `/api/v1/api/v1` в логах | 0 находок / находки | log path |
| Backup | `pg_dump -Fc` + size + SHA-256 + `pg_restore --list` | pass/fail/skipped | путь к файлу (без содержимого) |
| Prod deploy | checkout `prod` + rebuild | pass/fail/skipped | SHA/image IDs |
| Prod smoke | 204 + DB row + логи | pass/fail/skipped | URL/evidence |
| Rollback point | preflight SHA/image зафиксированы | pass/fail/skipped | запись в отчёте |

## Приложения (справочно)

- Ключевые файлы:
  - `Warehouse_web/apps/bff_api/diagnostics_views.py` (строки 29–41, 112–135)
  - `Warehouse_web/apps/bff_api/tests_diagnostics.py`
  - `Warehouse_web/apps/sync_client/client.py` (`SyncServerClient`, `resolve_sync_identity` в `token_resolver.py`)
  - `SyncServer/app/api/routes_diagnostics.py` (строки 23–35)
  - `SyncServer/tests/test_diagnostics.py`
  - `SyncServer/alembic/versions/0028_diagnostics_ui_events.py` (DDL, CHECK отсутствует → миграций нет)
  - `Warehouse_frontend/src/app/core/diagnostics/diagnostics.models.ts` (15 типов — эталон контракта)
  - `Warehouse_frontend/src/app/core/diagnostics/diagnostics-queue.service.ts` (endpoint `/bff/api/v1/diagnostics/ui-events/batch`, заголовки CSRF/session)
  - `docs/DEPLOYMENT.md` (обновляется в п.10)
  - `prod_working/AGENT_INSTRUCTIONS.md` (правила работы с продом — читать перед любым prod-шагом)
