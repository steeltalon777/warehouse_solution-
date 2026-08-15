"""Visual comparison (TZ §13.4).

The visual layer is **informational** per §13.5 — cross-backend SSIM
and changed-pixel ratios are NOT a hard gate. They are reported as
SSIM/CHANGED-pixel ratios per page, and any mismatch against the
calibrated thresholds is decorated as ``REVIEW_REQUIRED`` in the
report but never flips the overall harness verdict.

Threshold defaults are populated from the calibration step
(``spike-out/calibration/noise_floor.json``). When the calibration
file is missing, the module falls back to the conservative defaults
from §13.5: SSIM ≥ 0.985, changed pixels ≤ 0.005.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tests.harness import raster

# ---------------------------------------------------------------------------
# Defaults from TZ §13.5
# ---------------------------------------------------------------------------

DEFAULT_SSIM_THRESHOLD: float = 0.985
DEFAULT_CHANGED_PIXELS_THRESHOLD: float = 0.005


@dataclass
class VisualThresholds:
    """Advisory thresholds for SSIM and changed pixel ratio."""

    ssim: float = DEFAULT_SSIM_THRESHOLD
    changed_pixels: float = DEFAULT_CHANGED_PIXELS_THRESHOLD

    @classmethod
    def from_noise_floor(cls, path: Path) -> VisualThresholds:
        """Load calibrated thresholds from a noise_floor.json file.

        Missing file or malformed file → :class:`VisualThresholds`
        with the conservative defaults from §13.5.
        """
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls()
        return cls(
            ssim=float(data.get("ssim_threshold", DEFAULT_SSIM_THRESHOLD)),
            changed_pixels=float(
                data.get("changed_pixels_threshold", DEFAULT_CHANGED_PIXELS_THRESHOLD)
            ),
        )


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _compute_changed_pixels(arr_a: Any, arr_b: Any, threshold: int = 32) -> tuple[float, int, int]:
    """Return the (ratio, changed_pixels, total_pixels) at ``threshold``.

    ``threshold`` is the maximum absolute per-channel difference
    accepted as "unchanged". 32 (out of 255) is a forgiving default
    that absorbs JPEG-style compression artefacts even though both
    backends ship real PDF.
    """
    import numpy as np

    a = arr_a.astype(np.int16)
    b = arr_b.astype(np.int16)
    diff = np.abs(a - b)
    channel_max = diff.max(axis=2) if diff.ndim == 3 else diff
    mask = channel_max > threshold
    total = int(mask.size)
    changed = int(mask.sum())
    ratio = changed / total if total else 0.0
    return ratio, changed, total


def compute_ssim(arr_a: Any, arr_b: Any) -> float:
    """Return the SSIM score between two RGB uint8 arrays."""
    from skimage.metrics import structural_similarity

    result: float = float(
        structural_similarity(arr_a, arr_b, channel_axis=2)  # type: ignore[no-untyped-call]
    )
    return result


def resize_to_match(arr_small: Any, arr_large: Any) -> Any:
    """Resize ``arr_small`` to the shape of ``arr_large`` (nearest-neighbour).

    Used when the two backends produce pages of slightly different
    pixel dimensions (e.g. integer rounding of MediaBox → pixels).
    """
    import numpy as np

    h, w = arr_large.shape[:2]
    src_h, src_w = arr_small.shape[:2]
    if src_h == h and src_w == w:
        return arr_small
    row_idx = (np.linspace(0, src_h - 1, h)).astype(np.int64)
    col_idx = (np.linspace(0, src_w - 1, w)).astype(np.int64)
    return arr_small[row_idx][:, col_idx]


# ---------------------------------------------------------------------------
# Public diff + comparison helpers
# ---------------------------------------------------------------------------


def compare_pages(
    pdf_a: Path,
    pdf_b: Path,
    page_index: int,
    pixel_threshold: int = 32,
) -> dict[str, Any]:
    """Compute SSIM and changed pixel ratio for one page index.

    Pages are rasterized at :data:`RASTER_DPI` and aligned by
    nearest-neighbour resize when the two pages disagree in pixel size.
    """
    arr_a = raster.rasterize_page_to_array(pdf_a, page_index)
    arr_b = raster.rasterize_page_to_array(pdf_b, page_index)
    if arr_b.shape != arr_a.shape:
        arr_b = resize_to_match(arr_b, arr_a)
    ssim_score = compute_ssim(arr_a, arr_b)
    ratio, _, _ = _compute_changed_pixels(arr_a, arr_b, threshold=pixel_threshold)
    return {
        "ssim": ssim_score,
        "changed_pixels": ratio,
        "pixel_a_shape": list(arr_a.shape),
        "pixel_b_shape": list(arr_b.shape),
    }


def write_diff_png(
    pdf_a: Path,
    pdf_b: Path,
    page_index: int,
    out_path: Path,
    pixel_threshold: int = 32,
) -> None:
    """Write a diff PNG visualising per-pixel changes.

    Identical pixels are painted white; changed pixels are painted
    red (channel difference > ``pixel_threshold``).
    """
    import numpy as np

    arr_a = raster.rasterize_page_to_array(pdf_a, page_index)
    arr_b = raster.rasterize_page_to_array(pdf_b, page_index)
    if arr_b.shape != arr_a.shape:
        arr_b = resize_to_match(arr_b, arr_a)
    a = arr_a.astype(np.int16)
    b = arr_b.astype(np.int16)
    diff = np.abs(a - b).max(axis=2)
    mask = diff > pixel_threshold
    out = np.full(arr_a.shape, 255, dtype=np.uint8)
    out[mask] = [255, 0, 0]
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Write PNG via PIL (already in the spike extra).
    from PIL import Image

    Image.fromarray(out).save(out_path)


def compare_pdfs(
    pdf_a: Path,
    pdf_b: Path,
    thresholds: VisualThresholds,
) -> dict[str, Any]:
    """Compare the two PDFs page-by-page and assemble the visual report.

    When the page counts differ, only the overlapping pages are
    compared; pages that exist in only one backend get a "page_count_mismatch"
    flag. The overall SSIM/CHANGED-pixel thresholds are advisory
    (§13.5); the function returns a ``review_required`` boolean for
    the entire document but never raises or returns a fatal error.
    """
    import pymupdf  # spike extra, lazy

    doc_a = pymupdf.open(pdf_a)  # type: ignore[no-untyped-call]
    doc_b = pymupdf.open(pdf_b)  # type: ignore[no-untyped-call]
    try:
        pages_a = len(doc_a)
        pages_b = len(doc_b)
        page_count_match = pages_a == pages_b
        common = min(pages_a, pages_b)
    finally:
        doc_a.close()  # type: ignore[no-untyped-call]
        doc_b.close()  # type: ignore[no-untyped-call]

    page_results: dict[str, Any] = {}
    any_review_required = not page_count_match
    for page_idx in range(common):
        result = compare_pages(pdf_a, pdf_b, page_idx)
        ssim_score = result["ssim"]
        changed_ratio = result["changed_pixels"]
        review_required = ssim_score < thresholds.ssim or changed_ratio > thresholds.changed_pixels
        any_review_required = any_review_required or review_required
        page_results[f"page-{page_idx + 1}"] = {
            "ssim": ssim_score,
            "changed_pixels": changed_ratio,
            "review_required": review_required,
            "pixel_a_shape": result["pixel_a_shape"],
            "pixel_b_shape": result["pixel_b_shape"],
        }

    return {
        "page_count_a": pages_a,
        "page_count_b": pages_b,
        "page_count_match": page_count_match,
        "pages_compared": common,
        "thresholds": {
            "ssim": thresholds.ssim,
            "changed_pixels": thresholds.changed_pixels,
        },
        "pages": page_results,
        "review_required": any_review_required,
    }
