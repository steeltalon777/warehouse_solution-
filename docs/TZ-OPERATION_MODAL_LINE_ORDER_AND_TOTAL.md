# TZ: Порядок позиций и отображение «Всего» в модальном окне операции

## TZ

- `/home/makc/AI_sandbox/warehouse_solution/docs/TZ-OPERATION_MODAL_LINE_ORDER_AND_TOTAL.md`

## Execution Strategy

- [x] 🟢 Parallel execution recommended
- **Reason:** Две доработки затрагивают разные области: (A) модель + сервис + компонент таблицы — порядок строк; (B) шаблон + computed — заголовок с «Всего». Они могут быть выполнены параллельно разными исполнителями, затем соинтегрированы.

## Execution Checklist

- [x] 0. Context verified
- [x] 1. Architecture boundaries confirmed
- [x] 2. Implementation stage 1 — lineNumber + table column (Work Unit A)
- [x] 3. Implementation stage 2 — totalQuantity in header (Work Unit B)
- [x] 4. Static checks: `npm run build` passes
- [x] 5. Unit/component tests pass
- [x] 6. Stand smoke tests: модальное окно на реальном стенде
- [ ] 7. UI automation: Playwright-сценарии добавления/удаления/сохранения позиций
- [ ] 8. Regression: операции не сломаны
- [ ] 9. Documentation updated
- [ ] 10. Final acceptance review complete

## Check Rules

- Architect создаёт чеклист и критерии приёмки.
- Executor agents отмечают пункты implementation и test только после запуска проверок.
- QA verifier отмечает final acceptance только после ревью evidence.
- Если проверка пропущена — остаётся unchecked с указанием причины.

---

## Контекст

Модальное окно создания/редактирования операции в Angular (`Warehouse_frontend`) должно быть доработано в двух аспектах:

1. **Порядок позиций:** добавляемые в операцию ТМЦ должны сохранять порядок добавления. Каждая строка должна иметь видимый порядковый номер, стабильный при сохранении/загрузке и корректно обновляемый при удалении.
2. **Заголовок секции позиций:** вместо `Позиции (N)` должно отображаться `Позиции: N, Всего: X`, где X — сумма quantity всех строк.

### Функциональные требования (из `Functional and WorkLogik.md`)

- Раздел 6: «Правила создания, редактирования и подтверждения операций» — черновик должен поддерживать произвольное добавление/удаление строк.
- Раздел 5.0: «таблица ТМЦ с поиском указанием количества» — таблица позиций является центральным элементом формы.
- Раздел 8: «кладовщик создаёт операцию -> добавляет построчно ТМЦ» — построчное добавление, порядок должен соответствовать порядку внесения.

Текущее состояние: данные требования выполняются частично — порядок в массиве сохраняется, но нет явного номера строки и нет суммы количеств в заголовке.

---

## Файлы в scope

| Файл | Назначение |
|------|------------|
| `Warehouse_frontend/src/app/core/models/operations.models.ts` | Модель `OperationLineDraftVm` — уже содержит `lineNumber?: number` (строка 227) |
| `Warehouse_frontend/src/app/core/services/operations.service.ts` | `buildPayload()` (строка 498) и `mapDtoToDraftVm()` (строка 217) |
| `Warehouse_frontend/src/app/core/services/operations.service.spec.ts` | Тесты сервиса |
| `Warehouse_frontend/src/app/features/operations/components/operation-create-modal/operation-create-modal.component.ts` | Основной компонент модалки: шаблон (строка 202), `lines` computed (строка 539), `onNewItemSelected` (строка 1026), `onInlineItemCreated` (строка 678), `onInlineSearchSelected` (строка 703), `removeLine` (строка 996) |
| `Warehouse_frontend/src/app/features/operations/components/operation-create-modal/operation-lines-table.component.ts` | Таблица позиций: шаблон заголовков (строка 38), тело таблицы (строка 61), `filteredSortedLines` (строка 305) |

## Файлы вне scope

- Бэкенд (`SyncServer/`, `Warehouse_web/`) — не трогаем, поле `line_number` уже есть в DTO
- Другие модальные окна и экраны (приёмка, issue-объекты)

---

## Implementation Level 1: lineNumber и колонка «№» в таблице (Work Unit A)

### A1. Модель — без изменений

Поле `lineNumber?: number` уже существует в `OperationLineDraftVm` (строка 227), добавлять ничего не нужно.

### A2. operation-create-modal.component.ts — присвоение lineNumber при создании строк

В трёх методах добавления строки нужно установить `lineNumber`:

**`onNewItemSelected` (строка 1031-1049):** Добавить в объект:
```typescript
lineNumber: d.lines.length + 1,
```

**`onInlineItemCreated` (строка 679-698):** Добавить:
```typescript
lineNumber: d.lines.length + 1,
```

**`onInlineSearchSelected` (строка 703-727):** Добавить:
```typescript
lineNumber: d.lines.length + 1,
```

### A3. operation-create-modal.component.ts — пересчёт lineNumber при удалении строки

**`removeLine` (строка 996-1000):** После фильтрации пересчитать lineNumber у оставшихся строк:
```typescript
removeLine(localId: string): void {
  this.localDraft.update(d => ({
    ...d,
    lines: d.lines
      .filter(l => l.localId !== localId)
      .map((l, idx) => ({ ...l, lineNumber: idx + 1 })),
  }));
}
```

### A4. operations.service.ts — buildPayload: использовать lineNumber для line_number

**`buildPayload` (строка 554-575):** Сейчас используется `line_number: idx + 1` на основе индекса в отфильтрованном массиве. Нужно заменить на использование `lineNumber` из исходной непроиндексированной линии. После фильтрации перенумеровать строки последовательно:
```typescript
.filter(l => l.quantity != null && l.quantity > 0 && (l.itemId || l.inlineItem))
.map((l, idx) => {
  const baseLine: Record<string, unknown> = {
    line_number: idx + 1,  // последовательная нумерация отфильтрованных строк
    qty: String(l.quantity),
  };
  // ...
})
```
Текущий код уже делает `line_number: idx + 1` — это правильно. Но важно, что после фильтрации нумерация идёт заново, а не используется исходный `lineNumber` (который мог иметь пропуски после удаления). Оставляем как есть — `idx + 1`.

### A5. operation-lines-table.component.ts — колонка «№»

**Шаблон (строка 38-58):** Добавить колонку `col-num` первой перед `col-name`:
```html
<th class="col-num">№</th>
```

**Тело таблицы (строка 61-112):** Добавить ячейку перед `col-name`:
```html
<td class="col-num">{{ line.lineNumber ?? '—' }}</td>
```

**Стили:** Добавить стиль для `.col-num`:
```css
.col-num { width: 40px; text-align: center; color: #94A3B8; font-size: 12px; white-space: nowrap; }
```

**`filteredSortedLines` (строка 305-329):** Не менять — сортировка пользователем остаётся рабочей. Но добавить `lineNumber` в список возможных колонок сортировки? Нет, это избыточно. По умолчанию строки отображаются в порядке массива `lines`, а не сортированными — это правильное поведение. Сортировка включается только по клику на заголовок.

**Важно:** Проверить, что `lines()` (строка 293) передаётся в таблицу как есть (в порядке массива). Да, так и есть (строка 205-206 в родителе: `[lines]="lines()"`).

### A6. operation-lines-table.component.ts — `colspan` в empty-state

При пустой таблице `colspan` сейчас `4` (строка 115). После добавления колонки «№» должно стать `5`:
```html
<td colspan="5" class="empty-state">
```

### A7. mapDtoToDraftVm — без изменений

`lineNumber: idx + 1` уже устанавливается (строка 242), этого достаточно.

### Acceptance criteria для Work Unit A

- [x] Каждая новая строка получает `lineNumber`, равный текущему количеству строк + 1
- [x] При удалении строки номера оставшихся перенумеровываются (1, 2, 3… без пропусков)
- [x] В таблице позиций отображается колонка «№» первой
- [x] При сохранении/загрузке операции порядок строк (и номера) сохраняются
- [x] `colspan` в empty-state обновлён до 5

---

## Implementation Level 2: «Всего» в заголовке (Work Unit B)

### B1. operation-create-modal.component.ts — computed `totalQuantity`

Добавить новый computed signal после `lines` (после строки 542):

```typescript
readonly totalQuantity = computed(() => {
  return this.localDraft().lines.reduce((sum, l) => sum + (l.quantity ?? 0), 0);
});
```

### B2. operation-create-modal.component.ts — шаблон

Изменить строку 202:
```html
<h3>Позиции ({{ lines().length }})</h3>
```
на:
```html
<h3>Позиции: {{ lines().length }}, Всего: {{ totalQuantity() }}</h3>
```

Примечание: `totalQuantity` — это число (сумма quantity), отображается как есть. Если нужна форматированная строка (например, `123.5` → `123,5`), можно использовать Angular `DecimalPipe`, но в текущем коде проекта форматирование не применяется для quantity. Оставляем as-is.

### Acceptance criteria для Work Unit B

- [x] Заголовок секции позиций показывает: `Позиции: N, Всего: X`
- [x] `X` = сумма `quantity` всех строк (null считается как 0)
- [x] При добавлении/удалении/изменении количества значение обновляется реактивно
- [x] При пустом списке показывает: `Позиции: 0, Всего: 0`

---

## Интеграционный чек (после выполнения Work Unit A и B)

- [x] Оба изменения не конфликтуют
- [x] `npm run build` проходит без ошибок
- [x] Модальное окно открывается, позиции добавляются/удаляются, заголовок обновляется

---

## Test Ladder

### Level 1: Static checks
```bash
cd Warehouse_frontend && npm run build
```
Ожидание: сборка без ошибок.

### Level 2: Unit tests
```bash
cd Warehouse_frontend && npm run test -- --watch=false
```
Проверить, что существующие тесты `operations.service.spec.ts` (особенно `mapDtoToDraftVm` и `buildPayload`) проходят.

### Level 3: Component tests
Не применимо — тестовый фреймворк для компонентов не инициализирован.

### Level 4: Integration tests (stand smoke)
На запущенном dev-стенде:
1. Открыть `/operations/` в браузере
2. Нажать «Создать операцию»
3. Добавить 3 позиции через поиск ТМЦ — проверить номера 1, 2, 3
4. Добавить 1 позицию через «Создать ТМЦ» — проверить номер 4
5. Проверить заголовок: `Позиции: 4, Всего: X` (X зависит от введённых quantity)
6. Удалить позицию №2 — проверить, что оставшиеся перенумерованы: 1, 2, 3
7. Заполнить quantity, сохранить черновик
8. Переоткрыть операцию — проверить, что порядок и номера сохранились

### Level 5: UI automation (Playwright)
Сценарии:
1. `create-operation-line-numbers.spec.ts` — проверка нумерации при добавлении/удалении
2. `create-operation-total-header.spec.ts` — проверка заголовка «Всего»

### Level 6: User scenarios
- Кладовщик создаёт операцию, добавляет 5 позиций, видит номера 1-5 и сумму
- Удаляет одну, номера пересчитываются, сумма обновляется
- Сохраняет черновик, переоткрывает — всё на месте
- Подтверждает операцию — в списке операций отображается корректно

### Level 7: Regression
- Существующие операции (созданные до изменений) открываются без ошибок
- Редактирование существующих операций не ломается
- Приёмка операций работает
- Фильтрация и сортировка таблицы позиций работают

---

## Stand Requirements

Dev-стенд должен быть запущен. Проверка:
```bash
curl -s --max-time 5 http://localhost:8000/api/v1/health && echo "SyncServer OK"
curl -s --max-time 5 http://localhost:8001/healthz/ && echo "Django OK"
```

Если стенд не запущен: `make up` из `/home/makc/AI_sandbox/warehouse_solution`.

После изменений Angular: `make build-angular` для пересборки и копирования бандла в Django.

---

## Риски

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| `lineNumber` конфликтует с серверным `line_number` при редактировании существующих строк | Низкая | Среднее | В `buildPayload` нумерация идёт заново (`idx + 1`), а не из `lineNumber`. Сервер принимает `line_number` как порядковый номер в запросе. |
| Сортировка таблицы пользователем сбивает с толку относительно порядка добавления | Средняя | Низкое | По умолчанию строки отображаются в исходном порядке. Сортировка — осознанное действие пользователя по клику на заголовок. |
| Изменение `colspan` ломает вёрстку | Низкая | Низкое | Проверить на стенде. |

---

## Architecture Review

**Дата:** 2026-06-17
**Рецензент:** Architect

### Вердикт: Approved — без блокеров

| Класс | Количество |
|-------|------------|
| 🔴 Blockers | 0 |
| 🟡 Warnings | 2 |
| 🔵 Notes | 1 |

### 🟡 Warnings

#### W1. Различие в формате заголовка
- **Checklist item:** Complexity — простейшее решение
- **Issue:** Формат `Позиции: N, Всего: X` (с двоеточием) отличается от текущего `Позиции (N)` (скобки). Пользователь в запросе указал формат с двоеточием.
- **Recommendation:** Реализовать `Позиции: N, Всего: X`. При приёмке уточнить у пользователя.

#### W2. Отсутствие форматирования числа `totalQuantity`
- **Checklist item:** Data & State — корректность отображения
- **Issue:** `totalQuantity` — сырой float. При суммах с артефактами IEEE 754 (например, `123.45600000000001`) отображение будет некрасивым. Такая же проблема существует во всех местах отображения quantity в проекте.
- **Recommendation:** Применить `Math.round(total * 1000) / 1000` или `DecimalPipe`. Не блокирует — существующая проблема, не регрессия.

### 🔵 Notes

#### N1. Совместимость с существующими операциями
- Загруженные через `mapDtoToDraftVm` строки уже имеют `lineNumber: idx + 1`. Новые строки без `lineNumber` (теоретически) покажут `—`. На практике все пути создания строк охвачены правками.
