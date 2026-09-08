// warehouse-waybill-ru@2.2.0 — measurable pagination engine.
//
// ИЗМЕРИМАЯ МОДЕЛЬ — НЕ ПОРТ LEGACY. В отличие от 2.0.0/2.1.0 (точный
// порт символьной эвристики legacy-рендера Warehouse_web
// paginate_waybill_lines), этот движок получает ГОТОВЫЕ измеренные
// высоты строк (Typst measure(), см. main.typ) и измеренные площади
// ролей (content-height минус хром страницы) и распределяет строки по
// страницам с балансировкой заполнения
// (TZ-QDE_WAYBILL_PAGINATION_REBALANCE_v1.0 §4.4).
//
// ОТКЛОНЕНИЕ ОТ ФОРМУЛЫ МЯГКОГО БЮДЖЕТА §4.4 (намеренное, подтверждено
// заказчиком 05.09.2026): буквальные фиксированные бюджеты
// T = F * A_role с F = sum_prefix / (A_first + P * A_middle) суммируются
// ровно в sum_prefix, поэтому успех требует бездефектной укладки строк
// по бюджетам — на реальных смешанных входах проход систематически
// проваливается и уходит в hard-fallback с «огрызками», что нарушает
// критерий равномерности §6.3. Реализована АДАПТАЦИЯ того же алгоритма:
// водозаполнение — уровень заполнения F' = remaining / remaining_capacity
// пересчитывается на старте каждой страницы (первая цель совпадает с
// закрытой формой F ТЗ; хвостовая страница префикса поглощает остаток).
//
// Сохранённые инварианты §4.4:
// * порядок строк никогда не меняется;
// * полный детерминизм (без случайности/времени);
// * максимальный суффикс-резерв последней страницы (>= 1 и <= n-1
//   строк, жёсткий предел A_last);
// * hard fallback по жёстким пределам при отказе балансировки;
// * существующие panic-сообщения дословно.
//
// Design rules:
// * Чистые функции: ни measure(), ни json(), ни доступа к файлам.
//   Высоты и площади приходят аргументами (длины Typst).
// * Ёмкостей в «row units» не существует — только физические высоты.
//
// API:
//   paginate(heights, areas) -> pages
//     heights: массив высот строк (length);
//     areas: (first, middle, last, single: length) — доступные площади
//     строк данных по ролям страницы (content-height минус хром роли).
//     Возвращает дескрипторы страниц:
//     (page-number, start, end, is-first, is-last, total-pages,
//     layout), где [start, end) — диапазон ИНДЕКСОВ строк, layout:
//     "first" | "middle" | "last".
//   char_len(s) — счёт кодпоинтов (используется хелперами main.typ).

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
// Greedy in-order packing (one pass with fixed budgets)
// ---------------------------------------------------------------------------

// Sum of heights in the index range [from, to).
#let _sum_range(heights, from, to) = {
  let acc = 0pt
  for i in range(from, to) {
    acc += heights.at(i)
  }
  acc
}

// Greedy in-order packing of rows [from, to) into a first page with
// budget ``b_first`` plus at most ``max_mid`` middle pages with budget
// ``b_mid``.
//
// A page is closed only when it is non-empty; an empty page takes the
// next row unconditionally (guarded: the row must fit the role's hard
// area, otherwise this P fails).
//
// Returns ``none`` when the rows do not fit ``max_mid`` middle pages,
// otherwise the array of (start, end) index ranges: the first page
// followed by the used middle pages.
#let _pack(heights, from, to, b_first, b_mid, max_mid) = {
  let ranges = ()
  let i = from
  let used = 0pt
  let page_start = from
  let mid_count = 0
  let budget = b_first
  while i < to {
    let h = heights.at(i)
    if used > 0pt and used + h > budget {
      ranges.push((page_start, i))
      mid_count += 1
      if mid_count > max_mid {
        return none
      }
      page_start = i
      used = 0pt
      budget = b_mid
    }
    used += h
    i += 1
  }
  ranges.push((page_start, to))
  ranges
}

// Water-filling pass for a fixed ``max_mid``: every page fills to the
// CURRENT remaining fill level, recomputed at each page start as
// F' = remaining_sum / remaining_total_capacity, target = F' * role
// area. Targets are NOT zero-sum: the final prefix page absorbs the
// remainder (its target is exactly what is left), so the pass succeeds
// for ordinary mixed inputs where a fixed-budget pass would require a
// perfect tiling. Pages close when the next row would exceed the
// target (or the hard role area, whichever is smaller); an empty page
// takes a row unconditionally only if it fits the hard role area.
//
// This implements the TZ §4.4 intent ("равномерный уровень заполнения")
// — the first page's F' equals the closed-form F of the literal pass;
// later F' values adapt to greedy waste instead of demanding a perfect
// partition.
#let _pack_water(heights, from, to, a_first, a_mid, max_mid) = {
  let ranges = ()
  let i = from
  let remaining = _sum_range(heights, from, to)
  while i < to {
    let is_first = ranges.len() == 0
    // Opening a middle page: it is page number ranges.len() (1-based
    // among middles), so it must not exceed max_mid.
    if not is_first and ranges.len() > max_mid {
      return none
    }
    let cap = if is_first { a_first } else { a_mid }
    let left_mids = if is_first { max_mid } else { max_mid - ranges.len() }
    let cap_total = cap + left_mids * a_mid
    let f = remaining / cap_total
    let target = if f > 1 { cap } else { f * cap }
    let page_start = i
    let used = 0pt
    while i < to {
      let h = heights.at(i)
      if used > 0pt and used + h > target {
        break
      }
      if used == 0pt and h > cap {
        return none
      }
      used += h
      i += 1
    }
    if used == 0pt {
      return none
    }
    ranges.push((page_start, i))
    remaining -= used
  }
  ranges
}

// ---------------------------------------------------------------------------
// Pagination entry point (TZ §4.4)
// ---------------------------------------------------------------------------

#let paginate(heights, areas) = {
  let n = heights.len()
  let a_first = areas.first
  let a_middle = areas.middle
  let a_last = areas.last
  let a_single = areas.single

  // 1. Empty document -> one stub "first" page (stretch not applied).
  if n == 0 {
    return ((
      page-number: 1,
      start: 0,
      end: 0,
      is-first: true,
      is-last: true,
      total-pages: 1,
      layout: "first",
    ),)
  }

  // 2. Every row must fit the largest role area.
  let max_area = calc.max(calc.max(a_first, a_middle), a_last)
  for h in heights {
    if h > max_area {
      panic("Waybill line is too tall to fit on one page.")
    }
  }

  // 3. The first row must fit the first-page layout: the first page
  //    (full header and requisites) must exist and row 0 always lands
  //    on it (see 5b: the prefix starts at index 0).
  if heights.at(0) > a_first {
    panic("Waybill line is too tall for the first-page layout.")
  }

  // 4. A single line must fit the single-page layout.
  if n == 1 and heights.at(0) > a_single {
    panic("Waybill line is too tall for the single-page layout.")
  }

  let total = _sum_range(heights, 0, n)

  // Single-page document: everything (full header AND signature form)
  // fits one page (minimal page count).
  if total <= a_single {
    return ((
      page-number: 1,
      start: 0,
      end: n,
      is-first: true,
      is-last: true,
      total-pages: 1,
      layout: "first",
    ),)
  }

  // 5a. Last-page reserve: MAXIMAL suffix within the hard A_last.
  //     The suffix keeps >= 1 row and leaves >= 1 row to the prefix
  //     (the first page must exist).
  let suffix_start = n
  let suffix_used = 0pt
  while suffix_start > 1 {
    let h = heights.at(suffix_start - 1)
    if suffix_used + h > a_last {
      break
    }
    suffix_used += h
    suffix_start -= 1
  }
  if suffix_used == 0pt {
    panic("Waybill line is too tall for the last-page layout.")
  }

  // 5b. Prefix (rows [0, suffix_start)) packed onto the first + middle
  //     pages with fill-level balancing.
  let sum_prefix = _sum_range(heights, 0, suffix_start)
  let p_min = 0
  let cap_acc = a_first
  while cap_acc < sum_prefix {
    cap_acc += a_middle
    p_min += 1
  }

  let ranges = none
  // Pass 1 (balanced, water-filling): every page fills to the CURRENT
  // remaining fill level F' = remaining / remaining_total_capacity.
  // The first page's F' equals the closed-form F of TZ §4.4
  // (sum_prefix / (A_first + P * A_middle)); later F' values adapt to
  // greedy waste instead of demanding a perfect tiling (the literal
  // fixed-F budgets sum exactly to sum_prefix, so they succeed only
  // for perfectly tiling inputs — water-filling reproduces exactly
  // that allocation in those cases and stays balanced otherwise).
  for p in range(p_min, p_min + 5) {
    let res = _pack_water(heights, 0, suffix_start, a_first, a_middle, p)
    if res != none {
      ranges = res
      break
    }
  }
  // Pass 2: hard-limit greedy fallback (balancing disabled for this
  // input).
  if ranges == none {
    for p in range(p_min, p_min + 5) {
      let res = _pack(heights, 0, suffix_start, a_first, a_middle, p)
      if res != none {
        ranges = res
        break
      }
    }
  }
  if ranges == none {
    panic("Waybill pagination failed.")
  }

  // Assemble page descriptors: first + used middles + last.
  let mid_ranges = ranges.slice(1)
  let total_pages = 1 + mid_ranges.len() + 1
  let pages = ((
    page-number: 1,
    start: 0,
    end: ranges.at(0).at(1),
    is-first: true,
    is-last: false,
    total-pages: total_pages,
    layout: "first",
  ),)
  for (idx, r) in mid_ranges.enumerate() {
    pages.push((
      page-number: idx + 2,
      start: r.at(0),
      end: r.at(1),
      is-first: false,
      is-last: false,
      total-pages: total_pages,
      layout: "middle",
    ))
  }
  pages.push((
    page-number: total_pages,
    start: suffix_start,
    end: n,
    is-first: false,
    is-last: true,
    total-pages: total_pages,
    layout: "last",
  ))
  pages
}
