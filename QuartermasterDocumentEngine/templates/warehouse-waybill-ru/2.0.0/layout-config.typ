// warehouse-waybill-ru@2.0.0 — customer-facing layout configuration.
//
// This is the ONLY file a customer/developer should edit when the
// printed form changes (see LAYOUT.md, "Changing the customer form").
// The pagination engine (components/pagination.typ) reads page
// capacities from here; the signature renderer
// (components/signatures.typ) reads the declarative signature blocks
// from here. No customer-facing parameter is hardcoded in the
// rendering logic.
//
// Source of truth: frozen legacy Django/WeasyPrint waybill form
// (Warehouse_web@133e2fa, apps/documents/services.py + templates/
// documents/waybill_pdf.html, WeasyPrint 66.0).

#let layout-config = (
  // -------------------------------------------------------------------------
  // A. Page capacities (visual rows per page role).
  //
  // One "row unit" = one visual line of the item name (see
  // name-chars-per-visual-line below). These are the legacy-calibrated
  // values for the MOVE form (4 signature blocks).
  // -------------------------------------------------------------------------
  page-rows: (
    first: 22,
    middle: 28,
    last: 19,
    single: 15,
  ),

  // Capacities for the last/single page roles by operation type
  // (legacy services.py LAST_PAGE_UNITS / SINGLE_PAGE_UNITS).
  // "default" is the fallback for unknown operation types.
  operation-last-rows: (
    MOVE: 19,
    ISSUE: 25,
    ISSUE_RETURN: 25,
    EXPENSE: 25,
    WRITE_OFF: 25,
    "default": 26,
  ),
  operation-single-rows: (
    MOVE: 15,
    ISSUE: 19,
    ISSUE_RETURN: 19,
    EXPENSE: 19,
    WRITE_OFF: 19,
    "default": 21,
  ),

  // -------------------------------------------------------------------------
  // B. Wrapping model.
  //
  // The pagination engine estimates how many visual lines an item name
  // will occupy, using the same greedy word-wrap model as the legacy
  // renderer: a line holds up to this many characters; tokens longer
  // than this are chunked.
  // -------------------------------------------------------------------------
  name-chars-per-visual-line: 40,

  // -------------------------------------------------------------------------
  // C. Page geometry (must match manifest.yaml page settings).
  // -------------------------------------------------------------------------
  page: (
    size: "a4",
    orientation: "portrait",
    margin: (top: 16mm, right: 14mm, bottom: 14mm, left: 14mm),
  ),

  // -------------------------------------------------------------------------
  // D. Typography.
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
  // E. Signature section.
  //
  // storekeeper-label is rendered on every page; the signature blocks
  // are rendered on the last page (and on a single page).
  // -------------------------------------------------------------------------
  storekeeper-label: "Кладовщик",
  signature-placeholder: "_________________/__________________",
  signature-grid: (
    columns: 1,
    gap-x: 8mm,
    gap-y: 4mm,
  ),
  // Declarative signature sets per operation type (legacy
  // services.py _build_extra_signatures). A block with
  // "driver: true" renders as a single placeholder line; other blocks
  // render label + position/signature hints + placeholders.
  operation-signature-sets: (
    MOVE: (
      (
        key: "operation-approved",
        label: "Операцию разрешил",
        position-label: "должность",
        signature-label: "фио/подпись",
        driver: false,
      ),
      (
        key: "driver",
        label: "Водитель",
        driver: true,
      ),
      (
        key: "base-chief",
        label: "Начальник базы",
        position-label: "должность",
        signature-label: "фио/подпись",
        driver: false,
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
        key: "operation-approved",
        label: "Операцию разрешил",
        position-label: "должность",
        signature-label: "фио/подпись",
        driver: false,
      ),
    ),
    ISSUE: (
      (
        key: "received",
        label: "Получил",
        position-label: "должность",
        signature-label: "фио/подпись",
        driver: false,
      ),
    ),
    ISSUE_RETURN: (
      (
        key: "received",
        label: "Получил",
        position-label: "должность",
        signature-label: "фио/подпись",
        driver: false,
      ),
    ),
    EXPENSE: (
      (
        key: "received",
        label: "Получил",
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
  // F. Requisites.
  //
  // Mirrors Django settings.DOCUMENT_SHIPPER_REQUISITES (the value is
  // rendered verbatim in the first-page header, exactly like the
  // legacy renderer).
  // -------------------------------------------------------------------------
  shipper-requisites:
    "ООО АС «Горизонт», ИНН:0302884660, КПП:752401001, 673314, Забайкальский край, Карымский район, пгт. Курорт-Дарасун, мкр. Северный, д.11, база Угдан",

  // -------------------------------------------------------------------------
  // G. Empty-document table row (legacy waybill_pdf.html {% empty %}).
  // -------------------------------------------------------------------------
  empty-row-text: "Нет строк для печати",

  // -------------------------------------------------------------------------
  // H. Sheet counter / footer.
  //
  // "Лист N из M" renders in a RESERVED footer area (Typst page
  // footer), never inside the body flow — table/signature content
  // can never overlap or clip it, and the counter can never be
  // pushed onto an orphan page by full-capacity tables. The counter
  // shows only when the document has more than one page (same rule
  // as the legacy renderer).
  // -------------------------------------------------------------------------
  counter-prefix: "Лист",
  // Vertical budget reserved for the counter/footer area. The page
  // bottom margin must be >= this value (14mm by default).
  counter-reserve: 12mm,
)
