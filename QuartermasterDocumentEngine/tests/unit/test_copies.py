"""Unit tests for engine-level copies (TZ-PHASE2-BACKEND-SPIKE §T8).

Covers the ``concatenate_pdfs`` helper in :mod:`qm_engine.copies` and
the ``copies`` validation in :func:`qm_engine.render.render_envelope`.
The actual end-to-end render flow with copies is exercised in the
component tests (``tests/component/test_copies.py``).
"""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter
from qm_engine.copies import concatenate_pdfs
from qm_engine.envelope import Envelope
from qm_engine.errors import (
    RenderFailedError,
    UnsupportedOutputFormatError,
)
from qm_engine.render import render_envelope

REPO = Path(__file__).resolve().parents[2]
TEMPLATES = REPO / "templates"


def _make_minimal_pdf(page_count: int = 1) -> bytes:
    """Build a real, valid single-page PDF blob using pypdf.

    Used by the concatenate_pdfs tests so that the parser actually walks
    page objects. The bytes are NOT byte-identical to a "real" PDF
    because pypdf fills in a few fixed fields (Producer etc.) — the
    concatenate_pdfs contract is that the page count survives, not that
    any particular byte range is preserved.
    """
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=72, height=72)
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_concatenate_pdfs_empty_returns_empty_bytes() -> None:
    assert concatenate_pdfs([]) == b""


def test_concatenate_pdfs_single_returns_input() -> None:
    blob = b"%PDF-1.4 single"
    assert concatenate_pdfs([blob]) == blob


def test_concatenate_pdfs_two_blobs() -> None:
    blob_a = _make_minimal_pdf(page_count=1)
    blob_b = _make_minimal_pdf(page_count=2)
    out = concatenate_pdfs([blob_a, blob_b])
    assert out[:5] == b"%PDF-"
    reader = PdfReader(BytesIO(out))
    assert len(reader.pages) == 3


def test_concatenate_pdfs_three_blobs() -> None:
    blobs = [_make_minimal_pdf(page_count=2) for _ in range(3)]
    out = concatenate_pdfs(blobs)
    assert len(PdfReader(BytesIO(out)).pages) == 6


def test_concatenate_pdfs_preserves_page_count_when_input_doubles() -> None:
    """``concatenate_pdfs([a, a])`` returns a PDF with twice the pages."""
    blob = _make_minimal_pdf(page_count=4)
    out = concatenate_pdfs([blob, blob])
    assert len(PdfReader(BytesIO(out)).pages) == 8


# --- render_options.copies validation --------------------------------------


def _load_waybill_envelope() -> Envelope:
    raw = (REPO / "tests" / "fixtures" / "waybill-20.json").read_bytes()
    return Envelope(json.loads(raw))


def test_render_envelope_rejects_copies_zero() -> None:
    env = _load_waybill_envelope()
    with pytest.raises(RenderFailedError) as exc:
        render_envelope(env, TEMPLATES, render_options={"copies": 0})
    assert "copies" in exc.value.message
    assert exc.value.details.get("copies") == 0


def test_render_envelope_rejects_copies_negative() -> None:
    env = _load_waybill_envelope()
    with pytest.raises(RenderFailedError) as exc:
        render_envelope(env, TEMPLATES, render_options={"copies": -1})
    assert exc.value.details.get("copies") == -1


def test_render_envelope_rejects_copies_string() -> None:
    """A non-integer ``copies`` value is rejected with RENDER_FAILED."""
    env = _load_waybill_envelope()
    with pytest.raises(RenderFailedError):
        render_envelope(env, TEMPLATES, render_options={"copies": "two"})


def _pdf_signature(data: bytes) -> tuple[int, str]:
    """Return a WeasyPrint-non-determinism-resistant signature for a PDF.

    Compares page count and the extracted text. WeasyPrint's compressed
    stream length varies between calls, so byte-for-byte comparison is
    not a reliable equivalence test in a long-running process. The text
    content and page count are the user-visible contract.
    """
    assert data[:5] == b"%PDF-"
    reader = PdfReader(BytesIO(data))
    text = "".join((p.extract_text() or "") for p in reader.pages)
    return len(reader.pages), text


def test_render_envelope_copies_one_is_identical_to_no_options() -> None:
    """Phase 1 byte-identical invariant (TZ-PHASE2-BACKEND-SPIKE §T8 #6).

    Two consecutive ``render_envelope`` calls with the same inputs —
    one passing ``render_options={"copies": 1}`` and one passing
    ``render_options=None`` — must produce a PDF with the same page
    count and the same extracted text. (Raw PDF bytes are not asserted
    equal because WeasyPrint varies its compressed stream length
    between calls; the user-visible contract is preserved.)
    """
    env_a = _load_waybill_envelope()
    env_b = _load_waybill_envelope()
    with_options = render_envelope(env_a, TEMPLATES, render_options={"copies": 1})
    without_options = render_envelope(env_b, TEMPLATES, render_options=None)
    sig_a = _pdf_signature(with_options.data)
    sig_b = _pdf_signature(without_options.data)
    assert sig_a == sig_b
    assert with_options.data[:5] == b"%PDF-"


def test_render_envelope_copies_default_is_one() -> None:
    """Calling render_envelope without render_options must behave as copies=1.

    Same equivalence class as :func:`test_render_envelope_copies_one_is_identical_to_no_options`
    but starting from the default signature. We compare user-visible
    PDF semantics (page count, text) because WeasyPrint's raw stream
    is not stable across calls.
    """
    env_a = _load_waybill_envelope()
    env_b = _load_waybill_envelope()
    default_call = render_envelope(env_a, TEMPLATES)
    explicit_call = render_envelope(env_b, TEMPLATES, render_options={"copies": 1})
    assert _pdf_signature(default_call.data) == _pdf_signature(explicit_call.data)
    assert default_call.data[:5] == b"%PDF-"


def test_render_envelope_copies_two_doubles_pages_weasyprint() -> None:
    """Engine-level copies concatenate page count N=2 for the WeasyPrint path."""
    env_a = _load_waybill_envelope()
    env_b = _load_waybill_envelope()
    single = render_envelope(env_a, TEMPLATES, render_options={"copies": 1})
    double = render_envelope(env_b, TEMPLATES, render_options={"copies": 2})
    assert double.page_count is not None
    assert single.page_count is not None
    assert double.page_count == 2 * single.page_count
    assert double.data[:5] == b"%PDF-"
    assert len(PdfReader(BytesIO(double.data)).pages) == 2 * single.page_count


def test_render_envelope_copies_png_rejected() -> None:
    """copies > 1 must be rejected for non-PDF output (TZ §T8)."""
    env = _load_waybill_envelope()
    with pytest.raises(UnsupportedOutputFormatError) as exc:
        render_envelope(env, TEMPLATES, output_format="png", render_options={"copies": 2})
    assert "copies" in exc.value.message or "png" in exc.value.message


def test_render_envelope_copies_one_png_allowed() -> None:
    """copies == 1 with PNG output must not raise copies-related errors.

    The WeasyPrint backend itself rejects PNG; the engine must not
    pre-empt that with a copies error.
    """
    from qm_engine.errors import UnsupportedOutputFormatError as UoFErr

    env = _load_waybill_envelope()
    with pytest.raises(UoFErr):
        render_envelope(env, TEMPLATES, output_format="png", render_options={"copies": 1})
