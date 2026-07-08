# Architecture Review — V3.1I Waybill Pagination & Draft Sync Hardening

**Date:** 2026-07-08
**Reviewer:** Architect
**Reviewed artifact:** `docs/TZ-V3.1I_WAYBILL_PAGINATION_AND_SYNC_HARDENING.md` (draft, 642 lines)
**Related:** `docs/TZ-V3.1H_WAYBILL_PDF_FIXES.md` (Final acceptance #9 open), `Functional and WorkLogik.md` §VII (lines 119–123)
**Method:** every factual claim in the TZ was re-verified against the actual source (`Warehouse_web/apps/documents/services.py`, `waybill_pdf.html`, `apps/bff_api/documents_views.py`, `SyncServer/app/services/operations_service.py`, `SyncServer/app/services/document_service.py`).

## Verdict

**Revisions required.** One 🔴 blocker in the I3 design produces a data-correctness bug (stale finalized document at submit) and is unrenderable by the only PDF renderer that exists. The plan must be revised before any executor is dispatched. The CSS/pagination diagnosis (A1/A2/A3) is accurate and valuable; only the SyncServer draft-document-type mapping needs correction, plus several coupling/test warnings to harden.

---

## Verified facts (basis for findings)

- `paginate_waybill_lines` (`Warehouse_web/apps/documents/services.py:197–246`): defaults `available_height_first_page_mm=170.0`, `available_height_continuation_mm=210.0`, `estimated_row_height_mm=7.0`, `extra_lines = len(name)//60`, ratio `0.6`. Returns `list[dict[str,Any]]` with `page_number/lines/is_first/total_pages/is_last`. ✅ A1 confirmed.
- `waybill_pdf.html`: `h1` (lines 25–30) has **no** `page-break-after: avoid`; `.signature-block` (lines 69–73) has only `page-break-inside: avoid`, no bottom pinning; `.page` is a plain `<section>`, **not** a flex container. ✅ A2, A3 confirmed.
- `operations_service.py`: `create_operation` (333–547) does **not** call `generate_from_operation`. ✅ A4 confirmed. `update_operation` (763–773) calls it **without** `document_type` → defaults to `"waybill"` for every draft type. `submit_operation` (1054–1092) uses a local `document_type_map` (RECEIVE→acceptance_certificate, MOVE/ISSUE/ISSUE_RETURN→waybill, EXPENSE/WRITE_OFF/ADJUSTMENT→act).
- `document_service.py:150`: `generate_from_operation(..., document_type: DocumentType = "waybill", ...)`. `_void_existing_documents` (348–368) and `_find_reusable_document` (317–346) both **filter by `document_type`**. At submit (`auto_finalize=True`, status `submitted`), a reusable draft is **finalized in place without rebuilding payload** (lines 341–345).
- `Warehouse_web/apps/documents/services.py:110–111`: `render_document_html` raises if `document_type != "waybill"` — **only waybill is renderable**.
- `apps/bff_api/documents_views.py:150–180`: `OperationWaybillOpenView` hard-codes `document_type="waybill"`.
- `Warehouse_web/requirements.txt:8`: `weasyprint>=66,<67` (the TZ's "53+" claim is satisfied by v66).
- §VII is explicitly marked «частичная реализация» → deviations are permitted without an ADR per workspace rules.

---

## 🔴 Blockers

### 1. I3 draft `document_type` map (`EXPENSE`/`WRITE_OFF` → `act`) is unrenderable and causes a stale finalized document at submit

- **Checklist item:** Coupling & Cohesion / Data & State — single source of truth for document type per lifecycle stage.
- **Issue:** TZ I3.2 proposes `DRAFT_DOCUMENT_TYPE_BY_OPERATION = {"MOVE":"waybill","ISSUE":"waybill","ISSUE_RETURN":"waybill","EXPENSE":"act","WRITE_OFF":"act"}`. This diverges from three established contracts:
  1. `generate_from_operation` defaults to `waybill` (`document_service.py:150`) and H1 `update_operation` relies on that default (`operations_service.py:766–770`) → drafts updated via H1 always get a **waybill**, never an act.
  2. The BFF "Накладная" button (`documents_views.py:160`) hard-codes `document_type="waybill"`.
  3. The Django renderer (`services.py:110–111`) **only renders waybill** — a draft `act` cannot be previewed.
- **Impact (data correctness):** For an `EXPENSE`/`WRITE_OFF` draft, I3 creates a draft `act` at create-time. On `submit_operation`, the submit map says `EXPENSE`→`act`; `generate_from_operation(document_type="act", auto_finalize=True)` runs with `status="submitted"` → `_find_reusable_document("act")` (lines 317–346) **finds the orphan draft act from create** and **finalizes it in place without rebuilding the payload** (lines 341–345). The finalized act therefore reflects the **create-time** operation state and silently ignores every draft edit the storekeeper made. Meanwhile the per-edit draft `waybill`s produced by H1 (default type) are never voided by the act path (void filters by `document_type`, line 356) → orphan accumulation.
- **Recommendation:** The draft preview map must be **waybill-only and restricted to operation types whose final document is also a waybill**: `{"MOVE":"waybill","ISSUE":"waybill","ISSUE_RETURN":"waybill"}`. Exclude `EXPENSE`/`WRITE_OFF`/`RECEIVE`/`ADJUSTMENT` from draft generation (they receive their final `act`/`acceptance_certificate` at submit, which the out-of-scope renderer cannot preview anyway — and the TZ explicitly lists "новые типы документов (только waybill)" as out of scope). This keeps draft preview renderable, consistent with H1 update default and the BFF button, and eliminates the stale-reuse path.

### 2. I3 does not route `update_operation` (H1) through the shared `draft_document_type_for_operation` helper

- **Checklist item:** Coupling & Cohesion — consistency of the document-type decision across lifecycle stages.
- **Issue:** TZ I3.2 says the helper should be used "и в `create_operation`, и в `submit_operation`" but **does not mention `update_operation`**. H1's call (`operations_service.py:766–770`) passes no `document_type`, so it keeps defaulting to `waybill` for **all** draft types. After blocker #1 is applied, `create` uses the helper (waybill for MOVE/ISSUE/ISSUE_RETURN, None for others) while `update` still defaults to waybill for everyone → `create`-vs-`update` divergence for `EXPENSE`/`WRITE_OFF` (create produces nothing, first update produces a waybill).
- **Impact:** Not a new data bug (waybill is renderable and voided per edit), but it reintroduces the exact class of inconsistency the TZ set out to remove and means the "накладная обновляется вместе с черновиком" guarantee is stage-dependent. It also leaves `EXPENSE`/`WRITE_OFF` drafts with a waybill preview whose type does not match the submit-time `act` — confusing for the storekeeper.
- **Recommendation:** Pass `document_type=draft_document_type_for_operation(operation.operation_type)` in the H1 call too, and `if document_type:` guard it (skip generation when the helper returns `None`). This makes create and update share one map. If the team deliberately wants `EXPENSE`/`WRITE_OFF` drafts to keep a waybill preview, document that decision explicitly instead of relying on a silent default.

> After applying blockers #1 and #2, re-classify: the data-correctness path is closed. The remaining items are warnings.

---

## 🟡 Warnings

### 3. I2 first-page height budget (189 mm) ignores extra signatures on single-page MOVE/ISSUE/WRITE_OFF operations

- **Checklist item:** Data & State — geometry model must match the layout model.
- **Issue:** TZ I2.1 computes `available_height_first_page_mm = 189.0` by subtracting only `@page` margin + `h1` + `header-lines` + `thead` (≈78 mm) from 267 mm. It does **not** subtract the signature block, which under the I1 flex layout is a reserved flex item on **every** page (`waybill_pdf.html:165`, outside the `is_first`/`is_last` guards). On a **single-page** operation that carries extra signatures (MOVE = 2 extra, ISSUE/ISSUE_RETURN/EXPENSE = 1, WRITE_OFF = 1, via `_build_extra_signatures`), the first page is also the last page and must host `Кладовщик` + extra signatures (~37 mm total). Real first-page row budget then ≈ 267 − 78 − 37 ≈ **152 mm**, while the paginator is allowed 189 mm → a ~37 mm overflow, i.e. the same "первый лист залезает на 2ю страницу" symptom, just shifted to a narrower case.
- **Impact:** Narrow but real: single-page MOVE/ISSUE/WRITE_OFF with ~20–22 short rows + extra signatures can spill one row + the extra signature block onto a second page.
- **Recommendation:** Either (a) pass `extra_signatures_count` (or `operation_type`) into `paginate_waybill_lines` and reduce the first-page budget when `is_first and is_last and extra_signatures`, or (b) use a more conservative `available_height_first_page_mm ≈ 170–175 mm` that already reserves signature headroom. Note the current 170 mm is closer to the signature-inclusive reality than the TZ's 189 mm; do not raise the budget without modeling the signature.

### 4. I1 and I2 are geometrically coupled, not independent stages

- **Checklist item:** Coupling & Cohesion.
- **Issue:** The TZ lists I1 (CSS flex) and I2 (Python pagination) as separate stages with independent acceptance. But I1's flex layout **changes the height budget** I2 must respect: flex reserves the signature block height on every page and lets `.waybill-table-wrap` fill the remainder, whereas the current non-flex flow lets the signature trail the table. I2's constants are only correct relative to I1's layout.
- **Impact:** An executor could land I2 with constants tuned for the wrong layout, or land I1 without re-tuning I2, and the unit tests (I4) for each would pass in isolation while the integrated PDF still overflows.
- **Recommendation:** Make I6 (stand smoke, real 40+ row PDF) the **joint integration gate** for I1+I2 and state this explicitly. Add an I4 unit test that asserts the paginator's `available_height_*` constants are consistent with the flex geometry (e.g. `first_page_budget + h1 + header + thead + signature_height ≤ 267`).

### 5. WeasyPrint flexbox in paged media is plausible but not guaranteed; no fallback documented

- **Checklist item:** Failure Modes — undefined behavior on a critical path.
- **Issue:** TZ I1.2 asserts "WeasyPrint корректно рендерит flex-контейнеры в paged-media … работает в WeasyPrint 53+." Installed version is 66, so the version predicate holds, but `display:flex` + `min-height` on a section that also uses `.page + .page { page-break-before: always }` is a known-tricky combination in WeasyPrint (flex overflow across forced page breaks is not fully specified by CSS Paged Media). The TZ's own risk table hints at edge cases but presents flexbox as the certain solution.
- **Impact:** If a WeasyPrint flex/paged-media edge case triggers (very long single cell, custom font metrics), the signature may not pin to the bottom or the page may break inside the flex container.
- **Recommendation:** Frame I1 as "primary approach" with a documented **plan B**: a CSS `position: running()` signature via `@page` margin boxes, or a table-based bottom spacer. Gate the choice on the I6 visual check; if flex fails visually, switch to plan B without re-opening the TZ.

### 6. Dead parameters `first_page_max_rows` / `continuation_max_rows` in `paginate_waybill_lines`

- **Checklist item:** Complexity — single clear responsibility.
- **Issue:** Both parameters are declared in the signature (`services.py:200–201`) but **never referenced** in the function body, which only uses the `available_height_*` and `estimated_row_height_mm` values. The TZ's "new signature" keeps them (defaults 22/26) with a "страховка" comment, implying they are safety caps — but they are not enforced.
- **Impact:** Misleading API; an executor may assume a hard row cap exists when it does not.
- **Recommendation:** Either add an enforced cap (`if len(current) >= max_rows: flush()`) or remove the parameters entirely. Do not carry unused "страховка" parameters into the new signature.

### 7. §VII п.1 semantic shift must be reflected in the doc update, not only п.2

- **Checklist item:** project rules — `Functional and WorkLogik.md` alignment.
- **Issue:** §VII п.1 states «накладная создаётся … **вместе с подтверждением** операции». I3 shifts creation to `create_operation` (draft stage). §VII is marked «частичная реализация», so the deviation is allowed without an ADR, but I10 proposes to refine only п.2. Leaving п.1 untouched makes the canonical doc internally contradictory.
- **Recommendation:** I10 should refine **п.1** as well (e.g. «накладная создаётся при создании черновика и фиксируется при подтверждении»), or add a one-line note in §VII that п.1 is superseded by the draft-sync behavior, with a reference to TZ-V3.1I.

### 8. Transaction poisoning risk on `generate_from_operation` failure inside the UoW

- **Checklist item:** Failure Modes — partial failure semantics.
- **Issue:** I3 wraps `generate_from_operation` in `try/except` inside the `create_operation` UoW transaction (H1 does the same in `update_operation`). A DB-level error (constraint, lock) can poison the transaction so that the subsequent `record_audit_event` and the commit fail, even though the intent was "don't abort create because of waybill."
- **Impact:** A waybill-generation DB error could roll back the whole operation create/update, contradicting the TZ's stated non-fatal intent.
- **Recommendation:** Wrap the I3 generation (and ideally the H1 call) in a nested savepoint (`uow.session.begin_nested()`) so a generation failure rolls back only the document work, not the operation. This is a pre-existing pattern, but I3 amplifies its reach.

### 9. I3 insertion point is ambiguous relative to the line-creation loop

- **Checklist item:** Operability — precise implementation instructions.
- **Issue:** TZ I3.1 says insert "после успешного `await uow.operations.create_operation(...)` (строка 421) и до `record_audit_event` (строка 533)". But operation lines are created in the loop at lines 440–530, and `created_operation = await uow.operations.get_operation_by_id(operation.id)` is at line 532. Placing the generate call "after 421" would generate a waybill with **zero lines** (lines not yet inserted).
- **Impact:** An executor following the literal instruction produces an empty draft waybill that only gets populated on the first `update_operation`, partially defeating I3's purpose.
- **Recommendation:** Specify the insertion point as **after line 532** (`created_operation = await get_operation_by_id(...)`), so `generate_from_operation`'s internal `get_operation_by_id` (line 180) sees the populated lines. Also pass `created_by_user_id=user_id` for audit parity with `submit_operation`.

### 10. Lingering draft waybills after submit (document-type sprawl)

- **Checklist item:** Data & State — source of truth across lifecycle.
- **Issue:** `submit_operation` creates the final `act`/`acceptance_certificate` but does **not** void the per-edit draft `waybill`s (different `document_type`, so `_void_existing_documents` does not touch them). After submit, `GET /documents/operations/<id>/documents?document_type=waybill` still returns a `draft` waybill for a submitted operation. Pre-existing, but I3 + H1 increase the volume of draft waybills.
- **Recommendation:** Either void/supersede draft waybills at submit, or document that draft waybills are expected to linger as preview artifacts (and have the BFF/UI filter them out for submitted operations). Pick one and state it in I10.

### 11. I7 Playwright E2E as written cannot inspect a PDF

- **Checklist item:** Test strategy — real, applicable checks.
- **Issue:** The I7 snippet does `page.frameLocator('iframe[name="waybill_pdf"]').locator('h1')` on the rendered PDF. `DocumentRenderView` serves `Content-Type: application/pdf` inline (`documents_views.py:89–95`); browsers render inline PDFs via the built-in viewer with **no DOM** accessible to Playwright. The `h1`/`.header-lines`/`.signature-block` locators will not resolve.
- **Impact:** The I7 acceptance "1 новый E2E-тест зелёный" cannot be met with the provided code.
- **Recommendation:** Redesign I7 to assert at the boundary Playwright can reach: trigger the "Накладная" button, assert the response is `application/pdf` with a non-empty body and a `200`/cache header, and optionally download the PDF and validate content with `pdftotext` (e.g. assert «Накладная №», «Кладовщик», «Лист … из …» appear) or a screenshot/hash comparison. Drop the in-PDF DOM queries.

### 12. `DOCUMENT_RENDERER_VERSION` bump is not in I1 acceptance (cache invalidation)

- **Checklist item:** Operability — deployment without stale artifacts.
- **Issue:** `render_document_pdf` caches by `(document_id, payload_hash, template_name, template_version, renderer_version)` (`services.py:50–104`). I1 changes `waybill_pdf.html` (CSS) but not the payload, so `payload_hash` is unchanged. Without bumping `DOCUMENT_RENDERER_VERSION` (env var) or `template_version`, previously rendered PDFs are served from cache until the 1 h TTL expires — the storekeeper sees the old broken layout for up to an hour after deploy.
- **Recommendation:** Add to I1 acceptance: bump `DOCUMENT_RENDERER_VERSION` (and/or `template_version`) as part of the change, and note it in the deploy/release notes.

---

## 🔵 Notes

### 13. I5 tests cover only MOVE (happy path)

I5's two tests use `MOVE`. Add: `EXPENSE` create → assert **0** draft documents (guards blocker #1's fix); `EXPENSE` create → submit → assert the finalized act payload matches the post-edit state (regression guard for stale-reuse). Also keep the TZ's RECEIVE → 0 assertion.

### 14. Docstring accuracy

TZ line 73 / I2.4 docstring says the function returns `list[dict[page_number, lines, ...]]`; the actual return is `list[dict[str, Any]]`. Minor; align the docstring with the real type.

---

## Gate decision

- **🔴 Blockers: 1 (must fix)** — blocker #1 (draft map). Blocker #2 is downgraded to warning once #1 is applied, but applying both together is strongly recommended for full consistency.
- **🟡 Warnings: 11** — track as explicit TZ tasks/acceptance criteria; do not silently drop.
- **🔵 Notes: 2.**

**Action:** Revise `docs/TZ-V3.1I_WAYBILL_PAGINATION_AND_SYNC_HARDENING.md` Stage I3 (and the I10 documentation items) per blocker #1 and warnings #2, #3, #7, #9, then the plan is ready for an executor. The CSS/pagination core (A1/A2/A3 → I1/I2) is sound in diagnosis and can proceed once the height-budget coupling (#3, #4) and the renderer-version bump (#12) are folded into the acceptance criteria.

No code was modified during this review (architect mode, read-only on source).
