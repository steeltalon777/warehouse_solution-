// warehouse-waybill-ru@2.0.0 — deterministic pagination engine.
//
// Replicates the frozen legacy pagination algorithm
// (Warehouse_web@133e2fa apps/documents/services.py
// paginate_waybill_lines + _estimated_line_units) for the canonical
// waybill form.
//
// IMPORTANT design rules:
// * Page capacities are NEVER hardcoded here. They come from
//   layout-config.typ (passed in as the ``caps`` argument).
// * The engine knows nothing about signatures, operation types or
//   customer content — it only distributes row indices into page
//   roles using the unit model.
// * A "row unit" is one visual line of the item name estimated with
//   the same greedy word-wrap model as the legacy renderer.
//
// Note on string lengths: Typst's ``str.len()`` counts UTF-8 bytes,
// while the legacy estimator counts characters. All length
// computations here use char_len() (codepoint count) so Cyrillic
// names are estimated exactly like the legacy renderer.

// ---------------------------------------------------------------------------
// Char-aware string helpers
// ---------------------------------------------------------------------------

#let char_len(s) = {
  let n = 0
  for c in s {
    n += 1
  }
  n
}

// ---------------------------------------------------------------------------
// Unit estimation (legacy _estimated_line_units)
// ---------------------------------------------------------------------------

// Estimate how many visual lines an item name will occupy under the
// legacy greedy word-wrap model. Words are chunked at
// ``chars_per_line`` characters; a line fills up to
// ``chars_per_line`` characters including single separators.
#let visual_lines(name, chars_per_line) = {
  let words = name.split(regex("\s+"))
  if words.len() == 0 {
    return 1
  }
  if words.len() == 1 and char_len(words.at(0)) == 0 {
    return 1
  }
  let lines = 1
  let current_length = 0
  for w in words {
    let word_len = char_len(w)
    let pos = 0
    while pos < word_len {
      let chunk_len = calc.min(chars_per_line, word_len - pos)
      let separator = if current_length > 0 { 1 } else { 0 }
      if current_length + separator + chunk_len <= chars_per_line {
        current_length += separator + chunk_len
      } else {
        lines += 1
        current_length = chunk_len
      }
      pos += chunk_len
    }
  }
  lines
}

// ---------------------------------------------------------------------------
// Prefix/suffix fillers (legacy take_prefix / last-page reservation)
// ---------------------------------------------------------------------------

// How many leading items fit within ``limit`` units (greedy).
#let take_prefix(units, limit) = {
  let used = 0
  let n = 0
  while n < units.len() {
    let u = units.at(n)
    if used + u > limit {
      break
    }
    used += u
    n += 1
  }
  n
}

// Reserve the last page: starting from the end of the array, pop
// items while they fit within ``limit`` units; stop at ``min_start``
// (inclusive lower bound). Returns the start index of the tail.
#let take_suffix(units, limit, min_start) = {
  let used = 0
  let start = units.len()
  while start > min_start {
    let u = units.at(start - 1)
    if used + u > limit {
      break
    }
    used += u
    start -= 1
  }
  start
}

// ---------------------------------------------------------------------------
// Pagination entry point
// ---------------------------------------------------------------------------

// Distribute ``lines`` into page descriptors using the unit model.
//
// ``caps`` is a dictionary: (first, middle, last,
// single: int) resolved by the caller from layout-config.typ.
//
// Returns an array of page descriptors:
// (page-number, lines, is-first, is-last, total-pages, layout)
// where layout is "first" | "middle" | "last".
//
// Behaviour (mirrors the legacy algorithm exactly):
// * empty lines      -> one "first" page with no lines;
// * sum <= single    -> one page (full first header + full form);
// * otherwise        -> first page prefix (>= 1 line reserved for the
//   last page), a greedy middle sequence, and a tail last page.
// * a line that cannot fit a role aborts with the same error
//   messages the legacy renderer raised as
//   DocumentPdfRenderError.
#let paginate(lines, units, caps) = {
  let n = lines.len()
  let total_units = units.fold(0, (acc, u) => acc + u)

  if n == 0 {
    return (
      (
        page-number: 1,
        lines: (),
        is-first: true,
        is-last: true,
        total-pages: 1,
        layout: "first",
      ),
    )
  }

  let cap_values = (caps.first, caps.middle, caps.last, caps.single)
  let max_cap = cap_values.fold(0, (acc, u) => calc.max(acc, u))
  for u in units {
    if u > max_cap {
      panic("Waybill line is too tall to fit on one page.")
    }
  }
  if n == 1 and units.at(0) > caps.single {
    panic("Waybill line is too tall for the single-page layout.")
  }
  if total_units <= caps.single {
    return (
      (
        page-number: 1,
        lines: lines,
        is-first: true,
        is-last: true,
        total-pages: 1,
        layout: "first",
      ),
    )
  }

  // First page: greedy prefix, but always reserve at least one line
  // for the last page (legacy take_prefix(end=len-1)).
  let first_end = calc.min(take_prefix(units, caps.first), n - 1)
  if first_end == 0 {
    panic("Waybill line is too tall for the first-page layout.")
  }

  // Last page: tail reserved from the end.
  let last_start = take_suffix(units, caps.last, first_end)
  let last_units = units.slice(last_start).fold(0, (acc, u) => acc + u)
  if last_units == 0 {
    panic("Waybill line is too tall for the last-page layout.")
  }

  // Middle pages: greedy middle-capacity chunks between first and last.
  let middle_starts = ()
  let cur = first_end
  while cur < last_start {
    let m = take_prefix(units.slice(cur, last_start), caps.middle)
    if m == 0 {
      panic("Waybill line is too tall for the middle-page layout.")
    }
    middle_starts.push(cur)
    cur += m
  }

  // Assemble page descriptors.
  let ranges = ((0, first_end, "first"),)
  for ms in middle_starts {
    let end = calc.min(
      ms + take_prefix(units.slice(ms, last_start), caps.middle),
      last_start,
    )
    ranges.push((ms, end, "middle"))
  }
  ranges.push((last_start, n, "last"))

  let pages = ()
  let total_pages = ranges.len()
  for r in ranges.enumerate() {
    let idx = r.at(0)
    let start = r.at(1).at(0)
    let end = r.at(1).at(1)
    let role = r.at(1).at(2)
    pages.push(
      (
        page-number: idx + 1,
        lines: lines.slice(start, end),
        is-first: role == "first",
        is-last: role == "last",
        total-pages: total_pages,
        layout: role,
      ),
    )
  }
  pages
}
