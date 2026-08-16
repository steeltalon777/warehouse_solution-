// warehouse-waybill-ru@2.0.0 — canonical warehouse waybill in Typst.
//
// Reproduces the frozen legacy Django/WeasyPrint waybill form
// (Warehouse_web@133e2fa: apps/documents/services.py +
// apps/documents/templates/documents/waybill_pdf.html, WeasyPrint
// 66.0): same content, same field semantics, same pagination
// behaviour (page roles first/middle/last, capacities 22/28/19 + 15
// single, visual-unit model), same 4-block MOVE signature section.
//
// Customer-facing parameters live in layout-config.typ — editing the
// form must not require touching this file or the components (see
// LAYOUT.md).
//
// Data access: the engine writes the full normalized envelope to
// ``document.json``. Envelope-level fields are read via ``doc.<field>``
// (``document_number``, ``document_id``); the inner warehouse
// document via ``doc.document.<field>``.

#import "layout-config.typ": layout-config
#import "components/pagination.typ": char_len, visual_lines, paginate
#import "components/signatures.typ": render_signature_section

// ---------------------------------------------------------------------------
// Page setup (geometry from layout-config.typ; fonts bundled DejaVu).
// ---------------------------------------------------------------------------

#set page(
  paper: layout-config.page.size,
  margin: layout-config.page.margin,
)
#set text(
  font: "DejaVu Sans",
  lang: "ru",
  size: layout-config.typography.body-size,
  fill: layout-config.typography.body-color,
)
#set par(leading: 0.3em)

#let doc = json("document.json")
#let inner = doc.document

// ---------------------------------------------------------------------------
// Value helpers (mirror legacy services.py helpers)
// ---------------------------------------------------------------------------

#let as_text(v) = {
  if type(v) == none {
    return ""
  }
  if type(v) == str {
    return v
  }
  if type(v) == bool {
    return if v { "true" } else { "false" }
  }
  str(v)
}

// ASCII-only uppercase for operation type tokens (the contract uses
// ASCII operation types; Typst 0.15.1 has no string case transform).
#let to_upper(s) = {
  let upper = (
    "a": "A", "b": "B", "c": "C", "d": "D", "e": "E", "f": "F",
    "g": "G", "h": "H", "i": "I", "j": "J", "k": "K", "l": "L",
    "m": "M", "n": "N", "o": "O", "p": "P", "q": "Q", "r": "R",
    "s": "S", "t": "T", "u": "U", "v": "V", "w": "W", "x": "X",
    "y": "Y", "z": "Z",
  )
  let out = ""
  for c in s {
    out += upper.at(c, default: c)
  }
  out
}

// First non-empty raw value among ``keys``, else ``none``.
#let pick_raw(keys, line) = {
  for k in keys {
    let v = line.at(k, default: none)
    if v != none and as_text(v) != "" {
      return v
    }
  }
  none
}

#let pick_text(keys, line, fallback) = {
  let v = pick_raw(keys, line)
  if v == none {
    return fallback
  }
  as_text(v)
}

// Legacy _format_quantity: Decimal normalize, "f" format, trailing
// zeros stripped after the decimal point (dot separator).
#let format_quantity(v) = {
  if type(v) == none {
    return "0"
  }
  if type(v) == str {
    if v == "" {
      return "0"
    }
    return v
  }
  if type(v) == int {
    return str(v)
  }
  if type(v) == float {
    if calc.abs(v - calc.round(v)) < 1e-9 {
      return str(calc.round(v))
    }
    let s = str(v)
    if s.contains(".") {
      let parts = s.split(".")
      let frac = parts.at(1)
      while char_len(frac) > 0 and frac.at(frac.len() - 1) == "0" {
        frac = frac.slice(0, frac.len() - 1)
      }
      if frac.len() == 0 {
        return parts.at(0)
      }
      return parts.at(0) + "." + frac
    }
    return s
  }
  str(v)
}

// Legacy _normalize_line: line_number / item_name / unit / quantity.
#let normalize_lines(raw_lines) = {
  raw_lines.enumerate().map(((idx, line)) => (
    line-number: {
      let ln = line.at("line_number", default: none)
      if ln == none or ln == 0 {
        str(idx + 1)
      } else {
        str(ln)
      }
    },
    item-name: pick_text(
      ("item_name", "item_name_snapshot"),
      line,
      "—",
    ),
    unit: pick_text(
      ("unit_symbol", "unit_name", "unit_symbol_snapshot"),
      line,
      "—",
    ),
    quantity: format_quantity(pick_raw(("quantity", "qty"), line)),
  ))
}

// Break long tokens (longer than ``chars_per_line`` characters) with
// zero-width spaces so Typst wraps them exactly where the legacy
// estimator chunked them (overflow-wrap: anywhere semantics). Words
// are rejoined with single spaces.
#let wrap_name(name, chars_per_line) = {
  let words = name.split(regex("\s+"))
  let parts = ()
  for w in words {
    if char_len(w) > chars_per_line {
      let out = ""
      let i = 0
      for c in w {
        if i > 0 and calc.rem(i, chars_per_line) == 0 {
          out += "\u{200b}"
        }
        out += c
        i += 1
      }
      parts.push(out)
    } else {
      parts.push(w)
    }
  }
  parts.join(" ")
}

// ---------------------------------------------------------------------------
// Header fields (legacy build_waybill_context fallback chains)
// ---------------------------------------------------------------------------

#let operation_display_number() = {
  let v = inner.at("operation_display_number", default: none)
  if v != none and as_text(v) != "" {
    return as_text(v)
  }
  let op = inner.at("operation", default: (:))
  let v2 = op.at("display_number", default: none)
  if v2 != none and as_text(v2) != "" {
    return as_text(v2)
  }
  // Computed fallback: ddMMyy/HHmm/site_id from operation_created_at
  // (or created_at) and sender.site_id.
  let site_id = "0"
  let sv = inner.at("sender", default: (:)).at("site_id", default: none)
  if sv != none {
    site_id = str(sv)
  }
  let dt = inner.at(
    "operation_created_at",
    default: inner.at("created_at", default: ""),
  )
  if type(dt) == str and dt.len() >= 16 {
    let iso = dt
    let dd = iso.slice(8, 10)
    let mm = iso.slice(5, 7)
    let yy = iso.slice(2, 4)
    let hh = iso.slice(11, 13)
    let mn = iso.slice(14, 16)
    return dd + mm + yy + "/" + hh + mn + "/" + site_id
  }
  let v3 = doc.at("document_number", default: none)
  if v3 != none and as_text(v3) != "" {
    return as_text(v3)
  }
  let v4 = doc.at("document_id", default: none)
  if v4 != none and as_text(v4) != "" {
    return as_text(v4)
  }
  ""
}

#let consignee_label() = {
  let v = inner.at("consignee_label", default: none)
  if v != none and as_text(v) != "" {
    return as_text(v)
  }
  let receiver = inner.at("receiver", default: (:))
  let v2 = receiver.at("site_name", default: none)
  if v2 != none and as_text(v2) != "" {
    return as_text(v2)
  }
  let v3 = receiver.at("site_code", default: none)
  if v3 != none and as_text(v3) != "" {
    return as_text(v3)
  }
  let recipient = inner.at("recipient", default: none)
  if type(recipient) == dictionary {
    let v4 = recipient.at("recipient_name", default: none)
    if v4 != none and as_text(v4) != "" {
      return as_text(v4)
    }
  }
  let sender = inner.at("sender", default: (:))
  let v5 = sender.at("site_name", default: none)
  if v5 != none and as_text(v5) != "" {
    return as_text(v5)
  }
  let v6 = sender.at("site_code", default: none)
  if v6 != none and as_text(v6) != "" {
    return as_text(v6)
  }
  "—"
}

#let basis_label() = {
  let v = inner.at("basis_label", default: none)
  if v != none and as_text(v) != "" {
    return as_text(v)
  }
  let basis = inner.at("basis", default: (:))
  let v2 = basis.at("label", default: none)
  if v2 != none and as_text(v2) != "" {
    return as_text(v2)
  }
  let v3 = inner.at(
    "operation_type_label",
    default: inner.at("operation_type", default: none),
  )
  if v3 != none and as_text(v3) != "" {
    return as_text(v3)
  }
  "Операция"
}

#let title = "Накладная № " + operation_display_number()

// ---------------------------------------------------------------------------
// Page rendering (page roles from the pagination engine)
// ---------------------------------------------------------------------------

#let render_title(is_first, config) = {
  if is_first {
    [
      #block(spacing: 6mm)[
        #align(center)[
          #text(size: config.typography.title-size, weight: "bold")[#title]
        ]
      ]
      #block(spacing: 6mm)[
        #set par(leading: 0.3em)
        #text(weight: "bold")[Грузоотправитель:] #config.shipper-requisites \
        #v(1.5mm)
        #text(weight: "bold")[Грузополучатель:] #consignee_label() \
        #v(1.5mm)
        #text(weight: "bold")[Основание:] #basis_label()
      ]
    ]
  } else {
    block(spacing: 4mm)[
      #align(center)[
        #text(size: config.typography.short-title-size, weight: "bold")[#title]
      ]
    ]
  }
}

#let render_table(rows, config) = {
  block[
    // leading 0.4em reproduces the legacy table line box (~8.5 mm per
    // single-line row incl. 2mm cell inset) that the page capacities
    // were calibrated against (TZ-V3.1I rev.7).
    #set par(leading: 0.4em)
    #table(
      columns: (11mm, 1fr, 24mm, 28mm),
      stroke: config.typography.table-stroke + config.typography.body-color,
      inset: 2mm,
      align: (center + top, left + top, center + top, right + top),
      table.header(
        table.cell(fill: config.typography.header-fill, align: center + top, [*№*]),
        table.cell(fill: config.typography.header-fill, align: center + top, [*Наименование ТМЦ*]),
        table.cell(fill: config.typography.header-fill, align: center + top, [*Ед. изм*]),
        table.cell(fill: config.typography.header-fill, align: right + top, [*Кол-во*]),
      ),
      ..if rows.len() == 0 {
        (([—], [#config.empty-row-text], [—], [0]),)
      } else {
        rows.map(row => (
          [#row.line-number],
          [#wrap_name(row.item-name, config.name-chars-per-visual-line)],
          [#row.unit],
          [#row.quantity],
        ))
      }.flatten(),
    )
  ]
}

#let render_counter(page_number, total_pages, config) = [
  #v(4mm)
  #align(right)[
    #set text(
      size: config.typography.counter-size,
      fill: config.typography.counter-color,
    )
    #config.counter-prefix #page_number из #total_pages
  ]
]

#let render_page(page_desc, config, blocks) = {
  block(breakable: false)[
    #render_title(page_desc.is-first, config)
    #render_table(page_desc.lines, config)
    #render_signature_section(page_desc.is-last, config, blocks)
    #if page_desc.total-pages > 1 [
      #render_counter(page_desc.page-number, page_desc.total-pages, config)
    ]
  ]
}

// ---------------------------------------------------------------------------
// Document flow: normalize -> estimate units -> paginate -> render
// ---------------------------------------------------------------------------

#let raw_lines = inner.at("lines", default: ())
#let rows = normalize_lines(raw_lines)
#let units = rows.map(
  r => visual_lines(r.item-name, layout-config.name-chars-per-visual-line),
)
#let op_type = to_upper(as_text(inner.at("operation_type", default: "RECEIVE")))
#let caps = (
  first: layout-config.page-rows.first,
  middle: layout-config.page-rows.middle,
  last: layout-config.operation-last-rows.at(
    op_type,
    default: layout-config.operation-last-rows.at("default"),
  ),
  single: layout-config.operation-single-rows.at(
    op_type,
    default: layout-config.operation-single-rows.at("default"),
  ),
)
#let pages = paginate(rows, units, caps)
#let signature_blocks = layout-config.operation-signature-sets.at(
  op_type,
  default: (),
)

#set document(title: title)

#for (idx, page_desc) in pages.enumerate() {
  render_page(page_desc, layout-config, signature_blocks)
  if idx < pages.len() - 1 {
    pagebreak()
  }
}
