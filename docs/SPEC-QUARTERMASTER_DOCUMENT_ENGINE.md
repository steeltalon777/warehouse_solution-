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

Renderer отвечает за физический размер страницы, поля, высоту строк, перенос текста, разбиение таблиц, повторяемые заголовки и подвалы, резервирование места под подписи, размещение финальных подписных блоков, номера страниц и ориентацию.

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

Клиент указывает документ, шаблон или render profile. Выбор конкретного backend выполняет template registry. Это позволяет сохранить существующие формы на WeasyPrint, разрабатывать новые формы на Typst или другом движке, мигрировать шаблоны по одному и не переписывать интеграции клиентов при смене backend.

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
│   └── chromium/
├── cli/
├── tests/
│   ├── fixtures/
│   ├── golden/
│   ├── compatibility/
│   └── determinism/
└── docs/
```

Фактическая структура может отличаться в зависимости от выбранного языка, но границы модулей должны сохраниться.

## 7. Document Envelope

Общий envelope содержит маршрутизационные и версионные данные, но не заменяет конкретный контракт документа.

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

## 8. Template Package и registry

Каждый шаблон является версионированным пакетом с manifest.

```yaml
template_id: warehouse-waybill-ru
template_version: 2.0.0
document_contract: warehouse.operation-document/v2
backend: typst
entrypoint: main.typ
outputs: [pdf, png]
locales: [ru-RU]
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

## 9. Интерфейс backend

```text
render(
    normalized_document,
    template_package,
    output_format,
    render_options
) -> RenderResult
```

`RenderResult` содержит bytes или путь к artifact, MIME type, page count, backend name/version, template id/version, document contract, SHA-256, warnings, render duration и диагностические metadata.

Backend не должен обращаться к БД, выполнять авторизацию, хранить persistent cache, создавать audit-записи прикладной системы или выбирать бизнес-тип документа.

## 10. CLI contract

```bash
quartermaster-doc validate --input payload.json
quartermaster-doc render --input payload.json --output document.pdf
quartermaster-doc render --stdin --stdout --format pdf
quartermaster-doc inspect-template --template warehouse-waybill-ru --version 2.0.0
quartermaster-doc capabilities
```

CLI должно поддерживать input через файл и stdin, output через файл и stdout, JSON diagnostics, предсказуемые exit codes, отсутствие обязательного сетевого соединения, Windows и Linux, безопасную работу с временными файлами и режим строгой валидации.

## 11. Границы cache, audit и artifact storage

В renderer core не входят Redis, Django cache, `RenderedDocumentArtifact`, сохранение PDF, retry scheduler, привязка artifact к пользователю и бизнес-аудит.

Host / Artifact Service отвечает за cache key, persistent storage, статусы `RENDERING`, `READY`, `FAILED`, retry, audit, права доступа, связь artifact с документом, удаление и решение о повторном рендере.

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

## 12. Кандидаты технологий

Окончательный выбор выполняется после spike.

### 12.1. Python + WeasyPrint

Плюсы: максимальный reuse текущего кода, быстрый путь к устранению дублирования, HTML preview.

Минусы: системные зависимости, сложная Windows-упаковка, CSS pagination и риск сохранения текущих проблем формы.

### 12.2. Python host + Typst backend

Плюсы: удобный registry/CLI, Typst ориентирован на печатную вёрстку, шаблоны не зависят от Python, host позднее можно заменить на Rust.

Минусы: новый стек шаблонов, необходимость проверить кириллицу, таблицы, переносы, сложные формы и preview.

### 12.3. Rust host + Typst

Плюсы: строгий единый CLI, поставка для WPF/Linux, типизация контрактов, потенциальное встраивание Typst.

Минусы: выше стоимость первой версии, меньше reuse и риск преждевременного ухода в FFI/JNI.

### 12.4. Chromium / Paged.js

Плюсы: зрелая HTML/CSS экосистема, мощный preview, удобство веб-разработки.

Минусы: тяжёлая поставка, браузерный runtime, расход памяти и слабее автономный desktop/offline сценарий.

### 12.5. Прямое программное построение PDF

ReportLab, printpdf, pdf-writer и аналоги рассматривать только для узких специализированных задач. Не выбирать основным направлением без доказанной необходимости.

## 13. Обязательный сравнительный spike

### 13.1. Многостраничная складская накладная MOVE

Проверить 3–4 страницы, правила первой/средней/последней страницы, повтор шапки, подписи, длинные названия, кириллицу, физические поля и детерминированность.

### 13.2. Путевой лист автомобиля

Проверить строгую сетку, рамки, компактную типографику, подписи, даты/время, одометр, данные водителя/автомобиля и пригодность для ручного заполнения.

### 13.3. Месячный отчёт ГСМ

Проверить длинную таблицу, группировки, итоги, landscape, повторяемые заголовки, десятичные значения, простой график и preview.

## 14. Критерии сравнения backend

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

Результат spike оформляется отдельным документом с измерениями, эталонными файлами, обнаруженными ограничениями и итоговой рекомендацией.

## 15. Тестовая стратегия

Обязательны:

- contract tests;
- golden tests;
- determinism tests;
- compatibility tests;
- Windows 11 smoke;
- Linux container smoke;
- пути и данные с кириллицей;
- offline mode;
- работа без установленных пользовательских шрифтов.

## 16. Миграционная стратегия

### Phase 0. ADR и spike

Утвердить границы, envelope, сравнить backend и принять решение по host/backend.

### Phase 1. Standalone engine skeleton

CLI, registry, validation, один backend, один template package и golden tests.

### Phase 2. Накладная

Перенести канонический шаблон, обеспечить parity, переключить один host и устранить дублирование.

### Phase 3. Все текущие складские документы

Waybill, acceptance certificate, act, invoice и удаление старых pipeline после стабилизации.

### Phase 4. Новые семейства

Путевые листы, ГСМ, инвентаризационные и управленческие отчёты.

### Phase 5. Дополнительная упаковка

Только при доказанной необходимости: Rust host, embedded engine, FFI, JNI или отдельный artifact service.

## 17. Требования к ADR

ADR должен зафиксировать:

1. SyncServer как producer domain payload.
2. `documents.payload` как source of truth для renderer.
3. renderer как stateless consumer.
4. разделение document contracts по семействам.
5. versioned template packages.
6. backend abstraction.
7. отсутствие cache/audit/storage в core.
8. CLI как первичный integration contract.
9. правила обратной совместимости.
10. результат spike и технологическое решение.

Номер ADR определить по фактической последовательности репозитория.

## 18. Deliverables

1. ADR о standalone modular document engine.
2. JSON Schema общего envelope.
3. Черновые schemas трёх spike-документов.
4. Backend interface specification.
5. CLI contract.
6. Template manifest schema.
7. Три минимальных шаблона для spike.
8. Comparative report.
9. Выбранный backend и язык host с обоснованием.
10. Migration plan для SyncServer и Warehouse_web.
11. Перечень старого кода для последующего удаления.
12. Follow-up implementation issues.

## 19. Acceptance Criteria

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
- [ ] сформирован migration plan;
- [ ] созданы follow-up implementation issues.

## 20. Definition of Done

- ADR принят.
- Контракты и manifests находятся под version control.
- Spike воспроизводим одной documented командой.
- Результаты spike доступны в репозитории.
- Выбранный вариант подтверждён тремя классами документов.
- Архитектура не привязана к Django, FastAPI, ORM или конкретному UI.
- Старые документы не меняют внешний вид без смены `template_version`.
- Следующий исполнитель может начать Phase 1 без повторного архитектурного исследования.
