# AUTH — аутентификация и авторизация SyncServer

## Service Auth (фактическая схема)

Два заголовки, оба — UUID-токены из базы SyncServer:

| Заголовок | Субъект | Когда нужен |
|---|---|---|
| `X-User-Token` | Пользователь (`users.user_token`) | **Основной.** Все эндпоинты скилла требуют `require_user_identity` |
| `X-Device-Token` | Устройство (`devices.device_token`) | Опционально, для аудита (какое устройство работало от имени пользователя) |

- НЕ Bearer и НЕ `Authorization`. Токен не-UUID → 401. Неизвестный → 401
  (`invalid X-User-Token`). Деактивированный пользователь → 403
  (`User account is inactive`), устройство → 403 (`Device is inactive`).
- Токены создаются на сервере (seed/bootstrap) и хранятся в БД; сервер их из
  env не читает. Значения выдаются администратором один раз.

## Acting User Context

Отдельного механизма имперсонации (заголовка вида `X-Acting-User`)
**в SyncServer НЕТ** (проверено grep по `acting|impersonat|X-Acting`).
«Acting user» — это всегда пользователь, чей `X-User-Token` передан.
Поэтому конфигурация скилла использует один пользовательский токен
кладовщика (+ опциональный device-токен рабочего места).

## Переменные конфигурации скилла (адаптированы к фактической схеме)

| Переменная | Обязательна | Назначение |
|---|---|---|
| `SYNC_SERVER_BASE_URL` | да | Базовый URL, напр. `https://sync.example.com` или `http://192.168.x.x:8000` |
| `SYNC_SERVER_USER_TOKEN` | да | `X-User-Token` кладовщика (UUID) |
| `SYNC_SERVER_DEVICE_TOKEN` | нет | `X-Device-Token` рабочего места (UUID), аудит |
| `SYNC_SERVER_SITE_ID` | нет | Площадка по умолчанию для остатков |
| `SYNC_SERVER_ALLOW_INSECURE_LOCAL` | нет (default false) | Разрешить HTTP без TLS только для localhost/частных сетей |

Шаблон — `templates/syncserver.env.example`. Значения — только в
`%LOCALAPPDATA%\WarehouseAgent\secrets\syncserver.env` с ACL (см. SECURITY.md).

## Роли и права

- Канонические роли: `root`, `chief_storekeeper`, `storekeeper`, `observer`.
- Глобальный бизнес-доступ: `is_root` или `role == "chief_storekeeper"`.
- Site-скоупы (`UserAccessScope`): `can_view`, `can_operate`,
  `can_manage_catalog` на конкретные площадки.
- Чтение каталога/остатков: роли `chief_storekeeper|storekeeper|observer`
  (иначе 403 `catalog read access denied` / `read balances permission required`).
- Создание draft: все четыре роли. Изменение draft: только создатель,
  chief_storekeeper, root (иначе 403).

## Диагностика без секретов

`python warehouse_api.py config check` возвращает только факты наличия:

```json
{
  "ok": true,
  "command": "config.check",
  "data": {
    "base_url_configured": true,
    "base_url_scheme": "https",
    "insecure_local_allowed": false,
    "user_token_present": true,
    "device_token_present": true,
    "site_id_configured": true,
    "secrets_file_exists": true,
    "secrets_acl_safe": true,
    "secrets_acl_detail": "ACL: только текущий пользователь и SYSTEM",
    "cases_dir": "C:\\Users\\User\\AppData\\Local\\WarehouseAgent\\cases"
  }
}
```

Значения токенов не выводятся никогда.

## Ошибки аутентификации

| Ситуация | HTTP | Тело |
|---|---|---|
| Нет токена | 401 | `{"detail": "No authentication tokens provided"}` |
| Нет `X-User-Token` там, где обязателен | 401 | `{"detail": "X-User-Token is required"}` |
| Токен не UUID | 401 | `{"detail": "Invalid X-User-Token"}` |
| Токен не найден | 401 | `{"detail": "invalid X-User-Token"}` |
| Пользователь неактивен | 403 | `{"detail": "User account is inactive"}` |
| Недостаточно прав (роль/скоуп) | 403 | `{"detail": "catalog read access denied"}` и т.п. |
