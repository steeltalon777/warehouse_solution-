"""Unit tests for the bundled fonts manifest and integrity checks.

Pure Python tests — no WeasyPrint render. Cover the public surface of
``qm_engine.fonts``: directory layout, manifest loading, SHA-256
verification, and the failure modes that must raise
``FontNotAvailableError`` (TZ-PHASE2-BACKEND-SPIKE §8 T4).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from qm_engine import errors
from qm_engine import fonts as engine_fonts

REPO = Path(__file__).resolve().parents[2]
FONTS_DIR = REPO / "fonts"


def test_fonts_dir_exists() -> None:
    """The bundled ``fonts/`` directory must exist on disk."""
    assert engine_fonts.fonts_dir().is_dir()
    assert engine_fonts.fonts_dir() == FONTS_DIR


def test_manifest_loads() -> None:
    """``load_manifest`` returns a dict with the four required TTF files."""
    manifest = engine_fonts.load_manifest()
    assert isinstance(manifest, dict)
    files = manifest.get("files")
    assert isinstance(files, list)
    names = {entry["name"] for entry in files}
    assert names == {
        "DejaVuSans.ttf",
        "DejaVuSans-Bold.ttf",
        "DejaVuSans-Oblique.ttf",
        "DejaVuSans-BoldOblique.ttf",
    }
    for entry in files:
        assert isinstance(entry.get("sha256"), str)
        assert len(entry["sha256"]) == 64


def test_manifest_sha256_matches() -> None:
    """``verify_manifest`` passes against the shipped files."""
    manifest = engine_fonts.load_manifest()
    engine_fonts.verify_manifest(manifest)
    # ensure_bundled_fonts returns the manifest and is the top-level guard.
    assert engine_fonts.ensure_bundled_fonts() == manifest


def test_verify_missing_file_raises(tmp_path: Path) -> None:
    """Renaming one TTF out of the bundle triggers ``FontNotAvailableError``."""
    if not FONTS_DIR.is_dir():
        pytest.skip("fonts/ bundle not present in this checkout")

    missing_check = FONTS_DIR / "DejaVuSans.ttf"
    backup_path = FONTS_DIR / "DejaVuSans.ttf.__test_backup"
    try:
        missing_check.rename(backup_path)
        try:
            with pytest.raises(errors.FontNotAvailableError) as exc:
                engine_fonts.ensure_bundled_fonts()
            assert exc.value.code == "FONT_NOT_AVAILABLE"
            assert exc.value.exit_code == 4
            details = exc.value.details
            assert "missing" in details
            assert "DejaVuSans.ttf" in details["missing"]
        finally:
            backup_path.rename(missing_check)
    except OSError as exc:  # pragma: no cover - filesystem-specific
        pytest.skip(f"could not rename font file in this environment: {exc}")


def test_verify_corrupt_sha_raises(tmp_path: Path) -> None:
    """A manifest with a wrong SHA-256 raises ``FontNotAvailableError``."""
    manifest = engine_fonts.load_manifest()
    bad = json.loads(json.dumps(manifest))
    bad["files"] = [dict(entry, sha256="0" * 64) for entry in bad["files"]]
    with pytest.raises(errors.FontNotAvailableError) as exc:
        engine_fonts.verify_manifest(bad)
    assert exc.value.code == "FONT_NOT_AVAILABLE"
    details = exc.value.details
    assert "mismatch" in details
    mismatches = {m["name"] for m in details["mismatch"]}
    assert mismatches == {
        "DejaVuSans.ttf",
        "DejaVuSans-Bold.ttf",
        "DejaVuSans-Oblique.ttf",
        "DejaVuSans-BoldOblique.ttf",
    }


def test_required_files_constant_covers_all_four_variants() -> None:
    """The internal ``REQUIRED_FONT_FILES`` list is the Phase 2 baseline."""
    assert set(engine_fonts.REQUIRED_FONT_FILES) == {
        "DejaVuSans.ttf",
        "DejaVuSans-Bold.ttf",
        "DejaVuSans-Oblique.ttf",
        "DejaVuSans-BoldOblique.ttf",
    }


def test_default_font_family_constant() -> None:
    """Default font family is pinned to ``DejaVu Sans``."""
    assert engine_fonts.DEFAULT_FONT_FAMILY == "DejaVu Sans"
