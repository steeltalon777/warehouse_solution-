// warehouse-waybill-ru@2.2.0 — canonical warehouse waybill in Typst.
//
// Derived from 2.1.0 (customer form 03.09.2026: signatures on the
// last page only, per-type signature sets). 2.2.0 is the measurable
// pagination rebalance (05.09.2026,
// TZ-QDE_WAYBILL_PAGINATION_REBALANCE_v1.0): row heights and page
// chrome are MEASURED with Typst measure() inside a single #context,
// the distribution is computed by the balanced pagination engine
// (components/pagination.typ, water-filling adaptation of TZ §4.4 —
// NOT the legacy character heuristic), rows are stretched up to
// +15% to fill pages, and over-tall names get a 10pt/9pt fallback.
//
// Unit model (CP1-verified): every page-flow unit (title, table,
// signature) is a block(above: 0pt, below: 0pt) wrapper — measured
// height equals the actually occupied height, so a page is exactly
// the sum of its units. Internal spacing is expressed with v() /
// block(spacing) INSIDE the units.
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
#import "components/pagination.typ": char_len, paginate
#import "components/signatures.typ": render_signature_section

// ---------------------------------------------------------------------------
// Page setup (geometry from layout-config.typ; fonts bundled DejaVu).
// ---------------------------------------------------------------------------

#set page(
  paper: layout-config.page.size,
  margin: layout-config.page.margin,
  // The sheet counter lives in the RESERVED footer area (bottom
  // margin), so body content can never overlap/clip it and a
  // full-capacity table can never push it onto an orphan page
  // (hardening invariant; legacy WeasyPrint instead produced an
  // orphan counter-only page on such inputs — intentionally NOT
  // reproduced). Shows only when the document has > 1 page.
  footer: context [
    #if counter(page).final().first() > 1 [
      #align(right)[
        #set text(
          size: layout-config.typography.counter-size,
          fill: layout-config.typography.counter-color,
        )
        #layout-config.counter-prefix #counter(page).display() из #counter(page).final().first()
      ]
    ]
  ],
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
// zero-width spaces so Typst wraps them (overflow-wrap: anywhere
// semantics). Words are rejoined with single spaces.
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
// Layout units (zero external spacing — measured height == occupied
// height; CP1 ground-truth verified).
// ---------------------------------------------------------------------------

// First-page title unit: full title + requisites (internal spacing
// only).
#let title_unit(is_first, config) = block(above: 0pt, below: 0pt)[
  #if is_first {
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
]

// Table row cell content: name with optional fallback size.
#let name_cell(row, config) = {
  let size = row.at("size", default: none)
  let name = wrap_name(row.item-name, config.max-token-chars)
  if size == none {
    [#name]
  } else {
    text(size: size)[#name]
  }
}

// One logical table row (4 cells). ``target`` = stretched row height
// (length) or none (natural height). The fixed-height block keeps
// content top-aligned; the table-level cell alignment handles the
// horizontal placement of the block box.
#let row_cells(row, config, target) = {
  if target == none {
    (
      [#row.line-number],
      [#name_cell(row, config)],
      [#row.unit],
      [#row.quantity],
    )
  } else {
    (
      block(height: target - 4mm)[#row.line-number],
      block(height: target - 4mm)[#name_cell(row, config)],
      block(height: target - 4mm)[#row.unit],
      block(height: target - 4mm)[#row.quantity],
    )
  }
}

// Header cells (shared by the data table and the header-only unit).
#let header_cells(config) = (
  table.cell(fill: config.typography.header-fill, align: center + top, [*№*]),
  table.cell(fill: config.typography.header-fill, align: center + top, [*Наименование ТМЦ*]),
  table.cell(fill: config.typography.header-fill, align: center + top, [*Ед. изм*]),
  table.cell(fill: config.typography.header-fill, align: right + top, [*Кол-во*]),
)

// Table unit: header row + data rows (same builder for measurement
// and rendering). Empty rows -> the empty-document stub row.
#let table_unit(rows, config, sizes, targets) = block(above: 0pt, below: 0pt)[
  // Legacy line-box geometry: explicit top/bottom edges restore the
  // legacy ~1.164 em line box (see LAYOUT.md §1).
  #set par(leading: 0pt)
  #set text(top-edge: 0.582em, bottom-edge: -0.582em)
  #table(
    columns: (11mm, 1fr, 24mm, 28mm),
    stroke: config.typography.table-stroke + config.typography.body-color,
    inset: 2mm,
    align: (center + top, left + top, center + top, right + top),
    table.header(..header_cells(config)),
    ..if rows.len() == 0 {
      (([—], [#config.empty-row-text], [—], [0]),)
    } else {
      rows.enumerate().map(((idx, row)) => row_cells(
        (..row, size: sizes.at(idx)),
        config,
        if targets == none { none } else { targets.at(idx) },
      )).flatten()
    }.flatten(),
  )
]

// Header-row-only unit: the exact HT chrome (NO stub row — the data
// table with empty rows renders the stub instead, which would measure
// one line too tall).
#let header_row_unit(config) = block(above: 0pt, below: 0pt)[
  #set par(leading: 0pt)
  #set text(top-edge: 0.582em, bottom-edge: -0.582em)
  #table(
    columns: (11mm, 1fr, 24mm, 28mm),
    stroke: config.typography.table-stroke + config.typography.body-color,
    inset: 2mm,
    align: (center + top, left + top, center + top, right + top),
    table.header(..header_cells(config)),
  )
]

// Signature unit (last page only; content from components/signatures.typ,
// unchanged).
#let sig_unit(config, blocks) = block(above: 0pt, below: 0pt, breakable: false)[
  #render_signature_section(true, config, blocks)
]

// Page unit: title + table (+ signatures on the last page).
#let render_page(page, config, blocks, all_rows, all_sizes) = block(above: 0pt, below: 0pt, breakable: false)[
  // The sheet counter is NOT part of the body flow: it lives in the
  // reserved page footer (see the page setup above).
  #if page.is-first {
    title_unit(true, config)
  } else {
    title_unit(false, config)
  }
  #table_unit(
    all_rows.slice(page.start, page.end),
    config,
    all_sizes.slice(page.start, page.end),
    page.targets,
  )
  #if page.is-last {
    sig_unit(config, blocks)
  }
]

// ---------------------------------------------------------------------------
// Document flow: normalize -> measure -> paginate -> stretch -> render
// (everything inside ONE context; measure() needs it).
// ---------------------------------------------------------------------------

#set document(title: title)

#context {
  let config = layout-config

  // Physical sheet invariant (TZ §4.1): the geometry table must match
  // the page margins.
  if config.page-geometry.content-height != config.page-geometry.paper-height - config.page.margin.top - config.page.margin.bottom {
    panic("page-geometry is inconsistent with page margins")
  }
  if config.page-geometry.content-width != config.page-geometry.paper-width - config.page.margin.left - config.page.margin.right {
    panic("page-geometry is inconsistent with page margins")
  }

  let W = config.page-geometry.content-width
  let raw_lines = inner.at("lines", default: ())
  let rows = normalize_lines(raw_lines)
  let op_type = to_upper(as_text(inner.at("operation_type", default: "RECEIVE")))
  let signature_blocks = config.operation-signature-sets.at(
    op_type,
    default: (),
  )

  // --- Measured page chrome -------------------------------------------------
  let hf = measure(title_unit(true, config), width: W).height
  let hm = measure(title_unit(false, config), width: W).height
  let ht = measure(header_row_unit(config), width: W).height
  let hs = measure(sig_unit(config, signature_blocks), width: W).height

  // Available data-row areas per role (TZ §4.2).
  let a_first = config.page-geometry.content-height - hf - ht
  let a_middle = config.page-geometry.content-height - hm - ht
  let a_last = config.page-geometry.content-height - hm - ht - hs
  let a_single = config.page-geometry.content-height - hf - ht - hs

  // H1 — normal one-line row height (reference for font fallback).
  // table_unit always renders the header row, so the measured raw
  // height includes HT — subtract it (exact length arithmetic).
  let h1 = measure(table_unit((
      (line-number: "1", item-name: "А", unit: "шт", quantity: "1"),
    ), config, (none,), none), width: W).height - ht

  // --- Row heights with font fallback (TZ §4.3), cached by content ---
  let threshold = config.font-fallback.max-lines * h1
  let cache = (:)
  let heights = ()
  let sizes = ()
  for row in rows {
    let key = row.item-name + "|" + row.unit + "|" + row.quantity
    let entry = cache.at(key, default: none)
    if entry == none {
      entry = (
        base: measure(table_unit((row,), config, (none,), none), width: W).height - ht,
        s1: none,
        s2: none,
      )
      cache.insert(key, entry)
    }
    let h = entry.base
    let chosen = none
    if h > threshold {
      for (idx, size) in config.font-fallback.sizes.enumerate() {
        let field = if idx == 0 { "s1" } else { "s2" }
        let hk = entry.at(field, default: none)
        if hk == none {
          hk = measure(table_unit((row,), config, (size,), none), width: W).height - ht
          entry.insert(field, hk)
        }
        if hk <= threshold {
          chosen = size
          h = hk
          break
        }
      }
    }
    heights.push(h)
    sizes.push(chosen)
  }

  // --- Pagination (measurable balanced engine, TZ §4.4) ---
  let areas = (first: a_first, middle: a_middle, last: a_last, single: a_single)
  let pages = paginate(heights, areas)

  // --- Row stretch (TZ §4.5): only up, never compress ---
  let stretch = config.row-stretch
  let rendered = pages.map(p => {
    let hsum = 0pt
    for i in range(p.start, p.end) {
      hsum += heights.at(i)
    }
    let arole = if p.is-first and p.is-last {
      a_single
    } else if p.layout == "first" {
      a_first
    } else if p.layout == "middle" {
      a_middle
    } else {
      a_last
    }
    let s = if hsum > 0pt {
      calc.min((arole - stretch.safety-gap) / hsum, stretch.max)
    } else {
      1.0
    }
    let targets = if s > 1.0 {
      heights.slice(p.start, p.end).map(h => h * s)
    } else {
      none
    }
    (..p, targets: targets)
  })

  // --- Emit pages (Typst never decides page breaks) ---
  for (idx, page) in rendered.enumerate() {
    render_page(page, config, signature_blocks, rows, sizes)
    if idx < rendered.len() - 1 {
      pagebreak()
    }
  }
}
