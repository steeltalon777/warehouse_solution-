"""Unit tests for engine-level watermark (TZ-PHASE2-BACKEND-SPIKE §T8 review note #1).

The watermark flag is thread through ``render_options`` and injected into
the normalized document at both the top level and inside the inner
``document`` mapping (mirror-copies pattern). Phase 1 callers that do
not pass the flag see byte-identical behaviour — no ``watermark`` key
is added to the normalized document.

The real WeasyPrint / Typst binary probes and font/asset checks are
bypassed by monkey-patching ``engine.qm_engine.render._BACKENDS`` with
a recording stub that captures the ``normalized_document`` it receives.
That keeps the unit tests fast and dependency-free.
"""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import pytest
from click.testing import CliRunner
from pypdf import PdfReader, PdfWriter
from qm_backends.base import RenderResult
from qm_cli.main import cli
from qm_engine import render as engine_render
from qm_engine.envelope import Envelope
from qm_engine.errors import RenderFailedError

REPO = Path(__file__).resolve().parents[2]
TEMPLATES = REPO / "templates"


def _minimal_pdf(page_count: int = 1) -> bytes:
    """Build a real single-page PDF blob using pypdf (same helper as test_copies)."""
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=72, height=72)
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


# --- Recording backend stub -----------------------------------------------


class _RecordingBackend:
    """Minimal backend stub that captures the ``normalized_document`` dict.

    Returns a real PDF blob so the engine-level copies concatenation
    path works when the caller asks for ``copies > 1``.
    """

    def __init__(self, name: str = "recording") -> None:
        self.name = name
        self.calls: list[dict[str, object]] = []

    def available(self) -> bool:
        return True

    def render(
        self,
        normalized_document: dict[str, object],
        template_package: object,
        output_format: str,
        render_options: dict[str, object],
    ) -> RenderResult:
        # Deep-capture so subsequent in-place mutations don't leak.
        self.calls.append(
            {
                "normalized_document": json.loads(json.dumps(normalized_document)),
                "output_format": output_format,
                "render_options": dict(render_options),
            }
        )
        return RenderResult(
            data=_minimal_pdf(page_count=1),
            format=output_format,
            page_count=1,
            warnings=[],
        )


@pytest.fixture
def recording_backend(monkeypatch: pytest.MonkeyPatch) -> _RecordingBackend:
    """Replace the engine's backends with a single recorder.

    The waybill-render template declares ``backend: typst`` so we
    register the recorder under that name. The recorder captures the
    normalized document so tests can introspect the watermark field
    injection.
    """
    backend = _RecordingBackend(name="typst")
    monkeypatch.setitem(engine_render._BACKENDS, "typst", backend)
    return backend


def _load_waybill_envelope() -> Envelope:
    raw = (REPO / "tests" / "fixtures" / "waybill" / "waybill-20.typst.json").read_bytes()
    return Envelope(json.loads(raw))


def _load_route_sheet_envelope() -> Envelope:
    raw = (
        REPO / "tests" / "fixtures" / "route-sheet" / "vehicle-route-sheet-1.weasy.json"
    ).read_bytes()
    return Envelope(json.loads(raw))


# --- Test 1: default (Phase 1 byte-identical) ------------------------------


def test_render_options_default_no_watermark(recording_backend: _RecordingBackend) -> None:
    """Phase 1 callers see byte-identical behaviour: no ``watermark`` key.

    Passing ``render_options={}`` (or ``render_options=None``) must not
    inject the ``watermark`` key at either the top level of the
    normalized document or inside the inner ``document`` mapping.
    """
    envelope = _load_waybill_envelope()
    engine_render.render_envelope(envelope, TEMPLATES, render_options={})
    assert len(recording_backend.calls) == 1
    normalized = recording_backend.calls[0]["normalized_document"]
    assert "watermark" not in normalized
    inner = normalized.get("document")
    assert isinstance(inner, dict)
    assert "watermark" not in inner


# --- Test 2: True injects at both levels -----------------------------------


def test_render_options_watermark_true_injects_both_levels(
    recording_backend: _RecordingBackend,
) -> None:
    """``watermark=True`` is mirrored at top level and inside the document."""
    envelope = _load_waybill_envelope()
    engine_render.render_envelope(envelope, TEMPLATES, render_options={"watermark": True})
    assert len(recording_backend.calls) == 1
    normalized = recording_backend.calls[0]["normalized_document"]
    assert normalized.get("watermark") is True
    inner = normalized.get("document")
    assert isinstance(inner, dict)
    assert inner.get("watermark") is True


# --- Test 3: explicit False is preserved -----------------------------------


def test_render_options_watermark_false_injects_false(
    recording_backend: _RecordingBackend,
) -> None:
    """Explicit ``watermark=False`` is preserved at both levels."""
    envelope = _load_waybill_envelope()
    engine_render.render_envelope(envelope, TEMPLATES, render_options={"watermark": False})
    assert len(recording_backend.calls) == 1
    normalized = recording_backend.calls[0]["normalized_document"]
    assert normalized.get("watermark") is False
    inner = normalized.get("document")
    assert isinstance(inner, dict)
    assert inner.get("watermark") is False


# --- Test 4: invalid types are rejected ------------------------------------


@pytest.mark.parametrize("bad_value", ["yes", 1, 0, 1.5, None, [True], {"v": True}])
def test_render_options_rejects_non_bool_watermark(
    recording_backend: _RecordingBackend, bad_value: object
) -> None:
    """Non-boolean ``watermark`` values raise ``RenderFailedError``.

    The engine treats the flag as a strict boolean: anything else is a
    programmer error and is surfaced as ``RENDER_FAILED`` so the CLI
    exit code is consistent with other validation paths.
    """
    envelope = _load_waybill_envelope()
    with pytest.raises(RenderFailedError) as exc:
        engine_render.render_envelope(envelope, TEMPLATES, render_options={"watermark": bad_value})
    assert "watermark" in exc.value.message
    # The recorder must not have been called — validation rejects
    # before the backend is invoked.
    assert recording_backend.calls == []


# --- Test 5: CLI flag defaults to no-watermark -----------------------------


def test_cli_default_no_watermark_flag() -> None:
    """Click ``--watermark/--no-watermark`` flag defaults to ``False``.

    The CLI surface exposes the flag with a default of ``False`` so the
    default ``qm-render render`` invocation is byte-identical to
    Phase 1 (TZ §T8 review note #1). Calling ``render`` without any
    watermark flag accepts the payload and produces a valid PDF.
    """
    runner = CliRunner()
    payload_path = REPO / "tests" / "fixtures" / "route-sheet" / "vehicle-route-sheet-1.weasy.json"
    with runner.isolated_filesystem():
        out = Path("rs-default.pdf")
        result = runner.invoke(
            cli,
            [
                "--templates-dir",
                str(TEMPLATES),
                "render",
                "--input",
                str(payload_path),
                "--output",
                str(out),
            ],
        )
        assert result.exit_code == 0, f"CLI failed: {result.output}"
        assert out.is_file()
        data = out.read_bytes()
    assert data[:5] == b"%PDF-"
    reader = PdfReader(BytesIO(data))
    text = "".join((p.extract_text() or "") for p in reader.pages)
    # The default path must NOT include the ОБРАЗЕЦ stamp.
    assert "ОБРАЗЕЦ" not in text


# --- Bonus: copies path also preserves watermark ---------------------------


def test_render_options_watermark_with_copies_preserves_at_each_iteration(
    recording_backend: _RecordingBackend,
) -> None:
    """Watermark is preserved at both levels for each per-copy render.

    With ``copies=2`` and ``watermark=True`` the engine must inject the
    flag into every per-copy normalized document, mirroring the copies
    injection pattern.
    """
    envelope = _load_waybill_envelope()
    result = engine_render.render_envelope(
        envelope,
        TEMPLATES,
        render_options={"copies": 2, "watermark": True},
    )
    # The engine renders N times and concatenates; the recorder
    # captures every per-copy call.
    assert len(recording_backend.calls) == 2
    for call in recording_backend.calls:
        normalized = call["normalized_document"]
        assert normalized.get("watermark") is True
        inner = normalized.get("document")
        assert isinstance(inner, dict)
        assert inner.get("watermark") is True
        # Copies fields still present per the existing T8 contract.
        assert normalized.get("copy_number") in (1, 2)
        assert normalized.get("copies_total") == 2
        assert inner.get("copy_number") in (1, 2)
        assert inner.get("copies_total") == 2
    # The result is a concatenated PDF with the expected page count.
    assert result.page_count is not None
    assert result.page_count == 2 * 1  # 1 page per copy
