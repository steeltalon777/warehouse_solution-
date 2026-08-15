"""Envelope asset materialisation (TZ-PHASE2-BACKEND-SPIKE §8 T5).

Envelope payloads may carry an ``assets`` mapping of base64-encoded
binary blobs (typically PNG/SVG for QR codes, barcodes, signature scans).
Backends receive the parsed envelope, materialise each asset into a
temporary directory, and reference it from the template by its name
(``<img src="qr.png">`` for WeasyPrint, ``#image("qr.png")`` for Typst).

The materialiser is deliberately strict:

- Asset names must match ``^[a-z0-9_-]+$`` so they can be embedded in a
  URL without escaping. Any other character is rejected with
  :class:`AssetNotAvailableError` (exit 4).
- ``mime`` and ``data_base64`` must be non-empty strings; base64 decoding
  errors are surfaced with the same exit code.

The materialised directory is created inside a caller-owned
:class:`tempfile.TemporaryDirectory` so cleanup is automatic when the
render finishes (TZ §12).
"""

from __future__ import annotations

import base64
import binascii
import io
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from qm_engine.errors import AssetNotAvailableError

# Asset names are used as relative URLs in the template, so we restrict
# the charset to ``[a-z0-9_-]`` only. No uppercase (CSS/URL case
# sensitivity), no dots (no extension guessing), no slashes (no
# traversal).
_NAME_RE = re.compile(r"^[a-z0-9_-]+$")

# Tiny lookup table mapping MIME types to the file extension the file is
# written with.  Unknown MIME types fall back to ``.bin``; the materialiser
# does not validate the MIME match (the producer is responsible).
_MIME_TO_EXT: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/svg+xml": ".svg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "application/pdf": ".pdf",
}


def _extension_for(mime: str) -> str:
    return _MIME_TO_EXT.get(mime.lower(), ".bin")


def _decode_base64(name: str, payload: str) -> bytes:
    try:
        return base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise AssetNotAvailableError(
            f"Asset '{name}' has invalid base64 payload",
            {"name": name, "cause": str(exc)},
        ) from exc


def materialise_assets(assets: Mapping[str, Any], dest: Path) -> dict[str, Path]:
    """Decode every entry of ``assets`` into ``dest`` and return a name→Path map.

    The caller owns ``dest`` (typically a :class:`tempfile.TemporaryDirectory`
    member); this function only writes files. On any failure it raises
    :class:`AssetNotAvailableError` and does **not** clean up partial files
    — the caller discards the whole directory.
    """
    if not isinstance(assets, Mapping):
        raise AssetNotAvailableError(
            "Envelope 'assets' must be a mapping",
            {"got_type": type(assets).__name__},
        )

    dest.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}

    for name, entry in assets.items():
        if not isinstance(name, str) or not _NAME_RE.match(name):
            raise AssetNotAvailableError(
                f"Asset name '{name}' is invalid; must match ^[a-z0-9_-]+$",
                {"name": name},
            )
        if not isinstance(entry, Mapping):
            raise AssetNotAvailableError(
                f"Asset '{name}' must be a mapping with 'mime' and 'data_base64'",
                {"name": name, "got_type": type(entry).__name__},
            )

        mime = entry.get("mime")
        if not isinstance(mime, str) or not mime:
            raise AssetNotAvailableError(
                f"Asset '{name}' is missing a non-empty 'mime'",
                {"name": name},
            )

        data_b64 = entry.get("data_base64")
        if not isinstance(data_b64, str) or not data_b64:
            raise AssetNotAvailableError(
                f"Asset '{name}' is missing a non-empty 'data_base64'",
                {"name": name},
            )

        raw = _decode_base64(name, data_b64)
        if not raw:
            raise AssetNotAvailableError(
                f"Asset '{name}' decoded to zero bytes",
                {"name": name},
            )

        target = dest / f"{name}{_extension_for(mime)}"
        target.write_bytes(raw)
        written[name] = target

    return written


def read_envelope_assets(envelope: Any) -> Mapping[str, Any]:
    """Return ``envelope.assets`` as a plain mapping, defaulting to ``{}``."""
    assets = getattr(envelope, "assets", None)
    if assets is None:
        return {}
    if not isinstance(assets, Mapping):
        raise AssetNotAvailableError(
            "Envelope 'assets' must be a mapping",
            {"got_type": type(assets).__name__},
        )
    return assets


def make_qr_png(text: str) -> bytes:
    """Return PNG bytes for a QR code encoding ``text``.

    Producer-side helper (TZ §8 T5). Raises
    :class:`AssetNotAvailableError` if the optional ``segno`` package is
    not installed.
    """
    try:
        import segno
    except ImportError as exc:
        raise AssetNotAvailableError(
            "segno is required to generate QR codes; install [spike] extra",
            {"missing": "segno"},
        ) from exc

    qr = segno.make(text, error="M")
    buf = io.BytesIO()
    qr.save(buf, kind="png", scale=4)
    return buf.getvalue()


def make_code128_png(text: str) -> bytes:
    """Return PNG bytes for a Code 128 barcode encoding ``text``.

    Producer-side helper (TZ §8 T5). Raises
    :class:`AssetNotAvailableError` if the optional ``python-barcode``
    package is not installed.
    """
    try:
        import barcode  # type: ignore[import-untyped]
        from barcode.writer import ImageWriter  # type: ignore[import-untyped]
    except ImportError as exc:
        raise AssetNotAvailableError(
            "python-barcode is required to generate Code 128 barcodes; install [spike] extra",
            {"missing": "python-barcode"},
        ) from exc

    code = barcode.get("code128", text, writer=ImageWriter())
    buf = io.BytesIO()
    code.write(buf, options={"module_height": 8.0, "module_width": 0.2, "quiet_zone": 2.0})
    return buf.getvalue()
