# TZ: Merge Categories And Items — Backend

## Execution Strategy

- [ ] 🟡 Sequential execution recommended
- **Reason:** работа идёт в одном сервисе (`CatalogAdminService`) через общий `UnitOfWork`. Добавление двух эндпоинтов (merge items + merge categories) затрагивает одни и те же файлы: `routes_catalog_admin.py`, `catalog_admin_service.py`, `catalog_repo.py`, `schemas/catalog.py`. Параллельные правки в этих файлах создадут конфликты. Однако BFF-прокси (Django) можно делать параллельно с SyncServer после согласования контракта.

## Execution Checklist

- [x] 0. Context verified
- [x] 1. Architecture boundaries confirmed
- [x] 2. Implementation stage 1 complete — SyncServer merge items
- [x] 3. Implementation stage 2 complete — SyncServer merge categories
- [x] 4. Unit/component tests complete
- [x] 5. Integration tests with real dependencies complete
- [x] 6. Stand smoke tests complete
- [x] 7. BFF proxy endpoints complete
- [x] 8. Regression checks complete (363 tests, 0 regressions)
- [x] 9. Documentation updated
- [x] 10. Final acceptance review complete

## Check Rules

- Architect creates this checklist and acceptance criteria.
- Executor agents may check implementation and test items only after running the required verification.
- QA verifier may check final acceptance only after reviewing evidence.
- Failed or unavailable checks stay unchecked with a blocker note.

---

## 1. Goal

Реализовать API слияния (merge) категорий и ТМЦ в SyncServer и BFF-прокси в Django:

- `POST /catalog/admin/items/merge` — слияние ТМЦ (source → target)
- `POST /catalog/admin/categories/merge` — слияние категорий (source → target)
- BFF-прокси: `POST /bff/api/v1/catalog/admin/items/merge` и `POST /bff/api/v1/catalog/admin/categories/merge`

SSR-фронтенд уже имеет формы для merge, но API не реализован. Angular-фронтенд будет реализован в отдельном TZ.

---

## 2. Functional Requirements Alignment

`Functional and WorkLogik.md`, раздел III (справочники/каталог):
- Управление каталогом — chief_storekeeper или root
- Слияние ТМЦ: все операции, остатки и связи source-ТМЦ переносятся на target-ТМЦ, source деактивируется
- Слияние категорий: все ТМЦ из source-категории переносятся в target-категорию, source деактивируется

Архитектурные ограничения:
- SyncServer — единственный source of truth
- Все мутации каталога требуют `_require_catalog_admin` (root или chief_storekeeper)
- Операция merge должна быть атомарной (один UOW)

---

## 3. Existing Implementation Reference

### 3.1 Существующие merge-паттерны в SyncServer

Три референсных реализации:

| Сервис | Метод | Файл |
|--------|-------|------|
| `ReviewItemsService` | `merge_review_item()` | `app/services/review_items_service.py:102` |
| `TemporaryItemsResolutionService` | `merge_to_item()` | `app/services/temporary_items_resolution_service.py:202` |
| `IssueObjectsRepo` | `merge_issue_objects()` | `app/repos/issue_objects_repo.py:188` |

Общий паттерн (детально — см. исследование explore-агента):
1. Загрузить source + target, проверить существование и не-self-merge
2. Проверить права доступа
3. Перенести связи (балансы, строки операций) с source на target
4. Деактивировать source (`is_active = False`)
5. Заархивировать `inventory_subject` source
6. Всё в одной транзакции UOW

### 3.2 Существующий Django-клиент

`Warehouse_web/apps/sync_client/catalog_api.py` уже содержит методы:
- `merge_items(payload)` → `POST /catalog/admin/items/merge` (стр. 573)
- `merge_categories(payload)` → `POST /catalog/admin/categories/merge` (стр. 778)

Эти методы вызывают несуществующие сейчас эндпоинты (404). После реализации в SyncServer они заработают.

### 3.3 Существующий CatalogAdminService

`app/services/catalog_admin_service.py` имеет CRUD для units, categories, items, batch. Методы merge отсутствуют.

### 3.4 Таблицы, ссылающиеся на items и categories

| Таблица | FK | Действие при merge |
|---------|-----|--------------------|
| `balances` | `item_id` | Перенести балансы с source на target через ADJUSTMENT-операции |
| `operation_lines` | `item_id` | Обновить `item_id` на target |
| `inventory_subjects` | `item_id` | Заархивировать source-subject |
| `temporary_items` | `item_id`, `resolved_item_id` | Не трогать (временные ТМЦ не участвуют в merge каталога) |
| `items` | `category_id` | При merge категорий — обновить `category_id` на target |

### 3.5 Проверка «замороженных» ТМЦ

`CatalogAdminService._assert_item_not_frozen()` (стр. 218) проверяет, что ТМЦ не находится в репозитории непринятого (lost assets). Эта проверка должна выполняться и для merge.

---

## 4. Реализация в SyncServer

### Stage 1 — Merge Items

#### 4.1.1 Схема запроса

Добавить в `SyncServer/app/schemas/catalog.py`:

```python
class ItemMergeRequest(BaseModel):
    source_item_id: int
    target_item_id: int
    comment: str | None = None

class CategoryMergeRequest(BaseModel):
    source_category_id: int
    target_category_id: int
    comment: str | None = None
```

#### 4.1.2 Метод в CatalogAdminService

Добавить в `app/services/catalog_admin_service.py`:

```python
async def merge_items(
    self,
    uow: UnitOfWork,
    *,
    source_item_id: int,
    target_item_id: int,
    comment: str | None = None,
    resolved_by_user_id: UUID,
) -> Item:
```

Логика:
1. `source = await uow.catalog.get_item_by_id(source_item_id)` — 404 если не найден
2. `target = await uow.catalog.get_item_by_id(target_item_id)` — 404 если не найден
3. `if source_item_id == target_item_id` → 422 «нельзя слить ТМЦ саму в себя»
4. Проверить `source.deleted_at is None` и `target.deleted_at is None`
5. Проверить `target.is_active is True`
6. `self._assert_item_not_frozen(source)` — замороженные ТМЦ нельзя сливать
7. `self._assert_item_not_frozen(target)`
8. Перенос балансов (как в `ReviewItemsService.merge_review_item`):
   - `source_subject = await uow.inventory_subjects.get_by_item_id(source_item_id)`
   - `target_subject = await uow.inventory_subjects.get_or_create_for_item(item_id=target_item_id)`
   - `source_balances = await uow.balances.get_all_by_inventory_subject(int(source_subject.id))`
   - Для каждого balance: создать пару ADJUSTMENT-операций (write_off с source + receipt на target)
9. Обновление строк операций:
   - Все `operation_lines` с `item_id = source_item_id` → `item_id = target_item_id`
   - Только для неподтверждённых (draft) операций? **Нет** — обновляем все, включая подтверждённые (merge — это административная операция)
10. Заархивировать `source_subject` через `uow.inventory_subjects.archive()`
11. Деактивировать source: `source.is_active = False`
12. Установить `source.merged_into_id = target_item_id` (требует миграции — см. ниже)
13. Записать audit: `source.review_resolved_by_user_id = resolved_by_user_id` (или отдельное поле — см. миграцию)
14. `await uow.catalog.update_item(source)`
15. Вернуть `target` (или `source` с обновлёнными полями)

#### 4.1.3 Миграция Alembic

Добавить поля в таблицу `items`:

```python
# Новые поля для merge
merged_into_id = Column(Integer, ForeignKey("items.id"), nullable=True)
merged_at = Column(DateTime(timezone=True), nullable=True)
merged_by_user_id = Column(UUID, nullable=True)
merge_comment = Column(String, nullable=True)
```

Аналогично для `categories` (см. Stage 2).

#### 4.1.4 Эндпоинт в routes_catalog_admin.py

```python
@router.post("/items/merge", response_model=ItemResponse)
async def merge_items(
    payload: ItemMergeRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> ItemResponse:
    await _require_catalog_admin(identity=identity)
    service = CatalogAdminService()
    async with uow:
        await service.merge_items(
            uow,
            source_item_id=payload.source_item_id,
            target_item_id=payload.target_item_id,
            comment=payload.comment,
            resolved_by_user_id=identity.user_id,
        )
        # После merge возвращаем target (или source с merged_into_id?)
        target = await uow.catalog.get_item_by_id(payload.target_item_id)
    logger.info("merge_items", request_id=get_request_id(request),
                source_item_id=payload.source_item_id,
                target_item_id=payload.target_item_id,
                user_id=identity.user_id)
    return ItemResponse.model_validate(target)
```

### Stage 2 — Merge Categories

#### 4.2.1 Метод в CatalogAdminService

```python
async def merge_categories(
    self,
    uow: UnitOfWork,
    *,
    source_category_id: int,
    target_category_id: int,
    comment: str | None = None,
    resolved_by_user_id: UUID,
) -> Category:
```

Логика:
1. `source = await uow.catalog.get_category_by_id(source_category_id)` — 404
2. `target = await uow.catalog.get_category_by_id(target_category_id)` — 404
3. `if source_category_id == target_category_id` → 422
4. Проверить `source.deleted_at is None`, `target.deleted_at is None`, `target.is_active`
5. Проверить, что target не является потомком source (циклическая зависимость)
6. Все ТМЦ в source-категории: `UPDATE items SET category_id = target_category_id WHERE category_id = source_category_id`
7. Подкатегории source: перенести в target (обновить `parent_id`)
8. Деактивировать source: `source.is_active = False`
9. `source.merged_into_id = target_category_id` (требует миграции)
10. Audit поля
11. `await uow.catalog.update_category(source)`

#### 4.2.2 Миграция Alembic для categories

```python
# Новые поля в таблице categories
merged_into_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
merged_at = Column(DateTime(timezone=True), nullable=True)
merged_by_user_id = Column(UUID, nullable=True)
merge_comment = Column(String, nullable=True)
```

#### 4.2.3 Эндпоинт в routes_catalog_admin.py

```python
@router.post("/categories/merge", response_model=CategoryResponse)
async def merge_categories(
    payload: CategoryMergeRequest,
    request: Request,
    uow: UnitOfWork = Depends(get_uow),
    identity: Identity = Depends(require_user_identity),
) -> CategoryResponse:
    ...
```

---

## 5. Реализация BFF-прокси в Django

### 5.1 Новые BFF-эндпоинты

Добавить в `Warehouse_web/apps/bff_api/catalog_admin_views.py` (или создать новый модуль):

```python
class ItemMergeView(LoginRequiredMixin, View):
    def post(self, request):
        if not _require_catalog_admin(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            payload = json.loads(request.body)
            api = CatalogAPI(request.user.sync_client)
            data = api.merge_items(payload)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)

class CategoryMergeView(LoginRequiredMixin, View):
    def post(self, request):
        if not _require_catalog_admin(request.user):
            return _error("Access denied", "forbidden", 403)
        try:
            payload = json.loads(request.body)
            api = CatalogAPI(request.user.sync_client)
            data = api.merge_categories(payload)
            return _ok(data)
        except SyncServerAPIError as exc:
            return _handle_sync_error(exc)
```

### 5.2 URL patterns

Добавить в `Warehouse_web/apps/bff_api/urls.py`:

```python
path("catalog/admin/items/merge", catalog_admin_views.ItemMergeView.as_view(), name="bff_item_merge"),
path("catalog/admin/categories/merge", catalog_admin_views.CategoryMergeView.as_view(), name="bff_category_merge"),
```

### 5.3 Auth/permission

BFF должен проверять `can_manage_catalog(request.user)` или эквивалент (chief_storekeeper / root).

---

## 6. Test Strategy

### Static checks
- `python -m pytest` в SyncServer
- `python manage.py test` в Django
- `python -m alembic upgrade head` — миграция применяется без ошибок

### Unit tests (SyncServer)

- `test_merge_items_success` — успешный merge: балансы перенесены, строки операций обновлены, source деактивирован
- `test_merge_items_self_merge_422` — нельзя слить ТМЦ саму в себя
- `test_merge_items_source_not_found_404`
- `test_merge_items_target_not_found_404`
- `test_merge_items_frozen_409` — замороженная ТМЦ (lost asset) не сливается
- `test_merge_items_balance_transfer` — балансы корректно переносятся через ADJUSTMENT
- `test_merge_items_operation_lines_updated` — строки операций обновлены
- `test_merge_categories_success` — все ТМЦ перенесены, source деактивирован
- `test_merge_categories_self_merge_422`
- `test_merge_categories_cycle_check` — target не потомок source
- `test_merge_categories_subcategories_transferred`

### Integration tests (SyncServer + test DB)

- Полный сценарий: создать две ТМЦ с балансами и операциями → merge → проверить балансы/операции
- Полный сценарий для категорий: создать категорию с ТМЦ и подкатегориями → merge → проверить

### BFF tests (Django)

- `test_item_merge_bff_200` — авторизованный chief/root получает 200
- `test_item_merge_bff_403` — обычный пользователь получает 403
- `test_item_merge_bff_propagates_sync_error` — ошибка SyncServer пробрасывается

### Stand smoke tests

- `curl -X POST http://localhost:8001/bff/api/v1/catalog/admin/items/merge -d '{"source_item_id":1,"target_item_id":2}'` → 200

### Regression checks

- Существующие catalog CRUD (create/update/delete/list) не затронуты
- Batch-операции не затронуты
- SSR merge-формы продолжают работать (теперь без ошибок)

---

## 7. Real Test Stand

Docker-стенд как обычно: SyncServer `:8000`, Django `:8001`, PostgreSQL `:5432`.

Seed data:
- Минимум 2 активные ТМЦ (items) с балансами и строками операций
- Минимум 2 категории с ТМЦ
- Одна замороженная ТМЦ (в lost assets) для негативного теста
- Пользователь chief_storekeeper для auth-тестов

---

## 8. Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Балансы не переносятся корректно | Остатки «теряются» при merge | Тщательное тестирование ADJUSTMENT-операций |
| Операционные строки не обновляются | История операций указывает на несуществующую ТМЦ | Проверить все operation_lines с item_id = source |
| Merge замороженной ТМЦ ломает lost assets | Инвариант репозитория непринятого нарушен | `_assert_item_not_frozen()` на source и target |
| Циклическая зависимость категорий | Бесконечная рекурсия в дереве | Проверка, что target не потомок source |
| Миграция конфликтует с существующими данными | Alembic upgrade fail | Проверить миграцию на копии БД, nullable поля |

---

## 9. Acceptance Criteria

- `POST /catalog/admin/items/merge` — 200 при валидном merge
- Балансы source перенесены на target
- Строки операций source обновлены на target
- Source деактивирован (`is_active=False`, `merged_into_id=target`)
- Self-merge → 422
- Frozen item merge → 409
- `POST /catalog/admin/categories/merge` — 200
- ТМЦ source-категории перенесены в target
- Подкатегории перенесены
- Source-категория деактивирована
- BFF-прокси пробрасывает запросы и ошибки корректно
- Права доступа проверяются (403 для не-admin)

---

## 10. Out Of Scope

- UI (Angular/SSR) — отдельный TZ
- Merge units (единиц измерения) — не требуется
- Merge temporary items — уже реализован
- Отмена/undo merge — не в этом TZ
- Массовый merge (batch) — не в этом TZ

---

## 11. Files In Scope

### SyncServer
- `app/api/routes_catalog_admin.py` — новые эндпоинты
- `app/services/catalog_admin_service.py` — методы `merge_items()`, `merge_categories()`
- `app/schemas/catalog.py` — `ItemMergeRequest`, `CategoryMergeRequest`
- `app/repos/catalog_repo.py` — возможно, вспомогательные методы
- `alembic/versions/` — новая миграция
- `tests/` — тесты merge

### Django / Warehouse_web
- `apps/bff_api/catalog_admin_views.py` — новые BFF-вью
- `apps/bff_api/urls.py` — новые URL patterns
- `apps/sync_client/catalog_api.py` — методы уже существуют, без изменений

