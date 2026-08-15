"""Component tests for the WeasyPrint baseline backend (SPEC v2 §10)."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfReader
from qm_backends.weasyprint_backend import WeasyPrintBackend
from qm_engine.envelope import parse_envelope
from qm_engine.render import render_envelope

REPO = Path(__file__).resolve().parents[2]
WAYBILL = REPO / "tests" / "fixtures" / "waybill-20.json"
TEMPLATES = REPO / "templates"


@pytest.fixture(scope="module")
def waybill_envelope():
    return parse_envelope(WAYBILL.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def rendered(waybill_envelope):
    result = render_envelope(waybill_envelope, TEMPLATES, output_format="pdf")
    return result


def test_backend_available() -> None:
    assert WeasyPrintBackend().available() is True


def test_render_produces_pdf_header(rendered) -> None:  # type: ignore[no-untyped-def]
    assert rendered.data[:5] == b"%PDF-"


def test_render_nonempty(rendered) -> None:  # type: ignore[no-untyped-def]
    assert len(rendered.data) > 0


def test_render_at_least_one_page(rendered) -> None:  # type: ignore[no-untyped-def]
    assert rendered.page_count is not None
    assert rendered.page_count >= 1


def test_render_format_is_pdf(rendered) -> None:  # type: ignore[no-untyped-def]
    assert rendered.format == "pdf"


def test_render_unsupported_format(waybill_envelope) -> None:  # type: ignore[no-untyped-def]
    from qm_engine.errors import UnsupportedOutputFormatError

    with pytest.raises(UnsupportedOutputFormatError):
        render_envelope(waybill_envelope, TEMPLATES, output_format="png")


def test_render_enumeration_visible_in_pdf(rendered) -> None:  # type: ignore[no-untyped-def]
    """Cyrillic long names must survive into the PDF text layer."""
    reader = PdfReader(BytesIO(rendered.data))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "Труба" in text or "Болт" in text


def test_page_count_parsing() -> None:
    """pypdf-based page count on a real rendered artifact is >= 1."""
    result = render_envelope(parse_envelope(WAYBILL.read_text(encoding="utf-8")), TEMPLATES)
    assert WeasyPrintBackend._count_pages(result.data) >= 1
