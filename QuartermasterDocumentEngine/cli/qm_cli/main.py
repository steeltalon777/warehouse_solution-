"""qm-render — universal CLI (SPEC v2 §3, §22; ADR-0001 D3; ROADMAP Phase 1).

Commands: version, capabilities, validate, inspect-template, render.
All output is JSON on stdout; errors are JSON on stderr with the documented
exit codes (TZ-PHASE1-CLI-SKELETON).
"""

from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path
from typing import Any, cast

import click
from qm_engine import paths
from qm_engine import render as engine_render
from qm_engine.envelope import parse_envelope
from qm_engine.errors import EngineError
from qm_engine.registry import Registry
from qm_engine.render import get_backend, inspect_template, render_envelope

# Candidate module-level attribute names that a backend may use to declare
# its supported output formats. Order matters — the first hit wins. Used by
# :func:`_available_output_formats` to derive per-backend ``output_formats``
# without hard-coding backend names in the CLI (TZ-PHASE2-BACKEND-SPIKE
# §T8 review note #2).
_BACKEND_FORMAT_ATTRS: tuple[str, ...] = (
    "SUPPORTED_FORMATS",
    "SUPPORTED_OUTPUT_FORMATS",
    "OUTPUT_FORMATS",
)


def _emit(obj: dict[str, Any]) -> None:
    click.echo(json.dumps(obj, ensure_ascii=False))


def _resolve_templates_dir(ctx: click.Context) -> Path:
    """CLI --templates-dir > env QM_TEMPLATES_DIR > bundle default."""
    flag = ctx.obj.get("templates_dir")
    if flag:
        return Path(flag).resolve()
    return paths.default_templates_dir()


def _emit_error(err: EngineError) -> None:
    click.echo(json.dumps(err.to_dict(), ensure_ascii=False), err=True)


def _raise_exit(code: int) -> None:
    raise click.exceptions.Exit(code)


def _run(command) -> None:  # type: ignore[no-untyped-def]
    """Run a thunk, translating EngineError to stderr JSON + exit code."""
    try:
        command()
    except EngineError as err:
        _emit_error(err)
        _raise_exit(err.exit_code)
    except click.ClickException:
        raise
    except Exception as exc:  # noqa: BLE001 - unexpected internal error
        internal_error = EngineError(f"Internal error: {exc}", {})
        _emit_error(internal_error)
        _raise_exit(internal_error.exit_code)


@click.group()
@click.option(
    "--templates-dir",
    type=click.Path(path_type=Path, file_okay=False),
    help="Override template root (default <bundle>/templates, env QM_TEMPLATES_DIR).",
)
@click.pass_context
def cli(ctx: click.Context, templates_dir: Path | None) -> None:
    """Quartermaster Document Engine — offline document renderer."""
    ctx.ensure_object(dict)
    ctx.obj["templates_dir"] = templates_dir


@cli.command("version")
def version() -> None:
    """Print engine version and supported engine contract versions (JSON)."""
    _emit(
        {
            "engine": paths.ENGINE_VERSION,
            "engine_contract_versions": paths.ENGINE_CONTRACT_VERSIONS,
        }
    )


@cli.command("capabilities")
@click.pass_context
def capabilities(ctx: click.Context) -> None:
    """Print available backends, output formats and installed templates (JSON)."""
    templates_root = _resolve_templates_dir(ctx)
    registry = Registry(templates_root)
    installed = [
        {
            "id": p.template_id,
            "version": p.version,
            "document_contract": p.document_contract,
            "backend": p.backend,
            "locales": p.locales,
            "output_formats": p.output_formats,
        }
        for p in registry.list_installed()
    ]

    # Phase 2 (T6 / T8 review note #2): enumerate every backend registered
    # in the engine. Per-backend ``output_formats`` is derived via
    # :func:`_available_output_formats` rather than hard-coded in the CLI
    # so adding a new backend does not require touching this command.
    # The top-level ``output_formats`` field stays the sorted union for
    # backward compatibility.
    backends_payload = []
    formats_union: set[str] = set()
    for backend in sorted(engine_render._BACKENDS.values(), key=lambda b: b.name):
        formats = _available_output_formats(backend)
        backends_payload.append(
            {
                "name": backend.name,
                "available": backend.available(),
                "output_formats": formats,
            }
        )
        formats_union.update(formats)

    _emit(
        {
            "engine_version": paths.ENGINE_VERSION,
            "engine_contract_version": paths.ENGINE_CONTRACT_VERSION,
            "backends": backends_payload,
            "output_formats": sorted(formats_union),
            "templates": installed,
            "templates_dir": str(templates_root),
        }
    )


def _available_output_formats(backend: Any) -> list[str]:
    """Derive the sorted list of output formats a backend supports.

    Lookup order (TZ-PHASE2-BACKEND-SPIKE §T8 review note #2):

    1. An ``output_formats`` attribute on the backend instance/class.
    2. A module-level constant on the backend's owning module — any of
       ``SUPPORTED_FORMATS`` / ``SUPPORTED_OUTPUT_FORMATS`` /
       ``OUTPUT_FORMATS`` (first hit wins).
    3. The literal ``"pdf"`` (Phase 1 baseline invariant — every
       engine-level backend must at minimum produce PDF, per
       TZ-PHASE1-CLI-SKELETON).

    The fallback ensures that a backend which has not declared its
    formats is still reported as PDF-capable (matching the Phase 1
    contract) rather than producing an empty list. Backends that do
    declare richer formats (e.g. Typst → ``("pdf", "png")``) are
    discovered via #1 or #2 without any CLI change.
    """
    # 1. instance / class attribute
    candidate = getattr(backend, "output_formats", None)
    if isinstance(candidate, (list, tuple)) and candidate:
        return sorted(str(f) for f in candidate)
    # 2. module-level constant
    module = inspect.getmodule(type(backend))
    if module is not None:
        for attr in _BACKEND_FORMAT_ATTRS:
            candidate = getattr(module, attr, None)
            if isinstance(candidate, (list, tuple)) and candidate:
                return sorted(str(f) for f in candidate)
    # 3. Phase 1 baseline fallback
    return ["pdf"]


@cli.command("validate")
@click.option("--input", "input_path", type=click.Path(path_type=Path), help="Payload file.")
@click.option("--stdin", is_flag=True, help="Read payload from stdin.")
@click.pass_context
def validate(ctx: click.Context, input_path: Path | None, stdin: bool) -> None:
    """Validate envelope + document contract + template presence."""
    payload = _read_payload(input_path, stdin)
    root = _resolve_templates_dir(ctx)
    _run(lambda: _do_validate(payload, root))


def _do_validate(payload: str | bytes, root: Path) -> None:
    envelope = parse_envelope(payload)
    package = Registry(root).lookup(envelope.template_id, envelope.template_version)
    Registry(root).check_contract(package, envelope.document_contract)
    _emit(
        {
            "valid": True,
            "engine_contract_version": envelope.engine_contract_version,
            "document_contract": envelope.document_contract,
            "template_id": envelope.template_id,
            "template_version": envelope.template_version,
            "templates_dir": str(root),
        }
    )


@cli.command("inspect-template")
@click.option("--template", "template_id", required=True, help="Template id.")
@click.option("--version", "version", required=True, help="Template version.")
@click.pass_context
def inspect_template_cmd(ctx: click.Context, template_id: str, version: str) -> None:
    """Print template manifest and compatibility status (JSON)."""
    root = _resolve_templates_dir(ctx)
    _run(lambda: _do_inspect(root, template_id, version))


def _do_inspect(root: Path, template_id: str, version: str) -> None:
    package = inspect_template(root, template_id, version)
    backend_available = get_backend(package.backend).available()
    _emit(
        {
            "template_id": package.template_id,
            "template_version": package.version,
            "manifest": package.manifest,
            "compatibility": {
                "document_contract": package.document_contract,
                "backend": package.backend,
                "backend_available": backend_available,
            },
        }
    )


@cli.command("render")
@click.option("--input", "input_path", type=click.Path(path_type=Path), help="Payload file.")
@click.option("--stdin", is_flag=True, help="Read payload from stdin.")
@click.option(
    "--output",
    "output_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Output artifact path.",
)
@click.option("--stdout", is_flag=True, help="Write artifact to stdout.")
@click.option(
    "--format", "output_format", type=str, default="pdf", help="Output format (Phase 1: pdf only)."
)
@click.option(
    "--copies",
    type=click.IntRange(min=1),
    default=1,
    help="Number of identical copies (engine-level). Default 1. PDF only.",
)
@click.option(
    "--watermark/--no-watermark",
    default=False,
    help=(
        "Render diagonal 'ОБРАЗЕЦ' watermark on the artifact. Default --no-watermark "
        "(Phase 1 byte-identical). Templates must opt in by reading the "
        "``watermark`` field from their data context."
    ),
)
@click.pass_context
def render(
    ctx: click.Context,
    input_path: Path | None,
    stdin: bool,
    output_path: Path | None,
    stdout: bool,
    output_format: str,
    copies: int,
    watermark: bool,
) -> None:
    """Render a document to an artifact. Modes: file→file, file→stdout, stdin→stdout."""
    if stdin == (input_path is not None):
        raise click.ClickException("Provide exactly one of --input FILE or --stdin.")
    if not stdout and output_path is None:
        raise click.ClickException("Provide --output FILE or --stdout to write the artifact.")
    if stdout and output_path is not None:
        raise click.ClickException("Use either --output or --stdout, not both.")

    payload = _read_payload(input_path, stdin)
    root = _resolve_templates_dir(ctx)
    _run(lambda: _do_render(payload, root, output_format, output_path, stdout, copies, watermark))


def _do_render(
    payload: str | bytes,
    root: Path,
    output_format: str,
    output_path: Path | None,
    to_stdout: bool,
    copies: int,
    watermark: bool,
) -> None:
    envelope = parse_envelope(payload)
    result = render_envelope(
        envelope,
        root,
        output_format=output_format,
        render_options={"copies": copies, "watermark": watermark},
    )
    if to_stdout:
        sys.stdout.buffer.write(result.data)
    else:
        assert output_path is not None
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(result.data)


def _read_payload(input_path: Path | None, stdin: bool) -> str | bytes:
    if stdin:
        return sys.stdin.buffer.read()
    assert input_path is not None
    return input_path.read_bytes()


def main() -> int:
    return cast(int, cli(prog_name="qm-render"))


if __name__ == "__main__":
    main()
