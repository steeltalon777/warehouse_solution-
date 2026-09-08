# warehouse-waybill-ru@2.2.0 — LAYOUT

Canonical production waybill template (Typst). Derived from
`warehouse-waybill-ru@2.1.0` (customer form 03.09.2026: signatures on
the last page only, per-type signature sets).

**2.2.0 is the measurable pagination rebalance (05.09.2026,
TZ-QDE_WAYBILL_PAGINATION_REBALANCE_v1.0) and intentionally replaces
the pagination MODEL:**

* row heights, table header, title blocks and signature blocks are
  **measured** with Typst `measure()` inside a single `#context` —
  the legacy character heuristic (`visual_lines`,
  `name-chars-per-visual-line`, unit capacities) is REMOVED;
* pages are packed and **balanced by physical height** (water-filling
  adaptation of TZ §4.4 — see §5): uniform fill level, no page
  "stumps";
* rows are **stretched** up to +15% so the table visually fills the
  page (never compressed);
* item names taller than 2 normal lines get a **font fallback**
  (11pt → 10pt → 9pt, name cell only);
* the physical sheet geometry is explicit (`page-geometry`) and
  verified against the page margins at render start.

**This is NOT a port of the legacy algorithm.** Page counts of 2.2.0
intentionally diverge from the frozen legacy renderer for "fat"
documents (see §10).

| Field | Value |
|---|---|
| Template id | `warehouse-waybill-ru` |
| Version | `2.2.0` |
| Backend | `typst` (Typst 0.15.1, bundled DejaVu Sans) |
| Document contract | `warehouse.operation-document/v2` |
| Entry point | `main.typ` |
| Customer configuration | `layout-config.typ` |
| Pagination engine | `components/pagination.typ` (pure, measured heights) |
| Signature renderer | `components/signatures.typ` (unchanged from 2.1.0) |

---

## 1. Page anatomy

* Paper: A4 portrait (`210 × 297 mm`).
* Margins: top `16 mm`, left/right `14 mm`, bottom `14 mm`
  (identical to the legacy `@page` rule). Content box:
  `182 × 267 mm` — declared explicitly in `layout-config.page-geometry`
  and verified at render start (`content-height == paper-height −
  margin.top − margin.bottom`, same for width; mismatch → panic
  `page-geometry is inconsistent with page margins`).
* Fonts: DejaVu Sans (bundled, `--ignore-system-fonts`); Cyrillic is
  mandatory and always available.
* Body text: `11 pt`, colour `#111827`; table line box restored with
  `#set text(top-edge: 0.582em, bottom-edge: -0.582em)` and
  `#set par(leading: 0pt)` (legacy ~12.8 pt line box).
* Table: 4 columns — `№` (`11 mm`, centred), `Наименование ТМЦ`
  (remaining width), `Ед. изм` (`24 mm`, centred), `Кол-во`
  (`28 mm`, right). Border `0.6 pt` `#111827`, header row fill
  `#f3f4f6`, cell inset `2 mm`.
* **Unit model**: every page-flow unit (title block, table, signature
  block) is wrapped in `block(above: 0pt, below: 0pt)`; all internal
  spacing is expressed inside the unit (`block(spacing: …)`, `v()`).
  A unit's measured height equals the height it actually occupies, so
  a page is exactly the sum of its units. Typst never decides where a
  page breaks: each page is one `block(breakable: false)` separated by
  an explicit `pagebreak()`.

## 2. First page

* Full header: title `Накладная № <number>` (`16 pt`, bold,
  centred) followed by three requisites lines:
  * `Грузоотправитель: <shipper_requisites>` (config);
  * `Грузополучатель: <consignee label>` (payload fallback chain);
  * `Основание: <basis label>` (payload fallback chains — unchanged
    from 2.1.0).
* Table.
* No signature content.
* Available data-row area: `A_first = content-height − HF − HT`
  (HF/HM/HT are measured, not constants).

Fallback chains (identical to 2.1.0 / legacy `build_waybill_context`):

* Consignee: `payload.consignee_label` → `receiver.site_name` →
  `receiver.site_code` → `recipient.recipient_name` →
  `sender.site_name` → `sender.site_code` → `—`.
* Basis: `payload.basis_label` → `basis.label` →
  `operation_type_label` → `operation_type` → `Операция`.
* Title number: `payload.operation_display_number` →
  `operation.display_number` → computed `ddMMyy/HHmm/site_id` →
  envelope `document_number` → envelope `document_id`.

## 3. Middle page

* Short header: title `Накладная № <number>` (`14 pt`, bold,
  centred) only — no requisites.
* Table.
* No signature content.
* Available data-row area: `A_middle = content-height − HM − HT`.

## 4. Last page

* Short header.
* Table with the remaining rows.
* Full signature form (unchanged 2.1.0 sets — see §7):
  * `Кладовщик: _________________/__________________` — always;
  * MOVE: `Водитель` (driver-style) + `Груз принял`;
  * ISSUE / ISSUE_RETURN / EXPENSE: `Принял`;
  * WRITE_OFF: `Списание разрешил`;
  * RECEIVE / ADJUSTMENT / CORRECTION: no extra blocks.
* Sheet counter `Лист N из M` — rendered in the **reserved page
  footer area** (Typst page footer inside the bottom margin), never
  inside the body flow; shows only when the document has more than
  one page.
* Available data-row area: `A_last = content-height − HM − HT − HS`,
  where `HS` is the measured signature block of the operation type
  (`HS(op)`).

### Footer / counter invariant

Unchanged from 2.1.0: the counter lives in the reserved footer area,
body content can never overlap/clip it or push it onto an orphan
page. `counter-reserve: 12mm` ≤ bottom margin `14 mm`.

## 5. Pagination model (measured, balanced)

`components/pagination.typ` is a **pure** engine: it receives ready
measured heights and role areas, and returns index ranges. It never
calls `measure()` or `json()` and contains no capacity literals.

### 5.1 Measurement (main.typ, one `#context`)

* `H1` — the height of a one-line row (reference ~8.5 mm; taken from
  the measurement only). Row heights `h[i]` are measured as real
  one-row tables with the actual content (cached by exact
  name|unit|quantity content).
* Page chrome: `HF` (first-page header block), `HM` (short title),
  `HT` (table header row — measured via a dedicated header-only unit,
  NOT through the data-table builder whose empty-input branch renders
  the stub row), `HS(op)` (signature block per operation type).
* Available areas: `A_first = C − HF − HT`,
  `A_middle = C − HM − HT`, `A_last = C − HM − HT − HS(op)`,
  `A_single = C − HF − HT − HS(op)`.

### 5.2 Font fallback (before packing)

If `h[i] > 2 × H1`, the name cell is re-measured at `10pt`, then
`9pt` (`font-fallback.sizes`); the first size with
`h ≤ 2 × H1` wins. If none fits, the row keeps its natural height and
participates in packing as-is (no panic). Only the name cell changes
size; other cells keep 11pt.

### 5.3 Packing and balancing (TZ §4.4, water-filling adaptation)

Steps (deterministic; rows are never reordered):

1. Empty document → one stub "first" page (no stretch).
2. Any row taller than the largest role area → panic
   `Waybill line is too tall to fit on one page.`
3. First row taller than `A_first` → panic
   `Waybill line is too tall for the first-page layout.`
4. A single row taller than `A_single` → panic
   `Waybill line is too tall for the single-page layout.`
5. Everything (with full header AND signature form) fitting
   `A_single` → one page (minimal page count).
6. **Last-page reserve = maximal suffix**: rows are taken from the
   end while their summed height fits the hard `A_last`; the suffix
   keeps ≥ 1 row and leaves ≥ 1 row to the prefix. No trailing row
   fits → panic `Waybill line is too tall for the last-page layout.`
7. **Prefix balancing over first + middle pages**: for
   `P = P_min .. P_min + 4` (`P_min` = least P with
   `Σprefix ≤ A_first + P·A_middle`), greedy in-order packing with a
   per-page target `T = F' × A_role` where
   `F' = remaining / remaining_capacity` is recomputed at every page
   start; pages close only when non-empty; the final prefix page
   absorbs the remainder. First successful P wins.
8. If no P packs (pathological separability): the same P range is
   retried greedily by **hard limits** (balancing disabled for that
   input). Still no success → panic
   `Waybill pagination failed.`

**Deliberate deviation from the literal §4.4 soft-budget formula**
(customer-approved 05.09.2026): the literal budgets
`T = F·A_role` with `F = Σprefix/(A_first + P·A_middle)` sum exactly
to `Σprefix`, so success would require a perfect zero-waste tiling —
on real mixed inputs the pass fails systematically and falls back to
hard greedy with page "stumps", violating the uniformity criterion
(§6.3 of the TZ). The water-filling adaptation keeps every §4.4
invariant: row order, determinism, maximal last-page suffix, hard
fallback, exact panic messages.

### 5.4 Row stretch (TZ §4.5)

Per page: `s_p = min((A_role − safety-gap) / H_p, 1.15)`.
`s_p ≤ 1` → natural heights; `s_p > 1` → every row of that page is
rendered with the target height `h[i]·s_p` (cells inside
`block(height: t_i − 2·inset)`, content top-aligned, cell alignments
unchanged). Pages are never overfilled; a page with few rows is
stretched by at most +15% and keeps free space at the bottom.
Compression below natural height is intentionally NOT implemented:
packing by measured heights never overfills, and squeezing risks
clipping text in `block(height: …)`.

## 6. Signature section

Unchanged from 2.1.0: declarative blocks from
`operation-signature-sets`, storekeeper line always present on the
last page, `grid` with `signature-grid.columns/gap-x/gap-y`. First and
middle pages carry no signature content.

## 7. Signature configuration contract

Unchanged from 2.1.0 (see the 2.1.0 LAYOUT.md §7): block dictionary
`key / label / position-label / signature-label / driver`, grouped per
operation type. The 2.2.0 sets equal the customer-approved 2.1.0 sets.

## 8. Changing the customer form

`warehouse-waybill-ru@2.1.0` is frozen on disk (never accepted as
production; superseded by 2.2.0). Form changes ship as a NEW template
version. Within 2.2.0 the tunable parameters are ALL in
`layout-config.typ`:

* Sheet geometry — `page` (margins) and `page-geometry`
  (paper/content sizes; must satisfy the consistency invariant).
* Landscape orientation later: `orientation` + the four paper/content
  numbers; the algorithm is unchanged.
* Token chunking — `max-token-chars` (only affects `wrap_name`).
* Font fallback — `font-fallback.max-lines` / `.sizes`.
* Row stretch — `row-stretch.max` / `.safety-gap`.
* Typography — `typography.*`.
* Signature blocks — `operation-signature-sets.<TYPE>`; grid —
  `signature-grid.*`; labels/hints per block.
* Requisites — `shipper-requisites`; empty row text —
  `empty-row-text`; counter — `counter-prefix`, `counter-reserve`.

There are NO page-capacity numbers anymore: page fill is derived from
measurements. After changing signature sets the LAST/single page
areas adapt automatically (`HS(op)` is measured).

Workflow:

1. Copy the package directory to a new semver version.
2. Edit `layout-config.typ` only.
3. Bump `manifest.yaml` `version` (must match the directory name).
4. Run the test ladder (QDE unit + integration + golden; for a form
   change also a structural comparison per the integration TZ).
5. Accept the new version; keep the old version untouched.

**Why a new template version?** Published template versions are
immutable (ADR-0031, ADR-0001 D6). A form edit changes the printed
document and must be a new version with its own goldens.

## 9. Versioning rules

* `2.0.0` — frozen legacy-port baseline; keeps rendering
  byte-identically with its own goldens (regression suite
  `tests/integration/test_canonical_waybill.py` pins it).
* `2.1.0` — customer form change of 03.09.2026; frozen on disk,
  goldens not produced (form was superseded before visual acceptance
  completed).
* `2.2.0` — measurable pagination rebalance (this version); the
  current production candidate. Goldens for 2.2.0 are produced by a
  separate architect step AFTER the customer accepts the printed
  form.
* Customer form changes → new semver version; never edit an accepted
  version in place; manifest `version` must match the package
  directory name.

## 10. Golden / reference provenance

* Legacy visual reference (2.0.0 era): frozen renderer
  `Warehouse_web@133e2fa` + WeasyPrint 66.0, page counts
  1 / 4 / 10 / 27 / 66 for the 1/20/75/200/500 line fixtures.
* **2.2.0 intentionally diverges**: page counts are derived from
  measured physical heights with balancing, NOT from the legacy unit
  model. Observed 2.2.0 counts for the same fixtures (05.09.2026):
  1 / 2 / 5 / 12 / 30 — all ≤ legacy. For real documents the
  divergence is larger (e.g. MOVE 143 lines: legacy 8 pages with an
  uneven 6-line page vs 2.2.0 6 pages uniformly filled). This is the
  documented, customer-approved purpose of 2.2.0; the shadow
  comparison procedure (6D/6E) must treat page-count differences for
  2.2.0 as expected, not as defects.
* Golden assertions for 2.2.0 are produced after customer acceptance
  (`scripts/golden_update.py --fixtures waybill-qde22-1,…`); until
  then `pytest -m golden` must stay green on the frozen versions.
* Determinism: Typst renders with pinned `--creation-timestamp`
  (engine `DEFAULT_TYPST_TIMESTAMP`), bundled fonts,
  `--ignore-system-fonts`; repeated renders are byte-identical
  (verified per render in the 2.2.0 integration checks).
