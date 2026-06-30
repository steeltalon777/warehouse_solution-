# TZ: V3.1F — Admin Panel Hardening

**Date:** 2026-06-22
**Based on:** Аудит admin-форм 2026-06-22, репродукция бага сброса пароля
**Status:** Ready

## Execution Strategy

- [ ] 🟢 Parallel execution recommended
- **Reason:** F1 (password bug fix) и F5 (URL paths) — независимые правки в разных файлах. F2 (password reset) независим от остальных. F3 (multi-site) и F4 (device parity) затрагивают разные зоны и могут делаться параллельно. Интеграционный прогон — после всех.

---

## Execution Checklist

- [ ] 0. Context verified — аудит выполнен, корень бага подтверждён
- [ ] 1. Stage F1: Fix password clearing bug
- [ ] 2. Stage F1 tests: unit tests for password preservation
- [ ] 3. Stage F2: Password reset flow
- [ ] 4. Stage F2 tests: unit + stand smoke (reset email + form)
- [ ] 5. Stage F3: Multi-site support for storekeepers
- [ ] 6. Stage F3 tests: unit + stand smoke (multi-site save/edit)
- [ ] 7. Stage F4: Device admin parity with user admin
- [ ] 8. Stage F4 tests: unit + stand smoke (device CRUD + status)
- [ ] 9. Stage F5: Fix URL paths in admin templates
- [ ] 10. Integration: full admin workflow smoke tests
- [ ] 11. Regression: SyncServer 410+ tests, Django 325 tests
- [ ] 12. Final acceptance review

---

## Stage F1: Fix password clearing bug 🔴 Blocker

### Диагноз

`UserChangeForm.save()` в Django **безусловно** вызывает `user.set_password(self.cleaned_data["password"])`. В стандартном `UserChangeForm` поле `password` — это `ReadOnlyPasswordHashField`, всегда возвращающий исходный хеш, поэтому перехеширование безвредно. Но `SyncManagedUserAdminForm` заменяет поле на `CharField`, и при пустом вводе `cleaned_data["password"] = ""`.  

`ModelAdmin._changeform_view()` вызывает `save_form(request, form, change)` → `form.save(commit=False)` → `UserChangeForm.save()` → `user.set_password("")` — хеш пустой строки записывается в `user.password`. Затем `save_model()` получает уже испорченный объект, `if password:` — False, `set_password` не перевызывается, `obj.save()` сохраняет пустой пароль в БД.

### Задача F1.1: Override `save()` в форме

**Файл:** `Warehouse_web/apps/users/admin_forms.py`

Добавить в `SyncManagedUserAdminForm`:

```python
def save(self, commit: bool = True):
    user = super(UserChangeForm, self).save(commit=False)
    password = self.cleaned_data.get("password")
    if password:
        user.set_password(password)
    if commit:
        user.save()
        if hasattr(self, "save_m2m"):
            self.save_m2m()
    return user
```

Ключевое: вызываем `super(UserChangeForm, self).save(commit=False)` — прыгаем через `UserChangeForm` к `BaseModelForm`, минуя опасный `set_password`.  

**НЕ вызываем** `super().save()` (т.е. `UserChangeForm.save`) — именно в нём баг.

### Задача F1.2: Убрать дублирующую логику из `save_model()`

**Файл:** `Warehouse_web/apps/users/admin.py`, метод `save_model()` (строки 479–485)

После фикса F1.1 `form.save()` уже корректно обрабатывает пароль. Дублирующий код в `save_model()` можно упростить:

```python
# Было:
# password = form.cleaned_data.get("password")
# obj.email = form.cleaned_data["email"]
# obj.first_name = form.cleaned_data.get("full_name") or ""
# obj.is_staff = False
# obj.is_superuser = False
# if password:
#     obj.set_password(password)

# Стало: убрать set_password из save_model (перенесено в form.save)
obj.email = form.cleaned_data["email"]
obj.first_name = form.cleaned_data.get("full_name") or ""
obj.is_staff = False
obj.is_superuser = False
```

### Acceptance criteria F1

- [ ] Пользователь, отредактированный через админку без заполнения пароля, сохраняет прежний пароль
- [ ] Пользователь с новым паролем — пароль меняется
- [ ] `python manage.py test apps.users.tests` — все тесты зелёные
- [ ] Ручной smoke: создать пользователя → задать пароль → отредактировать email → проверить вход со старым паролем

---

## Stage F2: Password reset flow 🟡

### Текущее состояние
- Self-service смена пароля: `/users/profile/` через `UserProfileForm` — **работает**
- Сброс пароля (восстановление): **отсутствует**
- В админке нет ссылки «сбросить пароль» для managed-пользователя

### Задача F2.1: Подключить Django PasswordResetView

**Файлы:**
- `Warehouse_web/config/urls.py` — добавить стандартные auth views
- `Warehouse_web/templates/registration/password_reset_form.html` — форма ввода email
- `Warehouse_web/templates/registration/password_reset_email.html` — тело письма
- `Warehouse_web/templates/registration/password_reset_done.html` — «письмо отправлено»
- `Warehouse_web/templates/registration/password_reset_confirm.html` — ввод нового пароля
- `Warehouse_web/templates/registration/password_reset_complete.html` — «пароль изменён»

**URL-паттерны:**
```python
from django.contrib.auth import views as auth_views

urlpatterns += [
    path("users/password-reset/", auth_views.PasswordResetView.as_view(
        template_name="registration/password_reset_form.html",
        email_template_name="registration/password_reset_email.html",
    ), name="password_reset"),
    path("users/password-reset/done/", auth_views.PasswordResetDoneView.as_view(
        template_name="registration/password_reset_done.html",
    ), name="password_reset_done"),
    path("users/password-reset/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(
        template_name="registration/password_reset_confirm.html",
    ), name="password_reset_confirm"),
    path("users/password-reset/complete/", auth_views.PasswordResetCompleteView.as_view(
        template_name="registration/password_reset_complete.html",
    ), name="password_reset_complete"),
]
```

### Задача F2.2: Кнопка «Сбросить пароль» в админке

**Файл:** `Warehouse_web/templates/admin/auth/user/change_form.html`

Добавить кнопку рядом с существующими (sync/repair/rotate-token):
```html
<form method="get" action="{% url 'password_reset' %}">
    <input type="hidden" name="email" value="{{ original.email }}">
    <input type="submit" value="Сбросить пароль">
</form>
```

### Задача F2.3: Базовый email backend

**Файл:** `Warehouse_web/config/settings/development.py`

Для dev-стенда использовать console backend (письма выводятся в консоль):
```python
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
```

Для production — настраивается отдельно (SMTP или sendgrid).

### Acceptance criteria F2

- [ ] URL `/users/password-reset/` принимает email, отправляет ссылку сброса
- [ ] Переход по ссылке → форма нового пароля → успешный сброс → вход с новым паролем
- [ ] Кнопка «Сбросить пароль» видна в админке на странице редактирования пользователя
- [ ] Для root/superuser кнопка не показывается (root не управляется через админский reset)

---

## Stage F3: Multi-site support for storekeepers 🟡

### Текущее состояние
- Модель `SyncUserBinding.site_ids` — `JSONField`, поддерживает список
- `build_scopes()` в `UserSyncService` — принимает список `site_ids`
- Админка: только один `ChoiceField` → `site_ids = [default_site_id]`
- При repair из SyncServer может восстановиться несколько сайтов, но админка их не показывает

### Задача F3.1: Multi-select поле в форме

**Файл:** `Warehouse_web/apps/users/admin_forms.py`

Заменить `default_site_id` на `site_ids`:

```python
site_ids = forms.MultipleChoiceField(
    label="Склады",
    choices=[],
    required=True,
    help_text="Выберите один или несколько складов, к которым привязан пользователь.",
)
```

Убрать `default_site_id` из формы (сделать вычисляемым: первый в списке).

**В `__init__`:**
```python
self.fields["site_ids"].choices = self.site_choices
# Восстановить выбранные сайты из binding
binding = self._get_binding()
if binding and binding.site_ids:
    self.fields["site_ids"].initial = [str(s) for s in binding.site_ids]
```

### Задача F3.2: Валидация в `clean()`

```python
site_ids_list = [str(sid) for sid in (cleaned_data.get("site_ids") or [])]
if not site_ids_list:
    raise ValidationError("Нужно выбрать хотя бы один склад.")
default_site_id = site_ids_list[0]  # первый — дефолтный
```

### Задача F3.3: Сохранение в `save_model()`

**Файл:** `Warehouse_web/apps/users/admin.py`

```python
site_ids_list = [str(sid) for sid in (form.cleaned_data.get("site_ids") or [])]
binding.default_site_id = site_ids_list[0] if site_ids_list else ""
binding.site_ids = site_ids_list

service.apply_prepared_state(
    ...
    site_ids=site_ids_list,
    default_site_id=site_ids_list[0] if site_ids_list else "",
)
```

### Задача F3.4: Обновить `prepare_sync()` и `apply_prepared_state()`

**Файл:** `Warehouse_web/apps/users/services.py`

Методы уже принимают `site_ids: list[str]` — изменений не требуется. Проверить, что `build_scopes()` корректно создаёт scope для каждого site_id.

### Задача F3.5: Обновить fieldsets в админке

**Файл:** `Warehouse_web/apps/users/admin.py`

Заменить `"default_site_id"` на `"site_ids"` в `fieldsets` и `add_fieldsets`.

### Acceptance criteria F3

- [ ] При создании пользователя можно выбрать несколько складов
- [ ] При редактировании — выбранные склады отображаются, можно изменить
- [ ] После сохранения `SyncUserBinding.site_ids` содержит список выбранных ID
- [ ] `build_scopes()` вызывается с полным списком
- [ ] Кладовщик с несколькими складами может оперировать на всех привязанных складах
- [ ] Главный кладовщик может выбрать «все склады» (опционально — отдельный чекбокс)

---

## Stage F4: Device admin parity with user admin 🟡

### Задача F4.1: `MANUAL_OVERRIDE` при изменении device token

**Файл:** `Warehouse_web/apps/users/admin.py`, `SyncDeviceBindingAdmin.save_model()`

Добавить логику, аналогичную `SyncUserBindingAdmin.save_model()`:

```python
def save_model(self, request, obj, form, change):
    service = DeviceSyncService()
    try:
        with transaction.atomic():
            if change and "sync_device_token" in form.changed_data:
                obj.sync_status = SyncStatus.MANUAL_OVERRIDE
                obj.manual_token_updated_at = timezone.now()
                obj.manual_token_updated_by = request.user
                obj.last_sync_error = ""
            super().save_model(request, obj, form, change)
            if change:
                service.sync_existing_binding(binding=obj)
            else:
                service.create_binding(binding=obj)
    except Exception as exc:
        if obj.pk:
            service.mark_failure(binding=obj, error=exc, status=SyncStatus.REPAIR_REQUIRED)
        raise
```

### Задача F4.2: Online/offline статус устройства

**Файлы:**
- `Warehouse_web/apps/users/admin.py` — колонка и фильтр
- `Warehouse_web/apps/users/services.py` — обновление `last_seen_at` из SyncServer

**В `SyncDeviceBindingAdmin`:**
```python
list_display = (..., "online_status", ...)

@admin.display(description="Статус", ordering="last_seen_at")
def online_status(self, obj):
    if not obj.last_seen_at:
        return format_html('<span style="color:gray;">—</span>')
    delta = timezone.now() - obj.last_seen_at
    if delta < timedelta(minutes=5):
        return format_html('<span style="color:green;">🟢 Online</span>')
    elif delta < timedelta(hours=1):
        return format_html('<span style="color:orange;">🟡 Away</span>')
    return format_html('<span style="color:red;">🔴 Offline</span>')
```

Добавить `last_seen_at` в `readonly_fields` и `list_display`.

### Задача F4.3: `add_form` для создания устройства

**Файл:** `Warehouse_web/apps/users/admin_forms.py`

Создать `SyncManagedDeviceCreationForm`, наследующий `SyncManagedDeviceAdminForm`:

```python
class SyncManagedDeviceCreationForm(SyncManagedDeviceAdminForm):
    class Meta(SyncManagedDeviceAdminForm.Meta):
        fields = ("device_code", "device_name", "is_active")
```

**Файл:** `Warehouse_web/apps/users/admin.py`

Добавить `add_form = SyncManagedDeviceCreationForm` в `SyncDeviceBindingAdmin`.

### Задача F4.4: `get_form()` с разделением create/edit

Аналогично `SyncManagedUserAdmin.get_form()`:

```python
def get_form(self, request, obj=None, change=False, **kwargs):
    if obj is None:
        kwargs["form"] = self.add_form
    return super().get_form(request, obj, change=change, **kwargs)
```

### Задача F4.5: Отображение `last_seen_at`, `health` в detail view

Добавить в `fields` и `readonly_fields`:
- `last_seen_at` — timestamp последней активности
- `syncserver_device_id` — уже есть в readonly
- Возможно `health_status` — вычисляемое поле (online/offline/error)

### Acceptance criteria F4

- [ ] Device admin показывает online/offline статус в таблице
- [ ] Ручное изменение device token → статус `MANUAL_OVERRIDE`
- [ ] Форма создания устройства работает (`add_form`)
- [ ] `last_seen_at` отображается в detail view
- [ ] Rotate-token, repair, sync кнопки работают как у пользователей

---

## Stage F5: Fix URL paths in admin templates 🔴

### Диагноз

**Файл:** `Warehouse_web/templates/admin/auth/user/change_form.html`

Кнопки используют относительные пути `sync/`, `repair/`, `rotate-token/` от текущей страницы изменения (`/admin/auth/user/13/change/`), что резолвится в `/admin/auth/user/13/change/sync/` — **не совпадает** с зарегистрированными URL (`/admin/auth/user/13/sync/`).

В **device** template (`admin/users/syncdevicebinding/change_form.html`) используется `../sync/` — корректно.

### Задача F5.1: Исправить URL в user change_form

**Файл:** `Warehouse_web/templates/admin/auth/user/change_form.html`

```html
<!-- Было -->
<form method="post" action="sync/">
<form method="post" action="repair/">
<form method="post" action="rotate-token/">

<!-- Стало -->
<form method="post" action="../sync/">
<form method="post" action="../repair/">
<form method="post" action="../rotate-token/">
```

### Acceptance criteria F5

- [ ] Кнопка «Синхронизировать» на странице пользователя ведёт на корректный URL
- [ ] Кнопка «Восстановить из SyncServer» работает
- [ ] Кнопка «Сбросить и перегенерировать токен» работает
- [ ] Поведение идентично device admin

---

## Files in scope

| Файл | Этап | Тип изменений |
|---|---|---|
| `Warehouse_web/apps/users/admin_forms.py` | F1, F3, F4 | Fix `save()`, multi-site, device creation form |
| `Warehouse_web/apps/users/admin.py` | F1, F3, F4 | `save_model` cleanup, multi-site save, device parity |
| `Warehouse_web/config/urls.py` | F2 | Password reset URLs |
| `Warehouse_web/config/settings/development.py` | F2 | Email backend |
| `Warehouse_web/templates/admin/auth/user/change_form.html` | F2, F5 | Reset button + URL fix |
| `Warehouse_web/templates/registration/password_reset_*.html` | F2 | New templates |
| `Warehouse_web/apps/users/services.py` | F3, F4 | Multi-site scopes, device last_seen |
| `Warehouse_web/apps/users/tests/` | F1-F4 | Unit tests |

## Out of scope

- SMTP-конфигурация для production email (отдельный TZ/infra)
- Device health monitoring (Zabbix/Prometheus)
- Управление правами (permissions) в админке — остаётся на SyncServer
- Root-пользователи — не управляются через `SyncManagedUserAdminForm`
- UI за пределами Django admin (Angular SPA, SSR)
- Миграции БД для новых полей (если потребуются — в рамках F4)

## Test Ladder

| Level | Применение |
|---|---|
| Static checks | ✅ format, lint, type checks |
| Unit tests | ✅ `apps.users.tests` — password preservation, multi-site validation, device status |
| Component tests | ✅ Django admin form tests (form.is_valid, save flow) |
| Integration tests | ✅ DB-backed — создание/редактирование пользователей и устройств |
| Stand smoke tests | ✅ Dev-стенд: admin CRUD через Playwright |
| UI automation | ✅ Playwright: full admin workflows |
| User scenarios | ✅ Создать пользователя → задать пароль → сменить email без пароля → войти; сброс пароля через email; multi-site storekeeper |
| Regression pack | ✅ SyncServer 410+ tests, Django 325 tests |
| Acceptance review | ✅ Evidence table |

## Stand Requirements

- Docker dev-стенд: `warehouse_web`, `warehouse_syncserver`, `warehouse_postgres`
- Django admin: `http://localhost:8001/admin/`, логин `admin`/`admin123`
- Health checks: `http://localhost:8001/healthz/`, `http://localhost:8000/api/v1/health`
- Email backend: console (письма в stdout контейнера)
