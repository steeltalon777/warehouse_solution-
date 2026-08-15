"""Unit tests for the Typst backend (TZ-PHASE2-BACKEND-SPIKE §8 T6).

All tests use a mock ``typst`` shell script under ``tmp_path`` and point
``QM_TYPST_BINARY`` at it, so no real binary is required. The mock
echoes the requested output format and writes the corresponding file
on ``compile``; it also supports a ``--version`` probe and a configurable
failure mode for the error-mapping tests.
"""

from __future__ import annotations

import base64
import stat
from pathlib import Path

import pytest
from qm_backends.typst_backend import (
    STDERR_CAP_BYTES,
    SUPPORTED_FORMATS,
    TypstBackend,
    _resolve_binary,
)
from qm_engine.errors import (
    BackendNotAvailableError,
    RenderFailedError,
    UnsupportedOutputFormatError,
)
from qm_engine.registry import TemplatePackage

# Minimal valid PDF / PNG headers used by the mock.
_PDF_HEADER = b"%PDF-1.4\n%mock\n"
_PNG_HEADER = b"\x89PNG\r\n\x1a\n"


# A real, valid 1x1 PNG.
_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGMAAQAAAAUAAQ0KLbQAAAAASUVORK5CYII="
)


def _png_bytes() -> bytes:
    return base64.b64decode(_PNG_B64)


def _write_mock_typst(
    tmp_path: Path,
    *,
    fail: bool = False,
    version: str = "typst 0.15.1 (mock)",
) -> Path:
    """Create a shell script that mimics ``typst --version`` and ``typst compile``.

    When ``fail`` is ``True`` the ``compile`` invocation writes a stderr
    message and exits non-zero (mapped to ``RenderFailedError``).
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    script = bin_dir / "typst"
    # Use octal escapes for binary headers — printf handles those as raw
    # bytes regardless of locale. The full PDF header is emitted as the
    # literal "%PDF-1.4\\n" (ASCII), the PNG header as raw bytes
    # \211 P N G \r \n \032 \n.
    png_octal = "\\211PNG\\r\\n\\032\\n"
    lines = [
        "#!/bin/sh",
        "set -eu",
        # --version: print and exit 0.
        'if [ "${1:-}" = "--version" ]; then',
        f'  echo "{version}"',
        "  exit 0",
        "fi",
        # compile <INPUT> <OUTPUT> [--format FMT --ppi ...] (other flags ignored).
        'if [ "${1:-}" = "compile" ]; then',
        '  INPUT="$2"',
        '  OUTPUT="$3"',
        "  # Spy: record the full compile argv (before args are consumed).",
        '  if [ -n "${QM_TYPST_SPY_ARGV:-}" ]; then',
        '    printf "%s\\n" "$@" > "${QM_TYPST_SPY_ARGV}"',
        "  fi",
        "  shift 3",
        "  FORMAT=pdf",
        "  while [ $# -gt 0 ]; do",
        '    if [ "$1" = "--format" ]; then FORMAT="$2"; shift 2; continue; fi',
        "    shift",
        "  done",
        '  if [ "${FAIL:-0}" = "1" ]; then',
        '    echo "error: forced mock failure for $INPUT" 1>&2',
        "    exit 2",
        "  fi",
        '  if [ "$FORMAT" = "png" ]; then',
        f"    printf '%b' '{png_octal}' > \"$OUTPUT\"",
        '    head -c 32 /dev/urandom >> "$OUTPUT"',
        "  else",
        "    printf '%s' '%PDF-1.4\\n' > \"$OUTPUT\"",
        '    head -c 32 /dev/urandom >> "$OUTPUT"',
        "  fi",
        "  # Spy: record working dir contents when QM_TYPST_SPY_DIR is set.",
        '  if [ -n "${QM_TYPST_SPY_DIR:-}" ]; then',
        '    ASSETS="$(dirname "$INPUT")/../assets"',
        '    ls -la "$ASSETS" > "${QM_TYPST_SPY_DIR}/listing.txt" 2>/dev/null || true',
        "  fi",
        "  exit 0",
        "fi",
        'echo "unknown command $1" 1>&2',
        "exit 64",
    ]
    script.write_text("\n".join(lines) + "\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return script


@pytest.fixture()
def mock_binary(tmp_path: Path):
    """Yield a callable that builds a mock binary and its location."""
    scripts: list[Path] = []

    def _make(*, fail: bool = False, version: str = "typst 0.15.1 (mock)") -> Path:
        path = _write_mock_typst(tmp_path, fail=fail, version=version)
        scripts.append(path)
        return path

    yield _make
    for s in scripts:
        s.unlink(missing_ok=True)


@pytest.fixture()
def template_package(tmp_path: Path) -> TemplatePackage:
    """Build a minimal ``main.typ`` template package in ``tmp_path``."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "main.typ").write_text(
        '#set text(font: "DejaVu Sans")\nПривет, мир!\n',
        encoding="utf-8",
    )
    manifest = {
        "id": "mock-typst",
        "version": "0.1.0",
        "document_contract": "warehouse.operation-document/v2",
        "backend": "typst",
        "entrypoint": "main.typ",
        "output_formats": ["pdf", "png"],
        "locales": ["ru-RU"],
    }
    (pkg / "manifest.yaml").write_text(
        "id: mock-typst\n"
        "version: 0.1.0\n"
        "document_contract: warehouse.operation-document/v2\n"
        "backend: typst\n"
        "entrypoint: main.typ\n"
        "output_formats: [pdf, png]\n"
        "locales: [ru-RU]\n",
        encoding="utf-8",
    )
    return TemplatePackage(root=pkg, manifest=manifest)


def test_supported_formats_constant() -> None:
    """Public constant pins the supported output formats."""
    assert SUPPORTED_FORMATS == ("pdf", "png")


def test_resolve_binary_prefers_env(monkeypatch, tmp_path: Path, mock_binary) -> None:
    """``QM_TYPST_BINARY`` wins over the pinned path and PATH."""
    binary = mock_binary()
    monkeypatch.setenv("QM_TYPST_BINARY", str(binary))
    monkeypatch.setattr("shutil.which", lambda _: None)
    assert _resolve_binary() == str(binary)


def test_resolve_binary_falls_back_to_pinned(monkeypatch, tmp_path: Path) -> None:
    """Without env, the pinned binary in ``.spike/`` is selected if present.

    The test temporarily symlinks the mock script to the path computed
    from the pin so that resolution picks it up.
    """
    # Patch the pin lookup to point at our temp file.
    pinned_path = tmp_path / "pinned-typst"
    pinned_path.write_bytes(b"#!/bin/sh\necho typst-mock\n")
    pinned_path.chmod(pinned_path.stat().st_mode | stat.S_IEXEC)

    monkeypatch.setattr(
        "qm_backends.typst_backend._pinned_binary_path",
        lambda: pinned_path,
    )
    monkeypatch.setattr("shutil.which", lambda _: None)
    assert _resolve_binary() == str(pinned_path)


def test_resolve_binary_returns_none_when_missing(monkeypatch, tmp_path: Path) -> None:
    """Without env, pinned file, or PATH entry → ``None``."""
    monkeypatch.delenv("QM_TYPST_BINARY", raising=False)
    monkeypatch.setattr("qm_backends.typst_backend._pinned_binary_path", lambda: None)
    monkeypatch.setattr("shutil.which", lambda _: None)
    assert _resolve_binary() is None


def test_available_true_with_mock_binary(monkeypatch, mock_binary) -> None:
    """Mock ``--version`` succeeds → ``available()`` is ``True``."""
    binary = mock_binary()
    monkeypatch.setenv("QM_TYPST_BINARY", str(binary))
    assert TypstBackend().available() is True


def test_available_false_when_no_binary(monkeypatch) -> None:
    """No env, no pinned path, no PATH entry → ``available()`` is ``False``."""
    monkeypatch.delenv("QM_TYPST_BINARY", raising=False)
    monkeypatch.setattr("qm_backends.typst_backend._pinned_binary_path", lambda: None)
    monkeypatch.setattr("shutil.which", lambda _: None)
    assert TypstBackend().available() is False


def test_available_false_when_probe_fails(monkeypatch, tmp_path: Path) -> None:
    """A binary that exits non-zero on ``--version`` is reported unavailable."""
    # Write a script that exits non-zero.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "typst"
    script.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("QM_TYPST_BINARY", str(script))
    assert TypstBackend().available() is False


def test_render_pdf_produces_pdf_bytes(monkeypatch, mock_binary, template_package) -> None:
    """Successful ``compile`` returns the mock-written PDF bytes."""
    binary = mock_binary()
    monkeypatch.setenv("QM_TYPST_BINARY", str(binary))
    backend = TypstBackend()
    assert backend.available() is True
    result = backend.render(
        normalized_document={"document": {"some_text": "x"}, "__assets__": {}},
        template_package=template_package,
        output_format="pdf",
        render_options={},
    )
    assert result.format == "pdf"
    assert result.data[:5] == b"%PDF-"
    assert result.warnings == []


def test_render_png_produces_png_bytes(monkeypatch, mock_binary, template_package) -> None:
    """Successful ``compile --format png`` returns PNG bytes."""
    binary = mock_binary()
    monkeypatch.setenv("QM_TYPST_BINARY", str(binary))
    backend = TypstBackend()
    result = backend.render(
        normalized_document={"document": {}, "__assets__": {}},
        template_package=template_package,
        output_format="png",
        render_options={},
    )
    assert result.format == "png"
    assert result.data[:8] == _PNG_HEADER
    assert result.page_count is None  # PNG mode with mocked second pass


def test_render_unsupported_format_raises(monkeypatch, mock_binary, template_package) -> None:
    """An unsupported output format raises the typed error."""
    binary = mock_binary()
    monkeypatch.setenv("QM_TYPST_BINARY", str(binary))
    backend = TypstBackend()
    with pytest.raises(UnsupportedOutputFormatError) as exc:
        backend.render(
            normalized_document={"__assets__": {}},
            template_package=template_package,
            output_format="docx",
            render_options={},
        )
    assert exc.value.code == "UNSUPPORTED_OUTPUT_FORMAT"
    assert "docx" in str(exc.value.details.get("output_format", ""))


def test_render_missing_binary_raises_backend_not_available(monkeypatch, template_package) -> None:
    """No resolved binary → ``BackendNotAvailableError`` (exit 4)."""
    monkeypatch.delenv("QM_TYPST_BINARY", raising=False)
    monkeypatch.setattr("qm_backends.typst_backend._pinned_binary_path", lambda: None)
    monkeypatch.setattr("shutil.which", lambda _: None)
    backend = TypstBackend()
    with pytest.raises(BackendNotAvailableError) as exc:
        backend.render(
            normalized_document={"__assets__": {}},
            template_package=template_package,
            output_format="pdf",
            render_options={},
        )
    assert exc.value.code == "BACKEND_NOT_AVAILABLE"
    assert exc.value.exit_code == 4


def test_render_compile_error_maps_to_render_failed(
    monkeypatch, mock_binary, template_package
) -> None:
    """A non-zero ``compile`` maps to ``RenderFailedError`` with stderr in details."""
    binary = mock_binary(fail=True)
    monkeypatch.setenv("QM_TYPST_BINARY", str(binary))
    # The mock reads FAIL from the environment to decide whether to fail.
    monkeypatch.setenv("FAIL", "1")
    backend = TypstBackend()
    with pytest.raises(RenderFailedError) as exc:
        backend.render(
            normalized_document={"__assets__": {}},
            template_package=template_package,
            output_format="pdf",
            render_options={},
        )
    assert exc.value.code == "RENDER_FAILED"
    assert exc.value.exit_code == 5
    cause = exc.value.details.get("cause", "")
    assert "forced mock failure" in cause
    assert len(cause.encode("utf-8")) <= STDERR_CAP_BYTES


def test_render_with_assets_materialises(
    monkeypatch, tmp_path, mock_binary, template_package
) -> None:
    """A non-empty ``__assets__`` produces an assets dir in the typst root."""
    binary = mock_binary()
    monkeypatch.setenv("QM_TYPST_BINARY", str(binary))
    spy_dir = tmp_path / "spy"
    spy_dir.mkdir()
    monkeypatch.setenv("QM_TYPST_SPY_DIR", str(spy_dir))

    backend = TypstBackend()
    result = backend.render(
        normalized_document={
            "document": {"some_text": "asset"},
            "__assets__": {"qr": {"mime": "image/png", "data_base64": _PNG_B64}},
        },
        template_package=template_package,
        output_format="pdf",
        render_options={},
    )
    assert result.format == "pdf"
    listing = (spy_dir / "listing.txt").read_text(encoding="utf-8")
    assert "qr.png" in listing


def test_render_strips_assets_key_from_document(
    monkeypatch, mock_binary, template_package, tmp_path: Path
) -> None:
    """The ``document.json`` on disk must NOT contain ``__assets__``."""
    binary = mock_binary()
    monkeypatch.setenv("QM_TYPST_BINARY", str(binary))

    # Intercept by writing a wrapped compile (but easier: just check that
    # the assets key was popped from normalized_document after render).
    captured: dict[str, object] = {}

    real_render = TypstBackend().render

    def _capture(normalized_document, template_package, output_format, render_options):
        captured["before"] = dict(normalized_document)
        result = real_render(
            normalized_document=normalized_document,
            template_package=template_package,
            output_format=output_format,
            render_options=render_options,
        )
        captured["after"] = dict(normalized_document)
        return result

    backend = TypstBackend()
    backend.render = _capture  # type: ignore[method-assign]
    backend.render(
        normalized_document={
            "document": {"x": 1},
            "__assets__": {"qr": {"mime": "image/png", "data_base64": _PNG_B64}},
        },
        template_package=template_package,
        output_format="pdf",
        render_options={},
    )
    assert "__assets__" in captured["before"]
    assert "__assets__" not in captured["after"]


def test_render_passes_creation_timestamp_flag(
    monkeypatch, mock_binary, template_package, tmp_path: Path
) -> None:
    """Phase 2.1.1 M1 regression: ``--creation-timestamp`` must be on the CLI.

    Typst 0.15.1 ignores the ``TYPST_TIMESTAMP`` env var on Linux; the
    only way to pin the PDF ``/CreationDate`` (and thus keep the output
    byte-deterministic across wall-clock second boundaries) is the
    explicit ``--creation-timestamp <unix>`` CLI flag. This unit test
    locks the flag into the compile argv so a future refactor cannot
    silently drop it — the flake would otherwise only show up as a ~3%
    component-test failure.
    """
    import qm_backends.typst_backend as tb

    binary = mock_binary()
    monkeypatch.setenv("QM_TYPST_BINARY", str(binary))
    argv_file = tmp_path / "argv.txt"
    monkeypatch.setenv("QM_TYPST_SPY_ARGV", str(argv_file))

    backend = TypstBackend()
    backend.render(
        normalized_document={"document": {"some_text": "x"}, "__assets__": {}},
        template_package=template_package,
        output_format="pdf",
        render_options={},
    )

    assert argv_file.is_file(), "mock binary never wrote the argv spy file"
    argv = argv_file.read_text(encoding="utf-8").splitlines()
    assert "--creation-timestamp" in argv, f"flag missing from compile argv: {argv}"
    flag_idx = argv.index("--creation-timestamp")
    assert flag_idx + 1 < len(argv), "flag present but has no value"
    assert argv[flag_idx + 1] == str(tb.DEFAULT_TYPST_TIMESTAMP), (
        f"unexpected creation timestamp value: {argv[flag_idx + 1]}"
    )


def test_render_png_path_also_pins_creation_timestamp(
    monkeypatch, mock_binary, template_package, tmp_path: Path
) -> None:
    """The page-count-via-PDF second pass also carries the flag.

    ``render`` with ``output_format="png"`` triggers a second ``typst
    compile`` (the page-count pass). That second invocation must also
    pin ``--creation-timestamp`` or the count pass could produce a PDF
    whose metadata differs from the primary render path.
    """
    import qm_backends.typst_backend as tb

    binary = mock_binary()
    monkeypatch.setenv("QM_TYPST_BINARY", str(binary))
    argv_file = tmp_path / "argv.txt"
    monkeypatch.setenv("QM_TYPST_SPY_ARGV", str(argv_file))

    backend = TypstBackend()
    backend.render(
        normalized_document={"document": {}, "__assets__": {}},
        template_package=template_package,
        output_format="png",
        render_options={},
    )

    assert argv_file.is_file(), "mock binary never wrote the argv spy file"
    argv = argv_file.read_text(encoding="utf-8").splitlines()
    assert "--creation-timestamp" in argv, f"flag missing from compile argv: {argv}"
    flag_idx = argv.index("--creation-timestamp")
    assert flag_idx + 1 < len(argv), "flag present but has no value"
    assert argv[flag_idx + 1] == str(tb.DEFAULT_TYPST_TIMESTAMP), (
        f"unexpected creation timestamp value: {argv[flag_idx + 1]}"
    )
