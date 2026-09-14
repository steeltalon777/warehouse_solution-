# ADR-0034: QDE waybill — null-safety для nullable object-полей контракта (receiver=null robustness)

- **Status:** Proposed
- **Date:** 2026-09-14
- **Deciders:** пользователь, Architect Agent
- **Scope:** какой слой обязан обрабатывать `receiver: null` (и прочие nullable object-поля) в `warehouse.operation-document/v2` при рендере через QDE
- **Trigger:** Phase 6D evidence (template 2.2.0, корпус 5633 waybill): **186 QDE failures** из 5633; воспроизводится на 2.0.0/2.1.0/2.2.0 (pre-existing)
- **Supersedes:** ничего
- **Related decisions:** ADR-0029 §5/§6/§7; ADR-0030; ADR-0031 D4 (versioning шаблонов); ADR-0032 D2 (builder pass-through)

---

## 1. Контекст и свежие факты (Phase 6D)

Evidence-прогон `phase6d-2.2.0-20260914T045747Z` (корпус = SyncServer `GET /documents?document_type=waybill`, 5633 документа):

| Метрика | Значение |
|---|---|
| total_runs / distinct | 5633 / 5633 |
| MATCH / REVIEW_REQUIRED / MISMATCH | 4469 / 978 / 0 |
| **QDE_FAILED** | **186** |
| comparable / text_match | 5447 / 5447 (100%) |
| pages_match | 4469/5447 (82%, «diagnostic only» — 2.2.0 rebalance) |

Все 978 REVIEW_REQUIRED — только `PAGE_COUNT_DIFF` (ожидаемый эффект pagination rebalance). Все 186 QDE_FAILED имеют legacy-артефакт (legacy-рендер их **успешно** печатает).

### 1.1. Прямое воспроизведение (подтверждено на стенде)

Рендер envelope с payload `{... "receiver": null, consignee_label отсутствует, "operation_type": "RECEIVE" ...}` через установленный QDE CLI:

```
2.2.0: main.typ:258:11: error: type none has no method `at`
2.1.0: main.typ:252:11: error: type none has no method `at`
2.0.0: main.typ:250:11: error: type none has no method `at`
```

### 1.2. Точная сверка с корпусом БД

Текущая БД стенда == evidence-корпус (5633 waybill: finalized 418 / void 5176 / draft 39).

- **receiver = JSON `null`**: 727/5633 (12.9%). Распределение по operation types:
  ADJUSTMENT 1/1, EXPENSE 4/4, ISSUE 203/203, **MOVE 0/2195**, RECEIVE 319/3030, WRITE_OFF 200/200.
- **Crash-множество** (null receiver **и** отсутствующий/пустой `consignee_label`): ровно **186** документов, все RECEIVE, все finalized. Пересечение с id из evidence CSV — **186/186, 1:1**.
- Почему только 186 из 727: шаблон проверяет `consignee_label` **первым** в fallback-цепочке. Текущий SyncServer всегда генерирует непустой `consignee_label`; падают только **старые stored payloads** (созданные до появления поля).

---

## 2. Contract truth

**`QuartermasterDocumentEngine/contracts/warehouse.operation-document/v2/schema.json`** явно типизирует:

```json
"receiver": { "type": ["object", "null"] },
"operation": { "type": ["object", "null"] },
"sender":    { "type": ["object", "null"] },
"basis":     { "type": ["object", "null"] },
"source_site": { "type": ["object", "null"] },
"destination_site": { "type": ["object", "null"] },
"issued_to":  { "type": ["object", "null"] },
"recipient":  { "type": ["object", "null"] },
"created_by": { "type": ["object", "null"] },
"submitted_by": { "type": ["object", "null"] },
"signatures": { "type": ["object", "null"] },
"localization": { "type": ["object", "null"] }
```

`required: ["lines"]` — единственное обязательное поле. Description схемы: *«Accepts both the phase1-minimal shape (header + lines) and the prod payload shape»* — то есть отсутствующий `receiver` и `receiver: null` — **легальный input по самому определению контракта**.

Pipeline QDE (проверено по коду):

1. `qm_engine/envelope.py::parse_envelope` — валидирует envelope и `document` **против этой схемы** (jsonschema Draft202012). `receiver: null` проходит.
2. `qm_engine/registry.py::check_contract` — сверяет `manifest.document_contract` шаблона с envelope. `warehouse-waybill-ru/2.2.0/manifest.yaml` декларирует `document_contract: warehouse.operation-document/v2` → **шаблон контрактно обязался рендерить весь домен этого контракта**.
3. `qm_engine/render.py` + `qm_backends/typst_backend.py` — пишут в `document.json` **полный normalized envelope**; нормализация = только copies/watermark/assets (Phase 2.1). **Ни один слой не нормализует nullable object-поля**.
4. Шаблон получает payload как есть. `inner.at("receiver", default: (:))` защищает только от **отсутствующего ключа**; явный `null` связывает `receiver = none`, и `none.at("site_name", ...)` — compile error в Typst.

Builder `Warehouse_web/apps/documents/services.py::build_qde_envelope` (ADR-0032 D2) кладёт `document["payload"]` в `envelope.document` **как есть** — by design, `payload_hash` документа должен оставаться честным идентификатором рендер-входа.

**Вывод (contract truth):** `receiver: null` — валидный контрактный input. Контракт нельзя ужесточить без отзыва собственного описания; оба «потребителя контракта» (engine-валидация и manifest шаблона) пропускают null до шаблона. Значит дефект — в шаблоне.

---

## 3. Intended semantics of receiver

1. **Доменный смысл**: `receiver` = «склад-получатель»; по функциональным требованиям (`Functional and WorkLogik.md` §5.4) склад-получатель существует **только у MOVE** («перемещение — склад отправитель и склад получатель»). Для RECEIVE/ISSUE/WRITE_OFF/EXPENSE/ADJUSTMENT `receiver = null` — **семантически корректное** состояние, а не ошибка данных. Это подтверждает `SyncServer/app/services/document_service.py::_build_payload` (498–512): `receiver_info = None`, если нет `destination_site`.
2. **Display-семантика** (канон = legacy-рендер): `Warehouse_web/apps/documents/services.py::_consignee_label` (506–518) — fallback-цепочка:
   `consignee_label` → `receiver.site_name|site_code` → `recipient.recipient_name` → `sender.site_name|site_code` → `"—"` — вся null-safe (`isinstance(..., dict)`).
   Шаблон 2.2.0 реализует **ту же цепочку** (`consignee_label()` в main.typ), но падает на null receiver вместо перехода к следующему фолбэку.
3. Для 186 падающих RECEIVE-документов legacy-цепочка даёт `sender.site_name` — то есть сам склад-получатель. Это **семантически правильный** Грузополучатель для прихода: guard ничего обязательного не маскирует, он воспроизводит legacy.

---

## 4. Root cause

**Шаблон нарушает собственный манифест.** `warehouse-waybill-ru` декларирует `document_contract: warehouse.operation-document/v2`, но не принимает весь домен контракта: idiom `inner.at(k, default: (:))` не эквивалентен «null-safe доступ», а только «missing-key-safe доступ». В Typst JSON `null` связывается в `none`, у которого нет метода `.at`.

Уязвимые цепочки в 2.2.0 (`main.typ`), где контракт допускает `null`, а шаблон зовёт `.at` без guard:

| Поле | Строки 2.2.0 | В prod-корпусе | Статус |
|---|---|---|---|
| `receiver` | 257–262 | **null у 727/5633** | 🔴 падает (186 crash) |
| `sender` | 224, 273–278 | никогда не null (SyncServer всегда строит) | 🟡 латентный дефект |
| `operation` | 216–217 | никогда не null | 🟡 латентный дефект |
| `basis` | 290–291 | никогда не null | 🟡 латентный дефект |
| `recipient` | 266–268 | null у 430/457 (не-void) | ✅ уже guarded (`type(...) == dictionary`) |

Не читаются шаблоном вовсе: `signatures`, `localization`, `issued_to`, `created_by`, `submitted_by`, `source_site`, `destination_site`, `organization` (вложенный), `header`. `lines` — required в схеме (null не пройдёт валидацию). `doc.*` — поля валидированного envelope, безопасны.

Почему баг не пойман раньше:
- все QDE fixtures/golden — MOVE-shaped (receiver = объект), null-кейсов нет (gap в тестах);
- evidence-коллектор прячет stderr QDE («render_shadow_pdf returned None»), причина не видна;
- новые SyncServer-payload всегда содержат `consignee_label`, поэтому свежие документы не доходят до падающей строки — доходят только старые stored payloads.

---

## 5. Решение

### D1. **Verdict: TEMPLATE FIX (вариант B)** — шаблон обязан быть null-safe для всех контрактно-nullable полей, которые он разыменовывает.

- Применить существующий в шаблоне idiom (type-check как у `recipient`, строки 266–267) к четырём цепочкам: `receiver`, `sender` (обе точки: 224 и 273–278), `operation`, `basis`.
- Fallback-порядок не менять — он каноничен (совпадает с legacy `_consignee_label`).
- Фикс выпускается **новой версией шаблона `2.2.1`** (semver patch; ADR-0031 D4: template packages версионируются отдельно; выпущенные версии неизменяемы). 2.0.0/2.1.0/2.2.0 остаются историческими релизами с известным дефектом и **не должны** попадать в `DOCUMENT_TEMPLATE_MAP`.

### D2. **Отвергнуто: CONTRACT FIX (вариант A) — сделать receiver обязательным**

- Противоречит описанию схемы (phase1-minimal shape вообще без receiver) и engine-тесту пустого документа;
- receiver семантически отсутствует у всех не-MOVE операций — это не «invalid envelope», а нормальное состояние;
- завалил бы валидацию для **727 stored документов** (immutable payloads; SyncServer их не перегенерирует для QDE — ADR-0032 D4) и превратил бы RENDER_FAILED в INVALID_PAYLOAD — строго хуже.

### D3. **Отвергнуто как primary: ENVELOPE FIX (вариант C) — нормализация null → {} в builder/adapter**

- ADR-0032 D2: builder передаёт payload **как есть**; рекурсивная трансформация payload в seam сломает честность `payload_hash` как identity рендер-входа;
- builder — не единственный потребитель: QDE CLI/тесты/будущие WPF/Rust-хосты рендерят напрямую — их нормализация в Django не защитит;
- нормализация в engine — изменение семантики для всех контрактов (null vs missing станут неразличимы), overreach без нового контрактного правила;
- маскирует дефект шаблона, который всё равно обязан принимать полный домен контракта.

Допускается **позднее** как defense-in-depth, если появится второй producer с нестабильным payload — но не как фикс этого бага.

### D4. **Опциональный companion (не блокирует): observability evidence-коллектора**

`collect_phase6d_evidence` сейчас пишет в строку `error="render_shadow_pdf returned None"`, теряя stderr QDE. Для dispute-resolution Phase 6E рекомендуется захватывать stderr/cause в поле ошибки. Отдельная мелкая задача, не часть этого ADR.

---

## 6. Минимальный patch scope

1. **QDE** `QuartermasterDocumentEngine/templates/warehouse-waybill-ru/2.2.1/` — копия 2.2.0 + null-safe guards в `main.typ` (4 цепочки, idiom `recipient`). Только `main.typ`; `layout-config.typ`, `components/*` не трогаются.
2. **Warehouse_web** `config/settings/base.py`: `DOCUMENT_TEMPLATE_MAP = {"waybill": ("warehouse-waybill-ru", "2.2.1")}`.
3. Dockerfile менять не нужно: `COPY .../templates/warehouse-waybill-ru` копирует каталог целиком, 2.2.1 попадёт в образ.

Не трогаем: SyncServer, схему контракта, builder, БД, кэш-модели.

---

## 7. Необходимые тесты (test ladder)

| Уровень | Что | Где |
|---|---|---|
| Unit (QDE) | fixture/envelope-тесты остаются зелёными; добавить fixture с `receiver: null` | `QuartermasterDocumentEngine/tests/unit/`, `tests/fixtures/` |
| Integration (QDE) | рендеры через engine+Typst: `receiver=null`+нет `consignee_label` → exit 0, в тексте PDF значение `sender.site_name` (parity с legacy); `sender=null`; `operation=null`; `basis=null`; все-null phase1-minimal shape; повторный рендер byte-identical | `tests/integration/` (новый `test_nullable_fields.py`, паттерн `test_canonical_waybill.py`) |
| Golden (QDE) | golden-кейс `warehouse-waybill-ru-2.2.1` с null-field fixtures, регистрация в `tests/golden/index.json` | `tests/golden/` |
| Django (Warehouse_web) | `render_via_qde` на реальном падающем payload (id `0385ae37-b269-4ebb-b865-6a1af1e715f9`) → успех; извлечённый Грузополучатель == legacy `_consignee_label`; артефакт с `template_version=2.2.1` | `apps/documents/tests/` |
| Stand smoke | повторный прогон `collect_phase6d_evidence` → `qde_failures == 0`, identity assertion все 2.2.1 | стенд + management command |
| Regression | существующие `test_shadow_integration.py`, `test_envelope_builder.py`, `test_collect_phase6d_evidence.py` зелёные | `python manage.py test` |

UI automation (Playwright) — не применимо (server-side рендер); user scenario покрывается evidence-прогоном и окном Phase 6E.

---

## 8. Migration / compatibility risk

- **Ноль** изменений в SyncServer, БД, контракте, builder. Никаких миграций.
- Bump шаблона меняет ось `template_version` identity артефакта → **одноразовый** пере-рендер кэшированных waybill-артефактов (5447; warm-рендер ~2–4 мс) — штатный механизм кэша.
- Для 5447 уже рендерящихся документов вывод **байт-в-байт не меняется**: guard срабатывает только на ветках, которые раньше падали. Layout-влияние отсутствует.
- 186 документов впервые получат QDE-PDF; их page-count попадёт в пул REVIEW pagination rebalance — штатный поток Phase 6E, не авария.
- Rollback: вернуть `DOCUMENT_TEMPLATE_MAP` на 2.2.0 (дефект возвращается, но это и есть статус-кво до фикса).
- Старые версии шаблонов остаются установленными с дефектом: правило — **никогда не пинить 2.0.0/2.1.0/2.2.0** в прод-маппинг.

---

## 9. Execution strategy

**Sequential, один исполнитель.** Обоснование: шаблон и settings-маппинг должны выкатиться согласованно; тесты зависят от обоих; суммарный объём мал. Параллельность не даёт выигрыша и размазывает ownership одного дефекта.

1. Шаблон 2.2.1 + QDE unit/integration/golden (в `QuartermasterDocumentEngine/`).
2. Bump `DOCUMENT_TEMPLATE_MAP` + Django parity-тест на реальном payload.
3. Прогон `collect_phase6d_evidence` → 0 failures.
4. (Опционально, отдельной задачей) D4 — stderr в evidence-строку.

Для будущего Swarm: ownership шага 1 = QDE, шага 2 = Warehouse_web; интеграционная точка — evidence-прогон; параллельные шаги 1 и 2 допустимы только при зафиксированном контракте имени версии 2.2.1, иначе sequential.

---

## 10. Acceptance criteria

ADR принят, когда:

1. Verdict TEMPLATE FIX зафиксирован; варианты A и C явно отвергнуты с данным rationale.
2. Patch scope (2 файла + тесты) подтверждён; список уязвимых цепочек (receiver/sender/operation/basis) полный.
3. Test ladder из §7 описан и выполним до старта Phase 6E.
4. Rollback-путь (§8) задокументирован.
5. Phase 6E может стартовать с нулём QDE_FAILED в evidence.

---

## Cross-references

- ADR-0029 §5/§6/§7 (envelope, per-family contracts, backend).
- ADR-0030 (Typst primary), ADR-0031 D4 (template versioning), ADR-0032 D2/D4/D5 (builder pass-through, legacy path, allowlist).
- `QuartermasterDocumentEngine/doc/SPEC-QUARTERMASTER_DOCUMENT_ENGINE-v2.md`, `ADR-0001` (engine-internal).
- `docs/TZ-QDE_INTEGRATION_READINESS.md` §10.4/§10.5 (Phase 6D/6E).
- Evidence: `Warehouse_web/spike-out/waybill-qde-vs-django/phase6d-2.2.0-20260914T045747Z/`.
- `Functional and WorkLogik.md` §5.4, стр. 128 (реквизиты накладной).
