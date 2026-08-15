"""Typst backend (Phase 2 spike, TZ-PHASE2-BACKEND-SPIKE §11).

Drives a pinned ``typst`` subprocess to produce PDF or PNG output. The
binary is resolved at runtime from ``QM_TYPST_BINARY`` -> ``.spike/typst-<v>/...``
-> PATH. No network access in render-time.

Pipeline per render:

1. Resolve the binary (env var / pinned path / PATH probe).
2. Call ``ensure_bundled_fonts()`` — the renderer never uses system fonts.
3. Materialise envelope assets into a temp directory; pass it as
   ``--root`` so the template can refer to ``qr.png`` etc. by name.
4. Copy the template package into a per-render workdir alongside a
   ``document.json`` snapshot so Typst's ``#let doc = json("document.json")``
   resolves under ``--root``.
5. Run ``typst compile <main.typ> <out> --font-path <bundle>
   --ignore-system-fonts --root <workdir>``. Determinism:
   ``TYPST_TIMESTAMP`` env (default 1700000000).
6. Map exit codes: ``RENDER_FAILED`` on Typst non-zero; truncate stderr
   to 2 KB. ``UNSUPPORTED_OUTPUT_FORMAT`` on bad format. ``BACKEND_NOT_AVAILABLE``
   if the binary is missing.

Phase 2.1: ``document.json`` is the **full normalized envelope**
(top-level fields + ``document`` inner mapping), matching the WeasyPrint
behaviour (TZ-PHASE2-BACKEND-SPIKE §T5 line 225: "normalized document =
полный envelope.data, как в Phase 1"). Templates read envelope fields
through ``doc.<field>`` and inner document fields through
``doc.document.<field>``. The internal ``__assets__`` key is the only
field stripped before serialisation; everything else — including
``document_number``, ``template_id``, ``locale``, ``render_profile`` —
is reachable from Typst templates without a warehouse-specific proxy.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from qm_engine import assets as engine_assets
from qm_engine import fonts as engine_fonts
from qm_engine.errors import (
    BackendNotAvailableError,
    RenderFailedError,
    UnsupportedOutputFormatError,
)
from qm_engine.registry import TemplatePackage

from .base import RenderResult

_ASSETS_KEY = "__assets__"

SUPPORTED_FORMATS: tuple[str, ...] = ("pdf", "png")

# Default deterministic timestamp (Nov 2023). Pinned so golden regression
# tests stay stable across upgrades until 0.15.x breaks.
#
# Phase 2.1 review-fix M1: this value is now passed to Typst via the
# ``--creation-timestamp`` CLI flag (the ``TYPST_TIMESTAMP`` env var
# alone is ignored by Typst 0.15.1 on Linux — verified during the
# Phase 2.1 determinism diagnostic). Once the CLI flag is in place,
# output is byte-deterministic across renders crossing wall-clock
# second boundaries.
DEFAULT_TYPST_TIMESTAMP = 1700000000

# Maximum bytes of stderr we copy into RenderFailedError details.
STDERR_CAP_BYTES = 2048

# Timeout for ``--version`` probe in ``available()``.
VERSION_TIMEOUT_S = 5

# Timeout for a render call.
RENDER_TIMEOUT_S = 120


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _pin_path() -> Path:
    return _repo_root() / "spike" / "typst-pin.json"


def _pinned_version() -> str | None:
    path = _pin_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    version = data.get("version")
    return str(version) if isinstance(version, str) and version else None


def _pinned_binary_path() -> Path | None:
    version = _pinned_version()
    if not version:
        return None
    if os.name == "nt":
        win_dir = "typst-x86_64-pc-windows-msvc"
        return _repo_root() / ".spike" / f"typst-{version}" / win_dir / "typst.exe"
    return (
        _repo_root() / ".spike" / f"typst-{version}" / "typst-x86_64-unknown-linux-musl" / "typst"
    )


def _resolve_binary() -> str | None:
    env = os.environ.get("QM_TYPST_BINARY")
    if env:
        path = Path(env)
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    pinned = _pinned_binary_path()
    if pinned is not None and pinned.is_file() and os.access(pinned, os.X_OK):
        return str(pinned)
    which = shutil.which("typst")
    if which:
        return which
    return None


class TypstBackend:
    """Phase 2 spike Typst backend (subprocess pinned binary)."""

    name: str = "typst"

    def available(self) -> bool:
        """Return ``True`` if a usable ``typst`` binary is reachable.

        Probe with ``--version`` (5 s timeout). No network access.
        """
        binary = _resolve_binary()
        if not binary:
            return False
        try:
            proc = subprocess.run(
                [binary, "--version"],
                capture_output=True,
                text=True,
                timeout=VERSION_TIMEOUT_S,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        if proc.returncode != 0:
            return False
        stdout = (proc.stdout or "").strip()
        return stdout.startswith("typst ")

    def render(
        self,
        normalized_document: dict[str, Any],
        template_package: TemplatePackage,
        output_format: str,
        render_options: dict[str, Any],
    ) -> RenderResult:
        if output_format not in SUPPORTED_FORMATS:
            raise UnsupportedOutputFormatError(
                f"Backend '{self.name}' supports {SUPPORTED_FORMATS}, got '{output_format}'",
                {
                    "backend": self.name,
                    "output_format": output_format,
                    "supported": list(SUPPORTED_FORMATS),
                },
            )

        binary = _resolve_binary()
        if not binary:
            raise BackendNotAvailableError(
                "Typst backend is not available: no typst binary resolved",
                {
                    "backend": self.name,
                    "checked": [
                        "QM_TYPST_BINARY",
                        ".spike/typst-<pin>/...",
                        "PATH (typst)",
                    ],
                },
            )

        # Fonts must be present and verified before invoking typst
        # (TZ §12). ``ensure_bundled_fonts`` raises FontNotAvailableError
        # on missing/corrupt files; render-time cannot proceed.
        engine_fonts.ensure_bundled_fonts()

        # Phase 2 T5: materialise envelope assets. The internal
        # ``__assets__`` key is reserved — strip before serialising.
        assets = normalized_document.pop(_ASSETS_KEY, {}) or {}
        # Phase 2.1: write the **full** normalized envelope to
        # ``document.json`` (TZ-PHASE2-BACKEND-SPIKE §T5 / §11.2 —
        # "normalized document = полный envelope.data, как в Phase 1").
        # Typst templates access envelope-level fields directly via
        # ``doc.<field>`` (e.g. ``doc.document_number``,
        # ``doc.template_id``, ``doc.locale``) and inner document
        # fields via ``doc.document.<field>``. Phase 2 T8 review-fix
        # copy/watermark fields are still injected by ``render.py``
        # into both the top level and the inner ``document`` mapping,
        # so templates can read them from either side.
        document_payload = dict(normalized_document)

        warnings: list[str] = []
        out_ext = output_format
        with tempfile.TemporaryDirectory(prefix="qm-typst-") as workdir_str:
            workdir = Path(workdir_str)
            assets_dir = workdir / "assets"
            assets_dir.mkdir(parents=True, exist_ok=True)
            engine_assets.materialise_assets(assets, assets_dir)

            # Copy the template package into the workdir so ``main.typ``
            # can ``#include`` other files. We copy the package root to
            # ``workdir/pkg`` and document.json alongside so absolute
            # paths in the template stay under ``--root``.
            pkg_dest = workdir / "pkg"
            shutil.copytree(template_package.root, pkg_dest)

            doc_payload_path = pkg_dest / "document.json"
            doc_payload_path.write_text(
                json.dumps(document_payload, ensure_ascii=False),
                encoding="utf-8",
            )

            entrypoint_rel = Path(str(template_package.manifest["entrypoint"])).as_posix()
            entrypoint_abs = pkg_dest / entrypoint_rel
            if not entrypoint_abs.is_file():
                raise RenderFailedError(
                    "Typst template entrypoint not found in package",
                    {
                        "backend": self.name,
                        "template": str(template_package.root),
                        "entrypoint": entrypoint_rel,
                    },
                )

            out_file = workdir / f"out.{out_ext}"
            # Pin the PDF ``/CreationDate`` metadata so the output is
            # byte-deterministic across renders that cross a wall-clock
            # second boundary (Phase 2.1 review-fix M1).
            #
            # ``TYPST_TIMESTAMP`` env var is supposed to set the same
            # value per Typst 0.15.x docs, but in practice the var is
            # ignored on Linux; only the explicit ``--creation-timestamp``
            # CLI flag produces a pinned timestamp. We pass both for
            # forward compatibility (the env var is read by Typst if
            # the CLI flag is missing in a future version).
            creation_ts = os.environ.get("TYPST_TIMESTAMP") or str(DEFAULT_TYPST_TIMESTAMP)
            cmd: list[str] = [
                binary,
                "compile",
                str(entrypoint_abs),
                str(out_file),
                "--font-path",
                str(engine_fonts.fonts_dir()),
                "--ignore-system-fonts",
                "--root",
                str(workdir),
                "--creation-timestamp",
                creation_ts,
                "--diagnostic-format",
                "short",
            ]
            if output_format == "png":
                cmd.extend(["--format", "png", "--ppi", "150"])

            env = dict(os.environ)
            env.setdefault("TYPST_TIMESTAMP", str(DEFAULT_TYPST_TIMESTAMP))

            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    env=env,
                    timeout=RENDER_TIMEOUT_S,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise RenderFailedError(
                    "Typst render failed to start",
                    {"backend": self.name, "cause": str(exc), "binary": binary},
                ) from exc

            if proc.returncode != 0:
                stderr_snip = (proc.stderr or "")[:STDERR_CAP_BYTES]
                # Try to also surface non-fatal warnings if any.
                if proc.stdout:
                    for line in proc.stdout.splitlines():
                        if line.startswith("warning:"):
                            warnings.append(line)
                raise RenderFailedError(
                    "Typst render failed",
                    {
                        "backend": self.name,
                        "cause": stderr_snip,
                        "template": str(template_package.root),
                        "exit_code": proc.returncode,
                    },
                )

            if not out_file.is_file():
                raise RenderFailedError(
                    "Typst produced no output file",
                    {
                        "backend": self.name,
                        "template": str(template_package.root),
                        "out_file": str(out_file),
                    },
                )

            data = out_file.read_bytes()

        page_count: int | None
        if output_format == "pdf":
            page_count = _count_pdf_pages(data)
        else:
            # PNG output renders the first page only — Typst's
            # ``--format png`` returns a single raster. We still
            # compute page count via a second PDF pass so downstream
            # tooling can report multi-page documents.
            page_count = _page_count_via_pdf_pass(binary, template_package, document_payload)

        return RenderResult(
            data=data,
            format=output_format,
            page_count=page_count,
            warnings=warnings,
        )


def _count_pdf_pages(pdf_bytes: bytes) -> int | None:
    try:
        from io import BytesIO

        from pypdf import PdfReader

        with BytesIO(pdf_bytes) as stream:
            return len(PdfReader(stream).pages)
    except Exception:  # noqa: BLE001 - non-fatal metadata
        return None


def _page_count_via_pdf_pass(
    binary: str,
    template_package: TemplatePackage,
    document_payload: dict[str, Any],
) -> int | None:
    """Render the same template as PDF in a scratch dir to count pages.

    Used when the user requested PNG output: the resulting PNG shows only
    the first page, but downstream tooling may still need the total.
    """
    with tempfile.TemporaryDirectory(prefix="qm-typst-count-") as workdir_str:
        workdir = Path(workdir_str)
        try:
            shutil.copytree(template_package.root, workdir / "pkg")
        except OSError:
            return None
        doc_path = workdir / "pkg" / "document.json"
        doc_path.write_text(json.dumps(document_payload, ensure_ascii=False), encoding="utf-8")
        entrypoint_abs = workdir / "pkg" / str(template_package.manifest["entrypoint"])
        if not entrypoint_abs.is_file():
            return None
        out_file = workdir / "out.pdf"
        try:
            creation_ts = os.environ.get("TYPST_TIMESTAMP") or str(DEFAULT_TYPST_TIMESTAMP)
            proc = subprocess.run(
                [
                    binary,
                    "compile",
                    str(entrypoint_abs),
                    str(out_file),
                    "--font-path",
                    str(engine_fonts.fonts_dir()),
                    "--ignore-system-fonts",
                    "--root",
                    str(workdir),
                    "--creation-timestamp",
                    creation_ts,
                    "--diagnostic-format",
                    "short",
                ],
                capture_output=True,
                text=True,
                timeout=RENDER_TIMEOUT_S,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if proc.returncode != 0 or not out_file.is_file():
            return None
        return _count_pdf_pages(out_file.read_bytes())
