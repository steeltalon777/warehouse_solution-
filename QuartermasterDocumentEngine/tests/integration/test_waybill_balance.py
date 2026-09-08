"""2.2.0 waybill integration tests (TZ-QDE_WAYBILL_PAGINATION_REBALANCE §6.3).

These tests exercise the measurable-pagination template
``warehouse-waybill-ru@2.2.0`` end-to-end: canonical envelope (fixtures
``waybill-qde22-*``, document bodies identical to ``waybill-qde-*``)
-> QDE engine -> real Typst 0.15.1 -> PDF:

* row integrity (every line number exactly once, original order);
* frame limits (text inside the sheet frame; stretched tables respect
  the ``row-stretch.safety-gap``);
* page counts pinned in ``EXPECTED_PAGES_22`` — values intentionally
  differ from the frozen legacy renderer (LAYOUT.md §10); every value
  must stay <= the legacy count for the same fixture;
* uniform fill of first+middle pages measured PHYSICALLY from the PDF
  table borders (row counts vary legitimately with name heights and
  are informational only);
* signatures on the last page only; footer counter rules;
* font fallback (long wordy name -> reduced size; unbroken 200-char
  token -> no panic, natural height kept);
* deterministic repeated renders (byte-identical).

The frozen 2.0.0 suite (``test_canonical_waybill.py``) and all unit
tests are intentionally untouched — this file only ADDS 2.2.0 coverage.

The tests skip cleanly when the pinned Typst binary is unavailable.
"""

from __future__ import annotations

import hashlib
import json
import re
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfReader
from qm_engine.envelope import parse_envelope
from qm_engine.render import render_envelope

REPO = Path(__file__).resolve().parents[2]
TEMPLATES = REPO / "templates"
FIXTURES = REPO / "tests" / "fixtures" / "waybill-qde22"
TEMPLATE_ID = "warehouse-waybill-ru"
TEMPLATE_VERSION = "2.2.0"

# Deterministic 2.2.0 page counts (fixed from the 05.09.2026 renders of
# the committed fixtures; re-measure and re-pin ONLY via a reviewed
# change). The legacy renderer (2.0.0) produced 1/4/10/27/66 — the
# 2.2.0 counts intentionally differ (measured balancing, LAYOUT.md
# §10); the acceptance bound is: never MORE pages than legacy.
EXPECTED_PAGES_22: dict[int, int] = {1: 1, 20: 2, 75: 5, 200: 12, 500: 30}
EXPECTED_PAGES_LEGACY: dict[int, int] = {1: 1, 20: 4, 75: 10, 200: 27, 500: 66}

# A4 content frame: 297mm - 14mm bottom margin, in points, + 2pt
# tolerance (same convention as test_canonical_waybill.py).
BOTTOM_LIMIT_PT = 841.89 - 14 * 72 / 25.4 + 2
FRAME_BOTTOM_PT = 841.89 - 14 * 72 / 25.4

# row-stretch.safety-gap = 0.5mm (layout-config.typ): a stretched table
# must end at least this far above the frame bottom (+1pt render
# tolerance for stroke rounding).
SAFETY_GAP_PT = 0.5 * 72 / 25.4
TABLE_BOTTOM_LIMIT_PT = FRAME_BOTTOM_PT - SAFETY_GAP_PT + 1.0

# Measured table header row height (CP1 ground truth, 2.2.0 chrome).
HEADER_ROW_PT = 8.52 * 72 / 25.4

# Uniformity thresholds (TZ §6.3 п.4).
FILL_SPREAD_MAX = 0.30
FILL_MIN_SHARE = 0.60


def _typst_available() -> bool:
    from qm_backends.typst_backend import TypstBackend

    try:
        return TypstBackend().available()
    except Exception:  # noqa: BLE001 - availability probe
        return False


pytestmark = [
    pytest.mark.skipif(
        not _typst_available(),
        reason="real typst binary not present; run scripts/fetch_typst.py",
    )
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fixture(n: int) -> dict:
    raw = (FIXTURES / f"waybill-qde22-{n}.typst.json").read_text(encoding="utf-8")
    return parse_envelope(raw).data


def _render(envelope: dict, templates_root: Path = TEMPLATES) -> bytes:
    parsed = parse_envelope(json.dumps(envelope, ensure_ascii=False))
    result = render_envelope(parsed, templates_root, output_format="pdf")
    assert result.format == "pdf"
    assert not result.warnings, f"typst emitted warnings: {result.warnings}"
    return result.data


def _page_count(pdf_bytes: bytes) -> int:
    return len(PdfReader(BytesIO(pdf_bytes)).pages)


def _pages_info(pdf_bytes: bytes, total: int) -> dict:
    """Extract per-page texts, row numbers, table border spans, limits."""
    import pymupdf

    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        texts = [doc[i].get_text() for i in range(len(doc))]
        rows_per_page = []
        table_spans = []
        text_bottom = 0.0
        footer_bottom = 0.0
        for page in doc:
            nums = set()
            for word in page.get_text("words"):
                x0, y0, text = word[0], word[1], word[4]
                if x0 < 75 and y0 > 60 and re.fullmatch(r"\d{1,4}", text):
                    v = int(text)
                    if 1 <= v <= total:
                        nums.add(v)
            rows_per_page.append(nums)
            hl = []
            for d in page.get_drawings():
                for item in d["items"]:
                    if item[0] == "l":
                        p1, p2 = item[1], item[2]
                        if abs(p1.y - p2.y) < 0.1:
                            hl.append(p1.y)
                    elif item[0] == "re":
                        r = item[1]
                        hl.append(r.y0)
                        hl.append(r.y1)
            hl = [y for y in hl if y > 60]
            table_spans.append((min(hl), max(hl)) if hl else (0.0, 0.0))
            for word in page.get_text("words"):
                if word[4].startswith("Лист"):
                    footer_bottom = max(footer_bottom, word[3])
                    continue
                if word[1] > BOTTOM_LIMIT_PT - 2:
                    continue
                text_bottom = max(text_bottom, word[3])
    finally:
        doc.close()
    return {
        "texts": texts,
        "rows_per_page": rows_per_page,
        "table_spans": table_spans,
        "text_bottom": text_bottom,
        "footer_bottom": footer_bottom,
    }


def _ordered_rows(rows_per_page: list[set[int]]) -> list[int]:
    ordered: list[int] = []
    for nums in rows_per_page:
        ordered.extend(sorted(nums))
    return ordered


def _assert_common(pdf_bytes: bytes, n: int, info: dict, expect_move_labels: bool = True) -> None:
    """Shared invariants: integrity, order, frame, footer, signatures."""
    pages = _page_count(pdf_bytes)
    texts = info["texts"]

    # 1. Row integrity + original order (all rows, in page order).
    ordered = _ordered_rows(info["rows_per_page"])
    if n > 0:
        missing = sorted(set(range(1, n + 1)) - set(ordered))
        dupes = sorted(v for v in set(ordered) if ordered.count(v) > 1)
        assert ordered == list(range(1, n + 1)), (
            f"row integrity/order violated: missing={missing[:10]} dupes={dupes[:10]}"
        )
    else:
        assert not ordered

    # 2. Frame limits: text inside the sheet; stretched table bottom
    #    respects the safety gap.
    assert info["text_bottom"] <= BOTTOM_LIMIT_PT, (
        f"content overflows the bottom frame: {info['text_bottom']:.1f} > {BOTTOM_LIMIT_PT:.1f}"
    )
    for _top, bot in info["table_spans"]:
        assert bot <= TABLE_BOTTOM_LIMIT_PT, (
            f"table bottom {bot:.1f} exceeds frame - safety-gap limit {TABLE_BOTTOM_LIMIT_PT:.1f}"
        )

    # 5. Footer counter rules.
    if pages > 1:
        assert all(f"Лист {i + 1} из {pages}" in texts[i] for i in range(pages)), (
            "sheet counter missing/wrong on some page"
        )
        assert info["footer_bottom"] <= 841.89 - 2, "counter clipped at the page edge"
    else:
        assert not any("Лист" in t for t in texts), "counter rendered on a single-page document"

    # Header / signatures (2.1.0-approved form, unchanged in 2.2.0).
    assert "Грузоотправитель:" in texts[0]
    if pages > 1:
        assert not any("Грузоотправитель:" in t for t in texts[1:]), (
            "full header repeated on a non-first page"
        )
    assert "Кладовщик" in texts[-1], "storekeeper signature missing on the last page"
    if expect_move_labels and pages > 1:
        for label in ("Водитель", "Груз принял"):
            assert label in texts[-1], f"MOVE signature {label!r} missing on the last page"
            assert not any(label in t for t in texts[:-1]), (
                f"MOVE signature {label!r} leaked onto a non-last page"
            )


# ---------------------------------------------------------------------------
# Pagination matrix: pinned counts + integrity + frame + footer + signatures
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("n", [1, 20, 75, 200, 500])
def test_fixture_pagination_integrity_and_chrome(n: int) -> None:
    """Canonical envelope -> QDE -> Typst -> PDF with pinned 2.2.0 counts."""
    envelope = _fixture(n)
    pdf = _render(envelope)
    pages = _page_count(pdf)
    pinned = EXPECTED_PAGES_22[n]
    assert pages == pinned, (
        f"waybill-qde22-{n} rendered {pages} pages, pinned EXPECTED_PAGES_22={pinned} "
        "(re-measure deliberately and update the constant, see LAYOUT.md §10)"
    )
    # Acceptance bound: 2.2.0 must not need MORE pages than the legacy
    # renderer for the same document (divergence downwards is intended).
    assert EXPECTED_PAGES_22[n] <= EXPECTED_PAGES_LEGACY[n]
    _assert_common(pdf, n, _pages_info(pdf, n))


def test_single_page_rules() -> None:
    """Empty document -> 1 stub page; fixture-1 -> 1 page with signatures."""
    empty = _fixture(1)
    empty["document"]["lines"] = []
    empty["document"]["total_lines"] = 0
    pdf = _render(empty)
    texts = _pages_info(pdf, 0)["texts"]
    assert len(texts) == 1
    assert "Нет строк для печати" in texts[0]
    assert "Кладовщик" in texts[0]
    assert "Грузоотправитель:" in texts[0]
    assert not any("Лист" in t for t in texts)

    pdf1 = _render(_fixture(1))
    assert _page_count(pdf1) == 1
    texts1 = _pages_info(pdf1, 1)["texts"]
    assert "Грузоотправитель:" in texts1[0]
    assert "Кладовщик" in texts1[0]
    assert "Водитель" in texts1[0]
    assert "Груз принял" in texts1[0]
    assert not any("Лист" in t for t in texts1)


# ---------------------------------------------------------------------------
# Uniform fill of first+middle pages (physical, border-based)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("n", [75, 200, 500])
def test_uniform_physical_fill(n: int) -> None:
    """First+middle pages share a common fill level (TZ §6.3 п.4).

    Fill is measured physically per page as the occupied row area
    (table height minus header row) over the available row area
    (frame bottom minus table top minus header row) — row COUNTS vary
    legitimately with name heights and are not the criterion.
    """
    envelope = _fixture(n)
    pdf = _render(envelope)
    info = _pages_info(pdf, n)
    pages = _page_count(pdf)
    fills = []
    for top, bot in info["table_spans"][: pages - 1]:
        available = BOTTOM_LIMIT_PT - 2 - top - HEADER_ROW_PT
        occupied = bot - top - HEADER_ROW_PT
        fills.append(occupied / available)
    assert fills, "no prefix pages"
    spread = (max(fills) - min(fills)) / max(fills)
    min_share = min(fills) / (sum(fills) / len(fills))
    # Actual values pinned here for reviewer visibility (05.09.2026:
    # spread 0.000..0.151, min_share >= 0.85 across the fixtures).
    assert spread <= FILL_SPREAD_MAX, (
        f"fill spread {spread:.3f} > {FILL_SPREAD_MAX}: {fills}"
    )
    assert min_share >= FILL_MIN_SHARE, (
        f"min fill share {min_share:.3f} < {FILL_MIN_SHARE}: {fills}"
    )


# ---------------------------------------------------------------------------
# Font fallback (TZ §4.3 / §6.3 п.8)
# ---------------------------------------------------------------------------


def _envelope_with_long_name(name: str) -> dict:
    env = _fixture(20)
    doc = env["document"]
    doc["lines"][0]["item_name"] = name
    doc["lines"][0]["comment"] = None
    return env


def test_font_fallback_long_wordy_name() -> None:
    """A long wordy name (>2 normal lines at 11pt) falls back to 10pt."""
    wordy = ("Кран шаровой фланцевый стальной для трубопроводов пара и горячей воды "
             "с номинальным диаметром сто миллиметров, давление шестнадцать бар")
    envelope = _envelope_with_long_name(wordy)
    pdf = _render(envelope)  # no panic
    info = _pages_info(pdf, 20)
    _assert_common(pdf, 20, info)

    # Fallback engaged: some text span of the long name renders smaller
    # than the 11pt body size (10pt or 9pt). Spans wrap without
    # hyphenation, so every span text is a substring of the name.
    import pymupdf

    doc = pymupdf.open(stream=pdf, filetype="pdf")
    try:
        sizes = set()
        for page in doc:
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = span["text"].strip()
                        if len(text) > 3 and text in wordy:
                            sizes.add(round(span["size"], 1))
        assert sizes, "long name text not found in the PDF"
        assert any(s < 10.9 for s in sizes), f"fallback size not applied for the long name: {sizes}"
    finally:
        doc.close()


def test_font_fallback_unbroken_token_no_panic() -> None:
    """A 200-char unbroken token renders without panic at natural height.

    The 40-char ZWSP chunking is font-size independent, so even 9pt
    cannot bring such a row to <= 2 normal lines; per TZ §4.3 the row
    keeps its natural height and participates in packing (no panic).
    """
    token = "Шланг" + "X" * 195
    envelope = _envelope_with_long_name(token)
    pdf = _render(envelope)  # must not panic
    info = _pages_info(pdf, 20)
    _assert_common(pdf, 20, info)
    all_text = "".join(info["texts"])
    assert token[:40] in all_text, "long token text lost"


# ---------------------------------------------------------------------------
# Determinism (TZ §6.3 п.9)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("n", [1, 20, 75, 200, 500])
def test_repeated_render_is_byte_identical(n: int) -> None:
    """Two renders of the same fixture are byte-identical."""
    pdf_a = _render(_fixture(n))
    pdf_b = _render(_fixture(n))
    assert hashlib.sha256(pdf_a).hexdigest() == hashlib.sha256(pdf_b).hexdigest()
