# TZ-FRONTEND_OPERATION_SUBMIT_ERROR_SURFACE

**Статус:** готово к реализации
**Дата:** 2026-07-31
**Автор:** architect (по запросу пользователя)
**Связанные документы:**
* ADR-0025 — `docs/adr/0025-operation-submit-domain-errors.md`
* Scope — `.agent/SCOPE-operation-submit-domain-errors.md`
* Серверный TZ — `docs/TZ-SYNCSERVER_OPERATION_SUBMIT_DOMAIN_ERRORS.md`
* Спек экрана — `Warehouse_frontend/docs/screens_plan/operations-screen-spec.md:630-720, 1184`

---

## 0. Execution Checklist

- [x] 0. Контекст verified
- [x] 1. Контекст и подтверждённые факты
- [x] 2. Цели и не-цели
- [x] 3. TypeScript-модели envelope
- [x] 4. Parser / normalizer
- [x] 5. Сервис ошибок и хранение
- [x] 6. Inline-подсветка строк
- [x] 7. Подсчёт строк в toast
- [x] 8. Toast для operation-level ошибок
- [x] 9. Scroll / focus
- [x] 10. Очистка групповых ошибок
- [x] 11. a11y
- [x] 12. Неизвестные коды
- [x] 13. Unit-тесты
- [x] 14. Playwright-сценарии
- [x] 15. Стенд smoke
- [x] 16. Документация
- [x] 17. Final acceptance

## Check Rules

* Архитектор создаёт чек-лист и критерии приёмки.
* Executor проверяет только после реализации и собственного прогона всех применимых уровней тестов.
* Если уровень недоступен — оставить пустым с пометкой «стенд недоступен».
* Перед любым real-stand прогоном — Stand Availability Protocol из `AGENTS.md`.

---

## 1. Подтверждённые факты репозитория

Зафиксированы при разведке 2026-07-31.

### 1.1. Frontend стек

* Angular (standalone components), Vitest unit runner (`@angular/build:unit-test`), Playwright e2e.
* `Warehouse_frontend/docs/screens_plan/operations-screen-spec.md:630-720` — спек экрана с inline-подсветкой «На складе: X шт / Количество: 5 / Ошибка: Недостаточно».
* `Warehouse_frontend/docs/screens_plan/operations-screen-spec.md:1184` — «quantity validation warns on insufficient stock for MOVE/ISSUE».
* BFF — Django (`Warehouse_web`), same-origin endpoints, никаких SyncServer-токенов в браузере.
* Verify: `npm run build`, `npm run test:unit` (`npx ng test --watch=false`), `make test-e2e` для Playwright.

### 1.2. Текущая модель ошибок на фронте

* `Warehouse_frontend/.../operations-create-modal.component.ts` — текущая форма создания/редактирования операции.
* BFF сейчас возвращает ошибки через `_error(str(exc), "sync_error", status=...)` — НЕ пробрасывает полный payload. **Это меняется в серверном TZ** (см. `TZ-SYNCSERVER_OPERATION_SUBMIT_DOMAIN_ERRORS.md` §8).
* Angular получит envelope только после того, как Django BFF начнёт его пробрасывать. Эта зависимость фиксируется как «внешнее условие» в §10.

### 1.3. Соседние scope, которые **не перекраивает** этот TZ

Рядом с этим TZ существует ещё один утверждённый scope, затрагивающий ту же форму операции. Этот TZ **не должен** вмешиваться в его зону ответственности:

| Scope / TZ | Зона ответственности | Что этот TZ **не** делает |
|---|---|---|
| `.agent/SCOPE-ops-balances-manual.md` (от 2026-07-14, TZ ещё не написан) | Кнопка «Обновить всё» в шапке таблицы строк, удаление `refreshBeforePersist()` перед submit, точечный автозапрос остатков при добавлении/выборе ТМЦ и при смене склада, скрытие остатка в `ItemCacheSearchComponent`. Backend не трогается | **Не** добавляет и **не** меняет кнопку «Обновить всё», **не** трогает `refreshBeforePersist()`, **не** меняет `ItemCacheSearchComponent`, **не** вводит клиентский pre-submit refresh остатков |
| `docs/TZ-V3.2_CATALOG_CACHE_AND_OPERATION_PERSISTENCE_HARDENING.md` D2 «Обновить и проверить ТМЦ» | Кэш поиска ТМЦ (`catalog_cache_item`), stale items, ghost rows после merge/delete | **Не** трогает кэш поиска ТМЦ, **не** добавляет кнопку «Обновить и проверить ТМЦ» |

### 1.4. Согласованность с Success Criteria из SCOPE-ops-balances-manual

Этот TZ соблюдает инвариант из SCOPE-ops-balances-manual §5: «Submit операции не вызывает фонового обновления остатков — submit работает на текущих значениях формы». Этот TZ:

* **не** вводит pre-submit refresh остатков;
* submit отправляет то, что есть в форме, и получает envelope ошибки **с сервера** (агрегированная проверка остатков в `submit_operation` — см. `TZ-SYNCSERVER_OPERATION_SUBMIT_DOMAIN_ERRORS.md` §5);
* stale-серверные ошибки на строках формы очищаются при изменении этих строк (этот TZ §10) — это не pre-submit refresh, а очистка визуального состояния строки после её редактирования;
* если кладовщик подозревает, что остатки устарели, он нажимает «Обновить всё» из SCOPE-ops-balances-manual (реализуется отдельным TZ, **не** этим).

### 1.5. Допущение о зависимости от SCOPE-ops-balances-manual

Допущение: этот TZ не зависит от того, реализован ли уже SCOPE-ops-balances-manual. Если кнопка «Обновить всё» ещё не добавлена — этот TZ всё равно работает корректно: при server-side reject кладовщик видит envelope и inline-подсветку, без необходимости что-либо обновлять вручную (или с обновлением через другие механизмы).

### 1.3. Подтверждённые ID-типы от сервера

См. TZ 1 §1.2:

* `operation.id`, `user.id` — UUID.
* `site.id`, `item.id`, `inventory_subject.id` — integer.
* `operation_line.id` — integer (BigInteger, отображается как number).
* `version` — integer.

`line.uuid` (UUID) — есть, но для подсветки используется `line.id` (стабильный integer после submit).

---

## 2. Цели и не-цели

### In scope

1. TypeScript-модели envelope и `errors[]` (зеркало Pydantic-схем).
2. Parser/normalizer envelope → внутренняя модель `OperationSubmitError`.
3. Fallback parser для legacy `{detail: string}` (если BFF ещё не обновлён или SyncServer вернул старый формат).
4. Хранение line-group ошибок с группировкой по `error_group_id`.
5. Inline-подсветка строк по `operation_line_ids`.
6. Toast с подсчётом уникальных строк (а не длины `errors[]`).
7. Toast для operation-level ошибок с фиксированными текстами.
8. Scroll и focus на первую проблемную строку.
9. Очистка всей группы при изменении любой строки группы.
10. a11y: `aria-invalid`, иконка + текст, не только цвет.
11. Unit-тесты parser, normalizer, error service.
12. Playwright-сценарии для submit-flow.

### Out of scope

1. Client-side precheck остатков перед submit (отдельная задача — `SCOPE-ops-balances-manual.md`).
2. Кнопка «Обновить всё» в шапке таблицы строк — отдельный TZ по `SCOPE-ops-balances-manual.md`.
3. Удаление `refreshBeforePersist()` — отдельный TZ по `SCOPE-ops-balances-manual.md`.
4. Изменение `ItemCacheSearchComponent` (скрытие остатка в выпадашке) — отдельный TZ по `SCOPE-ops-balances-manual.md`.
5. Bulk-эндпоинт `POST /bff/api/v1/operations/refresh-balances` — отдельная задача.
6. Кэш поиска ТМЦ (`catalog_cache_item`) — `TZ-V3.2_CATALOG_CACHE_AND_OPERATION_PERSISTENCE_HARDENING.md`.
7. Кнопка «Обновить и проверить ТМЦ» — `TZ-V3.2_CATALOG_CACHE_AND_OPERATION_PERSISTENCE_HARDENING.md` D2.
8. Изменение BFF endpoints (делается в серверном TZ).
9. Изменение legacy Django SSR формы.
10. Локализация / i18n.
11. Метрики ошибок.

---

## 3. TypeScript-модели

### 3.1. Расположение

Файл: `Warehouse_frontend/src/app/features/operations/submit-error/envelope.ts` (**новый**).

### 3.2. Single source of truth

Этот TZ **не определяет** структуру envelope. Структура envelope определена в `docs/TZ-SYNCSERVER_OPERATION_SUBMIT_DOMAIN_ERRORS.md` §3.3 (Pydantic-схема `ProblemEnvelope`, `ProblemErrorLineGroup`, `ProblemErrorOperation`). Все примеры JSON в этом TZ — ссылки на Pydantic-схему. Если Pydantic-схема меняется — этот TZ обновляется следом.

Это **ручное зеркалирование** типов (OpenAPI-генерация TypeScript в проекте пока не настроена). При расхождении — источник истины Pydantic, а не TypeScript.

### 3.3. Зеркало Pydantic

**`unit` — display-only.** `unit_id` не участвует в ключе агрегации остатков на сервере (ADR-0025 §0). `unit` в envelope — это только отображаемые данные для UI; если `unit` отсутствует, UI показывает количество без символа единицы.

**`temporary_item_blocked` отсутствует.** См. ADR-0025 §0 — отменённое положение scope. В кодах `errors[].code` такого значения нет.

**Идентификация `operation_line.id`.** Целые integer, сериализуются как JSON Number. `Number.isSafeInteger` ограничение `2^53 - 1`; BigInteger в Postgres переполнит только при ~9 квадриллионах строк. Parser проверяет `Number.isSafeInteger` для каждого `operation_line_ids[i]` и при переполнении логирует и помечает группу как `malformed`.

### 3.4. Raw DTO + нормализация

Подход: не приводить произвольный `code` сразу к union известных кодов. Сначала — **raw DTO**, потом **нормализация** в один из трёх типов.

Файл: `Warehouse_frontend/src/app/features/operations/submit-error/envelope.ts`.

```typescript
// Raw DTO — точное зеркало JSON, без narrowing
export interface RawSubmitError {
  code: string;                              // любой string, не union
  scope: 'operation' | 'line_group';
  operation_line_ids?: number[];
  item?: { id: number; name: string };
  stock_site?: { id: number; name: string };
  issue_object?: { id: number; name: string };
  required_qty?: string;
  available_qty?: string;
  unit?: { id: number; name: string; symbol: string };
  expected_version?: number;
  actual_version?: number;
  current_state?: string;
  allowed_states?: string[];
}

export interface RawSubmitErrorEnvelope {
  type: string;
  title: string;
  status: number;
  code: string;
  detail: string;
  instance?: string;
  trace_id?: string;
  errors: RawSubmitError[];
}

// Известные типы после нормализации
export type KnownErrorCode =
  | 'insufficient_stock'
  | 'insufficient_issued_balance'
  | 'stale_version'
  | 'operation_in_wrong_state'
  | 'role_not_permitted'
  | 'operation_not_found';

export interface KnownLineGroupError {
  kind: 'known_line_group';
  code: 'insufficient_stock' | 'insufficient_issued_balance';
  operation_line_ids: number[];
  item: { id: number; name: string };
  stock_site?: { id: number; name: string };
  issue_object?: { id: number; name: string };
  required_qty: string;
  available_qty: string;
  unit?: { id: number; name: string; symbol: string };
}

export interface KnownOperationError {
  kind: 'known_operation';
  code: Exclude<KnownErrorCode, 'insufficient_stock' | 'insufficient_issued_balance'>;
  expected_version?: number;
  actual_version?: number;
  current_state?: string;
  allowed_states?: string[];
}

export interface UnknownError {
  kind: 'unknown';
  code: string;
  scope: 'operation' | 'line_group';
  detail?: string;       // envelope.detail (errors[].detail в серверном контракте отсутствует)
}

export type NormalizedSubmitError = KnownLineGroupError | KnownOperationError | UnknownError;
```

Нормализация (`normalizer.ts`):

* для каждого `RawSubmitError` из envelope проверяется `code`:
  * `'insufficient_stock'` / `'insufficient_issued_balance'` + `scope === 'line_group'` → `KnownLineGroupError` (проверяется наличие обязательных полей; отсутствие → `UnknownError` с логированием `missing_required_fields`);
  * `'stale_version'` / `'operation_in_wrong_state'` / `'role_not_permitted'` / `'operation_not_found'` + `scope === 'operation'` → `KnownOperationError`;
  * всё остальное → `UnknownError` с `detail = envelope.detail`.

`UnknownError.detail` берётся из **`envelope.detail`** (а не из `errors[i].detail`, которого в серверном контракте нет — см. TZ 1 §3.3).

### 3.5. Контрактный тест на JSON fixtures

Файл: `Warehouse_frontend/src/app/features/operations/submit-error/envelope.fixtures.ts` (**новый**).

JSON-fixtures берутся из примеров в `TZ-SYNCSERVER_OPERATION_SUBMIT_DOMAIN_ERRORS.md` §3.3 / §10. Тест `envelope.spec.ts` проверяет, что parser успешно десериализует каждый fixture и типы соответствуют интерфейсам. Любое расхождение — failed test, обновляем TypeScript до совпадения с Pydantic.

---

## 4. Parser / normalizer

### 4.1. Расположение

Файл: `Warehouse_frontend/src/app/features/operations/submit-error/parser.ts` (**новый**).

### 4.2. Входные формы

* Новый envelope (после реализации серверного TZ + BFF).
* Legacy `{detail: string}` — fallback.

### 4.3. Контракт

```typescript
export interface ParseResult {
  ok: boolean;
  envelope: SubmitErrorEnvelope | null;
  unknown: boolean;                           // true если не удалось распознать
  logPayload?: unknown;                       // для логирования
}

export function parseSubmitErrorResponse(raw: unknown): ParseResult;
```

Поведение:

* `raw` — это `HttpErrorResponse.error` или `unknown`.
* Если `raw` — JSON-объект с `errors: SubmitError[]` и `code: string` — парсим как envelope.
* Если `raw` — JSON-объект с `detail: string` и без `errors` — legacy fallback: создаём envelope `{code: 'unknown', detail: raw.detail, errors: []}`.
* Иначе — `{unknown: true}`, логируем `raw` в консоль (через `LogService`).
* Никакого regex-парсинга текста. Это явно запрещено в ADR-0025 §«Отклонённые альтернативы».

---

## 5. Сервис ошибок и хранение

### 5.1. Расположение

Файл: `Warehouse_frontend/src/app/features/operations/submit-error/submit-error.service.ts` (**новый**).

### 5.2. Состояние

```typescript
@Injectable({ providedIn: 'root' })
export class SubmitErrorService {
  // Группы ошибок хранятся отдельно. Каждая группа имеет стабильный id.
  private groups = signal<Record<string, ErrorGroup>>({});
  envelope = signal<SubmitErrorEnvelope | null>(null);

  // Производные: уникальные operation_line_id → group_id
  linesByGroup = computed(() => ...);
  erroredLineIds = computed(() => ...);
}

interface ErrorGroup {
  id: string;                                 // стабильный group id (uuid v4)
  error: NormalizedSubmitError;               // после нормализации
  receivedAt: number;                         // timestamp
  stale: boolean;                             // true после изменения любой строки группы (§10)
}
```

### 5.3. API

* `setFromHttpError(raw: unknown)` — вызвать parser и нормализатор, обновить `envelope` и `groups`. Все новые группы инициализируются с `stale: false`.
* `clearAll()` — сбросить `envelope` и `groups`. **Обязательный** вызов в lifecycle модалки (см. §5.5).
* `invalidateByLineIds(lineIds: number[])` — пометить все группы, у которых `error.operation_line_ids` (для `KnownLineGroupError`) пересекается с `lineIds`, как `stale: true`. Используется при изменении любой строки группы.
* `clearByLineIds(lineIds: number[])` — удалить все группы, у которых `error.operation_line_ids` ⊆ `lineIds`. Альтернативный сценарий (не выбираем).
* `firstErroredLineId(): number | null` — для scroll/focus.

### 5.4. Детерминированный порядок групп

Группы в `groups` хранятся в порядке получения от сервера (insertion order). Поскольку сервер уже детерминирует порядок (TZ 1 §3.4), UI просто рендерит в этом порядке.

### 5.5. Lifecycle модалки — `SubmitErrorService` не хранит состояние между открытиями

`SubmitErrorService` **не** переиспользует состояние между разными открытиями одной и той же модалки:

* **Либо** провайдер делается на уровне компонента модалки (`providers: [SubmitErrorService]` в `@Component({...})`), тогда каждый новый mount создаёт свежий экземпляр;
* **Либо** провайдер остаётся `providedIn: 'root'`, но `OperationCreateModalComponent` вызывает `clearAll()`:
  * в `ngOnInit` (или `OnInit` сигналах) — при каждом открытии;
  * в `ngOnDestroy` — при закрытии;
  * при изменении `operationId` (если модалка переиспользуется для разных операций).

Это гарантирует, что ошибка от предыдущего submit не «протекает» в новое открытие формы.

Если выбран первый вариант (component-level provider), `OperationCreateModalComponent` обязан прокинуть инстанс сервиса в `OperationLinesTableComponent` через `inputs()` или DI.

---

## 6. Inline-подсветка строк

### 6.1. Файл

`Warehouse_frontend/src/app/features/operations/operation-create-modal/` — модификация существующих компонентов.

### 6.2. Поведение

* Каждая строка с `errorGroupId` отображает:
  * визуальная подсветка (CSS-класс `row--has-error`);
  * иконка (warning icon, не только цвет);
  * текстовая подсказка под строкой: «На складе: X ед., запрошено: Y ед.» — из `error.required_qty` и `error.available_qty` (`required_qty` отображается как есть, строкой);
  * `aria-invalid="true"` на редактируемых полях строки;
  * `aria-describedby` указывает на id текстовой подсказки.
* Агрегированная группа (`operation_line_ids.length > 1`):
  * каждая строка группы подсвечивается одинаково;
  * текст подсказки — общий (один и тот же текст для всех строк группы);
  * счётчик «1 из N» не отображается (избыточно).

### 6.3. CSS

`Warehouse_frontend/src/styles/operations/_submit-errors.scss` (**новый**):

```scss
.row--has-error { outline: 2px solid var(--color-error, #c00); }
.row--has-error--stale { outline-style: dashed; }     // когда группа помечена как stale
```

Цвет + outline (не только цвет) — требование a11y.

### 6.4. Не делать

* Не использовать разные цвета для разных `errors[].code` — все доменные ошибки выглядят одинаково.
* Не показывать в подсказке `stock_site.name`/`issue_object.name`/`item.name` — это перегрузка; достаточно «На складе: X / Запрошено: Y».

---

## 7. Подсчёт строк в toast

### 7.1. Правило

Считать **уникальные `operation_line_ids`** из всех `line_group` ошибок envelope. Не длину `errors[]`.

Примеры:

* `errors = [{operation_line_ids: [1, 4]}]` → toast «ошибки в 2 строках».
* `errors = [{operation_line_ids: [1]}, {operation_line_ids: [4]}]` → toast «ошибки в 2 строках».
* `errors = [{operation_line_ids: [1, 4]}, {operation_line_ids: [7, 9]}]` → toast «ошибки в 4 строках».

### 7.2. Реализация

```typescript
function countErroredLines(envelope: SubmitErrorEnvelope): number {
  const ids = new Set<number>();
  for (const err of envelope.errors) {
    if (err.scope === 'line_group') {
      for (const id of err.operation_line_ids) ids.add(id);
    }
  }
  return ids.size;
}
```

Для operation-level ошибок (`scope: 'operation'`) — отдельные фиксированные тексты (см. §8), без подсчёта строк.

---

## 8. Toast для operation-level ошибок

### 8.1. Шаблон текстов

```typescript
export const OPERATION_LEVEL_TOAST_MESSAGES: Record<string, string> = {
  stale_version: 'Операция была изменена другим пользователем. Перечитайте данные.',
  operation_in_wrong_state: 'Операцию нельзя провести в текущем состоянии.',
  role_not_permitted: 'Недостаточно прав для проведения операции.',
  operation_not_found: 'Операция не найдена.',
};
```

### 8.2. Поведение

* Если envelope содержит только operation-level ошибки (нет `line_group`) — показываем toast с фиксированным текстом.
* Если envelope содержит смесь — показываем:
  * отдельный toast для каждой operation-level ошибки (с её текстом);
  * один toast для line_group ошибок («Не удалось провести операцию: ошибки в N строках»).
* При `stale_version` — после показа toast и закрытия модалки submit, форма предлагает перечитать операцию (отдельная кнопка «Обновить» рядом с submit). Это требование из уточнённого §«Success Criteria» исходного scope.
* При `operation_in_wrong_state` — toast «Операцию нельзя провести в текущем состоянии». Это включает случай повторного submit (операция уже проведена или отменена). См. правило **state-before-version** в ADR-0025 §7 и TZ 1 §7.1.
* При `unknown` (parser не распознал) — toast «Не удалось провести операцию. Попробуйте ещё раз или обратитесь к администратору.»; в консоль — `console.error` с полным payload.

### 8.3. Не делать

* Не блокировать UI глобальным модальным окном — только toast + scroll/focus.
* Не вызывать API автоматически для «перечитать» — только по кнопке.

---

## 9. Scroll / focus

### 9.1. Поведение

* При показе envelope после submit:
  1. Найти первую строку с активной ошибкой через `submitErrorService.firstErroredLineId()`.
  2. Если строка найдена — `scrollIntoView({ behavior: 'smooth', block: 'center' })`.
  3. Перевести фокус на первое редактируемое поле этой строки (qty, comment, и т.д.).
  4. Если строк нет (только operation-level ошибки) — фокус на кнопку «Закрыть» или «Обновить».

### 9.2. Edge cases

* Строка не видна в DOM (виртуальный скролл?) — прокрутить до неё через `Element.scrollIntoView`.
* Строка disabled — пропустить, искать следующую errored.
* Несколько ошибок в одной строке — фокус на поле qty.

---

## 10. Очистка групповых ошибок

### 10.1. Правило

Агрегированная ошибка — это **группа строк**. Изменение **любой** строки группы делает ошибку всей группы устаревшей.

### 10.2. Поведение

При изменении поля строки (qty, item, и т.д.):

1. Определить `affected_line_ids: number[]` — изменённая строка + все строки, которые были в одной с ней error-группе.
2. Для каждой error-группы, у которой `operation_line_ids` пересекается с `affected_line_ids`:
   * пометить группу как `stale: true` (CSS-класс `row--has-error--stale`);
   * сохранять в UI, но визуально отличать (пунктирная рамка).
3. При следующем submit:
   * `clearAll()` сбрасывает все группы и `stale`-метки.

### 10.3. Альтернатива (для простых форм)

Вместо `stale`-метки — сразу удалять группу при изменении любой строки группы. Менее информативно для пользователя, но проще. **Выбираем `stale`-вариант** как более полезный.

### 10.4. Не делать

* Не удалять группу по изменению `comment`/`note` — только значимых полей (qty, item, batch).
* Не показывать пользователю «ошибка устарела» явно — достаточно визуального отличия.

---

## 11. a11y

### 11.1. Требования

* `aria-invalid="true"` на редактируемых полях строки с ошибкой.
* `aria-describedby="<error-text-id>"` на тех же полях, чтобы скринридер прочитал текст подсказки.
* Текст подсказки (`<div id="error-text-id" role="alert">`) — это то, что скринридер прочитает.
* Toast-компонент — `role="alert"` или `aria-live="assertive"` (для критичных ошибок submit).
* Не полагаться только на цвет — иконка + текст + outline.

### 11.2. Тесты

* Playwright-сценарий с `@axe-core/playwright` или ручная проверка скринридером.

---

## 12. Неизвестные коды

### 12.1. Поведение

* Если `errors[].code` не входит в список известных (`insufficient_stock`, `insufficient_issued_balance`, `stale_version`, `operation_in_wrong_state`, `role_not_permitted`, `operation_not_found`) — нормализатор возвращает `UnknownError { kind: 'unknown', code, scope, detail: envelope.detail }`.
* UI использует `envelope.detail` для отображения (серверный контракт **не** содержит `errors[].detail` — см. TZ 1 §3.3).
* Inline-подсветка показывает `envelope.detail` или generic «Ошибка сервера».
* В консоли — `console.error('[submit-error] unknown code', { code, error })`.
* Это не должно ломать UI — envelope валиден, просто код не опознан.
* Список известных кодов — **единственный источник истины** в этом TZ, синхронизированный с TZ 1 §3.3. Если серверный TZ добавляет новый код — этот TZ обновляется следом.

### 12.2. Метрика

Счётчик «неизвестных кодов» — отдельная задача, не в этой итерации.

---

## 13. Unit-тесты

Файл: `Warehouse_frontend/src/app/features/operations/submit-error/parser.spec.ts` (**новый**).

* `parses_envelope_with_insufficient_stock` — нормализация в `KnownLineGroupError`, поля `item`/`stock_site`/`required_qty`/`available_qty` присутствуют.
* `parses_envelope_with_insufficient_stock_missing_required_field` — отсутствует `item` → `UnknownError`, `console.error` вызван с `missing_required_fields`.
* `parses_envelope_with_stale_version` — нормализация в `KnownOperationError`.
* `parses_envelope_with_operation_in_wrong_state` — нормализация в `KnownOperationError`, `current_state`/`allowed_states[]` присутствуют.
* `parses_envelope_with_role_not_permitted` — нормализация в `KnownOperationError` с минимальными полями.
* `parses_envelope_with_operation_not_found` — нормализация в `KnownOperationError`.
* `parses_envelope_with_aggregated_line_group` — `operation_line_ids: [1, 4]`, обе строки в `operation_line_ids`.
* `parses_envelope_with_unknown_code` — `code = "future_unknown_code"` → `UnknownError { kind: 'unknown', code, scope, detail: envelope.detail }`. `detail` берётся из `envelope.detail`, **не** из `errors[].detail`.
* `parses_envelope_with_unsafely_large_line_id` — `operation_line_ids: [Number.MAX_SAFE_INTEGER + 1]` → логирование `unsafe_integer` и пометка `malformed: true` (UI не подсвечивает).
* `parses_legacy_detail_only` — fallback envelope с `detail: string` без `errors`.
* `parses_unknown_payload` — `raw = null` / `raw = "string"` → `unknown: true`.

Файл: `Warehouse_frontend/src/app/features/operations/submit-error/submit-error.service.spec.ts` (**новый**).

* `setFromHttpError_envelope_stores_groups_with_stale_false`.
* `clearAll_resets_state`.
* `invalidateByLineIds_marks_intersecting_groups_as_stale` — изменение одной строки группы помечает **всю группу** как `stale: true`, не только изменённую строку.
* `clearByLineIds_removes_groups`.
* `firstErroredLineId_returns_first_line_in_first_group`.
* `countErroredLines_dedupes_line_ids`.
* `lifecycle_no_state_leak_between_mounts` — тест с явным `clearAll()` на `ngOnInit`/`ngOnDestroy`: после первого submit с ошибкой, `destroy` и новый `init` — состояние пустое, ошибки от предыдущего submit не видны.
* `lifecycle_no_state_leak_with_component_provider` — альтернативный тест: компонент с `providers: [SubmitErrorService]` создаёт свежий инстанс при каждом mount; предыдущее состояние недоступно.

Verify: `npm run test:unit`.

---

## 14. Playwright-сценарии

Файл: `Warehouse_frontend/e2e/operations/submit-errors.spec.ts` (**новый**).

Сценарии:

1. **`submit_with_insufficient_stock_shows_inline_highlight`**:
   * создать операцию MOVE с двумя строками одной ТМЦ (60 + 60 при остатке 80);
   * submit;
   * ожидать toast «ошибки в 2 строках»;
   * ожидать inline-подсветку обеих строк;
   * ожидать текст «На складе: 80 м, запрошено: 120 м» под каждой строкой.

2. **`submit_with_stale_version_shows_refresh_button`**:
   * открыть draft в двух вкладках;
   * из вкладки 1 изменить `effective_at` или другие поля draft (операция остаётся DRAFT), сохранить — версия увеличивается;
   * из вкладки 2 submit с предыдущей `expected_version`;
   * ожидать toast «Операция была изменена другим пользователем»;
   * ожидать кнопку «Обновить» рядом с submit.

3. **`submit_already_submitted_returns_operation_in_wrong_state`** (state-before-version):
   * провести операцию (submit успешен);
   * попытаться submit ещё раз (например, из другой вкладки или через повторное нажатие);
   * ожидать toast «Операцию нельзя провести в текущем состоянии»;
   * ожидать `errors[0].code === "operation_in_wrong_state"`, **не** `stale_version`.

4. **`changing_line_clears_group_error`**:
   * submit с insufficient_stock → обе строки подсвечены;
   * изменить qty одной из строк;
   * ожидать: подсветка группы становится `stale` (пунктир).

5. **`success_submit_clears_all_errors`**:
   * submit с insufficient_stock → ошибки;
   * исправить все строки → submit успешно;
   * ожидать: подсветка исчезла, toast закрылся.

6. **`unknown_code_does_not_crash_ui`**:
   * mock backend вернуть envelope с `errors[0].code = "future_unknown_code"`;
   * submit;
   * ожидать: UI не падает, inline-подсветка показывает generic сообщение.

7. **`scroll_and_focus_to_first_errored_line`**:
   * создать длинный список строк (10), первая — без ошибки, вторая — без ошибки, третья — с ошибкой;
   * submit с недостаточным остатком;
   * ожидать: scroll к третьей строке, фокус на её поле qty.

Verify: `make test-e2e` (Playwright в Docker) или локально с `make test-e2e-headed`.

---

## 15. Стенд smoke

После реализации — на dev-стенде:

1. Открыть `http://localhost:8001/operations/<id>/edit` для draft-операции.
2. Подложить состояние «недостаточно на складе» (на стенде есть готовый сценарий через `make test-e2e`).
3. Submit.
4. Проверить визуально: toast, inline-подсветка, текст подсказки, scroll, focus.
5. Проверить через DevTools: BFF вернул envelope, Angular его распарсил.

Если стенд недоступен — `make up`, иначе чекбокс остаётся пустым с пометкой.

---

## 16. Документация

1. Обновить `Warehouse_frontend/docs/screens_plan/operations-screen-spec.md:651-659` — явно указать «серверная ошибка приходит в envelope; см. TZ-FRONTEND_OPERATION_SUBMIT_ERROR_SURFACE».
2. Добавить запись в `docs/INDEX.md` (если есть раздел про текущие TZ).

---

## 17. Критерии приёмки

1. Angular парсит envelope из BFF в `SubmitErrorEnvelope`.
2. Inline-подсветка работает для одной строки и для агрегированной группы.
3. Toast считает уникальные `operation_line_ids`, не длину `errors[]`.
4. Operation-level ошибки имеют фиксированные тексты, не показывают подсчёт строк.
5. Scroll + focus на первую проблемную строку.
6. Изменение любой строки группы помечает всю группу как `stale`.
7. Перед новым submit все ошибки сбрасываются.
8. Неизвестный код не ломает UI.
9. Legacy `{detail: string}` обрабатывается через fallback parser.
10. a11y: `aria-invalid`, `aria-describedby`, `role="alert"`, иконка + текст + outline.
11. Unit-тесты `parser.spec.ts`, `submit-error.service.spec.ts` — все зелёные.
12. Playwright `submit-errors.spec.ts` — все сценарии зелёные.
13. `npm run build`, `npm run test:unit` — без регрессий.
14. Stand smoke §15 — пройден.

---

## 18. Исполнитель

Стандартный workflow executor: реализация → unit-тесты → Playwright → стенд smoke → отчёт с evidence table → commit на `dev` (после зелёных проверок).