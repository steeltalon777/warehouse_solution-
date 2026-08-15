"""Internal helpers for the harness modules.

This module hides the pytest collection boundary: ``tests/harness/`` is
on the test path, so anything that imports :mod:`tests.harness.compare`
triggers CLI registration. The helper utilities below are deliberately
plain (no CLI decorators, no heavy imports) so the rest of the harness
can be imported freely from test code.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qm_engine import paths as engine_paths

RASTER_DPI: int = 150


# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------

# Map a fixture stem (e.g. "waybill-20", "vehicle-route-sheet-1",
# "fuel-report-100") to the source fixture directory + document family.
FIXTURE_FAMILIES: dict[str, str] = {
    "waybill": "waybill",
    "vehicle-route-sheet": "route-sheet",
    "fuel-report": "fuel",
}


def detect_family(fixture_name: str) -> str:
    """Return the fixture family ("waybill", "route-sheet", "fuel").

    Detection is by longest prefix match against
    :data:`FIXTURE_FAMILIES`. Raises ``ValueError`` when the name is
    not recognised — that is the same behaviour as the structural
    checker and the report writer.
    """
    for prefix, family in FIXTURE_FAMILIES.items():
        if fixture_name.startswith(prefix):
            return family
    raise ValueError(f"Unknown fixture family: {fixture_name}")


def fixture_paths(fixture_name: str, repo_root: Path) -> tuple[Path, Path]:
    """Return the absolute (weasy, typst) fixture paths for a name.

    The harness assumes one weasy and one typst fixture per logical
    document, both located under ``tests/fixtures/<family>/``. The
    family is detected via :func:`detect_family`.
    """
    family = detect_family(fixture_name)
    fixture_dir = repo_root / "tests" / "fixtures" / family
    weasy = fixture_dir / f"{fixture_name}.weasy.json"
    typst = fixture_dir / f"{fixture_name}.typst.json"
    return weasy, typst


def resolve_templates_dir(flag: str | None) -> Path:
    """Resolve the templates directory (flag > env > bundle default).

    Mirrors the CLI precedence in ``cli/qm_cli/main.py``: an explicit
    flag wins, then ``QM_TEMPLATES_DIR``, then the bundle default.
    """
    if flag:
        return Path(flag).resolve()
    resolved: Path = engine_paths.default_templates_dir()
    return resolved


# ---------------------------------------------------------------------------
# Subprocess render helper
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RenderOutcome:
    """Result of a single ``qm-render`` invocation."""

    success: bool
    output_path: Path
    stderr: str = ""
    returncode: int = 0


def render_pdf(
    fixture_path: Path,
    output_path: Path,
    templates_dir: Path,
    timeout: int = 600,
) -> RenderOutcome:
    """Render a single envelope to PDF via the qm-render CLI.

    The CLI is invoked as a subprocess so the harness remains a true
    black-box observer of the engine. The fixture's envelope already
    pins ``template_id`` and ``template_version``; this function does
    not select a backend explicitly.

    Parameters
    ----------
    fixture_path:
        Absolute path to the envelope JSON.
    output_path:
        Where the PDF will be written (also absolute).
    templates_dir:
        ``--templates-dir`` value to pass through.
    timeout:
        Subprocess timeout in seconds. Default 600 because the
        1500-row fuel Typst render comfortably fits inside.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    # Use ``qm_cli.main`` instead of ``qm_cli`` because the package
    # does not ship a ``__main__.py``; ``main.py`` exposes the
    # click group via ``if __name__ == "__main__": main()``.
    # ``--templates-dir`` is a group-level option in click, so it
    # must appear before the subcommand name.
    cmd = [
        sys.executable,
        "-m",
        "qm_cli.main",
        "--templates-dir",
        str(templates_dir),
        "render",
        "--input",
        str(fixture_path),
        "--output",
        str(output_path),
        "--format",
        "pdf",
    ]
    env = dict(os.environ)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            env=env,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return RenderOutcome(
            success=False,
            output_path=output_path,
            stderr=f"render timed out after {timeout}s: {exc}",
            returncode=-1,
        )

    stderr_text = result.stderr.decode("utf-8", errors="replace")
    if result.returncode != 0 or not output_path.exists():
        return RenderOutcome(
            success=False,
            output_path=output_path,
            stderr=stderr_text,
            returncode=result.returncode,
        )
    return RenderOutcome(
        success=True,
        output_path=output_path,
        stderr=stderr_text,
        returncode=result.returncode,
    )


# ---------------------------------------------------------------------------
# Per-family regex helpers
# ---------------------------------------------------------------------------


# Footer pattern: "Лист N из M" (Typst) or "Страница N из M" (WeasyPrint).
# Used both for the structural block check and as a hint to skip
# matched numbers that are actually page-of-total counters.
FOOTER_PATTERN = re.compile(r"(?:Лист|Страница)\s+\d+\s+из\s+\d+", re.IGNORECASE)

# Row pattern: a sequence of digits followed by a non-digit token on
# a subsequent line. This is intentionally permissive — it matches
# both WeasyPrint and Typst folded layouts, regardless of whether the
# next column is a Cyrillic name (waybill) or a date/datetime (route
# sheet, fuel report). The footer substring is stripped first so the
# page-of-total counter (``Лист 1 из 1``) is not counted as a row.
ROW_PATTERN = re.compile(
    r"(?:^|\n)\s*(\d{1,4})\s*\n\s*[^\d\n\-]",
    re.MULTILINE,
)

# Typst enum+1 artefact: ``#idx + 1`` renders as the literal text
# ``<idx> + 1`` in the typst-maintained templates. Row numbers
# following that pattern are still detected via :func:`count_expected_rows`.
TYPST_ENUM_ARTIFACT = re.compile(r"\b(\d{1,4})\s*\+\s*1\b")


def count_expected_rows(page_texts: list[str], expected: int) -> int:
    """Count distinct row numbers in 1..expected that appear in the text.

    More robust than a single regex because the two backends lay
    out tables differently: WeasyPrint puts the row number on its
    own line above the next column; Typst sometimes renders the
    counter as ``idx + 1`` inline. Counting how many of the expected
    numbers (1..N) actually appear in the text handles both layouts
    and gracefully tolerates layout drift in long tables.
    """
    if expected <= 0:
        return 0
    if expected > 5000:
        # Cap the search to avoid pathological scans on huge inputs.
        expected = 5000
    joined = "\n".join(page_texts)
    cleaned = strip_footer(joined)
    found = 0
    for n in range(1, expected + 1):
        # Word-boundary match so "10" does not match "100".
        if re.search(rf"(?:^|\b){n}(?:\b|\s|$)", cleaned):
            found += 1
    return found


def strip_footer(text: str) -> str:
    """Remove ``Лист N из M`` / ``Страница N из M`` substrings from text.

    The harness needs to count data rows, not page-of-total markers.
    Removing the footer substring before counting makes the regex
    robust against backend layouts that differ in the footer wording.
    """
    return FOOTER_PATTERN.sub("", text)


def format_float(value: float, decimals: int = 2) -> str:
    """Format a float in a backend-friendly way.

    Russian fixtures use a comma as the decimal separator in the
    rendered output, but the JSON envelope uses a dot. The semantic
    checker accepts both forms.
    """
    formatted = f"{value:.{decimals}f}"
    return formatted


def safe_load_json(path: Path) -> dict[str, Any]:
    """Load JSON from ``path`` with a single error boundary."""
    loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return loaded
