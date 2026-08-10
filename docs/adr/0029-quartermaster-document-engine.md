# ADR-0029: Quartermaster Document Engine — Architecture and Lifecycle Boundaries

- **Status:** Proposed
- **Date:** 2026-08-06
- **Deciders:** пользователь, Architect Agent
- **Scope:** новая архитектура document rendering для SyncServer, Warehouse_web, WPF, Android, CLI, batch-задач и будущих offline-клиентов
- **Companion TZ:** `docs/TZ-QUARTERMASTER_DOCUMENT_ENGINE_ARCHITECTURE_AND_BACKEND_SPIKE.md` (создаётся следующим шагом)
- **Source research:** `docs/SPEC-QUARTERMASTER_DOCUMENT_ENGINE.md`, ADR-0001, ADR-0011, ADR-0016, ADR-0017, ADR-0018
- **Related decisions:** ADR-0001 (SyncServer как source of truth), ADR-0011 (Django ↔ SyncServer transport hardening), ADR-0016 (offline sync architecture), ADR-0017 (WPF via Rust core), ADR-0018 (audit architecture)
- **Supersedes:** ничего; настоящий ADR не отменяет существующие rendering pipelines до завершения spike и принятия migration plan

---

## Context

Текущее состояние document rendering:

1. **SyncServer** рендерит PDF через Jinja2 + WeasyPrint 66.0. Поддерживает `waybill`, `acceptance_certificate`, `act`, `invoice`. In-memory TTL cache.
2. **Warehouse_web (Django BFF)** рендерит PDF через Django templates + WeasyPrint 66.x. Поддерживает только `waybill`. Django cache. Модель `RenderedDocumentArtifact` со статусами рендера и SHA-256.

Оба контура получают документные данные и самостоятельно строят HTML/PDF. Это создаёт:

- Дублирование шаблонов и кода;
- Риск визуального и функционального рассинхрона;
- Различие в поддерживаемых типах документов между контурами;
- Двойную стоимость исправления ошибок и развития форм;
- Зависимость каждого клиента от собственного PDF pipeline;
- Сложность подключения WPF, Android, CLI, batch-задач и офлайн-режима.

Перспективные требования за пределами накладных и актов:

- Путевые листы автомобилей и техники;
- Месячные отчёты ГСМ;
- Складские и инвентаризационные отчёты;
- Любые печатные формы Quartermaster и смежных приложений.

Подтверждённые архитектурные ограничения:

- ADR-0001: SyncServer — единственный источник warehouse domain data. Все доменные writes идут через его services.
- ADR-0011: HTTP/JSON `/api/v1` — канонический Django ↔ SyncServer contract. SyncServer API остаётся публичным контрактом для всех клиентов.
- ADR-0016 / ADR-0017: будущие desktop/mobile offline-клиенты строятся вокруг `Warehouse_client_core` и не подключаются к SyncServer напрямую.

Настоящий ADR **не предрешает** выбор конкретного PDF backend. Кандидаты (WeasyPrint, Typst, опционально Chromium) оцениваются в spike на одинаковых fixtures с задокументированной матрицей критериев. ADR фиксирует **границы** компонента, **жизненный цикл** artifact'ов, **distribution model** и **метод** принятия технологического решения.

---

## Decision

### 1. Quartermaster Document Engine живёт в отдельном репозитории

- Репозиторий: `steeltalon777/QuartermasterDocumentEngine`.
- Не git submodule. Submodule создаёт вторую проблему синхронизации поверх первой и плохо ложится на платформенные release bundles.
- Не PyPI-пакет с шаблонами. Шаблоны поставляются как часть release bundle, а не как отдельный пакет.

Единица поставки — versioned release bundle для каждой платформы:

```text
quartermaster-document-engine-{distribution_version}-{platform}-{arch}.{tar.gz|zip}
├── engine executable/runtime
├── templates/
│   ├── warehouse-waybill-ru@2.0.0
│   ├── acceptance-certificate-ru@1.1.0
│   └── vehicle-route-sheet-ru@1.0.0
├── contracts/
├── fonts/
├── manifests/
└── checksums.json
```

Платформенно-независимая поставка позволяет не привязывать engine к конкретному host language: после spike distribution формируется под фактический host (Python или Rust) и backend (WeasyPrint или Typst).

SyncServer проверяет совместимость с engine через CI contract tests, но не хранит движок и шаблоны.

### 2. Версионирование имеет пять независимых осей

| Ось | Назначение | Кто меняет |
|---|---|---|
| `engine_version` | CLI и orchestration | Engine team |
| `backend_version` | Конкретный PDF backend (Typst, WeasyPrint) | Engine team + spike result |
| `document_contract` | Версия входного payload для семейства документов | Engine team + SyncServer owner |
| `template_version` | Версия конкретной формы | Template author |
| `distribution_version` | Совместимая сборка комплекта | Release process |

Новый template без изменения engine API всё равно создаёт новый distribution bundle. Это сохраняет воспроизводимость «один bundle = один проверяемый набор».

### 3. Engine — stateless consumer, не producer

Engine принимает самодостаточный документный envelope через CLI (stdin, file, stdout) или как Python/Rust library. Engine **не знает** про:

- `Operation`, `OperationLine`, `OperationRevisionLine`;
- SQLAlchemy, Django ORM, любые persistence-фреймворки;
- REST API SyncServer и любые сетевые вызовы во время рендера;
- Роли пользователей, авторизацию, бизнес-процессы;
- Persistent cache, audit storage, retry queues;
- Загрузку assets по сети во время базового рендера.

Engine может быть вызван из:

- CLI (напрямую, out-of-process);
- Python library (внутренний вызов из того же процесса Django);
- Long-lived worker'а (отдельный процесс);
- WPF / Android как out-of-process через CLI.

Renderer CLI **не получает** `document_id` для обращения к SyncServer. CLI принимает готовый JSON envelope и работает offline.

### 4. SyncServer — единственный producer доменного payload

SyncServer отвечает за:

- Доменные правила создания документа;
- Выбор `document_type`;
- Snapshot semantics, lifecycle (`draft` / `finalized` / `voided` / `supersede`);
- Построение immutable versioned payload;
- Сохранение payload и его хеша;
- Закрепление `template_id` и `template_version` в envelope.

Payload builder остаётся в SyncServer. Renderer не дополняет payload внешними данными. Любая попытка renderer обратиться к SyncServer / PostgreSQL / Django ORM во время рендера является нарушением контракта.

### 5. SyncServer выбирает `template_id` и `template_version`

SyncServer фиксирует `template_id` и `template_version` в envelope как **opaque identifiers**. SyncServer не проверяет физическое наличие template package в каком-либо deployment'е.

Render-host выполняет следующий flow:

1. Получает payload от клиента (Django, WPF, CLI).
2. Проверяет, установлен ли нужный template package в текущем bundle.
3. Вызывает engine.
4. Engine валидирует совместимость с `engine_contract_version` и `document_contract`.

Если template не установлен, engine возвращает машиночитаемую ошибку `TEMPLATE_NOT_INSTALLED`. Render-host решает реакцию (HTTP 503 клиенту, fallback на сохранённый PDF, запрос на установку bundle). SyncServer не участвует в этом решении.

### 6. Document envelope версионируется per-family

Контракты семейств документов (пример):

```text
warehouse.operation-document/v1..vN
transport.vehicle-route-sheet/v1
transport.equipment-route-sheet/v1
fuel.monthly-report/v1
inventory.balance-report/v1
```

Один гигантский payload запрещён. Семейства могут переиспользовать общие структуры из `contracts/common/`, но каждое семейство имеет собственный контракт и не обязано содержать чужие поля.

Обязательные правила envelope:

- `engine_contract_version` и `document_contract` версионируются независимо.
- `template_version` фиксируется в envelope или в render request.
- Renderer не дополняет отсутствующие бизнес-данные из внешних источников.
- Даты и числа передаются в однозначном машинном формате.
- Локализация форматирования выполняется renderer по `locale`.
- Денежные и количественные значения не передаются через binary float там, где критична точность.
- Assets — локальные, встроенные в bundle или переданные явно. Сетевые загрузки ресурсов во время базового рендера запрещены.

### 7. Backend — абстракция с конкретными реализациями

Renderer реализует общий логический интерфейс:

```text
render(
    normalized_document,
    template_package,
    output_format,
    render_options
) -> RenderResult
```

Backend-кандидаты Phase 0:

- **WeasyPrint 66** — baseline и migration backend. Сохраняется как минимум до конца обязательного периода воспроизводимости исторических PDF.
- **Typst** — основной кандидат на основной backend. Оценивается в spike.
- **Chromium / Paged.js** — рассматривается только при подтверждённой потребности. Без spike-обоснования в поставку не входит.

`RenderResult` содержит: bytes или путь к временному artifact, MIME type, page count, backend name и version, template id/version, document contract, SHA-256, warnings, render duration, диагностические metadata.

Backend **не должен**: обращаться к БД, выполнять авторизацию, хранить persistent cache, создавать audit-записи, выбирать бизнес-тип документа.

Выбор backend выполняет template registry по `manifest.backend`. Клиент указывает `document_contract` и `template_id`, но не выбирает backend явно. Это позволяет:

- Сохранить старые формы на WeasyPrint без переписывания клиентских интеграций;
- Развивать новые формы на Typst;
- Мигрировать шаблоны по одному;
- Не блокировать клиентов на смене backend.

**Настоящий ADR не объявляет победителя.** Решение фиксируется либо дополнением этого ADR после spike, либо отдельным ADR по результатам spike. ADR фиксирует метод, а не предсказание.

### 8. Django BFF — временный server-side render-host

На Phase 1–3 Django BFF остаётся server-side render-host'ом и владельцем `RenderedDocumentArtifact`. SyncServer не знает о готовности PDF — для него PDF является производным артефактом, а не частью доменного состояния документа.

Архитектура render-host'а **пересматривается** при появлении хотя бы одного trigger condition:

- Появился второй server-side consumer;
- Появился плановый или ночной batch-рендер;
- Нагрузка превышает 100 документов за одну batch-операцию;
- Нужна общая очередь рендера;
- Нужен общий object storage;
- Рендер должен запускаться без Django;
- Рендер заметно влияет на latency веб-запросов;
- Worker pool Django регулярно исчерпывается PDF-задачами;
- Требуется централизованный retry или приоритизация задач.

До появления любого trigger condition отдельный artifact service не создаётся.

### 9. Artifact lifecycle — immutable PDF предпочтительнее нового рендера

Политика:

1. Уже отрендеренный PDF не перерисовывается автоматически после обновления шаблона.
2. Artifact хранит полный набор воспроизводимых метаданных: `payload_hash`, `document_contract`, `template_id`, `template_version`, `engine_version`, `backend`, `backend_version`, `pdf_sha256`.
3. Новый рендер существующего документа создаёт **новую revision** artifact'а, а не молча заменяет старую.
4. Старые template packages хранятся в release archive столько, сколько нужна воспроизводимость. Срок хранения самих PDF определяется отдельной политикой retention по семейству документов и **не** фиксируется настоящим ADR.
5. Каждый опубликованный template package имеет SHA-256. Удаление или перезапись опубликованной версии запрещены.
6. Если PDF утрачен — recovery использует зафиксированные версии template package, manifest, contracts и совместимый engine bundle. Результат записывается как новая artifact revision с фиксацией причины.
7. Если PDF утрачен и template package утрачен — это критическая потеря архивных данных. Восстановление не выполняется молча на современном шаблоне.

Если сохранённый PDF существует — он предпочтительный источник выдачи, даже если `template_version` уже обновился. Клиент получает исторический PDF, а не его перерисованную копию.

### 10. CLI — primary integration contract

CLI принимает input через stdin или файл, отдаёт output через stdout или файл. Минимальные команды:

```bash
quartermaster-doc validate --input payload.json
quartermaster-doc render --input payload.json --output document.pdf
quartermaster-doc render --stdin --stdout --format pdf
quartermaster-doc inspect-template --template <id> --version <version>
quartermaster-doc capabilities
```

CLI обязан:

- Поддерживать JSON diagnostics и предсказуемые exit codes;
- Работать offline без обязательного сетевого соединения;
- Поддерживать Windows и Linux;
- Безопасно работать с временными файлами;
- Поддерживать режим строгой валидации;
- Выводить версию engine и backend.

JSON result при успехе включает: `status`, `engine_version`, `backend`, `backend_version`, `document_contract`, `template_id`, `template_version`, `format`, `pages`, `sha256`. При ошибке — `status`, `code`, `message`, `supported_contracts` (если применимо).

### 11. Шрифты и внешние ресурсы — часть воспроизводимой поставки

- Шрифты поставляются вместе с template package или engine distribution.
- Зависимость от шрифтов «установленных у пользователя» запрещена.
- Одинаковые версии шрифтов используются в Windows, Linux и контейнере.
- Лицензия шрифта допускает распространение.
- Перед spike обязателен аудит фактических шрифтов в текущих SyncServer и Django templates.
- Проверяются: кириллица, цифры, символы единиц, специальные знаки, fallback chain.
- Отсутствие ожидаемого шрифта — ошибка поставки, не повод молча использовать системный аналог.

---

## Consequences

### Pros

- Единый source of truth для document rendering устраняет дублирование шаблонов.
- Один engine для SyncServer, Django, WPF, Android, CLI, batch и будущих offline-клиентов.
- Версионированные template packages и immutable PDFs дают воспроизводимость архивных документов.
- CLI как primary integration contract не требует Python runtime в .NET/Android клиентах.
- Spike на трёх классах документов защищает от premature technology commitment.
- Trigger conditions для render-host архитектуры явно определены и falsifiable.
- Per-family contracts изолируют изменения между семействами.

### Cons / Risks

- Новый репозиторий требует собственного CI, релизного процесса и ownership.
- Миграция существующих Jinja2 templates на новый pipeline стоит времени и ручного труда.
- Visual regression harness, golden storage и SSIM policy требуют отдельной инфраструктуры.
- Spike может не дать явного победителя — нужна честная mixed-backend стратегия.
- Cold start CLI может конкурировать с warm render за latency budget в Django.
- Долгосрочное поддержание архива всех версий template packages требует дисциплины release-процесса.

---

## Rejected For Phase 0

### Git submodule в `QuartermasterDocumentEngine`

Отклонено: создаёт вторую проблему синхронизации поверх первой. Submodule плохо ложится на платформенные release bundles, затрудняет cross-repo CI и ownership.

### PyPI-пакет с шаблонами внутри

Отклонено: смешивает версионирование engine и templates, делает невозможной платформенную поставку одним артефактом, привязывает шаблоны к Python ecosystem.

### SyncServer как render-host

Отклонено: смешивает producer и consumer. Нарушает ADR-0001. Делает SyncServer зависимым от PDF pipeline, что не нужно для доменной логики.

### Renderer как long-lived server-side сервис с первого дня

Отклонено: преждевременное усложнение до появления trigger conditions (§8). На Phase 1–3 Django BFF достаточен.

### ADR фиксирует Typst как победителя backend заранее

Отклонено: spike должен быть источником решения. ADR фиксирует метод, а не предсказание.

### Один универсальный payload для всех семейств документов

Отклонено: транспортный документ не обязан содержать складские поля, а складская накладная не обязана знать про одометр. Per-family контракты изолируют эволюцию.

---

## Out of Scope

- Конкретный выбор PDF backend (Phase 0 spike).
- Вынесение рендера в отдельный artifact service (Phase 5, при trigger conditions §8).
- Электронная подпись, PKI, юридически значимый ЭДО.
- Визуальный конструктор шаблонов.
- Прямой рендер из SyncServer (Phase 0+ только Django, WPF, CLI).
- Миграция существующих Jinja2 templates на новый backend (Phase 2–3, после spike).
- Интеграция с регуляторными системами (Честный ЗНАК, ЕГАИС) до появления продуктового требования.
- Retention policy самих PDF по семействам документов (отдельная политика, не часть настоящего ADR).

---

## Implementation Spec

Исполнимая спецификация — `docs/TZ-QUARTERMASTER_DOCUMENT_ENGINE_ARCHITECTURE_AND_BACKEND_SPIKE.md` (создаётся следующим шагом).

TZ обязан включать:

- Чек-лист по `docs/AGENT_TZ_WORKFLOW.md` со всеми applicable уровнями test ladder.
- Конкретные spike-наборы: накладная 1 / 20 / 75 / 200 / 500 строк; путевой лист (1 авто, 1 водитель, 50 записей, 10 заправок); отчёт ГСМ 100 / 500 / 1500 строк, landscape.
- Concurrency benchmark: cold render, 10 sequential, 10 parallel, 50 через pool=4, p50/p95, peak memory.
- Performance SLA с target и hard limit для каждого сценария.
- Оценочную матрицу backend-кандидатов с весами.
- Visual regression policy: hard structural checks, SSIM ≥ 0.995, ≤ 0.5% pixels changed, нулевое расхождение в critical regions.
- Dispute policy: REVIEW_REQUIRED при непредусмотренном отличии, обновление golden только в составе осознанного template-version bump.
- Cross-platform smoke на Linux container и Windows 11.
- Стратегию миграции существующих Jinja2 templates через migration harness (одинаковые fixtures, рендер на оба backend, визуальный diff, ручной перенос), без автоматического конвертера.

---

## Confidence

- **High** для границ producer/consumer, distribution model, пяти осей версионирования, envelope, CLI contract, artifact lifecycle, trigger conditions render-host архитектуры.
- **Medium** для выбора backend (зависит от spike на трёх классах документов).
- **Medium** для конкретных performance SLA (требуют измерения baseline WeasyPrint на текущем стенде).
- **High** для политики иммутабельности PDF и архивирования template packages.
