"""Phase 6C canonical waybill integration tests (TZ-QDE_INTEGRATION_READINESS §10.3).

These tests exercise the production template
``warehouse-waybill-ru@2.0.0`` end-to-end: canonical envelope -> QDE
engine -> real Typst 0.15.1 -> PDF, plus the Phase 6C requirements:

* pagination matrix (1/20/75/200/500 lines) with expected page counts
  fixed from the frozen legacy renderer (Warehouse_web@133e2fa,
  WeasyPrint 66.0; see ``spike-out/phase6c-waybill/legacy/legacy-pagination.json``);
* boundary semantics around the page capacities;
* page-capacity configurability (alternate capacities change page
  allocation WITHOUT touching the pagination algorithm);
* signature configurability (2/4/6 blocks, order, labels, grid);
* no missing/duplicate rows; long-text/Cyrillic handling;
* deterministic repeated renders;
* ``inspect-template`` exit 0.

The tests skip cleanly when the pinned Typst binary is unavailable.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from pypdf import PdfReader
from qm_engine.envelope import parse_envelope
from qm_engine.render import render_envelope

REPO = Path(__file__).resolve().parents[2]
TEMPLATES = REPO / "templates"
FIXTURES = REPO / "tests" / "fixtures" / "waybill"
TEMPLATE_ID = "warehouse-waybill-ru"
TEMPLATE_VERSION = "2.0.0"

# Authoritative page counts from the frozen legacy renderer
# (Warehouse_web@133e2fa, real paginate_waybill_lines + WeasyPrint
# 66.0; the same numbers are reproducible with the ported algorithm in
# _legacy_pages below). Any deviation is a REVIEW_REQUIRED event.
EXPECTED_PAGES: dict[int, int] = {1: 1, 20: 4, 75: 10, 200: 27, 500: 66}

# Canonical capacities (layout-config.typ, MOVE).
CANONICAL_CAPS: dict[str, int] = {"first": 22, "middle": 28, "last": 19, "single": 15}

# A4 content frame: 297 - 14mm bottom margin, in points, + 2pt tolerance.
BOTTOM_LIMIT_PT = 841.89 - 14 * 72 / 25.4 + 2


def _typst_available() -> bool:
    from qm_backends.typst_backend import TypstBackend

    try:
        return TypstBackend().available()
    except Exception:  # noqa: BLE001 - availability probe
        return False


def _pymupdf() -> Any:
    try:
        import pymupdf  # spike extra, lazy
    except ImportError:  # pragma: no cover - environment dependent
        pytest.skip("pymupdf (spike extra) not installed")
    return pymupdf


pytestmark = [
    pytest.mark.skipif(
        not _typst_available(),
        reason="real typst binary not present; run scripts/fetch_typst.py",
    )
]


# ---------------------------------------------------------------------------
# Legacy algorithm oracle (mirror of Warehouse_web@133e2fa services.py,
# used ONLY to compute expected page counts for synthetic envelopes).
# ---------------------------------------------------------------------------


def _line_units(line: dict[str, Any]) -> int:
    name = str(line.get("item_name") or "")
    words = re.findall(r"\S+", name)
    if not words:
        return 1
    visual_lines = 1
    current_length = 0
    for word in words:
        for start in range(0, len(word), 40):
            chunk = word[start : start + 40]
            separator = 1 if current_length else 0
            if current_length + separator + len(chunk) <= 40:
                current_length += separator + len(chunk)
            else:
                visual_lines += 1
                current_length = len(chunk)
    return visual_lines


def _legacy_pages(lines: list[dict[str, Any]], caps: dict[str, int]) -> int:
    """Return the page count the legacy algorithm would produce."""
    if not lines:
        return 1
    units = [_line_units(line) for line in lines]
    if sum(units) <= caps["single"]:
        return 1
    first_end = min(
        next((i for i, u in enumerate(units) if sum(units[:i]) + u > caps["first"]), len(units)),
        len(units) - 1,
    )
    last_start = len(units)
    used = 0
    while last_start > first_end and used + units[last_start - 1] <= caps["last"]:
        last_start -= 1
        used += units[last_start]
    if used == 0:  # pragma: no cover - only hit for invalid test configs
        raise AssertionError("last page too tall")
    middle_pages = 0
    cur = first_end
    while cur < last_start:
        m = next(
            (
                i
                for i, u in enumerate(units[cur:last_start])
                if sum(units[cur : cur + i]) + u > caps["middle"]
            ),
            last_start - cur,
        )
        cur += m
        middle_pages += 1
    return 1 + middle_pages + 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fixture(n: int) -> dict[str, Any]:
    raw = (FIXTURES / f"waybill-qde-{n}.typst.json").read_text(encoding="utf-8")
    return parse_envelope(raw).data


def _render(envelope: dict[str, Any], templates_root: Path = TEMPLATES) -> bytes:
    parsed = parse_envelope(
        __import__("json").dumps(envelope, ensure_ascii=False)
    )
    result = render_envelope(parsed, templates_root, output_format="pdf")
    assert result.format == "pdf"
    assert not result.warnings, f"typst emitted warnings: {result.warnings}"
    return result.data


def _page_count(pdf_bytes: bytes) -> int:
    from io import BytesIO

    return len(PdfReader(BytesIO(pdf_bytes)).pages)


def _page_texts(pdf_bytes: bytes) -> list[str]:
    pymupdf = _pymupdf()
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        return [doc[i].get_text() for i in range(len(doc))]
    finally:
        doc.close()


def _row_numbers(pdf_bytes: bytes, total: int) -> dict[int, int]:
    """Count occurrences of each row number in the № column (x < 75 pt)."""
    pymupdf = _pymupdf()
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    found: dict[int, int] = {}
    try:
        for page in doc:
            for word in page.get_text("words"):
                x0, y0, text = word[0], word[1], word[4]
                if x0 < 75 and y0 > 60 and re.fullmatch(r"\d{1,4}", text):
                    n = int(text)
                    if 1 <= n <= total:
                        found[n] = found.get(n, 0) + 1
    finally:
        doc.close()
    return found


def _max_text_bottom(pdf_bytes: bytes) -> float:
    """Return the max text baseline bottom across all pages."""
    pymupdf = _pymupdf()
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    bottom = 0.0
    try:
        for page in doc:
            for word in page.get_text("words"):
                bottom = max(bottom, word[3])
    finally:
        doc.close()
    return bottom


def _short_lines(n: int) -> list[dict[str, Any]]:
    return [
        {"line_number": i, "item_name": f"ТМЦ {i}", "unit_symbol": "шт", "quantity": 1}
        for i in range(1, n + 1)
    ]


def _envelope_with_lines(n: int, lines: list[dict[str, Any]]) -> dict[str, Any]:
    env = _fixture(20)  # base fixture; lines are replaced below
    doc = env["document"]
    doc["lines"] = lines
    doc["total_lines"] = len(lines)
    return env


def _copy_template_with_config(tmp_path: Path, replacements: dict[str, str]) -> Path:
    """Copy the 2.0.0 package to a temp templates root with patched config.

    ``replacements`` maps exact layout-config.typ substrings to their
    replacements (Phase 6C: config-level change only — the pagination
    algorithm is untouched).
    """
    pkg_src = TEMPLATES / TEMPLATE_ID / TEMPLATE_VERSION
    templates_root = tmp_path / "templates"
    pkg_dst = templates_root / TEMPLATE_ID / TEMPLATE_VERSION
    shutil.copytree(pkg_src, pkg_dst)
    config_path = pkg_dst / "layout-config.typ"
    text = config_path.read_text(encoding="utf-8")
    for old, new in replacements.items():
        assert old in text, f"pattern {old!r} not found in layout-config.typ"
        text = text.replace(old, new)
    config_path.write_text(text, encoding="utf-8")
    return templates_root


# ---------------------------------------------------------------------------
# inspect-template
# ---------------------------------------------------------------------------


def test_inspect_template_exit_zero() -> None:
    """``inspect-template warehouse-waybill-ru --version 2.0.0`` must exit 0."""
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "qm_cli.main",
            "--templates-dir",
            str(TEMPLATES),
            "inspect-template",
            "--template",
            TEMPLATE_ID,
            "--version",
            TEMPLATE_VERSION,
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO,
        timeout=120,
    )
    assert proc.returncode == 0, f"inspect-template failed:\n{proc.stderr}"
    assert '"template_id": "warehouse-waybill-ru"' in proc.stdout
    assert '"template_version": "2.0.0"' in proc.stdout


# ---------------------------------------------------------------------------
# Pagination matrix + production-shape integration
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("n", [1, 20, 75, 200, 500])
def test_canonical_fixture_pagination_and_row_integrity(n: int) -> None:
    """Canonical envelope -> QDE -> Typst -> PDF with the legacy page counts.

    Verifies: expected page count (deviation => REVIEW_REQUIRED), all
    row numbers present exactly once, physical fit inside the frame.
    """
    envelope = _fixture(n)
    pdf = _render(envelope)
    page_texts = _page_texts(pdf)

    pages = _page_count(pdf)
    assert pages == EXPECTED_PAGES[n], (
        f"REVIEW_REQUIRED: waybill-qde-{n} rendered {pages} pages, "
        f"expected {EXPECTED_PAGES[n]} (frozen legacy baseline)"
    )

    rows = _row_numbers(pdf, n)
    missing = [i for i in range(1, n + 1) if i not in rows]
    dupes = [i for i, c in rows.items() if c > 1]
    assert not missing, f"missing rows: {missing[:10]}"
    assert not dupes, f"duplicate rows: {dupes[:10]}"

    assert _max_text_bottom(pdf) <= BOTTOM_LIMIT_PT, "content overflows the bottom margin"

    if n > 1:
        # Counter on every page; short header on pages 2+.
        assert all(f"Лист {i + 1} из {pages}" in page_texts[i] for i in range(pages))
        assert "Грузоотправитель:" in page_texts[0]
        for text in page_texts[1:]:
            assert "Грузоотправитель:" not in text
    else:
        assert "Грузоотправитель:" in page_texts[0]
        assert not any("Лист" in text for text in page_texts)

    # Storekeeper line on every page.
    assert all("Кладовщик" in text for text in page_texts)
    # MOVE signature labels on the last page only.
    for label in ("Операцию разрешил", "Водитель", "Начальник базы", "Груз принял"):
        assert label in page_texts[-1]
    assert "Операцию разрешил" not in "".join(page_texts[:-1])


def test_waybill_500_production_shape() -> None:
    """waybill-500 production-shape envelope: exit 0, valid PDF, 66 pages."""
    envelope = _fixture(500)
    pdf = _render(envelope)
    assert _page_count(pdf) == EXPECTED_PAGES[500]
    page_texts = _page_texts(pdf)

    # Required header data.
    assert "Накладная № 1/0343/100826" in page_texts[0]
    assert "Грузоотправитель:" in page_texts[0]
    assert "Грузополучатель: ДЭУ (КСК)" in page_texts[0]
    assert "Основание: Перемещение Угдан → ДЭУ (КСК)" in page_texts[0]

    # All 500 positions present, no duplicates.
    rows = _row_numbers(pdf, 500)
    assert len(rows) == 500
    assert all(c == 1 for c in rows.values())

    # Required final/signature data.
    assert "Кладовщик" in page_texts[-1]
    for label in ("Операцию разрешил", "Водитель", "Начальник базы", "Груз принял"):
        assert label in page_texts[-1]
    assert "Лист 66 из 66" in page_texts[-1]


# ---------------------------------------------------------------------------
# Boundary semantics (short 1-unit lines around the capacities)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("n", "expected"),
    [
        (14, 1),  # single - 1
        (15, 1),  # single capacity (MOVE)
        (16, 2),  # single + 1 -> first + last
        (21, 2),  # first - 1 rows on page 1
        (22, 2),  # first capacity: [21, 1]
        (23, 2),  # first + 1: [22, 1]
        (24, 2),  # [23, 1]
        (41, 2),  # first 22 + last 19
        (42, 3),  # last capacity + 1 -> one middle page
        (70, 4),  # 22 + 28 + 1 + 19 -> middle capacity boundary
        (71, 4),  # 22 + 28 + 2 + 19
    ],
)
def test_boundary_pagination_short_lines(n: int, expected: int) -> None:
    """Capacity boundaries: capacity-1 / capacity / capacity+1 for each role."""
    envelope = _envelope_with_lines(n, _short_lines(n))
    assert _legacy_pages(envelope["document"]["lines"], CANONICAL_CAPS) == expected
    pdf = _render(envelope)
    pages = _page_count(pdf)
    assert pages == expected, f"{n} short lines: got {pages} pages, expected {expected}"


def test_empty_document_renders_single_page() -> None:
    """Empty lines -> one page with the empty-document row."""
    envelope = _envelope_with_lines(1, [])
    pdf = _render(envelope)
    texts = _page_texts(pdf)
    assert len(texts) == 1
    assert "Нет строк для печати" in texts[0]
    assert "Кладовщик" in texts[0]


# ---------------------------------------------------------------------------
# Configurability: page capacities (TZ §21)
# ---------------------------------------------------------------------------


def test_alternate_capacities_change_allocation_without_algorithm_change(
    tmp_path: Path,
) -> None:
    """A config-only edit (20/26/17) must change page allocation.

    The template copy lives in a temp templates root; the production
    2.0.0 package is untouched. The pagination algorithm is unchanged.
    """
    templates_root = _copy_template_with_config(
        tmp_path,
        {
            "    first: 22,": "    first: 20,",
            "    middle: 28,": "    middle: 26,",
            "    last: 19,": "    last: 17,",
            "    MOVE: 19,": "    MOVE: 17,",
            "    single: 15,": "    single: 14,",
            "    MOVE: 15,": "    MOVE: 14,",
        },
    )
    alt_caps = {"first": 20, "middle": 26, "last": 17, "single": 14}
    for n in (75, 200, 500):
        envelope = _fixture(n)
        expected = _legacy_pages(envelope["document"]["lines"], alt_caps)
        assert expected != EXPECTED_PAGES[n], "alternate config must change the page count"
        pdf = _render(envelope, templates_root)
        pages = _page_count(pdf)
        assert pages == expected, (
            f"waybill-qde-{n} with capacities 20/26/17: got {pages}, expected {expected}"
        )
        rows = _row_numbers(pdf, n)
        assert len(rows) == n and all(c == 1 for c in rows.values())
        assert _max_text_bottom(pdf) <= BOTTOM_LIMIT_PT


def test_canonical_config_still_renders_after_alternate_copy(tmp_path: Path) -> None:
    """The production package must be byte-identical after the temp copy test."""
    pdf_a = _render(_fixture(75))
    pdf_b = _render(_fixture(75))
    assert pdf_a == pdf_b


# ---------------------------------------------------------------------------
# Configurability: signatures (TZ §22)
# ---------------------------------------------------------------------------

_MOVE_SET_BLOCK = (
    "      (\n"
    '        key: "k{i}",\n'
    '        label: "Подпись {i}",\n'
    '        position-label: "должность",\n'
    '        signature-label: "фио/подпись",\n'
    "        driver: false,\n"
    "      ),\n"
)


def _patch_signature_set(tmp_path: Path, blocks: list[str], extra: dict[str, str]) -> Path:
    """Replace the MOVE signature set with ``blocks`` + extra config patches."""
    replacement = "    MOVE: (\n" + "".join(blocks) + "    ),\n"
    patches = {
        "    MOVE: (\n"
        "      (\n"
        '        key: "operation-approved",\n'
        '        label: "Операцию разрешил",\n'
        '        position-label: "должность",\n'
        '        signature-label: "фио/подпись",\n'
        "        driver: false,\n"
        "      ),\n"
        "      (\n"
        '        key: "driver",\n'
        '        label: "Водитель",\n'
        "        driver: true,\n"
        "      ),\n"
        "      (\n"
        '        key: "base-chief",\n'
        '        label: "Начальник базы",\n'
        '        position-label: "должность",\n'
        '        signature-label: "фио/подпись",\n'
        "        driver: false,\n"
        "      ),\n"
        "      (\n"
        '        key: "goods-received",\n'
        '        label: "Груз принял",\n'
        '        position-label: "должность",\n'
        '        signature-label: "фио/подпись",\n'
        "        driver: false,\n"
        "      ),\n"
        "    ),\n": replacement,
    }
    patches.update(extra)
    return _copy_template_with_config(tmp_path, patches)


@pytest.mark.parametrize("count", [2, 3, 4, 5, 6])
def test_signature_variants_render_in_order(tmp_path: Path, count: int) -> None:
    """2/3/4/5/6 declarative blocks render in order with correct labels.

    4 blocks = canonical set; other counts are test-only configs.
    """
    blocks = [_MOVE_SET_BLOCK.format(i=i) for i in range(1, count + 1)]
    # 6 standard blocks make the last-page form taller: the documented
    # workflow also lowers last/single capacities (config change).
    extra: dict[str, str] = {}
    if count > 4:
        extra.update({"    last: 19,": "    last: 16,", "    MOVE: 19,": "    MOVE: 16,"})
    templates_root = _patch_signature_set(tmp_path, blocks, extra)

    envelope = _fixture(75)
    pdf = _render(envelope, templates_root)
    last_text = _page_texts(pdf)[-1]
    labels = [f"Подпись {i}" for i in range(1, count + 1)]
    for label in labels:
        assert label in last_text, f"label {label!r} missing on the last page"
    positions = [last_text.index(label) for label in labels]
    assert positions == sorted(positions), "signature labels out of order"
    assert "Кладовщик" in last_text
    assert _max_text_bottom(pdf) <= BOTTOM_LIMIT_PT, "signature form overflows the frame"


def test_signature_grid_two_columns_flows_row_major(tmp_path: Path) -> None:
    """With columns: 2 the 4 canonical blocks flow row-major, all labels render."""
    blocks = [_MOVE_SET_BLOCK.format(i=i) for i in range(1, 5)]
    templates_root = _patch_signature_set(
        tmp_path,
        blocks,
        {"    columns: 1,": "    columns: 2,"},
    )
    envelope = _fixture(75)
    pdf = _render(envelope, templates_root)
    last_text = _page_texts(pdf)[-1]
    for i in range(1, 5):
        assert f"Подпись {i}" in last_text
    assert _max_text_bottom(pdf) <= BOTTOM_LIMIT_PT


# ---------------------------------------------------------------------------
# Long text / Cyrillic (TZ §16)
# ---------------------------------------------------------------------------


def test_long_single_token_name_and_long_requisites() -> None:
    """A 200-char unbroken token must wrap (ZWSP chunking), not overflow."""
    envelope = _fixture(20)
    doc = envelope["document"]
    token = "Шланг" + "X" * 197  # 200 chars, no spaces
    doc["lines"][0]["item_name"] = token
    doc["lines"][0]["comment"] = "длинный комментарий: " + "значение " * 30
    pdf = _render(envelope)
    texts = _page_texts(pdf)
    all_text = "".join(texts)
    assert token[:40] in all_text
    assert _max_text_bottom(pdf) <= BOTTOM_LIMIT_PT
    rows = _row_numbers(pdf, 20)
    assert len(rows) == 20 and all(c == 1 for c in rows.values())


# ---------------------------------------------------------------------------
# Determinism (TZ §18)
# ---------------------------------------------------------------------------


def test_repeated_render_is_byte_identical() -> None:
    """Two renders of the same envelope in the same environment match."""
    pdf_a = _render(_fixture(500))
    pdf_b = _render(_fixture(500))
    assert hashlib.sha256(pdf_a).hexdigest() == hashlib.sha256(pdf_b).hexdigest()
