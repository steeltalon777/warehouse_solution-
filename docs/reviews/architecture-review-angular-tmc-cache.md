# Architecture Review — актуальность кэша ТМЦ и сохранение Angular-операций

**Дата:** 2026-07-13  
**Статус:** Final, revision 4  
**Формат:** лёгкое архитектурное ревью, без реализации и без изменения runtime-кода

## 1. Verdict

**Кнопку «Принудительно обновить ТМЦ» добавить можно, но как самостоятельное исправление она недостаточна.** В текущем контуре основной риск находится не в Angular, а одновременно в двух нижних слоях:

1. SyncServer допускает путь, при котором soft-deleted review item может остаться `is_active=true`, а часть catalog read-моделей фильтрует только `is_active` и не проверяет `deleted_at`.
2. Django хранит постоянный `catalog_cache_item`, но не имеет завершённого протокола invalidation/reconciliation после deactivate/delete/merge.

В результате Angular может честно повторно запросить данные и снова получить «призрак». Рекомендуемый порядок: **сначала исправить authoritative-инвариант SyncServer, затем Django cache coherence, и только после этого добавить Angular refresh/repair UX**.

Дополнительное уточнение жалобы выявило отдельный риск: после нажатия «Сохранить» кладовщик позднее открывает операцию и видит предыдущий состав без последних добавлений. Это **не cache symptom**, потому что повторное открытие получает detail операции из SyncServer. Текущий save-flow допускает неотправленный и потерянный save-intent, а SyncServer заменяет весь набор строк без optimistic concurrency. Исправление сохранения должно войти в тот же первый релиз, но отдельным контрактом.

## 2. Контекст инцидента

На production со старой версией приложения при редактировании draft-операции поиск предложил ТМЦ, строка была добавлена, но сохранение завершилось ошибкой `item does not exist`. В каталоге тот же объект ещё отображался, а повторное удаление сообщило, что объект уже удалён или смержен. В новой вкладке поиск этот объект уже не нашёл.

Дополнительный production-аудит, переданный владельцем продукта 2026-07-13, подтвердил 26 строк `is_active=true AND deleted_at IS NOT NULL`; приведён пример item `2064`. Агент не подключался к production DB, поэтому count является внешним evidence и должен быть повторён перед remediation. Root cause подтверждён текущим кодом: `CatalogRepo.list_items_page()` фильтрует `is_active`, но не `Item.deleted_at`, а `CatalogRepo.soft_delete_item()` устанавливает delete metadata без `is_active=false`.

Отдельная пользовательская жалоба сформулирована точнее: кнопка «Сохранить черновик» нажимается, однако после закрытия и повторного открытия операции сервер возвращает предыдущий шаг — новые строки отсутствуют. Поэтому визуальный success indicator полезен, но сам по себе проблему не решает: требуется доказуемая persistence-консистентность.

Точная production-ревизия не зафиксирована, поэтому соответствие инцидента конкретному коммиту не доказано. Однако в текущем коде найдены несколько подтверждённых архитектурных путей к такому классу ошибки.

Канонический документ формулирует требования буквально:

> **II.5.0:** «таблица ТМЦ с поиском указанием количества на выбранном складе и категории (**поиск должен быть закеширован**)».

> **II.8:** «кладовщик создаёт операцию → добавляет построчно ТМЦ (**на фронтенде должен работать кеш и поиск**) → делает подтверждение… именно на этом моменте в СинкСервере идёт проверка полномочий».

Эти требования обязывают сохранить быстрый кэшированный поиск, но не назначают кэш источником истины. Пункт II.8 прямо сохраняет SyncServer в authoritative write-flow; удалённые, inactive или merged-source ТМЦ не должны предлагаться как пригодные для новой строки операции.

## 3. Фактическая схема

### 3.1. Поиск в модальном окне операции

```text
OperationCreateModalComponent
  -> ItemCacheSearchComponent.localResults (память компонента)
  -> CatalogSearchService.searchItemsOnce()
  -> GET /bff/api/v1/catalog/search/items
  -> CatalogCachedItemSearchView
  -> CatalogLookupService
  -> Django DB: catalog_cache_item (cache-first)
  -> только при недостатке строк: SyncServer /catalog/read/items
```

### 3.2. Остальные клиентские состояния

| Область | Фактическое хранение | Жизненный цикл | Риск для инцидента |
|---|---|---|---|
| Picker ТМЦ операции | `ItemCacheSearchComponent.localResults` | До нового поиска/выбора/закрытия компонента | Низкий сам по себе |
| Фильтр журнала операций | `OperationsPageComponent.itemSearchCache: Map<query, ids>` | До уничтожения страницы | Может устареть внутри вкладки, но это не picker строк операции |
| Номенклатура Angular | `NomenclatureService.allItems` из bootstrap | До `loadBootstrap()`/перезагрузки SPA | Может показывать старый snapshot между изменениями в других вкладках/клиентах |
| Единицы измерения Angular | `CatalogSearchService.unitCache` | Жизнь root-service | Не объясняет удалённую ТМЦ |
| Поиск Django | таблица `catalog_cache_item` | Между запросами, перезапусками и вкладками | Основной долгоживущий cache-risk |
| SyncServer | PostgreSQL catalog tables | Authoritative | Должен определять пригодность item |

`cacheBust=true` в `NomenclatureService.loadBootstrap()` добавляет query nonce только к bootstrap-запросу. Он не очищает `catalog_cache_item` и сам по себе не исправляет server-side ghost.

Старая SSR-форма операций также использует `CatalogLookupService` через `Warehouse_web/apps/operations/services.py`. Поэтому найденный server-side дефект применим и к старой production-версии независимо от того, какой именно Angular bundle был развёрнут.

## 4. Findings

### 🔴 F1. Нарушен единый инвариант soft-delete в SyncServer

`OperationsService._delete_temporary_items_of_operation()` при отмене операции вызывает `CatalogRepo.soft_delete_item()`. Репозиторий выставляет `deleted_at` и `deleted_by_user_id`, но не гарантирует `is_active=false`.

Для обычной ТМЦ это частично скрыто правилом «сначала deactivate, потом delete». Для активной `requires_review=true` ТМЦ удаление разрешено, поэтому возможна запись:

```text
deleted_at != null AND is_active == true
```

При этом:

- `OperationsService._ensure_item_usable()` правильно отклоняет её по `deleted_at`;
- `CatalogRepo.list_items_page()` и `get_item_read_model()` проверяют `is_active`, category и unit, но не везде явно проверяют `Item.deleted_at IS NULL`;
- поиск/каталог способен показать item, который операция затем отвергнет.

Это наиболее сильное соответствие описанному production-симптому: item виден в каталоге, повторное удаление отвечает «already deleted», а операция отвечает `item not found`.

**Обязательный инвариант:** item пригоден для нового использования только если одновременно:

```text
exists
AND deleted_at IS NULL
AND is_active = true
AND merged_into_id IS NULL
AND category active/not deleted
AND unit active/not deleted
```

Инвариант должен обеспечиваться и write-path, и каждым operational read-model. Одного фильтра в UI недостаточно.

### 🔴 F2. Django cache sync не умеет удалять «исчезнувшие» записи

`CatalogCacheSyncService.sync_items()` читает active browse-страницы и выполняет только upsert. Если source item после merge/deactivate/delete больше не входит в active browse, соответствующая строка Django не обновляется и остаётся `is_active=true`.

Дополнительно:

- `CatalogLookupService` фильтрует только локальное `is_active=true`;
- `CatalogCachedItemSearchView` может вернуть полный `limit` из кэша без запроса в SyncServer;
- если remote всё же вызван, merge-алгоритм ставит cached items первыми;
- отсутствие локального ID в ограниченной remote search-странице не рассматривается как tombstone;
- успешные Django BFF batch/delete/merge handlers не делают write-through invalidation этой строки.

Следовательно, возраст ghost entry сейчас не ограничен TTL.

### 🟠 F3. Нет consistency-контракта для operation picker

Один endpoint одновременно пытается быть быстрым поиском, fallback при недоступности SyncServer и источником валидных ID для warehouse write. Это разные требования.

Поле `source: cache|remote` уже присутствует в DTO, но picker его не использует для решения «можно ли выбрать item». Нет `stale`, `cache_age`, `catalog_revision` или результата authoritative validation.

### 🟠 F4. Перед save/submit обновляются остатки, но не item references

`OperationCreateModalComponent.refreshBeforePersist()` обновляет balances. Выбранные `item_id` повторно не проверяются, а merged-source не диагностируется как конфликт с canonical target.

Server-side reject обязателен и должен остаться последней защитой, но UI сейчас получает позднюю общую ошибку вместо предметного состояния строки.

### 🟡 F5. Межвкладочная актуальность не определена — P2 follow-up

После catalog mutation текущая nomenclature-вкладка перезагружает bootstrap, но другие вкладки и пользователи не получают сигнал. `BroadcastChannel` может улучшить same-browser UX, но не решает multi-user coherence; основное решение должно находиться в SyncServer/BFF. BroadcastChannel и proactive same-browser notifications не входят в P1.

### 🔴 F6. Save-intent может потеряться до отправки

`OperationCreateModalComponent.onSave()` и `onSubmit()` сначала ожидают `refreshBeforePersist()`, и только затем испускают `save`/`submit` в родительскую страницу. Флаг `OperationsService.isSaving` включается ещё позже — когда родитель уже получил событие и начал HTTP-запрос.

В этом окне:

- кнопка закрытия, поля формы и обе mutation-кнопки не заблокированы общим состоянием persist;
- пользователь может закрыть и уничтожить компонент до `output.emit()`;
- пользователь может изменить строки после снятия фактического snapshot;
- параллельные Save/Submit могут пройти разные preflight и отправить разные snapshots;
- успешный ответ родителя устанавливает `editingDraft` из snapshot, переданного при клике, и effect дочернего компонента способен затереть более поздние локальные изменения.

Баланс-запрос не должен находиться между кликом и фиксацией save-intent. Он может обновлять подсказки параллельно, но authoritative проверка остаётся на SyncServer.

### 🔴 F7. Full-replace строк выполняется без optimistic concurrency

`OperationsService.update_operation()` в SyncServer при наличии `lines` вызывает `delete_operation_lines()` и заново создаёт весь набор. Модель операции имеет и инкрементирует `version`, но:

- `OperationResponse` не возвращает `version`;
- Angular `OperationDto`/`OperationDraftVm` его не хранят;
- PATCH/submit не принимают `expected_version` или `If-Match`;
- второй запрос из старой вкладки или запоздавший повторный клик работает по принципу last-write-wins и может восстановить предыдущий состав.

Дополнительно update Angular разбит на PATCH состава и отдельный PATCH `effective-at`; Confirm разбит на create/update и последующий submit. При сбое второй части пользователь получает общую ошибку, хотя первая часть уже могла сохраниться. Для нового draft неуспешный submit не переносит созданный `id` обратно в modal state, поэтому повторная попытка способна создать ещё один draft. Стабильный idempotency key для обычного create отсутствует; для inline-create ключ генерируется заново на каждую сборку payload.

Текущие тесты проверяют успешный HTTP и in-memory строки после save, но не доказывают сценарий «добавить строку → сохранить → закрыть → повторно GET → сравнить состав», конфликт двух вкладок и закрытие во время preflight.

### 🔴 F8. Ошибка соединения имеет неопределённый outcome, а UI считает её обычным failure

HTTP/JSON не должен применить «частично дошедший PATCH»: оборванное или malformed тело не проходит JSON parsing. Но разрыв может случиться **после commit и до ответа**. Тогда Angular не знает, сохранена операция или нет.

Текущий контур не закрывает этот failure mode:

- Angular `BffApiService` не задаёт явный mutation timeout и не различает definite reject от ambiguous network outcome;
- status `0`, reset/timeout и BFF `502/504` сводятся к строке ошибки без recovery protocol;
- `OperationsService.loadBalances()` поглощает любую ошибку preflight, очищает balances и продолжает flow без предупреждения;
- Django имеет 10-секундные connect/read/write/pool timeouts по умолчанию;
- `Warehouse_web/apps/sync_client/transport.py` правильно не повторяет PATCH/POST автоматически, но после timeout не знает, успел ли SyncServer commit;
- Django `_handle_sync_error()` сводит SyncServer payload к `message/code` и не передаёт `fields`/mutation outcome, хотя Angular transport умеет принять `fields`;
- Django middleware выдаёт/возвращает `X-Request-Id`, однако Angular его не сохраняет и одного request ID недостаточно для идемпотентного повтора;
- error alert расположен в верхней части прокручиваемого modal body, тогда как Save/Confirm находятся в фиксированном footer; ошибка может появиться вне текущей видимой области без focus/scroll;
- существующая create-idempotency SyncServer применяется только когда payload содержит inline temporary item, а Angular генерирует новый ключ при новой сборке payload.

Следовательно, сообщения «сервер недоступен» и «не удалось сохранить» могут быть ложными: запись могла завершиться. Слепой повтор опасен дублем create или перезаписью строк.

## 5. Alternatives

| Вариант | Плюсы | Минусы | Verdict |
|---|---|---|---|
| Ничего не менять, советовать Ctrl+F5 | Нулевая стоимость | Ошибка данных остаётся; refresh может вернуть тот же ghost | Reject |
| Только Angular-кнопка с очисткой signals/Map | Быстро и заметно пользователю | Не очищает Django table и не исправляет SyncServer read-model | Reject как fix; допустимо только как UX-дополнение |
| Полностью отключить cache и всегда искать в SyncServer | Простая consistency-модель | Выше latency/нагрузка; нет graceful fallback | Допустимый emergency hotfix |
| TTL на `catalog_cache_item` | Ограничивает время устаревания | В течение TTL ghost всё равно selectable; TTL не обрабатывает merge | Недостаточно |
| Authoritative invariant + write-through invalidation + explicit fresh/validate contract | Устраняет первопричины, сохраняет быстрый поиск | Требует согласованных изменений трёх проектов | **Recommended** |

## 6. Recommended design

### 6.1. P0 — восстановить authoritative correctness

1. В SyncServer сделать soft-delete атомарным переходом: `deleted_at` всегда сопровождается `is_active=false`.
2. Все operational catalog reads независимо фильтруют `deleted_at IS NULL`, `is_active=true` и `merged_into_id IS NULL`; category/unit также должны быть usable.
3. Добавить безопасную one-time data remediation для уже существующих `deleted_at IS NOT NULL AND is_active=true` после backup и до cache rebuild.
4. Проверить старые review/temporary cancellation paths, а не только явный endpoint удаления review item.

### 6.2. P1 — определить BFF cache-coherence

**Write-through:** после успешных create/update/deactivate/delete/merge/batch в Django BFF:

- active target/create/update — upsert canonical snapshot;
- deactivate/delete/merged source — немедленно `is_active=false` в `catalog_cache_item`;
- merge target — upsert target;
- category/unit mutation, способная изменить доступность или отображение зависимых items, — invalidation поколения кэша или обязательный reconciliation зависимых строк;
- локальная cache update выполняется только после успешного ответа SyncServer.

**External writers:** write-through не видит изменения, сделанные другим клиентом напрямую через SyncServer. Поэтому нужен reconciliation:

- предпочтительно incremental change feed с monotonic sequence/catalog revision и tombstone/merge metadata;
- допустимый первый этап — полный active reconciliation, который помечает unseen local rows inactive **только после полностью успешного scan**;
- scan с ошибкой, `max_pages` или неполной пагинацией не имеет права массово инвалидировать записи.

Текущий `updated_after` можно использовать только после проверки cursor semantics для одинаковых timestamp и добавления достаточного состояния (`deleted_at`, `merged_into_id` или явный status). Иначе возможны пропуски.

### 6.3. P1 — разделить fast search и authoritative resolution

Для operation picker нужен явный контракт, например:

```http
GET /bff/api/v1/catalog/search/items?q=...&consistency=authoritative
```

Семантика:

- `authoritative`: BFF идёт в SyncServer, возвращает только usable items и прогревает/исправляет локальный кэш;
- `fast`: cache-first для некритичных lookup-сценариев;
- при недоступности SyncServer cached results могут отображаться с `stale=true`, но не должны становиться новой строкой операции без validation.

Для draft lines полезнее один batch-resolution endpoint, чем N запросов:

```http
POST /bff/api/v1/catalog/items/resolve
{
  "item_ids": [101, 202]
}
```

Ответ по каждому requested ID:

```json
{
  "requested_id": 101,
  "status": "active | merged | inactive | deleted | missing",
  "canonical_item_id": 303,
  "item": null
}
```

Источник этого решения — SyncServer service, не Django ORM. Для `merged` resolver следует до конечного target с cycle guard. Django только проксирует/агрегирует.

### 6.4. P1 — Angular «Обновить ТМЦ» как repair action

Кнопка уместна в модальном окне операции рядом с picker и должна:

1. отменить текущий search request/очистить `localResults`;
2. повторить текущий query в `authoritative` режиме;
3. batch-проверить уже добавленные постоянные `item_id`;
4. для `merged` показать source и canonical target, но в первом срезе не заменять автоматически;
5. для `merged/deleted/inactive/missing` подсветить строку, запретить save/submit и предложить пользователю явно удалить или заменить её;
6. не трогать inline draft payload, который ещё не материализован в item.

Если source и canonical target уже присутствуют в одном draft, нельзя молча создавать две строки одного target. UI показывает collision и оставляет сохранение заблокированным. Автоматическое объединение количеств не входит в первый срез.

Название лучше отражает действие: **«Обновить и проверить ТМЦ»**, а не «Очистить кэш».

Автоматически тот же resolver следует вызывать:

- после загрузки существующего draft;
- непосредственно перед save/submit;
- после server error класса `catalog_item_unusable`.

Между validation и write остаётся race. Это нормально: SyncServer повторяет проверку внутри транзакционного write-path, а Angular обрабатывает структурированную ошибку строки.

### 6.5. Error contract

Вместо общей строки `item does not exist` BFF должен сохранять структурированное состояние SyncServer, например:

```json
{
  "code": "catalog_item_unusable",
  "message": "Одна или несколько ТМЦ больше недоступны",
  "fields": {
    "lines.1.item_id": "deleted",
    "lines.3.item_id": "merged:303"
  }
}
```

Это не переносит бизнес-правила в Angular: UI только связывает authoritative error с конкретной строкой.

### 6.6. Observability

Минимальные метрики/логи без названий ТМЦ и без токенов:

- `catalog_search_requests_total{mode,source}`;
- `catalog_cache_result_age_seconds`;
- `catalog_cache_invalidations_total{reason}`;
- `catalog_item_resolution_total{status}`;
- `operation_write_rejected_total{code=catalog_item_unusable}`;
- `operation_mutation_outcome_total{command,result}` с `result=committed|rejected|unknown|reconciled`;
- `operation_mutation_replay_total{result=same_payload|payload_conflict}`;
- request ID через Angular → Django → SyncServer.

Если после P0/P1 reject остаётся, по request ID можно отличить stale cache, race и старый draft.

### 6.7. Два разных уровня принудительного обновления

#### A. Пользовательская команда в операции

Команда **«Обновить и проверить ТМЦ»** доступна кладовщику и работает только с текущим draft:

1. фиксирует неизменяемый snapshot текущих persisted `item_id`;
2. вызывает authoritative batch resolver через Django BFF;
3. очищает результаты текущего picker и повторяет введённый поиск в authoritative mode;
4. помечает каждую проблемную строку и блокирует Save/Submit;
5. не запускает полный rebuild общего Django-кэша и не требует административных прав;
6. не изменяет строки и количества автоматически.

Это быстрая repair/diagnostic операция, а не гарантия записи. Перед фактическим persist тот же resolver запускается автоматически; SyncServer повторяет проверку в транзакции.

#### B. Административная полная reconciliation

В Django уже есть SSR POST `nomenclature:ssr/cache/sync/` и кнопка «Обновить кэш поиска операций». Сейчас `CatalogCacheSyncService.sync_items()` только upsert-ит активные remote items, поэтому stale rows после delete/deactivate/merge переживают эту «синхронизацию».

В P1 административная команда должна называться **«Пересобрать кэш поиска ТМЦ»** и:

- быть доступна только chief/root через существующую server-side permission boundary;
- не использоваться кладовщиком как способ починить одну операцию;
- выполнять полный scan active items и собирать множество уникальных seen IDs;
- проверять complete-success: нет ошибки, нет `max_pages`, число уникальных seen IDs согласовано с `total_count`;
- только после complete-success помечать ранее active, но unseen строки inactive;
- возвращать `fetched/upserted/deactivated/skipped/duration`;
- блокировать повторный клик в текущем UI и логировать начало/завершение запуска;
- при ошибке сохранять безопасные upsert-ы, но не выполнять массовую деактивацию.

Пока измеренная длительность scan укладывается в HTTP budget, существующий POST остаётся синхронным. `run_id`, DB-backed lease/status и job runner относятся к P2 и нужны только при доказанной конкуренции запусков или превышении request budget. Fire-and-forget thread внутри Django worker не допускается.

Без snapshot/revision SyncServer остаётся race с catalog mutation во время scan. В P1 риск ограничивается write-through invalidation, complete-success guard и повторной проверкой `total_count`; целевой P2-вариант — monotonic catalog revision/change feed.

### 6.8. Persistence contract для Save и Confirm

Save-flow должен стать явной state machine:

```text
idle -> validating_items -> saving -> saved
                           -> error
                           -> conflict
```

Обязательные свойства:

1. Нажатие фиксирует immutable snapshot и переводит форму в busy **до первого await**.
2. Save-intent передаётся владельцу операции сразу; уничтожение modal не должно молча отменять ещё не испущенный output.
3. На время persist блокируются повторный Save, Confirm, редактирование и бесшумное закрытие. Закрытие либо запрещено, либо требует явного подтверждения отмены/ожидания.
4. `refreshBeforePersist()` не задерживает фиксацию intent. Balance refresh остаётся подсказкой; item resolver является явным precondition orchestration.
5. `OperationResponse` возвращает `version`; PATCH и submit требуют `expected_version`. Несовпадение даёт `409 operation_version_conflict`, не изменяя строки.
6. Полный draft, включая `effective_at`, сохраняется одним atomic SyncServer command. Отдельный endpoint изменения даты можно сохранить для post-submit privileged flow, но draft save не должен состоять из двух независимых записей.
7. Create получает стабильный `client_request_id` для каждого пользовательского save-intent и повторно использует его при сетевом retry. Идемпотентность нужна для всех draft, не только inline items.
8. Если Save выполнен, а отдельный Submit отклонён бизнес-правилом, UI принимает серверный `id/version/snapshot` и сообщает: «Черновик сохранён, подтверждение не выполнено: …». Повторная попытка не создаёт новый draft.
9. Success устанавливается только после authoritative response. UI показывает «Сохранено HH:MM» и сохраняет returned version; это evidence для пользователя, но не замена серверному контракту.
10. Перед закрытием после success допустим контрольный GET/fingerprint в диагностическом rollout-режиме; постоянный второй GET не нужен после доказательства корректности response/transaction.

Для Confirm предпочтителен один SyncServer `save-and-submit` command с `expected_version`, применяющий draft changes и submit в одной UoW. Если этот контракт откладывается, двухшаговый клиент обязан сохранять результат первого шага в modal state и явно различать `draft_saved` и `submitted`.

### 6.9. Протокол при обрыве Angular → Django → SyncServer

#### Классы исходов

| Наблюдение клиента | Интерпретация | Действие |
|---|---|---|
| `2xx` с валидным response | Commit подтверждён | Принять returned `id/version/fingerprint` |
| `4xx/409/422` со структурированной ошибкой | Запрос определённо отклонён | Показать field/conflict errors, не повторять автоматически |
| Browser status `0`, timeout, connection reset | Outcome неизвестен | Перейти в `checking_outcome`, не говорить «не сохранено» |
| BFF `502/504` после попытки write в SyncServer | Outcome консервативно неизвестен | P1: authoritative GET/version/fingerprint; P2: receipt; не выполнять blind retry |
| Ошибка client validation до HTTP | Запрос не отправлялся | Вернуть форму в editable state |

`navigator.onLine` может быть только подсказкой: он не доказывает доступность Django и не определяет outcome уже отправленной записи.

#### P1 — bounded recovery без mutation receipt

P1 использует уже существующие aggregate данные и не вводит отдельную таблицу receipts:

1. `OperationResponse` возвращает `version`.
2. Update и submit требуют `expected_version`; stale request получает 409 и не меняет строки.
3. Каждый create получает стабильный `client_request_id`, созданный один раз на save-intent и повторно используемый при retry. SyncServer распространяет существующую idempotency-проверку на **все** create, а не только inline item flow.
4. Angular хранит immutable snapshot и его canonical fingerprint до определённого результата.
5. Browser timeout явно настроен и превышает внутренний Django→SyncServer deadline с измеренным запасом. Timeout означает `unknown`, а не `failed`.

После ambiguous update Angular делает authoritative GET операции и сравнивает:

```text
intended fingerprint = ordered(item_id, qty, line_number) + editable operation fields
expected_version
current fingerprint
current version
```

- fingerprint совпал и version увеличилась — Save считается восстановленным;
- version не изменилась и fingerprint старый — можно предложить повтор PATCH с тем же snapshot и `expected_version`;
- version увеличилась, но fingerprint другой — операция была изменена конкурентно; показать conflict и не перезаписывать;
- GET недоступен — оставить состояние `outcome_unknown` и кнопку «Проверить ещё раз».

После ambiguous submit GET проверяет authoritative `status/version`: `submitted` означает успех, `draft` при ожидаемой версии допускает явный повтор, иная версия означает conflict. После ambiguous create клиент повторяет **тот же payload с тем же `client_request_id`**; SyncServer возвращает ранее созданную операцию либо создаёт её один раз.

Минимальная Angular state machine:

```text
saving -> saved | rejected | checking_outcome
checking_outcome -> saved_after_check | safe_to_retry | conflict | outcome_unknown
```

Сообщение «Соединение прервано. Проверяем, сохранилась ли операция…» выводится рядом с footer и переводит focus/scroll к detail. Django сохраняет структурированные `fields`, код ошибки и `X-Request-Id`; generic `sync_error` недостаточен. P1 не сохраняет полный operation payload в browser storage и не обещает offline editing.

#### P2 — mutation receipt и recovery после reload

Полноценный end-to-end `Idempotency-Key` для Create/Save/Save-and-Submit, SyncServer mutation receipt, outcome endpoint, bounded polling и `sessionStorage` pending metadata остаются целевым P2. Переход в P2 обоснован, если метрики покажут частые ambiguous outcomes, если одного aggregate GET/fingerprint недостаточно или потребуется recovery после reload.

P2 receipt должен обеспечивать unique `(actor_user_id, mutation_id)`, canonical request hash, same-payload replay, 409 для changed payload, actor-scoped lookup, retention и проверку receipt **до** optimistic version guard. Existing `machine_last_batch_id` не заменяет историю receipts.

## 7. Minimum valuable slice

Первый релиз не должен сразу строить полноценную event-driven cache platform. Достаточный срез:

1. SyncServer invariant/read filters + cleanup неконсистентных active-deleted items.
2. Версионный operation contract: response `version`, `expected_version`, атомарный draft update и стабильный `client_request_id` для всех create.
3. Django write-through invalidation и complete-success full reconciliation вместо upsert-only административной синхронизации.
4. `consistency=authoritative`/batch resolve для operation item search и validation.
5. Angular action «Обновить и проверить ТМЦ», блокировка unusable lines и persist state machine без pre-emit await.
6. Reopen-after-save, delayed-save и двухвкладочные Playwright-сценарии.

P2 включает mutation receipt/recovery после reload, monotonic catalog revision/change feed, tracked admin reconciliation job и BroadcastChannel. Эти механизмы вводятся только по данным метрик или при недостаточности P1 recovery.

## 8. Execution Strategy

**Рекомендуется последовательное выполнение.** Причина: сначала должны быть зафиксированы authoritative usability/resolve, version и idempotency contracts SyncServer; BFF и Angular зависят от них, а ошибка затрагивает production data correctness.

| Этап | Владелец файлов | Зависимость | Интеграционная точка |
|---|---|---|---|
| 1. Domain invariant, resolve, operation version и idempotent-create contracts | `SyncServer/app/services/`, repos, schemas/routes, tests | Нет | `/api/v1/catalog/*`, `/api/v1/operations/*` |
| 2. Cache invalidation/reconciliation и BFF proxies | `Warehouse_web/apps/catalog_cache/`, `apps/bff_api/`, tests | Этап 1 | `/bff/api/v1/catalog/*`, operation error/version passthrough |
| 3. Refresh/repair UX и persist state machine | `Warehouse_frontend/src/app/core/services/`, operations components, tests | Контракт этапа 2 | Angular service DTO/state |
| 4. Stand + UI acceptance | E2E specs и Docker stand | Этапы 1–3 | Полный Browser → BFF → SyncServer flow |

Для будущего Swarm максимальное полезное число потоков — **2**, и только после фиксации API: один поток на Django BFF/cache, второй на Angular fixtures/UI. SyncServer contract, data cleanup и итоговая интеграция выполняются последовательно.

Порядок тестов: SyncServer → Django → Angular build/component → stand integration → Playwright → regression.

## 9. Verification ladder для будущей реализации

| Уровень | Обязательная проверка |
|---|---|
| Static | Python lint/type checks по принятому проектом набору; Angular build/type check |
| SyncServer unit/integration | Soft-delete active review item делает inactive; browse/read исключает fixture `deleted_at != null, is_active=true`; merge resolution возвращает canonical target; stale `expected_version` не заменяет lines; successful update возвращает новый version/fingerprint; повтор create с тем же `client_request_id` и payload не создаёт дубль, changed payload даёт 409 |
| Django component/integration | Полный local-cache hit не возвращает invalidated item; delete/merge/batch делают write-through; неполный/failed reconciliation не prune-ит cache; полный reconcile деактивирует unseen; operation version и structured fields не теряются в proxy; write-timeout маппится в ambiguous outcome |
| Angular component | Refresh использует authoritative mode; deleted/merged line блокирует persist; inline line не валидируется как persisted item; busy начинается до preflight; close/double-click не теряют intent; submit failure сохраняет returned draft id/version; status 0/timeout запускает reconcile, а не показывает definite failure |
| Real stand smoke | Создать item → найти → deactivate/delete/merge → обновить picker → source отсутствует либо строка явно заблокирована → после явной замены draft сохраняется без `item not found`; повторный GET совпадает с save snapshot |
| Playwright | (1) добавить строки → Save → закрыть → открыть → exact line fingerprint совпадает; (2) задержать balances/preflight и сразу закрыть/нажать повторно — silent loss невозможен; (3) две вкладки одной операции — stale вкладка получает 409; (4) в A открыт draft со старым item, в B item merge/delete — refresh/Save даёт repair UX; (5) оборвать response после update commit — UI сверяет GET/fingerprint; потерянный create response не создаёт дубль при retry с тем же key |
| Regression | Обычный быстрый поиск, inline item flow, catalog batch, balances refresh, unavailable SyncServer fallback |

### 9.1. Существующее покрытие и оценка новых тестов

| Слой | Уже есть | Подтверждённый пробел | Ориентир новых cases |
|---|---|---|---:|
| SyncServer | `tests/test_operations_service_update.py`, `test_operations_effective_at_api.py`, `test_operations_service_cancel.py` и operation API/policy tests | Нет reopen/fingerprint после замены lines, optimistic conflict, idempotent create для обычных items и catalog ghost invariant | 9–11 |
| Django | `apps/catalog_cache/tests.py`, `apps/bff_api/tests.py` | Нет prune-after-complete-scan, failed-scan safety, write-through delete/merge и сохранения structured operation errors/version | 6–8 |
| Angular unit/component | `src/app/core/services/operations.service.spec.ts` | Нет pre-await busy, close/double-click safety, line-level resolver state, version conflict и timeout→GET recovery | 6–8 |
| Playwright | `operations-draft.spec.ts`, `operations-create-modal.spec.ts`, `operations-submit.spec.ts` | Draft проверяется в списке или в том же modal, но не exact reopen; нет двух вкладок, delayed preflight и lost-response recovery | 4–5 |

Итого для TZ следует планировать примерно **25–32 новых сфокусированных test cases**. Это оценка, а не обязательная квота: после фиксации API допускается объединить parameterized cases без потери evidence.

## 10. Acceptance criteria

1. Ни один catalog read для новых строк операции не возвращает `deleted_at != null`, inactive или merged-source item как selectable.
2. Успешная catalog mutation через Django перестаёт находиться в operation search без ручного rebuild процесса.
3. Refresh action не ограничивается очисткой Angular state: в network evidence виден authoritative BFF/SyncServer запрос.
4. Уже открытый draft диагностирует каждую устаревшую строку; merged source показывает canonical target и остаётся заблокированным до явной замены пользователем.
5. SyncServer по-прежнему отклоняет race-condition write и возвращает структурированный код/line errors.
6. Cache outage/degraded mode не превращает stale cached result в подтверждённый warehouse write.
7. После подтверждённого Save повторный GET той же операции возвращает тот же набор `item_id`, количеств и line order, который был в зафиксированном save snapshot.
8. Закрытие modal, двойной клик и задержанный preflight не могут привести к отсутствующему PATCH без явного сообщения пользователю.
9. Запрос со stale operation version получает 409 и не заменяет текущие строки предыдущим snapshot.
10. Если draft update успешен, а submit неуспешен, повторная попытка использует существующий operation ID; UI различает «сохранено» и «подтверждено».
11. Административная пересборка удаляет ghost rows только после complete-success scan; ошибочный/неполный scan ничего массово не деактивирует.
12. После потерянного update/submit response клиент проверяет authoritative GET/version/fingerprint и не выполняет blind overwrite.
13. Повтор create с тем же `client_request_id` и payload возвращает ту же операцию без дубля; повтор с изменённым payload получает 409.
14. В логах Angular/BFF/SyncServer один request ID и безопасный client request ID позволяют связать попытку и recovery без записи названий ТМЦ или payload.

## 11. Rollout and rollback

1. Сначала deploy обратно совместимые SyncServer response fields, idempotent create, version validation и catalog invariant/read filters. До включения обязательного `expected_version` старые клиенты работают в compatibility mode, но метрики помечают unversioned writes.
2. После backup выполнить audit/remediation active-deleted записей и только затем перестроить Django catalog cache.
3. Deploy Django authoritative mode/write-through/reconciliation и structured version/error passthrough, сохраняя прежнюю форму response для старого клиента на период rollout.
4. Deploy Angular refresh/repair UX, persist state machine и timeout→GET recovery; включить Playwright acceptance.
5. После подтверждённого adoption отключить unversioned operation writes. Не включать strict mode до проверки, что production Angular bundle обновлён.

При проблеме Angular action можно временно скрыть feature flag/конфигурацией, не откатывая server correctness. Откат data remediation допускается только из заранее проверенного backup; повторно активировать soft-deleted items автоматически нельзя. BFF remote-first можно временно заменить cache-first только при сохранении обязательного resolver перед write.

## 12. Risks and non-goals

| Риск | Митигация |
|---|---|
| Full reconciliation ошибочно удалит cache при частичном scan | Prune только после complete-success marker и проверки total/page count |
| Remote-first повысит latency | Debounce, pooled transport, batch resolve, измерить P95 до возврата к cache-first |
| Validation/save race | Финальная проверка остаётся в SyncServer transaction path |
| Merge chain/cycle | Resolver следует chain с depth limit и cycle detection |
| Source и target уже есть в draft | Явный collision UX; не дублировать и не суммировать строки незаметно |
| Несколько Django instances | Точкой coherence остаётся общая Django DB; process-local signals не являются решением |
| Старые production данные уже неконсистентны | Backup, отдельный audit query/remediation, cache rebuild после исправления invariant |
| Запоздавший Save из вкладки перезаписывает свежий | `expected_version`, atomic compare-and-update, 409 conflict UX |
| Modal закрыт до фактического emit | Busy до первого await; persist orchestration принадлежит живущему дольше parent/service |
| Update сохранился, submit упал | Принять returned draft state и явно показать partial lifecycle outcome; не повторять create |
| Full reconcile запущен параллельно | В P1 UI блокирует повтор и операции остаются convergent; при реальной multi-worker конкуренции поднять P2 с DB lease/run ID |
| Update/submit commit прошёл, response потерян | P1: authoritative GET + version/fingerprint; P2 при необходимости: mutation receipt |
| Create commit прошёл, response потерян | Повтор exact payload с тем же `client_request_id` возвращает existing operation |
| Browser timeout короче backend deadline | Явная согласованная deadline policy; любой timeout всё равно трактуется как ambiguous |
| Один create key случайно использован с новым payload | Canonical request hash и 409 idempotency conflict |
| Пользователь перезагрузил страницу во время unknown outcome | P1 не обещает восстановление несохранённого payload; receipt/session recovery относится к P2 |
| Операция изменилась после ambiguous commit | Сравнить intended fingerprint/current version; не накатывать старый snapshot на новый |
| Долгий admin reconcile не укладывается в HTTP budget | Не усложнять P1 заранее; при подтверждённом превышении вынести в P2 job runner с run status |

Вне первого среза: offline-клиенты, замена HTTP/JSON, прямой доступ Django к SyncServer DB, WebSocket/event-bus для каталога, общий Redux/store rewrite Angular.

## 13. Evidence reviewed

| Область | Источник |
|---|---|
| Functional requirement | `Functional and WorkLogik.md`, II.5.0, II.8 |
| Angular picker | `Warehouse_frontend/src/app/features/operations/components/item-cache-search/item-cache-search.component.ts` |
| Angular search service | `Warehouse_frontend/src/app/core/services/catalog-search.service.ts` |
| Angular pre-persist refresh | `Warehouse_frontend/src/app/features/operations/components/operation-create-modal/operation-create-modal.component.ts` |
| Angular save/submit orchestration | `Warehouse_frontend/src/app/features/operations/pages/operations-page/operations-page.component.ts`, `core/services/operations.service.ts` |
| Django cached search | `Warehouse_web/apps/bff_api/catalog_views.py::CatalogCachedItemSearchView` |
| Django cache storage/sync | `Warehouse_web/apps/catalog_cache/models.py`, `services.py` |
| Existing admin cache action | `Warehouse_web/apps/catalog/views.py::CatalogCacheSyncView`, `templates/catalog/manage_workspace.html` |
| SyncServer operation guard | `SyncServer/app/services/operations_service.py::_ensure_item_usable` |
| SyncServer full-replace update | `SyncServer/app/services/operations_service.py::update_operation`, `app/repos/operations_repo.py::delete_operation_lines` |
| Missing version API contract | `SyncServer/app/models/operation.py`, `app/schemas/operation.py::OperationResponse`, Angular `operations.models.ts` |
| Transport timeouts/retry policy | `Warehouse_web/apps/sync_client/transport.py`, `client.py`, Angular `core/api/bff-api.service.ts` |
| Request tracing | `Warehouse_web/apps/common/middleware.py::RequestTracingMiddleware` |
| Cancel cleanup path | `SyncServer/app/services/operations_service.py::_delete_temporary_items_of_operation` |
| Soft-delete behavior | `SyncServer/app/repos/catalog_repo.py::soft_delete_item` |
| Catalog read filters | `SyncServer/app/repos/catalog_repo.py::list_items_page`, `get_item_read_model` |
| Architecture boundary | `docs/adr/0011-django-syncserver-internal-transport-hardening.md` |

## 14. Decision packaging

Review остаётся в `docs/reviews/` как evidence и не должен быть переименован в ADR. После принятия направления решения лучше зафиксировать двумя сфокусированными ADR, потому что каталог и operation persistence имеют разные инварианты и rollback:

1. **ADR-0018 — Catalog item usability and BFF cache coherence:** soft-delete invariant, authoritative/fast modes, write-through и complete-success reconciliation.
2. **ADR-0019 — Operation draft mutation consistency:** response `version`, `expected_version`, atomic draft update, idempotent create и P1 timeout→GET recovery; mutation receipt явно deferred в P2.

Номера `0012`–`0017` уже заняты. После acceptance ADR единый исполнимый TZ может связать оба решения последовательными этапами SyncServer → Django → Angular, не смешивая их acceptance criteria.

## 15. Review limitations

- Production не исследовался, секреты и production DB не читались.
- Точный commit запущенной старой production-версии не подтверждён.
- Runtime/stand-тесты не выполнялись: это source-level architecture review, а не реализация.
- Skill `architecture-review` в текущем окружении недоступен; stress-test выполнен вручную по границам source of truth, failure modes, race conditions, rollout, observability и test ladder.
