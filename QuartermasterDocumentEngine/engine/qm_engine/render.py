"""Render orchestration (SPEC v2 §2, ADR-0001 D2, TZ-PHASE1-CLI-SKELETON).

Pipeline: validated envelope → registry lookup → backend selection → render.
The engine is stateless: it holds no DB, no network and no domain logic.

Phase 2 (T5) adds an internal ``__assets__`` key to the normalized
document so backends can materialise ``envelope.assets`` without
exposing the field to the Jinja2 context. Phase 2 (T6) adds the Typst
backend alongside WeasyPrint. Phase 2 (T8) adds engine-level copies
(``render_options["copies"]``): the envelope is rendered N times with
``copy_number`` / ``copies_total`` injected into the document, and the
resulting PDFs are concatenated. ``copies == 1`` is a no-op wrapper path
so Phase 1 byte-identicality is preserved.

Phase 2 (T8) review-fix also adds engine-level watermark
(``render_options["watermark"]``, default False). When present, the flag
is injected into the normalized document at BOTH the top level and the
inner ``document`` mapping (mirror-copies pattern) so both Jinja2 /
WeasyPrint (``{{ watermark }}``) and Typst (``doc.at("watermark")``)
templates can read it. The flag is omitted from the normalized document
entirely when ``render_options`` does not contain the key, so Phase 1
default behaviour stays byte-identical.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from qm_backends.base import Backend, RenderResult
from qm_backends.typst_backend import TypstBackend
from qm_backends.weasyprint_backend import WeasyPrintBackend

from qm_engine.copies import concatenate_pdfs
from qm_engine.envelope import Envelope
from qm_engine.errors import (
    BackendNotAvailableError,
    RenderFailedError,
    UnsupportedOutputFormatError,
)
from qm_engine.registry import Registry, TemplatePackage

# Reserved key used to thread ``envelope.assets`` into the backend without
# leaking the field into the Jinja2 / Typst template context.
_ASSETS_KEY = "__assets__"

# Render option keys for engine-level copies (TZ-PHASE2-BACKEND-SPIKE §T8).
_COPIES_KEY = "copies"

# Default copy count when ``render_options.copies`` is not provided.
_DEFAULT_COPIES = 1

# Minimum allowed copies value. ``copies < 1`` is rejected with
# ``RenderFailedError`` (TZ-PHASE2-BACKEND-SPIKE §5 invariant 6 — no new
# error codes in Phase 2, so we reuse the existing RENDER_FAILED class).
_MIN_COPIES = 1

# Output formats for which copies are supported. PNG returns a single
# raster (page 1), so multi-copy is meaningless — the engine rejects the
# combination explicitly (TZ-PHASE2-BACKEND-SPIKE §T8).
_COPIES_SUPPORTED_FORMATS = frozenset({"pdf"})

# Render option key for engine-level watermark (TZ-PHASE2-BACKEND-SPIKE §T8,
# review note #1). Default behaviour (key absent) is a no-op so Phase 1
# callers see byte-identical output.
_WATERMARK_KEY = "watermark"

_BACKENDS: dict[str, Backend] = {
    "weasyprint": WeasyPrintBackend(),
    "typst": TypstBackend(),
}


def get_backend(name: str) -> Backend:
    backend = _BACKENDS.get(name)
    if backend is None:
        raise BackendNotAvailableError(
            f"Backend '{name}' is not available in this engine",
            {"backend": name, "available": sorted(_BACKENDS)},
        )
    return backend


def render_envelope(
    envelope: Envelope,
    templates_root: Path,
    output_format: str = "pdf",
    render_options: dict[str, Any] | None = None,
) -> RenderResult:
    """Orchestrate envelope → registry → backend → artifact.

    The ``render_options.copies`` key (default 1) controls engine-level
    copies (TZ-PHASE2-BACKEND-SPIKE §T8). When ``copies == 1`` the call
    is byte-identical to Phase 1 — no extra fields are injected into
    the document and no concatenation is performed. When ``copies > 1``
    the backend is called ``copies`` times with ``copy_number`` /
    ``copies_total`` injected into the document each time, and the
    resulting PDFs are concatenated via pypdf.

    The ``render_options.watermark`` key (bool, optional) controls
    engine-level watermark (TZ-PHASE2-BACKEND-SPIKE §T8 review note
    #1). When present, the boolean is injected at both the top level
    of the normalized document and inside the inner ``document``
    mapping so both Jinja2/WeasyPrint and Typst templates can read
    it. When the key is absent the field is not added at all, so the
    Phase 1 default path stays byte-identical.
    """
    opts = render_options or {}
    copies_raw = opts.get(_COPIES_KEY, _DEFAULT_COPIES)
    try:
        copies = int(copies_raw)
    except (TypeError, ValueError) as exc:
        raise RenderFailedError(
            f"Invalid copies value: {copies_raw!r}",
            {"copies": copies_raw, "min": _MIN_COPIES},
        ) from exc
    if copies < _MIN_COPIES:
        raise RenderFailedError(
            f"copies must be >= {_MIN_COPIES}, got {copies}",
            {"copies": copies, "min": _MIN_COPIES},
        )
    if copies > 1 and output_format not in _COPIES_SUPPORTED_FORMATS:
        raise UnsupportedOutputFormatError(
            f"copies > 1 is only supported for PDF output, got '{output_format}'",
            {
                "output_format": output_format,
                "supported_with_copies": sorted(_COPIES_SUPPORTED_FORMATS),
            },
        )

    watermark = _resolve_watermark(opts)

    registry = Registry(templates_root)
    package = registry.lookup(envelope.template_id, envelope.template_version)
    registry.check_contract(package, envelope.document_contract)

    backend = get_backend(package.backend)
    if not backend.available():
        raise BackendNotAvailableError(
            f"Backend '{package.backend}' is not available",
            {
                "backend": package.backend,
                "template": f"{envelope.template_id}@{envelope.template_version}",
            },
        )

    base_document = dict(envelope.data)
    base_document[_ASSETS_KEY] = dict(envelope.assets or {})
    if watermark is not None:
        _inject_watermark(base_document, watermark)

    if copies == 1:
        return backend.render(
            normalized_document=base_document,
            template_package=package,
            output_format=output_format,
            render_options=opts,
        )

    return _render_copies(
        base_document=base_document,
        backend=backend,
        package=package,
        output_format=output_format,
        render_options=opts,
        copies=copies,
    )


def _render_copies(
    base_document: dict[str, Any],
    backend: Backend,
    package: TemplatePackage,
    output_format: str,
    render_options: dict[str, Any],
    copies: int,
) -> RenderResult:
    """Render the document ``copies`` times and concatenate the PDFs.

    Each per-copy render receives a deep copy of ``base_document`` (so a
    backend that mutates the input dict, e.g. WeasyPrint popping the
    internal ``__assets__`` key, doesn't leak state between calls). The
    template sees ``copy_number`` and ``copies_total`` and can print a
    banner such as "Экземпляр 1 из 2".

    The copy fields are exposed at two levels so both backends can find
    them: at the top level of the normalized document (Jinja2 / WeasyPrint
    template access via ``{{ copy_number }}``) and inside the inner
    ``document`` mapping (Typst template access via
    ``json("document.json").at("copy_number", default: 0)``).
    """
    blobs: list[bytes] = []
    page_counts: list[int | None] = []
    warnings: list[str] = []
    for i in range(1, copies + 1):
        per_copy_doc = deepcopy(base_document)
        per_copy_doc["copy_number"] = i
        per_copy_doc["copies_total"] = copies
        inner = per_copy_doc.get("document")
        if isinstance(inner, dict):
            inner = dict(inner)
            inner["copy_number"] = i
            inner["copies_total"] = copies
            per_copy_doc["document"] = inner
        result = backend.render(
            normalized_document=per_copy_doc,
            template_package=package,
            output_format=output_format,
            render_options=render_options,
        )
        blobs.append(result.data)
        page_counts.append(result.page_count)
        warnings.extend(result.warnings)

    concatenated = concatenate_pdfs(blobs)
    if any(pc is None for pc in page_counts):
        total_pages: int | None = None
    else:
        total_pages = sum(pc for pc in page_counts if pc is not None)
    return RenderResult(
        data=concatenated,
        format=output_format,
        page_count=total_pages,
        warnings=warnings,
    )


def inspect_template(
    templates_root: Path,
    template_id: str,
    version: str,
) -> TemplatePackage:
    """Resolve a template package and return it for inspection."""
    return Registry(templates_root).lookup(template_id, version)


def _resolve_watermark(opts: dict[str, Any]) -> bool | None:
    """Validate and return the watermark flag from ``render_options``.

    Returns ``None`` when the key is absent (Phase 1 byte-identical
    no-op), the boolean value when present. Raises ``RenderFailedError``
    when the value is not a ``bool``.
    """
    if _WATERMARK_KEY not in opts:
        return None
    value = opts[_WATERMARK_KEY]
    if not isinstance(value, bool):
        raise RenderFailedError(
            f"Invalid watermark value: {value!r}; must be a bool",
            {"watermark": value, "type": type(value).__name__},
        )
    return value


def _inject_watermark(document: dict[str, Any], watermark: bool) -> None:
    """Inject the watermark flag at the top level and into inner ``document``.

    Mirrors the copies injection pattern (``copy_number`` /
    ``copies_total``) so both Jinja2/WeasyPrint (``{{ watermark }}``)
    and Typst (``doc.at("watermark", default: false)``) templates can
    read it from a single engine-level flag. Mutates ``document`` in
    place; the inner ``document`` mapping is replaced with a shallow
    copy if present to avoid mutating shared envelope state.
    """
    document[_WATERMARK_KEY] = watermark
    inner = document.get("document")
    if isinstance(inner, dict):
        inner = dict(inner)
        inner[_WATERMARK_KEY] = watermark
        document["document"] = inner
