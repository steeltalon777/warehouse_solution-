# ADR-0031: QuartermasterDocumentEngine — Ownership and Versioning

- **Status:** Proposed
- **Date:** 2026-08-15
- **Deciders:** пользователь, Architect Agent
- **Scope:** как `QuartermasterDocumentEngine` живёт в version control и как Warehouse Solution его потребляет
- **Supersedes:** ADR-0029 §1 (отменяет «отдельный репозиторий steeltalon777/QuartermasterDocumentEngine» как целевую долгосрочную модель)
- **Related decisions:** ADR-0029 §1 (rejected git submodule, PyPI package); AUDIT-2026-08-10 ARC-08 (untracked сосед, вне CI)

---

## Context

1. **Текущее состояние**: `QuartermasterDocumentEngine/` — отдельный git-репозиторий (nested в `warehouse_solution/`), в root-repo отображается как `?? untracked`. Собственный `.venv` (~0.5 ГБ), собственный CI **отсутствует**.
2. **AUDIT-2026-08-10 ARC-08** фиксирует: «Untracked-компоненты (QuartermasterDocumentEngine, warehouse-storekeeper) имеют локальные тесты, но вне CI и вне контроля версий». Это P3 hardening долг.
3. **ADR-0029 §1** (Quartermaster Document Engine architecture) явно отклонил:
   - **Git submodule**: «создаёт вторую проблему синхронизации поверх первой; submodule плохо ложится на платформенные release bundles».
   - **PyPI-пакет с шаблонами**: «смешивает версионирование engine и templates, делает невозможной платформенную поставку одним артефактом».
4. **Текущая рекомендация задачи** (от пользователя): «не предлагать комбинацию вида "не submodule, но gitlink + lockfile" без объяснения, поскольку gitlink является частью механики submodule». Это отсекает гибридные варианты.
5. **Phase 2 evidence**: QDE развивается в темпе Warehouse Solution. За 14 дней прошёл 5 крупных итераций (Phase 1, Phase 2 T1-T8, Phase 2 T9-T12, Phase 2.1, Phase 2.1.1, Phase 2.1.2 — коммиты `b305eb3`...`31b774a`). Никакой внешней coordination overhead не было.
6. **Реальная независимость жизненного цикла QDE отсутствует в проекте**: ни одного внешнего consumer нет. Warehouse Solution — единственный пользователь QDE.

---

## Decision

### D1. **Monorepo**. QDE входит в `warehouse_solution` как `QuartermasterDocumentEngine/` подкаталог.

- QDE остаётся **логически обособленным компонентом**: собственный `pyproject.toml`, `engine/`, `backends/`, `cli/`, `tests/`, `doc/`, `contracts/`, `templates/`, `fonts/`.
- В корневом `pyproject.toml` (workspace level, если появится) QDE остаётся отдельным пакетом.
- QDE собственный CHANGELOG.md и ROADMAP продолжают жить в `QuartermasterDocumentEngine/doc/`.
- В Phase 6 **только `Warehouse_web` потребляет QDE как установленный Python package внутри своего Docker image**. `SyncServer` QDE не устанавливает и не вызывает; он сохраняет существующий legacy direct-render path согласно ADR-0032 D4. Это не меняет monorepo ownership: исходники QDE находятся в общем root-repo, но runtime dependency появляется только там, где QDE реально используется.

### D2. **Сильные подкаталоговые границы**

```text
warehouse_solution/
├── QuartermasterDocumentEngine/     ← self-contained component
│   ├── pyproject.toml               ← own deps, own version
│   ├── engine/  backends/  cli/     ← no Warehouse imports here
│   ├── contracts/  templates/  fonts/
│   ├── tests/
│   └── doc/  ROADMAP  CHANGELOG
├── SyncServer/                      ← owns warehouse domain
├── Warehouse_web/                   ← BFF + render-host for QDE
├── Warehouse_frontend/              ← Angular SPA
└── ...
```

Правило границы: **QDE не импортирует `warehouse_solution`-specific код**. Обратная зависимость `Warehouse_web → QDE` разрешена; `QDE → Warehouse_web` запрещена. Это уже enforce'ится в QDE Phase 1 (`backends/` не знает про Django ORM) и сохраняется.

### D3. **CI pipeline — один репозиторий, разные jobs**

- `.github/workflows/` или эквивалент запускает:
  - `qde-unit`: `pytest QuartermasterDocumentEngine/tests/unit` на каждое изменение в `QuartermasterDocumentEngine/**`.
  - `qde-integration`: `pytest QuartermasterDocumentEngine/tests/integration + component` с pinned Typst binary.
  - `qde-golden`: `pytest -m golden` (с LFS или JSON-fallback — Phase 2.1 политика).
  - `syncserver-tests`: SyncServer pytest.
  - `warehouse_web-tests`: `python manage.py test`.
- Параллельный запуск jobs; ARC-08 закрывается автоматически.
- Cross-component integration tests (Warehouse_web + QDE на одном Docker image) — отдельный job.

### D4. **Версионирование**

- **QDE `engine_version`** (`qm_engine.__version__`, semver) — независимая ось версионирования.
- **QDE `engine_contract_version`** — semver, независимо от `engine_version`. Может расширяться backward-compatibly (Phase 2.1: `engine_contract_versions: ["1.0.0"]`).
- **QDE `backend_version`** — per-backend pin (например `typst: 0.15.1`, `weasyprint: 69.0`).
- **Warehouse Solution version** — не зависит от `engine_version`. Warehouse_web release notes ссылаются на «QDE engine X.Y.Z + bundled templates A, B, C».
- **Template packages** — версионируются отдельно (`warehouse-waybill-ru@2.0.0`).

### D5. **ADR и документация QDE остаются в QDE**

- `QuartermasterDocumentEngine/doc/ADR-0001-...` (engine-internal ADR) остаётся в подкаталоге — это решение **внутри** QDE.
- Warehouse-relevant ADR (0030, 0031, 0032, этот пакет) лежат в `warehouse_solution/docs/adr/` — это решения **про интеграцию**.
- Чёткое разделение: engine-internal vs integration-level.

---

## Consequences

### Pros

- **ARC-08 закрыт немедленно.** QDE попадает под CI root-repo, тесты запускаются в обязательном порядке.
- **Single source of truth**: один `git log`, один `git blame`, один blame-history при расследовании рендер-багов.
- **Synchronous refactoring**: правки в envelope/contract видны обоим сторонам в одном PR. Меньше шансов на silent drift между QDE Phase 6 и Warehouse_web.
- **Simpler Docker**: `warehouse_web` Dockerfile устанавливает QDE из monorepo в той же multi-stage сборке. Для production используется обычный `pip install ./QuartermasterDocumentEngine`; editable install (`-e`) допустим только для dev-среды.
- **Шрифты/templates и pinned Typst binary собираются в один `Warehouse_web` runtime image**: QDE package поставляет свои package data, а Typst binary добавляется отдельным verified build-stage согласно ADR-0032 D7. Runtime download не требуется.
- **Меньше ceremony**: никаких cross-repo PR, никаких lockfile-ов, никаких «обновить submodule pointer».

### Cons / обязательства

- **QDE больше не «отдельно переиспользуемый»**. Это допустимо, потому что реальных внешних consumer нет. Если появятся — потребуется либо extract (Phase 12+), либо остаться в monorepo с чёткими границами.
- **Размер root-repo растёт**. Текущий `QuartermasterDocumentEngine/` ≈ ~1 ГБ с `.venv`, но `.venv` gitignored. Source ≈ несколько десятков МБ. Приемлемо.
- **CI feedback loop** может замедлиться, если не разнести jobs (D3). Решается параллельными jobs.
- **Release notes для QDE** теперь живут в root CHANGELOG либо в `QuartermasterDocumentEngine/CHANGELOG.md`. Принято: в `QuartermasterDocumentEngine/CHANGELOG.md` (D5).

### Risks

| Риск | Митигация |
|---|---|
| Случайная cross-import `QDE → Warehouse_web` | Architecture test в QDE pytest: `ast` scan на запрещённые imports |
| Большой root-repo замедляет клонирование | Git shallow clone + sparse-checkout поддерживаются; `.venv` не в git |
| Conflict в `docs/adr/` нумерации между engine-internal и integration | D5: engine-internal ADRs имеют отдельный namespace (ADR-0001 в QDE) |
| Потеря «release independence» QDE | D4: `engine_version` остаётся независимой осью. Phase 12 trigger для extract сохраняется. |

---

## Rejected Alternatives

### Independent repo + git submodule

Отклонено ADR-0029 §1. Подтверждено в настоящем ADR.

### Independent repo + gitlink + lockfile

Это **submodule-lite** — gitlink-объекты в tree, отдельный `.gitmodules`, отдельный fetch step. Те же проблемы синхронизации, что у submodule. Не выбрано.

### Independent repo + PyPI-пакет

Отклонено ADR-0029 §1: «смешивает версионирование engine и templates». Сохраняется в отвергнутых.

### Independent repo + vendored copy

Вендоринг без версионирования. Через месяц drift, никаких CI guarantees. Не выбрано.

### Independent repo + container/sidecar (deployment-time only)

Решает deployment, не source control. ARC-08 остаётся открытым. Не выбрано как замена monorepo; **может появиться в Phase 11** как deployment-unit, если сработают trigger conditions.

### Subdirectory как fully-internal Warehouse module (без границ)

Слишком слабая граница. Engine теряет логическую идентичность. Reject.

---

## Out of Scope

- Конкретный CI-provider (GitHub Actions, GitLab CI, etc.) — implementation detail в Phase 6 / doc update.
- Перенос `QuartermasterDocumentEngine/` из `steeltalon777/QuartermasterDocumentEngine` GitHub repo в `warehouse_solution/` — операционная задача. Может потребовать `git mv` или fresh import. ADR не предписывает способ; только outcome.
- Long-term извлечение QDE обратно в independent repo (Phase 12 trigger).

---

## Migration Plan

С момента принятия настоящего ADR:

1. **Шаг 1** (операционный): `QuartermasterDocumentEngine/` либо импортируется из GitHub в root-repo как подкаталог, либо копируется из локального nested-repo с сохранением git-history. Конкретный способ — на усмотрение пользователя.
2. **Шаг 2**: `QuartermasterDocumentEngine/` добавляется в root `.gitignore` подкаталог `.venv/` и `.spike/` (уже есть в собственном `.gitignore`).
3. **Шаг 3**: CI jobs (`qde-unit`, `qde-integration`, `qde-golden`) описываются в `.github/workflows/`. ARC-08 закрыт.
4. **Шаг 4**: `docs/adr/0029-quartermaster-document-engine.md` §1 обновляется: было «отдельный репозиторий steeltalon777/QuartermasterDocumentEngine», стало «входит в warehouse_solution как подкаталог, см. ADR-0031».
5. **Шаг 5**: README.md и ARCHITECTURE.md добавляют ссылку на `QuartermasterDocumentEngine/` как на часть monorepo.

---

## Acceptance Criteria

ADR-0031 принимается когда:

1. Шаги 1-5 migration plan выполнены либо явно отложены с указанием ответственного.
2. Phase 6A может начаться с установки `QuartermasterDocumentEngine` из monorepo в `Warehouse_web` Docker image (`pip install ./QuartermasterDocumentEngine`; `-e` только для dev).
3. CI jobs работают; ARC-08 больше не открыт.
4. Architecture test (`QDE → Warehouse_web` import detection) добавлен и зелёный.

---

## Cross-references

- ADR-0029 §1 (отменяется в части «отдельный репозиторий steeltalon777»).
- `docs/AUDIT_ARCHITECTURE_SECURITY_2026-08-10.md` ARC-08 (закрывается).
- `QuartermasterDocumentEngine/doc/ADR-0001-QUARTERMASTER-DOCUMENT-ENGINE.md` (engine-internal, не меняется).
- `docs/adr/0030-qde-primary-rendering-backend-typst.md` (companion).
- `docs/adr/0032-qde-warehouse-integration-contract.md` (companion).
- `docs/TZ-QDE_INTEGRATION_READINESS.md` (companion implementation TZ).

---

## Confidence

- **High** для того, что monorepo закрывает ARC-08 и упрощает Phase 6.
- **High** для того, что D2 (границы через подкаталог) удерживается architecture test'ом.
- **Medium** для того, что ARC-08 не появится снова в форме «CI не запускает qde-integration». Решается через обязательные required checks на PR.
- **Medium** для долгосрочной устойчивости модели. Если через 6+ месяцев появится реальный внешний consumer QDE — потребуется пересмотр через Phase 12 trigger.