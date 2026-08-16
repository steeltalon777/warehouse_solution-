# warehouse-waybill-ru@2.0.0 — LAYOUT

Canonical production waybill template (Typst). Reproduces the frozen
legacy Django/WeasyPrint form (`Warehouse_web@133e2fa`,
`apps/documents/templates/documents/waybill_pdf.html` +
`apps/documents/services.py`, WeasyPrint 66.0).

| Field | Value |
|---|---|
| Template id | `warehouse-waybill-ru` |
| Version | `2.0.0` |
| Backend | `typst` (Typst 0.15.1, bundled DejaVu Sans) |
| Document contract | `warehouse.operation-document/v2` |
| Entry point | `main.typ` |
| Customer configuration | `layout-config.typ` |
| Pagination engine | `components/pagination.typ` |
| Signature renderer | `components/signatures.typ` |

---

## 1. Page anatomy

* Paper: A4 portrait (`210 × 297 mm`).
* Margins: top `16 mm`, left/right `14 mm`, bottom `14 mm`
  (identical to the legacy `@page` rule). Content box:
  `182 × 267 mm`.
* Fonts: DejaVu Sans (bundled, `--ignore-system-fonts`); Cyrillic is
  mandatory and always available.
* Body text: `11 pt`, colour `#111827` (legacy `body`).
* Table: 4 columns — `№` (`11 mm`, centred), `Наименование ТМЦ`
  (remaining width), `Ед. изм` (`24 mm`, centred), `Кол-во`
  (`28 mm`, right). Border `0.75 pt` `#111827` (legacy 1 px), header
  row fill `#f3f4f6` (legacy `th` background), cell inset `2 mm`
  (legacy `td` padding).
* Table line box: Typst's default table-cell line box for DejaVu Sans
  is only ~0.76 em, which would compress rows and push the last text
  line against the row border. `render-table` restores the legacy
  ~1.164 em line box with
  `#set text(top-edge: 0.582em, bottom-edge: -0.582em)` and
  `#set par(leading: 0pt)` — a table row always has enough height for
  the actually rendered wrapped content, and one visual unit equals
  one 12.8 pt line + 2 mm insets, exactly like the legacy renderer
  (verified against WeasyPrint row geometry).
* Each logical page is rendered as one non-breakable block separated
  by an explicit `pagebreak()` — Typst never decides where pages
  break.

## 2. First page

* Full header: title `Накладная № <number>` (`16 pt`, bold,
  centred) followed by three requisites lines:
  * `Грузоотправитель: <shipper_requisites>` (config, mirrors
    Django `settings.DOCUMENT_SHIPPER_REQUISITES`);
  * `Грузополучатель: <consignee label>` (payload fallback chain,
    see below);
  * `Основание: <basis label>` (payload fallback chain).
* Table.
* Short signature block: `Кладовщик: _________________/__________________`.
* Capacity: `22` row units (see §5).

Fallback chains (identical to legacy `build_waybill_context`):

* Consignee: `payload.consignee_label` → `receiver.site_name` →
  `receiver.site_code` → `recipient.recipient_name` →
  `sender.site_name` → `sender.site_code` → `—`.
* Basis: `payload.basis_label` → `basis.label` →
  `operation_type_label` → `operation_type` → `Операция`.
* Title number: `payload.operation_display_number` →
  `operation.display_number` → computed `ddMMyy/HHmm/site_id`
  (from `operation_created_at`/`created_at` and `sender.site_id`) →
  envelope `document_number` → envelope `document_id`.

## 3. Middle page

* Short header: title `Накладная № <number>` (`14 pt`, bold,
  centred) only — no requisites.
* Table.
* Short signature block (`Кладовщик`).
* Capacity: `28` row units.

## 4. Last page

* Short header.
* Table with the remaining rows.
* Full signature form:
  * `Кладовщик: _________________/__________________`;
  * declarative extra blocks from `layout-config.typ`
    (`operation-signature-sets[<operation type>]`); MOVE renders 4
    blocks: `Операцию разрешил`, `Водитель` (driver-style), `Начальник
    базы`, `Груз принял`.
* Sheet counter `Лист N из M` (right-aligned, `9 pt`, `#4b5563`) —
  only when the document has more than one page (same rule as
  legacy).
* Capacity: `19` row units for MOVE (per-operation-type values in
  config).

## 5. Pagination capacities

The pagination engine (`components/pagination.typ`) is a faithful
port of the legacy algorithm (`services.py paginate_waybill_lines`,
TZ-V3.1I rev. 7):

* A **row unit** is one visual line of the item name, estimated with
  the same greedy word-wrap model as the legacy renderer
  (`name-chars-per-visual-line: 40`, long tokens chunked at 40).
* Roles and capacities (visual units):

| Role | Page header | Signature block | Capacity (MOVE) |
|---|---|---|---|
| `first` | full | short (`Кладовщик`) | `22` |
| `middle` | short | short (`Кладовщик`) | `28` |
| `last` | short | full form | `19` |
| `single` | full | full form | `15` |

* Single-page rule: when the total unit sum fits the `single`
  capacity, the document is one page with the full first header AND
  the full signature form (legacy `is_first == is_last`).
* Multi-page rule: the first page takes a greedy prefix (always
  reserving ≥ 1 line for the last page), the last page is reserved
  from the tail, middle pages are greedy `middle`-capacity chunks.
* Failure behaviour: a line taller than any page role aborts the
  render with the same error messages the legacy renderer raised as
  `DocumentPdfRenderError` (Typst `panic`, engine exit code 5).

Known worst-case note: a page filled with ALL single-line rows at
full capacity (e.g. 22 rows on the first page, 28 on a middle page)
consumes slightly more than the 267 mm frame (rows are 8.5 mm/unit
exactly like the legacy budget, but the fixed page overhead —
header/thead/storekeeper/counter — is marginally larger than the
legacy calibration constants). The frozen legacy renderer handles
this input by producing an orphan counter page (a documented legacy
defect class that rev.7 was designed to avoid); the Typst template
keeps the page count deterministic with at most a ~2 mm overhang of
the sheet counter. Real production data (mixed line lengths) never
hits this case: the canonical fixtures 1/20/75/200/500 render within
the frame (verified, overflow = 0). Capacities are NOT reduced for
this case — that would change the accepted legacy allocation
semantics; the limitation is documented here instead.

Capacities live ONLY in `layout-config.typ` (`page-rows`,
`operation-last-rows`, `operation-single-rows`). The pagination
engine contains no page-capacity literals.

## 6. Signature section

* `components/signatures.typ` renders signatures from declarative
  data — there is no hardcoded signature count anywhere in the
  template.
* Storekeeper line renders on every page (short form) and as the
  first line of the full form (last/single page).
* Block flavours:
  * standard block: label line, then
    `(должность) _________________ (фио/подпись) _________________/__________________`
    (hints `9 pt`, `#6b7280`; placeholder with `0.2 pt` tracking);
  * driver block (`driver: true`): label line + single placeholder
    line (legacy `Водитель`).
* Blocks flow through a `grid` with `signature-grid.columns`,
  `gap-x`, `gap-y` (row-major; incomplete final row allowed). The
  canonical config uses 1 column / vertical stack, matching the
  legacy stacked layout.

## 7. Signature configuration contract

Each block is a dictionary:

| Key | Type | Meaning |
|---|---|---|
| `key` | string | stable semantic identifier (not rendered) |
| `label` | string | rendered block label |
| `position-label` | string? | hint under the label (standard blocks) |
| `signature-label` | string? | hint under the signature (standard blocks) |
| `driver` | bool | driver-style single-line block |

Blocks are grouped per operation type in
`layout-config.typ.operation-signature-sets`. The canonical MOVE set
(4 blocks) is reproduced from the frozen legacy
`_build_extra_signatures`:

| key | label | flavour |
|---|---|---|
| `operation-approved` | `Операцию разрешил` | standard |
| `driver` | `Водитель` | driver |
| `base-chief` | `Начальник базы` | standard |
| `goods-received` | `Груз принял` | standard |

Payload fields are intentionally NOT invented: the legacy form uses
static placeholders, so blocks carry no payload binding.

## 8. Changing the customer form

`warehouse-waybill-ru@2.0.0` is immutable after acceptance. Any form
change ships as a NEW template version (see §9). Within that new
version, the workflow is:

1. Copy the package directory: `2.0.0` → `2.1.0` (or appropriate
   semver bump).
2. Edit `layout-config.typ` only:

   * Row count on the first page — `page-rows.first`.
   * Row count on a middle page — `page-rows.middle`.
   * Row count on the last page — `operation-last-rows.MOVE`
     (or the relevant operation type; `"default"` is the fallback).
   * Single-page capacity — `operation-single-rows.MOVE`
     (or relevant type).
   * Signature blocks — `operation-signature-sets.MOVE`: add/remove
     block dictionaries; order in the list is render order.
   * Labels — block `label` (and `position-label` /
     `signature-label` hints).
   * Grid — `signature-grid.columns` (1/2/3), `gap-x`, `gap-y`.
   * Wrapping model — `name-chars-per-visual-line` (must stay in
     sync with how long names actually wrap).
   * Requisites text — `shipper-requisites`.

   **When signatures change, also re-check `last_page_rows`**:
   the last-page capacity is calibrated to the full signature form
   height. Example from the legacy calibration: 4 MOVE blocks →
   `19`; growing to 6 blocks reduces the budget to roughly `16`
   (verify empirically — see tests below). The capacity must never
   be derived from the signature height automatically; it stays an
   explicit number in the config.

3. Bump `manifest.yaml` `version` to the new version.
4. Update goldens: run
   `python scripts/golden_update.py --fixtures waybill-qde-1,waybill-qde-20,waybill-qde-75,waybill-qde-200,waybill-qde-500`
   AFTER verifying the new output structure manually — never use a
   blind `--update-golden` to bless any result.
5. Run the test ladder:

   ```bash
   pytest tests/unit -q
   pytest tests/integration tests/component -q
   pytest -m golden -q
   ```

   plus, for a form change:

   ```bash
   python -m tests.harness.compare --fixture waybill-qde-75 \
     --templates warehouse-waybill-ru@1.0,warehouse-waybill-ru@2.1.0 \
     --out spike-out/compare/waybill-qde-75 --skip-visual
   ```

6. Accept the new template version; keep the old version untouched.

**Why a new template version?** Published template versions are
immutable (QDE ADR-0001 D6 / ADR-0031). A form edit changes the
printed document, so it must be a new version with its own goldens —
never an in-place edit of an accepted version.

## 9. Versioning rules

* `2.0.0` is the accepted canonical production version.
* Customer form changes → new semver version (patch/minor/major at
  the customer's discretion): `2.1.0`, `2.2.0`, `3.0.0`, …
* Never edit an accepted version in place.
* Manifest `version` must match the package directory name.
* Old versions keep their own goldens and must keep rendering
  byte-identically.

## 10. Golden / reference provenance

* Legacy visual reference (generated for Phase 6C, not committed as
  binary): frozen renderer `Warehouse_web@133e2fa`,
  `apps.documents.services.render_document_html` + WeasyPrint `66.0`
  (Docker container `warehouse_web`), fixtures
  `tests/fixtures/waybill/waybill-qde-{1,20,75,200,500}.typst.json`
  (same document bodies as the QDE fixtures), output under
  `QuartermasterDocumentEngine/spike-out/phase6c-waybill/legacy/`.
  Page counts produced by the real legacy renderer: 1 / 4 / 10 / 27 /
  66.
* Golden assertions: `tests/golden/warehouse-waybill-ru-2.0.0/*.expected.json`
  (JSON-only, LFS unavailable) generated by
  `scripts/golden_update.py` and verified by `pytest -m golden`.
* Determinism: Typst renders with pinned `--creation-timestamp`
  (engine `DEFAULT_TYPST_TIMESTAMP`), bundled fonts,
  `--ignore-system-fonts`; repeated renders are byte-identical
  (verified by tests).
* Known technological differences vs WeasyPrint (documented, not
  defects): glyph metrics rounding, sub-pixel positioning, text
  extraction order, PDF producer metadata; page count and structure
  are identical to the legacy renderer.
