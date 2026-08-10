# SPEC: Quartermaster Document Engine

**Статус:** Ready for implementation planning  
**Тип задачи:** архитектурное проектирование + технический spike  
**Область:** Quartermaster / Warehouse Solution  
**Дата:** 2026-08-06

---

## 1. Контекст

В системе существуют два независимых контура рендеринга PDF:

1. **SyncServer**
   - Jinja2 templates;
   - WeasyPrint 66.0;
   - поддерживаются `waybill`, `acceptance_certificate`, `act`, `invoice`;
   - in-memory TTL cache.

2. **Warehouse_web (Django BFF)**
   - Django templates;
   - WeasyPrint 66.x;
   - поддерживается только `waybill`;
   - Django cache;
   - модель `RenderedDocumentArtifact` со статусами рендера и SHA-256 результата.

Оба контура получают документные данные и самостоятельно строят HTML/PDF. Это создаёт:

- дублирование шаблонов и кода;
- риск визуального и функционального рассинхрона;
- различия в поддерживаемых типах документов;
- двойную стоимость исправления ошибок и развития форм;
- зависимость каждого клиента от собственного PDF pipeline;
- сложности с подключением WPF, Android, CLI, batch-задач и офлайн-режима.

Планируемый компонент должен развиваться не только как renderer накладных. В перспективе он должен обслуживать:

- накладные;
- акты;
- приёмочные документы;
- путевые листы автомобилей и техники;
- отчёты ГСМ;
- складские и инвентаризационные отчёты;
- иные печатные формы Quartermaster и смежных приложений.

---

## 2. Цель

Спроектировать и подготовить к реализации универсальный модульный **Quartermaster Document Engine**, который:

1. принимает версионированный самодостаточный документный payload;
2. валидирует его по публичному контракту;
3. выбирает зарегистрированный шаблон и backend;
4. детерминированно формирует PDF и при необходимости preview-форматы;
5. запускается как автономное CLI;
6. одинаково используется SyncServer, Django, WPF, Android и служебными сценариями;
7. допускает подключение нескольких renderer backend без изменения клиентского контракта;
8. позволяет добавлять новые семейства документов без разрастания единого универсального payload.

---

## 3. Не-цели

В эту задачу не входят:

- перенос доменной логики операций из SyncServer;
- получение документа из SyncServer по UUID внутри renderer core;
- доступ renderer к PostgreSQL или моделям ORM;
- принятие решения, какой документ должен быть создан при submit операции;
- хранение токенов и выполнение авторизации;
- перенос аудита рендера в общий core;
- обязательный немедленный перевод всех существующих форм на новый backend;
- реализация визуального конструктора шаблонов;
- электронная подпись, PKI и юридически значимый ЭДО;
- окончательный выбор языка или PDF backend без сравнительного spike.

---

## 4. Архитектурные принципы

### 4.1. SyncServer остаётся producer документа

SyncServer отвечает за:

- доменные правила создания документа;
- выбор `document_type`;
- работу с операциями и ревизиями;
- snapshot semantics;
- draft/finalized/voided/supersede lifecycle;
- построение immutable versioned payload;
- сохранение payload и его хеша.

Payload builder остаётся в SyncServer. Он не переносится в renderer core.

### 4.2. Renderer является stateless consumer

Renderer получает готовый документный контракт и не знает о:

- `Operation`;
- `OperationLine`;
- `OperationRevisionLine`;
- SQLAlchemy;
- Django ORM;
- REST API SyncServer;
- ролях пользователей;
- статусах бизнес-процессов, кроме уже отражённых в payload.

Базовая модель:

```text
Domain entities / revisions
          ↓
SyncServer Payload Builder
          ↓
Immutable Document Payload
          ↓
Quartermaster Document Engine
          ↓
PDF / preview artifact
```

### 4.3. Пагинация является частью renderer

Renderer отвечает за:

- физический размер страницы;
- поля;
- высоту строк;
- перенос текста;
- разбиение таблиц;
- повторяемые заголовки и подвалы;
- резервирование места под подписи;
- размещение финальных подписных блоков;
- номера страниц;
- ориентацию;
- многостраничные правила конкретного шаблона.

### 4.4. Один гигантский payload запрещён

Каждое семейство документов получает отдельный контракт:

```text
warehouse.operation-document/v1
transport.vehicle-route-sheet/v1
transport.equipment-route-sheet/v1
fuel.monthly-report/v1
inventory.balance-report/v1
```

Общие структуры могут переиспользоваться, но транспортный документ не обязан содержать складские поля, а складская накладная не обязана знать про одометр и путевые точки.

### 4.5. Backend не является частью публичного клиентского API

Клиент указывает документ, шаблон или render profile. Выбор конкретного backend выполняет template registry.

Это позволяет:

- сохранить существующие формы на WeasyPrint;
- разрабатывать новые формы на Typst или другом движке;
- мигрировать шаблоны по одному;
- не переписывать интеграции клиентов при смене backend.

---

## 5. Целевая архитектура

```text
┌─────────────────────────────────────────────┐
│ Clients / Hosts                             │
│ SyncServer | Django | WPF | Android | CI    │
└──────────────────────┬──────────────────────┘
                       │ JSON / stdin / file
┌──────────────────────▼──────────────────────┐
│ CLI / Host Adapter                          │
│ arguments, stdin/stdout, exit codes         │
└──────────────────────┬──────────────────────┘
                       │
┌──────────────────────▼──────────────────────┐
│ Document Engine                             │
│ registry | validation | normalization       │
│ assets | localization | backend selection   │
└──────────────┬──────────────────────────────┘
               │ Presentation Model
┌──────────────▼──────────────────────────────┐
│ Renderer Backends                           │
│ WeasyPrint | Typst | optional Chromium      │
└──────────────┬──────────────────────────────┘
               │
┌──────────────▼──────────────────────────────┐
│ Artifacts                                   │
│ PDF | HTML | SVG | PNG | metadata           │
└─────────────────────────────────────────────┘
```

---

## 6. Предлагаемая структура компонента

```text
quartermaster_document_engine/
├── contracts/
│   ├── envelope/
│   ├── common/
│   ├── warehouse/
│   ├── transport/
│   ├── fuel/
│   └── inventory/
├── templates/
│   ├── warehouse-waybill-ru/
│   ├── acceptance-certificate-ru/
│   ├── write-off-act-ru/
│   ├── vehicle-route-sheet-ru/
│   └── fuel-monthly-report-ru/
├── engine/
│   ├── registry/
│   ├── validation/
│   ├── normalization/
│   ├── localization/
│   ├── assets/
│   ├── errors/
│   └── rendering/
├── backends/
│   ├── weasyprint/
│   ├── typst/
│   └── chromium/              # только при подтверждённой необходимости
├── cli/
├── tests/
│   ├── fixtures/
│   ├── golden/
│   ├── compatibility/
│   └── determinism/
└── docs/
```

Фактическая структура может отличаться в зависимости от выбранного языка, но границы модулей должны сохраниться.

---

## 7. Document Envelope

Общий envelope содержит маршрутизационные и версионные данные, но не заменяет конкретный контракт документа.

Пример:

```json
{
  "engine_contract_version": "1.0.0",
  "document_contract": "warehouse.operation-document/v2",
  "document_type": "waybill",
  "template_id": "warehouse-waybill-ru",
  "template_version": "2.0.0",
  "locale": "ru-RU",
  "render_profile": "print",
  "document_id": "uuid",
  "document_number": "210726/1430/1",
  "document": {},
  "assets": {}
}
```

Обязательные правила:

- `document_contract` версионируется независимо от engine;
- `template_version` фиксируется в метаданных документа или render request;
- renderer не дополняет отсутствующие бизнес-данные из внешних источников;
- даты и числа передаются в однозначном машинном формате;
- локализация форматирования выполняется renderer по `locale`;
- денежные и количественные значения не должны передаваться через binary float там, где критична точность;
- assets должны быть локальными, встроенными либо переданными явно;
- сетевые загрузки ресурсов во время базового render запрещены.

---

## 8. Template Package и registry

Каждый шаблон является версионированным пакетом с manifest.

Пример:

```yaml
template_id: warehouse-waybill-ru
template_version: 2.0.0
document_contract: warehouse.operation-document/v2
backend: typst
entrypoint: main.typ

outputs:
  - pdf
  - png

locales:
  - ru-RU

paper:
  format: A4
  orientation: portrait

assets:
  fonts:
    - NotoSans-Regular.ttf
    - NotoSans-Bold.ttf

capabilities:
  multi_page_tables: true
  page_preview: true
```

Registry обязан:

- находить шаблон по `template_id` и версии;
- проверять совместимость с `document_contract`;
- выбирать backend;
- проверять наличие ресурсов;
- запрещать неявную подмену версии шаблона;
- возвращать машиночитаемую ошибку при несовместимости.

---

## 9. Интерфейс backend

Backend должен реализовывать общий логический интерфейс:

```text
render(
    normalized_document,
    template_package,
    output_format,
    render_options
) -> RenderResult
```

`RenderResult` содержит:

- bytes или путь к временному artifact;
- MIME type;
- page count, если доступно;
- renderer backend name;
- backend version;
- template id/version;
- document contract;
- SHA-256;
- warnings;
- render duration;
- дополнительные диагностические metadata.

Backend не должен:

- обращаться к БД;
- выполнять авторизацию;
- хранить persistent cache;
- создавать audit-записи прикладной системы;
- выбирать бизнес-тип документа.

---

## 10. CLI contract

Минимальные команды:

```bash
quartermaster-doc validate \
  --input payload.json

quartermaster-doc render \
  --input payload.json \
  --output document.pdf

quartermaster-doc render \
  --stdin \
  --stdout \
  --format pdf

quartermaster-doc inspect-template \
  --template warehouse-waybill-ru \
  --version 2.0.0

quartermaster-doc capabilities
```

CLI должно поддерживать:

- input через файл и stdin;
- output через файл и stdout;
- JSON diagnostics;
- предсказуемые exit codes;
- отсутствие обязательного сетевого соединения;
- относительные и абсолютные пути;
- Windows и Linux;
- безопасную работу с временными файлами;
- режим строгой валидации;
- вывод версии engine и backend.

Пример успешного JSON result:

```json
{
  "status": "success",
  "engine_version": "0.1.0",
  "backend": "typst",
  "backend_version": "x.y.z",
  "document_contract": "warehouse.operation-document/v2",
  "template_id": "warehouse-waybill-ru",
  "template_version": "2.0.0",
  "format": "application/pdf",
  "pages": 3,
  "sha256": "..."
}
```

Пример ошибки:

```json
{
  "status": "error",
  "code": "UNSUPPORTED_DOCUMENT_CONTRACT",
  "message": "warehouse.operation-document/v3 is not supported",
  "supported_contracts": [
    "warehouse.operation-document/v1",
    "warehouse.operation-document/v2"
  ]
}
```

---

## 11. Границы cache, audit и artifact storage

### В renderer core не входят

- Redis;
- Django cache;
- ORM-модель `RenderedDocumentArtifact`;
- сохранение PDF в БД или object storage;
- retry scheduler;
- привязка artifact к пользователю;
- бизнес-аудит.

### Host / Artifact Service отвечает за

- cache key;
- persistent artifact storage;
- статусы `RENDERING`, `READY`, `FAILED`;
- retry;
- audit;
- права доступа;
- связь artifact с документом;
- политику удаления;
- проверку существующего SHA-256;
- решение о повторном рендере.

Рекомендуемый cache key:

```text
document_payload_hash
+ document_contract
+ template_id
+ template_version
+ engine_version
+ backend_version
+ output_format
+ render_profile
```

---

## 12. Кандидаты технологий

Окончательный выбор выполняется после spike.

### 12.1. Python + WeasyPrint

Плюсы:

- максимальное повторное использование текущего кода;
- существующий опыт;
- Jinja2 и Django templates легко свести к одному engine;
- быстрый путь к устранению дублирования;
- HTML preview.

Минусы:

- системные зависимости;
- упаковка для Windows требует отдельной проверки;
- особенности CSS pagination;
- риск сохранения текущих проблем формы;
- сложные фиксированные бланки могут требовать большого количества CSS-подгонки.

### 12.2. Python host + Typst backend

Плюсы:

- Python удобно использовать для registry, JSON Schema, CLI и миграции;
- Typst ориентирован на печатную вёрстку;
- шаблоны не зависят от Python;
- позднее host можно заменить на Rust без переписывания контрактов и `.typ` шаблонов;
- перспективен для путевых листов, отчётов и строгих форм.

Минусы:

- новый шаблонизатор и новый стек;
- необходимо проверить кириллицу, таблицы, переносы и сложные формы;
- preview и миграция текущих HTML-шаблонов требуют отдельной стратегии;
- возможна зависимость от внешнего бинарника Typst либо его встраивания.

### 12.3. Rust host + Typst

Плюсы:

- единый строгий CLI;
- удобная поставка для WPF и Linux;
- сильная типизация контрактов;
- потенциальное встраивание Typst;
- отсутствие Python runtime в конечной поставке.

Минусы:

- выше стоимость первой версии;
- меньше reuse текущей реализации;
- сложнее итерации на этапе исследования;
- FFI/JNI не должны становиться преждевременной целью.

### 12.4. Chromium / Paged.js

Плюсы:

- зрелая HTML/CSS экосистема;
- мощный preview;
- удобен для сложных веб-отчётов;
- доступна привычная фронтенд-разработка.

Минусы:

- тяжёлая поставка;
- браузерный runtime;
- расход памяти;
- сложнее автономный desktop/offline сценарий;
- увеличенная поверхность обновления и безопасности.

### 12.5. Прямое программное построение PDF

Примеры: ReportLab, printpdf, pdf-writer и аналоги.

Рассматривать только для узких специализированных задач.

Не выбирать основным направлением без доказанной необходимости, поскольку engine придётся самостоятельно реализовывать:

- перенос текста;
- таблицы;
- пагинацию;
- повтор шапок;
- типографику;
- раскладку подписей;
- обработку шрифтов;
- правила разрыва блоков.

---

## 13. Обязательный сравнительный spike

Для сравнения backend необходимо реализовать минимальные версии трёх принципиально разных документов.

### 13.1. Многостраничная складская накладная MOVE

Проверить:

- 3–4 страницы;
- полный заголовок только на первой странице;
- сокращённый заголовок на последующих;
- повтор заголовка таблицы;
- подпись кладовщика на каждой странице;
- расширенный блок подписей на последней странице;
- длинные названия ТМЦ;
- кириллицу;
- точные физические поля;
- детерминированность результата.

### 13.2. Путевой лист автомобиля

Проверить:

- большое количество отдельных полей;
- строгую сетку;
- рамки;
- компактную типографику;
- подписи;
- даты и время;
- показания одометра;
- данные водителя и автомобиля;
- печать на A4;
- пригодность для ручного заполнения оставшихся полей.

### 13.3. Месячный отчёт ГСМ

Проверить:

- длинную таблицу;
- группировки;
- промежуточные и итоговые суммы;
- несколько страниц;
- landscape orientation;
- повторяемые заголовки;
- десятичные значения;
- возможность вставки простого графика или диаграммы;
- экспорт preview.

---

## 14. Критерии сравнения backend

Каждый кандидат оценивается по единой матрице:

| Критерий | Вес |
|---|---:|
| Качество и предсказуемость PDF | 20 |
| Многостраничные таблицы и пагинация | 15 |
| Строгие формы и физическая геометрия | 15 |
| Простота разработки шаблонов | 10 |
| Windows deployment | 10 |
| Linux/container deployment | 8 |
| Offline suitability | 7 |
| Кириллица и управление шрифтами | 5 |
| Preview formats | 4 |
| Скорость рендера | 3 |
| Размер поставки | 2 |
| Зрелость и сопровождаемость | 1 |

Результат spike оформляется отдельным документом с:

- измерениями;
- скриншотами или golden PDF;
- обнаруженными ограничениями;
- итоговой рекомендацией;
- причиной отклонения остальных кандидатов.

---

## 15. Тестовая стратегия

### 15.1. Contract tests

- валидный payload принимается;
- обязательные поля проверяются;
- неизвестная major-версия отклоняется;
- compatible minor-версия обрабатывается по принятой политике;
- некорректные числа и даты отклоняются;
- внешние сетевые assets запрещаются.

### 15.2. Golden tests

Для каждого шаблона хранить:

- fixture payload;
- ожидаемый page count;
- эталонный PDF либо визуальные page snapshots;
- извлечённый текст для semantic check;
- ожидаемые metadata.

### 15.3. Determinism tests

Одинаковые:

- payload;
- template;
- fonts;
- engine version;
- backend version;
- render options

должны формировать одинаковый SHA-256 либо документ, эквивалентный по заранее определённой политике нормализации metadata.

### 15.4. Compatibility tests

- старые payload v1.0/v1.1 продолжают рендериться;
- migration/adapter явно тестируется;
- обновление нового template version не меняет старый versioned template;
- отсутствие старого шаблона считается ошибкой поставки, а не поводом молча использовать новый.

### 15.5. Cross-platform smoke

Обязательные среды:

- Linux container;
- Windows 11;
- кодировка и пути с кириллицей;
- offline mode;
- отсутствие установленных пользовательских шрифтов.

---

## 16. Миграционная стратегия

### Phase 0. ADR и spike

- утвердить границы компонента;
- зафиксировать document envelope;
- сравнить backend;
- принять решение по языку host и основному backend.

### Phase 1. Standalone engine skeleton

- CLI;
- registry;
- validation;
- один backend;
- один template package;
- fixtures и golden tests.

### Phase 2. Накладная

- перенести канонический шаблон накладной;
- обеспечить функциональный паритет;
- переключить один host;
- сравнить результаты;
- устранить дублирование шаблонов.

### Phase 3. Все текущие складские документы

- waybill;
- acceptance certificate;
- act;
- invoice;
- единый registry;
- удаление старых renderer pipeline после стабилизации.

### Phase 4. Новые семейства

- путевые листы;
- ГСМ;
- инвентаризационные и управленческие отчёты.

### Phase 5. Дополнительная упаковка

Только при доказанной необходимости:

- Rust host;
- embedded engine;
- FFI для WPF;
- JNI для Android;
- server-side artifact service.

---

## 17. Требования к первому ADR

Новый ADR должен зафиксировать:

1. SyncServer как единственный producer domain payload.
2. `documents.payload` как source of truth для renderer.
3. renderer как stateless consumer.
4. разделение document contracts по семействам.
5. versioned template packages.
6. backend abstraction.
7. отсутствие cache/audit/storage в core.
8. CLI как первичный универсальный integration contract.
9. правила обратной совместимости.
10. результат сравнительного spike и принятое технологическое решение.

Номер ADR определить по фактической последовательности репозитория. Нельзя заранее жёстко использовать `ADR-0024`, если этот номер уже занят.

---

## 18. Deliverables

Результатом задачи должны стать:

1. ADR о standalone modular document engine.
2. JSON Schema общего envelope.
3. черновые schemas трёх spike-документов.
4. формальная backend interface specification.
5. CLI contract.
6. template package manifest schema.
7. три минимальных шаблона для spike.
8. comparative report по backend.
9. выбранный основной backend и язык host с обоснованием.
10. migration plan для SyncServer и Warehouse_web.
11. перечень старого кода, который позднее подлежит удалению.
12. отдельные follow-up задачи на реализацию этапов.

---

## 19. Acceptance Criteria

Задача считается выполненной, если:

- [ ] обследованы оба текущих renderer pipeline;
- [ ] подтверждено и описано фактическое дублирование;
- [ ] зафиксирована граница producer/consumer;
- [ ] payload builder остаётся в SyncServer;
- [ ] определён versioned document envelope;
- [ ] определена модель отдельных contract families;
- [ ] описан template registry и manifest;
- [ ] описан backend interface;
- [ ] определён CLI contract с stdin/stdout и JSON errors;
- [ ] cache, audit и artifact storage исключены из core;
- [ ] реализованы три spike-документа;
- [ ] минимум два реальных backend сравнены на одних fixtures;
- [ ] выполнен Windows smoke;
- [ ] выполнен Linux/container smoke;
- [ ] проверена работа без сети;
- [ ] оформлена сравнительная матрица;
- [ ] принято и документировано технологическое решение;
- [ ] сформирован поэтапный migration plan;
- [ ] созданы follow-up implementation issues.

---

## 20. Definition of Done

- ADR принят.
- Контракты и manifests находятся под version control.
- Spike воспроизводим одной documented командой.
- Результаты spike приложены или доступны в репозитории.
- Выбранный вариант подтверждён не одной накладной, а тремя классами документов.
- Архитектура не привязана к Django, FastAPI, ORM или конкретному UI.
- Существующие документы не меняют внешний вид задним числом без смены `template_version`.
- Следующий исполнитель может начать реализацию Phase 1 без повторного архитектурного исследования.
