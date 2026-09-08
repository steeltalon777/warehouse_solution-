// warehouse-waybill-ru@2.2.0 — customer-facing layout configuration.
//
// This is the ONLY file a customer/developer should edit when the
// printed form changes (see LAYOUT.md, "Changing the customer form").
// No customer-facing parameter is hardcoded in the rendering logic.
//
// 2.2.0 is the measurable pagination rebalance (05.09.2026,
// TZ-QDE_WAYBILL_PAGINATION_REBALANCE_v1.0). Compared to 2.1.0:
//   * the physical sheet geometry is explicit (page-geometry) and the
//     engine verifies its consistency with the page margins;
//   * the legacy "row unit" capacities (page-rows, operation-*-rows,
//     name-chars-per-visual-line) are REMOVED — pagination is computed
//     from measured physical heights, not from character heuristics;
//   * font-fallback and row-stretch parameters are added;
//   * signature sets and requisites are unchanged from 2.1.0 (the
//     customer-approved form of 03.09.2026).

#let layout-config = (
  // -------------------------------------------------------------------------
  // A. Physical sheet geometry (single source of truth).
  //
  // The engine verifies at render start that content-height ==
  // paper-height - margin.top - margin.bottom and content-width ==
  // paper-width - margin.left - margin.right; on mismatch it panics
  // ("page-geometry is inconsistent with page margins"). All
  // pagination arithmetic is derived from content-height/width.
  //
  // Landscape orientation later: change orientation + the four
  // paper/content numbers; the algorithm is unchanged.
  // -------------------------------------------------------------------------
  page: (
    size: "a4",
    orientation: "portrait",
    margin: (top: 16mm, right: 14mm, bottom: 14mm, left: 14mm),
  ),
  page-geometry: (
    paper-width: 210mm,
    paper-height: 297mm,
    content-width: 182mm,  // = paper-width - left - right
    content-height: 267mm, // = paper-height - top - bottom
  ),

  // -------------------------------------------------------------------------
  // B. Token chunking for wrap_name (overflow-wrap: anywhere model).
  //
  // Used ONLY to break over-long single tokens with zero-width spaces
  // so Typst can wrap them. NOT a pagination capacity.
  // -------------------------------------------------------------------------
  max-token-chars: 40,

  // -------------------------------------------------------------------------
  // C. Font fallback (TZ §4.3). Only item names are affected.
  //
  // If a measured row is taller than max-lines x H1 (the normal
  // one-line row height), the name cell is re-measured with the next
  // smaller size; the first size that brings the row height to
  // <= max-lines x H1 wins. If even the last size does not fit, the
  // row keeps its natural height (no panic).
  // -------------------------------------------------------------------------
  font-fallback: (
    max-lines: 2,
    sizes: (10pt, 9pt),
  ),

  // -------------------------------------------------------------------------
  // D. Row stretch (TZ §4.5). Stretch only, never compress.
  //
  // s_p = min((A_role - safety-gap) / H_p, max). s_p <= 1 renders
  // natural heights; s_p > 1 stretches each row of the page to
  // h_i * s_p (the table visually fills the page, but a page with few
  // rows is never stretched to the full sheet — free space stays at
  // the bottom).
  // -------------------------------------------------------------------------
  row-stretch: (
    max: 1.15,
    safety-gap: 0.5mm,
  ),

  // -------------------------------------------------------------------------
  // E. Typography (unchanged from 2.1.0).
  // -------------------------------------------------------------------------
  typography: (
    body-size: 11pt,
    title-size: 16pt,
    short-title-size: 14pt,
    hint-size: 9pt,
    counter-size: 9pt,
    body-color: rgb("#111827"),
    hint-color: rgb("#6b7280"),
    counter-color: rgb("#4b5563"),
    header-fill: rgb("#f3f4f6"),
    table-stroke: 0.6pt,
  ),

  // -------------------------------------------------------------------------
  // F. Signature section (unchanged from the approved 2.1.0 form,
  // customer form 03.09.2026): storekeeper line + declarative blocks
  // on the LAST page only.
  // -------------------------------------------------------------------------
  storekeeper-label: "Кладовщик",
  signature-placeholder: "_________________/__________________",
  signature-grid: (
    columns: 1,
    gap-x: 8mm,
    gap-y: 4mm,
  ),
  operation-signature-sets: (
    MOVE: (
      (
        key: "driver",
        label: "Водитель",
        driver: true,
      ),
      (
        key: "goods-received",
        label: "Груз принял",
        position-label: "должность",
        signature-label: "фио/подпись",
        driver: false,
      ),
    ),
    WRITE_OFF: (
      (
        key: "write-off-approved",
        label: "Списание разрешил",
        position-label: "должность",
        signature-label: "фио/подпись",
        driver: false,
      ),
    ),
    ISSUE: (
      (
        key: "received",
        label: "Принял",
        position-label: "должность",
        signature-label: "фио/подпись",
        driver: false,
      ),
    ),
    ISSUE_RETURN: (
      (
        key: "received",
        label: "Принял",
        position-label: "должность",
        signature-label: "фио/подпись",
        driver: false,
      ),
    ),
    EXPENSE: (
      (
        key: "received",
        label: "Принял",
        position-label: "должность",
        signature-label: "фио/подпись",
        driver: false,
      ),
    ),
    RECEIVE: (),
    CORRECTION: (),
    ADJUSTMENT: (),
  ),

  // -------------------------------------------------------------------------
  // G. Requisites (unchanged from 2.1.0; mirrors Django
  // settings.DOCUMENT_SHIPPER_REQUISITES).
  // -------------------------------------------------------------------------
  shipper-requisites:
    "ООО АС «Горизонт», ИНН:0302884660, КПП:752401001, 673314, Забайкальский край, Карымский район, пгт. Курорт-Дарасун, мкр. Северный, д.11, база Угдан",

  // -------------------------------------------------------------------------
  // H. Empty-document table row (legacy waybill_pdf.html {% empty %}).
  // -------------------------------------------------------------------------
  empty-row-text: "Нет строк для печати",

  // -------------------------------------------------------------------------
  // I. Sheet counter / footer (unchanged from 2.1.0).
  //
  // "Лист N из M" renders in the RESERVED footer area (Typst page
  // footer), never inside the body flow; shows only when the document
  // has more than one page.
  // -------------------------------------------------------------------------
  counter-prefix: "Лист",
  counter-reserve: 12mm,
)
