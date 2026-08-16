"""Packaging tests for Phase 6A A1 (ADR-0032 D7, TZ §6.5/§9.1).

Verifies that ``pip install`` of the QDE delivers the canonical runtime
resources (fonts, canonical templates, contract schemas) into
``<sys.prefix>/share/quartermaster_document_engine/`` and that
``qm_engine.paths`` resolves them there.

Two levels, both run in the normal ``pytest tests/integration`` invocation:

1. ``pip wheel`` build — the built wheel must contain the fonts, the
   canonical ``warehouse-waybill-ru`` template versions and all contract
   schemas, and must NOT contain spike artifacts, caches, PDFs or tests.
2. ``pip install --no-index --no-deps`` into a throwaway venv (in /tmp via
   pytest's tmp_path_factory) — ``paths.default_fonts_dir()`` /
   ``default_templates_dir()`` / ``contracts_dir()`` must resolve to the
   installed share location and the mandatory files must be present and
   hash-verified by ``ensure_bundled_fonts``.
"""

from __future__ import annotations

import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

# Resource keys that must land in the wheel under the share layout.
WHEEL_REQUIRED_SUBSTRINGS = (
    "share/quartermaster_document_engine/fonts/DejaVuSans.ttf",
    "share/quartermaster_document_engine/fonts/DejaVuSans-Bold.ttf",
    "share/quartermaster_document_engine/fonts/DejaVuSans-Oblique.ttf",
    "share/quartermaster_document_engine/fonts/DejaVuSans-BoldOblique.ttf",
    "share/quartermaster_document_engine/fonts/manifest.json",
    "share/quartermaster_document_engine/fonts/LICENSE",
    "share/quartermaster_document_engine/templates/warehouse-waybill-ru/0.1.0/manifest.yaml",
    "share/quartermaster_document_engine/templates/warehouse-waybill-ru/0.1.0/main.html",
    "share/quartermaster_document_engine/templates/warehouse-waybill-ru/1.0/manifest.yaml",
    "share/quartermaster_document_engine/templates/warehouse-waybill-ru/1.0/main.html",
    "share/quartermaster_document_engine/templates/warehouse-waybill-ru/2.0.0/manifest.yaml",
    "share/quartermaster_document_engine/templates/warehouse-waybill-ru/2.0.0/main.typ",
    "share/quartermaster_document_engine/templates/warehouse-waybill-ru/2.0.0/layout-config.typ",
    "share/quartermaster_document_engine/contracts/envelope/v1/envelope.schema.json",
    "share/quartermaster_document_engine/contracts/warehouse.operation-document/v2/schema.json",
    "share/quartermaster_document_engine/contracts/fuel.monthly-report/v1/schema.json",
    "share/quartermaster_document_engine/contracts/transport.vehicle-route-sheet/v1/schema.json",
)

# Path fragments that must never appear anywhere in the wheel.
WHEEL_FORBIDDEN_FRAGMENTS = (".spike", "spike-out", "spike-", "__pycache__", ".pdf", "tests/")


@pytest.fixture(scope="session")
def built_wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build the project wheel once per test session into /tmp."""
    wheel_dir = tmp_path_factory.mktemp("qde-wheel")
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--no-cache-dir",
            "-w",
            str(wheel_dir),
            str(REPO),
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert proc.returncode == 0, (
        f"pip wheel failed (exit {proc.returncode})\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    wheels = sorted(wheel_dir.glob("*.whl"))
    assert len(wheels) == 1, f"expected exactly one wheel, got {wheels}"
    return wheels[0]


def _wheel_names(wheel: Path) -> list[str]:
    with zipfile.ZipFile(wheel) as zf:
        return zf.namelist()


def _has_substring(names: list[str], substring: str) -> bool:
    return any(substring in name for name in names)


# ---------------------------------------------------------------------------
# Level 1: wheel contents
# ---------------------------------------------------------------------------


def test_wheel_contains_required_resources(built_wheel: Path) -> None:
    names = _wheel_names(built_wheel)
    missing = [sub for sub in WHEEL_REQUIRED_SUBSTRINGS if not _has_substring(names, sub)]
    assert not missing, f"wheel {built_wheel.name} is missing resources: {missing}"


def test_wheel_contains_python_packages(built_wheel: Path) -> None:
    names = _wheel_names(built_wheel)
    assert _has_substring(names, "qm_engine/paths.py")
    assert _has_substring(names, "qm_backends/typst_backend.py")
    assert _has_substring(names, "qm_cli/main.py")
    assert _has_substring(names, "qm_engine/py.typed")


def test_wheel_excludes_spike_caches_pdf_tests(built_wheel: Path) -> None:
    names = _wheel_names(built_wheel)
    for name in names:
        for fragment in WHEEL_FORBIDDEN_FRAGMENTS:
            assert fragment not in name, (
                f"wheel {built_wheel.name} contains forbidden path {name!r} (fragment {fragment!r})"
            )


def test_wheel_excludes_spike_templates_and_assets(built_wheel: Path) -> None:
    names = _wheel_names(built_wheel)
    assert not any("templates/spike" in name for name in names), (
        f"spike templates leaked into wheel: {[n for n in names if 'templates/spike' in n]}"
    )
    assert not any("assets/" in name and ".pdf" in name for name in names)
    assert not any(".git/" in name for name in names)


# ---------------------------------------------------------------------------
# Level 2: install into a throwaway venv and resolve paths
# ---------------------------------------------------------------------------


def _clean_env_without_qm_vars() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if not k.startswith("QM_")}


def test_install_into_venv_resolves_installed_share_paths(
    built_wheel: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    venv_dir = tmp_path_factory.mktemp("qde-install-venv")
    venv_python = venv_dir / "bin" / "python"

    proc = subprocess.run(
        [sys.executable, "-m", "venv", str(venv_dir)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert proc.returncode == 0, f"venv creation failed: {proc.stderr}"

    proc = subprocess.run(
        [
            str(venv_python),
            "-m",
            "pip",
            "install",
            "--no-index",
            "--no-deps",
            str(built_wheel),
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert proc.returncode == 0, f"pip install failed: {proc.stdout}\n{proc.stderr}"

    probe = (
        "import sys\n"
        "from pathlib import Path\n"
        "from qm_engine import paths\n"
        "print(paths.default_fonts_dir())\n"
        "print(paths.default_templates_dir())\n"
        "print(paths.contracts_dir())\n"
        "print(sys.prefix)\n"
    )
    proc = subprocess.run(
        [str(venv_python), "-c", probe],
        capture_output=True,
        text=True,
        timeout=120,
        env=_clean_env_without_qm_vars(),
    )
    assert proc.returncode == 0, f"path probe failed: {proc.stderr}"
    fonts_dir, templates_dir, contracts_dir, prefix = [
        Path(line.strip()) for line in proc.stdout.splitlines()
    ]

    share_root = Path(prefix) / "share" / "quartermaster_document_engine"
    assert fonts_dir == share_root / "fonts", (
        f"default_fonts_dir resolved to {fonts_dir}, expected {share_root / 'fonts'}"
    )
    assert templates_dir == share_root / "templates"
    assert contracts_dir == share_root / "contracts"

    # Mandatory files must be present at the resolved locations.
    for rel in (
        "fonts/DejaVuSans.ttf",
        "fonts/DejaVuSans-Bold.ttf",
        "fonts/DejaVuSans-Oblique.ttf",
        "fonts/DejaVuSans-BoldOblique.ttf",
        "fonts/manifest.json",
        "fonts/LICENSE",
        "templates/warehouse-waybill-ru/0.1.0/manifest.yaml",
        "templates/warehouse-waybill-ru/1.0/manifest.yaml",
        "templates/warehouse-waybill-ru/2.0.0/manifest.yaml",
        "templates/warehouse-waybill-ru/2.0.0/main.typ",
        "templates/warehouse-waybill-ru/2.0.0/layout-config.typ",
        "contracts/envelope/v1/envelope.schema.json",
        "contracts/warehouse.operation-document/v2/schema.json",
    ):
        assert (share_root / rel).is_file(), f"installed resource missing: {rel}"

    # No spike artifacts may leak into the installed share tree.
    installed_names = [str(p.relative_to(share_root)) for p in share_root.rglob("*")]
    for name in installed_names:
        for fragment in ("spike", "__pycache__"):
            assert fragment not in name, f"installed share tree contains {name!r}"

    # The manifest verification must pass against the installed fonts.
    verify = (
        "from qm_engine import fonts\nm = fonts.ensure_bundled_fonts()\nprint(len(m['files']))\n"
    )
    proc = subprocess.run(
        [str(venv_python), "-c", verify],
        capture_output=True,
        text=True,
        timeout=120,
        env=_clean_env_without_qm_vars(),
    )
    assert proc.returncode == 0, (
        f"ensure_bundled_fonts failed against installed fonts: {proc.stderr}"
    )
    assert proc.stdout.strip() == "4"

    # The console script entry point is installed too.
    assert (venv_dir / "bin" / "qm-render").is_file()

    # Phase 6C (TZ §25): the production template package must land in
    # the installed share tree with its runtime files (the registry
    # discovers a template purely by its manifest.yaml location).
    pkg_root = share_root / "templates" / "warehouse-waybill-ru" / "2.0.0"
    for rel in (
        "manifest.yaml",
        "main.typ",
        "layout-config.typ",
        "components/pagination.typ",
        "components/signatures.typ",
    ):
        assert (pkg_root / rel).is_file(), f"installed 2.0.0 resource missing: {rel}"
    manifest_text = (pkg_root / "manifest.yaml").read_text(encoding="utf-8")
    assert "id: warehouse-waybill-ru" in manifest_text
    assert "version: 2.0.0" in manifest_text


def test_install_env_override_beats_installed_share(
    built_wheel: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """After install, QM_FONTS_DIR / QM_TEMPLATES_DIR still win over share."""
    venv_dir = tmp_path_factory.mktemp("qde-install-venv-env")
    venv_python = venv_dir / "bin" / "python"
    proc = subprocess.run(
        [sys.executable, "-m", "venv", str(venv_dir)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert proc.returncode == 0, f"venv creation failed: {proc.stderr}"
    proc = subprocess.run(
        [str(venv_python), "-m", "pip", "install", "--no-index", "--no-deps", str(built_wheel)],
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert proc.returncode == 0, f"pip install failed: {proc.stderr}"

    custom_fonts = tmp_path_factory.mktemp("qde-env-fonts")
    custom_templates = tmp_path_factory.mktemp("qde-env-templates")
    env = _clean_env_without_qm_vars()
    env["QM_FONTS_DIR"] = str(custom_fonts)
    env["QM_TEMPLATES_DIR"] = str(custom_templates)

    probe = (
        "from qm_engine import paths\n"
        "print(paths.default_fonts_dir())\n"
        "print(paths.default_templates_dir())\n"
    )
    proc = subprocess.run(
        [str(venv_python), "-c", probe],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    assert proc.returncode == 0, f"path probe failed: {proc.stderr}"
    fonts_dir, templates_dir = [Path(line.strip()) for line in proc.stdout.splitlines()]
    assert fonts_dir == custom_fonts.resolve()
    assert templates_dir == custom_templates.resolve()
