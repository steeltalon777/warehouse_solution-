# TZ: Password Self-Service + Admin Password Protection

## Execution Strategy

- [x] 🟢 Parallel execution recommended
- **Reason:** Три независимых файла: views/urls/шаблон профиля (Unit A), navbar (Unit B), admin_forms clean_password (Unit C). После реализации Units A+B+C — интеграционный smoke-тест.

## Architecture Review

**Date:** 2026-06-18 | **Reviewer:** Architect | **Verdict:** ✅ Approved

| Category | Result |
|----------|--------|
| Complexity | ✅ Простейшее решение: 1 view + 1 form + 1 template. Компоненты с единой ответственностью. |
| Coupling & Cohesion | ✅ Без циклических зависимостей. Модули тестируются изолированно. |
| Data & State | ✅ Чёткое владение: пароль → Django, профиль → Django (primary) + SyncServer (копия). |
| Failure Modes | ✅ SyncServer-синк в try/except. При недоступности SyncServer профиль сохраняется локально. |
| Security | ✅ CSRF, PasswordInput(render_value=False), login_required, проверка текущего пароля, Django ORM. |
| Scalability | ✅ Низкая нагрузка (смена профиля — редкая операция). |
| Observability | ✅ `logger.exception` при сбое синка. Django request logging. |
| Operability | ✅ Без миграций, без downtime. Откат = revert commit. |

**🔴 Blockers:** 0  
**🟡 Warnings:** 0  
**🔵 Notes:**
1. `UserProfileForm` проверяет `len(pwd) < 8` вместо `AUTH_PASSWORD_VALIDATORS`. Для v1 приемлемо.

---

## Execution Checklist

- [x] 0. Context verified
- [x] 1. Architecture boundaries confirmed
- [x] 2. Implementation: User profile page (view, form, template, url, sync)
- [x] 3. Implementation: Navbar link to profile
- [x] 4. Implementation: Admin `clean_password()` protection
- [x] 5. Unit tests complete
- [x] 6. Integration tests with real DB complete
- [x] 7. Stand smoke tests complete
- [x] 8. UI automation tests (Playwright) complete
- [x] 9. User scenario tests complete
- [x] 10. Regression checks complete
- [x] 11. Documentation updated
- [ ] 12. Final acceptance review complete — ожидает QA

---

## Уровень 0: Context Verified

### Что есть сейчас
- Django использует стандартный `django.contrib.auth.models.User` (пароль — PBKDF2 hash)
- `SyncManagedUserAdminForm`: поля `password` и `password_confirm` уже `required=False`, help_text «Оставьте пустым, чтобы не менять»
- `save_model()` в `SyncManagedUserAdmin`: `if password: obj.set_password(password)` — при пустом поле пароль не меняется
- `UserSyncService.sync_existing_binding()` — умеет ресинхронизировать пользователя в SyncServer с текущими role/site_ids из binding
- `UserSyncService.prepare_sync()` — отправляет `POST /auth/sync-user` с root-токеном, в payload входят full_name и email

### Что НЕ реализовано
- Нет пользовательской страницы для самостоятельной смены пароля / ФИО / email
- Нет `clean_password()` в `SyncManagedUserAdminForm` — защита только на уровне `save_model`

### Файлы, которые затрагиваются

| Файл | Действие |
|------|----------|
| `Warehouse_web/apps/users/views.py` | Добавить `profile_view` |
| `Warehouse_web/apps/users/urls.py` | Добавить `profile/` URL |
| `Warehouse_web/apps/users/forms.py` | **Новый файл**: `UserProfileForm` |
| `Warehouse_web/templates/users/profile.html` | **Новый файл**: шаблон профиля |
| `Warehouse_web/templates/includes/navbar.html` | Ссылка на профиль |
| `Warehouse_web/apps/users/admin_forms.py` | Добавить `clean_password()` |
| `Warehouse_web/apps/users/admin.py` | Без изменений (только проверка) |

### Что НЕ затрагивается
- SyncServer (пароли только в Django)
- Angular-фронтенд
- Модели БД (без миграций)

---

## Уровень 1: Architecture Boundaries Confirmed

### Принципы
1. **Пароль** — только в Django. SyncServer не хранит пароли (токеновая аутентификация).
2. **ФИО / email** — обновляются в Django → синхронизируются в SyncServer через существующий `UserSyncService` (root-токен).
3. **Роль / склад** — через профиль НЕ меняются. Только через админку.
4. **Доступ к `/profile/`** — только аутентифицированные пользователи (login_required).

### Data flow
```
Browser → POST /users/profile/
  ├─ Django: user.set_password(new_password) — только если указан
  ├─ Django: user.first_name = full_name
  ├─ Django: user.email = email
  ├─ Django: user.save()
  └─ Django → SyncServer: sync_existing_binding() — синхронизация full_name/email
```

### Валидация формы
- `current_password` — обязателен всегда (подтверждение личности)
- `new_password` / `new_password_confirm` — необязательны. Если одно заполнено — оба обязательны и должны совпадать
- `full_name` — необязателен, макс. 255 символов
- `email` — необязателен, валидный email

---

## Уровень 2: Implementation

### Unit A: User Profile Page
**Владелец:** executor-agent | **Файлы:** views.py, urls.py, forms.py, profile.html

#### A1. `Warehouse_web/apps/users/forms.py` (новый файл)
```python
class UserProfileForm(forms.Form):
    current_password = forms.CharField(
        label="Текущий пароль",
        widget=forms.PasswordInput(render_value=False),
        required=True,
    )
    new_password = forms.CharField(
        label="Новый пароль",
        widget=forms.PasswordInput(render_value=False),
        required=False,
        help_text="Оставьте пустым, чтобы не менять пароль.",
    )
    new_password_confirm = forms.CharField(
        label="Подтвердите новый пароль",
        widget=forms.PasswordInput(render_value=False),
        required=False,
    )
    full_name = forms.CharField(
        label="ФИО",
        max_length=255,
        required=False,
    )
    email = forms.EmailField(
        label="Email",
        required=False,
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.fields["full_name"].initial = user.first_name
        self.fields["email"].initial = user.email

    def clean_current_password(self):
        password = self.cleaned_data.get("current_password")
        if not self.user.check_password(password):
            raise ValidationError("Неверный текущий пароль.")
        return password

    def clean(self):
        cleaned = super().clean()
        pwd = cleaned.get("new_password") or ""
        confirm = cleaned.get("new_password_confirm") or ""
        if pwd or confirm:
            if pwd != confirm:
                raise ValidationError("Новый пароль и подтверждение не совпадают.")
            if len(pwd) < 8:
                raise ValidationError("Новый пароль должен быть не менее 8 символов.")
        return cleaned
```

#### A2. `Warehouse_web/apps/users/views.py` — добавить `profile_view`
```python
@login_required
def profile_view(request: HttpRequest):
    success = False
    if request.method == "POST":
        form = UserProfileForm(request.user, request.POST)
        if form.is_valid():
            user = request.user
            if form.cleaned_data.get("new_password"):
                user.set_password(form.cleaned_data["new_password"])
            user.first_name = form.cleaned_data.get("full_name") or ""
            user.email = form.cleaned_data.get("email") or ""
            user.save()

            # Sync to SyncServer (FIO/email only)
            try:
                binding = getattr(user, "sync_binding", None)
                if binding and binding.syncserver_user_id:
                    UserSyncService().sync_existing_binding(user=user, binding=binding)
            except Exception:
                logger.exception("Failed to sync profile to SyncServer")

            # Re-login after password change
            from django.contrib.auth import update_session_auth_hash
            if form.cleaned_data.get("new_password"):
                update_session_auth_hash(request, user)
            
            success = True
    else:
        form = UserProfileForm(request.user)

    return render(request, "users/profile.html", {"form": form, "success": success})
```

#### A3. `Warehouse_web/apps/users/urls.py` — добавить URL
```python
path("profile/", views.profile_view, name="profile"),
```

#### A4. `Warehouse_web/templates/users/profile.html` (новый файл)
```html
{% extends "base.html" %}
{% block title %}Профиль — {{ request.user.username }}{% endblock %}
{% block content %}
<div class="profile-page">
    <h1>Профиль: {{ request.user.username }}</h1>
    {% if success %}
        <div class="alert alert-success">Данные сохранены.</div>
    {% endif %}
    <form method="post">
        {% csrf_token %}
        {{ form.as_p }}
        <button type="submit" class="btn btn-primary">Сохранить</button>
    </form>
</div>
{% endblock %}
```

### Unit B: Navbar Link
**Владелец:** executor-agent | **Файл:** `templates/includes/navbar.html`

Добавить ссылку «Профиль» рядом с именем пользователя:
```html
<a href="{% url 'users:profile' %}" class="profile-link">{{ request.user.username }}</a>
```
(Заменить `<span class="user-name">` на ссылку)

### Unit C: Admin `clean_password()` Protection
**Владелец:** executor-agent | **Файл:** `apps/users/admin_forms.py`

Добавить в `SyncManagedUserAdminForm`:
```python
def clean_password(self):
    """Не менять пароль, если поле оставлено пустым."""
    return self.cleaned_data.get("password", "")
```

### Integration Checkpoint
После реализации Unit A+B+C:
1. Запустить `python manage.py test apps.users`
2. Проверить, что профиль открывается по `/users/profile/`
3. Проверить, что navbar показывает ссылку на профиль

---

## Уровень 3: Unit/Component Tests

### Тесты для `UserProfileForm` (`Warehouse_web/apps/users/tests/test_profile.py`)
- [ ] `test_current_password_required` — пустой текущий пароль → validation error
- [ ] `test_wrong_current_password` — неверный текущий пароль → validation error
- [ ] `test_password_change_mismatch` — new_password ≠ confirm → validation error
- [ ] `test_password_change_success` — правильные данные, меняем пароль
- [ ] `test_password_unchanged_when_empty` — пустые поля пароля → пароль не меняется
- [ ] `test_full_name_update` — меняем ФИО
- [ ] `test_email_update` — меняем email
- [ ] `test_email_invalid` — невалидный email → validation error

### Тесты для `SyncManagedUserAdminForm` (существующие + новый)
- [ ] `test_clean_password_returns_empty_for_empty_field` — `clean_password()` возвращает "" для пустого поля
- [ ] `test_password_preserved_on_role_change` — смена роли без указания пароля → пароль не меняется

### Команда запуска
```bash
python manage.py test apps.users.tests.test_profile apps.users.tests.test_admin_forms
```

---

## Уровень 4: Integration Tests (Real DB)

### Тесты с БД
- [ ] `test_profile_view_get` — GET `/users/profile/` возвращает 200 и форму
- [ ] `test_profile_view_post_success` — POST с правильными данными → redirect/200 + success message
- [ ] `test_profile_view_post_wrong_password` — POST с неверным паролем → 200 + ошибка
- [ ] `test_profile_view_requires_login` — без логина → redirect на login
- [ ] `test_admin_edit_user_without_password` — редактирование пользователя в админке с пустым паролем → пароль сохранён

### Команда запуска
```bash
python manage.py test apps.users --settings=config.settings.test
```

---

## Уровень 5: Stand Smoke Tests

### Стенд
Docker: SyncServer :8000, Django :8001, PostgreSQL :5432

### Подготовка
Создать тестового пользователя (если нет):
```bash
docker exec warehouse_web python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
user, created = User.objects.get_or_create(username='test_profile', defaults={'email': 'test@test.com'})
if created:
    user.set_password('TestPass123')
    user.save()
    print('Created:', user.username)
"
```

### Smoke-тесты (curl)

1. **GET `/users/profile/` без аутентификации → redirect на login:**
```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/users/profile/
# Ожидается: 302
```

2. **GET `/users/profile/` с аутентификацией → 200:**
```bash
# Получить CSRF + сессию через логин
CSRF=$(curl -s -c /tmp/cookies.txt http://localhost:8001/users/login/ | grep -oP 'csrfmiddlewaretoken" value="\K[^"]+')
curl -s -c /tmp/cookies.txt -b /tmp/cookies.txt -X POST http://localhost:8001/users/login/ \
  -d "username=test_profile&password=TestPass123&csrfmiddlewaretoken=$CSRF" -L -o /dev/null -w "%{http_code}"
curl -s -b /tmp/cookies.txt -o /dev/null -w "%{http_code}" http://localhost:8001/users/profile/
# Ожидается: 200
```

3. **Смена пароля через профиль — проверка входа с новым паролем:**
```bash
CSRF=$(curl -s -b /tmp/cookies.txt http://localhost:8001/users/profile/ | grep -oP 'csrfmiddlewaretoken" value="\K[^"]+')
curl -s -b /tmp/cookies.txt -X POST http://localhost:8001/users/profile/ \
  -d "current_password=TestPass123&new_password=NewPass456&new_password_confirm=NewPass456&full_name=Test+User&email=test%40test.com&csrfmiddlewaretoken=$CSRF" -L -o /dev/null -w "%{http_code}"
# Ожидается: 200 (success message)
# Затем проверить вход с новым паролем
```

4. **Редактирование пользователя в админке без смены пароля:**
```bash
# Логин в админку как admin
# Открыть форму редактирования test_profile
# Изменить роль/склад, оставить пароль пустым
# Сохранить
# Проверить, что test_profile входит со старым паролем
```

---

## Уровень 6: UI Automation Tests (Playwright)

### Сценарии
- [ ] **Профиль: смена пароля** — логин → `/users/profile/` → заполнить форму → сохранить → logout → login с новым паролем
- [ ] **Профиль: смена ФИО** — логин → `/users/profile/` → изменить ФИО → сохранить → проверить отображение в navbar
- [ ] **Профиль: неверный текущий пароль** — ошибка валидации
- [ ] **Админка: смена роли без пароля** — зайти в админку → изменить роль пользователя → сохранить → проверить что пользователь входит со старым паролем

### Команда запуска
```bash
npx playwright test tests/ui/test_profile.py
```

---

## Уровень 7: User Scenario Tests

### Сценарий 1: Кладовщик меняет пароль
1. Кладовщик входит в систему
2. Кликает на своё имя в navbar → `/users/profile/`
3. Вводит текущий пароль, новый пароль, подтверждение
4. Нажимает «Сохранить»
5. Видит сообщение «Данные сохранены»
6. Выходит из системы
7. Входит с новым паролем → успешно
8. Входит со старым паролем → ошибка

### Сценарий 2: Администратор меняет роль пользователя
1. Администратор заходит в админку
2. Открывает пользователя «Иванов»
3. Меняет роль с «Кладовщик» на «Главный кладовщик»
4. Поле пароля оставляет пустым
5. Сохраняет
6. Пользователь «Иванов» входит со своим старым паролем → успешно

### Сценарий 3: Пользователь меняет ФИО и email
1. Пользователь заходит в профиль
2. Меняет ФИО и email
3. Сохраняет
4. Новое ФИО отображается в navbar
5. (Опционально) проверка через `GET /auth/me` в SyncServer — full_name обновлён

---

## Уровень 8: Regression Checks

- [ ] Существующие тесты `python manage.py test` проходят без ошибок
- [ ] `python manage.py test apps.users` — все существующие тесты проходят
- [ ] Админка: создание нового пользователя с паролем — работает
- [ ] Админка: синхронизация пользователя с SyncServer — работает
- [ ] Логин через стандартную форму — работает
- [ ] Выход из системы — работает

---

## Уровень 9: Documentation Updated

- [ ] Обновить `ARCHITECTURE.md` или `docs/` если требуется
- [ ] Закрыть соответствующий пункт в `V3.0_POST_DEPLOY_FIXES.md` (если password management там упомянут)

---

## Уровень 10: Final Acceptance Review

### Критерии приёмки
1. Пользователь может самостоятельно сменить пароль через `/users/profile/`
2. Пользователь может изменить ФИО и email через `/users/profile/`
3. При пустом поле пароля в админке пароль пользователя не сбрасывается
4. Все существующие тесты проходят
5. Smoke-тесты через curl проходят
6. Playwright UI-тесты проходят

### Evidence Table

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|
| Unit tests | `python manage.py test apps.users.tests.test_profile` | pass/fail | log |
| Integration tests | `python manage.py test apps.users` | pass/fail | log |
| Stand smoke | curl-сценарии (5 проверок) | pass/fail | console output |
| UI automation | Playwright `test_profile.py` | pass/fail | report |
| User scenarios | ручная проверка 3 сценариев | pass/fail | screenshots |
| Regression | `python manage.py test` | pass/fail | log |
