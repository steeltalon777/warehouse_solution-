# План реализации «Ключевых слов» (hashtags) для Items

## Часть 0 — SyncServer: предварительные доработки

| # | Файл | Что |
|---|------|-----|
| **0.1** | `SyncServer/app/services/catalog_admin_service.py` | Создать утилиту `_normalize_hashtags(tags)` (strip, lower, убрать `#`, дедупликация) и вызывать в `create_item()` и `update_item()` |
| **0.2** | `SyncServer/app/services/operations_service.py` | Вызвать `_normalize_hashtags` в `_create_temporary_item_for_line()` (draft payload) и в `_materialize_temporary_items()` |
| **0.3** | `SyncServer/app/repos/catalog_repo.py:52-98` | Добавить `cast(Item.hashtags, String).ilike(term)` в поиск `list_items_page()` + добавить `hashtags` в SELECT |
| **0.4** | `SyncServer/app/schemas/catalog.py:94-105` | Добавить `hashtags: list[str] \| None` в `CatalogBrowseItemDto` |
| **0.5** | `SyncServer/app/repos/temporary_items_repo.py:91-99` | Добавить `cast(TemporaryItem.hashtags, String).ilike(term)` в поиск `list_items()` |
| **0.6** | `SyncServer/app/models/temporary_item.py` | Добавить GIN-индекс `idx_temporary_items_hashtags` на `hashtags` |
| **0.7** | Миграция Alembic | Создать миграцию для GIN-индекса на `temporary_items.hashtags` |

## Часть 1 — Django: форма создания/редактирования Item

| # | Файл | Что |
|---|------|-----|
| **1.1** | `Warehouse_web/apps/catalog/forms.py` | Добавить в `ItemForm` поле `hashtags = CharField(required=False, widget=TextInput(attrs={'data-tag-input': 'true', 'placeholder': 'Введите слово и нажмите Enter...'}))` |
| **1.2** | `Warehouse_web/apps/catalog/forms.py` | Добавить `clean_hashtags()` — split по запятой, strip, lower, убрать `#`, дедупликация → вернуть `list[str]` |
| **1.3** | `Warehouse_web/templates/catalog/item_form.html` | Заменить `{{ form.as_p }}` на ручную вёрстку полей (по аналогии с другими шаблонами), чтобы поле hashtags рендерилось с `data-tag-input` |
| **1.4** | `Warehouse_web/static/js/ui_components.js` | Добавить `initTagInputs()` — vanilla JS tag-input: чипсы + поле ввода, Enter/запятая для добавления, крестик для удаления, скрытый input с comma-separated значениями |
| **1.5** | `Warehouse_web/static/css/app.css` | Стили для `.tag-input`, `.tag-input__chip`, `.tag-input__field` |

## Часть 2 — Django: поиск по ключевым словам (единое поле с `#`)

| # | Файл | Что |
|---|------|-----|
| **2.1** | `Warehouse_web/apps/catalog/views.py:187-192` | Дополнить `_matches_item_search()` — проверять hashtags: `any(search_term in (tag or '').casefold() for tag in (item.get('hashtags') or []))` |
| **2.2** | `Warehouse_web/apps/catalog_cache/models.py` | Добавить поле `hashtags = models.JSONField(null=True, blank=True)` в `CatalogCacheItem` |
| **2.3** | Миграция Django | `python manage.py makemigrations catalog_cache` |
| **2.4** | `Warehouse_web/apps/catalog_cache/services.py:84-140` | В `_upsert_items()` сохранять `hashtags` из `item.get('hashtags')` (после 0.4 browse начнёт возвращать) |
| **2.5** | `Warehouse_web/apps/catalog_cache/services.py:241-252` | В `_build_search_filter()` добавить `Q(hashtags__icontains=token)` |
| **2.6** | `Warehouse_web/apps/catalog_cache/services.py:212-225` | В `_serialize_item()` добавить `"hashtags": item.hashtags` |
| **2.7** | `Warehouse_web/templates/catalog/manage_item_list.html` | Добавить колонку «Ключевые слова» в таблицу |

## Часть 3 — Django: UI-тексты («ключевые слова» вместо hashtags)

| # | Файл | Что |
|---|------|-----|
| **3.1** | `Warehouse_web/templates/catalog/item_form.html` | Label поля: `"Ключевые слова"`, help_text: `"Например: Toyota, оригинал, тормозные колодки"` |
| **3.2** | `Warehouse_web/templates/balances/list.html` | Заменить placeholder `#тег` → `#ключевое_слово` |
| **3.3** | `Warehouse_web/templates/catalog/manage_item_list.html` | Колонка «Ключевые слова» |
| **3.4** | `Warehouse_web/templates/operations/form.html` | Если нужно — добавить подсказку о `#` в placeholder поиска |

## Порядок выполнения

```
Часть 0 (SyncServer) → Часть 1 (форма) → Часть 2 (поиск) → Часть 3 (тексты)
```

**Часть 0** критична первой: без неё browse не вернёт hashtags, и кеш не сможет их синхронизировать.

## Что НЕ требует изменений

- **Остатки** — сервер уже ищет по `#tag` (balances_repo.py:126-135), клиент просто передаёт `search` as-is
- **Временные ТМЦ (список)** — после 0.5 сервер сам найдёт по hashtags
- **Список операций** — поиск по ID/комментарию, hashtags нерелевантны
