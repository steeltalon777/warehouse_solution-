# Architecture Review — Search Normalization & Hardening

**Date:** 2026-07-10
**Reviewer:** Architect
**TZ:** `docs/TZ-SEARCH_NORMALIZATION.md`

## Verdict

**Approved with conditions.**

План архитектурно корректен. Все технические риски верифицированы на dev-стенде. Условия — два warning'а, которые нужно отразить в реализации, плюс критическое уточнение по двух-term паттерну (добавлено после review).

**Post-review amendment (2026-07-10):** Добавлено разделение `build_normalized_like_term` / `build_raw_like_term` в TZ. Использование одного нормализованного term для всех колонок сломало бы поиск по SKU/кодам с дефисами, слешами и точками. См. TZ раздел 2.1 «Критическое правило: два term, не один».

---

## Verification Summary (dev-stand probes)

| Проверка | Результат | Детали |
|---|---|---|
| `\w` regex с кириллицей в PostgreSQL | ✅ Pass | `regexp_replace('Круг шлифовальный. для электр./точил', '[^\w\s]', ' ', 'g')` → сохраняет кириллицу, заменяет пунктуацию |
| SQL normalization pipeline vs Python | ✅ Match | SQL и Python дают идентичный результат: `круг шлифовальный для электр точил` |
| `ё→е` replacement в SQL | ✅ Pass | `Берёза и Ёлка` → `береза и елка` — совпадает с Python |
| `pg_trgm` extension availability | ✅ Available | v1.6 в postgres:15-alpine |
| Объём данных | ✅ Small | items: 1706, categories: 176, sites: 5, devices: 1 — GIN-индексы создаются мгновенно |
| NULL `normalized_name` в items | ✅ Zero | 0 строк с NULL — все заполнены миграцией 0002 |
| Корректность `normalized_name` | ⚠️ **73% некорректно** | **1253 из 1706** items имеют `normalized_name`, несовместимый с `_normalize_text()` — backfill обязателен |

---

## 🔴 Blockers

Нет.

---

## 🟡 Warnings

### 1. 73% items имеют некорректный `normalized_name` — backfill критичен

- **Checklist item:** Data & State — source of truth
- **Issue:** Миграция 0002 бэкфиллила `normalized_name = lower(trim(name))`, что не сворачивает двойные пробелы и не удаляет пунктуацию. На dev-стенде **1253 из 1706** items (73%) имеют `normalized_name`, несовместимый с Python `_normalize_text()`. Это означает, что переключение поиска на `normalized_name` **без backfill** сделает поиск хуже, а не лучше — для 73% строк normalized_name не совпадёт с ожидаемым.
- **Impact:** Поиск будет работать хуже, чем сейчас, если backfill не выполнен до переключения поиска.
- **Recommendation:** Миграция (Phase 0, раздел 2.4) с backfill **обязательна** и должна быть применена **до** переключения поиска в Phase 1. Порядок: миграция → потом repo fixes. В ТЗ это уже отражено (Phase 0 → Phase 1), но executor'ам нужно явно указать: "не переключать поиск на `normalized_name` пока миграция не применена".

### 2. Event listeners изменят поведение тестовых фикстур

- **Checklist item:** Failure Modes — partial failure
- **Issue:** Event listeners (Phase 0.2) будут автоматически вычислять `normalized_name` для всех ORM-created entities. Тесты, создававшие `Item(name="foo")` без `normalized_name`, получат `normalized_name="foo"` автоматически. Любой тест с `assert item.normalized_name is None` сломается.
- **Impact:** Тесты могут упасть с `AssertionError: expected None, got "foo"`.
- **Recommendation:** Executor'ы Work Units должны найти и обновить assertions, проверяющие `normalized_name is None`. В ТЗ (раздел 5.1) это отмечено, но executor'ам нужно явно проверить через `rg "normalized_name.*None\|None.*normalized_name" tests/`.

### 3. Description search — поведенческое изменение минимально

- **Checklist item:** Complexity — simplest solution
- **Issue:** Текущий поиск включает `Item.description.ilike(сырой_ввод)`. После изменений description будет искаться с `raw_term` (strip → escape → wrap). `raw_term` сохраняет пунктуацию и не меняет регистр, поэтому поведенческое изменение минимально: только экранирование LIKE-спецсимволов (`%`, `_`) и strip пробелов.
- **Impact:** Минимальное — description search остаётся тем же ILIKE без регистра, плюс защита от LIKE-инъекций.
- **Recommendation:** Не требует release notes. Не блокирует реализацию.

**Изменено после review:** Изначально TZ предлагал использовать нормализованный term для description. После уточнения (раздел 2.1 «два term») description использует `raw_term`, что снимает поведенческое изменение.

---

## 🔵 Notes

### 1. GIN-индексы без CONCURRENTLY

- **Checklist item:** Operability — deploy without downtime
- **Note:** Миграция использует `CREATE INDEX IF NOT EXISTS ... USING gin` без `CONCURRENTLY`. На 1706 строках это мгновенно. При росте до >100k строк может потребоваться `CONCURRENTLY` (требует `autocommit_block` в Alembic).
- **Action:** Не требуется на текущем масштабе. Отметить как future consideration.

### 2. Двойное вычисление normalized_name (сервис + event listener)

- **Checklist item:** Coupling — circular dependencies
- **Note:** После добавления event listeners сервисы всё ещё вручную устанавливают `normalized_name` (catalog_admin_service:155, 261, 316; machine_service:676, 685, 752, 767). Event listener перезапишет значение. Это безвредно (детерминированная функция), но создаёт redundant work.
- **Action:** Опциональная очистка — удалить ручные `normalized_name=...` вызовы из сервисов после verifying что event listener работает. Не блокер.

### 3. `build_normalized_like_term` / `build_raw_like_term` возвращает None для whitespace-only ввода

- **Checklist item:** Failure Modes — partial failure
- **Note:** Если пользователь введёт `"   "` (только пробелы), `build_normalized_like_term` и `build_raw_like_term` вернут None. Код в TZ (раздел 2.5) обрабатывает это: `if normalized_term is None and raw_term is None: pass` → поиск без фильтра.
- **Action:** Убедиться, что все 15 точек поиска обрабатывают `term is None` корректно — не падают и не добавляют WHERE-условие. Это уже отражено в паттерне TZ.

### 4. Operations repo — нет normalized-колонок и не будет

- **Checklist item:** Complexity — simplest solution
- **Note:** `operations_repo.py` ищет по `notes`, `item_name_snapshot`, `item_sku_snapshot`, `hashtags`. Эти поля не имеют и не должны иметь normalized-версий (снапшоты — точные копии, notes — свободный текст, hashtags — JSONB). Для Operations применяется только нормализация term + экранирование.
- **Action:** Это корректное архитектурное решение. Документировано в TZ (раздел 2.5 и раздел 9).

---

## Checklist Results

| Checklist Area | Items | Pass | Warning | Fail |
|---|---|---|---|---|
| Complexity | 4 | 4 | 0 | 0 |
| Coupling & Cohesion | 4 | 4 | 0 | 0 |
| Data & State | 4 | 3 | 1 | 0 |
| Failure Modes | 5 | 4 | 1 | 0 |
| Security | 5 | 5 | 0 | 0 |
| Scalability | 4 | 4 | 0 | 0 |
| Observability | 4 | 4 | 0 | 0 |
| Operability | 3 | 2 | 1 | 0 |
| **Total** | **33** | **30** | **3** | **0** |

---

## Gate Decision

**Proceed.** Все findings — warnings и notes, нет blockers.

Обязательные условия для executor'ов:
1. **Миграция с backfill должна быть применена ДО переключения поиска на `normalized_name`** (Phase 0 → Phase 1).
2. **Найти и обновить assertions** `normalized_name is None` в тестах (`rg "normalized_name.*None" tests/`).
3. ~~Документировать behavioral change в description search.~~ **Снято** — после перехода на `raw_term` для description поведенческое изменение минимально (только LIKE-экранирование + strip).
4. **Использовать два term** (нормализованный и raw) в каждой точке поиска — см. TZ раздел 2.1 «Критическое правило: два term, не один». `raw_term` для `sku`/`code`/`device_code`/`description`/`notes`/снапшотов, `normalized_term` для `normalized_name`/`normalized_key`.
