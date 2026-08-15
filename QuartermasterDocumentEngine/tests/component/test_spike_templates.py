"""Component tests for the 5 spike template packages (TZ-PHASE2-BACKEND-SPIKE §8 T7).

For each package we run ``qm-render render`` against the matching fixture
(``tests/fixtures/{doctype}/{fixture}.{weasy,typst}.json``) and verify:

- the artifact is a valid PDF (or PNG for ``--format png``)
- ``page_count >= 1``
- semantic content from the fixture appears in the text layer

Tests skip cleanly when the corresponding backend is unavailable.
"""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfReader
from qm_engine.envelope import parse_envelope
from qm_engine.render import render_envelope

REPO = Path(__file__).resolve().parents[2]
TEMPLATES = REPO / "templates"
WAYBILL_FIX = REPO / "tests" / "fixtures" / "waybill" / "waybill-20.typst.json"
ROUTE_FIX = REPO / "tests" / "fixtures" / "route-sheet" / "vehicle-route-sheet-1.weasy.json"
ROUTE_FIX_TYPST = REPO / "tests" / "fixtures" / "route-sheet" / "vehicle-route-sheet-1.typst.json"
FUEL_FIX = REPO / "tests" / "fixtures" / "fuel" / "fuel-report-100.weasy.json"
FUEL_FIX_TYPST = REPO / "tests" / "fixtures" / "fuel" / "fuel-report-100.typst.json"


def _weasyprint_available() -> bool:
    try:
        import weasyprint  # noqa: F401
    except ImportError:
        return False
    return True


def _typst_available() -> bool:
    from qm_backends.typst_backend import TypstBackend

    try:
        return TypstBackend().available()
    except Exception:  # noqa: BLE001 - availability probe
        return False


_skip_no_weasyprint = pytest.mark.skipif(
    not _weasyprint_available(),
    reason="weasyprint not installed in this environment",
)
_skip_no_typst = pytest.mark.skipif(
    not _typst_available(),
    reason="real typst binary not present; run scripts/fetch_typst.py",
)


def _pdf_pages(pdf_bytes: bytes) -> int:
    return len(PdfReader(BytesIO(pdf_bytes)).pages)


def _pdf_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


# ---------------------------------------------------------------------------
# 1. spike-waybill-typst@0.1.0
# ---------------------------------------------------------------------------


@_skip_no_typst
@pytest.mark.spike
def test_spike_waybill_typst_renders_pdf() -> None:
    """The Typst waybill produces a valid multi-page PDF with semantic content."""
    envelope = parse_envelope(WAYBILL_FIX.read_text(encoding="utf-8"))
    result = render_envelope(envelope, TEMPLATES, output_format="pdf")
    assert result.data[:5] == b"%PDF-"
    assert result.page_count is not None
    assert result.page_count >= 1
    assert _pdf_pages(result.data) == result.page_count

    text = _pdf_text(result.data)
    # Phase 2.1: the Typst backend now writes the **full normalized
    # envelope** to ``document.json``, so the template reads the
    # envelope-level ``document_number`` (``WB-FIX-20``) directly via
    # ``doc.document_number``. The previous fallback to
    # ``operation.display_number`` is no longer used (TZ-PHASE2-BACKEND-SPIKE
    # §T5 / §11.2 / Phase 2.1 §1).
    fixture_doc = json.loads(WAYBILL_FIX.read_text(encoding="utf-8"))
    document_number = fixture_doc.get("document_number")
    display_number = fixture_doc["document"]["operation"]["display_number"]
    assert document_number in text, (
        f"expected envelope-level document_number {document_number!r} in PDF text layer"
    )
    # ``operation.display_number`` is no longer rendered into the
    # header — it would have to live on the inner document path
    # ``doc.document.operation.display_number``. Sanity check that
    # the template is not silently rebinding to it.
    assert display_number not in text, (
        f"unexpected display_number {display_number!r} in PDF text layer "
        "(template should use envelope-level document_number)"
    )

    # At least one Cyrillic item name from the fixture lines. Narrow table
    # columns wrap long names across many lines, so check the leading word.
    item_names = [line["item_name"] for line in fixture_doc["document"]["lines"]]
    leading_words = {name.split(" ")[0] for name in item_names if name}
    found_words = [w for w in leading_words if w in text]
    assert found_words, (
        "expected at least one Cyrillic item_name from the fixture in the PDF text layer"
    )


# ---------------------------------------------------------------------------
# 2. spike-route-sheet-weasy@0.1.0
# ---------------------------------------------------------------------------


@_skip_no_weasyprint
@pytest.mark.spike
def test_spike_route_sheet_weasy_renders_pdf() -> None:
    """The WeasyPrint route sheet produces a valid PDF with semantic content."""
    envelope = parse_envelope(ROUTE_FIX.read_text(encoding="utf-8"))
    result = render_envelope(envelope, TEMPLATES, output_format="pdf")
    assert result.data[:5] == b"%PDF-"
    assert result.page_count is not None
    assert result.page_count >= 1
    assert _pdf_pages(result.data) == result.page_count

    text = _pdf_text(result.data)
    fixture_doc = json.loads(ROUTE_FIX.read_text(encoding="utf-8"))

    # Vehicle plate from the fixture.
    plate = fixture_doc["document"]["vehicle"]["plate"]
    assert plate in text, f"expected vehicle plate {plate!r} in PDF text layer"

    # Driver full name from the fixture.
    driver_name = fixture_doc["document"]["driver"]["full_name"]
    assert driver_name in text, f"expected driver name {driver_name!r} in PDF text layer"

    # At least 5 distinct trip purpose prefixes appear. (Narrow table columns
    # wrap multi-word purposes across lines, so we check the leading word.)
    purpose_prefixes = {t["purpose"].split(" ")[0] for t in fixture_doc["document"]["trips"]}
    found_prefixes = [p for p in purpose_prefixes if p in text]
    assert len(found_prefixes) >= 5, (
        f"expected at least 5 trip purpose prefixes in PDF text, found {len(found_prefixes)}: "
        f"{found_prefixes}"
    )

    # At least 3 refuel volumes appear (each fixture refuel has a unique volume).
    refuel_volumes = [str(r["volume_l"]) for r in fixture_doc["document"]["refuels"]]
    found_volumes = [v for v in refuel_volumes if v in text]
    assert len(found_volumes) >= 3, (
        f"expected at least 3 refuel volumes in PDF text, found {len(found_volumes)}"
    )


# ---------------------------------------------------------------------------
# 3. spike-route-sheet-typst@0.1.0
# ---------------------------------------------------------------------------


@_skip_no_typst
@pytest.mark.spike
def test_spike_route_sheet_typst_renders_pdf() -> None:
    """The Typst route sheet produces a valid PDF with semantic content.

    Note: Typst renders Russian-decimal numbers with ``,`` rather than ``.``
    (``123.5`` -> ``123,5``). The test accepts both formats.
    """
    envelope = parse_envelope(ROUTE_FIX_TYPST.read_text(encoding="utf-8"))
    result = render_envelope(envelope, TEMPLATES, output_format="pdf")
    assert result.data[:5] == b"%PDF-"
    assert result.page_count is not None
    assert result.page_count >= 1
    assert _pdf_pages(result.data) == result.page_count

    text = _pdf_text(result.data)
    fixture_doc = json.loads(ROUTE_FIX_TYPST.read_text(encoding="utf-8"))

    plate = fixture_doc["document"]["vehicle"]["plate"]
    assert plate in text, f"expected vehicle plate {plate!r} in PDF text layer"

    driver_name = fixture_doc["document"]["driver"]["full_name"]
    assert driver_name in text, f"expected driver name {driver_name!r} in PDF text layer"

    purposes = {t["purpose"].split(" ")[0] for t in fixture_doc["document"]["trips"]}
    found_purposes = [p for p in purposes if p in text]
    assert len(found_purposes) >= 5, (
        f"expected at least 5 trip purpose prefixes in PDF text, found {len(found_purposes)}: "
        f"{found_purposes}"
    )

    refuel_volumes = fixture_doc["document"]["refuels"]
    found_volumes: list[str] = []
    for r in refuel_volumes:
        v = r["volume_l"]
        if str(v) in text or f"{v:.1f}".replace(".", ",") in text:
            found_volumes.append(str(v))
    assert len(found_volumes) >= 3, (
        f"expected at least 3 refuel volumes in PDF text, found {len(found_volumes)}"
    )


# ---------------------------------------------------------------------------
# 4. spike-fuel-report-weasy@0.1.0
# ---------------------------------------------------------------------------


@_skip_no_weasyprint
@pytest.mark.spike
def test_spike_fuel_report_weasy_renders_pdf() -> None:
    """The WeasyPrint fuel report produces a valid landscape PDF with semantic content."""
    envelope = parse_envelope(FUEL_FIX.read_text(encoding="utf-8"))
    result = render_envelope(envelope, TEMPLATES, output_format="pdf")
    assert result.data[:5] == b"%PDF-"
    assert result.page_count is not None
    assert result.page_count >= 1
    assert _pdf_pages(result.data) == result.page_count

    # Landscape MediaBox check (MediaBox[2] > MediaBox[3]).
    reader = PdfReader(BytesIO(result.data))
    media_box = reader.pages[0].mediabox
    assert float(media_box.width) > float(media_box.height), (
        f"expected landscape orientation (width > height), got {media_box.width}x{media_box.height}"
    )

    text = _pdf_text(result.data)
    fixture_doc = json.loads(FUEL_FIX.read_text(encoding="utf-8"))

    # Period: MM.YYYY format from the WeasyPrint template.
    period = fixture_doc["document"]["period"]
    period_str = f"{period['month']:02d}.{period['year']}"
    assert period_str in text, f"expected period {period_str!r} in PDF text layer"

    # At least 5 distinct vehicle plates appear.
    plates = [v["plate"] for v in fixture_doc["document"]["vehicles"]]
    found_plates = [p for p in plates if p in text]
    assert len(found_plates) >= 5, (
        f"expected at least 5 distinct vehicle plates in PDF text, found {len(found_plates)}"
    )

    # Grand total cost.
    grand_total = fixture_doc["document"]["grand_total"]
    cost_str = f"{grand_total['total_cost']:.2f}"
    assert cost_str in text, f"expected grand total cost {cost_str!r} in PDF text layer"


# ---------------------------------------------------------------------------
# 5. spike-fuel-report-typst@0.1.0
# ---------------------------------------------------------------------------


@_skip_no_typst
@pytest.mark.spike
def test_spike_fuel_report_typst_renders_pdf() -> None:
    """The Typst fuel report produces a valid landscape PDF with semantic content."""
    envelope = parse_envelope(FUEL_FIX_TYPST.read_text(encoding="utf-8"))
    result = render_envelope(envelope, TEMPLATES, output_format="pdf")
    assert result.data[:5] == b"%PDF-"
    assert result.page_count is not None
    assert result.page_count >= 1
    assert _pdf_pages(result.data) == result.page_count

    # Landscape MediaBox check.
    reader = PdfReader(BytesIO(result.data))
    media_box = reader.pages[0].mediabox
    assert float(media_box.width) > float(media_box.height)

    text = _pdf_text(result.data)
    fixture_doc = json.loads(FUEL_FIX_TYPST.read_text(encoding="utf-8"))

    # Period: accept either MM.YYYY (WeasyPrint style) or MM/YYYY (Typst style).
    period = fixture_doc["document"]["period"]
    period_dot = f"{period['month']:02d}.{period['year']}"
    assert period_dot in text, f"expected period {period_dot!r} in PDF text layer"

    # At least 5 distinct vehicle plates.
    plates = [v["plate"] for v in fixture_doc["document"]["vehicles"]]
    found_plates = [p for p in plates if p in text]
    assert len(found_plates) >= 5, (
        f"expected at least 5 distinct vehicle plates in PDF text, found {len(found_plates)}"
    )

    # Grand total cost — accept either ``.`` (en-US) or ``,`` (ru-RU) decimal.
    grand_total = fixture_doc["document"]["grand_total"]
    cost_dot = f"{grand_total['total_cost']:.2f}"
    cost_comma = cost_dot.replace(".", ",")
    assert (cost_dot in text) or (cost_comma in text), (
        f"expected grand total cost {cost_dot!r} or {cost_comma!r} in PDF text layer"
    )
