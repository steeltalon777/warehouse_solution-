# Итоговый отчёт UI-тестирования

**Дата:** 2026-05-01
**Окружение:** SyncServer 127.0.0.1:8000, Warehouse_web 127.0.0.1:8001
**Браузер:** Chromium (headless)
**Пользователи:** admin, chief_storekeeper, storekeeper, observer

---

## Phase 0 — Health checks ✅

- SyncServer `/health` и `/ready` → 200
- Warehouse_web `/healthz/` и `/healthz/sync/` → 200

## Phase 1 — Root login и навигация ✅

- admin/089786 логинится через Django LoginView (`django.contrib.auth.views.LoginView`)
- Dashboard `/client/` — все разделы в сайдбаре (Каталог, Остатки, Операции, Номенклатура, Администрирование)
- JS-ошибок нет (только favicon 404)

## Phase 2 — Создание склада ✅

- Сайт `ui_20260501_112923_site` (code=4) создан через Django Admin
- `syncserver_site_id=4` подтверждён в SyncServer `/catalog/sites`

## Phase 3 — Создание пользователей ✅

| Логин | Роль | Сайт | Статус синхронизации |
|---|---|---|---|
| ui_20260501_112923_chief | chief_storekeeper | site=4 | synced |
| ui_20260501_112923_keeper | storekeeper | site=4 | synced |
| ui_20260501_112923_observer | observer | site=4 | synced |

## Phase 4 — Permission smoke ✅

| Раздел | Chief | Storekeeper |
|---|---|---|
| Каталог | ✅ | ✅ |
| Остатки | ✅ | ✅ |
| Операции | ✅ | ✅ |
| Номенклатура | ✅ | ❌ (скрыт, 403) |
| Администрирование | ❌ (/admin/ → redirect, /admin-panel/ → 403) | ❌ |

## Phase 5 — Номенклатура ✅

- Категория `UI_Test_Items` (ID 7) создана
- 3 ТМЦ: UI_Test_Item_A (ID 16, шт), UI_Test_Item_B (ID 17, м), UI_Test_Item_C (ID 18, кг)

## Phase 6 — RECEIVE операция ✅

- Операция **c2fb2e56**: RECEIVE, 3 позиции (A:100, B:200, C:50) на site=4
- Создана как черновик через UI (поиск + add-item)

## Phase 7 — Полная приёмка ✅

- Операция c2fb2e56: подтверждена → все 3 позиции приняты полностью (100/200/50)
- Статус: Приёмка завершена

## Phase 8 — Частичная приёмка с потерями ✅

- Операция **2d6eb845** (50/30/20) на site=4
- Принято: A:40, B:25, C:18
- Потери: A:10, B:5, C:2
- Lost-assets страница: 3 записи, статус 'Открыто', привязаны к 2d6eb845

## Phase 9 — MOVE flow ✅

- Операция **a353f164**: MOVE 30x UI_Test_Item_A (site 4 → Акша)
- Подтверждена → приёмка на стороне Акша завершена

## Phase 10 — EXPENSE flow ✅

- Операция **49c25483**: EXPENSE 20x UI_Test_Item_B с site 4
- Подтверждена (без отдельной приёмки)

## Phase 11 — Temporary item flow ✅

- Поиск несуществующего ТМЦ → кнопка "Добавить временную ТМЦ"
- Операция **9f2cf94c**: RECEIVE temp item UI_TEMP_ITEM_Y (qty=1)
- Подтверждена → принята
- Temp-элемент ID 9 отображается в `/temporary-items/` со статусом "Активна"
- Доступны действия: Просмотр, Преобразовать, Объединить, Удалить

## Phase 12 — Balances ✅

| ТМЦ | Склад | Количество |
|---|---|---|
| UI_Test_Item_A | ui_20260501_112923_site | 160 |
| UI_Test_Item_B | ui_20260501_112923_site | 235 |
| UI_Test_Item_C | ui_20260501_112923_site | 88 |
| UI_TEMP_ITEM_Y | ui_20260501_112923_site | 1 |
| UI_Test_Item_A | Акша | 30 |

## Phase 13 — Devices & Access

- `/admin-panel/access/` → 200 OK (нет данных — нет записей)
- `/admin-panel/devices/` → ✅ Устройства: DJANGO_WEB, Комп на Акше

---

## Дефекты (статус после повторной проверки)

### ~~1. Sync identity не загружается для root-пользователя~~ ✅ **ИСПРАВЛЕН**

- `/users/sync/identity/` — загружается корректно, отображает "SyncServer Identity Information" с данными пользователя.
- `/users/sync/site-switch/` — также должен работать.
- **Причина появления в тесте:** Старая Playwright-сессия (созданная до исправления) не имела sync identity в Django session, так как identity записывается в момент login. После `logout + clearCookies + login` — работает штатно.

### ~~2. Устройства (Devices) — 500 VariableDoesNotExist~~ ✅ **ИСПРАВЛЕН**

- `/admin-panel/devices/` — загружается корректно, таблица с устройствами: DJANGO_WEB, Комп на Акше.
- Кнопка "Создать устройство" работает.
- **Причина:** Несовпадение ключей шаблона (`d.code`/`d.name`) и вьюхи (`device_code`/`device_name`).

---

## Batch API (SyncServer) — тестирование bulk-эндпоинтов

**Метод:** curl/PowerShell `Invoke-RestMethod` к SyncServer (127.0.0.1:8000/api/v1)
**Auth:** `X-User-Token: 6e244ea9-31db-4547-bb95-d158dbe1584c` (root)

### `POST /catalog/admin/units/bulk` ✅

| Сценарий | Результат |
|---|---|
| Создание 3 единиц (active + inactive) | ✅ 201 Created, IDs 5-7 |
| Дубликат symbol | ✅ 409 Conflict |
| Пустой items | ✅ 422 Unprocessable |
| Отсутствует name | ✅ 422 Unprocessable |
| Проверка через GET /catalog/admin/units | ✅ Данные видны |

### `POST /catalog/admin/categories/bulk`

| Сценарий | Результат |
|---|---|
| Создание 3 категорий (active + inactive) | ✅ IDs 8-10 |
| Иерархия parent_id (children of ID 8) | ✅ IDs 12-13, parent_id=8 |
| Несуществующий parent_id (999) | ✅ 404 Not Found |
| Дубликат code `UI_BCA` | ❌ **БАГ** — создалась категория ID 11 DupCat с code=UI_BCA, хотя ID 8 уже имеет code=UI_BCA |
| Проверка через GET /catalog/admin/categories | ✅ Данные видны |

### `POST /catalog/admin/items/bulk`

Не существует (405 Method Not Allowed). В `API_MAP.md` не описан.

### Найденный дефект

| # | Описание | Серьёзность | Компонент |
|---|---|---|---|
| 3 | `POST /catalog/admin/categories/bulk` не проверяет уникальность `code` — категории с одинаковым `code` создаются без ошибки | **Medium** | `POST /catalog/admin/categories/bulk` — missing unique validation on `code` |
