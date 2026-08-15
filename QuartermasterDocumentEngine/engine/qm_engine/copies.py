"""Engine-level copies helper (TZ-PHASE2-BACKEND-SPIKE §T8).

Pure helpers used by ``engine.qm_engine.render`` to concatenate the per-copy
PDFs produced by a backend into a single document. The engine treats copies
as an outer wrapper around the existing render pipeline — every backend
behaves identically, no backend-specific code is touched.
"""

from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader, PdfWriter


def concatenate_pdfs(blobs: list[bytes]) -> bytes:
    """Concatenate a list of PDF byte blobs into a single PDF.

    Uses pypdf. Empty input returns empty bytes. A single blob is returned
    as-is (no parse, no rewrite) so the output bytes are bit-identical to
    the input.
    """
    if not blobs:
        return b""
    if len(blobs) == 1:
        return blobs[0]
    writer = PdfWriter()
    for blob in blobs:
        reader = PdfReader(BytesIO(blob))
        for page in reader.pages:
            writer.add_page(page)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()
