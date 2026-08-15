"""Visual comparison harness for the Quartermaster Document Engine spike.

Stage T9 of TZ-PHASE2-BACKEND-SPIKE (§13). The harness compares PDFs
produced by two backends (WeasyPrint and Typst) for the same envelope,
verifying structural, semantic and visual gates.

Modular layout:

* :mod:`tests.harness.raster` — PyMuPDF rasterization at 150 DPI.
* :mod:`tests.harness.structural` — page count, MediaBox, blocks, table rows.
* :mod:`tests.harness.semantic` — field comparison against the envelope.
* :mod:`tests.harness.visual` — SSIM, changed pixel ratio, diff PNG.
* :mod:`tests.harness.report` — markdown summary.
* :mod:`tests.harness.compare` — CLI entry point + library API.

Heavy spike dependencies (PyMuPDF, scikit-image) are imported lazily
inside the functions that actually need them so that the test suite
remains importable without the ``[spike]`` extra installed.
"""
