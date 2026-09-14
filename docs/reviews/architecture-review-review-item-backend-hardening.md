# Architecture Review — Quartermaster 4.0: Review Item Backend Hardening

**Дата:** 2026-09-14
**Reviewer:** Architect (Stage 1 — analysis only, код не менялся)
**Closure:** 2026-09-14 (Stage 2A–2D) — D1/D2/D3 реализованы, верифицированы и закоммичены; документ переведён в READY FOR 4.0.
**Контекст:** ADR-0033 frontend принят и закрыт. При приёмке обнаружены три pre-existing backend/BFF дефекта. Angular в этой задаче не меняется.
**Метод:** доменная политика определена по `Functional and WorkLogik.md` (канонический FR), ADR-0012/0028/0033, коду SyncServer, легаси-сервису `TemporaryItemsResolutionService`, тестам и живому воспроизведению на изолированной тестовой схеме Postgres (in-process ASGI, scratch-скрипт через stdin, схема удалена после прогона; файлы репозитория не создавались).

---

## Verdict

> ## Review Item backend **READY FOR 4.0**
>
> Закрытие 2026-09-14 (Stage 2A–2C): оба RELEASE BLOCKER (D1, D3) и FIX BEFORE 4.0 (D2) исправлены и верифицированы — targeted и полные тесты, BFF, Angular unit + build, stand smoke. D4 остаётся 4.1 FOLLOW-UP. Перед production release — обязательный read-only аудит прод-БД на ранее возникшие данные (см. «Remediation note» в D3); auto-fix нет.

| # | Дефект | Статус | Commit(s) |
|---|---|---|---|
| D1 | `GET /review-items/{id}/operations` → 500 MissingGreenlet | ✅ **FIXED** | `ba63ad2` (SyncServer) |
| D2 | List DTO без `total_balance` / `has_pending_acceptance` | ✅ **FIXED** | `b9e5137` (SyncServer), `0f8f5f4` (Warehouse_frontend), `b98ed92` (Warehouse_web) |
| D3 | Merge review-item при активном pending acceptance | ✅ **FIXED** | `85ff707` (SyncServer) |
| D4 (наблюдение) | Detail DTO усекает дробные остатки до `int` | 4.1 FOLLOW-UP | — |

## Implementation closure (Stage 2A–2C)

**D1 (commit `ba63ad2`).** `get_operations_by_item_id` переведён на каноническую eager-load цепочку (`lines→item→temporary_item→resolved_item`; `lines→inventory_subject→temporary_item→resolved_item`), зеркально `list_operations`, без новых абстракций. HTTP-регрессия `tests/test_review_items_operations_greenlet_regression.py`: modern `catalog_item`-строка и реальная legacy `temporary_item`-строка (active + `merged_to_item` resolved-проекции).

**D2 (commits `b9e5137`, `0f8f5f4`, `b98ed92`).** List DTO отдаёт серверные `total_balance: Decimal` (сумма остатков по subject item'а), `has_pending_acceptance` (только pending qty>0) и `has_active_registers` (pending|lost|issued — enforcement-предикат). Агрегация страницы: subjects-map + `SUM(balances)` + `UNION ALL` регистров → константное число запросов; тест `tests/test_review_items_list_action_state.py` (6 сценариев, DB cross-check, list/detail parity, N+1-гард). Angular потребляет server-поля и блокирует destructive actions при `has_active_registers=true`; BFF — pass-through + контракт-тест.

**D3 (commit `85ff707`).** Guard `has_active_registers(source_subject)` → 409 до любых мутаций merge (паритет с `delete_review_item` и legacy-политикой); тесты `tests/test_review_items_merge_guards.py` (8 тестов: pending/lost/issued, state-unchanged, RECEIVE→pending→409→accept→200).

### Verification evidence

| Проверка | Команда | Результат |
|---|---|---|
| SyncServer full | `.venv/bin/python -m pytest -q` | **1004 passed**, 3 skipped, 13 deselected, 6 xfailed |
| BFF | `python manage.py test apps.bff_api` (Docker) | **126 OK** |
| Angular unit | `npm run test:unit` | **255 passed** (26 files) |
| Angular build | `npm run build` | OK |
| Stand smoke D1 | `GET /review-items/{id}/operations` → 200 (modern item 4768; legacy 849/839 resolved-проекции) | SMOKE_OK |
| Stand smoke D2 | `GET /review-items` (page 50) — SQL cross-check 50/50, detail parity | SMOKE_OK |
| Stand smoke D3 | RECEIVE→pending→merge **409**→accept→merge **200** (item 4767) | SMOKE_OK |

### ADR-0033 checklist impact

Отдельных пунктов «§7.1/§7.2» в Execution Checklist ADR-0033 нет: пункт 5 («Этап 4: BFF + Angular…») объединяет обязательные §7.1/§7.2-поверхности и optional §7.3 (warning в inline-модалке). Обязательные поверхности подтверждены прогонами этого closure (BFF 126 OK, включая identity-BFF тесты; Angular 255 passed), однако чек-боксы ADR-0033 в этой docs-only задаче не изменяются — исполнитель/верификатор ADR-0033 является отдельной ролью. **§7.3/optional не закрывается.**

---

## Доменная политика (определена до анализа дефектов)

Источники (приоритет по убыванию): `Functional and WorkLogik.md` §IV/§V → ADR-0012/0028/0033 → легаси-код `TemporaryItemsResolutionService` → `ReviewItemsService` → тесты. Поведение Angular использовалось только как corroborating evidence, не как источник политики.

Ключевые правила:

1. **FR §IV.2.1:** список «ТМЦ, требующие проверки» — таблица с пагинацией, сортировкой и полями «название, когда создана и **количество в остатка**». Остаток в списке — требование канонического FR.
2. **FR §IV.1.3:** удаление допустимо, только если ТМЦ не состоит в остатках.
3. **FR §IV.1.4:** «преобразовать временную тмц в постоянную (или сделать мерж с постоянной) можно **только после завершённой приёмки** где есть эта временная тмц, временной ТМЦ не должно быть в репозитории непринятого».
4. **FR §V (~строка 104):** ТМЦ, попавшие в репозиторий непринятого, «замораживаются к изменению».
5. **FR §IV.3.1:** слияние суммирует остатки source и target.
6. **ADR-0033 AC-14 / §3:** merge — **единственный** санкционированный механизм переноса остатков; guard-сценарии не должны менять остатки.
7. **ADR-0012:** в новом flow submit материализует inline-payload в постоянный Item (`requires_review=true`, `review_status=needs_review`) с обычным `InventorySubject`; moderation через `/api/v1/review-items/*`.
8. **Легаси-политика (перенесена частично):** `TemporaryItemsResolutionService._check_no_active_registers` (`app/services/temporary_items_resolution_service.py:22-37`) → 409 «…has active pending/lost/issued registers; resolve them before approve/merge»; вызывалась в `approve_as_item` (180), `merge_to_item` (350), `delete_temporary_item` (467).
9. **Паритет в новом сервисе:** `ReviewItemsService.delete_review_item` (`app/services/review_items_service.py:397-402`) блокирует удаление при `has_active_registers` (pending ИЛИ lost ИЛИ issued qty>0, `app/repos/asset_registers_repo.py:29-61`). **Merge и confirm аналогичной проверки не получили** — политика потеряна при портировании.
10. **Механика приёмки:** RECEIVE/MOVE — acceptance-типы (`operations_service.py:66`). Submit RECEIVE пишет **только** pending-регистр, без остатка (`operations_service.py:2391-2402`). Остаток появляется лишь в `accept_operation_lines` → `balances.update_balance_quantity(site, line.inventory_subject_id, +accepted)` (`operations_service.py:2753-2757`).

**Итоговое решение по пункту 3 задачи:** merge при наличии активных регистров (pending/lost/issued) **должен быть запрещён** (вариант «block»). Вариант «мигрировать/canonicalize pending на target» **не санкционирован**: он прямо противоречит FR §IV.1.4 («только после завершённой приёмки»), фальсифицировал бы исторические ссылки регистров на `operation_line_id` (PK `pending_acceptance_balances`, проверки ADR-0028 ACCEPTANCE_EFFECT_GAP / EFFECT_CHAIN_BROKEN) и подменил бы аудит приёмки. Текущее поведение **не является намеренным**: это регрессия портирования — в легаси-сервисе проверка была, в `delete_review_item` она сохранена, в `merge_review_item` отсутствует.

---

## D1 — `GET /review-items/{id}/operations` → 500 MissingGreenlet

> **Статус: ✅ FIXED — commit `ba63ad2` (2026-09-14).** Реализация и verification — в «Implementation closure» выше.

### Root cause (подтверждён живым воспроизведением)

Eager-load drift в репозитории. Цепочка:

1. Route `app/api/routes_review_items.py:154-180` вызывает `uow.operations.get_operations_by_item_id(...)` и строит `OperationListResponse(items=operations,...)` (строка 175).
2. `app/repos/operations_repo.py:560-611` `get_operations_by_item_id` загружает **только** `.options(selectinload(Operation.lines))` (строка 605).
3. `OperationLineResponse` (`app/schemas/operation.py:185-225`) объявляет поля `subject_type`, `temporary_item_id`, `temporary_item_status`, `resolved_item_id`, `resolved_item_name` — это Python `@property` на `OperationLine` (`app/models/operation.py:361-397`), обращающиеся к ленивым relationships `inventory_subject`, `item`, `item.temporary_item`, `temporary_item.resolved_item` → async lazy-load вне greenlet-контекста.

Зафиксированный traceback воспроизведения (2026-09-14, dev HEAD, изолированная схема):

```
pydantic_core._pydantic_core.ValidationError: 5 validation errors for OperationListResponse
items.0.lines.0.subject_type
  Error extracting attribute: MissingGreenlet: greenlet_spawn has not been called; ...
items.0.lines.0.temporary_item_id      — то же
items.0.lines.0.temporary_item_status  — то же
items.0.lines.0.resolved_item_id       — то же
items.0.lines.0.resolved_item_name     — то же
  (фрейм: app/api/routes_review_items.py:175, in list_review_item_operations)
HTTP status as seen by client: 500
```

Дефект **детерминированный и всеобщий**: у любого review item всегда есть ≥1 операция (породивший RECEIVE), а линии всегда eagerly-загружены, поэтому pydantic валидирует каждую линию и трогает свойства → 500 для каждого review item. Пустой список вернул бы 200, но такой случай недостижим.

`expire_on_commit=False` (`app/core/db.py:30`) — не причина; отношения просто никогда не загружены.

**Почему ускользнул от тестов:** `tests/test_temporary_items_stage3b.py` — happy-path тесты «GET /review-items/{id}/operations» вызывают **репозиторий напрямую** (строки 167-185, 197-208) без сериализации; единственный HTTP-вызов — тест прав 403 (строки 251-256). Путь response_model-сериализации не покрыт.

### Intended behavior

200 + `OperationListResponse` с полными полями линий (включая temporary/resolved-проекции) — идентично `GET /operations` и `GET /temporary-items/{id}/operations`, которые используют каноническую цепочку eager-load.

### Severity: RELEASE BLOCKER

Публичный `/api/v1` endpoint стабильно возвращает 500 на принятом 4.0 UI-surface (история операций review item). Прямо противоречит Project Priority #1 («Stabilize SyncServer API contracts»).

### Minimal fix

В `get_operations_by_item_id` (`operations_repo.py`, stmt на строках 602-609) зеркально повторить каноническую цепочку из `list_operations` (строки 327-336) / `get_operations_by_temporary_item_id` (строки 540-556):

```python
.options(
    selectinload(Operation.lines)
    .selectinload(OperationLine.item)
    .selectinload(Item.temporary_item)
    .selectinload(TemporaryItem.resolved_item),
    selectinload(Operation.lines)
    .selectinload(OperationLine.inventory_subject)
    .selectinload(InventorySubject.temporary_item)
    .selectinload(TemporaryItem.resolved_item),
    selectinload(Operation.lines),
)
```

Контракт не меняется. Аудит дрейфа выполнен: `OperationListResponse` строится ещё в `routes_temporary_items.py:114` (repo с полной цепочкой ✅) и `routes_operations.py:123` (`list_operations`, полная цепочка ✅); `get_operation_by_id` (строки 86+) — полная цепочка ✅. **Дрейф единичен.**

### Затрагиваемые файлы

- `SyncServer/app/repos/operations_repo.py` (только `get_operations_by_item_id`).

### Необходимые тесты

1. Новый HTTP-регрессионный тест (стиль `tests/test_admin_sites_greenlet_regression.py`): seed → RECEIVE с inline temporary_item → submit (chief) → `GET /api/v1/review-items/{id}/operations` с chief-токеном → assert 200, `items[0].lines[0]` содержит непустые `subject_type`/`temporary_item_id`/`temporary_item_status`; в docstring зафиксировать «до фикса — 500 MissingGreenlet».
2. Перевести happy-path проверки stage3b с repo-direct на HTTP-уровень (или добавить HTTP-вариант), чтобы сериализация больше не ускользала.
3. Прогон `python -m pytest` (SyncServer) целиком.

---

## D2 — List DTO без `total_balance` / `has_pending_acceptance`

> **Статус: ✅ FIXED — commits `b9e5137` (SyncServer), `0f8f5f4` (Warehouse_frontend), `b98ed92` (Warehouse_web).** Реализация и verification — в «Implementation closure» выше.

### Root cause

Контракт list-ответа никогда не содержал этих полей ни в одной версии backend:

- `ReviewItemResponse` (`app/schemas/review_item.py:12-33`) — 19 полей, подтверждено живым воспроизведением: `category_id, category_name, created_at, description, hashtags, id, is_active, item_name, requires_review, review_created_by_user_id, review_note, review_resolved_at, review_resolved_by_user_id, review_status, sku, unit_id, unit_name, unit_symbol, updated_at`. `total_balance`/`has_pending_acceptance` отсутствуют.
- Легаси `TemporaryItemResponse` (`app/schemas/temporary_item.py:28-50`) их тоже не имел; легаси Django SSR (`Warehouse_web/apps/temporary_items/views.py`) не обогащал.
- grep: `total_balance`/`has_pending_acceptance` — **0 совпадений** в исходниках SyncServer и Warehouse_web; встречаются только в Angular-моделях и скомпилированном chunk.
- `app/repos/catalog_repo.py:637-684` `list_review_items_page` — плоский запрос Item без агрегатов.
- BFF (`Warehouse_web/apps/bff_api/review_items_views.py:23-42` → `apps/sync_client/review_items_api.py:78-98` `list_review_items_page`) — **чистый dict pass-through** (`return self.client.get("/review-items", params=params)`), новых полей не теряет.

Потребитель (принятый ADR-0033 Angular, read-only evidence): `temp-items.models.ts` объявляет `TemporaryItem.total_balance: number` как обязательное поле; `toTempItemVm` читает `item.total_balance ?? 0`; сервис `temp-items.service.ts` hardcode-ит `hasPendingAcceptance=false`, `opsCount=0`. Следствие сегодня: **каждая строка списка показывает остаток 0** → `computeActionFlags` выдаёт `canDelete=true` («Можно удалить») даже для ТМЦ с остатком и `canConvert/canMerge=false` с причиной «Нет остатка для преобразования/слияния» — инверсия флагов на list surface. FR-требуемая колонка «количество в остатка» (§IV.2.1) физически не может быть показана без N+1.

### Intended behavior (contract intent)

Поля **должны** присутствовать в list-контракте, серверно-вычисляемые:

- `total_balance` — прямое требование FR §IV.2.1 (колонка остатка в таблице списка). Клиент не может вычислить его без N+1 по detail-запросам.
- `has_pending_acceptance` — необходимое условие корректного action gating по FR §IV.1.4/§V (заморозка) без N+1 по `/pending-acceptance?item_id=`. Имя поля совпадает с моделью потребителя и с фильтром `has_pending_acceptance`, уже объявленным в Angular-моделях.

Расширение **аддитивное** (не ломает существующих потребителей) и подтверждено contract intent: потребитель объявил поля с первого дня, backend их никогда не отдавал. Это не «расширение API без подтверждения» — это закрытие незакрытого контракта.

Типы: `total_balance: Decimal` (сериализуется строкой, как в operations DTO), **не int** — остатки `Numeric(18,3)`, дробные количества легальны (см. D4: существующий detail-DTO уже грешит усечением `qty=int(br.qty)`, `routes_review_items.py:123` — не повторять).

Семантика флага — осознанное решение: отдавать `has_pending_acceptance` = pending qty>0 (точное соответствие имени и UI-текстовкам «участвует в незавершённой приёмке»). Серверная **enforcement**-политика шире (pending|lost|issued через `has_active_registers`); чтобы UI никогда не показывал действия, которые сервер отвергнет, рекомендуется дополнительно отдать `has_active_registers: bool` тем же агрегатом (аддитивно, стоит 0 дополнительных запросов). Потребление обоих полей Angular — отдельный follow-up (в этой задаче Angular не меняем; `total_balance` при этом подхватится принятым фронтом **автоматически** через `item.total_balance ?? 0`).

### Severity: FIX BEFORE 4.0

Нарушение канонического FR §IV.2.1 и инверсия action flags на принятом экране. Порчи данных нет: деструктивные операции защищены серверно (delete — `has_active_registers`+balances 409; merge — после фикса D3).

### Minimal fix

1. `app/schemas/review_item.py`: в `ReviewItemResponse` добавить `total_balance: Decimal = Decimal("0")`, `has_pending_acceptance: bool = False`, (рекомендуется) `has_active_registers: bool = False`. Defaults сохраняют валидность всех прочих мест, строящих `ReviewItemResponse` (confirm/merge-ответы).
2. Агрегация **одним-двумя запросами на страницу** (без N+1) в list-ручке `routes_review_items.py:57-88` или в `catalog_repo.list_review_items_page`:
   - `SUM(balances.qty)` по `inventory_subjects.item_id IN (page item ids)` GROUP BY item_id;
   - `EXISTS`/`SUM(qty)>0` по `pending_acceptance_balances` (и для `has_active_registers` — также `lost_asset_balances`, `issued_asset_balances`) по subject'ам тех же item id.
3. Django BFF: изменений не требует (dict pass-through подтверждён).
4. Angular: изменений не требует для `total_balance` (подхватится автоматически); потребление `has_pending_acceptance`/`has_active_registers` — отдельный follow-up тикет (вне scope).

### Затрагиваемые файлы

- `SyncServer/app/schemas/review_item.py`;
- `SyncServer/app/api/routes_review_items.py` (list-ручка) и/или `SyncServer/app/repos/catalog_repo.py` (`list_review_items_page`);
- возможно `SyncServer/app/repos/balances_repo.py` / `asset_registers_repo.py` (новый агрегатный метод за UoW).

### Необходимые тесты

1. Component/integration (pytest + реальная PG-схема): seed двух review items — один с принятым остатком 5.500 на сайте и pending-строкой, другой пустой → list-ответ: `total_balance == "5.500"` / `has_pending_acceptance == true` и `0`/`false` соответственно; `total_count`/пагинация не изменились.
2. Guard против N+1: количество SQL-запросов на страницу постоянно (опционально, через echo/count).
3. Регресс: существующие тесты review-items (confirm/merge-ответы остаются валидными с новыми defaults).
4. BFF pass-through smoke (опционально, `Warehouse_web`: `python manage.py test` для sync_client-контракта, если добавляется contract-тест).

---

## D3 — Merge review-item при существующем pending acceptance

> **Статус: ✅ FIXED — commit `85ff707` (2026-09-14).** Реализация и verification — в «Implementation closure» выше.

### Сценарий и живое воспроизведение (2026-09-14, dev HEAD)

Сценарий задачи: **RECEIVE partial/pending → review item → merge before acceptance → accept.**

| Шаг | Факт (зафиксировано прогоном) |
|---|---|
| RECEIVE inline qty=5 (storekeeper) + submit (chief) | review item id=3, subject id=2; `pending_rows=[(line 2, qty '5.000')]`; `balances=[]` (submit остаток не пишет) |
| `POST /review-items/3/merge {target_item_id: 1}` | **HTTP 200**; `review_status=merged`, `is_active=false`; subject `archived_at` установлен; переноса нет (балансы нулевые); **pending-строка остаётся** на архивированном subject: `[(2, '5.000')]` |
| `POST /operations/{id}/accept-lines {accepted_qty: 5}` | **HTTP 200** — приёмка не проверяет ни `item.is_active`, ни `subject.archived_at` |
| Финальное состояние БД | **Архивированный subject слитого item: `balances=['5.000']`. Target subjects=[3], target balances=[] (ноль).** `pending_rows_left=[]` |

### Root cause

`ReviewItemsService.merge_review_item` (`app/services/review_items_service.py:172-362`) не вызывает `has_active_registers` перед переносом/архивацией — проверка, существующая в `delete_review_item` (397-402) и в легаси `_check_no_active_registers` (invoke в `merge_to_item`, строка 350), при портировании в review-flow потеряна. Downstream-факторы, делающие дефект тихим:

- `accept_operation_lines` не проверяет `archived_at`/`is_active`;
- `balances_repo.update_balance_quantity` → upsert без archived-guard (`balances_repo.py:60-75`);
- `asset_registers_repo.list_pending` (213-278) не фильтрует архивированные subject'ы → строка остаётся видимой и принимаемой после merge.

### Нарушенные инварианты

1. **FR §IV.3.1** («слияние суммирует остатки»): принятые 5 ед. не попали на target — target получил 0.
2. **ADR-0033 AC-14 / §3** (merge — единственный санкционированный механизм переноса остатков): перенос выполнен в состоянии, когда переносить нечего, а последующее пополнение ушло «в никуда» учёта.
3. **FR §IV.1.4 / §V** (merge только после завершённой приёмки; замороженность в репозитории непринятого).
4. **Историческая целостность (ADR-0028):** accepted-остаток на архивированном subject неактивного item — состояние, которое integrity CLI **не детектирует** (effects и balances остаются взаимно консистентны; проверки BALANCE_EFFECT_DRIFT / ACCEPTANCE_EFFECT_GAP не триггерятся) → **молчаливая перманентная порча учёта**.

### Intended behavior

Merge обязан отклоняться с **409** при `has_active_registers(source_subject)` (pending ИЛИ lost ИЛИ issued qty>0) — паритет с `delete_review_item`, легаси-политикой и FR §IV.1.4. Миграция pending-строк на target запрещена (см. «Доменная политика» выше).

Отдельное осознанное решение: **`confirm_review_item` НЕ блокировать.** В легаси approve блокировался, потому что преобразование перепривязывало subject; в новом flow (ADR-0012) confirm сохраняет тот же item и тот же subject, pending-ссылки остаются валидными, приёмка корректно пополняет остаток — инвариант не нарушается. Identity-модерация и физическая приёмка в новом flow ортогональны (submit создаёт pending до модерации — это нормальная последовательность). Опциональный паритетный hardening confirm — предмет обсуждения 4.1, не требование.

### Severity: RELEASE BLOCKER

Молчаливая, перманентная, не детектируемая integrity-инструментами порча складского учёта (принятый товар исчезает из учёта target). Единственный барьер сегодня — клиентская блокировка в Angular; API/BFF-контракт её не обеспечивает, а клиенты не обязаны быть только браузерными (планируемый `Warehouse_client_core`, прямые вызовы BFF).

### Minimal fix

В `merge_review_item` после резолва `source_subject` (строка 216) и `target_subject` (строка 223), но **до** цикла переноса балансов (строка 250):

```python
if await uow.asset_registers.has_active_registers(int(source_subject.id)):
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="review item has active pending/lost/issued registers; resolve them before merge",
    )
```

(формулировка — паритет с `delete_review_item` 397-402 и легаси `_check_no_active_registers`). Транзакция merge атомарна — состояние при 409 не меняется.

### Затрагиваемые файлы

- `SyncServer/app/services/review_items_service.py` (только `merge_review_item`).

### Необходимые тесты

1. Новый `tests/test_review_items_merge_guards.py` (pytest, реальная PG-схема):
   - RECEIVE inline → submit → merge при pending → **409**; assert: subject не архивирован, item активен, `review_status=needs_review`, pending-строка цела, балансов нет;
   - accept-lines полностью → merge → **200**, балансы перенесены на target (существующее happy-path поведение сохранено);
   - mark_lost сценарий: pending → lost qty>0 → merge → **409**;
   - частичная приёмка (accepted < qty, остаток в pending) → merge → **409**.
2. Регресс: существующие merge-тесты (happy path без регистров) проходят без изменений.
3. `python -m pytest` (SyncServer) целиком.

### Ремедиация существующих данных (operational note)

После деплоя фикса D3 новые порчи невозможны, но уже возникшие (если merge вызывался напрямую через API/BFF) остаются невидимыми для integrity CLI. Аудит-запросы (имена таблиц сверены с моделями; выполнять read-only на прод-копии):

```sql
-- 1. Pending-строки на архивированных subject'ах
SELECT p.operation_line_id, p.inventory_subject_id, p.qty, s.archived_at
FROM pending_acceptance_balances p
JOIN inventory_subjects s ON s.id = p.inventory_subject_id
WHERE s.archived_at IS NOT NULL AND p.qty > 0;

-- 2. Ненулевые остатки на архивированных subject'ах неактивных (слитых) items
SELECT b.site_id, b.inventory_subject_id, b.qty, i.id AS item_id, i.review_status
FROM balances b
JOIN inventory_subjects s ON s.id = b.inventory_subject_id
JOIN items i ON i.id = s.item_id
WHERE s.archived_at IS NOT NULL AND b.qty <> 0 AND i.is_active = false;
```

При находках — точечная ручная коррекция через штатные adjustment-операции с аудитом (не прямой UPDATE). Решение о ремедиации принимает пользователь.

**Подтверждённый инцидент (dev-стенд, read-only аудит 2026-09-14):** запрос №1 — 0 строк; запрос №2 — 2 строки:

- **item 4729** — срабатывание D3 на старом коде: `review_item.merge` 2026-09-14 04:26:28 выполнен при активном pending → accept 04:27:06 → принятые `5.000` легли на архивированный subject (target не пополнён; мёртвый остаток, integrity CLI не детектирует);
- item 3659 — legacy non-review (`review_status` NULL, subject archived 2026-07-31, остаток 1.000), не D3-класс; решение по нему — отдельно.

**Обязательное условие production release:** выполнить оба аудита выше **read-only** на прод-БД (или её копии) до релиза. **Никакого auto-fix.** При находках решение о ремедиации принимает пользователь; коррекция — только штатными adjustment-операциями с аудитом, не прямым UPDATE.

---

## 4.1 FOLLOW-UP (после закрытия D1–D3)

1. **`ReviewItemBalanceDto.qty` → Decimal (D4).** `ReviewItemBalanceDto.qty: int` (`SyncServer/app/schemas/review_item.py:71-74`) и `qty=int(br.qty)` в detail-ручке (`routes_review_items.py:123`) **усекают** дробные остатки `Numeric(18,3)` (5.750 → 5). 500 не возникает (явный int-каст), но detail-экран показывает неверные дробные остатки. Фикс аддитивен, но меняет JSON-тип поля → согласовать с потребителями в 4.1. В list-контракте D2 исправлено сразу (Decimal).
2. **Register guard TOCTOU/concurrency.** Проверка `has_active_registers` не берёт `FOR UPDATE` на register-строках — унаследованный паритет с legacy `_check_no_active_registers` и `delete_review_item`; этой задачей риск не введён и не ухудшен. При необходимости — отдельный дизайн блокировок (последовательная проверка под блокировкой subject/register-строк).
3. **Modern review-item vs legacy TemporaryItem projections.** `review-items` confirm/merge не выставляют `TemporaryItem.status`/`resolved_item_id` — проекции заполняются только legacy-потоком (`/temporary-items/*`); у современных review-item линий `temporary_item_id/status` и `resolved_item_id/name` остаются null. Требует отдельного решения о консистентности read-модели (не менять в 4.0 без ADR).

---

## Stress-test (architecture-review checklist) — сводка

- **Complexity:** все три фикса — зеркальное повторение существующих паттернов того же кода (options-цепочка, has_active_registers-гард, аддитивные DTO-поля). Проще некуда. ✅
- **Coupling:** D3 переиспользует уже применяемый в delete репо-метод; D2 не добавляет связей между сервисами (агрегация внутри SyncServer); BFF/Angular изменений не требуют. ✅
- **Data & state:** источник истины — SyncServer; миграции не нужны (схема БД не меняется). ✅
- **Failure modes:** D3 превращает молчаливую порчу в явный 409 (улучшение); D1/D2 — read-only пути. ✅
- **N+1 / scalability:** D1 — selectinload, константное число запросов (как `list_operations`); D2 — явное требование «агрегация на страницу, не на строку» + тест-гард. ✅
- **Security:** все ручки уже за `require_temporary_item_moderation` (chief/root); поверхность не расширяется. ✅
- **Observability:** 409 D3 логируется штатным access-log + рекомендуется warning-лог с item_id/subject_id для мониторинга попыток. 🔵
- **Operability:** деплой без downtime (чистый backend, аддитивные поля); rollback — откат коммитов. Ремедиация данных — отдельный аудит-шаг (см. выше). ✅
- **Найденное при stress-test:** D4 (int-усечение detail-остатков) — вынесено в 4.1; единичность eager-load дрейфа подтверждена аудитом всех трёх потребителей `OperationListResponse`.

## Execution Strategy

**Sequential, один исполнитель.** Обоснование: все три фикса живут в одном доменном кластере review-items (`operations_repo.py`, `schemas/review_item.py` + `routes_review_items.py`/`catalog_repo.py`, `review_items_service.py`), делят одну тестовую поверхность (seed-паттерн RECEIVE-inline→submit→merge/accept) и один прогон `python -m pytest`; суммарный diff мал (~50-80 строк кода + ~200 строк тестов). Файлы технически не пересекаются, поэтому при желании допустим **staged parallel** (максимум 2 потока): Stage A — D1+D3 независимо (разные файлы, разные тест-файлы), Stage B — D2 после утверждения контрактных имён/типов. Параллельность >2 бесполезна: интеграция и ревью всё равно последовательные.

Порядок внутри sequential: **D3 → D1 → D2** (сначала закрываем порчу данных, затем 500, затем контракт).

Integration points: Django BFF — не трогаем (pass-through подтверждён); Angular — не трогаем (follow-up тикет на потребление `has_pending_acceptance`/`has_active_registers` заводит пользователь отдельно).

## Test ladder (для последующего TZ)

| Уровень | Применимость |
|---|---|
| 1 Static | ruff/lint штатный; новых зависимостей нет |
| 2 Unit | не требуется отдельно (логика в сервисах покрыта component-уровнем) |
| 3/4 Component+Integration (PG) | основные тесты: D1 HTTP-регрессия; D2 list-агрегаты; D3 merge-гарды (409/200 сценарии) |
| 5 Stand smoke | после деплоя: `GET /review-items/{id}/operations` → 200 на стенде; merge при pending → 409 |
| 6 UI automation | не требуется (Angular не меняем); опционально существующий Playwright-регресс экрана «ТМЦ, требующие проверки» |
| 7 User scenarios | RECEIVE partial → попытка merge → 409 → accept → merge → 200 → остатки на target |
| 8 Regression | `python -m pytest` (SyncServer) полностью; stage3b-тесты без изменений проходят |

## Итоговые ответы по дефектам (сводка)

| | D1 | D2 | D3 |
|---|---|---|---|
| **Root cause** | eager-load drift в `get_operations_by_item_id` (только lines) | поля никогда не отдавались backend; потребитель объявил их с первого дня | проверка `has_active_registers` потеряна при портировании из легаси в `merge_review_item` |
| **Intended behavior** | 200 + полные line-проекции | серверные `total_balance` (Decimal) + `has_pending_acceptance` (+`has_active_registers`) в list | 409 при активных регистрах; миграция pending запрещена; confirm не блокировать |
| **Severity** | RELEASE BLOCKER | FIX BEFORE 4.0 | RELEASE BLOCKER |
| **Minimal fix** | options-цепочка в repo | 2-3 аддитивных поля + 1-2 агрегатных запроса на страницу | один guard в сервисе |
| **Файлы** | `operations_repo.py` | `schemas/review_item.py`, `routes_review_items.py` и/или `catalog_repo.py` | `review_items_service.py` |
| **Тесты** | HTTP-регрессия 200 | list-контракт + N+1-гард | merge-гарды 409/200 (4 сценария) |
