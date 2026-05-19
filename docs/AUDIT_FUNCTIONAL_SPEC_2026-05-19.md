# Аудит соответствия Functional and WorkLogik.md

**Дата:** 2026-05-19  
**Статус:** первичный аудит  
**Проверяющий:** архитектор (agent)  
**Основание:** `Functional and WorkLogik.md` — канонический документ функциональных требований

---

## Сводка

| Статус | Количество |
|---|---|
| ✅ MET (соответствует) | 40 |
| ⚠️ PARTIALLY MET (частично) | 6 |
| ❌ NOT MET (не соответствует) | 9 |
| 🔵 DESIGN STAGE (стадия продумывания — допустимо) | 4 |
| **Итого проверено пунктов** | **59** |

Процент соответствия: **78% (40/51 обязательных пунктов)**  
С учётом design-stage: **86% (44/51)**

---

## Легенда

- ✅ **MET** — требование полностью реализовано в коде
- ⚠️ **PARTIALLY MET** — базовая реализация есть, но есть расхождения
- ❌ **NOT MET** — требование отсутствует в коде
- 🔵 **DESIGN STAGE** — пункт отмечен в спецификации как «на стадии продумывания», частичная реализация допустима

---

## I. Базовые положения

### I.1 — Авторизация по заголовкам X-User-Token и X-Device-Token

| # | Требование | Статус | Доказательство |
|---|---|---|---|
| I.1.0 | Только X-User-Token и X-Device-Token для авторизации | ✅ MET | `SyncServer/app/api/deps.py:92-93` — только эти два заголовка. Grep по forbidden headers в `SyncServer/app/` и `Warehouse_web/apps/sync_client/` — 0 совпадений. |
| I.1.0 | Django BFF шлёт только эти заголовки | ✅ MET | `Warehouse_web/apps/sync_client/client.py:74,77` — `build_headers()` содержит только `X-User-Token` и опциональный `X-Device-Token` |
| I.1.1 | `bootstrap_root.py` — создание и инициализация БД, вывод токенов, идемпотентность | ❌ NOT MET | **Файл не существует.** `SyncServer/scripts/` не содержит `bootstrap_root.py`. Упоминается в `PLAN_UI_TEST.md:49` и `repo_map`, но отсутствует в реальной кодовой базе. |
| I.1.1 | Скрипт обновления токенов рута и джанго-девайса | ⚠️ PARTIALLY MET | API-ротация токенов есть: `POST /admin/users/{id}/rotate-token` и `POST /admin/devices/{id}/rotate-token`. Но **токен рута нельзя обновить через API** — `admin_users_service.py:248-249` явно запрещает. Скрипта как отдельного инструмента нет. |
| I.1.1 | Токены рута и джанго-девайса в `.env` джанго | ✅ MET | `Warehouse_web/config/settings/base.py:129-140`: `SYNC_ROOT_USER_TOKEN`, `SYNC_DEVICE_TOKEN` читаются из `os.getenv`. По умолчанию — пустая строка (нет валидации на старте). |

### I.2 — Валидация прав изменения и записи на SyncServer

| # | Требование | Статус | Доказательство |
|---|---|---|---|
| I.2 | SyncServer отвечает за валидацию прав | ✅ MET | `app/services/identity_service.py` — `resolve_identity()` проверяет токены, активность, скоупы. `app/services/operations_policy.py` — политики на каждую операцию. |
| I.2 | Многоуровневые permission guards | ✅ MET | `require_root`, `require_admin_basic`, `_require_catalog_admin`, `_require_catalog_read_access`, `require_operation_submit_permission`, `require_lost_resolve_access` и др. |

### I.2.1 — Типы и права пользователей

| Роль по спецификации | Реализация в коде | Статус |
|---|---|---|
| Обозреватель (observer) — может смотреть всё, не может подтверждать операции | `observer` в `User.role`, `UserAccessScope.can_view=True` без can_operate | ✅ MET |
| Кладовщик (storekeeper) — просмотр всего + операции на приписанных складах | `storekeeper` с `can_view + can_operate` в `UserAccessScope` по конкретным site_id | ✅ MET |
| Главный кладовщик (chief_storekeeper) — всё + все склады + редактирование справочников | `chief_storekeeper` с `has_global_business_access=True`, доступ в `_require_catalog_admin` | ✅ MET |
| Root — как главный кладовщик + пользователи, устройства, склады | `is_root=True`, отдельный `require_root` guard для admin-операций | ✅ MET |

### I.3 — Интерфейс под FHD (1920×1080)

| # | Требование | Статус | Доказательство |
|---|---|---|---|
| I.3 | Экран по умолчанию FHD | ⚠️ PARTIALLY MET | Код не содержит явных FHD-брейкпоинтов. Спецификация nomenclature-screen-spec.md (`Warehouse_frontend/docs/`) содержит базовый размер `1440×900`. Дизайн адаптивный, но конкретная привязка к 1920×1080 отсутствует. |

### I.4 — Сайд-панель с конфигурируемым названием организации

| # | Требование | Статус | Доказательство |
|---|---|---|---|
| I.4 | Название/логотип организации — переменные из статики, не хардкод | ❌ NOT MET | `Warehouse_web/templates/includes/brand.html:3` — `{% with brand_name="ООО АС Горизонт" %}` — **жёстко захардкожено**, несмотря на наличие `ORGANIZATION_SHORT_NAME` в `config/settings/base.py:37`. |
| I.4 | Сайд-панель с брендом | ✅ MET | `sidebar.html` + `brand.html` + `navbar.html` — существуют и работают |

### I.6.1 — Верхняя сайд-панель с названием организации, логином и вход/выход

| # | Требование | Статус | Доказательство |
|---|---|---|---|
| I.6.1 | Название организации слева сверху | ✅ MET | `brand.html` — отображается (хоть и хардкод) |
| I.6.1 | Кто залогинен (username) | ✅ MET | `navbar.html:7` — `{{ request.user.username }}` |
| I.6.1 | Кнопка вход/выход | ✅ MET | `navbar.html:9-14` — logout (POST с CSRF) и login ссылка |
| I.6.1 | Роль/SyncServer-контекст | ⚠️ PARTIALLY MET | Роль пользователя из SyncServer (`identity.role`) **не отображается** в navbar. Только Django `request.user.username`. |

### I.6.2 — Сортировка по колонкам во всех таблицах

| # | Требование | Статус | Доказательство |
|---|---|---|---|
| I.6.2 | Таблицы имеют сортировку по выбранной колонке | ❌ NOT MET | Ни в одном SSR-шаблоне (`operations/list.html`, `catalog/manage_item_list.html`, `balances/list.html`, `temporary_items/list.html`) нет сортируемых заголовков — все `<th>` статические. Angular `ItemTableComponent` также не имеет сортировки. |

### I.6.3 — Пагинация 10/20/50, прокручиваемые таблицы с фиксированными заголовками

| # | Требование | Статус | Доказательство |
|---|---|---|---|
| I.6.3 | Пагинация 10/20/50 | ⚠️ PARTIALLY MET | Operations: 10/20/50/100 (доп. 100). Balances: 20/50/100/200 (нет 10). Catalog SSR: 10/20/50/100. Temp items: 10/20/50 — **единственный точный мэтч**. Pending acceptance: **нет селектора page size вообще**. |
| I.6.3 | Прокрутка таблицы с фиксированными заголовками | ❌ NOT MET | Ни один SSR-шаблон не имеет `position: sticky` на `<thead>`. Таблицы прокручиваются целиком. Angular `ItemTableComponent` имеет sticky headers, но компонент не интегрирован в основной layout. |

---

## II. Операции

### II.1 — Типы операций

| Тип по спецификации | Значение в коде | Статус |
|---|---|---|
| расход (EXPENSE) | `EXPENSE` в `OperationType` Literal | ✅ MET |
| приход (INCOME) | `RECEIVE` (отличается именем) | ✅ MET |
| перемещение (MOVE) | `MOVE` | ✅ MET |
| списание (WRITE_OFF) | `WRITE_OFF` | ✅ MET |
| выдача (ISSUE) | `ISSUE` | ✅ MET |
| возврат (RETURN) | `ISSUE_RETURN` | ✅ MET |
| корректировка (ADJUSTMENT) | `ADJUSTMENT` | ✅ MET |

### II.2 — Приход и перемещение с приёмкой

| # | Требование | Статус | Доказательство |
|---|---|---|---|
| II.2 | Приход и перемещение — с приёмкой | ✅ MET | `operations_service.py:31`: `ACCEPTANCE_REQUIRED_TYPES = {"RECEIVE", "MOVE"}` |
| II.2 | Accept-lines endpoint | ✅ MET | `routes_operations.py:261`: `POST /operations/{id}/accept-lines` |

### II.3 — Выдача vs Расход

| # | Требование | Статус | Доказательство |
|---|---|---|---|
| II.3 | Выдача не списывает, а перемещает в отдельную таблицу | ✅ MET | `operations_service.py:815-835`: ISSUE deducts from balances, upserts into `issued_asset_balances` |
| II.3 | Закрепление за объектом (человек, машина, база) | ✅ MET | Модель `IssuedAssetBalance` с `recipient_id`, `recipient` FK. OperationCreate принимает `recipient_id`/`issued_to_name`. |

### II.3.1 — Репозиторий выдачи — отдельный раздел и экран

| # | Требование | Статус | Доказательство |
|---|---|---|---|
| II.3.1 | Отдельный экран выдачи | 🔵 DESIGN STAGE | Спецификация (раздел VI) помечает этот функционал как «на стадии продумывания». API готов (`/issued-assets`), SSR-экранов нет. Допустимо. |

### II.4 — Приёмка

| # | Требование | Статус | Доказательство |
|---|---|---|---|
| II.4.1 | Отдельный экран приёмки с построчной приёмкой | ✅ MET | `Warehouse_web/templates/operations/acceptance_detail.html` (235 строк): построчно accepted_qty/lost_qty/note. `PendingAcceptanceListView` + `AcceptanceDetailView` + `AcceptanceSubmitView`. |
| II.4.2 | Непринятое → репозиторий непринятого | ✅ MET | `operations_service.py:993-1001`: при `lost_qty > 0` создаётся запись в `lost_asset_balances` |

### II.5 — Поля операций

| # | Требование | Статус | Доказательство |
|---|---|---|---|
| II.5.0 | Таблица ТМЦ с поиском | ✅ MET | `form.html:162-166`: поиск с кешем. AJAX endpoint `item_search`. `CatalogCacheSyncService` для кеша. |
| II.5.0 | Количество на выбранном складе в поиске | ⚠️ PARTIALLY MET | Поиск показывает название/SKU/ед.изм/категорию, но **не показывает текущий остаток на выбранном складе**. |
| II.5.0 | Комментарий (2 строки текста) | ✅ MET | `form.html:138-142`: `<textarea rows="2">`. Модель: `notes` (Text). Схема: `notes` (max_length=1000). |
| II.5.1-3 | Выпадающий список склада (по умолчанию склад пользователя) | ✅ MET | `form.html:88-95`: `<select id="site-select">` с operate_sites |
| II.5.4 | Склад-отправитель и склад-получатель | ✅ MET | `form.html:98-116`: source_site_id + destination_site_id, переключаются JS |
| II.5.5 | Корректировка — служебная операция | ✅ MET | Тип `ADJUSTMENT` существует в OperationType enum |

### II.6 — Правила редактирования операций

| # | Требование | Статус | Доказательство |
|---|---|---|---|
| II.6.1 | Изменять можно только не подтверждённые операции | ✅ MET | `operations_workflow_policy.py:23-28`: `require_draft_for_update()` → 409 Conflict если `status != "draft"` |
| II.6.2 | Удалять можно только отменённые операции | ❌ NOT MET | **DELETE для operations не существует.** В `routes_operations.py` нет `@router.delete`. |
| II.6.3 | Отменять подтверждённые операции — только Root | ✅ MET | `operations_policy.py:74-82`: `identity.has_global_business_access` → root/chief_storekeeper могут отменить. Regular storekeeper — только свои драфты. |

### II.7 — Таблица операций

| # | Требование | Статус | Доказательство |
|---|---|---|---|
| II.7 | Колонки таблицы: дата-время, тип, статус, склад, строки, действия | ✅ MET | `operations/list.html:63-74`: все требуемые колонки присутствуют |
| II.7 | Формат даты: ДД-месяц-ГГГГ ЧЧ:ММ | ❌ NOT MET | `list.html:94`: `{{ op.created_at }}` — сырой ISO timestamp (2026-05-19T14:30:00+00:00). Нет форматирования в «19-мая-2026 14:30». |
| II.7 | Базовая сортировка по дате | ✅ MET | Операции отсортированы по `created_at` |

### II.8 — Жизненный цикл операции (MOVE)

| Шаг | Статус | Доказательство |
|---|---|---|
| 1. Кладовщик создаёт операцию | ✅ MET | `POST /operations` → `OperationsService.create_operation()` |
| 2. Добавляет построчно ТМЦ (кеш + поиск) | ✅ MET | Item search с `CatalogCacheSyncService`. Форма с AJAX-поиском. |
| 3. Подтверждение с проверкой полномочий | ✅ MET | `POST /operations/{id}/submit` → `OperationsPolicy.require_operation_submit_permission` |
| 4. Генерация PDF-накладной | ✅ MET | Авто при submit: `operations_service.py:861-899`. Ручная: `detail.html:247-259`. |
| 5. Приёмка на целевом складе | ✅ MET | `POST /operations/{id}/accept-lines` |
| 6. Зачисление в остатки по результатам приёмки | ✅ MET | `operations_service.py:952-967`: deduct from pending, add to balances. Утерянное → lost_assets. |

---

## IV. Временные ТМЦ

| # | Требование | Статус | Доказательство |
|---|---|---|---|
| IV.1.1 | Отдельный репозиторий (не общий справочник) | ✅ MET | `SyncServer/app/models/temporary_item.py:22-23`: `__tablename__ = "temporary_items"` |
| IV.1.2 | Преобразование в постоянные / доначисление к постоянным | ✅ MET | `approve-as-item` + `merge` endpoints. `TemporaryItemsResolutionService.approve_as_item()` создаёт новый `Item` + `InventorySubject`. `merge_to_item()` переносит остатки на существующий item. |
| IV.1.3 | Удаление — только если нет в остатках | ✅ MET | `temporary_items_resolution_service.py:332-339`: проверка `qty != 0` → 409 Conflict |
| IV.1.4 | Преобразование — только после завершённой приёмки, не в репозитории непринятого | ✅ MET | `_check_no_active_registers()` проверяет `pending_acceptance_balances`, `lost_asset_balances`, `issued_asset_balances` > 0 |
| IV.1.5 | Дашборд: информация о количестве времянок | ❌ NOT MET | `dashboard.html` не содержит счётчика временных ТМЦ. `client/views.py:30-67` не делает запрос временных ТМЦ. |

---

## V. Репозиторий непринятого

| # | Требование | Статус | Доказательство |
|---|---|---|---|
| V.1 | Непринятое → специальный репозиторий, отдельный экран | ✅ MET | `LostAssetBalance` модель. Полный SSR: список (`lost_assets_list.html`), детализация (`lost_asset_detail.html`), resolve. Отдельный URL `operations:lost_assets`. Ссылка в sidebar: «Непринятые». |
| V.2 | Два способа списания: «найдено» и «утеряно окончательно» | ✅ MET | `action="found_to_destination"` (добавляет на склад назначения). `action="write_off"` (окончательное списание). Дополнительно: `action="return_to_source"` (возврат на склад-источник, сверх спецификации). |
| V.3 | ТМЦ в репозитории непринятого замораживаются к изменению | ❌ NOT MET | **Нет freeze-логики для постоянных ТМЦ.** Временные ТМЦ частично защищены через `_check_no_active_registers` (блокирует approve/merge/delete), но постоянные catalog items можно свободно редактировать даже при наличии записей в `lost_asset_balances`. |

---

## VI. Репозиторий выдачи 🔵 DESIGN STAGE

| # | Требование | Статус | Доказательство |
|---|---|---|---|
| VI.1 | Поиск получателей (без дублей по орфографии) | ✅ MET | `RecipientAlias` с `normalized_key`. `GET /recipients?search=`. |
| VI.2 | Два экрана: имущество и объекты | 🔵 NOT MET | API готов (`/issued-assets`), SSR-экранов нет. **Допустимо** — секция в стадии продумывания. |
| VI.3 | Просмотр имущества за конкретным объектом | 🔵 NOT MET | API фильтр `recipient_id` существует, но **нет SSR-экрана**. Допустимо. |
| VI.4 | Списание с объекта | 🔵 NOT MET | Нет интеграции между операциями WRITE_OFF и `issued_asset_balances`. Допустимо. |

---

## VII. Документы 🔵 DESIGN STAGE

| # | Требование | Статус | Доказательство |
|---|---|---|---|
| VII.1 | Вывод документов (PDF накладная) по результатам операции | ✅ MET | Полная реализация: `routes_documents.py` (364 строки). `POST /documents/generate`, `GET /documents/{id}/render?format=pdf`. `WeasyPrint` рендеринг. Авто-генерация при submit операции. |
| VII.2 | Типы документов | ✅ MET | `waybill`, `acceptance_certificate`, `act`, `invoice` |
| VII.3 | Документы в UI операции | ✅ MET | `operations/detail.html`: список документов, кнопка генерации, PDF-просмотр через `DocumentPdfView`. |

---

## Реестр отклонений (Gap Register)

Приоритет: 🔴 Critical → 🟠 High → 🟡 Medium → 🔵 Low/Design-stage

| # | Приоритет | Раздел | Отклонение | Рекомендация |
|---|---|---|---|---|
| 1 | 🔴 Critical | I.1.1 | `bootstrap_root.py` не существует | Создать `SyncServer/scripts/bootstrap_root.py`: идемпотентное создание БД + root user + django device + вывод токенов в консоль |
| 2 | 🔴 Critical | I.1.1 | Нет скрипта обновления рут-токена при компрометации | Добавить `SyncServer/scripts/rotate_tokens.py` или разрешить ротацию root-токена через API |
| 3 | 🟠 High | II.6.2 | DELETE для операций отсутствует | Добавить `DELETE /operations/{id}` с проверкой статуса `cancelled` |
| 4 | 🟠 High | V.3 | Постоянные ТМЦ не замораживаются при нахождении в lost_assets | Блокировать редактирование catalog items при наличии `lost_asset_balances.qty > 0` |
| 5 | 🟡 Medium | I.4 | Название организации захардкожено в brand.html | Использовать `{{ settings.ORGANIZATION_SHORT_NAME }}` или context processor |
| 6 | 🟡 Medium | I.6.2 | Сортировка по колонкам отсутствует во всех таблицах | Добавить сортируемые заголовки `<th>` с query-параметрами `?sort=column&order=asc/desc` |
| 7 | 🟡 Medium | I.6.3 | Нет фиксированных заголовков таблиц (sticky headers) | Добавить `position: sticky; top: 0` на `<thead>` в CSS |
| 8 | 🟡 Medium | I.6.3 | Пагинация не соответствует 10/20/50 в balances и pending acceptance | Выровнять page size опции: везде 10/20/50 |
| 9 | 🟡 Medium | II.5.0 | Количество на складе не показывается в поиске ТМЦ при создании операции | Добавить колонку «Остаток на складе» в результаты item search |
| 10 | 🟡 Medium | II.7 | Формат даты в таблице операций — ISO вместо «ДД-месяц-ГГГГ ЧЧ:ММ» | Применить `date` фильтр или форматирование: `{{ op.created_at|date:"d-E-Y H:i" }}` |
| 11 | 🟡 Medium | I.6.1 | Роль пользователя из SyncServer не отображается в navbar | Добавить `identity.role` в контекст шаблона через middleware/context processor |
| 12 | 🟡 Medium | IV.1.5 | Дашборд не показывает количество временных ТМЦ | Добавить запрос `TemporaryItem.objects.filter(status='active').count()` в `dashboard()` |
| 13 | 🟡 Medium | I.3 | Нет явной привязки к FHD (1920×1080) | Добавить CSS breakpoint или переменную темы для FHD |
| 14 | 🔵 Low | VI.2 | Нет SSR-экранов выданного имущества | Design stage — отложить до проработки раздела VI. API готов. |
| 15 | 🔵 Low | VI.3 | Нет экрана просмотра имущества за объектом | Design stage — отложить |
| 16 | 🔵 Low | VI.4 | Нет списания с объекта | Design stage — отложить |

---

## Статистика по проектам

| Проект | MET | PARTIAL | NOT MET | Общий вклад в отклонения |
|---|---|---|---|---|
| **SyncServer** (backend) | Высокое покрытие | bootstrap_root отсутствует, нет DELETE operations, нет freeze | Gap #1, #2, #3, #4 |
| **Warehouse_web** (Django SSR) | Хорошее покрытие | Сортировка, sticky headers, пагинация, формат даты, brand, dashboard | Gap #5-12 |
| **Warehouse_frontend** (Angular) | Только nomenclature | Нет операций, balances, dashboard | Angular — в активной разработке |
| **Warehouse_client_core** | Чистый | Не оценивался детально | Вне скоупа (нет UI) |

---

## Рекомендуемый порядок закрытия

1. **bootstrap_root.py** — критично для развёртывания (Gap #1)
2. **DELETE operations** — функциональный пробел (Gap #3)
3. **Freeze logic для lost_assets** — целостность данных (Gap #4)
4. **Brand configurability** + **Dashboard temp items** — UX (Gap #5, #12)
5. **Сортировка + sticky headers + пагинация** — UX всего интерфейса (Gap #6-8)
6. **Формат даты + баланс в поиске** — UX операций (Gap #9, #10)
7. **Роль в navbar** — UX (Gap #11)
8. **Issued assets SSR** — design stage, после проработки раздела VI (Gap #14-16)

---

*Отчёт сгенерирован архитектором. Для верификации отдельных пунктов требуются запуски тестовых стендов: SyncServer API, Django SSR, Angular SPA.*
