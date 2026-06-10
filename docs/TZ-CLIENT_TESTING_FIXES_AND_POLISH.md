# TZ: Client Testing — Fixes And Polish

## Execution Strategy

- [x] 🟢 Parallel execution recommended
- **Reason:** все 7 пунктов — независимые правки в разных компонентах `Warehouse_frontend`. Пункт #2 может потребовать мелкой синхронизации контракта с SyncServer. После фиксации контрактов все работы можно вести параллельно.

### Parallel work units

| Unit | Пункт | Владелец | Зона | Зависимости |
|---|---|---|---|---|
| A | #1 Исчезновение записи после apply | `Warehouse_frontend` nomenclature | `nomenclature.service.ts`, `nomenclature-page` | — |
| B | #2 Категория опциональна | `Warehouse_frontend` + возможно `SyncServer` | `item-edit-form`, `batch` контракт | — |
| C | #3 Поисковые combobox | `Warehouse_frontend` nomenclature | `item-edit-form` | — |
| D | #4 Hashtags в форме ТМЦ | `Warehouse_frontend` nomenclature | `item-edit-form`, модели | — |
| E | #5 Модалки: backdrop static | `Warehouse_frontend` operations + nomenclature + issued-assets | Все модальные компоненты | — |
| F | #6 Автор → Комментарий | `Warehouse_frontend` operations | `operations-table`, `operations.models` | — |
| G | #7 Пагинация операций | `Warehouse_frontend` operations | `operations-table`, `operations-page` | — |

---

## Execution Checklist

- [ ] 0. Context verified
- [ ] 1. Architecture boundaries confirmed
- [ ] 2. Fix #1 — запись не исчезает после apply
- [ ] 3. Fix #2 — категория опциональна при создании ТМЦ
- [ ] 4. Fix #3 — поисковые combobox для категорий/единиц
- [ ] 5. Fix #4 — поле hashtags в форме ТМЦ
- [ ] 6. Fix #5 — модальные окна с backdrop static
- [ ] 7. Fix #6 — замена «Автор» на «Комментарий» в таблице операций
- [ ] 8. Fix #7 — восстановление пагинации на экране операций
- [ ] 9. Unit/component tests complete
- [ ] 10. Stand smoke tests complete
- [ ] 11. UI automation tests complete (Playwright)
- [ ] 12. Regression checks complete
- [ ] 13. Documentation updated
- [ ] 14. Final acceptance review complete

---

## Check Rules

- Executor agents may check implementation and test items only after running the required verification.
- QA verifier may check final acceptance only after reviewing evidence.
- Если стенд недоступен — `стенд недоступен`.

---

## Source

Клиент провёл тестирование dev-стенда 2026-06-10 и выявил следующие проблемы. Все пункты касаются `Warehouse_frontend`, кроме #2 (возможна синхронизация с SyncServer).

---

## Fix #1 🔴 — Исчезновение записи после «Применить все»

### Симптом

Создал позицию (категорию/ТМЦ/единицу) → нажал «Применить все» → запись исчезла из дерева. Жёсткий рефреш страницы (F5) — запись видна. Как будто batch применился на сервере, но дерево перерисовалось старыми данными.

### Вероятная причина

`NomenclatureService.applyBatch()` → после успеха вызывает `reloadBootstrap()`. Если reload-запрос приходит раньше фиксации batch на сервере, или BFF-кеш отдаёт старый ответ, дерево рендерится без новой записи.

### Требуемое поведение

1. После успешного `POST /bff/api/v1/catalog/admin/batch` сервер возвращает `records[]` с `local_id → entity_id`.
2. **Вариант A (optimistic):** до reload вставить новые записи в дерево локально, используя `records` из ответа. Затем reload для актуализации остальных данных.
3. **Вариант B (cache-bust):** reload с уникальным параметром (timestamp), гарантирующим свежий ответ.
4. После reload запись должна быть видна в дереве **без** ручного рефреша.

### In scope

- `Warehouse_frontend/src/app/core/services/nomenclature.service.ts` — `applyBatch()`
- `Warehouse_frontend/src/app/features/nomenclature/pages/nomenclature-page/`

### Acceptance

- Создать категорию → Применить → категория видна в дереве
- Создать ТМЦ → Применить → ТМЦ видна в дереве
- Создать единицу → Применить → единица видна в списке
- Цикл «создать 3 сущности разных типов → один apply → все видны»

---

## Fix #2 🟡 — Категория опциональна при создании ТМЦ

### Симптом

SyncServer позволяет `category_id = null` (подставляет «Без категории»). Angular-форма `item-edit-form` требует категорию (`Validators.required`). Это расхождение блокирует создание ТМЦ без категории через SPA.

### Контекст

- `Functional and WorkLogik.md` II.5: категория упомянута, но не указана как обязательная.
- Inline-TMC модалка (TZ-OPERATIONS_INLINE) уже делает категорию опциональной.
- SyncServer исторически принимает `null` → системная категория «Без категории».

### Требуемое поведение

1. В `item-edit-form` убрать `Validators.required` с поля категории.
2. Если категория не выбрана — в batch-запросе `category_id: null` (или `category_local_id: null`).
3. UI-подсказка: placeholder «Без категории» в поле выбора.

### In scope

- `Warehouse_frontend/src/app/features/nomenclature/components/item-edit-form/`
- Возможно: `SyncServer/app/services/catalog_admin_service.py` — убедиться, что `null` корректно обрабатывается в batch

### Acceptance

- Создать ТМЦ без категории → Применить → ТМЦ создана с `category_id = <Без категории>`
- Создать ТМЦ с категорией → поведение без изменений
- Редактировать существующую ТМЦ — сменить категорию на «не выбрана» → Применить

---

## Fix #3 🟡 — Поисковые combobox для категорий и единиц

### Симптом

При создании/редактировании ТМЦ поля «Категория» и «Единица измерения» — обычные `<select>`. При сотнях категорий и десятках единиц найти нужную невозможно.

### Требуемое поведение

Заменить `<select>` на searchable combobox (с текстовым вводом и выпадающим списком отфильтрованных результатов):

1. **Категория:** поиск через `GET /bff/api/v1/catalog/search/categories?q=...&limit=20`
   - Ввод ≥2 символов → debounce 300ms → запрос → выпадающий список
   - Показывает: название категории + путь (родительские категории)
2. **Единица измерения:** поиск через `GET /bff/api/v1/catalog/units?limit=1000` + клиентский фильтр по `name` / `symbol`
   - Ввод ≥1 символа → локальный фильтр → выпадающий список
   - Показывает: `название (символ)`, например `Штука (шт)`

### Референс

Компонент `item-cache-search` уже реализует такой паттерн для поиска ТМЦ. Можно адаптировать или переиспользовать.

### In scope

- `Warehouse_frontend/src/app/features/nomenclature/components/item-edit-form/`
- Новый/адаптированный компонент: `searchable-select` или `catalog-combobox`

### Acceptance

- Поле «Категория»: ввод текста → выпадающий список с результатами поиска
- Поле «Ед. изм.»: ввод текста → фильтрация локального списка
- Выбор из списка → значение установлено
- Очистка поля (крестик) → значение сброшено (для категории — `null`, для единицы — ошибка валидации, т.к. единица обязательна)

---

## Fix #4 🟡 — Поле «Ключевые слова» (hashtags) для ТМЦ

### Симптом

В SPA-форме создания/редактирования ТМЦ нет поля для хештегов. Поиск по хештегам уже работает в `item-cache-search`, но создавать/редактировать хештеги через интерфейс нельзя.

### Контекст

- `TZ-NOMENCLATURE_BATCH_CATALOG_CRUD.md`, batch-контракт: `"hashtags": ["кабель", "витая пара", "cat5e"]`
- `TZ-OPERATIONS_INLINE_TMC_CREATION_MODAL`, раздел 5.3: hashtags «optional, не required»
- SyncServer `Item.hashtags` — JSON-массив строк

### Требуемое поведение

1. Добавить поле «Ключевые слова» в `item-edit-form` (под описанием).
2. UI: chips/tags input — ввод слова → Enter → тег добавлен. Крестик на теге — удалить.
3. Валидация:
   - Каждый тег: 1-50 символов, буквы/цифры/дефис/пробел
   - Максимум 20 тегов
   - Дубликаты игнорируются
4. Отправка в batch: `"hashtags": ["тег1", "тег2"]`
5. При редактировании существующей ТМЦ — теги загружаются из `ItemResponse.hashtags`

### In scope

- `Warehouse_frontend/src/app/features/nomenclature/components/item-edit-form/`
- `Warehouse_frontend/src/app/core/models/catalog.models.ts` — поле `hashtags`

### Acceptance

- Создать ТМЦ с тегами `["кабель", "медь"]` → Применить → в ответе `hashtags: ["кабель", "медь"]`
- Редактировать ТМЦ → добавить тег → Применить → теги обновлены
- Нажать Enter с дубликатом → дубликат не добавлен
- Пустой ввод (только пробелы) → тег не создаётся

---

## Fix #5 🟡 — Модальные окна: backdrop static

### Симптом

Клик мышкой в тёмную область вне модального окна закрывает его. Пользователь случайно тыкает мимо и теряет несохранённые данные.

### Требуемое поведение

Для всех модальных окон, где есть ввод данных:
- `backdrop: 'static'` — клик по фону **не** закрывает модалку
- `keyboard: false` — Escape **не** закрывает (опционально, оставить на усмотрение)

### In scope (все модальные компоненты)

- `Warehouse_frontend/src/app/features/operations/components/operation-create-modal/`
- `Warehouse_frontend/src/app/features/nomenclature/components/merge-item-modal/`
- `Warehouse_frontend/src/app/features/nomenclature/components/merge-category-modal/`
- `Warehouse_frontend/src/app/features/issued-assets/components/` — все модалки создания/редактирования

### Acceptance

- Открыть модалку создания операции
- Кликнуть в тёмную область — модалка **не** закрылась
- Кнопка «Отмена» / крестик в заголовке — модалка закрылась

---

## Fix #6 🟢 — Заменить «Автор» на «Комментарий» в таблице операций

### Симптом

Широкая колонка «Автор» (flex) в таблице операций несёт мало пользы. Клиент хочет видеть комментарий, указанный при создании операции.

### Текущее состояние

`TZ-OPERATIONS_LIST_TABLE_DISPLAY_REWORK.md`, раздел 9: колонка Author (flex) показывает FIO.

### Требуемое поведение

1. Убрать колонку «Автор».
2. Добавить колонку «Комментарий» (comment из `OperationResponse`), ширина flex.
3. Если комментарий пуст — `—`.
4. Длинный комментарий: ellipsis + `title` tooltip с полным текстом.

### In scope

- `Warehouse_frontend/src/app/features/operations/components/operations-table/`
- `Warehouse_frontend/src/app/core/models/operations.models.ts` — `OperationListRowVm`
- `Warehouse_frontend/src/app/core/services/operations.service.ts` — `mapToRowVm()`

### Acceptance

- Таблица операций: нет колонки «Автор»
- Таблица операций: есть колонка «Комментарий»
- Операция с комментарием «Срочная поставка» → видно «Срочная поставка»
- Операция без комментария → видно `—`
- Длинный комментарий (более 100 символов) → ellipsis + tooltip

---

## Fix #7 🔴 — Восстановить пагинацию на экране операций

### Симптом

На странице `/operations/` отсутствуют контролы пагинации (выбор страницы, «10/20/50 записей»). Все операции грузятся одним списком без разбивки на страницы.

### Контекст

- `Functional and WorkLogik.md` VIII.3: «во всех таблицах пагинация на 10,20,50 записей»
- `TZ-OPERATIONS_LIST_TABLE_DISPLAY_REWORK.md`, раздел 10: «Preserve pagination behavior»

### Требуемое поведение

1. Добавить `mat-paginator` (или эквивалент) под таблицей операций.
2. Page size по умолчанию: 20.
3. Опции: [10, 20, 50].
4. Параметры `page` / `page_size` пробрасываются в BFF-запрос `GET /bff/api/v1/operations`.
5. При смене страницы — запрос с новым `page`.
6. При смене page size — сброс на первую страницу.

### In scope

- `Warehouse_frontend/src/app/features/operations/components/operations-table/`
- `Warehouse_frontend/src/app/features/operations/pages/operations-page/`
- `Warehouse_frontend/src/app/core/services/operations.service.ts`

### Acceptance

- Таблица операций: под таблицей виден пагинатор
- Пагинатор показывает «10 / 20 / 50»
- Переключение страницы → новый запрос → новые строки
- Изменение page size → сброс на стр. 1 → новое количество строк
- Фильтры + поиск + пагинация работают вместе без конфликтов

---

## Architecture Boundaries

Все изменения — в `Warehouse_frontend`. Ни один пункт не требует:
- Прямых браузерных запросов к SyncServer
- Новых Django-моделей
- Изменения SyncServer бизнес-логики (кроме возможной проверки #2)

---

## Test Strategy

| Уровень | Команда | Применимость |
|---|---|---|
| Static | `npm run build` | Всегда |
| Unit | `npx ng test --watch=false` | Если инфраструктура доступна |
| Stand smoke | `curl :8001/healthz` + браузер | Всегда |
| UI automation | Playwright через `:8001` | Все пункты с UI-изменениями |
| Regression | Существующие Playwright-сценарии | После всех правок |

---

## Real Test Stand

| Сервис | Адрес | Health Check |
|---|---|---|
| SyncServer API | `http://localhost:8000` | `GET /api/v1/health` |
| Django / BFF | `http://localhost:8001` | `GET /healthz/` |
| PostgreSQL | `localhost:5432` | `pg_isready` |
| Angular | `http://localhost:4200` | `GET /` |

---

## Acceptance Criteria (общие)

- [ ] Все 7 пунктов реализованы
- [ ] `npm run build` без ошибок
- [ ] Существующие Django-тесты (279) не сломаны
- [ ] Существующие SyncServer-тесты (373) не сломаны
- [ ] Playwright smoke по основным экранам: `/operations`, `/nomenclature`, `/issued-assets`
- [ ] Ни одного прямого браузерного запроса к SyncServer
