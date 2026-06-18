# Scope: Audit Login + Password Self-Service

**Date:** 2026-06-18
**Decision Makers:** Architect + User

## Problem

1. **Аудит действий пользователей**: Синксервер уже логирует бизнес-операции (operation.*, catalog.*) через `AuditEvent`, но история входов/выходов хранится только локально в Django (`LoginAttempt`). Нужен централизованный аудит в SyncServer, без клиентского трекинга (cookies/JS).

2. **Управление паролем**: Пользователи не могут самостоятельно сменить пароль, ФИО или email. Только администратор через админку. Нужна пользовательская страница самообслуживания.

3. **Защита пароля в админке**: Убедиться, что редактирование пользователя в админке (смена роли/склада) не сбрасывает пароль.

## In Scope

### Часть 1: Централизованный аудит входов в SyncServer
- SyncServer: новый `event_type="auth.login"` и `"auth.logout"` в существующей модели `AuditEvent`
- SyncServer: новый endpoint `POST /api/v1/auth/audit-event` для приёма auth-событий от Django
- Django: `_record_login_attempt()` дополнительно отправляет событие в SyncServer
- Аудит read-операций (просмотров) — **не включаем**

### Часть 2: Пользовательская страница профиля
- Django: view + template `/profile/` (только для аутентифицированных)
- Форма: смена пароля (`password`, `password_confirm`), ФИО, email
- Валидация: совпадение паролей, минимальная длина, текущий пароль для подтверждения
- Синхронизация: при изменении ФИО/email — отправка в SyncServer
- URL и навигация: ссылка в верхней панели (рядом с именем пользователя)

### Часть 3: Защита пароля в админке
- `SyncManagedUserAdminForm`: добавить явный `clean_password()` для защиты от краевых случаев
- `SuperuserLocalAdminForm`: убедиться, что стандартный Django `UserChangeForm` не трогает пароль без явного указания

## Out Of Scope

- Аудит просмотров/read-операций (GET-запросов)
- Angular/SPA изменения (только Django SSR + шаблоны)
- Клиентский трекинг (cookies, JS, fingerprinting)
- Ротация токенов через пользовательскую страницу
- Управление ролью/складами через пользовательскую страницу (только админка)
- История неудачных попыток входа (только успешные входы/выходы)

## Success Criteria

1. При входе пользователя в Django в SyncServer создаётся `AuditEvent` с `event_type="auth.login"`, видимый через `GET /api/v1/admin/audit`
2. При выходе — `event_type="auth.logout"`
3. Пользователь может зайти на `/profile/`, изменить пароль, ФИО, email — и данные сохраняются
4. При редактировании пользователя в админке с пустым полем пароля — пароль не меняется
5. Существующие тесты Django и SyncServer проходят без регрессий

## Assumptions

| Assumption | Status | Validation |
|---|---|---|
| SyncServer доступен в момент логина (иначе audit-запись пишется только локально) | Reasonable | Принять fallback: если SyncServer недоступен, пишем только локальный LoginAttempt |
| Пользователи заходят через Django web (не через прямой API SyncServer) | Validated | Текущая архитектура: все входы через Django |
| Синхронизация ФИО/email из профиля в SyncServer использует существующий механизм `UserSyncService` | Reasonable | Нужно проверить: sync-user требует root-токен. Для self-service нужен либо новый endpoint, либо BFF-прокси |
| У пользовательской страницы `/profile/` не будет Angular-версии в первой итерации | Validated | Django SSR-template, позже можно мигрировать |

## Alternatives Considered

| Approach | Verdict | Reason |
|---|---|---|
| Do nothing (аудит) | ❌ | Fix #6 из V3.0_POST_DEPLOY_FIXES.md требует аудит, пользователь подтвердил |
| Логировать всё (read + mutations) | ❌ | Слишком много записей, пользователь выбрал «только входы + мутации» |
| Хранить аудит только в Django | ❌ | Пользователь выбрал централизацию в SyncServer |
| Self-service через админку | ❌ | Пользователь хочет отдельную страницу, а не админку для обычных пользователей |
| Новый `PATCH /auth/me` в SyncServer | 🟡 | Нужно для self-service sync. Оценить в TZ |

## Selected Approach

1. **Аудит входов**: Django → `POST /api/v1/auth/audit-event` → SyncServer `AuditEvent`. При недоступности SyncServer — fallback на локальный `LoginAttempt`.
2. **Страница профиля**: Django view `/profile/` с формой. Пароль — локально. ФИО/email — локально + sync в SyncServer через существующий `UserSyncService` (root-токен из `.env`).
3. **Защита админки**: добавить `clean_password()` в форму.

## First Slice

**Итерация 1 (минимальная):**
1. SyncServer: endpoint `POST /auth/audit-event`
2. Django: отправка login/logout audit в SyncServer
3. Django: страница `/profile/` с формой смены пароля, ФИО, email
4. Django: `clean_password()` в `SyncManagedUserAdminForm`

**Исключено из первой итерации:**
- UI automation тесты страницы профиля
- Миграция на Angular
- Retention/cleanup policy для audit-записей

## Next Step

Создать TZ в `/home/makc/AI_sandbox/warehouse_solution/docs/TZ-AUDIT_LOGIN_AND_PASSWORD_MGMT.md`
