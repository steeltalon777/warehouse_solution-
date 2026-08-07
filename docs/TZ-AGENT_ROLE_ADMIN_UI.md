# TZ-AGENT_ROLE_ADMIN_UI

**Статус:** готово к реализации
**Дата:** 2026-08-07
**Автор:** architect (по запросу пользователя; закрывает операционный gap после TZ-AGENT-ROLE-SYNCSERVER rev.2)
**Приоритет:** 🟡 средний (backend готов; админка отстаёт — кладовщик/root не может назначить `agent` через UI)
**Связанные документы:**
* ADR-0030 (`SyncServer/docs/adr/0030-agent-domain-role.md`) — базовое решение, Status: Accepted, **Implemented**
* `SyncServer/docs/TZ/TZ-AGENT-ROLE-SYNCSERVER.md` rev.2 — завершённая TZ, бэкенд готов
* `Functional and WorkLogik.md` §I/2.1.5 — `agent` как пятая роль
* `Role Matrix.md` — колонка agent
* `Warehouse_web/AGENTS.md` — стенд и verification matrix
* `docs/AGENT_TZ_WORKFLOW.md` — шаблон чек-листа и test ladder

---

## 0. Execution Checklist

### Implementation
- [x] 0. Контекст verified (TZ-AGENT-ROLE-SYNCSERVER §1.2, ADR-0030 §1 прочитаны)
- [x] 1. `apps/users/models.py` — добавить `AGENT = "agent", "LLM Agent"` в `Role` TextChoices
- [x] 2. `apps/users/migrations/0014_*.py` — миграция для смены choices (auto-generated через `makemigrations`)
- [x] 3. `apps/users/admin_forms.py::MANAGED_ROLE_CHOICES` — добавить `("agent", "LLM-агент")`
- [x] 4. `apps/users/admin_forms.py::SyncManagedUserAdminForm.clean` — для `role == "agent"` разрешить пустые `site_ids` и `default_site_id=None`
- [x] 5. `apps/users/services.py::ROLE_SCOPE_MAP` — добавить запись для `Role.AGENT`
- [x] 6. `apps/users/services.py::UserSyncService.prepare_sync` и `sync_user_to_remote` — для `role == "agent"` корректно формировать payload (default_site_id=None; scopes передать пустыми)
- [x] 7. `apps/common/permissions.py` — добавить `is_agent(user)` helper (опционально, для symmetry)
- [x] 8. `apps/users/admin.py::SyncManagedUserAdmin` — добавить `list_filter` по `sync_role` (`sync_binding__sync_role`, `is_active`, `is_superuser`)

### Tests
- [x] 9. Static checks: `python manage.py check`, `python manage.py makemigrations --check --dry-run` exit 0
- [x] 10. Unit tests: новые кейсы в `apps/users/tests/test_agent_role_admin.py` (новый файл, 22 теста A–G) — `Role.AGENT == "agent"`, `MANAGED_ROLE_CHOICES` содержит agent, `clean()` принимает пустые site_ids для agent, root всё ещё отклоняется, observer/storekeeper по-прежнему требуют хотя бы один site, helper `is_agent` корректно различает роли (agent=True, storekeeper=False, superuser=False, anonymous=False), CreationForm наследует agent-исключение
- [x] 11. Component tests: Django AdminTestCase (`force_login(superuser)`) — POST в admin add user с role=agent; POST change user с role=agent (через `apps.users.admin`, `apps.users.admin_forms`, `apps.users.services` mocks)
- [x] 12. Integration tests (DB-backed): создание agent через `UserSyncService.prepare_sync` и `sync_user_to_remote` с моком `service.client` → assert POST `/auth/sync-user` содержит `role=agent`, `default_site_id=None`; PUT `/admin/users/{id}/scopes` принимает `{"scopes": []}`. Регрессия: для `role=storekeeper` scopes генерируются по сайтам с `can_view=True, can_operate=True, can_manage_catalog=False`.
- [x] 13. Stand smoke: реальный стенд через Playwright — admin логинится в `/admin/`, открывает `/admin/auth/user/add/`, заполняет username/email/password/role=agent, сохраняет, верифицирует Django row (`sync_role=agent, default_site_id=NULL, site_ids=[]`, `sync_status=synced`), regression: `role=storekeeper` с пустыми сайтами → ошибка «Нужно выбрать хотя бы один склад»
- [x] 14. Regression: `python manage.py test apps.users` — все 151 тестов проходят (включая 22 новых)
- [x] 15. User scenario (через Playwright MCP): «root добавляет agent через Django admin → POST → 302 redirect на change page → row создан в auth_user + users_syncuserbinding (sync_role=agent, default_site_id=NULL, site_ids=[]) → SyncServer принял POST /auth/sync-user (200) и PUT /admin/users/{id}/scopes (200) со scopes=[]»
- [x] 16. Documentation: `INDEX.md` — ссылка на TZ, `MEMORY.md` — факт «agent role assignable через Django admin»

### Final
- [ ] 17. Final acceptance (QA verifier)

## Check Rules

* Архитектор (этот документ) создаёт чек-лист и критерии приёмки.
* Executor проверяет только после реализации и собственного прогона всех применимых уровней тестов (1-7).
* Если уровень недоступен (например, стенд недоступен) — оставить пустым с пометкой «стенд недоступен» в Evidence.
* Перед любым real-stand прогоном — Stand Availability Protocol из корневого `AGENTS.md` и `Warehouse_web/AGENTS.md`.
* Commit только в `dev`-ветку, по правилам `Warehouse_web/AGENTS.md`.

---

## 1. Контекст и мотивация

### 1.1. Проблема (операционный gap)

`TZ-AGENT-ROLE-SYNCSERVER` rev.2 завершён 2026-08-07: SyncServer принимает пятую доменную роль `agent` (миграция `0038_add_agent_role` применена на стенде). Однако в Django-админке (`http://localhost:8001/admin/`) роль `agent` **недоступна для назначения**:

* `apps/users/models.py::Role` (TextChoices) — 4 значения: ROOT, CHIEF_STOREKEEPER, STOREKEEPER, OBSERVER.
* `apps/users/admin_forms.py::MANAGED_ROLE_CHOICES` (строки 31-35) — 3 значения (root исключён из admin-формы по дизайну): CHIEF_STOREKEEPER, STOREKEEPER, OBSERVER. **AGENT отсутствует.**
* `apps/users/admin_forms.py::SyncManagedUserAdminForm.clean` (строка 111) — `if not site_ids_list: raise ValidationError("Нужно выбрать хотя бы один склад.")` — требует хотя бы один сайт, что для agent не имеет смысла (он global, scope-independent — см. ADR-0030 §4.3, TZ-AGENT-ROLE-SYNCSERVER §4.3).

### 1.2. Текущий workaround

Provisioning agent-user возможен только через прямой вызов SyncServer API под root-токеном:

```bash
curl -X POST http://localhost:8000/api/v1/auth/sync-user \
  -H "X-User-Token: $ROOT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"id": "<uuid>", "username": "llm_agent_1", "email": "...", "role": "agent", "is_active": true, "is_root": false, "default_site_id": null}'
```

Это работает, но **требует root-токен в shell-окружении** и не оставляет записи в Django `SyncUserBinding` (а значит, токен не отображается в `/admin/users/syncuserbinding/`). Операционно неудобно и нарушает single-source-of-truth для users через Django-админку.

### 1.3. Целевое состояние (post-TZ)

- Django admin Users → Add user → role dropdown содержит `LLM-агент (главного кладовщика)`.
- При выборе agent — site_ids становится необязательным (multi-select не валидируется, можно оставить пустым).
- При сохранении формы — `UserSyncService` отправляет в SyncServer POST `/auth/sync-user` с `role=agent`, `default_site_id=null`, пустые scopes.
- После сохранения — в `SyncUserBinding` появляется запись с `sync_role="agent"`; токен виден в `/admin/users/syncuserbinding/` (masked).
- Через `SyncServer API GET /auth/me` с этим токеном — возвращается `role=agent`.

---

## 2. Границы (in / out of scope)

### 2.1. In scope

1. Добавить `AGENT` в Django `Role` TextChoices + миграция.
2. Добавить agent в `MANAGED_ROLE_CHOICES` (admin form).
3. Ослабить `clean()` в `SyncManagedUserAdminForm` — для `role=agent` разрешить пустые site_ids и default_site_id=None.
4. Добавить запись в `ROLE_SCOPE_MAP` для agent (для consistency; сами scopes для agent пустые).
5. В `UserSyncService.prepare_sync` и `sync_user_to_remote` — корректно формировать payload для agent (default_site_id=None, scopes=[] или PUT skipped).
6. Добавить `is_agent(user)` helper в `apps/common/permissions.py` (опционально, но желательно для symmetry с `is_chief_storekeeper` / `is_storekeeper`).
7. Опционально: добавить `list_filter = ("sync_role",)` в `SyncManagedUserAdmin` (cosmetic).
8. Тесты: unit + AdminTestCase + integration (DB-backed с mock SyncServer client).
9. Stand smoke через Playwright (см. §7).
10. Documentation update (INDEX, MEMORY).

### 2.2. Out of scope

* **Не трогать** SyncServer API или схемы (всё уже работает по TZ-AGENT-ROLE-SYNCSERVER).
* **Не делать** отдельный Angular UI для управления agent-users (UI админки достаточно на данный момент; warehouse_admin логинится в Django admin).
* **Не делать** auto-rotation/auto-generation agent-user (existing `rotate_token` через `/admin/users/syncuserbinding/` достаточен).
* **Не делать** bulk-import agent tokens.
* **Не трогать** Django BFF/Angular screens — admin-форма Django полностью self-contained.
* **Не делать** локализацию нового текста «LLM-агент» (используем существующий паттерн `("agent", "LLM-агент")`; i18n — отдельная задача).
* **Не расширять** `Role` enum новыми ролями кроме agent.

---

## 3. Задействованный код

### 3.1. Файлы, которые будут изменены

| Файл | Что меняется | Объём |
|---|---|---|
| `Warehouse_web/apps/users/models.py` | Добавить `AGENT = "agent", "LLM Agent"` в `Role` (строки 30-40) | ~1 строка |
| `Warehouse_web/apps/users/migrations/0014_*.py` | Auto-generated миграция для смены choices | ~10-20 строк (auto) |
| `Warehouse_web/apps/users/admin_forms.py` | `MANAGED_ROLE_CHOICES` (31-35) — добавить agent; `SyncManagedUserAdminForm.clean` (95-127) — для agent ослабить site_ids; creation form наследует изменения | ~15-25 строк |
| `Warehouse_web/apps/users/services.py` | `ROLE_SCOPE_MAP` (26-42) — добавить agent; `prepare_sync` (72-107) и `sync_user_to_remote` (142-194) — для agent передать default_site_id=None и пустые scopes | ~10-15 строк |
| `Warehouse_web/apps/common/permissions.py` | Добавить `is_agent(user)` helper (после `is_storekeeper` ~строка 61) | ~5 строк |
| `Warehouse_web/apps/users/admin.py::SyncManagedUserAdmin` | Добавить `list_filter = ("sync_role",)` если отсутствует (после `list_display` ~строка 508) | ~1-2 строки |
| `Warehouse_web/apps/users/tests/test_admin_security.py` | Новые кейсы для agent через Django admin | ~50-80 строк |
| `INDEX.md` | Ссылка на этот TZ | ~2 строки |
| `MEMORY.md` | Факт «agent role assignable through Django admin» | ~1-2 строки |

### 3.2. Ключевые точки до правки

`apps/users/models.py:30-40`:
```python
class Role(models.TextChoices):
    ROOT = "root", "Root"
    CHIEF_STOREKEEPER = "chief_storekeeper", "Chief Storekeeper"
    STOREKEEPER = "storekeeper", "Storekeeper"
    OBSERVER = "observer", "Observer"
```

`apps/users/admin_forms.py:31-35`:
```python
MANAGED_ROLE_CHOICES = [
    (Role.CHIEF_STOREKEEPER, "Главный кладовщик"),
    (Role.STOREKEEPER, "Кладовщик"),
    (Role.OBSERVER, "Обозреватель"),
]
```

`apps/users/admin_forms.py:104-114` (clean):
```python
role = cleaned_data.get("sync_role")
site_ids_list = [str(sid) for sid in (cleaned_data.get("site_ids") or [])]

if not role:
    raise ValidationError("Роль обязательна.")
if role == Role.ROOT:
    raise ValidationError("Root-пользователи не управляются через Django-admin.")
if not site_ids_list:
    raise ValidationError("Нужно выбрать хотя бы один склад.")

default_site_id = site_ids_list[0]
```

`apps/users/services.py:26-42`:
```python
ROLE_SCOPE_MAP: dict[str, dict[str, bool]] = {
    Role.CHIEF_STOREKEEPER: {"can_view": True, "can_operate": True, "can_manage_catalog": True},
    Role.STOREKEEPER: {"can_view": True, "can_operate": True, "can_manage_catalog": False},
    Role.OBSERVER: {"can_view": True, "can_operate": False, "can_manage_catalog": False},
}
```

`apps/users/services.py:62-70`:
```python
def build_scopes(self, role: str, site_ids: list[str]) -> list[dict[str, Any]]:
    permissions = ROLE_SCOPE_MAP[role]  # KeyError если role не в map
    return [...]
```

### 3.3. Реализация (точно по правкам)

#### A. `apps/users/models.py`

Добавить одну строку:
```python
class Role(models.TextChoices):
    ROOT = "root", "Root"
    CHIEF_STOREKEEPER = "chief_storekeeper", "Chief Storekeeper"
    STOREKEEPER = "storekeeper", "Storekeeper"
    OBSERVER = "observer", "Observer"
    AGENT = "agent", "LLM Agent"  # ← новое
```

Миграция: `python manage.py makemigrations users` создаст `0014_*.py` автоматически.

#### B. `apps/users/admin_forms.py`

**MANAGED_ROLE_CHOICES** (расширить):
```python
MANAGED_ROLE_CHOICES = [
    (Role.CHIEF_STOREKEEPER, "Главный кладовщик"),
    (Role.STOREKEEPER, "Кладовщик"),
    (Role.OBSERVER, "Обозреватель"),
    (Role.AGENT, "LLM-агент"),  # ← новое (ADR-0030 §1, §4.3)
]
```

**`SyncManagedUserAdminForm.clean`** — ослабить для agent. Цель: для `role=agent` `site_ids` опциональны, `default_site_id=None`:

```python
def clean(self) -> dict[str, Any]:
    cleaned_data = super().clean()

    password = self._new_password
    password_confirm = cleaned_data.get("password_confirm") or ""
    if password or password_confirm:
        if password != password_confirm:
            raise ValidationError("Пароли не совпадают.")

    role = cleaned_data.get("sync_role")
    site_ids_list = [str(sid) for sid in (cleaned_data.get("site_ids") or [])]

    if not role:
        raise ValidationError("Роль обязательна.")
    if role == Role.ROOT:
        raise ValidationError("Root-пользователи не управляются через Django-admin.")

    # TZ-AGENT_ROLE_ADMIN_UI §3.3.B: agent — global, scope-independent,
    # site_ids не требуются (ADR-0030 §4.3, TZ-AGENT-ROLE-SYNCSERVER §4.3).
    is_agent_role = role == Role.AGENT

    if not is_agent_role and not site_ids_list:
        raise ValidationError("Нужно выбрать хотя бы один склад.")

    default_site_id = site_ids_list[0] if site_ids_list else None

    self.instance.username = cleaned_data.get("username") or self.instance.username
    self.instance.email = cleaned_data.get("email") or ""
    self.instance.is_active = bool(cleaned_data.get("is_active", True))

    self._desired_intent = {
        "full_name": cleaned_data.get("full_name") or "",
        "role": role,
        "site_ids": site_ids_list,
        "default_site_id": default_site_id,
    }

    return cleaned_data
```

`SyncManagedUserCreationForm` наследует `clean()` от `SyncManagedUserAdminForm` (не переопределяет), так что изменения применяются автоматически.

#### C. `apps/users/services.py`

**`ROLE_SCOPE_MAP`** — добавить agent:
```python
ROLE_SCOPE_MAP: dict[str, dict[str, bool]] = {
    Role.CHIEF_STOREKEEPER: {"can_view": True, "can_operate": True, "can_manage_catalog": True},
    Role.STOREKEEPER: {"can_view": True, "can_operate": True, "can_manage_catalog": False},
    Role.OBSERVER: {"can_view": True, "can_operate": False, "can_manage_catalog": False},
    # TZ-AGENT_ROLE_ADMIN_UI §3.3.C: agent scope-independent — глобальный,
    # но в mapping держим те же can_* что SyncServer access_service.py agent branch.
    # Реально scopes передаются пустым списком, см. ниже.
    Role.AGENT: {"can_view": True, "can_operate": False, "can_manage_catalog": True},
}
```

**`build_scopes`** — если `site_ids` пуст, возвращать `[]` (важно для agent, но безопасно и для остальных):

```python
def build_scopes(self, role: str, site_ids: list[str]) -> list[dict[str, Any]]:
    if not site_ids:
        return []  # ← защита: пустые site_ids → пустые scopes
    permissions = ROLE_SCOPE_MAP[role]
    return [
        {"site_id": self._normalize_site_id(site_id), **permissions}
        for site_id in site_ids
    ]
```

**`prepare_sync` и `sync_user_to_remote`** — обработать `default_site_id=None` для agent. SyncServer `/auth/sync-user` принимает `default_site_id=null` (проверено TZ-AGENT-ROLE-SYNCSERVER §1.2). `_normalize_site_id(None)` упадёт в `TypeError` → `str(None) = "None"`, что неправильно. Защищаем:

```python
# В prepare_sync (~строка 91):
"default_site_id": self._normalize_site_id(default_site_id) if default_site_id else None,
```

И аналогично в `sync_user_to_remote` (~строка 165).

**PUT /admin/users/{id}/scopes** — для agent передавать пустые scopes; SyncServer PUT endpoint принимает `{"scopes": []}`. Проверено: services.py:98 и :170 уже вызывают PUT с `self.build_scopes(role, site_ids)` — после правки `build_scopes` выше, для agent (с пустыми site_ids) PUT получит `{"scopes": []}`. Этого достаточно.

#### D. `apps/common/permissions.py` (опционально)

Добавить helper для symmetry:
```python
def is_agent(user) -> bool:
    """TZ-AGENT_ROLE_ADMIN_UI §3.3.D: agent identity (ADR-0030)."""
    return user.is_authenticated and _get_role(user) == "agent"
```

Если в проекте ещё нигде нет `_get_role(user) == "agent"` сравнения — этот helper не нужен. Но добавление безопасно и не влияет на другие роли.

#### E. `apps/users/admin.py::SyncManagedUserAdmin` (cosmetic)

Добавить фильтр по роли в `SyncManagedUserAdmin.list_filter`, если его там нет:
```python
list_filter = ("is_active", "is_superuser")  # или текущее значение + добавить "sync_role" если есть binding-join
```

Если `list_filter` уже есть и не включает `sync_role` — добавить. Если `SyncUserBinding` не связан через FK с User — фильтр может не сработать. В этом случае оставить как есть (не блокер).

---

## 4. Фазы реализации

| Фаза | Что | Файлы | Acceptance |
|---|---|---|---|
| **1** | Добавить `AGENT` в `Role` TextChoices + makemigrations | `apps/users/models.py`, новая миграция | grep `Role.AGENT == "agent"` → True; `manage.py migrate --plan` показывает `0014_*` |
| **2** | Расширить `MANAGED_ROLE_CHOICES` + ослабить `clean()` | `apps/users/admin_forms.py` | agent в choices; `clean()` принимает пустые site_ids для agent |
| **3** | Обновить `ROLE_SCOPE_MAP` + `build_scopes` + защитить `default_site_id` | `apps/users/services.py` | `build_scopes("agent", [])` → `[]`; `prepare_sync(role="agent", ...)` формирует payload с `default_site_id=None` |
| **4** | Добавить `is_agent` helper | `apps/common/permissions.py` | `is_agent(user_with_role_agent)` → True |
| **5** | Опционально: `list_filter` в `SyncManagedUserAdmin` | `apps/users/admin.py` | cosmetic, не блокер |
| **6** | Static checks | `Warehouse_web/` | `python manage.py check` exit 0; `makemigrations --check --dry-run` exit 0 |
| **7** | Unit + component + integration tests | `apps/users/tests/test_admin_security.py` | новые кейсы зелёные |
| **8** | Stand smoke + regression | стенд через `make status` + Playwright | Django admin `/admin/users/` показывает agent в dropdown; создание agent → token виден; существующие тесты зелёные |
| **9** | Documentation | `INDEX.md`, `MEMORY.md` | ссылки добавлены |

Sequential (все правки в одном Django app, shared ownership).

---

## 5. Стенд (по `Warehouse_web/AGENTS.md`)

### 5.1. Сервисы

| Сервис | Адрес | Health Check | Контейнер |
|---|---|---|---|
| SyncServer API | `http://localhost:8000` | `GET /api/v1/health` | `warehouse_syncserver` |
| Django (Warehouse_web) | `http://localhost:8001` | `GET /healthz/` | `warehouse_web` |
| PostgreSQL | `localhost:5432` | `pg_isready -h localhost -p 5432 -t 3` | `warehouse_postgres` |

**Важно:** SyncServer должен быть на миграции `0038_add_agent_role` (уже применена на стенде, проверено в ревью TZ-AGENT-ROLE-SYNCSERVER). Без этого Django-админка не сможет создать agent-user.

### 5.2. Протокол доступности

1. Перед любым real-stand тестом — пробинг health-эндпоинтов (`curl /api/v1/health`, `curl /healthz/`, `pg_isready`).
2. Если стенд не отвечает → `make up` (или `docker compose up -d`).
3. Если `make up` падает → репорт «стенд недоступен», чек-лист остаётся пустым с пометкой.

### 5.3. Окружение (имена переменных, не значения)

* `SYNC_SERVER_URL`
* `SYNC_ROOT_USER_TOKEN` — используется `SyncServerRootAdminClient` для POST `/auth/sync-user`
* `DJANGO_SETTINGS_MODULE`
* `SECRET_KEY`

### 5.4. Reset / cleanup

* `make restart` — полный рестарт стенда.
* `make build-web` — ребилд Warehouse_web.
* `python manage.py migrate` в `warehouse_web` — применить миграцию `0014_*`.
* Smoke-данные agent-user должны удаляться штатным способом (через `/admin/users/syncuserbinding/` → DELETE user, или через `cleanup_smoke_data` скрипт, если есть).

### 5.5. Seed-данные

* `admin/admin123` (Django superuser = root).
* SyncServer root token в settings.
* SyncServer должен иметь миграцию `0038_add_agent_role` (уже есть).

---

## 6. Verification matrix (test ladder)

| # | Уровень | Что | Команда / инструмент | Ожидаемый результат |
|---|---|---|---|---|
| 1 | Static | Django check | `python manage.py check` в `Warehouse_web/` | exit 0 |
| 2 | Static | Migration check | `python manage.py makemigrations --check --dry-run` | exit 0 (после коммита миграции) |
| 3 | Unit | `Role.AGENT == "agent"` | `python manage.py test apps.users.tests.test_admin_security` | зелёный |
| 4 | Unit | `MANAGED_ROLE_CHOICES` содержит agent | `python manage.py test apps.users.tests.test_admin_security` | зелёный |
| 5 | Unit | `clean()` принимает пустые site_ids для agent | `python manage.py test apps.users.tests.test_admin_security` | зелёный |
| 6 | Component | Django AdminTestCase: POST add user с role=agent | `python manage.py test apps.users.tests.test_admin_security` | зелёный; binding создан с `sync_role="agent"` |
| 7 | Component | Django AdminTestCase: POST change user → role=agent | `python manage.py test apps.users.tests.test_admin_security` | зелёный |
| 8 | Integration | DB-backed: `UserSyncService.prepare_sync(role="agent", site_ids=[])` → mock SyncServer POST `/auth/sync-user` → assert payload | `python manage.py test apps.users.tests.test_admin_security` | payload содержит `role=agent`, `default_site_id=null`, `scopes=[]` (через PUT в apply) |
| 9 | Stand smoke | `make status` → 3/3 healthy | `make status` | OK |
| 10 | Stand smoke | Django admin `/admin/users/user/add/` → dropdown содержит agent | Playwright через Django | dropdown видим |
| 11 | Stand smoke | Создание agent через Django admin | Playwright через Django | binding создан с `sync_role="agent"`, token виден |
| 12 | Stand smoke | Curl к SyncServer `/auth/me` с agent token | `curl -H "X-User-Token: <agent_token>" http://localhost:8000/api/v1/auth/me` | возвращает `role=agent` |
| 13 | Regression | `python manage.py test apps.users` | существующие тесты | 0 failed |
| 14 | Documentation | `git diff` по `INDEX.md`, `MEMORY.md` | изменения применены | git log |

### 6.1. Требуемые тесты (детально)

**A. `test_admin_security.py::RoleEnum`** (новый):
1. `Role.AGENT == "agent"`
2. `Role.AGENT.label == "LLM Agent"`

**B. `test_admin_security.py::ManagedRoleChoices`** (новый):
1. `"agent"` есть в списке choices для dropdown.
2. `"agent"` отсутствует в choices для root (root запрещён через `clean()`, не через choices).

**C. `test_admin_security.py::AgentClean`** (новый):
1. `SyncManagedUserAdminForm` с `role="agent"`, пустые `site_ids` — `clean()` не выбрасывает ValidationError.
2. `SyncManagedUserAdminForm` с `role="agent"`, `site_ids=[1,2]` — `clean()` принимает, `default_site_id = 1`.
3. `SyncManagedUserAdminForm` с `role="observer"`, пустые `site_ids` — `clean()` выбрасывает ValidationError «Нужно выбрать хотя бы один склад.» (regression).

**D. `test_admin_security.py::AdminAddAgentUser`** (Django AdminTestCase):
1. `client.force_login(superuser)`.
2. GET `/admin/users/user/add/` → status 200, форма содержит `select[name="sync_role"]` с option `value="agent"`.
3. POST `/admin/users/user/add/` с `username="llm_agent_smoke"`, `role="agent"`, `site_ids=` (пусто), `password=...`, `password_confirm=...`.
4. assert: 302 redirect на success URL.
5. assert: `User.objects.filter(username="llm_agent_smoke").exists()`.
6. assert: `SyncUserBinding.objects.get(user=user).sync_role == "agent"`.

**E. `test_admin_security.py::AdminChangeToAgentUser`** (Django AdminTestCase):
1. Создать user с `role="storekeeper"` (через admin или фабрику).
2. POST change-form с `role="agent"`, пустые `site_ids`.
3. assert: binding обновлён, `sync_role="agent"`.

**F. `test_admin_security.py::SyncUserPayloadForAgent`** (mock SyncServer):
1. Mock `SyncServerRootAdminClient.post` → возвращает fake user с `user_token`.
2. Mock `SyncServerRootAdminClient.put` (scopes) → возвращает `[]`.
3. Вызвать `UserSyncService.prepare_sync(role="agent", site_ids=[], default_site_id=None, ...)`.
4. assert: первый аргумент `post` (URL) содержит `/auth/sync-user`.
5. assert: второй аргумент `post` (kwargs.json) содержит `role="agent"`, `default_site_id=None`.
6. assert: `put` получил `{"scopes": []}`.

---

## 7. UI automation сценарии (Playwright, через Django admin)

Файл: `Warehouse_web/e2e/users/agent-role-admin.spec.ts` (новый). Структура:

```ts
test.describe('Django admin — agent role assignment', () => {
  test.beforeEach(async ({ page }) => {
    // Django admin login form (стандартный Django, не Angular)
    await page.goto('http://localhost:8001/admin/login/');
    await page.fill('input[name="username"]', 'admin');
    await page.fill('input[name="password"]', 'admin123');
    await page.click('input[type="submit"]');
  });

  test('SCENARIO A: agent role visible in dropdown', async ({ page }) => {
    await page.goto('http://localhost:8001/admin/users/user/add/');
    const options = await page.locator('select[name="sync_role"] option').allTextContents();
    expect(options).toContain('LLM-агент');
  });

  test('SCENARIO B: create agent user via admin', async ({ page }) => {
    await page.goto('http://localhost:8001/admin/users/user/add/');
    await page.fill('input[name="username"]', 'llm_agent_e2e_1');
    await page.fill('input[name="email"]', 'agent1@example.com');
    await page.fill('input[name="full_name"]', 'LLM Agent E2E');
    await page.fill('input[name="password"]', 'changeMe123!');
    await page.fill('input[name="password_confirm"]', 'changeMe123!');
    await page.selectOption('select[name="sync_role"]', 'agent');
    // site_ids оставляем пустым
    await page.click('input[name="_save"]');
    // redirect → user detail page
    await expect(page).toHaveURL(/\/admin\/users\/user\/\d+\/change\//);
  });

  test('SCENARIO C: agent binding visible in SyncUserBindingAdmin', async ({ page }) => {
    // предполагает успешный create из SCENARIO B или предсуществующего smoke-данного
    await page.goto('http://localhost:8001/admin/users/syncuserbinding/');
    const row = await page.locator('tr:has-text("llm_agent_e2e_1")');
    await expect(row).toContainText('agent');
  });
});
```

**Очистка:** через Django admin DELETE user (или скрипт `cleanup_smoke_data`, если есть).

---

## 8. Evidence (для executor'а)

| # | Check | Команда / инструмент | Ожидаемый результат | Evidence |
|---|---|---|---|---|
| 1 | Static | `python manage.py check` | exit 0 | путь к логу |
| 2 | Static | `python manage.py makemigrations --check --dry-run` | exit 0 | путь к логу |
| 3 | Unit A-F | `python manage.py test apps.users.tests.test_admin_security` | зелёный | путь к логу |
| 4 | Stand smoke 9-12 | `make status` + Playwright | 4/4 OK | log + report path |
| 5 | Regression | `python manage.py test apps.users` | 0 failed | log path |
| 6 | User scenario | Playwright MCP | 3/3 success criteria | screenshot/description |
| 7 | Documentation | `git diff` по `INDEX.md`, `MEMORY.md` | изменения применены | git log |

---

## 9. Стратегия выполнения (Execution strategy)

**Sequential** для executor:

- Фазы 1-5 — последовательно (один Django app, общий ownership).
- Фазы 6-9 — последовательно (зависят от реализации).

**Максимально полезных потоков (Swarm):** 1. Все правки в `apps/users/*` и тесно связаны через `MANAGED_ROLE_CHOICES` ↔ `Role` ↔ `services.ROLE_SCOPE_MAP` ↔ `clean()`. Параллелить рискованно — executor может сделать `Role.AGENT`, но не обновить `services.py`, и форма упадёт в KeyError.

---

## 10. Риски и допущения

| Риск / допущение | Митигация |
|---|---|
| SyncServer `/auth/sync-user` не принимает `default_site_id=null` для agent | Stand smoke §5.1 (проверка SyncServer миграции 0038 уже есть) + test §6.1.F (assert payload) + test §6.1.12 (curl `/auth/me`); если падает — executor сужает до «передавать первый активный site как fallback» |
| `ROLE_SCOPE_MAP` KeyError при `role="agent"` до того, как executor добавит запись | Тест §6.1.A (Role enum) + §6.1.B (choices) ловят это на unit-уровне; test §6.1.C (clean) — на component |
| Django makemigrations не сгенерирует миграцию для TextChoices (динамические choices) | Проверить: даже если текстовые choices динамические, Django всё равно фиксирует их в миграции. `makemigrations --check --dry-run` после правки должен быть exit 0; если нет — executor создаёт миграцию вручную с `AlterField(choices=...)` |
| Site-binding filter (`list_filter` по `sync_role`) не работает без FK | Cosmetic; если `list_filter` падает — executor откатывает эту правку (фаза 5 опциональна) |
| SyncServer миграция 0038 не применена на стенде (например, после `make clean`) | Stand smoke §5.1 явно проверяет; executor прогоняет `make status` перед UI-тестами; если SyncServer не отвечает — `make restart` или `make build-sync` |
| Форма `SyncManagedUserCreationForm` (add form) требует `password_confirm` и наследует clean — нужно проверить, что для agent `password_confirm` тоже работает | Тест §6.1.D покрывает это (POST add user с password + password_confirm) |
| Регрессия: существующие тесты Django admin ломаются из-за расширения choices | Regression §5.13; если ломаются — фиксим в том же коммите (минимально-обратимая правка) |
| Stand недоступен во время тестирования | Stand Availability Protocol из корневого AGENTS.md; оставить чек-лист пустым с пометкой «стенд недоступен» |

---

## 11. Что **не** делается (жёсткие границы)

* **Не менять** SyncServer API, схемы, миграции (0038 уже применена, всё работает).
* **Не делать** Angular UI для agent management (UI админки Django достаточно).
* **Не делать** bulk-import / auto-generation agent-user.
* **Не делать** auto-rotation / token lifecycle (existing `rotate_token` достаточен).
* **Не делать** локализацию «LLM-агент» (используем существующий паттерн).
* **Не трогать** Django BFF API endpoints, кроме случая если потребуется BFF для нового form-action (не предполагается).
* **Не вводить** новые роли кроме agent.
* **Не расширять** `apps/common/permissions.py` сверх `is_agent()` helper.

---

## 12. Связанные документы

| Документ | Связь |
|---|---|
| `SyncServer/docs/TZ/TZ-AGENT-ROLE-SYNCSERVER.md` rev.2 | Завершённая TZ, на которую опираемся |
| `SyncServer/docs/adr/0030-agent-domain-role.md` | Архитектурное решение (Accepted, Implemented) |
| `Functional and WorkLogik.md` §I/2.1.5 | Каноническое перечисление ролей (agent уже добавлен в `d6e8efe`) |
| `Role Matrix.md` | Колонка agent (уже добавлена в `d6e8efe`) |
| `docs/AGENT_TZ_WORKFLOW.md` | Шаблон чек-листа и test ladder |
| `Warehouse_web/AGENTS.md` | Стенд, verification matrix, Git-правила |
| Корневой `AGENTS.md` | Stand Availability Protocol |

---

## 13. Следующий шаг после приёмки

* Архивация этого TZ в `docs/archive/` после merge executor'а (помечать «реализовано» в `INDEX.md`).
* Если в будущем понадобится Angular UI для agent management (например, отдельный dashboard для root'а с просмотром agent tokens и rotate) — отдельный TZ.
* Если SyncServer введёт `agent` в свои admin UI endpoints (через `/admin/roles` уже отдаёт 5 ролей; возможно, в будущем появится `/admin/users?role=agent` filter и UI для agent-specific config) — sync с этой TZ.
* Если кладовщик/root захочет ограничить количество agent-users (например, не более 1) — отдельный constraint + TZ.
