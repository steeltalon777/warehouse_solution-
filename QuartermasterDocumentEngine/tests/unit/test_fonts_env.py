"""Unit tests for Phase 6A path resolution and the ``QM_FONTS_DIR`` axis.

Covers the resolution contract from ADR-0032 D3/D7 and TZ §6.5/§7.2:

1. ``QM_FONTS_DIR`` / ``QM_TEMPLATES_DIR`` env overrides win over both the
   installed share location and the bundle root.
2. The installed share location (``<sys.prefix>/share/quartermaster_document_engine``)
   is preferred over the bundle root when it exists (pip-installed layout).
3. Without env or share dir the bundle root is the fallback (source tree).
4. A missing/empty resolved fonts dir fails explicitly in
   ``ensure_bundled_fonts`` with ``FontNotAvailableError`` — never a silent
   fallback to system fonts.
5. The Typst backend passes the resolved fonts dir as ``--font-path``.
"""

from __future__ import annotations

import shutil
import stat
import subprocess
from pathlib import Path

import pytest
from qm_backends.typst_backend import TypstBackend
from qm_engine import errors, paths
from qm_engine import fonts as engine_fonts
from qm_engine.registry import TemplatePackage

REPO = Path(__file__).resolve().parents[2]
BUNDLE_FONTS = REPO / "fonts"


@pytest.fixture()
def isolated_share_root(monkeypatch, tmp_path: Path) -> Path:
    """Point ``_INSTALLED_SHARE_ROOT`` at a temp location and clear env vars."""
    share_root = tmp_path / "share" / "quartermaster_document_engine"
    monkeypatch.setattr(paths, "_INSTALLED_SHARE_ROOT", share_root)
    monkeypatch.delenv("QM_FONTS_DIR", raising=False)
    monkeypatch.delenv("QM_TEMPLATES_DIR", raising=False)
    return share_root


# ---------------------------------------------------------------------------
# QM_FONTS_DIR env override
# ---------------------------------------------------------------------------


def test_fonts_dir_from_env_none_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("QM_FONTS_DIR", raising=False)
    assert paths.fonts_dir_from_env() is None


def test_fonts_dir_from_env_resolves_relative_path(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "custom-fonts"
    target.mkdir()
    monkeypatch.setenv("QM_FONTS_DIR", str(target))
    assert paths.fonts_dir_from_env() == target.resolve()


def test_default_fonts_dir_env_override_wins(
    isolated_share_root, monkeypatch, tmp_path: Path
) -> None:
    target = tmp_path / "env-fonts"
    target.mkdir()
    monkeypatch.setenv("QM_FONTS_DIR", str(target))
    # Even a share dir that exists must not beat the env override.
    (isolated_share_root / "fonts").mkdir(parents=True)
    assert paths.default_fonts_dir() == target.resolve()


def test_default_fonts_dir_share_wins_over_bundle(isolated_share_root) -> None:
    share_fonts = isolated_share_root / "fonts"
    share_fonts.mkdir(parents=True)
    assert paths.default_fonts_dir() == share_fonts


def test_default_fonts_dir_bundle_fallback(isolated_share_root) -> None:
    assert paths.default_fonts_dir() == paths._BUNDLE_ROOT / "fonts"
    assert paths.default_fonts_dir().is_dir()


def test_fonts_module_reexports_resolved_dir(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "env-fonts"
    target.mkdir()
    monkeypatch.setenv("QM_FONTS_DIR", str(target))
    # The re-export is the *resolved* function, so backends that call
    # ``engine_fonts.fonts_dir()`` follow the env override automatically.
    assert engine_fonts.fonts_dir is paths.default_fonts_dir
    assert engine_fonts.fonts_dir() == target.resolve()


# ---------------------------------------------------------------------------
# QM_TEMPLATES_DIR env override (parallel mechanism, TZ §6.5)
# ---------------------------------------------------------------------------


def test_default_templates_dir_env_override_wins(
    isolated_share_root, monkeypatch, tmp_path: Path
) -> None:
    target = tmp_path / "env-templates"
    target.mkdir()
    monkeypatch.setenv("QM_TEMPLATES_DIR", str(target))
    (isolated_share_root / "templates").mkdir(parents=True)
    assert paths.default_templates_dir() == target.resolve()


def test_default_templates_dir_share_wins_over_bundle(isolated_share_root) -> None:
    share_templates = isolated_share_root / "templates"
    share_templates.mkdir(parents=True)
    assert paths.default_templates_dir() == share_templates


def test_default_templates_dir_bundle_fallback(isolated_share_root) -> None:
    assert paths.default_templates_dir() == paths.DEFAULT_TEMPLATES_DIR
    assert paths.default_templates_dir().is_dir()


def test_contracts_dir_share_wins_over_bundle(isolated_share_root) -> None:
    share_contracts = isolated_share_root / "contracts"
    share_contracts.mkdir(parents=True)
    assert paths.contracts_dir() == share_contracts


def test_contracts_dir_bundle_fallback(isolated_share_root) -> None:
    assert paths.contracts_dir() == paths._BUNDLE_ROOT / "contracts"


# ---------------------------------------------------------------------------
# Explicit failure on unusable resolved fonts dir (no silent fallback)
# ---------------------------------------------------------------------------


def test_missing_qm_fonts_dir_raises_font_not_available(monkeypatch, tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    monkeypatch.setenv("QM_FONTS_DIR", str(missing))
    with pytest.raises(errors.FontNotAvailableError) as exc:
        engine_fonts.ensure_bundled_fonts()
    assert exc.value.code == "FONT_NOT_AVAILABLE"
    assert exc.value.exit_code == 4
    assert "manifest" in str(exc.value)


def test_empty_qm_fonts_dir_raises_font_not_available(monkeypatch, tmp_path: Path) -> None:
    empty = tmp_path / "empty-fonts"
    empty.mkdir()
    monkeypatch.setenv("QM_FONTS_DIR", str(empty))
    with pytest.raises(errors.FontNotAvailableError) as exc:
        engine_fonts.ensure_bundled_fonts()
    assert exc.value.code == "FONT_NOT_AVAILABLE"
    assert exc.value.exit_code == 4
    assert "manifest" in str(exc.value)


def test_incomplete_qm_fonts_dir_raises_font_not_available(monkeypatch, tmp_path: Path) -> None:
    """A dir with the manifest but a missing TTF still fails explicitly."""
    partial = tmp_path / "partial-fonts"
    partial.mkdir()
    shutil.copy2(BUNDLE_FONTS / "manifest.json", partial / "manifest.json")
    for name in ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans-BoldOblique.ttf"):
        shutil.copy2(BUNDLE_FONTS / name, partial / name)
    # DejaVuSans-Oblique.ttf is deliberately absent.
    monkeypatch.setenv("QM_FONTS_DIR", str(partial))
    with pytest.raises(errors.FontNotAvailableError) as exc:
        engine_fonts.ensure_bundled_fonts()
    assert exc.value.code == "FONT_NOT_AVAILABLE"
    details = exc.value.details
    assert "DejaVuSans-Oblique.ttf" in details["missing"]


# ---------------------------------------------------------------------------
# Typst command line carries the resolved fonts dir as --font-path
# ---------------------------------------------------------------------------


@pytest.fixture()
def typst_template_package(tmp_path: Path) -> TemplatePackage:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "main.typ").write_text(
        '#set text(font: "DejaVu Sans")\nТест\n',
        encoding="utf-8",
    )
    manifest = {
        "id": "mock-typst",
        "version": "0.1.0",
        "document_contract": "warehouse.operation-document/v2",
        "backend": "typst",
        "entrypoint": "main.typ",
        "output_formats": ["pdf"],
        "locales": ["ru-RU"],
    }
    (pkg / "manifest.yaml").write_text(
        "id: mock-typst\nversion: 0.1.0\n"
        "document_contract: warehouse.operation-document/v2\n"
        "backend: typst\nentrypoint: main.typ\n"
        "output_formats: [pdf]\nlocales: [ru-RU]\n",
        encoding="utf-8",
    )
    return TemplatePackage(root=pkg, manifest=manifest)


def _write_mock_typst_binary(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    script = bin_dir / "typst"
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def test_typst_render_passes_resolved_font_path(
    monkeypatch, tmp_path: Path, typst_template_package: TemplatePackage
) -> None:
    """``--font-path`` in the typst argv equals the QM_FONTS_DIR-resolved dir.

    ``ensure_bundled_fonts`` runs before the subprocess and must succeed,
    so the env override points at a full copy of the bundled fonts.
    """
    fonts_copy = tmp_path / "fonts-copy"
    shutil.copytree(BUNDLE_FONTS, fonts_copy)
    monkeypatch.setenv("QM_FONTS_DIR", str(fonts_copy))
    binary = _write_mock_typst_binary(tmp_path)
    monkeypatch.setenv("QM_TYPST_BINARY", str(binary))

    captured: dict[str, list[str]] = {}

    def _fake_run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
        captured["cmd"] = cmd
        out_file = Path(cmd[3])
        out_file.write_bytes(b"%PDF-1.4\nmock\n")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("qm_backends.typst_backend.subprocess.run", _fake_run)

    backend = TypstBackend()
    backend.render(
        normalized_document={"document": {"some_text": "x"}, "__assets__": {}},
        template_package=typst_template_package,
        output_format="pdf",
        render_options={},
    )

    assert "cmd" in captured, "typst subprocess was never invoked"
    cmd = captured["cmd"]
    assert "--font-path" in cmd, f"--font-path missing from typst argv: {cmd}"
    font_path = cmd[cmd.index("--font-path") + 1]
    assert font_path == str(fonts_copy.resolve()), (
        f"expected --font-path {fonts_copy.resolve()}, got {font_path}"
    )
    assert "--ignore-system-fonts" in cmd
