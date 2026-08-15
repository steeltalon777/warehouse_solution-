"""Unit tests for ``qm_engine.assets`` (TZ-PHASE2-BACKEND-SPIKE §8 T5).

Pure-Python tests; no real binary required. Cover name validation, MIME
validation, base64 decoding, the empty-dict fast path, and the public
``read_envelope_assets`` wrapper.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import pytest
from qm_engine import assets as engine_assets
from qm_engine.errors import AssetNotAvailableError


def _png_payload() -> bytes:
    # Minimal valid 1x1 PNG.
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGMAAQAAAAUA"
        "AQ0KLbQAAAAASUVORK5CYII="
    )


def _png_asset_dict() -> bytes:
    return base64.b64encode(_png_payload())


def _asset(name: str = "qr") -> dict[str, Any]:
    return {"mime": "image/png", "data_base64": _png_asset_dict().decode("ascii")}


def test_materialise_assets_writes_files(tmp_path: Path) -> None:
    """Two well-formed assets decode and persist with the right extensions."""
    assets = {
        "qr": _asset("qr"),
        "logo": {"mime": "image/svg+xml", "data_base64": _png_asset_dict().decode("ascii")},
    }
    written = engine_assets.materialise_assets(assets, tmp_path)
    assert set(written) == {"qr", "logo"}
    assert (tmp_path / "qr.png").is_file()
    assert (tmp_path / "logo.svg").is_file()
    assert (tmp_path / "qr.png").read_bytes() == _png_payload()
    assert (tmp_path / "logo.svg").read_bytes() == _png_payload()


def test_materialise_assets_rejects_invalid_name(tmp_path: Path) -> None:
    """Names outside ``^[a-z0-9_-]+$`` are rejected with ``AssetNotAvailableError``."""
    for bad in ("../etc/passwd", "with spaces", "UPPER", "a.b", "a/b", ""):
        with pytest.raises(AssetNotAvailableError) as exc:
            engine_assets.materialise_assets({bad: _asset()}, tmp_path)
        assert exc.value.code == "ASSET_NOT_AVAILABLE"
        assert exc.value.exit_code == 4
        assert exc.value.details.get("name") == bad


def test_materialise_assets_rejects_bad_base64(tmp_path: Path) -> None:
    """A non-base64 ``data_base64`` raises ``AssetNotAvailableError``."""
    bad = _asset()
    bad["data_base64"] = "not-base64!"
    with pytest.raises(AssetNotAvailableError) as exc:
        engine_assets.materialise_assets({"qr": bad}, tmp_path)
    assert exc.value.code == "ASSET_NOT_AVAILABLE"
    assert exc.value.details.get("name") == "qr"
    assert "cause" in exc.value.details


def test_materialise_assets_rejects_empty_payload(tmp_path: Path) -> None:
    """Empty ``mime``/``data_base64`` raise with the offending field name."""
    for missing in ("mime", "data_base64"):
        bad = _asset()
        bad[missing] = ""
        with pytest.raises(AssetNotAvailableError) as exc:
            engine_assets.materialise_assets({"qr": bad}, tmp_path)
        assert exc.value.code == "ASSET_NOT_AVAILABLE"


def test_materialise_assets_rejects_non_mapping_entry(tmp_path: Path) -> None:
    """Entries that are not mappings raise with a clear error."""
    with pytest.raises(AssetNotAvailableError):
        engine_assets.materialise_assets({"qr": "raw-string"}, tmp_path)


def test_materialise_assets_ignores_empty(tmp_path: Path) -> None:
    """Empty input → empty output; no files written."""
    written = engine_assets.materialise_assets({}, tmp_path)
    assert written == {}
    assert list(tmp_path.iterdir()) == []


def test_read_envelope_assets_returns_empty_default() -> None:
    """An envelope without ``assets`` returns ``{}``."""

    class _Env:
        assets = None

    assert engine_assets.read_envelope_assets(_Env()) == {}


def test_read_envelope_assets_returns_mapping() -> None:
    """A plain mapping on the envelope is returned unchanged."""

    class _Env:
        assets = {"qr": _asset()}

    out = engine_assets.read_envelope_assets(_Env())
    assert set(out) == {"qr"}


def test_read_envelope_assets_rejects_non_mapping() -> None:
    """A non-mapping ``assets`` attribute is rejected."""

    class _Env:
        assets = ["not", "a", "mapping"]

    with pytest.raises(AssetNotAvailableError):
        engine_assets.read_envelope_assets(_Env())
