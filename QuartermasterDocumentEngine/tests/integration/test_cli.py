"""Integration tests for the qm-render CLI (SPEC v2 §3, §22; TZ-PHASE1)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
QM = REPO / ".venv" / "bin" / "qm-render"
WAYBILL = REPO / "tests" / "fixtures" / "waybill-20.json"
INVALID = REPO / "tests" / "fixtures" / "invalid"


def run_cli(*args: str, stdin: bytes | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    return subprocess.run(
        [str(QM), *args],
        input=stdin,
        capture_output=True,
        env=env,
        timeout=120,
    )


def test_version() -> None:
    r = run_cli("version")
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["engine"] == "0.1.0"
    assert data["engine_contract_versions"] == ["1.0.0"]


def test_capabilities_shows_backend_and_template() -> None:
    r = run_cli("capabilities")
    assert r.returncode == 0
    data = json.loads(r.stdout)
    backends = {b["name"] for b in data["backends"]}
    assert "weasyprint" in backends
    templates = {(t["id"], t["version"]) for t in data["templates"]}
    assert ("warehouse-waybill-ru", "0.1.0") in templates
    assert ("warehouse-waybill-ru", "1.0") in templates


def test_validate_file_ok() -> None:
    r = run_cli("validate", "--input", str(WAYBILL))
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["valid"] is True


def test_validate_stdin_ok() -> None:
    raw = WAYBILL.read_bytes()
    r = run_cli("validate", "--stdin", stdin=raw)
    assert r.returncode == 0
    assert json.loads(r.stdout)["valid"] is True


def test_render_file_to_file() -> None:
    r = run_cli("render", "--input", str(WAYBILL), "--output", "/tmp/qm-it-file.pdf")
    assert r.returncode == 0
    out = Path("/tmp/qm-it-file.pdf")
    assert out.read_bytes()[:5] == b"%PDF-"
    out.unlink(missing_ok=True)


def test_render_file_to_stdout() -> None:
    r = run_cli("render", "--input", str(WAYBILL), "--stdout", "--format", "pdf")
    assert r.returncode == 0
    assert r.stdout[:5] == b"%PDF-"
    assert len(r.stdout) > 0


def test_render_stdin_to_stdout() -> None:
    raw = WAYBILL.read_bytes()
    r = run_cli("render", "--stdin", "--stdout", "--format", "pdf", stdin=raw)
    assert r.returncode == 0
    assert r.stdout[:5] == b"%PDF-"
    assert len(r.stdout) > 0


def test_inspect_template() -> None:
    r = run_cli("inspect-template", "--template", "warehouse-waybill-ru", "--version", "0.1.0")
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["template_id"] == "warehouse-waybill-ru"
    assert data["manifest"]["backend"] == "weasyprint"
    assert data["compatibility"]["backend"] == "weasyprint"
    assert data["compatibility"]["backend_available"] is True


# --- Phase 1.1: --templates-dir must be honoured by every command. ---


@pytest.fixture()
def empty_templates_dir(tmp_path: Path) -> Path:
    d = tmp_path / "empty-templates"
    d.mkdir()
    return d


def test_validate_with_custom_empty_templates_dir(empty_templates_dir: Path) -> None:
    r = run_cli(
        "--templates-dir",
        str(empty_templates_dir),
        "validate",
        "--input",
        str(WAYBILL),
    )
    assert r.returncode == 3
    err = json.loads(r.stderr)
    assert err["error"]["code"] == "TEMPLATE_NOT_INSTALLED"


def test_render_with_custom_empty_templates_dir(empty_templates_dir: Path) -> None:
    raw = WAYBILL.read_bytes()
    r = run_cli(
        "--templates-dir",
        str(empty_templates_dir),
        "render",
        "--stdin",
        "--stdout",
        "--format",
        "pdf",
        stdin=raw,
    )
    assert r.returncode == 3
    err = json.loads(r.stderr)
    assert err["error"]["code"] == "TEMPLATE_NOT_INSTALLED"


def test_inspect_with_custom_empty_templates_dir(empty_templates_dir: Path) -> None:
    r = run_cli(
        "--templates-dir",
        str(empty_templates_dir),
        "inspect-template",
        "--template",
        "warehouse-waybill-ru",
        "--version",
        "0.1.0",
    )
    assert r.returncode == 3
    err = json.loads(r.stderr)
    assert err["error"]["code"] == "TEMPLATE_NOT_INSTALLED"


def test_capabilities_with_custom_empty_templates_dir(empty_templates_dir: Path) -> None:
    r = run_cli("--templates-dir", str(empty_templates_dir), "capabilities")
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["templates"] == []
    assert data["templates_dir"] == str(empty_templates_dir)


# --- Negative fixtures: each class-2 error from the table. ---


@pytest.mark.parametrize(
    "fixture,expected_code",
    [
        ("invalid-json.json", "INVALID_PAYLOAD"),
        ("missing-document-fields.json", "INVALID_PAYLOAD"),
        ("unsupported-engine-contract.json", "UNSUPPORTED_ENGINE_CONTRACT"),
        ("unsupported-document-contract.json", "UNSUPPORTED_DOCUMENT_CONTRACT"),
    ],
)
def test_validate_invalid_fixtures(fixture: str, expected_code: str) -> None:
    r = run_cli("validate", "--input", str(INVALID / fixture))
    assert r.returncode == 2
    err = json.loads(r.stderr)
    assert err["error"]["code"] == expected_code


def test_render_unsupported_output_format() -> None:
    raw = WAYBILL.read_bytes()
    r = run_cli("render", "--stdin", "--stdout", "--format", "png", stdin=raw)
    assert r.returncode == 2
    err = json.loads(r.stderr)
    assert err["error"]["code"] == "UNSUPPORTED_OUTPUT_FORMAT"


def test_render_missing_template_version() -> None:
    raw = WAYBILL.read_bytes().replace(b"0.1.0", b"9.9.9")
    r = run_cli("render", "--stdin", "--stdout", "--format", "pdf", stdin=raw)
    assert r.returncode == 3
    err = json.loads(r.stderr)
    assert err["error"]["code"] == "TEMPLATE_VERSION_NOT_INSTALLED"


def test_render_missing_template_id() -> None:
    raw = WAYBILL.read_bytes().replace(b"warehouse-waybill-ru", b"no-such-template")
    r = run_cli("render", "--stdin", "--stdout", "--format", "pdf", stdin=raw)
    assert r.returncode == 3
    err = json.loads(r.stderr)
    assert err["error"]["code"] == "TEMPLATE_NOT_INSTALLED"


def test_render_requires_output_or_stdout() -> None:
    r = run_cli("render", "--input", str(WAYBILL))
    assert r.returncode == 1  # click usage error


def test_render_requires_input_or_stdin() -> None:
    r = run_cli("render", "--stdout")
    assert r.returncode == 1  # click usage error


# --- Prod payloads must render through the version 1.0 dev template. ---

PROD_TEMPLATES = REPO / "doc" / "test_templates"

PROD_ENVELOPES = [
    "template_MOVE_15l.json",
    "template_MOVE_30l.json",
    "template_RECEIVE_15l.json",
    "template_WRITE_OFF_14l.json",
    "template_waybill_MOVE_5l.envelope.json",
    "template_act_ADJUSTMENT_1l.envelope.json",
]


@pytest.mark.parametrize("name", PROD_ENVELOPES)
def test_render_prod_envelope(name: str) -> None:
    r = run_cli("render", "--input", str(PROD_TEMPLATES / name), "--stdout", "--format", "pdf")
    assert r.returncode == 0, r.stderr.decode()
    assert r.stdout[:5] == b"%PDF-"
    assert len(r.stdout) > 0


@pytest.mark.parametrize("name", PROD_ENVELOPES)
def test_validate_prod_envelope(name: str) -> None:
    r = run_cli("validate", "--input", str(PROD_TEMPLATES / name))
    assert r.returncode == 0, r.stderr.decode()
    data = json.loads(r.stdout)
    assert data["valid"] is True
    assert data["template_version"] == "1.0"
