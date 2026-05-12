# PLAN_UI_TEST

## Цель

Подготовить и выполнить UI-проверку Warehouse_web поверх SyncServer для полного рабочего цикла склада:

- root/администратор подготавливает справочники доступа: склад, пользователей, роли, привязки к SyncServer;
- главный кладовщик/root ведёт номенклатуру: единицы, категории, ТМЦ;
- кладовщик создаёт складскую операцию;
- операция проводится через отправку и приёмку;
- проверяются остатки, ожидающие приёмки, непринятые/потерянные позиции и временные ТМЦ;
- фиксируются UI-ошибки, JS console errors, сетевые ошибки и несоответствия API/UI.

План рассчитан на ручное/полуавтоматическое прохождение через Playwright MCP, без внедрения test runner в проект.

## Доступные инструменты

- Playwright MCP: браузерная навигация, клики, формы, snapshot, screenshots, console messages, network requests.
- postgres MCP: read-only проверки состояния БД, если нужна верификация записей после UI-действий.
- ssh-stand MCP: развёртывание/проверка тестовой ВМ при необходимости.
- Локальный shell: запуск SyncServer и Warehouse_web, миграции, smoke-команды.

## Рекомендуемый стенд

Основной вариант: локальный запуск.

- SyncServer: `http://127.0.0.1:8000/api/v1`.
- Warehouse_web: `http://127.0.0.1:8001`.
- Warehouse_web `.env` уже настроен на локальный SyncServer.
- Локальный режим быстрее для Playwright-итераций и безопаснее для ВМ.

Fallback: тестовая ВМ через `ssh-stand`.

- Использовать, если локальная БД/зависимости мешают или нужно проверить container/prod-like окружение.
- Правило ВМ: "не убей".
- Перед destructive-действиями на ВМ: проверить контейнеры, volumes, БД и явно убедиться, что действие не сносит нужное состояние.
- Не хранить root-пароль и другие секреты в этом файле.

## Локальный запуск

### SyncServer

Рабочая директория: `D:\PROG\Warehouse_solution\SyncServer`.

Команды:

```powershell
python -m alembic upgrade head
python scripts/bootstrap_root.py
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Smoke URLs:

- `GET http://127.0.0.1:8000/api/v1/health`
- `GET http://127.0.0.1:8000/api/v1/ready`
- `GET http://127.0.0.1:8000/api/docs`

### Warehouse_web

Рабочая директория: `D:\PROG\Warehouse_solution\Warehouse_web`.

Команды:

```powershell
python manage.py migrate
python manage.py runserver 127.0.0.1:8001
```

Smoke URLs:

- `GET http://127.0.0.1:8001/healthz/`
- `GET http://127.0.0.1:8001/healthz/sync/`
- `GET http://127.0.0.1:8001/login/`

## Test Data Strategy

Использовать уникальный префикс для всех сущностей тестового прогона:

- `ui_<YYYYMMDD_HHMM>_site`
- `ui_<YYYYMMDD_HHMM>_chief`
- `ui_<YYYYMMDD_HHMM>_keeper`
- `ui_<YYYYMMDD_HHMM>_observer`
- `ui_<YYYYMMDD_HHMM>_unit`
- `ui_<YYYYMMDD_HHMM>_cat`
- `ui_<YYYYMMDD_HHMM>_item`
- `ui_<YYYYMMDD_HHMM>_temp_item`

Тестовые данные не удалять автоматически, если это мешает диагностике. Очистку делать отдельным согласованным шагом.

## Проверяемые UI-маршруты

### Auth и shell

- `/login/` — форма входа.
- `/logout/` — выход.
- `/` — redirect на `/client/`.
- `/client/` — dashboard.
- `/users/sync/site-switch/` — выбор активного склада.
- `/users/sync/identity/` — информация о SyncServer identity.
- `/users/sync/refresh/` — refresh identity/logout flow.

### Django admin

- `/admin/` — технический root/admin слой.
- `/admin/users/site/` — создание/редактирование склада, синхронизация с SyncServer.
- `/admin/auth/user/` — создание/редактирование пользователей, SyncServer binding.
- `/admin/users/syncuserbinding/` — проверка user binding.
- `/admin/users/syncdevicebinding/` — проверка device binding, sync, rotate-token, repair.

### Custom admin panel

- `/admin-panel/devices/` — список устройств.
- `/admin-panel/devices/create/` — создание устройства.
- `/admin-panel/devices/<id>/edit/` — редактирование устройства.
- `/admin-panel/access/` — просмотр доступов.

### Catalog browse

- `/catalog/` — пользовательский просмотр каталога.
- `/catalog/items/` — redirect/list behavior.
- `/catalog/categories/` — redirect/list behavior.

### Nomenclature management

- `/nomenclature/` — redirect на дерево.
- `/nomenclature/tree/` — дерево номенклатуры.
- `/nomenclature/cache/sync/` — POST sync cache.
- `/nomenclature/categories/` — список категорий.
- `/nomenclature/categories/create/` — создание категории.
- `/nomenclature/categories/<pk>/edit/` — редактирование категории.
- `/nomenclature/categories/<pk>/delete/` — удаление/деактивация категории.
- `/nomenclature/categories/merge/` — слияние категорий.
- `/nomenclature/units/` — список единиц.
- `/nomenclature/units/create/` — создание единицы.
- `/nomenclature/units/<pk>/edit/` — редактирование единицы.
- `/nomenclature/units/<pk>/delete/` — удаление единицы.
- `/nomenclature/items/` — список ТМЦ.
- `/nomenclature/items/create/` — создание ТМЦ.
- `/nomenclature/items/<pk>/edit/` — редактирование ТМЦ.
- `/nomenclature/items/<pk>/delete/` — удаление/деактивация ТМЦ.
- `/nomenclature/items/merge/` — слияние ТМЦ.
- `/nomenclature/items/<pk>/split/` — разделение ТМЦ.

### Operations

- `/operations/` — журнал операций.
- `/operations/create/` — создание операции.
- `/operations/item-search/` — AJAX search.
- `/operations/item-create/` — JSON endpoint для temporary item flow.
- `/operations/<operation_id>/` — карточка операции.
- `/operations/<operation_id>/submit/` — POST отправки операции.
- `/operations/<operation_id>/cancel/` — POST отмены операции.
- `/operations/pending-acceptance/` — ожидающие приёмки.
- `/operations/<operation_id>/acceptance/` — форма приёмки.
- `/operations/<operation_id>/acceptance/submit/` — POST приёмки.
- `/operations/lost-assets/` — непринятые/потерянные позиции.
- `/operations/lost-assets/<operation_line_id>/` — карточка lost asset.
- `/operations/lost-assets/<operation_line_id>/resolve/` — POST resolve.

### Balances

- `/balances/` — список остатков.
- `/balances/summary/` — сводка остатков.
- `/balances/by-site/` — остатки по складу.

### Temporary items

- `/temporary-items/` — список временных ТМЦ.
- `/temporary-items/item-search/` — AJAX поиск постоянных ТМЦ.
- `/temporary-items/<item_id>/` — карточка временной ТМЦ.
- `/temporary-items/<item_id>/approve/` — утверждение как постоянной ТМЦ.
- `/temporary-items/<item_id>/merge/` — слияние с существующей ТМЦ.
- `/temporary-items/<item_id>/delete/` — удаление.

## API Coverage From API_MAP

Проверять через UI и network requests следующие группы SyncServer API:

- Auth: `/auth/me`, `/auth/sites`, `/auth/context`, `/auth/sync-user`.
- Admin: `/admin/sites`, `/admin/users`, `/admin/users/{id}/scopes`, `/admin/access/scopes`, `/admin/devices`.
- Catalog read: `/catalog/items`, `/catalog/categories`, `/catalog/categories/tree`, `/catalog/units`, `/catalog/sites`, `/catalog/read/items`.
- Catalog admin: `/catalog/admin/units`, `/catalog/admin/categories`, `/catalog/admin/items`.
- Operations: `/operations`, `/operations/{id}`, `/operations/{id}/submit`, `/operations/{id}/cancel`, `/operations/{id}/accept-lines`.
- Balances: `/balances`, `/balances/by-site`, `/balances/summary`.
- Temporary items: `/temporary-items`, `/temporary-items/{id}`, `/temporary-items/{id}/merge`, `/temporary-items/{id}/approve-as-item`, `/temporary-items/{id}/operations`.
- Asset registers: `/pending-acceptance`, `/lost-assets`, `/lost-assets/{operation_line_id}`, `/lost-assets/{operation_line_id}/resolve`, `/issued-assets`.
- Documents: `/documents/*`, если UI появится или будет доступен через операционную карточку.
- Reports: `/reports/item-movement`, `/reports/stock-summary`, если UI появится.

## End-To-End Workflow

### Phase 0. Стенд и health

1. Поднять SyncServer.
2. Поднять Warehouse_web.
3. Проверить `/api/v1/health`, `/api/v1/ready`.
4. Проверить `/healthz/`, `/healthz/sync/`.
5. Открыть `/login/` через Playwright.
6. Проверить отсутствие JS console errors на login page.

Acceptance:

- Оба сервера отвечают.
- Login page отображает поля логина/пароля и submit button.
- В console нет fatal JS errors.

### Phase 1. Root login и базовая навигация

1. Войти root/superuser в Warehouse_web.
2. Открыть `/client/`.
3. Проверить sidebar: Главная, Каталог, Остатки, Операции, Номенклатура, Администрирование.
4. Открыть `/users/sync/identity/`.
5. Открыть `/users/sync/site-switch/`, если доступно несколько складов.

Acceptance:

- Root видит admin/nomenclature разделы.
- Sync identity отображается без ошибки.
- Site switch не ломает сессию.

### Phase 2. Root создаёт склад

Primary UI: Django admin.

1. Открыть `/admin/users/site/add/`.
2. Создать склад с уникальным code/name.
3. Проверить, что после сохранения появился `syncserver_site_id`.
4. Открыть список складов и найти созданный склад.
5. Проверить через custom/UI или API, что склад доступен в `/auth/sites` или `/catalog/sites`.

Acceptance:

- Склад создан локально и в SyncServer.
- В форме/списке нет SyncServer ошибок.
- `syncserver_site_id` заполнен.

### Phase 3. Root создаёт пользователей

Primary UI: Django admin.

Создать трёх пользователей:

- chief storekeeper: роль `chief_storekeeper`, default site = тестовый склад;
- storekeeper: роль `storekeeper`, default site = тестовый склад;
- observer: роль `observer`, default site = тестовый склад.

Шаги для каждого:

1. Открыть `/admin/auth/user/add/`.
2. Заполнить username, email, password, full_name, role, default_site_id, is_active.
3. Сохранить.
4. Открыть карточку пользователя.
5. Проверить Sync status и наличие user token/binding.
6. При необходимости выполнить sync/repair action из admin change form.

Acceptance:

- Пользователи созданы в Django и SyncServer.
- У каждого есть `SyncUserBinding` и `sync_user_token`.
- Роль и default site совпадают с ожидаемыми.

### Phase 4. Permission smoke

Проверить видимость и запреты по ролям.

Root:

- Видит `/admin/`, `/admin-panel/*`, `/nomenclature/*`, `/operations/*`, `/balances/*`.

Chief storekeeper:

- Видит `/nomenclature/*`, `/temporary-items/*`, `/operations/*`, `/balances/*`.
- Не должен видеть Django admin, если не staff/superuser.

Storekeeper:

- Видит `/client/`, `/catalog/`, `/operations/*`, `/balances/*`.
- Не должен иметь доступ к `/nomenclature/*`, `/temporary-items/*`, `/admin-panel/*`.

Observer:

- Проверить фактическое поведение dashboard и read-only pages.
- Dashboard в коде может запрещать observer, несмотря на `can_use_client`.

Acceptance:

- UI соответствует role matrix или выявлен дефект/несоответствие.
- Forbidden/redirect cases не дают 500.

### Phase 5. Номенклатура

Пользователь: chief или root.

1. Открыть `/nomenclature/units/`.
2. Создать единицу через `/nomenclature/units/create/`.
3. Отредактировать единицу.
4. Открыть `/nomenclature/categories/`.
5. Создать категорию через `/nomenclature/categories/create/`.
6. Отредактировать категорию.
7. Открыть `/nomenclature/items/`.
8. Создать ТМЦ через `/nomenclature/items/create/`, указав unit/category.
9. Отредактировать ТМЦ.
10. Открыть `/nomenclature/tree/` и проверить, что category/item отображаются в дереве.
11. Выполнить POST `/nomenclature/cache/sync/` кнопкой sync cache.
12. Открыть `/catalog/` как storekeeper и проверить, что ТМЦ ищется в browse catalog.

Acceptance:

- Unit/category/item создаются через UI.
- Списки, поиск, pagination и дерево видят созданные сущности.
- Network requests к `/catalog/admin/*` успешны.
- Ошибки формы отображаются в UI, не как 500.

### Phase 6. Операция RECEIVE

Пользователь: storekeeper.

1. Войти storekeeper.
2. Открыть `/operations/create/`.
3. Выбрать тип `RECEIVE`.
4. Убедиться, что выбран/доступен тестовый склад.
5. Через item search найти созданную ТМЦ.
6. Добавить строку с количеством, например `10`.
7. Заполнить дату/примечание, если требуется.
8. Нажать `Создать операцию`.
9. Открыть карточку операции.
10. Нажать `Отправить`.
11. Перейти в `/operations/pending-acceptance/`.
12. Найти операцию в ожидающих приёмки.

Acceptance:

- Operation draft payload формируется корректно.
- `POST /operations` успешен.
- `POST /operations/{id}/submit` успешен.
- Операция появляется в pending acceptance.

### Phase 7. Полная приёмка

Пользователь: storekeeper или chief с доступом к складу назначения.

1. Открыть `/operations/<id>/acceptance/`.
2. В строке операции указать `accepted_qty = 10`, `lost_qty = 0`.
3. Нажать `Подтвердить приёмку`.
4. Открыть `/balances/` и `/balances/by-site/`.
5. Проверить, что остаток по ТМЦ увеличился на `10`.
6. Проверить, что операция исчезла из pending acceptance или получила accepted status.

Acceptance:

- `POST /operations/{id}/accept-lines` успешен.
- Баланс увеличился.
- Pending acceptance обновился.

### Phase 8. Частичная приёмка с lost assets

Создать вторую RECEIVE или MOVE операцию.

1. Добавить количество, например `10`.
2. Submit operation.
3. На acceptance указать `accepted_qty = 7`, `lost_qty = 3`.
4. Подтвердить приёмку.
5. Открыть `/operations/lost-assets/`.
6. Найти lost asset по операции/ТМЦ.
7. Открыть detail.
8. Проверить варианты resolve: `found_to_destination`, `return_to_source`, `write_off`.
9. Выполнить один безопасный resolve на тестовой записи.
10. Проверить статус lost asset и изменение остатков.

Acceptance:

- UI validation не позволяет `accepted_qty + lost_qty > remaining`.
- Lost asset создаётся после частичной приёмки.
- Resolve работает и не даёт 500.

### Phase 9. MOVE flow

Предусловие: на source site есть положительный остаток тестовой ТМЦ.

1. Root/chief создаёт второй тестовый склад, если нужен destination.
2. Storekeeper/chief создаёт MOVE из source в destination.
3. Добавляет ТМЦ и количество.
4. Submit operation.
5. Destination user проходит acceptance.
6. Проверить source/destination balances.

Acceptance:

- MOVE требует source и destination.
- Source balance уменьшается при корректном workflow.
- Destination balance увеличивается после acceptance.

### Phase 10. EXPENSE flow

1. Создать EXPENSE операцию.
2. Указать recipient name.
3. Добавить ТМЦ с положительным остатком.
4. Submit operation.
5. Проверить `/balances/` и `/issued-assets`, если есть UI/API exposure.

Acceptance:

- EXPENSE требует recipient.
- Баланс корректно уменьшается.
- UI показывает ошибку при отсутствии recipient.

### Phase 11. Temporary item flow

Пользователь: storekeeper создаёт операцию с отсутствующей ТМЦ; chief/root модерирует.

1. На `/operations/create/` в item search ввести несуществующее имя.
2. Добавить temporary item line, если UI предлагает такой сценарий.
3. Создать и submit operation.
4. Chief/root открыть `/temporary-items/`.
5. Найти temporary item.
6. Открыть detail.
7. Проверить approve flow через `/temporary-items/<id>/approve/`.
8. Альтернативно проверить merge flow через `/temporary-items/<id>/merge/` и AJAX `/temporary-items/item-search/`.
9. Проверить, что temporary item стал resolved/merged/approved.

Acceptance:

- Temporary item создаётся и отображается.
- Approve создаёт постоянную ТМЦ.
- Merge связывает temporary item с существующей ТМЦ.
- Delete запрещён/разрешён согласно состоянию без 500.

### Phase 12. Balances и каталог после операций

1. Проверить `/balances/` filters: search, item_id, site_id, only_positive, page_size.
2. Проверить `/balances/by-site/` с тестовым складом.
3. Проверить `/balances/summary/`.
4. Проверить `/catalog/` как storekeeper: поиск созданной ТМЦ.
5. Проверить pagination/reset кнопки.

Acceptance:

- Остатки соответствуют операциям.
- Фильтры не ломают страницу.
- Storekeeper видит только доступные склады/данные.

### Phase 13. Devices и access panel

Пользователь: root.

1. Открыть `/admin-panel/devices/`.
2. Создать устройство через `/admin-panel/devices/create/`.
3. Отредактировать устройство.
4. Открыть `/admin-panel/access/`.
5. Проверить, что доступы созданных пользователей отображаются.

Acceptance:

- Device create/edit работает через SyncServer `/admin/devices`.
- Access page отображает данные без 500.

## Browser Verification Protocol

На каждой ключевой странице фиксировать:

- URL и роль пользователя.
- Accessibility snapshot: наличие заголовка, формы, таблицы, основных кнопок.
- Console messages уровня error/warning.
- Network requests к SyncServer: status code, unexpected 4xx/5xx.
- Screenshot при ошибке или визуальном дефекте.
- Текст UI-сообщения об успехе/ошибке.

Ошибкой считать:

- HTTP 500 на Django UI.
- JS error, влияющий на сценарий.
- SyncServer 4xx/5xx без понятного UI-сообщения.
- Успешное UI-сообщение при фактически не созданной сущности.
- Нарушение role permissions.
- Некорректный баланс после операции.

## Known UI Gaps

- Custom `/admin-panel/` не создаёт пользователей/склады/права; root setup покрывается через Django Admin.
- `apps.documents.urls` пустой, хотя SyncServer Documents API существует.
- Reports UI не найден, хотя SyncServer имеет `/reports/item-movement` и `/reports/stock-summary`.
- Recipients CRUD/merge API есть, но UI найден только как dropdown в lost asset resolve.
- Catalog bulk endpoints не имеют UI.
- Часть catalog read endpoints не имеет прямого UI покрытия.
- Temporary item endpoint `/temporary-items/{id}/operations` не имеет отдельной UI-страницы.
- Approve temporary item в UI реализован через create catalog item + merge, а не напрямую через `/approve-as-item`.
- Некоторые list row buttons в category/item UI выглядят как placeholder и требуют проверки в браузере.

## VM Fallback Plan

Использовать только если локальный запуск невозможен или нужен container smoke.

1. Через `ssh-stand` проверить ОС, docker, compose, свободные порты, текущие контейнеры.
2. Проверить, что PostgreSQL доступен и база тестовая.
3. Не выполнять `docker volume rm`, `docker compose down -v`, drop database или reset без явного подтверждения.
4. Развернуть SyncServer контейнер, выполнить migrations.
5. Развернуть Warehouse_web контейнер, выполнить migrations/collectstatic.
6. Проверить health endpoints.
7. Запустить те же Playwright UI сценарии против VM URL.

## Итоговые артефакты прогона

После выполнения UI-тестирования сформировать отчёт:

- окружение: local или VM, commit/hash, дата;
- список пройденных кейсов;
- список дефектов с URL, ролью, шагами, expected/actual;
- console/network findings;
- screenshots для дефектов;
- рекомендации: fix now / backlog / gap by design.
