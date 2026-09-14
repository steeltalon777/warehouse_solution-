// warehouse-waybill-ru@2.2.2 — globally balanced pagination engine.
//
// 2.2.2 replaces the 2.2.0/2.2.1 pagination strategy. 2.2.1 is an
// immutable null-safety patch over 2.2.0 (ADR-0034) and its algorithm is
// kept for audit only. The 2.2.2 change is scoped to pagination: main.typ,
// layout-config.typ and signatures.typ are byte-identical to 2.2.1.
//
// Defect fixed (QDE pagination root cause analysis, 2026-09-14):
// the 2.2.0/2.2.1 engine first committed the MAXIMAL suffix that fits the
// last page (TZ §4.4 step 5a) and then balanced only the remaining prefix
// on first+middle pages (step 5b). The last page was therefore excluded
// from balancing and received a disproportionate share of rows whenever
// the document had few (or few tall) rows; a floating-point knife edge
// (`used + h > target` at an exact mathematical tie) could even promote a
// feasible 2-page layout to 3 pages.
//
// New algorithm — exact, deterministic, no RNG:
//  1. minimal page count P*: smallest P >= 2 such that the ordered row
//     list fits the role capacities (A_first, A_middle x (P-2), A_last);
//     checked by earliest-fit greedy, which is exact for contiguous
//     in-order partitions. P == 1 uses A_single, exactly as before.
//  2. global balance at P*: exact Pareto DP over (page, end row) states;
//     each state keeps the non-dominated (max_fill, min_fill) pairs where
//     fill = used_height / A_role of that page. Row order is preserved,
//     hard capacities are never exceeded, and the objective is
//     lexicographic:
//       primary   spread = max(fill) - min(fill)
//       secondary max(fill)
//       tertiary  lexicographically smallest boundary tuple
//     The last page is balanced like every other page relative to its own
//     A_last (the signature section is already subtracted from A_last, so
//     no layout/signature change is required).
//
// Floating-point correctness:
//  * every capacity comparison goes through one centralised tolerance,
//    ``capacity-epsilon`` = 0.01pt ~= 3.5um. It is far below any visually
//    or physically relevant overflow (the authoritative hard-overflow
//    tests tolerate >= 1pt) and many orders of magnitude above the
//    ~1e-13pt ULP noise of A4-scale length arithmetic.
//  * the 32-row anchor regression (2-page partition lost to a 1-ULP
//    rounding at target == sum(prefix)) is covered by an integration test.
//
// Pure functions only: no measure(), no json(), no file access. Row
// heights arrive as Typst lengths from main.typ.
//
// API:
//   paginate(heights, areas) -> pages
//     page descriptors (page-number, start, end, is-first, is-last,
//     total-pages, layout) — unchanged from 2.2.1.
//   paginate-profiled(heights, areas) -> (pages, stats)
//     same plus deterministic counters (p-pages, dp-states,
//     dp-transitions, max-frontier) used by the performance checkpoint
//     and tests. No timing, no randomness.
//   char_len(s) — codepoint counter used by main.typ helpers.

// ---------------------------------------------------------------------------
// Char-aware length (used by main.typ helpers: wrap_name,
// format_quantity). Counts codepoints, not UTF-8 bytes.
// ---------------------------------------------------------------------------

#let char_len(s) = {
  let n = 0
  for c in s {
    n += 1
  }
  n
}

// ---------------------------------------------------------------------------
// Centralised capacity tolerance (single source of truth).
// ---------------------------------------------------------------------------

#let capacity-epsilon = 0.01pt

#let _fits(value, cap) = value <= cap + capacity-epsilon

// ---------------------------------------------------------------------------
// Feasibility (earliest-fit greedy, exact for contiguous in-order rows)
// ---------------------------------------------------------------------------

#let _prefix_sums(heights) = {
  let pre = (0pt,)
  let acc = 0pt
  for h in heights {
    acc += h
    pre.push(acc)
  }
  pre
}

#let _caps_for(p, a_first, a_middle, a_last) = {
  let caps = (a_first,)
  for _ in range(p - 2) {
    caps.push(a_middle)
  }
  caps.push(a_last)
  caps
}

// Earliest-fit: page closes only when the next row no longer fits the
// role capacity (with the centralised tolerance). Returns true when all
// rows are placed inside the given page capacities.
#let _feasible(heights, caps) = {
  let n = heights.len()
  let i = 0
  for cap in caps {
    let used = 0pt
    while i < n and _fits(used + heights.at(i), cap) {
      used += heights.at(i)
      i += 1
    }
  }
  i == n
}

#let _min_pages(heights, a_first, a_middle, a_last) = {
  let n = heights.len()
  for p in range(2, n + 1) {
    if _feasible(heights, _caps_for(p, a_first, a_middle, a_last)) {
      return p
    }
  }
  n
}

// ---------------------------------------------------------------------------
// Exact Pareto DP
// ---------------------------------------------------------------------------

#let _fill_ratio(seg, cap) = (seg / 1pt) / (cap / 1pt)

#let _reverse(arr) = {
  let out = ()
  for i in range(arr.len()) {
    out.push(arr.at(arr.len() - 1 - i))
  }
  out
}

// Compare two candidate keys (spread, mx, ends); true when ``a`` is
// strictly better. Deterministic lexicographic tie-break on boundaries.
#let _better(a, b) = {
  if a.spread < b.spread - 1e-12 {
    return true
  }
  if a.spread > b.spread + 1e-12 {
    return false
  }
  if a.mx < b.mx - 1e-12 {
    return true
  }
  if a.mx > b.mx + 1e-12 {
    return false
  }
  let n = calc.min(a.ends.len(), b.ends.len())
  for i in range(n) {
    if a.ends.at(i) < b.ends.at(i) {
      return true
    }
    if a.ends.at(i) > b.ends.at(i) {
      return false
    }
  }
  a.ends.len() < b.ends.len()
}

#let _paginate_core(heights, areas) = {
  let n = heights.len()
  let a_first = areas.first
  let a_middle = areas.middle
  let a_last = areas.last
  let a_single = areas.single

  // 1. Empty document -> one stub "first" page (stretch not applied).
  if n == 0 {
    return (
      pages: ((
        page-number: 1,
        start: 0,
        end: 0,
        is-first: true,
        is-last: true,
        total-pages: 1,
        layout: "first",
      ),),
      stats: (p-pages: 1, dp-states: 0, dp-transitions: 0, max-frontier: 0),
    )
  }

  // 2. Every row must fit the largest role area (hard physical limit).
  let max_area = calc.max(calc.max(a_first, a_middle), a_last)
  for h in heights {
    if h > max_area + capacity-epsilon {
      panic("Waybill line is too tall to fit on one page.")
    }
  }

  // 3. The first row must fit the first-page layout: row 0 always lands
  //    on the first page.
  if heights.at(0) > a_first + capacity-epsilon {
    panic("Waybill line is too tall for the first-page layout.")
  }

  // 4. A single line must fit the single-page layout.
  if n == 1 and heights.at(0) > a_single + capacity-epsilon {
    panic("Waybill line is too tall for the single-page layout.")
  }

  let pre = _prefix_sums(heights)
  let total = pre.at(n)

  // 5. Single-page document: full header AND signature form on one page.
  if _fits(total, a_single) {
    return (
      pages: ((
        page-number: 1,
        start: 0,
        end: n,
        is-first: true,
        is-last: true,
        total-pages: 1,
        layout: "first",
      ),),
      stats: (p-pages: 1, dp-states: 0, dp-transitions: 0, max-frontier: 0),
    )
  }

  // 6. Minimal page count over the ordered role sequence.
  let p_pages = _min_pages(heights, a_first, a_middle, a_last)
  let caps = _caps_for(p_pages, a_first, a_middle, a_last)

  // 7. Exact Pareto DP: states[j][i] = non-dominated
  //    (mx, mn, k, pi) entries for j pages ending at row i, where k is
  //    the previous boundary and pi the parent entry index.
  let levels = ()
  let level0 = ()
  for i in range(0, n + 1) {
    level0.push(if i == 0 { ((mx: 0.0, mn: 2.0, k: 0, pi: 0),) } else { () })
  }
  levels.push(level0)

  let dp_states = 0
  let dp_transitions = 0
  let max_frontier = 0

  for j in range(1, p_pages + 1) {
    let cap = caps.at(j - 1)
    let prev = levels.at(j - 1)
    let level = ()
    for _ in range(0, j) {
      level.push(())
    }
    let kmin = j - 1
    for i in range(j, n + 1) {
      while kmin < i and not _fits(pre.at(i) - pre.at(kmin), cap) {
        kmin += 1
      }
      let cand = ()
      for k in range(kmin, i) {
        let seg = pre.at(i) - pre.at(k)
        if not _fits(seg, cap) {
          continue
        }
        let parents = prev.at(k)
        if parents.len() == 0 {
          continue
        }
        dp_transitions += parents.len()
        let f = _fill_ratio(seg, cap)
        for (pi, pe) in parents.enumerate() {
          cand.push((
            mx: calc.max(pe.mx, f),
            mn: calc.min(pe.mn, f),
            k: k,
            pi: pi,
          ))
        }
      }
      let pruned = ()
      for c in cand {
        let dominated = false
        for e in pruned {
          if e.mx <= c.mx + 1e-12 and e.mn >= c.mn - 1e-12 {
            dominated = true
            break
          }
        }
        if dominated {
          continue
        }
        let kept = ()
        for e in pruned {
          if not (c.mx <= e.mx + 1e-12 and c.mn >= e.mn - 1e-12) {
            kept.push(e)
          }
        }
        kept.push(c)
        pruned = kept
      }
      if pruned.len() > 0 {
        dp_states += 1
        max_frontier = calc.max(max_frontier, pruned.len())
      }
      level.push(pruned)
    }
    levels.push(level)
  }

  let finals = levels.at(p_pages).at(n)
  if finals.len() == 0 {
    panic("Waybill pagination failed.")
  }

  // 8. Deterministic selection: (spread, max, lexicographic boundaries).
  let best = none
  for entry in finals {
    let ends_rev = (n,)
    let e = entry
    let jj = p_pages
    while jj > 1 {
      let pk = e.k
      e = levels.at(jj - 1).at(pk).at(e.pi)
      ends_rev.push(pk)
      jj -= 1
    }
    let ends = _reverse(ends_rev)
    let mx = 0.0
    let mn = 2.0
    let start = 0
    for j in range(p_pages) {
      let end = ends.at(j)
      let f = _fill_ratio(pre.at(end) - pre.at(start), caps.at(j))
      mx = calc.max(mx, f)
      mn = calc.min(mn, f)
      start = end
    }
    let key = (spread: mx - mn, mx: mx, ends: ends)
    if best == none or _better(key, best) {
      best = key
    }
  }

  // 9. Assemble page descriptors (unchanged shape).
  let bounds = best.ends
  let total_pages = p_pages
  let pages = ()
  let start = 0
  for j in range(p_pages) {
    let is_first = j == 0
    let is_last = j == p_pages - 1
    pages.push((
      page-number: j + 1,
      start: start,
      end: bounds.at(j),
      is-first: is_first,
      is-last: is_last,
      total-pages: total_pages,
      layout: if is_first { "first" } else if is_last { "last" } else { "middle" },
    ))
    start = bounds.at(j)
  }

  (
    pages: pages,
    stats: (
      p-pages: p_pages,
      dp-states: dp_states,
      dp-transitions: dp_transitions,
      max-frontier: max_frontier,
    ),
  )
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

#let paginate(heights, areas) = _paginate_core(heights, areas).pages

#let paginate-profiled(heights, areas) = _paginate_core(heights, areas)
