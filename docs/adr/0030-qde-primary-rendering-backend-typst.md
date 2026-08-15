# ADR-0030: Quartermaster Document Engine — Primary Rendering Backend (Typst)

- **Status:** Proposed
- **Date:** 2026-08-15
- **Deciders:** пользователь, Architect Agent
- **Scope:** primary rendering backend для `QuartermasterDocumentEngine` в production-интеграции с `Warehouse_web` (Phase 6 и далее)
- **Supersedes:** ничего; отменяет только provisional-рекомендацию из `docs/SPEC-QUARTERMASTER_DOCUMENT_ENGINE.md` §12 и Phase 2 §A (TL;DR) — переводит её в формальный статус
- **Related decisions:** ADR-0029 §5/§7/§10; ADR-0001 (QDE) D2/D7/D11/D13; `TZ-PHASE2-BACKEND-SPIKE.md` evidence package; `docs/SPEC-QUARTERMASTER_DOCUMENT_ENGINE.md`
- **Conflicting historical reference:** `TZ-PHASE2-BACKEND-SPIKE.md` §1.5 («Нужен ли отдельный ADR до реализации Phase 2?») и §A refer to the slot as `ADR-0002`. `ADR-0002` уже занят (`0002-warehouse-web-through-syncserver-api.md`). Корректный номер настоящего ADR — **0030** (следующий свободный после 0029). Все будущие ссылки указывают на ADR-0030.

---

## Context

1. **QDE Phase 0–2.1.2 закрыты** (`31b774a` в `QuartermasterDocumentEngine/`). Phase 2 backend-spike evidence: 215 тестов passed; zero hard vetoes на обоих backend'ах; performance matrix закрыта; byte-determinism Typst подтверждён 980 рендерами (Phase 2.1.2).
2. **Provisional preferred backend = Typst** (weighted **462 vs WeasyPrint 376**, +86 в пользу Typst). Основано на 12-критериальной scoring matrix из ROADMAP §Phase 5 / SPEC §14.
3. **WeasyPrint fails SPEC hard envelope** на `fuel-1500` в сценарии `pool=4` (≈112 s vs 60 s hard). На production 4 vCPU / 8 GB VPS ожидаемо хуже — реальный risk для Phase 5+.
5. **Backend distribution**: Typst = 54 MB static binary, верифицирован sha256 `29273eaa…`; WeasyPrint = 2.9 MB pure-Python + ~50 MB apt native libs (cairo, pango, gdk-pixbuf). Phase 5 deployment budget обязателен, если WeasyPrint останется primary.
6. **Windows verification NOT done.** `spike/typst-pin.json` хранит honest `binaries.windows-x64.archive_sha256 == "unverified-no-windows-env"`. Linux x64 binary проверен, sha256 совпадает.
7. **Первый production touchpoint QDE — Django BFF** (render-host по ADR-0029 §8). Django BFF деплоится на Linux container (`warehouse_web` Docker image), не на Windows. **Windows-среда QDE для Linux-интеграции архитектурно не требуется.**

Phase 2 оставил решение «provisional до Windows verification». Настоящий ADR закрывает эту provisional-ность для **Linux render-host path** и явно отделяет Windows-блокер от Phase 6.

---

## Decision

### D1. Primary rendering backend = **Typst 0.15.1** (Linux x64, pinned)

- **Backend binary**: `typst-x86_64-unknown-linux-musl`, версия **0.15.1**, commit `9dfd3a08`, binary sha256 `29273eaa04f6d00edd0c2bec578f565fc9c65be856bfbffc894567c68ed0b237`.
- **Bundled fonts**: DejaVu Sans (4 файла) + LICENSE + `fonts/manifest.json`. Cyrillic mandatory, silent fallback запрещён.
- **Deterministic env**: `TYPST_TIMESTAMP` env + явный CLI-флаг `--creation-timestamp 1700000000` (Phase 2.1.1 close-out M1).
- **Runtime**: subprocess pinned binary, argv-only, no shell, no network (verified `strace -e trace=network` = 0 syscalls).

### D2. WeasyPrint 69.0 остаётся **legacy/reference backend**

- Сохраняется в QDE bundle до момента, пока существуют historical artifacts, требующие воспроизводимости на старом движке.
- До cutover используется как primary legacy path; после cutover сохраняется только как **явный operator-controlled emergency rollback/fallback path**. Silent fallback при ошибке QDE запрещён; emergency fallback по умолчанию выключен и должен явно маркироваться (см. companion TZ §6).
- НЕ используется как primary в новых production templates.
- Шаблоны `warehouse-waybill-ru@0.1.0` и `@1.0` остаются в WeasyPrint-bundle для обратной совместимости с Phase 1 fixtures.

### D3. Выбор backend — по `manifest.backend` в template package

- Клиент указывает `template_id` + `template_version` + `document_contract`. Backend выбирает QDE template registry.
- Клиент НЕ передаёт `backend` как параметр. Это закрывает class of risks (D3 = ADR-0029 §7 unchanged).
- `template_id` разрешается через QDE registry; отсутствующий шаблон → `TEMPLATE_NOT_INSTALLED` (exit 4).

### D4. Migration policy

- Новые production templates создаются на Typst. Это правило применяется с момента принятия настоящего ADR.
- Существующие templates (`warehouse-waybill-ru@1.0`, syncserver-side Jinja2-waybill, Django waybill) мигрируются **по одному**, через:
  - production-typst template version (Phase 6C — `warehouse-waybill-ru@2.0.0`);
  - SHADOW-сравнение legacy vs QDE (Phase 6D);
  - явный acceptance gate (Phase 6E).
- Удаление legacy templates не входит в Phase 6 и требует отдельного ADR (не раньше Phase 11/12 trigger conditions по ADR-0029 §8).

### D5. Windows verification — deferred, не блокирует Phase 6

- Phase 6 (canonical waybill + Django BFF интеграция) выполняется на Linux. Windows-среда архитектурно не требуется.
- Windows verification Typst binary вносится в **Phase 8 / WPF integration** как обязательный gate (там она реально нужна).
- Статус V4 «Windows NOT-VERIFIED» в Phase 2 scoring matrix остаётся как **открытый долг**, привязанный к Phase 8, а не к Phase 6.
- Если WPF / desktop phase будет отменён — Windows verification становится optional, и V4 пересматривается отдельным ADR.

---

## Consequences

### Pros

- Phase 6 разблокирована без дополнительных блокеров (Windows-среда больше не нужна для Linux render-host).
- Performance budget ADR-0029 §8 trigger conditions смещается вверх: Typst проходит все сценарии, не провоцируя premature artifact service.
- Deterministic PDF bytes → безопаснее для исторической воспроизводимости: одинаковый canonical payload + одинаковые версии contract/template/engine/backend дают стабильный `pdf_sha256`. `documents.payload_hash` и `pdf_sha256` хэшируют **разные данные** и не обязаны совпадать по значению.
- После отдельного retire legacy renderer можно будет убрать WeasyPrint native libs и уменьшить Docker image. **В Phase 6 этого эффекта ещё нет**, потому что legacy renderer сохраняется для rollback.

### Cons / обязательства

- **One-way door light**: выбор Typst как primary фиксируется на уровне ADRs. Переход обратно на WeasyPrint или mixed — допустим, но требует нового ADR.
- **Linux only в Phase 6**: если пользователь хочет Windows-интеграцию раньше, нужно явно запросить — отдельная задача.
- **Версия Typst pinned**: 0.15.1 не обновляется без повторного spike и ADR-обновления.
- **Typst byte output vs WeasyPrint structural output**: visual diff при первом cutover неизбежен. Dispute policy фиксируется в TZ Phase 6E.

### Risks

| Риск | Митигация |
|---|---|
| Typst 0.15.x security issue без апгрейда | Pin зафиксирован; апгрейд = новый spike + новый ADR-апдейт |
| Typst license drift (Apache-2.0 → ...) | Phase 2 отметил license-compatible; ADR-0030 не меняет license |
| Visual diff при cutover на prod-waybill | Phase 6E acceptance + golden + dispute policy |
| Windows blocker в Phase 8 | ADR-0030 явно переносит в Phase 8; пользователь знает |
| WeasyPrint artifacts теряют воспроизводимость при удалении | D2 сохраняет WeasyPrint в bundle до выделенного ADR на retire |

---

## Rejected Alternatives

### WeasyPrint как primary

WeasyPrint проваливает SPEC hard envelope на `fuel-1500 pool=4` (≈112 s vs 60 s). На production 4 vCPU / 8 GB VPS ожидаемо хуже. Не выбран.

### Chromium / Paged.js как primary

Chromium не оценивался в Phase 2 spike (ADR-0029 §7: «без spike-обоснования в поставку не входит»). ADR-0001 (QDE) D7: «рассматривается только при подтверждённой необходимости». Не выбран.

### Mixed primary (Typst для новых, WeasyPrint для legacy)

Дублирует шаблоны и operational complexity. ADR-0029 §7 допускает mixed backend **per template** в manifest — это инфраструктурная возможность, а не целевая стратегия. Mixed primary = два пути production-валидации, два пути dispute. Не выбран на уровне ADR; **допустим per-template в manifest** (это и есть D3).

### ADR-0030 ждёт Windows verification

Архитектурно Windows не нужен для Phase 6 (Linux render-host). Ждать — означает задержать всю Phase 6 без объективной причины. Не выбрано.

### Rust host как primary

ADR-0001 (QDE) D13: «Python host можно оставить навсегда, если он проходит deployment/performance». Phase 2.1.2 perf evidence: Typst 11× быстрее WeasyPrint, нет performance-проблем. Rust host рассматривается в Phase 12 при измеримой пользе. Не выбран.

---

## Out of Scope

- Конкретный shipping-формат QDE bundle (Phase 11 trigger conditions ADR-0029 §8).
- Retention policy исторических PDF (отдельный ADR).
- Visual regression harness для legacy Django waybill (Phase 6E).
- WPF integration / Windows runtime (Phase 8, отдельный TZ).
- Автоконвертер Jinja → Typst (запрещён ADR-0029 §10 / Phase 3 §3).

---

## Acceptance Criteria

ADR-0030 принимается когда:

1. Все ADRs 0030, 0031, 0032 и TZ-QDE_INTEGRATION_READINESS зафиксированы в `dev` ветке.
2. Phase 6 может начаться без дополнительных архитектурных решений (кроме тех, что вытекают из ADR-0031/0032/TZ).
3. Windows verification явно перенесён в Phase 8 backlog.
4. Все ссылки в существующих документах на «ADR-0002 primary backend» исправлены на «ADR-0030».

---

## Cross-references (новые и обновляемые)

### Новые

- `docs/adr/0030-qde-primary-rendering-backend-typst.md` (настоящий документ)
- `docs/adr/0031-qde-ownership-and-versioning.md`
- `docs/adr/0032-qde-warehouse-integration-contract.md`
- `docs/TZ-QDE_INTEGRATION_READINESS.md`

### Требуют обновления

- `QuartermasterDocumentEngine/doc/TZ-PHASE2-BACKEND-SPIKE.md` §1.5 и §A — заменить «ADR-0002 primary backend» → «ADR-0030» (двухстрочный edit).
- `docs/SPEC-QUARTERMASTER_DOCUMENT_ENGINE.md` §12 — зафиксировать, что provisional-рекомендация Typst переведена в formal ADR-0030.
- `QuartermasterDocumentEngine/doc/ROADMAP-QUARTERMASTER_DOCUMENT_ENGINE-v1.md` Phase 5 — сослаться на ADR-0030 как формализованное решение.

---

## Confidence

- **High** для Linux production primary = Typst.
- **High** для того, что Phase 6 не зависит от Windows verification.
- **High** для того, что D3 (backend by manifest) совместим с ADR-0029 §7.
- **Medium** для конкретного visual diff dispute policy — закрывается в TZ Phase 6E.
- **Medium** для долгосрочной удерживаемости Typst 0.15.1 — зависит от upstream maintenance, не от нас.