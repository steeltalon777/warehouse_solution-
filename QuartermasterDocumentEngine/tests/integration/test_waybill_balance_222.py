"""2.2.2 waybill integration tests (global exact pagination balancing).

These tests pin the 2.2.2 contract on top of the frozen 2.2.0/2.2.1
suites (``test_waybill_balance.py`` / ``test_waybill_null_safety.py``
are intentionally untouched):

* minimal page count (2.2.2 packs the 32-row FP knife-edge document
  into 2 pages, not 3);
* hard capacities (frame + safety gap; occupied <= role area);
* every row exactly once, original order;
* GLOBAL physical fill including the last page, normalised per page
  role (``used_height / A_role``) and measured from the PDF — item
  row counts are a diagnostic metric only;
* FP knife-edge regression (anchor 32 -> 16/16);
* real-anchor regressions 44 / 69 / 143 with exact partitions;
* fixtures 20 / 75 / 200 / 500 with pinned page counts;
* deterministic repeated renders;
* null-safety cases of 2.2.1 still render on 2.2.2;
* header / table / signatures / footer unchanged vs 2.2.1.

The frozen 2.2.0 partition pins live in ``EXPECTED_PAGES_22``; the
2.2.1 partitions of the same anchors were 3/4/25 (32 rows) and
10/13/21 (44 rows) — the 2.2.2 packer deliberately rebalances them
(LAYOUT.md §10), the acceptance bound stays ``pages <= 2.2.0`` and
every page must carry at least one row.

Skips cleanly when the pinned Typst binary is unavailable.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from qm_engine.envelope import parse_envelope
from qm_engine.render import render_envelope

from tests.integration.test_waybill_balance import (
    BOTTOM_LIMIT_PT,
    HEADER_ROW_PT,
    _assert_common,
    _page_count,
    _pages_info,
    _render,
)

REPO = Path(__file__).resolve().parents[2]
TEMPLATES = REPO / "templates"
FIXTURES = REPO / "tests" / "fixtures" / "waybill-222"

# Sheet geometry (LAYOUT.md §1): A4 portrait, margins 16 mm top /
# 14 mm left,right,bottom -> content height.
MM_PT = 72 / 25.4
PAGE_H_PT = 841.89
CONTENT_H_PT = PAGE_H_PT - 30 * MM_PT
FRAME_TOP_PT = 16 * MM_PT

# Signature block height for the MOVE set (all waybill anchors are
# MOVE), measured in the 2.2.2 checkpoint: A_last = C - HM - HT - HS.
# Kept as a constant so the test normalises the last page exactly the
# way the engine does; the derived role areas are asserted against
# the measured engine areas below.
HS_MOVE_PT = 106.9
MEASURED_A_FIRST_PT = 620.25
MEASURED_A_MIDDLE_PT = 722.15
ROLE_AREA_TOLERANCE_PT = 3.0

# 2.2.2 partitions (item rows per page) pinned on fresh direct renders
# (checkpoint 1 + release-candidate rerun, deterministically identical).
EXPECTED_PARTITIONS: dict[str, list[int]] = {
    "anchor32": [16, 16],
    "anchor44": [15, 15, 14],
    "anchor69": [21, 25, 23],
    "anchor143": [20, 24, 27, 26, 23, 23],
    "qde20": [10, 10],
    "qde75": [13, 17, 16, 17, 12],
    "qde200": [14, 18, 18, 18, 18, 18, 17, 16, 17, 16, 17, 13],
    "qde500": [14, 17, 17, 18, 18, 17, 17, 16, 17, 16, 17, 16, 17, 16, 17, 16,
               17, 17, 17, 17, 17, 16, 16, 18, 18, 19, 15, 17, 17, 13],
}

# 2.2.0/2.2.1 page counts for the fixtures (frozen reference): the
# 2.2.2 counts must never exceed them.
REFERENCE_PAGES_220: dict[str, int] = {
    "qde20": 2, "qde75": 5, "qde200": 12, "qde500": 30,
}
EXPECTED_PAGES_222: dict[str, int] = {
    "qde20": 2, "qde75": 5, "qde200": 12, "qde500": 30,
}

# Physical fill acceptance (rendered table height / role area).
FILL_SPREAD_MAX = 0.12
FILL_MIN = 0.60
FILL_OVERFLOW_TOLERANCE = 0.01

NULL_CASES: list[tuple[str, list[str]]] = [
    ("receiver", ["Накладная № 120626/0550/2", "Грузополучатель: Акша", "Основание: Поступление"]),
    ("sender", ["Накладная № 100826/0343/0", "Грузополучатель: ДЭУ (КСК)"]),
    ("operation", ["Накладная № WB-FIX-3", "Грузополучатель: ДЭУ (КСК)"]),
    ("basis", ["Основание: Перемещение"]),
    ("minimal", ["Накладная № WB-MIN-1", "Грузополучатель: —", "Основание: Операция"]),
]

CANONICAL_SIGNERS = ("Кладовщик", "Оператор", "Водитель", "Груз принял")


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


def _fixture(name: str) -> dict:
    raw = (FIXTURES / f"waybill222-{name}.typst.json").read_text(encoding="utf-8")
    return parse_envelope(raw).data


def _partitions(info: dict) -> list[int]:
    return [len(nums) for nums in info["rows_per_page"]]


def _role_areas(info: dict) -> tuple[float, float, float]:
    """Derive (A_first, A_middle, A_last) from the rendered geometry."""
    spans = info["table_spans"]
    top_first = spans[0][0] - FRAME_TOP_PT
    top_middle = (spans[1][0] - FRAME_TOP_PT) if len(spans) > 1 else top_first
    # Page 0: the first drawing line is the table top (header row
    # inside the span) -> data area excludes the header row. Pages >0:
    # the header row top border sits above y=60 and is filtered out,
    # so the first line is already the first data row.
    a_first = CONTENT_H_PT - top_first - HEADER_ROW_PT
    a_middle = CONTENT_H_PT - top_middle
    a_last = a_middle - HS_MOVE_PT
    assert a_first == pytest.approx(MEASURED_A_FIRST_PT, abs=ROLE_AREA_TOLERANCE_PT), top_first
    assert a_middle == pytest.approx(MEASURED_A_MIDDLE_PT, abs=ROLE_AREA_TOLERANCE_PT), top_middle
    return a_first, a_middle, a_last


def _physical_fills(info: dict) -> tuple[list[float], tuple[float, float, float]]:
    """Global physical fills: (span - header row) / A_role, incl. last page."""
    pages = len(info["table_spans"])
    a_first, a_middle, a_last = _role_areas(info)
    fills: list[float] = []
    for idx, (top, bottom) in enumerate(info["table_spans"]):
        used = bottom - top - (HEADER_ROW_PT if idx == 0 else 0.0)
        if pages == 1:
            avail = a_first - HS_MOVE_PT
        elif idx == 0:
            avail = a_first
        elif idx == pages - 1:
            avail = a_last
        else:
            avail = a_middle
        fills.append(used / avail)
    return fills, (a_first, a_middle, a_last)


def _assert_partition(name: str, pdf: bytes, n: int) -> list[int]:
    info = _pages_info(pdf, n)
    _assert_common(pdf, n, info)
    parts = _partitions(info)
    assert parts == EXPECTED_PARTITIONS[name], (
        f"{name}: partition {parts} != pinned {EXPECTED_PARTITIONS[name]}"
    )
    assert sum(parts) == n, f"{name}: partition {parts} does not sum to {n}"
    assert all(p >= 1 for p in parts), f"{name}: stump page in {parts}"
    return parts


# ---------------------------------------------------------------------------
# Minimal page count + exact partitions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["qde20", "qde75", "qde200", "qde500"])
def test_fixture_page_count_and_partition(name: str) -> None:
    """Fixture page counts stay pinned (and <= the 2.2.0 reference)."""
    n = int(name.removeprefix("qde"))
    pdf = _render(_fixture(name))
    pages = _page_count(pdf)
    assert pages == EXPECTED_PAGES_222[name], f"{name}: {pages} pages"
    assert pages <= REFERENCE_PAGES_220[name], f"{name}: regression vs 2.2.0"
    _assert_partition(name, pdf, n)


@pytest.mark.parametrize("name", ["anchor32", "anchor44", "anchor69", "anchor143"])
def test_anchor_exact_partitions(name: str) -> None:
    """Real-anchor regressions with the exact 2.2.2 partitions."""
    n = int(name.removeprefix("anchor"))
    pdf = _render(_fixture(name))
    assert _page_count(pdf) == len(EXPECTED_PARTITIONS[name])
    _assert_partition(name, pdf, n)


def test_fp_knife_edge_32_balances_to_two_pages() -> None:
    """FP regression: the 32-row anchor must render 16/16, not 3/4/25.

    In 2.2.0/2.2.1 the two-page prefix attempt failed by +2.84e-14 pt
    against the exact zero-waste target and the packer fell back to a
    3-page layout with a 25-row last page. 2.2.2's capacity epsilon
    (0.01 pt) and global balancing produce the minimal 2-page layout.
    """
    pdf = _render(_fixture("anchor32"))
    assert _page_count(pdf) == 2
    assert _partitions(_pages_info(pdf, 32)) == [16, 16]


# ---------------------------------------------------------------------------
# Hard capacity + global physical fill (last page included)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["anchor32", "anchor44", "anchor69", "anchor143", "qde20", "qde75", "qde200", "qde500"],
)
def test_hard_capacity_and_global_fill(name: str) -> None:
    """Occupied height <= role area on every page; global fill uniform.

    Metric: ``used_height / A_role`` measured from the PDF table
    borders (stretch included). Item row counts above are diagnostics.
    The LAST page participates in the same uniformity assertion as
    first/middle pages.
    """
    n = int(name.removeprefix("anchor").removeprefix("qde"))
    pdf = _render(_fixture(name))
    info = _pages_info(pdf, n)
    _assert_common(pdf, n, info)
    fills, (a_first, a_middle, a_last) = _physical_fills(info)

    assert len(fills) == _page_count(pdf)
    assert all(f <= 1.0 + FILL_OVERFLOW_TOLERANCE for f in fills), (
        f"{name}: over-capacity page fill(s): {[round(f, 4) for f in fills]}"
    )
    assert max(fills) <= 1.0, f"{name}: hard capacity violated: {fills}"

    if len(fills) > 1:
        spread = max(fills) - min(fills)
        assert spread <= FILL_SPREAD_MAX, (
            f"{name}: global fill spread {spread:.4f} > {FILL_SPREAD_MAX}: "
            f"{[round(f, 4) for f in fills]} "
            f"(A_first={a_first:.2f}, A_middle={a_middle:.2f}, A_last={a_last:.2f})"
        )
        assert min(fills) >= FILL_MIN, (
            f"{name}: underfilled page {min(fills):.4f} < {FILL_MIN}: {fills}"
        )
        assert fills[-1] >= FILL_MIN, (
            f"{name}: last page stump {fills[-1]:.4f} < {FILL_MIN}: {fills}"
        )


def test_single_page_rules() -> None:
    """A one-row document is a single page; empty document -> stub page."""
    env = _fixture("qde20")
    env["document"]["lines"] = env["document"]["lines"][:1]
    env["document"]["total_lines"] = 1
    pdf = _render(env)
    assert _page_count(pdf) == 1
    texts = _pages_info(pdf, 1)["texts"]
    assert "Грузоотправитель:" in texts[0]
    assert "Кладовщик" in texts[0]
    assert "Водитель" in texts[0]
    assert "Груз принял" in texts[0]
    assert not any("Лист" in t for t in texts)

    empty = _fixture("qde20")
    empty["document"]["lines"] = []
    empty["document"]["total_lines"] = 0
    pdf = _render(empty)
    texts = _pages_info(pdf, 0)["texts"]
    assert len(texts) == 1
    assert "Нет строк для печати" in texts[0]
    assert "Кладовщик" in texts[0]


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["anchor44", "anchor143", "qde75"])
def test_repeated_render_is_byte_identical(name: str) -> None:
    """Two renders of the same 2.2.2 fixture are byte-identical."""
    first = _render(_fixture(name))
    second = _render(_fixture(name))
    assert hashlib.sha256(first).hexdigest() == hashlib.sha256(second).hexdigest()


# ---------------------------------------------------------------------------
# Null-safety carried over from 2.2.1
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("name", "needles"), NULL_CASES)
def test_null_safety_renders_with_expected_fallbacks(name: str, needles: list[str]) -> None:
    """The 2.2.1 null-safety cases render on 2.2.2 with same fallbacks."""
    envelope = _fixture(name)
    pdf = _render(envelope)
    info = _pages_info(pdf, len(envelope["document"]["lines"]))
    assert len(info["texts"]) == 1, f"{name}: null case must stay single-page"
    all_text = "\n".join(info["texts"])
    for needle in needles:
        assert needle in all_text, f"{name}: missing {needle!r}"
    _assert_common(pdf, len(envelope["document"]["lines"]), info)


# ---------------------------------------------------------------------------
# Header / table / signatures / footer unchanged vs 2.2.1
# ---------------------------------------------------------------------------


def test_blocks_unchanged_vs_221() -> None:
    """Same payload: 2.2.1 and 2.2.2 render the same chrome blocks.

    The row partition intentionally changes; header title, requisites,
    signature labels and the sheet counter must not.
    """
    fixture_221 = REPO / "tests" / "fixtures" / "waybill-221" / "waybill-qde221-75.typst.json"
    env_221 = parse_envelope(fixture_221.read_text(encoding="utf-8")).data
    pdf_221 = _render(env_221)
    pdf_222 = _render(_fixture("qde75"))

    texts_221 = _pages_info(pdf_221, 75)["texts"]
    texts_222 = _pages_info(pdf_222, 75)["texts"]

    def title_line(texts: list[str]) -> str:
        for line in texts[0].splitlines():
            if "Накладная №" in line:
                return line.strip()
        raise AssertionError("title line not found")

    assert title_line(texts_221) == title_line(texts_222)
    for label in ("Грузоотправитель:", "Грузополучатель:", "Основание:"):
        assert (label in texts_221[0]) == (label in texts_222[0])

    page_221 = len(texts_221)
    page_222 = len(texts_222)

    def signers(text: str) -> set[str]:
        return {label for label in CANONICAL_SIGNERS if label in text}

    assert signers(texts_221[-1]) == signers(texts_222[-1]), "signature set changed"
    assert signers(texts_222[-1]) >= {"Кладовщик", "Водитель", "Груз принял"}
    assert all(f"Лист 1 из {page_221}" in texts_221[0] for _ in [0])
    assert f"Лист 1 из {page_222}" in texts_222[0]
    assert f"Лист {page_222} из {page_222}" in texts_222[-1]
    assert "Наименование ТМЦ" in texts_222[0] and "Кол-во" in texts_222[0]


def test_footer_and_frame_limits() -> None:
    """Footer counter fits the reserved area; no content below the frame."""
    pdf = _render(_fixture("qde500"))
    info = _pages_info(pdf, 500)
    assert info["text_bottom"] <= BOTTOM_LIMIT_PT
    assert info["footer_bottom"] <= PAGE_H_PT - 2
