"""Bundled font manifest and integrity checks (TZ-PHASE2-BACKEND-SPIKE §8 T4).

The engine ships its own DejaVu Sans files at ``<bundle>/fonts/`` (see
``paths.fonts_dir()``). Rendering backends must call
:meth:`ensure_bundled_fonts` before producing output: it loads
``manifest.json``, verifies every file is present and that its SHA-256
matches the pinned value. Any failure raises
``FontNotAvailableError`` (exit code 4, code ``FONT_NOT_AVAILABLE``),
per TZ-PHASE2-BACKEND-SPIKE §12 (no silent fallback to a system font).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

from qm_engine.errors import FontNotAvailableError

from . import paths

# Re-exported for convenience so call sites can write
# ``qm_engine.fonts.fonts_dir()`` without importing ``paths``.
fonts_dir = paths.fonts_dir

# Pinned default font family. Used by both backends and by future
# manifest-driven font selection.
DEFAULT_FONT_FAMILY = "DejaVu Sans"

# Regular / Bold / Oblique / BoldOblique — the four required files for
# baseline waybill rendering. All four must be present even if a caller
# only declares a subset in the template manifest.
REQUIRED_FONT_FILES: tuple[str, ...] = (
    "DejaVuSans.ttf",
    "DejaVuSans-Bold.ttf",
    "DejaVuSans-Oblique.ttf",
    "DejaVuSans-BoldOblique.ttf",
)


def _manifest_path() -> Path:
    return fonts_dir() / "manifest.json"


def load_manifest() -> dict[str, Any]:
    """Read and parse ``fonts/manifest.json``.

    Returns the parsed mapping. Raises ``FontNotAvailableError`` if the
    manifest is missing or malformed.
    """
    path = _manifest_path()
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise FontNotAvailableError(
            f"Fonts manifest not found at {path}",
            {"path": str(path)},
        ) from exc
    except OSError as exc:
        raise FontNotAvailableError(
            f"Unable to read fonts manifest at {path}: {exc}",
            {"path": str(path)},
        ) from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FontNotAvailableError(
            f"Fonts manifest at {path} is not valid JSON: {exc.msg}",
            {"path": str(path), "line": exc.lineno, "column": exc.colno},
        ) from exc

    if not isinstance(data, dict):
        raise FontNotAvailableError(
            f"Fonts manifest at {path} must be a JSON object",
            {"path": str(path)},
        )
    return cast(dict[str, Any], data)


def _expected_hash(file_entry: dict[str, Any]) -> str:
    """Return the lowercase hex SHA-256 declared in a manifest file entry."""
    raw = file_entry.get("sha256")
    if not isinstance(raw, str) or not raw:
        raise FontNotAvailableError(
            "Manifest file entry is missing 'sha256'",
            {"file": file_entry.get("name")},
        )
    return raw.lower()


def _sha256_of(path: Path) -> str:
    """Return the lower-case hex SHA-256 of a file's bytes."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest().lower()


def verify_manifest(manifest: dict[str, Any]) -> None:
    """Verify that every file in ``manifest["files"]`` exists and matches.

    Raises :class:`FontNotAvailableError` with rich ``details`` on failure
    so the CLI can surface which file is missing or contradicts the
    pinned hash. The error is **not** swallowed; backends must propagate
    it so the renderer exits with code 4 instead of falling back to a
    system font (TZ-PHASE2-BACKEND-SPIKE §12, §8 T4).
    """
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise FontNotAvailableError(
            "Fonts manifest has no 'files' list",
            {"manifest_keys": sorted(manifest.keys())},
        )

    missing: list[str] = []
    mismatches: list[dict[str, str]] = []
    root = fonts_dir()

    for entry in files:
        if not isinstance(entry, dict):
            raise FontNotAvailableError(
                "Manifest file entry must be an object",
                {"entry": repr(entry)},
            )
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            raise FontNotAvailableError(
                "Manifest file entry is missing 'name'",
                {"entry": repr(entry)},
            )

        path = root / name
        if not path.is_file():
            missing.append(name)
            continue

        expected = _expected_hash(entry)
        actual = _sha256_of(path)
        if actual != expected:
            mismatches.append({"name": name, "expected": expected, "actual": actual})

    # T4 also requires the four canonical files to exist, regardless of
    # what the manifest lists. This protects against a manifest that
    # accidentally drops a required variant.
    for required_name in REQUIRED_FONT_FILES:
        if not (root / required_name).is_file() and required_name not in missing:
            missing.append(required_name)

    if missing or mismatches:
        details: dict[str, Any] = {}
        if missing:
            details["missing"] = sorted(set(missing))
        if mismatches:
            details["mismatch"] = mismatches
        raise FontNotAvailableError(
            "Bundled fonts are missing or corrupted; see details",
            details,
        )


def ensure_bundled_fonts() -> dict[str, Any]:
    """Top-level guard: load + verify the bundled font manifest.

    Backends must call this at the very start of any render that emits
    text. Returns the manifest dict so callers can inspect the declared
    family / files without re-reading the file.
    """
    manifest = load_manifest()
    verify_manifest(manifest)
    return manifest
