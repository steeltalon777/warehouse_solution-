# TZ-PHANTOM_ITEMS_CACHE_PRUNING_AND_REFRESH_FIX

**Статус:** готово к реализации
**Дата:** 2026-08-10
**Автор:** architect (по результатам обследования пользователя)
**Приоритет:** 🔴 высокий — жёсткий user-visible отказ сохранения операции («item XXXX not found») + сломанная кнопка «Обновить всё»
**Связанные документы:**
* `docs/TZ-OPERATION_MODAL_BALANCES_MANUAL_REFRESH.md` (выполнен; его решение разделило автосинк на две кнопки — см. §1.3)
* `Functional and WorkLogik.md` п. 71 — «кладовщик создаёт операцию -> добавляет построчно ТМЦ (на фронтенде должен работать кеш и поиск) -> подтверждение»
* `docs/AGENT_TZ_WORKFLOW.md` — шаблон чек-листа и test ladder
* Корневой `AGENTS.md` — architecture rules, verification matrix, Stand Availability Protocol

---

## 0. Execution Checklist

### Implementation — WP-A: Django, targeted авто-прунинг кэша (приоритет 1)
- [x] A1. `Warehouse_web/apps/bff_api/catalog_views.py` — в `CatalogItemsResolveView.post` после успешного `resolve_items()` добавить best-effort пруннинг `CatalogCacheItem` по статусам `missing/deleted/inactive/merged` через существующий `CatalogCacheSyncService.deactivate_item()`
- [x] A2. Прунинг не должен ломать ответ resolve: любой exception пруннинга логируется и проглатывается; ответ клиенту всегда содержит результаты resolve
- [x] A3. Логирование: INFO-строка с числом деактивированных записей (только когда > 0)

### Implementation — WP-B: Angular, авто-валидация и починка «Обновить всё» (приоритет 1)
- [x] B1. `operation-create-modal.component.ts` — выделить ядро `onRefreshCheckItems()` в переиспользуемый метод `validateAndApplyLineStatuses()`; `onRefreshCheckItems()` продолжает работать через него (поведение кнопки «Обновить и проверить» не меняется)
- [x] B2. `onSave()` и `onSubmit()` — перед emit вызывать `validateAndApplyLineStatuses()`; если после apply есть unusable-строки (`hasUnusableLines()`) или резолвер недоступен — НЕ эмитить, показать тост через существующий `toasts` signal
- [x] B3. `onRefreshAllBalances()` — убрать молчаливые no-op return'ы: валидация ТМЦ выполняется ВСЕГДА; обновление остатков только когда применимо (`shouldUseWarehouseBalances()` и выбран склад), иначе инфо-тост вместо тишины
- [x] B4. `operations.service.ts` `loadBalances()` — заменить молчаливое `catch → balances.set([])` на установку публичного signal `balanceLoadError` (баланс при этом всё равно `[]` — консервативно); на старте успешной загрузки сигнал сбрасывается
- [x] B5. Модалка: effect смены склада (~строки 1190-1191) — добавить обработку ошибки `loadBalances` (без падения, через `balanceLoadError`); `onRefreshAllBalances` показывает тост при ошибке остатков
- [x] B6. Быстрый путь: если в черновике нет не-temporary не-inline строк — валидация не делает сетевых вызовов

### Implementation — WP-C: периодическая полная сверка кэша (приоритет 2)
- [x] C1. Корневой `Makefile` — аддитивный target `sync-catalog-cache` (`docker compose exec warehouse_web python manage.py sync_catalog_cache`)
- [x] C2. `Warehouse_web/DEPLOYMENT.md` — секция с рекомендуемым cron/systemd-timer (интервал: ежечасно) и обоснованием

### Tests
- [x] T1. Static: `npm run build` (Angular) зелёный
- [x] T2. Static: `python manage.py check` (Django) без ошибок; `python manage.py makemigrations --check --dry-run` — новых миграций НЕТ (модели не меняются)
- [x] T3. Unit/component (vitest): `onSave`/`onSubmit` с фантомной строкой НЕ эмитят и показывают тост; с чистой строкой — эмитят; резолвер недоступен → save заблокирован с сообщением
- [x] T4. Unit/component (vitest): «Обновить всё» на объектном flow (ISSUE_RETURN/WRITE_OFF с объектом) выполняет валидацию ТМЦ и НЕ вызывает `loadBalances`; без склада — валидация + инфо-тост
- [x] T5. Unit/component (vitest): ошибка `loadBalances` → `balanceLoadError` установлен, баланс `[]`, тост при ручном refresh; существующие 15 тестов manual-refresh остаются зелёными (включая «onSave/onSubmit НЕ вызывают loadBalances» — валидация это resolve, не баланс)
- [x] T6. Django tests: resolve-view пруннинг — статусы missing/deleted/inactive/merged деактивируют кэш-запись; active не трогает; неизвестный id безопасен; exception пруннинга не ломает 200-ответ; 400-валидации view не сломаны
- [x] T7. Django integration (test DB): деактивированный `CatalogCacheItem` исключается из fast-поиска `CatalogLookupService.search_items`
- [x] T8. Stand smoke: phantom-сценарий через API (seed ТМЦ в SyncServer → warm кэша → удаление ТМЦ в SyncServer мимо Django → resolve → кэш деактивирован → fast-поиск не возвращает фантом)
- [x] T9. UI automation: новый `Warehouse_frontend/e2e/operations/operations-phantom-item-block.spec.ts` — фантомная строка блокирует Save с причиной, 404-тост НЕ появляется; после замены строки на валидную сохранение проходит
- [x] T10. Regression e2e: `operations-balances-manual.spec.ts`, `operations-catalog-refresh.spec.ts`, `operations-save-reliability.spec.ts`, `operations-create-modal.spec.ts`, `temporary-items.spec.ts`, `issued-assets-layout.spec.ts` (второй потребитель модалки)
- [x] T11. Regression Django: тест-сьюты `apps/catalog_cache` и `apps/bff_api` зелёные
- [x] T12. User scenario: «кладовщик добавляет в черновик ТМЦ, удалённый в SyncServer вне Django-админки → жмёт Сохранить → строка подсвечена с причиной, сохранение не происходит, понятное сообщение; после исправления строки операция сохраняется»
- [x] T13. Stand smoke WP-C: `make sync-catalog-cache` на стенде, stats-запись `complete=true`

### Final
- [x] F1. Documentation: чек-лист этого TZ закрыт с Evidence; при изменении entry points — обновить `AI_CONTEXT.md`/`AI_ENTRY_POINTS.md` (не ожидается)
- [x] F2. Final acceptance (QA verifier)

## Check Rules

* Архитектор (этот документ) создаёт чек-лист и критерии приёмки.
* Executor проверяет пункт только после реализации И личного прогона соответствующей верификации.
* Если стенд недоступен — пункт остаётся пустым с пометкой «стенд недоступен» в Evidence; перед любым real-stand прогоном — Stand Availability Protocol из корневого `AGENTS.md`.
* Commit только в `dev`, только файлы своей задачи, по правилам корневого `AGENTS.md`.
* Номера строк в §3-§4 указаны на момент обследования (2026-08-10) и могут съехать — ориентироваться по именам символов.

---

## 1. Контекст и проблема

### 1.1. Проблема 2 (первичная): фантомные ТМЦ → «item XXXX not found»

ТМЦ, удалённые/деактивированные в SyncServer **мимо Django-админки**, навсегда остаются `is_active=True` в Django-кэше `CatalogCacheItem`. Цепочка отказа (все факты верифицированы чтением кода):

| Узел | Поведение | Где |
|---|---|---|
| Прунинг кэша | Только ручной (`CatalogCacheSyncView.post`, management-команда) или write-through из Django-админки. Автоматики нет | `Warehouse_web/apps/catalog_cache/services.py`, `apps/catalog/views.py:400-407` |
| Поиск | Fast-режим `CatalogCachedItemSearchView`: при `len(cached_items) >= limit` возвращает ТОЛЬКО кэш, SyncServer не опрашивается | `Warehouse_web/apps/bff_api/catalog_views.py:613-615` |
| Добавление в черновик | Нет валидации существования ТМЦ | `operation-create-modal.component.ts:1450-1477` |
| Сохранение | Единственная защита — 404 `item with id {id} not found` в SyncServer при create_operation | `SyncServer/app/services/operations_service.py:1237-1242` |

Инфраструктура валидации **уже существует** полным контуром (TZ-V3.2), но запускается только вручную кнопкой «Обновить и проверить»:
* SyncServer: `POST /api/v1/catalog/read/items/resolve` со статусами `active/inactive/deleted/merged/missing`;
* BFF: `POST /bff/api/v1/catalog/read/items/resolve` (`CatalogItemsResolveView`, лимит 500 id) — **write-through в кэш НЕ делает**;
* Frontend: `OperationsService.validateLinesBeforePersist()` → `applyResolvedStatuses()` → `hasUnusableLines()` дизейблит Save/Submit (строки 332, 336 модалки).

### 1.2. Проблема 1: «Обновить всё» — поведенческий баг

Кнопка реализована TZ-OPERATION_MODAL_BALANCES_MANUAL_REFRESH (коммит 3e8ab4a), 15/15 юнит-тестов зелёные, но:

| Ситуация | Поведение | Где |
|---|---|---|
| ISSUE_RETURN/WRITE_OFF с объектом | Молчаливый no-op (`shouldUseWarehouseBalances()` = false) | `operation-create-modal.component.ts:1308` |
| Склад не выбран | Молчаливый no-op | `:1309-1310` |
| Ошибка BFF/SyncServer при загрузке остатков | Остатки молча обнуляются (`catch → balances.set([])`) | `operations.service.ts:738-740` |
| Фантомные ТМЦ | Кнопка их НЕ детектит (это делает другая кнопка) | — |

### 1.3. Связь: TZ-OPERATION_MODAL_BALANCES_MANUAL_REFRESH разделил автосинк

До того TZ автосинк перед save/submit проверял и остатки, и существование. После: «Обновить всё» (только остатки) + «Обновить и проверить» (только ТМЦ). Ни одна кнопка не делает всё сразу, автоматически не работает ничего → фантомы беспрепятственно доходят до SyncServer и падают в 404.

### 1.4. Соответствие функциональным требованиям

Фантомы прямо нарушают `Functional and WorkLogik.md` п. 71 (кеш и поиск должны работать при построчном добавлении ТМЦ). Данное ТЗ восстанавливает соответствие; отклонений от функциональных требований не вводит.

---

## 2. Решение: многослойная защита

```
Слой  Что делает                                        Где
L1    Авто-валидация существования строк перед          Angular модалка (WP-B1/B2)
      save/submit — переиспользует существующий
      resolver-контур; блокирует save при unusable
L2    Targeted авто-прунинг кэша по авторитетным        BFF resolve-view (WP-A)
      статусам resolve — валидационный трафик
      сам лечит кэш
L3    «Обновить всё» = остатки (где применимы) +        Angular модалка (WP-B3)
      валидация ТМЦ всегда; ошибки видимы (WP-B4/B5)
L4    Периодическая полная сверка кэша (cron)           WP-C, существующая команда
L5    SyncServer 404 остаётся последней защитой         БЕЗ ИЗМЕНЕНИЙ
```

Ни одного нового эндпоинта. SyncServer не изменяется вообще. Django-кэш — техническое состояние веба (разрешено architecture rules).

---

## 3. WP-A: Django — targeted пруннинг кэша в resolve-view

**Файл:** `Warehouse_web/apps/bff_api/catalog_views.py`, `CatalogItemsResolveView.post` (строки ~812-844).

**Поведение после успешного `resolve_items(client, item_ids)`:**

1. Для каждого результата со статусом `missing`, `deleted`, `inactive` или `merged` вызвать `CatalogCacheSyncService().deactivate_item(item_id)` (существующий метод, `services.py:75-83`: `UPDATE ... is_active=False, synced_at=now()` по `sync_id`). Имя поля статуса — по фактическому контракту ответа `CatalogReadService.resolve_items` (проверить при реализации).
2. `active` — не трогать (upsert активных записей сознательно вне scope: полной payload-гарантии в ответе resolve нет).
3. Прунинг best-effort: обёрнут в try/except, любой exception логируется (`logger.exception`) и проглатывается — ответ resolve всегда уходит клиенту.
4. При >0 деактиваций — INFO-лог с числом.
5. Идемпотентно и конкурентно-безопасно: повторный UPDATE тех же id безвреден.

**Эффект:** каждый автоматический validate перед save (WP-B2) деактивует фантом в кэше; последующий fast-поиск (`CatalogLookupService.search_items` фильтрует `is_active=True`, `services.py:353`) фантом не возвращает.

**Тесты (T6, T7):** Django TestCase с моком SyncServer-клиента; кейсы по каждому статусу; неизвестный id; exception пруннинга → 200; 400-валидации view; integration на test DB: деактивированная запись не находится fast-поиском.

---

## 4. WP-B: Angular — авто-валидация и починка «Обновить всё»

**Файлы:** `Warehouse_frontend/src/app/features/operations/components/operation-create-modal/operation-create-modal.component.ts`, `Warehouse_frontend/src/app/core/services/operations.service.ts` (+ spec-файлы).

### 4.1. B1/B2 — авто-валидация перед save/submit

* Ядро `onRefreshCheckItems()` (строки ~1578-1598: `validateLinesBeforePersist` → `applyResolvedStatuses` → `localDraft.set` → обработка `refreshError`) вынести в метод `validateAndApplyLineStatuses(): Promise<void>`; кнопка «Обновить и проверить» продолжает работать через него — её поведение не меняется.
* `onSave()` (строки ~1600-1608): после проверки `saveDisabledReason()`, ПЕРЕД `save.emit()` — `await validateAndApplyLineStatuses()`. Если после apply `hasUnusableLines()` — НЕ эмитить, показать тост через существующий `toasts` signal / `setToasts()` (рендер `operation-submit-toast` уже есть, строки 349-352): сообщение вида «Сохранение отменено: N строк содержат удалённые/недоступные ТМЦ» + указание на подсвеченные строки.
* `onSubmit()` (строки ~1631-1655): аналогично, ПЕРЕД emit; при блокировке дополнительно `diag.track('validation_failed', ...)` по аналогии с существующим паттерном.
* Резолвер недоступен (structured error из `validateLinesBeforePersist`) — save/submit также НЕ эмитить, тост с сообщением из `refreshError`. Обоснование: если резолвер недоступен, SyncServer с той же вероятностью недоступен, и create всё равно упадёт — честная блокировка с понятным сообщением лучше 502.
* B6: `validateLinesBeforePersist` уже пропускает temporary/inline строки; если persisted-строк нет — сетевого вызова не происходит (проверить юнит-тестом).
* Существующий тест «onSave/onSubmit НЕ вызывают loadBalances» (TZ-OPERATION_MODAL_BALANCES_MANUAL_REFRESH, пункт 10) остаётся валиден: валидация — это resolve, а не загрузка остатков.
* Валидация размещается именно ВНУТРИ модалки (до emit), а не в родительских хендлерах: у `OperationCreateModalComponent` два потребителя — `operations-page.component.ts` (create/update операции) и `object-panel.component.ts` (issued-assets, собственные `onModalSave`/`onModalSubmit`). Внутренняя валидация закрывает оба persist-пути без их модификации.

### 4.2. B3 — «Обновить всё» без молчаливых no-op

`onRefreshAllBalances()` (строки ~1307-1321) пересобрать:

1. Валидация ТМЦ (`validateAndApplyLineStatuses()`) выполняется **всегда** — кнопка становится суперсетом «Обновить и проверить», no-op-ситуаций не остаётся.
2. Обновление остатков (`loadBalances` + `refreshSourceQuantities`, существующий race-guard `balanceRefreshSeq`/`isBalanceRefreshing` сохраняется) — только когда `shouldUseWarehouseBalances()` И `siteId` выбран.
3. Если остатки неприменимы (объектный flow) или склад не выбран — вместо молчаливого return инфо-тост: «Остатки недоступны для объектных операций» / «Выберите склад, чтобы обновить остатки» (валидация ТМЦ при этом уже выполнена).

Кнопку «Обновить и проверить» НЕ удалять (она в зоне ответственности `item-cache-search.component.ts`; удаление — отдельное UX-решение). Задокументировать в отчёте, что «Обновить всё» теперь суперсет.

### 4.3. B4/B5 — видимость ошибок загрузки остатков

* `operations.service.ts` `loadBalances()` (строки ~729-741): добавить публичный `balanceLoadError = signal<string | null>(null)`. На старте загрузки — `balanceLoadError.set(null)`. В catch: `balances.set([])` (консервативно — отсутствие данных трактуется как нулевой остаток, quantity-валидация блокирует выдачу) **и** `balanceLoadError.set(сообщение)`. Метод не rethrow'ит.
* Вызывающих точек ровно две — обе обновить:
  * модалка `onRefreshAllBalances`: после `loadBalances` проверить `balanceLoadError()` → тост «Не удалось обновить остатки: ...»;
  * effect смены склада (~1190-1191, сейчас `.then(...)` без catch): ошибка не должна ронять effect; достаточно чтения/установки сигнала, опционально тихий лог.
* Отличать «остатков нет» от «ошибка загрузки» в UI: обязательный минимум — тост при ручном refresh; inline-индикатор у таблицы — опциональное улучшение, не блокирует приёмку.

**Тесты (T3-T5):** vitest unit/component по каждому пункту; существующие 15 тестов manual-refresh должны остаться зелёными без модификаций (если тест требует правки из-за нового сигнала — обосновать в отчёте).

---

## 5. WP-C: периодическая полная сверка кэша

Targeted-прунинг (WP-A) лечит кэш по факту обращения. Полная сверка закрывает остаточный случай «фантом ищется по названию, но ещё ни разу не попал в валидацию».

* **C1:** корневой `Makefile` — новый аддитивный target:
  `sync-catalog-cache: ## Полная сверка кэша каталога с SyncServer` → `docker compose exec warehouse_web python manage.py sync_catalog_cache`
* **C2:** `Warehouse_web/DEPLOYMENT.md` — секция «Периодическая сверка кэша каталога»: рекомендуемый cron/systemd-timer, интервал ежечасно, команда, поведение (прунинг только после полного успешного скана; при abort/partial запись в `CatalogCacheSyncStats.aborted_reason`, кэш не прунится — существующая гарантия `sync_items()`).

Нового кода в Django не добавляется — используется существующая management-команда.

---

## 6. Вне scope

* Новые BFF/SyncServer эндпоинты (дух §11 TZ-OPERATION_MODAL_BALANCES_MANUAL_REFRESH «без новых ручек» сохранён: не добавляется ни одного).
* Изменения SyncServer: 404-защита `operations_service.py:1237-1242` остаётся как есть (последний рубеж, L5).
* BFF-превалидация operation create/update (дублировала бы SyncServer; текущих слоёв достаточно; возможный будущий hardening).
* Upsert/догрев активных ТМЦ в кэш из resolve-view (только деактивация).
* Удаление кнопки «Обновить и проверить».
*	Event-driven инвалидация кэша (webhooks/очереди из SyncServer) — нет инфраструктуры, требует отдельного ADR.
* Миграции БД — модели не меняются.

---

## 7. Test ladder

| Уровень | Что | Команды | Статус в ТЗ |
|---|---|---|---|
| 1 Static | Angular build; Django checks; отсутствие миграций | `npm run build`; `python manage.py check`; `python manage.py makemigrations --check --dry-run` | T1, T2 |
| 2 Unit | Логика сервиса/модалки; пруннинг-логика | `npm run test:unit` (`npx ng test --watch=false`); `python manage.py test apps.bff_api` | T3-T6 |
| 3 Component | Поведение модалки (vitest) | `npm run test:unit` | T3-T5 |
| 4 Integration | Django test DB: кэш ↔ lookup | `python manage.py test apps.catalog_cache` | T7 |
| 5 Stand smoke | Phantom-сценарий через API; `sync_catalog_cache` | curl/скрипт против стенда; `make sync-catalog-cache` | T8, T13 |
| 6 UI automation | Playwright phantom-flow | `make test-e2e` из корня | T9 |
| 7 User scenario | Сценарий кладовщика с фантомом | вручную/через UI automation | T12 |
| 8 Regression | Существующие e2e + Django-сьюты | `make test-e2e`; `python manage.py test` | T10, T11 |
| 9 Acceptance | Evidence-таблица | этот TZ | F1, F2 |

WPF/FlaUI уровни неприменимы (desktop не затрагивается).

---

## 8. Тестовый стенд

Используется существующий Docker-стенд (корневой `AGENTS.md`): SyncServer `:8000` (`GET /api/v1/health`), Django `:8001` (`GET /healthz/`), PostgreSQL `:5432`, Angular `:4200`. Управление: `make up/restart/status` из корня.

* **Seed phantom-сценария (T8/T9):** создать ТМЦ через SyncServer API (токены — только через env-переменные стенда `SYNC_ROOT_USER_TOKEN`/`SYNC_DEVICE_TOKEN`, значения не логировать) → прогреть кэш (поиск с `consistency=authoritative` либо `make sync-catalog-cache`) → удалить/деактивировать ТМЦ напрямую в SyncServer мимо Django → выполнить сценарий.
* **Переиспользование:** e2e-хелперы для seed в SyncServer уже существуют — см. `Warehouse_frontend/e2e/global-setup.ts`, `Warehouse_frontend/e2e/helpers/`, паттерны в `operation-reliability.spec.ts`.
* **Сброс:** `make restart`; кэш-записи — через `sync_catalog_cache` (полная сверка) либо очистку таблицы `catalog_cache_item` в test-БД (НЕ в prod).
* **Учётные данные dev-стенда:** Django admin `admin/admin123` (`make reset-django-admin` при проблемах).

---

## 9. Execution Strategy

**Staged parallel.** Максимум полезных потоков: **2**.

### Stage 1 — два независимых shard'а параллельно

| Shard | Владеет | Не трогает |
|---|---|---|
| A (Django) | `Warehouse_web/apps/bff_api/catalog_views.py` + тесты `apps/bff_api`; корневой `Makefile` (аддитивно); `Warehouse_web/DEPLOYMENT.md` (аддитивно) | Frontend, модели кэша |
| B (Angular) | `operation-create-modal.component.ts`, `operations.service.ts` + spec-файлы | Django, e2e (кроме своих будущих) |

* Контракт между shard'ами: `POST /bff/api/v1/catalog/read/items/resolve` **не изменяется** — shard B потребляет его как есть, shard A расширяет только side-effect внутри view.
* Зависимостей между shard'ами нет: WP-B работает и без пруннинга (валидация блокирует фантом), WP-A полезен и без авто-валидации (любой ручной «Обновить и проверить» лечит кэш).
* Commit'ы: каждый shard коммитит в `dev` только свои файлы, после своих тестов.

### Stage 2 — последовательно, после обоих shard'ов

* Новый e2e-spec `Warehouse_frontend/e2e/operations/operations-phantom-item-block.spec.ts` (T9) — требует и пруннинг, и авто-валидацию.
* Regression pack (T10, T11).
* Stand smoke T8, T13.

### Stage 3

* Закрытие чек-листа, Evidence, документация (F1, F2).

**Порядок интеграционных проверок:** сначала Django-уровень (T6/T7 — дёшево, без стенда), затем frontend-уровень (T3-T5), затем стенд (T8) и только потом UI automation (T9).

---

## 10. Риски и остаточные ограничения

| # | Риск | Митигация / решение |
|---|---|---|
| R1 | +1 resolve-вызов на каждый save/submit (латентность) | Батч ≤500 id, один вызов на сохранение; SyncServer resolve — bulk-read. Приемлемо |
| R2 | Резолвер недоступен → save заблокирован | By design: create в SyncServer всё равно упадёт; честное сообщение вместо 502 (§4.1) |
| R3 | Fast-поиск всё ещё может вернуть фантом ДО первого обращения (остаточный) | WP-C (ежечасная сверка); фантом в любом случае блокируется на save (L1) и прунится при первом resolve (L2) |
| R4 | Гонка: ТМЦ удалён между resolve(active) и create | SyncServer 404 (L5) + существующий submit-error surface (тосты) обрабатывают отказ |
| R5 | `balances=[]` при ошибке может выглядеть как «нулевые остатки» | `balanceLoadError` + обязательный тост при ручном refresh (B4/B5); quantity-валидация консервативна |
| R6 | Конфликт с параллельными сессиями в Makefile/DEPLOYMENT.md | Изменения строго аддитивные, минимальные; при конфликте — остановить и сообщить (правила AGENTS.md) |
| R7 | Съехавшие номера строк к моменту реализации | Ориентир — имена символов; исполнитель сверяет с фактическим кодом |

---

## 11. Критерии приёмки (итоговые)

1. Черновик с фантомной строкой **не сохраняется и не отправляется**: save/submit блокируются до обращения к SyncServer, пользователь видит причину; 404 «item not found» в этом сценарии недостижим.
2. После первой же блокировки фантом деактивирован в Django-кэше и больше не возвращается fast-поиском.
3. «Обновить всё» не имеет молчаливых no-op: всегда выполняет валидацию ТМЦ, остатки — где применимы; ошибки остатков видимы.
4. Существующие регрессионные сьюты (15 тестов manual-refresh, e2e-пак операций, Django-сьюты кэша/BFF) зелёные.
5. Ни одного нового эндпоинта; SyncServer не изменён; миграций нет.

## Evidence (заполняется executor'ом)

| Check | Command / Tool | Result | Evidence |
|---|---|---|---|
| Static | `npm run build`, `python manage.py check`, `makemigrations --check --dry-run` | pass | Angular build успешен (только pre-existing SCSS budget warnings); `check` — 0 issues; миграций нет |
| Unit/component | `npm run test:unit`, `python manage.py test apps.bff_api apps.catalog_cache` | pass | Angular 23 файла / 202 теста; Django 127 тестов (включая 5×T6 и T7) |
| Stand smoke | phantom-сценарий API; `make sync-catalog-cache` | pass | T8 PASS (phantom-ТМЦ деактивирован кэш, fast-поиск не возвращает); T13 `Catalog cache sync completed ... deactivated=2 ... complete` |
| UI automation | `make test-e2e` (operations-phantom-item-block.spec.ts) | pass | T9 e2e прошёл (9s): фантом блокирует Save, 404-тост отсутствует, после замены строки — сохранение OK |
| Regression | e2e-пак + Django-сьюты | pass | T10: 6 спеков операций — 46 passed / 3 pre-existing skipped / 0 failed; T11: Django apps.bff_api + apps.catalog_cache — 127 passed |
