"""Physical basis/table regression for the unpromoted 2.2.3 prototype.

Use glyph outlines, not extraction bboxes (which include font-wide descent).
The 2 mm clear-ink minimum matches the table's 2 mm cell inset. At 11 pt,
3 mm of baseline-to-table spacing covers the Cyrillic descenders plus half
the 0.6 pt border stroke. No absolute page coordinate or PDF hash is pinned.
"""

from __future__ import annotations

from functools import lru_cache

import pymupdf
import pytest
from fontTools.ttLib import TTFont

from tests.integration.test_waybill_balance import _assert_common, _pages_info, _render
from tests.integration.test_waybill_balance_222 import (
    EXPECTED_PARTITIONS,
    NULL_CASES,
    REPO,
    _fixture,
    _typst_available,
)

MM_PT = 72 / 25.4
REQUIRED_GAP_PT = 2 * MM_PT
pytestmark = pytest.mark.skipif(not _typst_available(), reason="real Typst unavailable")


@lru_cache
def _font(name: str) -> TTFont:
    # The manifest pins these bundled fonts; reject unexpected substitution.
    assert name in ("DejaVuSans", "DejaVuSans-Bold"), name
    return TTFont(REPO / "fonts" / f"{name}.ttf")


def table_rules(page: pymupdf.Page) -> list[dict]:
    """Full-width horizontal table strokes, excluding signature underlines."""
    content_width = page.rect.width - 28 * MM_PT
    rules = []
    for drawing in page.get_drawings():
        if drawing["type"] not in ("s", "fs"):
            continue
        for item in drawing["items"]:
            if item[0] != "l":
                continue
            a, b = item[1:3]
            if abs(a.y - b.y) < 0.001 and abs(a.x - b.x) >= content_width - 0.01:
                rules.append({"y": a.y, "width": drawing["width"], "x0": min(a.x, b.x)})
    assert rules, "no table border found"
    return sorted(rules, key=lambda rule: rule["y"])


def basis_geometry(pdf: bytes) -> dict[str, float]:
    """PDF top-down pt: lowest basis outline -> upper painted table edge.

    Select all basis lines, including wrapping. Baseline == border centre
    must be included: that equality is precisely the frozen 2.2.2 defect.
    """
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        page = doc[0]
        label = next(w for w in page.get_text("words") if w[4] == "Основание:")
        rule = table_rules(page)[0]
        bottoms, baselines = [], set()
        for block in page.get_text("rawdict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    for char in span["chars"]:
                        baseline = char["origin"][1]
                        if not label[1] <= baseline <= rule["y"] + 0.01:
                            continue
                        font = _font(span["font"])
                        glyph = font["glyf"][font.getBestCmap()[ord(char["c"])]]
                        if not hasattr(glyph, "yMin"):  # spaces have no ink
                            continue
                        scale = span["size"] / font["head"].unitsPerEm
                        bottoms.append(baseline - glyph.yMin * scale)
                        baselines.add(baseline)
        assert bottoms, "basis glyph outlines not found"
        basis_bottom = max(bottoms)
        table_top = rule["y"] - rule["width"] / 2
        return {"basis_bottom": basis_bottom, "table_top": table_top,
                "gap": table_top - basis_bottom, "basis_lines": len(baselines)}


def row_sequence(pdf: bytes) -> list[list[int]]:
    """Preserve occurrences, unlike the historical set-based row helper."""
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        pages = []
        for page in doc:
            rules = table_rules(page)
            left = rules[0]["x0"]
            words = sorted(page.get_text("words"), key=lambda w: (w[1], w[0]))
            pages.append([int(w[4]) for w in words if w[4].isdigit()
                          and left <= w[0] < left + 11 * MM_PT
                          and rules[0]["y"] < w[1] < rules[-1]["y"]])
        return pages


def _candidate(name: str) -> dict:
    env = _fixture(name)
    env["template_version"] = "2.2.3"
    return env


def test_frozen_222_is_negative_control() -> None:
    """The geometric detector actually catches the reported overlap."""
    assert basis_geometry(_render(_fixture("anchor32")))["gap"] < 0


@pytest.mark.parametrize("name", list(EXPECTED_PARTITIONS))
def test_basis_separation_and_existing_page_budget(name: str) -> None:
    env = _candidate(name)
    pdf = _render(env)
    n = len(env["document"]["lines"])
    _assert_common(pdf, n, _pages_info(pdf, n))
    rows = row_sequence(pdf)
    assert [number for page in rows for number in page] == list(range(1, n + 1))
    assert len(rows) <= len(EXPECTED_PARTITIONS[name]), "cosmetic fix increased page count"
    assert basis_geometry(pdf)["gap"] >= REQUIRED_GAP_PT
    # Exact partitions are compared in checkpoint evidence, not silently
    # re-pinned here: any difference needs Product Owner review.


def test_wrapped_basis_and_requisites_keep_clear_ink_gap() -> None:
    env = _candidate("anchor32")
    env["document"]["consignee_label"] = "участок получения запасных частей " * 4
    env["document"]["basis_label"] = "Перемещение Угдан → участок Джекдача " * 5
    metrics = basis_geometry(_render(env))
    assert metrics["basis_lines"] > 1, "fixture did not exercise wrapping"
    assert metrics["gap"] >= REQUIRED_GAP_PT


@pytest.mark.parametrize(("name", "needles"), NULL_CASES)
def test_nullable_fallbacks_with_basis_gap(name: str, needles: list[str]) -> None:
    env = _candidate(name)
    pdf = _render(env)
    info = _pages_info(pdf, len(env["document"]["lines"]))
    _assert_common(pdf, len(env["document"]["lines"]), info)
    assert len(info["texts"]) == 1
    for needle in needles:
        assert needle in info["texts"][0]
    assert basis_geometry(pdf)["gap"] >= REQUIRED_GAP_PT


def test_repeated_problem_document_is_byte_identical() -> None:
    assert _render(_candidate("anchor32")) == _render(_candidate("anchor32"))
