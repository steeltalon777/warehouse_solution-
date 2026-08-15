"""Structural checks (TZ §13.2).

The structural checker is a HARD gate per backend. For each rendered
PDF it extracts:

* ``page_count`` — number of pages in the document.
* ``paper`` — paper size detected from the MediaBox (A4 / Letter).
* ``orientation`` — portrait or landscape.
* ``blocks_pass`` — required blocks (header, table, signatures, footer)
  detected by substring search in the extracted text.
* ``table_rows`` — count of numbered row prefixes in the main table.

The expected values come from the manifest.yaml (``page.size``,
``page.orientation``) and from the envelope document
(``lines`` / ``trips`` + ``refuels`` / ``rows`` per fixture family).
The number of detected rows is compared against the expected count,
and the comparison is reported as a note rather than a hard failure
because layout-dependent row numbers can legitimately differ.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tests.harness._internals import (
    count_expected_rows,
    detect_family,
)

# ---------------------------------------------------------------------------
# Page size tables (PDF user-space units, 1 pt = 1/72 inch)
# ---------------------------------------------------------------------------

# A4: 210x297 mm; Letter: 216x279.4 mm. Both rounded to two decimals.
A4_PT = (595.28, 841.89)
LETTER_PT = (612.0, 792.0)

PAGE_SIZES_PT: dict[str, tuple[float, float]] = {
    "A4": A4_PT,
    "Letter": LETTER_PT,
}


# ---------------------------------------------------------------------------
# Per-family expected substrings for the block check
# ---------------------------------------------------------------------------

# Multiple substrings are listed per block. A block is "present" if ANY
# of its substrings appears in the extracted text. WeasyPrint and
# Typst differ in casing (e.g. "Товарная накладная" vs
# "ТОВАРНАЯ НАКЛАДНАЯ"), so both forms are listed.

BLOCK_EXPECTATIONS: dict[str, dict[str, list[str]]] = {
    "waybill": {
        "header": ["Товарная накладная", "ТОВАРНАЯ НАКЛАДНАЯ"],
        "table": ["Наименование", "Кол-во"],
        "signatures": ["Сдал", "Принял", "Главный бухгалтер"],
        "footer": ["Лист", "Страница"],
    },
    "route-sheet": {
        "header": ["Путевой лист", "ПУТЕВОЙ ЛИСТ"],
        "table": ["км", "АЗС"],
        "signatures": ["Водитель", "Механик", "Диспетчер"],
        "footer": ["Лист", "Страница"],
    },
    "fuel": {
        "header": ["Отчёт по расходу", "ОТЧЁТ ПО РАСХОДУ"],
        "table": ["Объём", "Пробег"],
        # The fuel spike templates deliberately omit a signer
        # block (TZ §T7: the fuel-report layout focuses on data +
        # subtotals). An empty list means the block is always
        # considered present.
        "signatures": [],
        "footer": ["Лист", "Страница"],
    },
}


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class StructuralResult:
    """Outcome of running :func:`check_structural` on one PDF."""

    page_count: int
    paper: str
    orientation: str
    blocks_pass: dict[str, bool]
    table_rows: int
    expected_table_rows: int
    notes: list[str] = field(default_factory=list)

    @property
    def all_blocks_pass(self) -> bool:
        return all(self.blocks_pass.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_count": self.page_count,
            "paper": self.paper,
            "orientation": self.orientation,
            "blocks_pass": dict(self.blocks_pass),
            "table_rows": self.table_rows,
            "expected_table_rows": self.expected_table_rows,
            "all_blocks_pass": self.all_blocks_pass,
            "notes": list(self.notes),
        }


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def detect_paper_and_orientation(mediabox_width: float, mediabox_height: float) -> tuple[str, str]:
    """Detect paper size + orientation from a MediaBox (width, height).

    Returns ``("Unknown", orientation)`` when no standard paper size
    matches within 20 pt. The 20 pt tolerance covers the 1 pt drifts
    produced by rounding to the same dimension in the two backends.
    """
    width = float(mediabox_width)
    height = float(mediabox_height)
    orientation = "portrait" if height >= width else "landscape"

    shorter = min(width, height)
    longer = max(width, height)

    best_paper = "A4"
    best_diff = float("inf")
    for paper, (std_w, std_h) in PAGE_SIZES_PT.items():
        expected_short = min(std_w, std_h)
        expected_long = max(std_w, std_h)
        diff = abs(shorter - expected_short) + abs(longer - expected_long)
        if diff < best_diff:
            best_diff = diff
            best_paper = paper

    if best_diff > 20:
        return "Unknown", orientation
    return best_paper, orientation


def expected_table_rows(envelope: dict[str, Any], family: str) -> int:
    """Return the expected number of rows for the given family."""
    if family == "waybill":
        return len(envelope["document"]["lines"])
    if family == "route-sheet":
        doc = envelope["document"]
        return len(doc["trips"]) + len(doc["refuels"])
    if family == "fuel":
        return len(envelope["document"]["rows"])
    raise ValueError(f"Unknown family: {family}")


def check_blocks(family: str, page_texts: list[str]) -> dict[str, bool]:
    """Check that required blocks are present in the page text.

    An empty substring list marks the block as "not applicable" —
    the gate reports "pass" without doing any substring search.
    This is used for families whose templates deliberately omit a
    block (e.g. the fuel spike templates do not render a signer
    block).
    """
    expectations = BLOCK_EXPECTATIONS[family]
    all_text = "\n".join(page_texts)
    result: dict[str, bool] = {}
    for block_name, substrings in expectations.items():
        if not substrings:
            result[block_name] = True
        else:
            result[block_name] = any(substr in all_text for substr in substrings)
    return result


def count_table_rows(page_texts: list[str], expected: int) -> int:
    """Count rows by looking for numbered prefixes in the table.

    The implementation uses :func:`count_expected_rows` (i.e. count
    how many of the expected row numbers 1..N appear in the text)
    so the matcher is robust to the very different layouts produced
    by WeasyPrint (row number on its own line) and Typst (row number
    sometimes rendered as ``idx + 1`` inline). The expected count is
    passed in so the helper can abort on huge inputs.
    """
    return count_expected_rows(page_texts, expected)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def check_structural(
    pdf_path: Path,
    envelope: dict[str, Any],
    fixture_name: str,
) -> StructuralResult:
    """Run the structural gate on ``pdf_path``.

    Parameters
    ----------
    pdf_path:
        Rendered PDF (weasy backend or typst backend).
    envelope:
        Parsed envelope JSON (source of truth for row counts).
    fixture_name:
        Logical fixture name (used to detect the family).
    """
    import pymupdf  # spike extra, lazy

    family = detect_family(fixture_name)
    expected_rows = expected_table_rows(envelope, family)

    doc = pymupdf.open(pdf_path)  # type: ignore[no-untyped-call]
    try:
        page_count = len(doc)
        if page_count == 0:
            return StructuralResult(
                page_count=0,
                paper="Unknown",
                orientation="portrait",
                blocks_pass={k: False for k in BLOCK_EXPECTATIONS[family]},
                table_rows=0,
                expected_table_rows=expected_rows,
                notes=["PDF has no pages"],
            )
        page = doc[0]
        mediabox = page.mediabox
        width = float(mediabox.width)
        height = float(mediabox.height)
    finally:
        doc.close()  # type: ignore[no-untyped-call]

    paper, orientation = detect_paper_and_orientation(width, height)
    page_texts = _iter_page_texts(pdf_path)
    blocks_pass = check_blocks(family, page_texts)
    table_rows = count_table_rows(page_texts, expected_rows)

    notes: list[str] = []
    if abs(table_rows - expected_rows) > 0:
        notes.append(f"row count mismatch: expected {expected_rows}, found {table_rows}")

    return StructuralResult(
        page_count=page_count,
        paper=paper,
        orientation=orientation,
        blocks_pass=blocks_pass,
        table_rows=table_rows,
        expected_table_rows=expected_rows,
        notes=notes,
    )


def _iter_page_texts(pdf_path: Path) -> list[str]:
    """Return the text of each page as a list of strings (lazy import).

    Returning strings (rather than page objects) keeps the PyMuPDF
    document open for the duration of the iteration so the page
    objects are still valid when ``get_text`` is called.
    """
    import pymupdf  # spike extra, lazy

    doc = pymupdf.open(pdf_path)  # type: ignore[no-untyped-call]
    try:
        return [doc[i].get_text() for i in range(len(doc))]  # type: ignore[no-untyped-call]
    finally:
        doc.close()  # type: ignore[no-untyped-call]
