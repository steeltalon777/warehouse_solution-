# Архитектурное ревью: Angular UI-диагностика складских операций

**Дата:** 2026-07-15  
**Автор:** Системный архитектор (agent)  
**Статус:** Черновик ревью — без изменений кода  
**Версия фронтенда:** `3.2-angular` (заголовок `X-Warehouse-Client`)

---

## Содержание

- [1. Executive Summary](#1-executive-summary)
- [2. Текущая архитектура Angular-фронтенда](#2-текущая-архитектура-angular-фронтенда)
- [3. Фактический поток создания операции (receive)](#3-фактический-поток-создания-операции-receive)
- [4. Найденные точки риска](#4-найденные-точки-риска)
- [5. Текущая обработка ошибок](#5-текущая-обработка-ошибок)
- [6. Текущая HTTP-инфраструктура](#6-текущая-http-инфраструктура)
- [7. Состояние формы и черновики](#7-состояние-формы-и-черновики)
- [8. Анализ нагрузки на браузер](#8-анализ-нагрузки-на-браузер)
- [9. Рекомендуемая минимальная архитектура диагностики](#9-рекомендуемая-минимальная-архитектура-диагностики)
- [10. Схема событий](#10-схема-событий)
- [11. Batch-отправка и очередь](#11-batch-отправка-и-очередь)
- [12. Предлагаемые backend endpoints](#12-предлагаемые-backend-endpoints)
- [13. Разделение ответственности: audit, diagnostics, drafts](#13-разделение-ответственности-audit-diagnostics-drafts)
- [14. План внедрения по этапам](#14-план-внедрения-по-этапам)
- [15. Список файлов, которые потребуется изменить](#15-список-файлов-которые-потребуется-изменить)
- [16. Риски и открытые вопросы](#16-риски-и-открытые-вопросы)

---

## 1. Executive Summary

### Может ли операция реально потеряться на фронтенде?

**Да, но нужно различать три разных ситуации:**

1. **Операция не была создана** — действительно потеря данных (ошибка сети на этапе create, отсутствие идемпотентности).
2. **Операция создана, но не подтверждена** — черновик есть, submit не прошёл (ошибка сети, таймаут).
3. **Операция создана и подтверждена, но список не обновился** — это НЕ потеря данных, а ошибка отображения результата. Операция существует в SyncServer, но пользователь её не видит в журнале.

Для кладовщика все три выглядят как «всё пропало», но архитектурно это разные аварии с разными решениями.

### Ключевое ограничение ревью

Часть находок — это **потенциальные проблемы**, достижимость которых не доказана через call-site анализ. Перед превращением ревью в ТЗ нужна проверка всех call sites. Конкретно: `saveAndSubmit()` имеет **0 вызовов** за пределами сервиса (подтверждено `grep`-ом) — это технический долг, а не причина текущих жалоб.

### Главные находки

| # | Критичность | Суть | Достижимость |
|---|-------------|------|--------------|
| 1 | **BLOCKER** | `client_request_id` (idempotency key) генерируется заново при каждом вызове `createOperation` — повторная отправка после таймаута создаст дубликат операции | **Подтверждена** — `buildPayload` всегда вызывает `_newClientRequestId()` на строке 814 |
| 2 | **HIGH** | После успешного submit интерфейс не показывает надёжное подтверждение с `operation_id`. При ошибке `loadList()` пользователь не знает, была ли операция проведена | **Подтверждена** |
| 3 | **HIGH** | `onConfirmSubmit` закрывает confirm-модал до проверки успешности обновления списка, а при ошибке — модал создания уже закрыт, сообщение об ошибке невидимо | **Подтверждена** |
| 4 | **MEDIUM** | `onDraftSubmit` закрывает модал после успешного submit, но до завершения `loadList()`. Это ошибка отображения, а не потери данных (операция уже в SyncServer) | **Подтверждена** |
| 5 | **MEDIUM** | Нет `CanDeactivate` guard, нет `beforeunload`, нет подтверждения при закрытии модала — черновик молча теряется | **Подтверждена** |
| 6 | **MEDIUM** | Пустые `catch`-блоки в операциях (cancel, delete, restore, edit) — ошибка видна только через перезаписываемый `service.error`, пользователь может не заметить | **Подтверждена** |
| 7 | **LOW** | Метод `saveAndSubmit` поглощает ошибку submit (`catch { setPersist('saved') }`) — но **не вызывается** ни из одного компонента | **Технический долг**, не причина жалоб |
| 8 | **MEDIUM** | Нет сквозного `correlation_id` для связи логов фронтенда и бэкенда | **Подтверждена** |

### Правильная реакция на успешный submit

Не «удерживать модал до обновления списка» (это подтолкнёт пользователя нажать кнопку повторно), а:

```text
submit успешно вернул operation_id
→ показать «Операция №1234 проведена»
→ закрыть форму или перевести в read-only
→ обновить список
→ если список не загрузился — показать:
  «Операция №1234 сохранена, но журнал не обновился. Обновите страницу.»
```

### Исправленный план (переупорядочен)

**Этап 0 (срочно):** Исправить контракт результата: показывать `operation_id` после успеха, не путать ошибку `loadList()` с ошибкой submit.  
**Этап 1:** Идемпотентность и `outcome_unknown`: idempotency key один на черновик, поиск результата по ключу, запрет слепого повтора.  
**Этап 2:** Correlation ID: `session_id`, `tab_id`, `draft_id`, `idempotency_key`, `http_request_id`, `server_request_id`, `frontend_version`.  
**Этап 3:** Минимальная UI-диагностика (10 семантических событий).  
**Этап 4:** Защита черновика: `CanDeactivate`, `beforeunload`, автосохранение.

### Ожидаемая нагрузка диагностики

Реалистичная оценка (не волшебная арифметика):

- 200 событий в памяти: ~100–500 KB (JavaScript-объекты занимают больше сериализованного JSON)
- Batch из 20 событий: ~10–40 KB по сети
- Отправка раз в 15 секунд — ~1 запрос
- CPU: пренебрежимо (все операции вне Angular Zone)

Что всё равно совершенно нормально для рабочей станции.

---

## 2. Текущая архитектура Angular-фронтенда

### 2.1 Базовая информация

| Параметр | Значение |
|----------|---------|
| Angular | **21.2.0** |
| TypeScript | ~5.9.2 |
| RxJS | ~7.8.0 |
| NgRx | **отсутствует** |
| Архитектура компонентов | **Standalone** (нет NgModules) |
| Bootstrap | `bootstrapApplication` (`main.ts`) |
| Сборка | `@angular/build:application` (esbuild-based) |
| Тесты | Vitest для unit, Playwright для e2e |
| CSS | SCSS с shared tokens (`_tokens.scss`) |

### 2.2 State Management

Проект использует **Angular Signals** как основной механизм реактивного состояния:

- `signal<T>()` — для мутабельного локального состояния
- `computed<T>()` — для производных значений
- `effect()` — для побочных эффектов (загрузка балансов, синхронизация `submitError`)
- `input.required<T>()` / `output<T>()` — для взаимодействия parent-child

**RxJS используется только в сервисах для HTTP-запросов** (`firstValueFrom`, `Observable` в `CatalogSearchService`). Никаких `BehaviorSubject`, `Subject` для UI-состояния нет (кроме `searchQuery$` в `CatalogSearchService`).

**NgRx отсутствует.** Store-паттерн реализован через `@Injectable({providedIn: 'root'})` сигнал-сервисы.

### 2.3 Change Detection

- **Zone.js:** Подключён (стандартно для Angular). В конфигурации нет `provideExperimentalZonelessChangeDetection()`.
- **ChangeDetectionStrategy.OnPush:** **НЕ используется.** Все компоненты на `ChangeDetectionStrategy.Default`.
- Все компоненты используют сигналы в шаблонах (`{{ signal() }}`), что обеспечивает частичную оптимизацию даже без OnPush.

### 2.4 Структура feature-модулей

```
src/app/
├── core/
│   ├── api/
│   │   ├── api.service.ts          — /nomenclature/api/* (легаси, только каталог)
│   │   └── bff-api.service.ts      — /bff/api/v1/* (основной BFF-клиент)
│   ├── guards/
│   │   └── catalog-write.guard.ts  — только для nomenclature
│   ├── logging/
│   │   ├── global-error-handler.ts — ErrorHandler
│   │   ├── http-error.interceptor.ts — HTTP error interceptor
│   │   └── logging.spec.ts
│   ├── models/
│   │   ├── operations.models.ts    — DTO, VM, типы операций
│   │   ├── nomenclature.models.ts
│   │   ├── auth.models.ts и др.
│   ├── pipes/
│   │   └── min.pipe.ts
│   └── services/
│       ├── operations.service.ts   — CRUD и список операций
│       ├── auth-context.service.ts — контекст пользователя
│       ├── catalog-search.service.ts — поиск ТМЦ
│       ├── catalog-admin.service.ts
│       ├── catalog-change-buffer.service.ts
│       ├── documents.service.ts
│       └── ... прочие сервисы
├── features/
│   ├── operations/
│   │   ├── pages/
│   │   │   ├── operations-page/          — страница журнала операций
│   │   │   ├── operation-acceptance-page/
│   │   │   └── pending-acceptance-page/
│   │   ├── components/
│   │   │   ├── operation-create-modal/   — модал создания/редактирования
│   │   │   ├── operation-confirm-modal/  — модал подтверждения
│   │   │   ├── operations-table/
│   │   │   ├── operations-filter-panel/
│   │   │   ├── operations-status-tabs/
│   │   │   ├── item-cache-search/
│   │   │   └── inline-item-create-modal/
│   │   └── services/
│   │       └── acceptance.service.ts
│   ├── nomenclature/
│   ├── temporary-items/
│   ├── issued-assets/
│   └── lost-assets/
├── shared/
│   └── components/
│       └── error-alert/
├── app.ts          — корневой standalone-компонент
├── app.config.ts   — ApplicationConfig с провайдерами
├── app.routes.ts   — ленивые маршруты
└── app.html        — шаблон: <div class="warehouse-spa"><router-outlet /></div>
```

### 2.5 Маршруты операций

```typescript
// app.routes.ts
{ path: 'operations',                          loadComponent: OperationsPageComponent },
{ path: 'operations/:operationId/acceptance',  loadComponent: OperationAcceptancePageComponent },
{ path: 'operations/pending-acceptance',       loadComponent: PendingAcceptancePageComponent },
{ path: 'operations/lost-assets',              ... },
{ path: 'operations/lost-assets/:operationLineId', ... },
```

Все компоненты загружаются лениво (lazy-loaded). **Нет CanDeactivate guard.**

### 2.6 Feature flags и конфигурация

**Отсутствуют.** Нет глобального конфигурационного сервиса, нет feature flags, нет удалённой конфигурации. Единственный условный механизм — проверка `role` и `permissions` через `AuthContextService`.

---

## 3. Фактический поток создания операции (receive)

### 3.1 Пошаговая трассировка

#### Шаг 0: Открытие страницы

```
Файл:      app.routes.ts
Метод:     routes[3] — loadComponent: OperationsPageComponent
```

#### Шаг 1: Инициализация страницы

```
Файл:      operations-page.component.ts
Метод:     ngOnInit()
Строки:    345-348
Действие:  - service.loadSites()
           - void this.loadList()
```

#### Шаг 2: Нажатие «Создать операцию»

```
Файл:      operations-page.component.ts
Метод:     onCreateClick()
Строки:    411-419
Действие:  - editingDraft.set({ type: 'MOVE', status: 'draft', ... })
           - createModalSubmitError.set('')
           - showCreateModal.set(true)
```

#### Шаг 3: Отображение модала создания

```
Файл:      operation-create-modal.component.ts
Селектор:  app-operation-create-modal
Условие:   @if (showCreateModal()) — строка 117 шаблона родителя
```

#### Шаг 4: Модал инициализирует локальный черновик

```
Файл:      operation-create-modal.component.ts
Метод:     constructor() — effect
Строки:    954-961
Действие:  effect(() => { if (draft) localDraft.set(normalizeDraftForType(...)) })
```

#### Шаг 5: Пользователь меняет тип на RECEIVE

```
Файл:      operation-create-modal.component.ts
Метод:     onTypeModelChange()
Строки:    1064-1070
Действие:  normalizeDraftForType('RECEIVE', ...)
           → sourceSiteId = null, destinationSiteId = preferredSiteId
```

#### Шаг 6: Пользователь выбирает склад (destination)

```
Файл:      operation-create-modal.component.ts
Метод:     onLogicalWarehouseSiteChange()
Строки:    1076-1081
Действие:  type === 'RECEIVE' → destinationSiteId = value
```

#### Шаг 7: Автоматическая загрузка балансов (effect)

```
Файл:      operation-create-modal.component.ts
Метод:     constructor() — effect (строки 963-1002)
Триггер:   изменение relevantSiteId() (destinationSiteId для RECEIVE)
Действие:  service.loadBalances(siteId).then(() => refreshSourceQuantities())
```

#### Шаг 8: Пользователь ищет и добавляет ТМЦ

```
Файл:      operation-create-modal.component.ts
Метод:     onNewItemSelected()
Строки:    1189-1216
Действие:  localDraft.update(d => ({ ...d, lines: [...d.lines, newLine] }))
           itemSearch?.reset()
```

- Поиск: `item-cache-search.component.ts`
- Сервис поиска: `catalog-search.service.ts` → BffApiService → `/bff/api/v1/catalog/search/items`
- Поиск дебаунсится 150ms (`debounceTime(150)`)

#### Шаг 9: Пользователь вводит количество

```
Файл:      operation-create-modal.component.ts
Метод:     onQuantityChange()
Строки:    1229-1236
Действие:  localDraft.update(...)
```

Передаётся через `OperationLinesTableComponent.onQtyChange() → quantityChange.emit()`.

#### Шаг 10: Клиентская валидация (реактивная)

```
Файл:      operation-create-modal.component.ts
Метод:     saveDisabledReason() — computed
Строки:    697-725
Проверки:  - lines.length > 0
           - все позиции имеют itemId или inlineItem
           - все количества > 0
           - склад указан для типа операции
           - lineAvailableQtyError() для каждой строки
           - writeOffSource для WRITE_OFF
           - issueObjectId для ISSUE
```

Кнопка «Сохранить черновик» задизейблена при `saveDisabledReason()`.  
Кнопка «Подтвердить» задизейблена при `!canSubmitComputed()`.

#### Шаг 11: Пользователь нажимает «Сохранить черновик»

```
Файл:      operation-create-modal.component.ts
Метод:     onSave()
Строки:    1238-1242
Действие:  await refreshBeforePersist()  — перезагружает балансы
           save.emit(localDraft())       — output в родителя
```

#### Шаг 12: Родительский компонент обрабатывает сохранение

```
Файл:      operations-page.component.ts
Метод:     onDraftSave()
Строки:    672-694
Действие:
  1. draft.id ? updateOperation(draft.id, draft) : createOperation(draft)
  2. При успехе: editingDraft.set(mergeDraftAfterSuccessfulSave(...))
  3. void loadList() — обновление списка
  4. При ошибке: createModalSubmitError.set(message)
```

#### Шаг 13: API-вызов сохранения

```
Файл:      operations.service.ts
Метод:     createOperation() (или updateOperation)
Строки:    208-238
Действие:
  1. isSaving.set(true), error.set(null)
  2. buildPayload(draft, ...) — преобразование в DTO
  3. payload['client_request_id'] = _newClientRequestId()  // crypto.randomUUID()
  4. firstValueFrom(bff.postData('/operations', payload))
  5. При успехе: setPersist('saved'), return result
  6. В finally: isSaving.set(false)
```

#### Шаг 14: HTTP-вызов

```
Файл:      bff-api.service.ts
Метод:     postData() → post()
Строки:    61-73
Действие:
  1. POST /bff/api/v1/operations
  2. withCredentials: true
  3. Заголовки: Content-Type, X-CSRFToken, X-Warehouse-Client: 3.2-angular
  4. timeout: 30_000 ms
  5. catchError(this.handleError)
```

#### Шаг 15: Пользователь нажимает «Подтвердить»

```
Файл:      operation-create-modal.component.ts
Метод:     onSubmit()
Строки:    1248-1252
Действие:  await refreshBeforePersist()
           submit.emit(localDraft())
```

#### Шаг 16: Родитель обрабатывает submit

```
Файл:      operations-page.component.ts
Метод:     onDraftSubmit()
Строки:    696-714
Действие:
  1. Сначала сохраняет (create/update)
  2. Потом submitOperation(result.id)
  3. **Безусловно**: showCreateModal.set(false), editingDraft.set(null)
  4. void loadList()
  5. При ошибке: createModalSubmitError.set(message)
```

#### Шаг 17: API submit

```
Файл:      operations.service.ts
Метод:     submitOperation()
Строки:    286-313
Действие:
  1. isSubmitting.set(true)
  2. POST /bff/api/v1/operations/{id}/submit { submit: true }
  3. В finally: isSubmitting.set(false)
```

### 3.2 Визуальная схема потока

```text
Пользователь                     Angular                            Django BFF              SyncServer
    │                              │                                    │                       │
    │─ Открывает /operations       │                                    │                       │
    │                              │─ loadSites() ─────────────────────>│                       │
    │                              │─ loadList() ──────────────────────>│── GET /operations ────>│
    │─ «Создать операцию»          │                                    │                       │
    │                              │─ showCreateModal = true            │                       │
    │─ Выбирает RECEIVE            │                                    │                       │
    │─ Выбирает склад              │                                    │                       │
    │                              │─ loadBalances(siteId) ────────────>│── GET /balances ──────>│
    │─ Добавляет ТМЦ               │                                    │                       │
    │                              │─ searchItemsOnce ─────────────────>│── GET /catalog/search─>│
    │─ Вводит количество           │                                    │                       │
    │─ «Сохранить черновик»        │                                    │                       │
    │                              │─ createOperation(draft)            │                       │
    │                              │  ┌─ buildPayload()                │                       │
    │                              │  ├─ POST /bff/api/v1/operations ──>│── POST /api/v1/ops ──>│
    │                              │  └─ firstValueFrom()              │<── 201 Created ────────│
    │                              │─ editingDraft.set(savedDraft)     │                       │
    │                              │─ loadList() ──────────────────────>│                       │
    │─ «Подтвердить»               │                                    │                       │
    │                              │─ submitOperation(id)               │                       │
    │                              │  └─ POST .../{id}/submit ─────────>│── POST .../submit ───>│
    │                              │                                    │<── 200 OK ────────────│
    │                              │─ showCreateModal.set(false) ⚠️     │                       │
    │                              │─ editingDraft.set(null)    ⚠️     │                       │
    │─ Видит обновлённый список    │─ loadList() ──────────────────────>│                       │
```

---

## 4. Найденные точки риска

### Проблема 1: Отсутствие идемпотентности — новый client_request_id при каждом вызове

```text
ID:            RISK-001
Критичность:   BLOCKER
Файл:          operations.service.ts
Строки:         814 (buildPayload), 133-139 (_newClientRequestId), 208-238 (createOperation)
Методы:        buildPayload(), createOperation()
Текущее поведение:
  buildPayload() для новых операций (isCreate: true) всегда генерирует
  новый client_request_id через _newClientRequestId() (строка 814).
  В createOperation (строка 216) есть проверка:
    payload['client_request_id'] = payload['client_request_id'] || this._newClientRequestId();
  Но поскольку buildPayload уже установил новый UUID, запасной вызов
  _newClientRequestId() никогда не срабатывает.
  
  Итого: каждый вызов createOperation получает новый idempotency key.
Риск:
  - Таймаут 30 с → сервер мог создать операцию, ответ не дошёл
  - Пользователь видит ошибку, нажимает «Подтвердить» повторно
  - Создаётся ДУБЛИКАТ операции (новый client_request_id — сервер
    не распознаёт это как повтор того же бизнес-действия)
  - Идемпотентность, предусмотренная TZ C5, фактически не работает
Как воспроизвести:
  1. Начать создание операции, нажать «Подтвердить»
  2. Дождаться таймаута 30 с (обрыв сети на стороне клиента)
  3. Нажать «Подтвердить» повторно после восстановления сети
  4. В SyncServer две операции с разными client_request_id
Рекомендация:
  - Idempotency key должен создаваться ОДИН раз при создании черновика
    (или при первом createOperation) и храниться в draft.idempotencyKey
  - Повторные попытки (включая автоматические) используют тот же ключ
  - После operation_outcome_unknown фронтенд должен:
    1. Запросить операцию по client_request_id (GET /operations?client_request_id=X)
    2. Если найдена — показать результат
    3. Если не найдена — повторить createOperation с ТЕМ ЖЕ ключом
    4. Не создавать новую операцию с новым ключом
```

### Проблема 1a: Интерфейс не показывает operation_id после успешного submit

```text
ID:            RISK-001a
Критичность:   HIGH
Файл:          operations-page.component.ts
Строки:         696-714
Метод:         onDraftSubmit()
Текущее поведение:
  После успешного submitOperation() модал закрывается (стр. 703-704),
  но пользователю НЕ показывается идентификатор созданной операции.
  Затем void loadList() вызывается без await (стр. 706).
  
  Если loadList() упадёт (сеть):
  - Модал уже закрыт
  - Пользователь не знает, была ли операция создана
  - Никакого подтверждения с operation_id нет
Риск:
  - Это НЕ потеря данных (операция уже в SyncServer)
  - Это ошибка отображения: пользователь не видит результата
  - Важно: НЕ следует удерживать модал открытым до loadList() —
    это подтолкнёт пользователя нажать кнопку повторно и создаст дубликат
Как воспроизвести:
  1. Создать операцию, нажать «Подтвердить»
  2. Сразу после ответа сервера оборвать сеть
  3. Модал закрыт, список пуст, пользователь думает что операция потерялась
Рекомендация (правильная):
  - После успешного submit показать toast: «Операция №1234 проведена»
  - Закрыть или перевести форму в read-only
  - Обновить список
  - Если список не загрузился: «Операция №1234 сохранена, но журнал не обновился. Обновите страницу.»
  - НЕ удерживать модал открытым в ожидании loadList()
```

### Проблема 2: saveAndSubmit — технический долг (не вызывается)

```text
ID:            RISK-002
Критичность:   LOW (технический долг, не причина текущих жалоб)
Файл:          operations.service.ts
Строки:         320-349
Метод:         saveAndSubmit()
Текущее поведение:
  catch { this.setPersist('saved'); } — ошибка submit глотается,
  persistState переводится в 'saved' без дополнительной информации.
  
  Однако grep по всему src/ показывает: saveAndSubmit() имеет
  ровно 0 вызовов за пределами сервиса. Этот код недостижим
  из текущих компонентов.
Риск:
  - При будущем использовании — ошибка submit будет скрыта
  - Сейчас — не влияет на пользователей
Рекомендация:
  - НЕ является срочным исправлением
  - При рефакторинге: вернуть структуру с явным флагом submit_succeeded
  - Или удалить метод, если он не потребуется в обозримом будущем
```

### Проблема 3: onConfirmSubmit закрывает модал до проверки

```text
ID:            RISK-003
Критичность:   HIGH
Достижимость:  Подтверждена (путь из UI достижим)
Файл:          operations-page.component.ts
Строки:         823-841
Метод:         onConfirmSubmit()
Текущее поведение:
  showConfirmModal.set(false) — строка 829
  showCreateModal.set(false)  — строка 830
  editingDraft.set(null)      — строка 831
  Выполняется ДО loadList()
  При ошибке: createModalSubmitError.set(message) — но модал уже закрыт
  Далее showConfirmModal.set(false) повторно на строке 839
Риск:
  - Submit прошёл, список НЕ обновился
  - При ошибке: сообщение устанавливается в createModalSubmitError,
    но модал создания уже закрыт — пользователь не видит ошибку
  - Двойной вызов showConfirmModal.set(false) — логическая ошибка
Как воспроизвести:
  1. Открыть операцию из таблицы → confirm-модал → «Подтвердить»
  2. Если loadList упадёт — ошибка не видна нигде
Рекомендация:
  - После успешного submit: зафиксировать успех, показать operation_id
  - Закрыть confirm-модал **независимо** от загрузки списка
  - Затем попытаться обновить список
  - При сбое списка — показать отдельный warning (не ошибку submit)
  - Убрать дублирующий set(false) в catch
  - НЕ удерживать confirm-модал до loadList() — это подтолкнёт
    пользователя нажать кнопку повторно
```

### Проблема 4: Повторная отправка после таймаута без проверки

```text
ID:            RISK-004
Критичность:   HIGH (в связке с RISK-001 — BLOCKER)
Файл:          operations-page.component.ts
Строки:         696-714
Метод:         onDraftSubmit()
Текущее поведение:
  При ошибке (включая operation_outcome_unknown при таймауте)
  модал НЕ закрывается (showCreateModal.set(false) — только при успехе).
  Строки 703-704 выполняются только после успешного await submitOperation.
  
  Это правильное поведение для ветки ошибки.
  
  НО: в сочетании с RISK-001 (новый client_request_id) возникает:
  1. Сервер мог обработать запрос
  2. Клиент получил timeout → operation_outcome_unknown
  3. Пользователь видит ошибку, модал остаётся открытым
  4. Пользователь нажимает повторно
  5. Создаётся дубликат (новый client_request_id)
Риск:
  - Дубликат операции при повторной отправке после таймаута
  - В отличие от ошибочного утверждения в ранней версии ревью,
    черновик НЕ удаляется при ошибке — проблема именно в дублировании
Как воспроизвести:
  1. Нажать «Подтвердить»
  2. Дождаться таймаута 30 с
  3. Нажать «Подтвердить» повторно
  4. Две операции с одинаковым содержимым
Рекомендация:
  - При status='outcome_unknown' показывать явное предупреждение:
    «Результат неизвестен. Проверьте список операций. Не создавайте повторно.»
  - Блокировать повторный submit до ручного сброса
  - Внедрить идемпотентность (RISK-001) — тогда повторная отправка безопасна
```

### Проблема 5: Отсутствие защиты от ухода со страницы

```text
ID:            RISK-005
Критичность:   MEDIUM
Достижимость:  Подтверждена (легко воспроизвести)
Файл:          отсутствует
Метод:         отсутствует
Текущее поведение:
  - Нет CanDeactivate guard на маршрутах операций
  - Нет window.addEventListener('beforeunload', ...)
  - При переходе по боковому меню или закрытии вкладки —
    несохранённый черновик теряется без предупреждения
Риск:
  - Кладовщик заполнил форму на 20+ позиций, случайно нажал на меню
  - Вся работа потеряна
Как воспроизвести:
  1. Открыть создание операции, добавить 5 позиций
  2. Нажать на пункт меню «Номенклатура»
  3. Черновик потерян, предупреждения нет
Рекомендация:
  - Добавить CanDeactivate guard на основе hasUnsavedChanges()
  - Добавить beforeunload при наличии несохранённых изменений
  - Рассмотреть автосохранение в sessionStorage (см. раздел 7)
```

### Проблема 6: Двойной submit

```text
ID:            RISK-006
Критичность:   MEDIUM
Файл:          operation-create-modal.component.ts
Строка:         297 (шаблон)
Текущее поведение:
  [disabled]="!canSubmitComputed() || isSubmitting()"
  isSubmitting сбрасывается в finally сервисного метода.
  Между сбросом isSubmitting(false) и фактическим завершением
  обработки ответа в onDraftSubmit может быть окно для повторного клика.
Риск:
  - Теоретически возможен двойной submit при быстром двойном клике
  - Усугубляется тем, что модал не закрывается сразу при ошибке
Как воспроизвести:
  Сложно воспроизвести, но архитектурно уязвимость существует
Рекомендация:
  - Добавить локальный флаг isSubmittingLocal, который сбрасывается
    только после полного завершения обработки в родителе
  - Использовать css pointer-events: none на время отправки
```

### Проблема 7: Множественные subscribe без обработки error (каталог-сервис)

```text
ID:            RISK-007
Критичность:   LOW (не влияет напрямую на создание операций)
Файл:          catalog-search.service.ts
Строки:         140-147 (refreshItemsAuthoritative)
                176-179 (initItemSearch)
Текущее поведение:
  .subscribe(response => { ... }) — без обработки error
  (error перехвачен catchError выше, но теоретически ошибка в самом
  callback response-handler не будет обработана)
Риск:
  - Ошибка в момент записи в signal после успешного HTTP
  - В отличие от операций, здесь последствия минимальны
Рекомендация:
  - Добавить error callback в subscribe или использовать
    наблюдаемый подход с finalize
```

### Проблема 8: Очистка формы при смене маршрута

```text
ID:            RISK-008
Критичность:   MEDIUM
Файл:          operation-create-modal.component.ts
Текущее поведение:
  Черновик хранится в памяти компонента (localDraft signal).
  При уничтожении компонента (смена маршрута через router.navigate)
  состояние теряется.
  При закрытии модала через cancel.emit() — editingDraft.set(null)
  в родителе — также полная потеря.
Риск:
  - Пользователь случайно закрыл модал (клик по оверлею, Esc)
  - Черновик безвозвратно потерян
Как воспроизвести:
  1. Заполнить форму
  2. Нажать Esc или кликнуть по серому фону
  3. Модал закрыт, черновик потерян
Рекомендация:
  - Добавить подтверждение при закрытии модала с несохранёнными данными
  - Сохранять черновик в sessionStorage при закрытии
```

### Проблема 9: loadBalances молча глотает ошибки

```text
ID:            RISK-009
Критичность:   LOW
Файл:          operations.service.ts
Строки:         534-545
Метод:         loadBalances()
Текущее поведение:
  catch { this.balances.set([]); } — ошибка загрузки балансов
  полностью замолчена. Пользователь не знает, что данные о наличии
  неактуальны.
Риск:
  - При spice/expense операциях количество может превысить доступное
  - Ошибка обнаружится только на сервере при submit
Рекомендация:
  - Логировать событие диагностики при ошибке загрузки балансов
```

### Проблема 10: Отсутствие request_id / correlation_id

```text
ID:            RISK-010
Критичность:   MEDIUM
Файл:          bff-api.service.ts, operations.service.ts
Текущее поведение:
  - client_request_id генерируется фронтендом (crypto.randomUUID())
  - Но он НЕ отправляется в заголовках, только в теле POST-запроса
  - Серверный request_id не извлекается из ответа и не сохраняется
  - Невозможно связать фронтенд-логи с бэкенд-логами
Риск:
  - При жалобе пользователя невозможно восстановить цепочку:
    «запрос ушёл → сервер обработал → ответ вернулся»
  - Есть только client_request_id в теле, но нет сквозной трассировки
Рекомендация:
  - Добавить заголовок X-Request-Id на фронтенде
  - Извлекать X-Request-Id из ответа сервера
  - Логировать связку (client_request_id, server_request_id)
```

---

## 5. Текущая обработка ошибок

### 5.1 Global Error Handler

```typescript
// global-error-handler.ts
@Injectable()
export class GlobalErrorHandler implements ErrorHandler {
  handleError(error: unknown): void {
    const message = error instanceof Error ? error.message : String(error);
    const stack = error instanceof Error ? (error.stack?.slice(0, 500) ?? '') : '';
    console.error('[GlobalError]', message, stack);
    throw error;  // re-throw
  }
}
```

**Вывод:** Только `console.error`. Ошибка перевыбрасывается — в production попадёт в `window.onerror`. Никакой отправки на сервер, никакой очереди.

### 5.2 HTTP Error Interceptor

```typescript
// http-error.interceptor.ts — Functional interceptor
export const httpErrorInterceptor: HttpInterceptorFn = (req, next) => {
  const start = performance.now();
  return next(req).pipe(
    catchError((error: HttpErrorResponse) => {
      const errorCode = error.error?.error?.code ?? 'unknown';
      console.error('[HTTP]', req.method, req.urlWithParams, error.status, `${durationMs}ms`, errorCode);
      return throwError(() => error);
    })
  );
};
```

**Вывод:** Логирует только ошибки. Успешные запросы **не логируются**.  
Нет извлечения `request_id` из ответа (даже успешного).  
Перевыбрасывает原始的 `HttpErrorResponse` — downstream обработчики (BffApiService.handleError) парсят заново.

### 5.3 BffApiService.handleError

```typescript
// bff-api.service.ts, строки 143-190
private handleError(error: any) {
  // TimeoutError → operation_outcome_unknown
  // error.error?.error → парсинг ApiResponse
  // error.status === 0 → syncserver_unavailable
  // error.status === 403 → forbidden
  // error.status === 404 → not_found
  return throwError(() => ({ code, message, fields, current_version, request_id, status, retry_safe }));
}
```

**Вывод:** Нормализует ошибки в структуру `{ code, message, ... }`.  
**Но:** извлекает `request_id` из тела ошибки, но НЕ из заголовков ответа.  
**Но:** не извлекает request_id из успешного ответа.

### 5.4 Операционные методы (сервис)

```typescript
// operations.service.ts — normalizeError
private normalizeError(err: any): void {
  const message = err?.message || 'Произошла ошибка';
  this.error.set(message);
  if (err?.fields) {
    console.error('Validation errors:', err.fields);
    this.fieldErrors.set(err.fields);
  } else {
    this.fieldErrors.set(null);
  }
}
```

**Вывод:** Устанавливает `error` signal. При наличии `fields` пишет `console.error`.  
Используется **не во всех методах** — `loadSites`, `loadBalances`, `getOperation` используют его, но `loadList` и CRUD — да.

### 5.5 Обработка ошибок в компонентах

#### operations-page.component.ts

- `onDraftSave` (стр. 672): catch устанавливает `createModalSubmitError`
- `onDraftSubmit` (стр. 696): catch устанавливает `createModalSubmitError`, модал НЕ закрывается
- `onConfirmSubmit` (стр. 823): catch устанавливает `createModalSubmitError`, но модал УЖЕ закрыт (проблема RISK-003)
- `onDraftDelete` (стр. 765): catch — пустой блок, ошибка только в `service.error`
- `onRowCancel` (стр. 507): catch — пустой блок
- `onRowEdit` (стр. 488): catch — пустой блок
- `onDraftRestore` (стр. 796): catch — пустой блок

**Вывод:** Множество пустых catch-блоков. Ошибка «уходит» в `service.error`, но:
- `service.error` перезаписывается каждым новым вызовом
- Никакой очереди ошибок нет — предыдущая ошибка теряется
- Пользователь может не заметить мигающий error-баннер

### 5.6 Что пользователь сейчас МОЖЕТ НЕ увидеть

| Тип ошибки | Видимость | Причина |
|------------|-----------|---------|
| Ошибка loadList после submit | ❌ Не видна | Модал закрыт, ошибка в `service.error`, но пользователь уже на другой странице или смотрит на пустой список |
| Ошибка loadBalances | ❌ Не видна | catch { this.balances.set([]) } — молча |
| Ошибка валидации на сервере (422) | ⚠️ Частично | `fieldErrors` устанавливается, но только если модал ещё открыт |
| Таймаут 30 с | ✅ Видна | `operation_outcome_unknown` → `createModalSubmitError`. Модал **не закрывается** — пользователь видит ошибку и может попытаться снова (что при отсутствии идемпотентности ведёт к дубликату — RISK-001) |
| Ошибка сети (status 0) | ✅ Видна | `syncserver_unavailable` → error signal |
| 403 Forbidden | ✅ Видна | `forbidden` → error signal |
| 500 Internal Server Error | ✅ Видна | `unexpected_error` → error signal |

---

## 6. Текущая HTTP-инфраструктура

### 6.1 BffApiService

| Параметр | Значение |
|----------|---------|
| Базовый URL | `/bff/api/v1` |
| Таймаут мутаций | 30 000 ms (POST/PUT/PATCH/DELETE) |
| GET-запросы | Без таймаута |
| CSRF | Кука `csrftoken` → заголовок `X-CSRFToken` |
| Авторизация | Сессионная (withCredentials: true) |
| Заголовки | `X-Warehouse-Client: 3.2-angular` |

### 6.2 Interceptors

Единственный interceptor: `httpErrorInterceptor` (функциональный).

**Отсутствуют:**
- Interceptor для добавления `X-Request-Id`
- Interceptor для извлечения `X-Request-Id` из ответа
- Retry-interceptor
- Token-refresh interceptor
- Дедупликация запросов (нет `shareReplay`, нет `take(1)` на уровне HTTP)
- Audit/logging interceptor для всех запросов

### 6.3 Обработка ответа

```typescript
// bff-api.service.ts
postData<T>(path, body): Observable<T> {
  return this.post<T>(path, body).pipe(map(res => res.data as T));
}
```

- Ответ ожидается в формате `BffApiResponse<T>`: `{ ok: boolean, data?: T, error?: {...} }`
- Успешный ответ разворачивается до `data`
- Ошибочный ответ парсится в `handleError`
- Заголовки ответа (включая `X-Request-Id`) **не читаются**

### 6.4 Куда добавить диагностические заголовки

Место: `BffApiService.getMutationHeaders()` и отдельный метод для чтения ответа.

```typescript
// Рекомендуемые заголовки (добавлять в getMutationHeaders):
'X-Warehouse-Client': '3.2-angular'        // уже есть
'X-Client-Session-Id': '<session_uuid>'     // новый
'X-Client-Request-Id': '<crypto.randomUUID()>' // новый (на каждый запрос)
'X-Frontend-Version': '<git-sha>'           // новый (из окружения сборки)

// Рекомендуемые заголовки ответа (читать из response.headers):
'X-Request-Id'                               // существующий или новый
```

**Idempotency key** имеет смысл для запросов создания/обновления черновика. Уже передаётся в теле запроса как `client_request_id` — должен быть один на черновик и переиспользоваться при повторах.

### 6.5 Nginx и передача заголовков

Nginx (в конфигурации Docker) должен быть настроен на проброс кастомных заголовков. Без явной проверки конфигурации nginx невозможно гарантировать. Однако стандартная конфигурация `proxy_pass` пробрасывает большинство заголовков.

---

## 7. Состояние формы и черновики

### 7.1 Форма

| Параметр | Значение |
|----------|---------|
| Тип формы | **Template-driven** (`ngModel`, `ngModelChange`) |
| Хранение | В памяти: `localDraft` signal в `OperationCreateModalComponent` |
| Сериализация | Нет. Состояние теряется при уничтожении компонента |
| Autosave | **Отсутствует** |
| Восстановление | **Отсутствует** |

### 7.2 Хранение в браузере

- `localStorage`: **не используется**
- `sessionStorage`: **не используется**
- `IndexedDB`: **не используется**

Единственное постоянное хранилище — куки (CSRF-токен, сессия Django).

### 7.3 Защита от ухода

- `CanDeactivate`: **отсутствует**
- `beforeunload`: **отсутствует**
- Подтверждение при закрытии модала: **отсутствует** (кнопка «×» закрывает без подтверждения)

### 7.4 Dirty-check

Реализован в `operation-draft-mappers.ts`:

```typescript
// snapshotDraft(draft) → JSON-строка
// isDraftClean(draft)  → сравнение с lastSavedSnapshot
```

`hasUnsavedChanges` computed в модале сравнивает текущий draft со снепшотом.  
**Но:** этот флаг не используется ни для CanDeactivate, ни для beforeunload, ни для предупреждения при закрытии модала.

### 7.5 Очистка черновика

Черновик очищается в следующих случаях:
1. `onDraftSubmit()` — строка 703-704: `showCreateModal.set(false)`, `editingDraft.set(null)` — **после успешного submit**
2. `onDraftCancel()` — строка 760-763: модал закрывается, черновик очищается **без подтверждения**
3. `onDraftDelete()` — строка 765-776: явное удаление с `confirm()`
4. Смена маршрута — молча, при уничтожении компонента

**Критическое наблюдение:** Черновик очищается после успешного submit (стр. 703), но ДО того, как `loadList()` подтвердит, что операция появилась в списке. Это архитектурная гонка.

### 7.6 Возможность лёгкого автосохранения

**Оценка:** Добавить автосохранение относительно просто.

Предлагаемый подход:
- Подписаться на `localDraft` через `effect()` 
- При изменении (debounce 2 с) сохранять в `sessionStorage`
- При открытии модала — проверять `sessionStorage` и предлагать восстановление
- Очищать `sessionStorage` после успешного submit

Не смешивать с диагностическим логированием. Это отдельная подсистема.

### 7.7 Объекты, подлежащие сериализации

Черновик `OperationDraftVm` сериализуется в JSON для `sessionStorage`.  
**Нельзя сохранять:**
- Функции, Observable, Promise
- DOM-элементы
- Ссылки на сервисы

Текущая структура `OperationDraftVm` полностью сериализуема (только примитивы, строки, числа, массивы, вложенные объекты).

---

## 8. Анализ нагрузки на браузер

### 8.1 Оценка текущей нагрузки

| Метрика | Значение | Примечание |
|---------|----------|-----------|
| Размер бандла операций | ~88 kB (lazy chunk) | Приемлемо |
| Количество сигналов на странице | ~25 | В разумных пределах |
| RxJS подписок | ~5 (catalogSearch + operations) | Управляется через destroy$ |
| HTTP-запросов при открытии | 2 (sites + list) | Приемлемо |
| HTTP-запросов при работе с модалом | 1 (balances) + поиск | Дебаунс 150 мс |

### 8.2 Оценка дополнительной нагрузки от диагностики

Реалистичная оценка (JavaScript-объекты занимают больше сериализованного JSON):

| Компонент | Нагрузка | Обоснование |
|-----------|----------|-------------|
| Создание события | ~0.01 мс | Создание plain-объекта |
| Сериализация события (JSON) | ~0.05 мс | Объект ~300–1500 байт |
| 200 событий в памяти | ~100–500 KB | JS-объекты с замыканиями и строками |
| Batch из 20 событий (JSON) | ~10–40 KB по сети | Реальные JSON-объекты, не магические цифры |
| IndexedDB (опционально) | ~50–200 KB | 1000 событий |
| Влияние на change detection | ~0% | События вне зоны Angular (runOutsideAngular) |
| CPU при 1000 событий/час | <0.1% | Пакетная обработка, редкие срабатывания |

**Вывод:** Даже с реалистичными цифрами (не «волшебная арифметика» 4 KB на 200 событий) нагрузка пренебрежимо мала и не нуждается в оптимистичном преуменьшении для обоснования.

### 8.3 Принципы снижения нагрузки

1. **Запуск вне Angular Zone** — `NgZone.runOutsideAngular()` для очереди и отправки
2. **Нет глубокого клонирования** — только вычисляемые поля события, не весь черновик
3. **Пакетная отправка** — не чаще 10–15 с
4. **Ограниченная очередь** — макс. 200 в памяти
5. **Нет MutationObserver** — события создаются в явных точках кода
6. **Нет Session Replay** — на начальных этапах

---

## 9. Рекомендуемая минимальная архитектура диагностики

### 9.1 Архитектурный принцип

Диагностика реализуется как **автономный сервис**, не связанный с UI-состоянием:

```text
┌──────────────────────────────────────────────────────────┐
│                    Angular Application                    │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │ Components  │  │  Services    │  │ Diagnostics    │  │
│  │ (emit       │─▶│  (emit       │─▶│ Service        │  │
│  │  events)    │  │   events)    │  │                │  │
│  └─────────────┘  └──────────────┘  │ ┌────────────┐ │  │
│                                      │ │ Queue      │ │  │
│                                      │ │ (memory)   │ │  │
│                                      │ └────────────┘ │  │
│                                      │ ┌────────────┐ │  │
│                                      │ │ Sender     │ │  │
│                                      │ │ (batch)    │ │  │
│                                      │ └────────────┘ │  │
│                                      └────────────────┘  │
└──────────────────────────────────────────────────────────┘
                         │
                         ▼
              POST /bff/api/v1/diagnostics/ui-events/batch
                         │
                         ▼
              ┌─────────────────────┐
              │  Django BFF /       │
              │  SyncServer         │
              │  diagnostics table  │
              └─────────────────────┘
```

### 9.2 Базовый режим (всегда включён)

События:
- `submit_clicked`
- `submit_succeeded`
- `submit_failed`
- `request_failed` (только критические HTTP-ошибки)
- `validation_failed`
- `unexpected_error`
- `draft_lost` (переход без сохранения)
- `form_opened` / `form_closed`

### 9.3 Расширенный режим (feature flag)

Дополнительные события:
- `draft_autosaved` / `draft_restored`
- `items_changed` (сводка: N добавлено, M удалено)
- `request_started` / `request_succeeded`
- `navigation_away_with_unsaved`
- `balance_load_failed`
- `search_performed`

Активация:
- feature flag из Django BFF (`/bff/api/v1/config`)
- для конкретного `user_id`
- для конкретного `device_id`
- на ограниченное время (TTL 24 ч)
- автоматически после первой ошибки

---

## 10. Схема событий

### 10.1 DTO модели

```typescript
// diagnostics.models.ts (новый файл)

export type DiagnosticEventType =
  | 'form_opened'
  | 'form_closed'
  | 'draft_created'
  | 'draft_loaded'
  | 'draft_autosaved'
  | 'draft_restored'
  | 'draft_lost'
  | 'items_changed'
  | 'validation_failed'
  | 'balance_load_failed'
  | 'submit_clicked'
  | 'submit_succeeded'
  | 'submit_failed'
  | 'request_started'
  | 'request_succeeded'
  | 'request_failed'
  | 'response_processing_failed'
  | 'navigation_away_with_unsaved'
  | 'unexpected_error';

export type DiagnosticSeverity = 'debug' | 'info' | 'warning' | 'error' | 'critical';

export interface DiagnosticEventVm {
  // Обязательные
  event_id: string;            // crypto.randomUUID()
  event_type: DiagnosticEventType;
  occurred_at: string;         // ISO 8601
  session_id: string;          // сессия браузера (генерируется при старте)
  frontend_version: string;    // из environment / git describe

  // Контекстные (nullable)
  route?: string;              // текущий URL, напр. '/operations'
  operation_type?: string;     // 'RECEIVE' | 'MOVE' | ...
  draft_id?: string;           // UUID черновика (создаётся при открытии формы)
  idempotency_key?: string;    // Idempotency-Key бизнес-команды (один на черновик)
  http_request_id?: string;    // X-Client-Request-Id конкретного HTTP-запроса
  server_request_id?: string;  // X-Request-Id из заголовка ответа сервера
  user_id?: string;
  device_id?: string;          // из auth-контекста
  site_id?: string;
  tab_id?: string;             // идентификатор вкладки браузера

  // Мета
  severity: DiagnosticSeverity;

  // Детали (опционально, ограниченного размера)
  details?: DiagnosticEventDetails;
}

export interface DiagnosticEventDetails {
  // Общие
  items_count?: number;
  invalid_items_count?: number;
  duration_ms?: number;

  // HTTP
  http_method?: string;
  http_url?: string;
  http_status?: number;
  error_code?: string;
  error_message?: string;      // усечённое до 200 символов

  // Форма
  draft_status?: string;       // 'draft' | 'submitted' | 'cancelled'
  has_unsaved_changes?: boolean;

  // Причина
  reason?: string;             // краткое описание, до 500 символов

  // Дополнительно (только расширенный режим)
  stack_trace_snippet?: string; // первые 300 символов стека
}

export interface DiagnosticEventBatchVm {
  events: DiagnosticEventVm[];
  sent_at: string;             // ISO 8601
  sequence: number;            // монотонно возрастающий номер batch
}
```

### 10.2 Что НЕ логировать

- Каждый символ, каждое нажатие клавиши
- Движения мыши
- Полное содержимое формы (включая `lines` с названиями, количествами, ценами)
- Полные тела ответов сервера
- Токены, пароли, сессионные куки
- Персональные данные (`personName` полностью, адреса, телефоны)
- Скриншоты (Session Replay — только на отдельном этапе)

### 10.3 Ограничения размера

| Поле | Максимальный размер |
|------|---------------------|
| `details.error_message` | 200 символов |
| `details.reason` | 500 символов |
| `details.stack_trace_snippet` | 300 символов |
| Весь `details` | 2 KB |
| Одно событие целиком | 4 KB |
| Batch (20 событий) | 80 KB |

### 10.4 Приоритеты событий

| Приоритет | Типы событий | Отправка |
|-----------|-------------|----------|
| Critical | `submit_failed`, `unexpected_error` | Немедленно |
| Error | `request_failed`, `response_processing_failed` | В ближайшем batch |
| Warning | `validation_failed`, `draft_lost`, `navigation_away_with_unsaved` | Batch |
| Info | `submit_clicked`, `submit_succeeded`, `form_opened`, `draft_created` | Batch |
| Debug | `request_started`, `items_changed`, `search_performed` | Только в расширенном режиме |

---

## 11. Batch-отправка и очередь

### 11.1 Архитектура очереди

```typescript
// diagnostics-queue.service.ts (новый файл)

@Injectable({ providedIn: 'root' })
export class DiagnosticsQueueService {
  private queue: DiagnosticEventVm[] = [];
  private maxQueueSize = 200;
  private flushInterval = 15_000; // 15 с
  private maxBatchSize = 20;
  private sequence = 0;
  
  // Инициализация: setInterval на flush
  // beforeunload: sendBeacon для критических событий
}
```

### 11.2 Правила

| Правило | Значение |
|---------|----------|
| Максимум в памяти | 200 событий |
| При переполнении | Удаляются старые debug-события, critical сохраняются |
| Batch-интервал | 15 с (настраиваемый) |
| Досрочная отправка | При накоплении 20 событий |
| Критические события | Форсировать flush очереди через 250–500 мс (не мгновенно — чтобы несколько связанных ошибок ушли одной пачкой и не устроили шторм запросов) |
| При закрытии страницы | `navigator.sendBeacon()` — **best effort**, не гарантирует доставку. Batch обрезается до ~60 KB (лимит `keepalive`). Приоритет: critical/error, остальное разрешено потерять |
| Обычный flush | `fetch()` **без** `keepalive` — размер batch до 100 KB не ограничен лимитами `keepalive` (~64 KiB) |
| Backoff при ошибках | Экспоненциальный: 1с, 2с, 4с, 8с, макс. 30с |
| Максимум retry | 3 попытки на batch |
| Дедупликация | По `event_id` (НЕ по `client_request_id` — один request_id может иметь несколько событий: `submit_clicked`, `request_started`, `request_failed`, `retry_started`, `request_succeeded`). Повторяющиеся `items_changed` агрегировать отдельно |
| Защита логгера | При ошибке самого логгера — `console.error` и прекращение работы. **Критически важно:** HTTP interceptor НЕ должен логировать ошибки diagnostic-запросов — иначе рекурсия: ошибка отправки логов → interceptor создаёт `request_failed` → новая отправка → снова ошибка. Диагностические batch-запросы отправлять через отдельный низкоуровневый `fetch()`-клиент, минуя общие interceptors |

### 11.3 IndexedDB: нужна ли на первом этапе?

**Нет, не нужна.** Аргументы:

1. Критические события отправляются в ближайшем batch-интервале
2. `sendBeacon()` при закрытии страницы — best effort, но потеря нескольких некритичных событий при закрытии вкладки допустима для UI-диагностики
3. Объём данных минимален — потеря 15 с некритичных событий приемлема
4. IndexedDB добавляет сложность (асинхронность, миграции, коррупция хранилища)

IndexedDB может быть добавлена на **Этапе 4** если будут доказательства систематической потери событий.

### 11.4 Отправка в обход interceptors

**Критически важно:** диагностические batch-запросы должны отправляться через отдельный низкоуровневый `fetch()`-клиент, **минуя** Angular `HttpClient` и общие interceptors. Иначе возникает рекурсия:

```text
отправка логов упала
→ httpErrorInterceptor создаёт request_failed
→ diagnosticsService пытается отправить новый лог
→ новая ошибка
→ httpErrorInterceptor создаёт request_failed
→ ...
```

Решение:

```typescript
// diagnostics-queue.service.ts
private async sendBatch(events: DiagnosticEventVm[]): Promise<void> {
  const response = await fetch('/bff/api/v1/diagnostics/ui-events/batch', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': this.readCsrfToken(),
    },
    credentials: 'same-origin',
    body: JSON.stringify({ events, sent_at: new Date().toISOString(), sequence: this.sequence }),
    // keepalive НЕ используется для обычного flush — размер batch может превышать лимит ~64 KiB
  });
  if (!response.ok) throw new Error(`Diagnostics endpoint returned ${response.status}`);
}

// При закрытии вкладки — sendBeacon с ограниченным размером:
private flushOnUnload(): void {
  const critical = this.queue.filter(e => e.severity === 'critical' || e.severity === 'error');
  const payload = JSON.stringify({ events: critical, sent_at: new Date().toISOString(), sequence: this.sequence });
  if (payload.length > 60_000) {
    // Обрезать по приоритету, остальное разрешено потерять
    critical.length = Math.floor(critical.length * 60_000 / payload.length);
  }
  navigator.sendBeacon('/bff/api/v1/diagnostics/ui-events/batch', JSON.stringify({ events: critical, ... }));
}
```

### 11.5 Выполнение вне Angular Zone

```typescript
// diagnostics-queue.service.ts
constructor(private zone: NgZone) {
  this.zone.runOutsideAngular(() => {
    this.flushTimer = setInterval(() => this.flush(), this.flushInterval);
  });
}
```

Все операции с очередью, таймерами и отправкой выполняются вне Angular Zone, не вызывая change detection.

---

## 12. Предлагаемые backend endpoints

### 12.1 Приём событий

```text
POST /bff/api/v1/diagnostics/ui-events/batch
Content-Type: application/json

Request body: DiagnosticEventBatchVm
Response: 204 No Content
```

### 12.2 Конфигурация диагностики (для Django BFF)

```text
GET /bff/api/v1/diagnostics/config
Response: {
  enabled: boolean,
  extended_mode: boolean,
  extended_until: "2026-07-16T00:00:00Z" | null,
  sample_rate: 1.0
}
```

### 12.3 Требования к endpoint

| Требование | Значение |
|------------|----------|
| Авторизация | Django сессия (same-origin) |
| Макс. размер batch | 100 KB |
| Rate limiting | 10 запросов/мин на сессию |
| Обработка | Синхронная (bulk insert в PostgreSQL). При нагрузке в несколько тысяч событий в час отдельная очередь (Redis/Celery) не нужна. Ответ: `204 No Content` (пакет принят и записан) или `200 OK` с `{ accepted: N }`. **Не** `202 Accepted` — обработка синхронная, не отложенная |
| Таблица | `diagnostics_ui_events` |
| Индексы | `(session_id, occurred_at)`, `(event_type, occurred_at)`, `(draft_id)` |
| TTL | 30 дней (автоочистка) |
| Валидация event_type | Только из enum |
| Версионирование | Поле `schema_version` в batch (начинается с 1) |
| Отключение приёма | Через конфигурацию. При отключении endpoint возвращает `204 No Content` и отбрасывает пакет. **Не** `503` — иначе клиент начнёт backoff/retry, думая что сервер временно недоступен |

### 12.4 Связь с backend audit log

Связь через три идентификатора:

```text
UI idempotency_key  ↔  operation.client_request_id   (бизнес-команда)
UI http_request_id  ↔  BFF/SyncServer request context (конкретный HTTP-вызов)
UI server_request_id ↔  backend audit_log.request_id  (обработка на сервере)
```

Для восстановления цепочки «нажатие кнопки → HTTP-запрос → результат» нужны все три.

### 12.5 Хранение (Django/SyncServer)

**Рекомендация:** Отдельная таблица в PostgreSQL (не в SyncServer).

```sql
CREATE TABLE diagnostics_ui_events (
    id BIGSERIAL PRIMARY KEY,
    event_id UUID NOT NULL UNIQUE,
    event_type VARCHAR(50) NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    session_id UUID NOT NULL,
    tab_id UUID,
    frontend_version VARCHAR(50),
    route VARCHAR(200),
    operation_type VARCHAR(20),
    draft_id UUID,              -- создаётся при открытии формы
    idempotency_key UUID,       -- Idempotency-Key бизнес-команды (один на черновик)
    http_request_id UUID,       -- X-Client-Request-Id конкретного HTTP-запроса
    server_request_id UUID,     -- X-Request-Id из заголовка ответа сервера
    user_id VARCHAR(50),
    device_id VARCHAR(50),
    site_id VARCHAR(50),
    severity VARCHAR(20) NOT NULL,
    details JSONB,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    batch_sequence INTEGER,
    schema_version INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX idx_diag_events_session_time ON diagnostics_ui_events (session_id, occurred_at);
CREATE INDEX idx_diag_events_type_time ON diagnostics_ui_events (event_type, occurred_at);
CREATE INDEX idx_diag_events_draft ON diagnostics_ui_events (draft_id) WHERE draft_id IS NOT NULL;
CREATE INDEX idx_diag_events_idempotency ON diagnostics_ui_events (idempotency_key) WHERE idempotency_key IS NOT NULL;
-- Обычный индекс для TTL-очистки
CREATE INDEX idx_diag_received_at ON diagnostics_ui_events (received_at);
```

Очистка — заданием (cron/pg_cron), порциями по 20 000 строк. В PostgreSQL `DELETE` не поддерживает `LIMIT` напрямую, поэтому через подзапрос или CTE:

```sql
DELETE FROM diagnostics_ui_events
WHERE id IN (
    SELECT id
    FROM diagnostics_ui_events
    WHERE received_at < NOW() - INTERVAL '30 days'
    ORDER BY received_at
    LIMIT 20000
);
```

Порционная очистка предотвращает длительные блокировки таблицы.

---

## 13. Разделение ответственности: audit, diagnostics, drafts

| Измерение | Business Audit | UI Diagnostics | Draft Recovery |
|-----------|---------------|---------------|-----------------|
| **Назначение** | Что изменилось в системе | Что пытался сделать пользователь | Восстановить форму |
| **Где создаётся** | SyncServer (бэкенд) | Angular (фронтенд) | Angular + browser storage |
| **Данные** | Полные бизнес-сущности | Семантические события | Сериализованный черновик |
| **Хранение** | Постоянное (годы) | Краткосрочное (30–60 дней) | До подтверждения операции |
| **Триггер** | Совершение бизнес-действия | UI-события, HTTP, ошибки | Изменение формы, закрытие |
| **Связь** | `audit_log.request_id` | `client_request_id` → `server_request_id` | Не связан напрямую |
| **Пример** | «Операция #123 создана пользователем 5» | «Кнопка submit нажата, request_id=X» | `sessionStorage['draft_v1']` |
| **Регуляция** | Всегда включён | Базовый всегда, расширенный — feature flag | Всегда |
| **Чувствительные данные** | Бизнес-данные (ограниченный доступ) | НЕ содержит чувствительных данных | Только операторские данные того же пользователя |

### Категорическое правило

**Эти три подсистемы не заменяют друг друга:**

- Если операция не создалась в SyncServer — audit не поможет, нужна diagnostics
- Если пользователь потерял черновик — diagnostics покажет «почему», но не восстановит данные — нужно draft recovery
- Если операция создалась, но с ошибкой — diagnostics покажет путь ошибки, audit покажет результат

---

## 14. План внедрения по этапам

### Этап 0. Исправление контракта результата операции (1–2 дня)

**Срочно.** Отделить save, submit и refresh списка. Без диагностики.

- [ ] **RISK-001a** — После успешного submit показывать `operation_id`: «Операция №1234 проведена»
- [ ] **RISK-001a** — Не закрывать модал до показа `operation_id`; после показа — закрыть или перевести в read-only
- [ ] **RISK-001a** — При ошибке `loadList()` после успешного submit: показать «Операция №1234 сохранена, но журнал не обновился»
- [ ] **RISK-003** — Исправить порядок в `onConfirmSubmit`: закрывать confirm после показа результата
- [ ] **RISK-006** — Добавить обработку ошибок во все пустые catch-блоки (cancel, delete, restore, edit)
- [ ] Проверить все call sites `saveAndSubmit()` — подтверждено 0 вызовов, добавить `@deprecated` или исправить контракт

### Этап 1. Идемпотентность и outcome_unknown (1–2 дня)

- [ ] **RISK-001** — Idempotency key создаётся один раз при создании черновика и хранится в `draft.idempotencyKey`
- [ ] **RISK-001** — Повторные вызовы `createOperation` используют тот же ключ
- [ ] **RISK-001** — После `operation_outcome_unknown`: GET-запрос для поиска операции по `client_request_id`
- [ ] **RISK-004** — Блокировать повторный submit при `outcome_unknown` до явного сброса пользователем
- [ ] **RISK-004** — Показывать предупреждение: «Результат неизвестен. Проверьте список операций. Не создавайте повторно.»
- [ ] Проверить, что SyncServer реально использует `client_request_id` для дедупликации
- [ ] Проверить сквозной путь `client_request_id` через Django BFF → SyncServer

### Этап 2. Correlation ID (1 день)

- [ ] Добавить `X-Client-Request-Id` (новый на каждый HTTP-запрос) в `BffApiService.getMutationHeaders()`
- [ ] Добавить `X-Client-Session-Id` (логическая сессия приложения, из `sessionStorage`)
- [ ] Добавить `X-Client-Tab-Id` (уникальный для вкладки, генерируется при старте)
- [ ] Извлекать `X-Request-Id` (`server_request_id`) из заголовков ответа (HttpResponse, не только тело)
- [ ] Создать `DiagnosticsSessionService` — управление session_id, tab_id, draft_id, idempotency_key
- [ ] `draft_id` создаётся сразу при открытии новой формы (до первого сохранения)
- [ ] `idempotency_key` один на черновик, не меняется при повторах
- [ ] Добавить `frontend_version` из environment (git describe → environment.ts на этапе сборки)
- [ ] Проверить, что nginx пробрасывает кастомные заголовки
- [ ] Проверить, что Django/SyncServer возвращают `X-Request-Id` в заголовках ответа

### Этап 3. Минимальная UI-диагностика (2–3 дня)

Всего 10 событий базового режима:

```
form_opened, submit_clicked, validation_failed,
request_started, request_succeeded, request_failed,
outcome_unknown, response_processing_failed,
navigation_away_with_unsaved, unexpected_error
```

- [ ] Создать `core/diagnostics/diagnostics.models.ts` — модели событий
- [ ] Создать `core/diagnostics/diagnostics.service.ts` — сбор событий
- [ ] Создать `core/diagnostics/diagnostics-queue.service.ts` — очередь, batch-отправка через отдельный `fetch()`-клиент (в обход Angular HttpClient и interceptors, чтобы избежать рекурсии), все операции вне Angular Zone
- [ ] Встроить событийные точки в критические места:
  - `OperationCreateModalComponent` → `form_opened`, `submit_clicked`, `validation_failed`
  - `OperationsPageComponent` → `submit_succeeded`, `submit_failed`, `navigation_away_with_unsaved`
  - `OperationsService` → `request_succeeded`, `request_failed`, `outcome_unknown`
  - `HttpErrorInterceptor` → `request_failed`
  - `GlobalErrorHandler` → `unexpected_error`
- [ ] Реализовать backend endpoint `POST /bff/api/v1/diagnostics/ui-events/batch` (Django BFF, сессионная авторизация, не `csrf_exempt`)
- [ ] Создать миграцию для `diagnostics_ui_events` таблицы
- [ ] Настроить TTL-очистку (cron/pg_cron, порциями по 20 000 строк)

### Этап 4. Защита черновика (2 дня)

- [ ] Добавить автосохранение в `sessionStorage` через `effect()` в модале
- [ ] При открытии модала — проверять `sessionStorage` и предлагать восстановление
- [ ] Добавить `CanDeactivate` guard для `/operations` при открытом модале
- [ ] Добавить `window.addEventListener('beforeunload', ...)` при несохранённых изменениях
- [ ] Добавить подтверждение при закрытии модала с несохранёнными данными
- [ ] Очищать `sessionStorage` только после однозначного успеха операции
- [ ] Удалять черновик из `sessionStorage` при успешном submit

### Этап 5. Управляемая расширенная диагностика (1–2 дня, опционально)

- [ ] Реализовать endpoint конфигурации `/bff/api/v1/diagnostics/config`
- [ ] Feature flag: включение по `user_id`, `device_id`, TTL
- [ ] Разделить события на базовый и расширенный уровни
- [ ] Добавить периодический опрос конфигурации (раз в 5 мин)
- [ ] Автоматическое включение расширенного режима после первой ошибки

### Этап 6. Опциональный Session Replay (TBD)

**Только если предыдущих этапов недостаточно.**

- [ ] Оценить транскрайберы (rrweb, собственное решение)
- [ ] Оценить влияние на производительность и сеть
- [ ] Реализовать строгую фильтрацию чувствительных данных
- [ ] Реализовать включение «по запросу» для конкретной сессии

---

## 15. Список файлов, которые потребуется изменить

### Этап 0. Контракт результата

| Файл | Изменения |
|------|-----------|
| `operations-page.component.ts` | RISK-001a: показывать operation_id, не путать ошибку loadList с ошибкой submit |
| `operations-page.component.ts` | RISK-003: исправить порядок в onConfirmSubmit |
| `operations-page.component.ts` | RISK-006: обработка ошибок в catch-блоках |
| `operations.service.ts` | RISK-002: @deprecated на saveAndSubmit или исправление контракта |
| `operation-create-modal.component.ts` | Показывать operation_id после успешного submit |

### Этап 1. Идемпотентность

| Файл | Изменения |
|------|-----------|
| `operations.models.ts` | Добавить `idempotencyKey` в `OperationDraftVm` |
| `operations.service.ts` | RISK-001: idempotency key создаётся при первом create, хранится в черновике |
| `operations.service.ts` | RISK-001: buildPayload НЕ генерирует новый ключ при повторе |
| `operations.service.ts` | RISK-004: метод поиска операции по client_request_id |
| `operations-page.component.ts` | RISK-004: блокировка повтора при outcome_unknown |
| `operation-create-modal.component.ts` | RISK-004: предупреждение при outcome_unknown |

### Этап 2. Correlation

| Файл | Изменения |
|------|-----------|
| `bff-api.service.ts` | Добавить `X-Client-Request-Id`, `X-Client-Session-Id`, `X-Client-Tab-Id` |
| `bff-api.service.ts` | Извлекать `X-Request-Id` из заголовков ответа |
| `core/diagnostics/diagnostics-session.service.ts` | **Новый:** управление session_id, tab_id, draft_id |
| `environment.ts` (новый) | `frontendVersion` из git describe |

### Этап 3. Минимальная диагностика

| Файл | Изменения |
|------|-----------|
| `core/diagnostics/diagnostics.models.ts` | **Новый:** DTO событий |
| `core/diagnostics/diagnostics.service.ts` | **Новый:** сбор событий |
| `core/diagnostics/diagnostics-queue.service.ts` | **Новый:** очередь и отправка (вне Angular Zone) |
| `operation-create-modal.component.ts` | Встроить: form_opened, submit_clicked, validation_failed |
| `operations-page.component.ts` | Встроить: submit_succeeded, submit_failed, navigation_away_with_unsaved |
| `operations.service.ts` | Встроить: request_started, request_succeeded, request_failed, outcome_unknown |
| `http-error.interceptor.ts` | Отправлять request_failed через DiagnosticsService |
| `global-error-handler.ts` | Отправлять unexpected_error через DiagnosticsService |
| `app.config.ts` | Зарегистрировать провайдеры диагностики |
| `Warehouse_web/.../diagnostics/` | **Новый:** Django batch endpoint |
| Миграция Django | `diagnostics_ui_events` таблица + индексы |

### Этап 4. Защита черновика

| Файл | Изменения |
|------|-----------|
| `operation-create-modal.component.ts` | Автосохранение в sessionStorage, подтверждение при закрытии |
| `operations-page.component.ts` | Восстановление черновика при открытии |
| `core/guards/unsaved-changes.guard.ts` | **Новый:** CanDeactivate |
| `app.routes.ts` | Добавить CanDeactivate на /operations |

### Этап 5. Расширенная диагностика

| Файл | Изменения |
|------|-----------|
| `core/diagnostics/diagnostics-config.service.ts` | **Новый:** загрузка конфигурации |
| `diagnostics.service.ts` | Разделение базового/расширенного режима |
| Django endpoint | `GET /bff/api/v1/diagnostics/config` |

---

## 16. Риски и открытые вопросы

### Подтверждённые риски

| # | Риск | Вероятность | Влияние | Митигация |
|---|------|-------------|---------|-----------|
| R1 | Дубликат операции из-за отсутствия идемпотентности (RISK-001) | Средняя | Высокое | Этап 1: idempotency key один на черновик |
| R2 | Пользователь не видит operation_id после успеха (RISK-001a) | Высокая | Среднее | Этап 0: показывать подтверждение |
| R3 | Невозможность прокинуть X-Request-Id через nginx/Django | Низкая | Среднее | Проверить на Этапе 2 |
| R4 | Браузер не поддерживает sendBeacon | Низкая | Низкое | Fallback на fetch с keepalive |
| R5 | Переполнение очереди при каскадных ошибках | Средняя | Низкое | Ограничение очереди, приоритизация, задержка critical flush |
| R6 | Конфликт с Content Security Policy | Низкая | Среднее | Проверить заголовки CSP |
| R7 | Пользователь открыл несколько вкладок с одним черновиком | Средняя | Среднее | Разные tab_id, автосохранение в sessionStorage (изолировано по вкладкам) |

### Различение идентификаторов

Важно не смешивать:

| Идентификатор | Назначение | Жизненный цикл | Где хранится |
|---------------|-----------|----------------|--------------|
| `session_id` | Логическая пользовательская сессия приложения | От логина до логаута / истечения | `sessionStorage` или auth-контекст |
| `tab_id` | Конкретная вкладка браузера | От открытия до закрытия вкладки | Память (генерируется при старте) |
| `draft_id` | Идентификатор формы/черновика | Создаётся **сразу при открытии новой формы**, до первого сохранения | В черновике |
| `idempotency_key` (`client_request_id`) | Идентификатор логической бизнес-команды (Idempotency-Key) | Один на черновик, переиспользуется при повторах | В черновике |
| `http_request_id` (`X-Client-Request-Id`) | Идентификатор конкретного HTTP-запроса | Новый на каждый HTTP-вызов | Заголовок запроса |
| `server_request_id` (`X-Request-Id`) | ID обработки запроса на сервере | Назначается сервером, возвращается в ответе | Заголовок ответа |

При повторной попытке после таймаута:
- `idempotency_key` — **прежний**
- `http_request_id` — **новый**
- `draft_id` — **прежний**
- `server_request_id` — **новый** (новый HTTP-запрос)

### Открытые вопросы

1. **Nginx конфигурация:** Пробрасывает ли nginx кастомные заголовки (`X-Request-Id`, `X-Client-Request-Id`)? Нужно проверить `nginx.conf` в Docker-образе.
2. **SyncServer idempotency:** Реально ли SyncServer использует `client_request_id` для дедупликации операций? Нужно проверить код SyncServer.
3. **SyncServer audit log:** Существует ли уже `request_id` в SyncServer? Возвращается ли он в заголовках ответа? Нужно проверить.
4. **Django BFF:** Есть ли в Django middleware для `X-Request-Id`? Нужно проверить `Warehouse_web/middleware.py`.
5. **Нагрузка на БД:** При 100 активных пользователях, создающих ~50 событий в час — ~5000 событий/час. ~120 000/день. За 30 дней ~3.6 млн строк. Нужно оценить размер таблицы.
6. **GDPR/152-ФЗ:** Содержат ли диагностические события персональные данные? По текущему дизайну — нет (только `user_id` и `device_id`), но нужно формальное подтверждение.
7. **Отключение диагностики:** Как быстро должно применяться отключение через конфигурацию? Сейчас в дизайне — опрос раз в 5 минут.

### Предположения, требующие проверки

1. **Предположение:** Django BFF проксирует заголовки от SyncServer (включая `X-Request-Id`). **Требует проверки.**
2. **Предположение:** Все операции идут через `BffApiService`, а не через `ApiService` (легаси). **Подтверждено для операций.**
3. **Предположение:** `saveAndSubmit()` не вызывается. **Подтверждено:** 0 вызовов за пределами сервиса.
4. **Предположение:** Черновик удаляется при таймауте. **Опровергнуто:** при ошибке модал остаётся открытым. Ранняя версия ревью содержала неточность — исправлено.

### Что осталось непроверенным

1. **nginx.conf** — конфигурация Docker-образа, проброс заголовков
2. **SyncServer** — реальное поведение `client_request_id` при создании операции
3. **Django middleware** — наличие `X-Request-Id` в ответах
4. **Путь `X-Request-Id`** — возвращается ли он из SyncServer через Django BFF до Angular

---

## Заключение

1. **Операция может потеряться** — подтверждено. Но нужно различать: (а) реальную потерю (нет идемпотентности → дубликат вместо повтора), (б) ошибку отображения (операция создана, но список не обновился).
2. **Главный BLOCKER** — не закрытие модала, а отсутствие идемпотентности: каждый повторный вызов `createOperation` получает новый `client_request_id`, что делает невозможной безопасную повторную отправку после таймаута.
3. **Интерфейс не показывает `operation_id`** после успеха — пользователь не получает надёжного подтверждения, что операция проведена.
4. **saveAndSubmit() не вызывается** (0 call sites) — это технический долг, а не причина текущих жалоб.
5. **Форма НЕ очищается при ошибке** (включая таймаут) — модал остаётся открытым. Ранняя версия ревью содержала неточность на этот счёт — исправлено.
6. **Черновик молча теряется** при смене маршрута или закрытии модала — нет `CanDeactivate`, `beforeunload`, подтверждения.
7. **Связать действия Angular с SyncServer** можно через три идентификатора: `idempotency_key` (бизнес-команда), `http_request_id` (HTTP-запрос), `server_request_id` (обработка на сервере).
8. **Минимальный набор из 10 событий** даст достаточную диагностику без заметной нагрузки на браузер.

### Исправления относительно первой версии ревью

| Было | Стало | Причина |
|------|-------|---------|
| RISK-001 BLOCKER: закрытие модала до loadList | RISK-001 BLOCKER: отсутствие идемпотентности client_request_id | Закрытие модала — ошибка отображения, не потери данных |
| RISK-001a HIGH: нет operation_id после submit | Новая проблема | Настоящая причина «всё пропало» для пользователя |
| RISK-002 HIGH: saveAndSubmit глотает ошибку | RISK-002 LOW: технический долг, 0 вызовов | grep подтвердил недостижимость |
| При таймауте черновик удаляется | При таймауте модал остаётся открытым | Код подтверждает: set(false) только при успехе |
| 200 событий = 4 KB | 200 событий = 100–500 KB | Реалистичная оценка JS-объектов |
| Дедупликация по client_request_id | Дедупликация по event_id | Один request_id может иметь много событий |
| Critical — немедленная отправка | Critical — flush через 250–500 мс | Предотвращение шторма запросов |
| Асинхронная очередь (worker) | Синхронный bulk insert | Преждевременная оптимизация |
| Partial index с NOW() | Обычный индекс + порционная очистка | NOW() не работает в предикате partial index |
