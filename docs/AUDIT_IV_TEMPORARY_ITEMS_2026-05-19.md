# Аудит раздела IV: Временные ТМЦ

**Дата:** 2026-05-19  
**Основание:** `Functional and WorkLogik.md`, раздел IV
**Статус в спецификации:** `#функционал реализован в виде SSR`

---

## Сводка

| Статус | Количество |
|---|---|
| ✅ MET | 7 |
| ⚠️ PARTIALLY MET | 3 |
| ❌ NOT MET | 7 |
| **Итого** | **17 пунктов** |

**Процент соответствия: 41% (7/17)**  
С учётом partial: **59% (10/17)**

---

## Пункт 0. Преамбула

> «временные ТМЦ имеют системную категорию "uncotegoryzed" и системный юнит "штука"»

| Требование | Статус | Доказательство |
|---|---|---|
| Системная категория для времянок | ⚠️ PARTIALLY MET | `app/core/catalog_defaults.py:3-4`: `UNCATEGORIZED_CATEGORY_NAME = "Без категории"`, `UNCATEGORIZED_CATEGORY_CODE = "__UNCATEGORIZED__"`. Используется как fallback при `category_id is None` в `operations_service.py:413`. **НО:** код категории `__UNCATEGORIZED__`, а не `uncotegoryzed` как в спецификации. Функционально эквивалентно. |
| Системный юнит «штука» | ❌ NOT MET | `app/core/catalog_defaults.py:6-8`: `DEFAULT_UNIT_CODE = "шт"`, `DEFAULT_UNIT_NAME = "Штука"`, `DEFAULT_UNIT_SYMBOL = "шт"` — константы **определены, но НЕ используются** как fallback. В `app/schemas/temporary_item.py:16`: `unit_id: int` — обязательное поле в `TemporaryItemInlineCreate`. При создании временной ТМЦ (`operations_service.py:650`) `unit_id_value = payload["unit_id"]` — юнит должен быть явно передан клиентом, дефолта нет. |

---

## IV.1. Правила временных ТМЦ

### IV.1.1 — Отдельный репозиторий

> «временное ТМЦ создаётся и висит не в общем справочнике а в отдельном репозитории»

| Требование | Статус | Доказательство |
|---|---|---|
| Отдельная таблица | ✅ MET | `app/models/temporary_item.py:22-23`: `class TemporaryItem(Base): __tablename__ = "temporary_items"` — отдельная от `items` (постоянный каталог) таблица |
| Отдельный API | ✅ MET | `app/api/routes_temporary_items.py` (164 строки): полный CRUD с отдельным префиксом `/temporary-items` |
| Отдельный SSR-экран | ✅ MET | `Warehouse_web/apps/temporary_items/views.py` (404 строки): `TemporaryItemListView`. `Warehouse_web/templates/temporary_items/list.html` (189 строк). Отдельный URL namespace `temporary_items:`. Ссылка в sidebar. |
| При создании через операцию создаётся backing item (is_active=False) | ✅ MET | `operations_service.py:653-665`: создаётся `Item(is_active=False, source_system="temporary_item")` как backing item, к которому привязывается `TemporaryItem` |

### IV.1.2 — Преобразование в постоянные / доначисление

> «временные ТМЦ могут(и должны) быть преобразованны в постоянные или доначисленны к постоянным»

| Требование | Статус | Доказательство |
|---|---|---|
| `approve-as-item`: создание нового постоянного item | ✅ MET | `routes_temporary_items.py:74-91`: `POST /{id}/approve-as-item`. `temporary_items_resolution_service.py:116-200`: создаёт новый `Item` (строка 157-169), новый `InventorySubject` (строка 172), переносит остатки через ADJUSTMENT-операции (строка 180-189), резолвит temp item (строка 192-198) |
| `merge`: слияние с существующим постоянным item | ✅ MET | `routes_temporary_items.py:122-142`: `POST /{id}/merge`. `temporary_items_resolution_service.py:202-291`: валидирует target item (строка 231-241), переносит остатки (строка 265-274), архивирует temp subject (строка 277), резолвит temp item (строка 284-289) |
| Django UI: approve screen (преобразование) | ✅ MET | `Warehouse_web/apps/temporary_items/views.py:111-244`: `TemporaryItemApproveView` — создаёт catalog item через `CatalogService.create_item()`, затем вызывает `merge_to_item()` на SyncServer. **Особенность:** используется связка «создать + merge», а не прямой `approve-as-item` API. |
| Django UI: merge screen (объединение) | ✅ MET | `temporary_items/views.py:247-291`: `TemporaryItemMergeView` — поиск target item через `TemporaryItemCatalogSearchView`, затем `merge_to_item()` |

### IV.1.3 — Удаление только при нулевых остатках

> «удалять временные ТМЦ можно только если их нет в остатках»

| Требование | Статус | Доказательство |
|---|---|---|
| Баланс-чек перед удалением | ✅ MET | `temporary_items_resolution_service.py:332-339`: `for balance_row in balances: if balance_row.qty != 0: raise HTTPException(409, "temporary item has non-zero balances; cannot delete")` |
| Проверка активных регистров | ✅ MET | `temporary_items_resolution_service.py:327-330`: также `_check_no_active_registers()` перед удалением |
| Мягкое удаление (soft delete) | ✅ MET | Статус меняется на `STATUS_DELETED = "deleted"` (модель, строка 71). Backing item деактивируется (строка 345-346), inventory subject архивируется (строка 342) |
| Django UI: подтверждение удаления | ✅ MET | `temporary_items/views.py:318-365`: `TemporaryItemDeleteView` — GET для подтверждения, POST для удаления. `confirm_delete.html` шаблон. |
| Массовое удаление | ✅ MET | `temporary_items/views.py:368-404`: `TemporaryItemBulkDeleteView` — удаление выбранных через чекбоксы в таблице |

### IV.1.4 — Преобразование только после завершённой приёмки

> «преобразовать временную тмц в постоянную (или сделать мерж с постоянной) можно только после завершённой приёмки где есть эта временная тмц, временной ТМЦ не должно быть в репозитории непринятого»

| Требование | Статус | Доказательство |
|---|---|---|
| Блокировка approve при активных регистрах | ✅ MET | `temporary_items_resolution_service.py:152-154`: `_check_no_active_registers()` перед approve. Проверяет `pending_acceptance_balances`, `lost_asset_balances`, `issued_asset_balances` |
| Блокировка merge при активных регистрах | ✅ MET | `temporary_items_resolution_service.py:252-254`: `_check_no_active_registers()` перед merge |
| Что именно проверяется | ✅ MET | `asset_registers_repo.has_active_registers()` — запрос всех трёх таблиц регистров на `qty > 0`. Т.е. если временная ТМЦ есть в pending acceptance (не завершена приёмка), в lost assets (непринятое), или в issued assets — преобразование заблокировано. |
| Блокировка delete при активных регистрах | ✅ MET | `temporary_items_resolution_service.py:328-330`: тоже `_check_no_active_registers()` |

### IV.1.5 — Дашборд: информация о количестве времянок

> «в дашборде должна висеть информация о количестве времянок с просьбой незабыть преобразовать их в постоянные»

| Требование | Статус | Доказательство |
|---|---|---|
| Запрос количества в контроллере | ✅ MET | `Warehouse_web/apps/client/views.py:66-72`: `temp_api.list_temporary_items_page(filters={"status": "active", "page_size": 1})` → `temp_item_count = page_result.get("total_count", 0)` |
| Отображение в шаблоне | ✅ MET | `Warehouse_web/templates/client/dashboard.html:28-49`: карточка «Временные ТМЦ» с бейджем. Если `temp_item_count > 0` — бейдж `badge-warning`. Текст «Требуют внимания». Кнопка «Открыть» ведёт на `temporary_items:list`. |
| **ВАЖНОЕ УТОЧНЕНИЕ** | ✅ MET | **В сводном аудите (AUDIT_FUNCTIONAL_SPEC_2026-05-19.md) этот пункт был ошибочно отмечен как NOT MET.** На самом деле он **реализован** — и в контроллере, и в шаблоне. Сводный аудит необходимо скорректировать. |

---

## IV.2. Интерфейс экрана временных ТМЦ

### IV.2.1 — Таблица с пагинацией, сортировкой, прокруткой

> «таблица с пагинацией сортировкой и прокруткой с полями название, когда создана и количество в остатках»

| Требование | Статус | Доказательство |
|---|---|---|
| Пагинация 10/20/50 | ✅ MET | `temporary_items/list.html:57-65`: `<select id="page_size">` — 10, 20, 50. **Единственный экран в системе с точным соответствием спецификации I.6.3.** |
| Колонка «Название» | ✅ MET | `list.html:102`: `{{ item.name\|default:"—" }}` |
| Колонка «Когда создана» | ✅ MET | `list.html:117`: `{{ item.created_at\|date:"d.m.Y H:i" }}` — формат даты ДД.ММ.ГГГГ ЧЧ:ММ |
| Колонка **«Количество в остатках»** | ❌ NOT MET | **Отсутствует.** Таблица показывает: ID, Название, Код, Статус, Создано, Действия. Колонки с остатками нет. `TemporaryItemResponse` schema (`app/schemas/temporary_item.py:21-43`) **не содержит поле с остатками**. API `GET /temporary-items` не возвращает балансы. |
| Сортировка по колонкам | ❌ NOT MET | Все `<th>` в `list.html` статические, без sort-контролов. Совпадает с общей проблемой I.6.2. |
| Прокрутка таблицы с фиксированными заголовками | ❌ NOT MET | Нет `position: sticky` на `<thead>`. Таблица прокручивается целиком. |

### IV.2.2 — Модальное окно при клике

> «при клике на временную ТМЦ открывается модальное окно где указана информация, тоже что и в таблице + в каких операциях числится и чьим токеном была создана»

| Требование | Статус | Доказательство |
|---|---|---|
| Экран детализации | ⚠️ PARTIALLY MET | `temporary_items/detail.html` (115 строк) — открывается **отдельная страница**, а не модальное окно. Функционально информация присутствует, но UX отличается от спецификации. |
| Информация из таблицы | ✅ MET | ID, название, код, описание, статус, даты, site_id |
| Список операций, где числится ТМЦ | ❌ NOT MET | **Отсутствует в detail.html.** API endpoint `GET /temporary-items/{id}/operations` (`routes_temporary_items.py:94-119`) **существует**, но Django view `TemporaryItemDetailView` (`views.py:85-108`) **не вызывает его**. Контекст содержит только `{"item": item}` — без операций. |
| Чей токен (кто создал) | ⚠️ PARTIALLY MET | `detail.html:79`: `{{ item.user_id\|default:"—" }}` — показывает `user_id`, но **не username** и **не токен**. Спецификация говорит «чьим токеном была создана» — подразумевается идентификация пользователя. Показывается только UUID. |

### IV.2.3 — Удаление преобразованных из таблицы

> «если временная ТМЦ преобразованна в постоянную или смержена то её можно удалить из таблицы временных ТМЦ»

| Требование | Статус | Доказательство |
|---|---|---|
| Удаление преобразованных/смерженных | ❌ NOT MET | **Все статусы показываются в таблице**, включая `approved_as_item`, `merged_to_item`, `deleted`. Фильтр по статусу существует (`list.html:29-52`), но нет: а) автоскрытия решённых; б) кнопки «убрать из таблицы» для решённых; в) фильтра по умолчанию «только активные». Пользователь должен вручную выбрать фильтр `active`. |
| Кнопки действий скрыты для решённых | ✅ MET | `list.html:124-141`: кнопки «Преобразовать», «Объединить», «Удалить» показываются только если `item.status == "active"`. Это правильно, но не решает проблему видимости строк. |

---

## IV.3. Механизмы преобразования временных ТМЦ

### IV.3.1 — Слияние двух временных ТМЦ

> «Слияние с существующей временной ТМЦ - складываются в остатках»

| Требование | Статус | Доказательство |
|---|---|---|
| Merge temp → temp | ❌ NOT MET | **Текущий merge только temp → permanent.** `POST /temporary-items/{id}/merge` принимает `target_item_id: int` — ID **постоянного** catalog item. Нет endpoint'а для слияния двух временных ТМЦ. Нет логики объединения остатков двух `TemporaryItem`. |
| Балансы двух времянок | ❌ NOT MET | Спецификация: «складываются в остатках». Этот сценарий не реализован. |

### IV.3.2 — Преобразование в постоянную (approve-as-item)

> «полностью аналогичен созданию постоянной ТМЦ с назначением категорий, хештегов, единиц измерения»

| Требование | Статус | Доказательство |
|---|---|---|
| Категории при преобразовании | ⚠️ PARTIALLY MET | **В SyncServer** (`temporary_items_resolution_service.py:157-168`): новый `Item` копирует `category_id` из temp item. Категория, присвоенная при создании времянки, сохраняется. **В Django** (`temporary_items/views.py:148-155`): `ItemForm` с выбором категорий из полного списка — пользователь может изменить перед созданием. |
| Хештеги при преобразовании | ✅ MET | `hashtags` копируются из temp item в новый `Item` (строка 164) |
| Единицы измерения при преобразовании | ✅ MET | `unit_id` копируется из temp item в новый `Item` (строка 162) |
| **Расхождение в механизме** | ⚠️ PARTIALLY MET | **SyncServer** `approve_as_item()` создаёт item напрямую и переносит остатки через ADJUSTMENT-операции. **Django** `TemporaryItemApproveView` идёт другим путём: создаёт item через `CatalogService.create_item()` (admin catalog API), затем вызывает `merge_to_item()` (слияние времянки с только что созданным постоянным). Это рабочий, но другой путь — не используется прямой `approve-as-item` endpoint. |

---

## Реестр отклонений (по приоритету)

| # | Приоритет | Пункт | Отклонение | Рекомендация |
|---|---|---|---|---|
| 1 | 🟠 High | IV.0 | Нет системного юнита «штука» по умолчанию | Использовать `DEFAULT_UNIT_CODE`/`DEFAULT_UNIT_NAME` как fallback при создании времянки, если unit_id не указан (или сделать unit_id опциональным в `TemporaryItemInlineCreate`) |
| 2 | 🟠 High | IV.2.1 | Нет колонки «количество в остатках» в таблице | Добавить `balances` в `TemporaryItemResponse` (через `build_temporary_item_response` + запрос балансов), отобразить в `list.html` |
| 3 | 🟠 High | IV.3.1 | Нет слияния двух временных ТМЦ | Реализовать `POST /temporary-items/merge-temp` с `source_temp_id` и `target_temp_id`, балансы суммировать |
| 4 | 🟡 Medium | IV.2.2 | Модальное окно вместо отдельной страницы | Заменить переход на отдельную страницу модальным окном (или признать страницу приемлемой для SSR и скорректировать спецификацию) |
| 5 | 🟡 Medium | IV.2.2 | Список операций не показан в детализации | В `TemporaryItemDetailView.get()` добавить вызов `GET /temporary-items/{id}/operations` и передать в контекст |
| 6 | 🟡 Medium | IV.2.2 | Показан UUID вместо идентификации пользователя | В `detail.html` для `user_id` загружать username из API (или добавить `created_by_username` в `TemporaryItemResponse`) |
| 7 | 🟡 Medium | IV.2.3 | Решённые времянки остаются в таблице | По умолчанию фильтровать `?status=active` или добавить кнопку «Скрыть решённые» / автоскрытие `deleted` |
| 8 | 🟡 Medium | IV.2.1 | Нет сортировки и sticky headers | Общая проблема (gap #6, #7 сводного аудита) |
| 9 | 🔵 Low | IV.3.2 | Django approve идёт через create+merge, а не approve-as-item | Проверить, нет ли проблем с этим подходом. Возможно, унифицировать на прямой `approve-as-item`. |

---

## Карта файлов раздела IV

### SyncServer (backend)

| Файл | Роль | Строк |
|---|---|---|
| `app/models/temporary_item.py` | Модель TemporaryItem | 71 |
| `app/api/routes_temporary_items.py` | API endpoints | 164 |
| `app/services/temporary_items_resolution_service.py` | Логика approve/merge/delete | 355 |
| `app/schemas/temporary_item.py` | Pydantic схемы | 55 |
| `app/schemas/temporary_item_views.py` | Построение response | 33 |
| `app/core/catalog_defaults.py` | Системные константы | 8 |

### Warehouse_web (Django SSR)

| Файл | Роль | Строк |
|---|---|---|
| `apps/temporary_items/views.py` | Django views (list, detail, approve, merge, delete, bulk) | 404 |
| `apps/temporary_items/urls.py` | URL routing | ~23 |
| `apps/sync_client/temporary_items_api.py` | API client для SyncServer | ~100 |
| `templates/temporary_items/list.html` | Таблица с фильтрами | 189 |
| `templates/temporary_items/detail.html` | Детализация | 115 |
| `templates/temporary_items/approve.html` | Форма преобразования | ~50 |
| `templates/temporary_items/merge.html` | Форма слияния | ~40 |
| `templates/temporary_items/confirm_delete.html` | Подтверждение удаления | ~30 |
| `apps/client/views.py` (dashboard) | Дашборд с счётчиком | строки 65-72 |
| `templates/client/dashboard.html` | Шаблон дашборда | строки 28-49 |

---

## Итог

Раздел IV **имеет наиболее полную SSR-реализацию** среди всех разделов спецификации (особенно на фоне полного отсутствия SSR для раздела VI). Базовые сценарии (создание через операцию, просмотр списка, преобразование, слияние, удаление) работают.

**Главные пробелы:**

1. **Системный юнит «штука»** — константы есть, но не используются как fallback (IV.0)
2. **Остатки в таблице** — самая важная информация для кладовщика отсутствует (IV.2.1)
3. **Слияние двух времянок** — не реализовано (IV.3.1)
4. **Модальное окно** — заменено страницей, без списка операций (IV.2.2)
5. **Сортировка/sticky headers** — общая проблема всех SSR-таблиц (IV.2.1)

---

*Аудит выполнен архитектором. **Важное исправление к сводному аудиту:** пункт IV.1.5 (дашборд) на самом деле **реализован** — был ошибочно отмечен как NOT MET. Сводный аудит `AUDIT_FUNCTIONAL_SPEC_2026-05-19.md` требует корректировки.*
