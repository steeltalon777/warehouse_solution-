// spike-waybill-typst@0.1.0 — warehouse operation waybill in Typst.
// Honest same-form implementation of the WeasyPrint baseline
// `warehouse-waybill-ru@1.0`. Reads the **full normalized envelope**
// from `document.json` (written by ``qm_backends.typst_backend.TypstBackend``).
//
// Phase 2.1: envelope-level fields (``document_number``,
// ``template_id``, ``locale``, ``render_profile`` etc.) are reachable
// directly via ``doc.<field>`` — no warehouse-specific proxy is used
// for ``document_number``. Inner document fields are read via
// ``doc.document.<field>`` (TZ-PHASE2-BACKEND-SPIKE §T5 / §11.2).
//
// Engine-level copies banner (TZ-PHASE2-BACKEND-SPIKE §T8): when the
// engine renders more than one copy, ``copy_number`` and
// ``copies_total`` are injected into the inner document. The template
// prints a small "Экземпляр N из M" banner in the top-right corner. When
// ``copies_total <= 1`` (or the field is missing) no banner is shown,
// so the copies=1 path is byte-identical to Phase 1.
//
// Engine-level watermark (TZ §T8 review note #1): when the engine
// passes ``render_options.watermark == true``, ``document.watermark``
// is set to ``true`` in the inner mapping. The template paints a
// diagonal "ОБРАЗЕЦ" stamp across the page. When the flag is missing
// or ``false`` (Phase 1 default) no watermark is painted, so the
// default render stays byte-identical.
//
// Phase 2.1: density tuning (TZ §3 hardening). Margins reduced to 12 mm,
// table inset to 2 pt, body text 9 pt, line-table text 8 pt — gives
// practically comparable page count to WeasyPrint (target: ≤1.6× WeasyPrint
// page count on waybill-500).

#set page(
  paper: "a4",
  margin: (top: 12mm, left: 12mm, right: 12mm, bottom: 12mm),
  footer: context [
    #set text(size: 7pt, fill: luma(120))
    Лист #counter(page).display() из #counter(page).final().first()
  ],
)
#set text(font: "DejaVu Sans", lang: "ru", size: 9pt)
#set par(leading: 0.55em)

#let doc = json("document.json")
#let inner = doc.document

// --- Watermark (TZ §T8 review note #1) ------------------------------------

#let watermark = inner.at("watermark", default: false)
#if watermark [
  #place(top + left, rotate(35deg, text(60pt, fill: rgb("#88888822"), "ОБРАЗЕЦ")))
]

// --- Copies banner (TZ §T8) ----------------------------------------------

#let copies_total = inner.at("copies_total", default: 0)
#if copies_total > 1 [
  #place(
    top + right,
    text(weight: "bold", size: 10pt)[
      Экземпляр #inner.at("copy_number", default: 1) из #copies_total
    ],
  )
]

// --- Header --------------------------------------------------------------

#align(center)[
  #text(size: 13pt, weight: "bold")[ТОВАРНАЯ НАКЛАДНАЯ] \
  № #doc.at("document_number", default: inner.operation.display_number) \
  от #inner.operation.effective_at
]

#v(0.3em)

#let sender_name = if inner.source_site.organization.legal_name != "" {
  inner.source_site.organization.legal_name
} else {
  inner.source_site.site_name
}
#let receiver_name = if inner.destination_site.organization.legal_name != "" {
  inner.destination_site.organization.legal_name
} else {
  inner.destination_site.site_name
}

#block(
  width: 100%,
  stroke: 0.4pt + black,
  inset: 4pt,
  radius: 0pt,
)[
  #set text(size: 8pt)
  #grid(
    columns: (auto, 1fr),
    column-gutter: 6pt,
    row-gutter: 1pt,
    [Отправитель:], sender_name,
    [Получатель:], receiver_name,
    [Основание:], inner.basis.label,
  )
]

#v(0.3em)

// --- Lines table ---------------------------------------------------------

#let lines = inner.lines
#let total_lines = inner.total_lines

#set text(size: 8pt)
#table(
  columns: (auto, 1fr, auto, auto, auto, auto, auto, 1fr),
  stroke: 0.3pt + black,
  fill: (col, row) => if row == 0 { luma(230) },
  inset: 2pt,
  align: (left, left, left, right, left, left, left, left),
  table.header(
    repeat: true,
    [*№*], [*Наименование*], [*Артикул*], [*Кол-во*], [*Ед.*],
    [*Категория*], [*Партия*], [*Примечание*],
  ),
  ..lines.map(line => (
    [#line.line_number],
    [#line.item_name],
    [#if line.item_sku == "" or line.item_sku == none [—] else [#line.item_sku]],
    [#line.quantity],
    [#line.unit_symbol],
    [#line.category_name],
    [#if line.batch == none [—] else [#line.batch]],
    [#if line.comment == none [—] else [#line.comment]],
  )).flatten(),
)

#v(0.2em)

// --- Subtotal row -------------------------------------------------------

#align(left)[
  #set text(size: 9pt)
  #text(weight: "bold")[Всего наименований:] #total_lines
]

#v(0.4em)

// --- Signatures (MOVE-style: 4 signatures) -------------------------------

#let sigs = inner.signatures
#let roles = sigs.at("roles", default: (:))

#grid(
  columns: (1fr, 1fr),
  column-gutter: 12pt,
  [
    #set text(size: 8pt)
    Сдал: #h(0.5em) #roles.at("handed_over", default: "____________________") \
    #v(1.4em)
    #line(length: 100%, stroke: 0.3pt + black) \
    #set text(size: 7pt, fill: luma(120))
    (подпись)
  ],
  [
    #set text(size: 8pt)
    Принял: #h(0.5em) #roles.at("accepted_by", default: "____________________") \
    #v(1.4em)
    #line(length: 100%, stroke: 0.3pt + black) \
    #set text(size: 7pt, fill: luma(120))
    (подпись)
  ],
)

#v(0.3em)

#grid(
  columns: (1fr, 1fr),
  column-gutter: 12pt,
  [
    #set text(size: 8pt)
    Главный бухгалтер: #h(0.5em) #roles.at("chief_accountant", default: "____________________") \
    #v(1.4em)
    #line(length: 100%, stroke: 0.3pt + black) \
    #set text(size: 7pt, fill: luma(120))
    (подпись)
  ],
  [
    #set text(size: 8pt)
    Дата: #h(0.5em) #inner.operation.effective_at \
    #v(1.4em)
    #line(length: 100%, stroke: 0.3pt + black) \
    #set text(size: 7pt, fill: luma(120))
    (М.П.)
  ],
)