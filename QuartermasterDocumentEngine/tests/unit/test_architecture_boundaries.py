"""Architecture boundary guard (ADR-0031 D2).

QDE is a monorepo component with strong subdirectory boundaries:
``Warehouse_web -> QDE`` is allowed, while ``QDE -> Warehouse_web`` and
``QDE -> SyncServer`` are forbidden. This test scans every ``.py`` file
under ``engine/``, ``backends/``, ``cli/`` and ``scripts/`` with the ``ast``
module and fails if any module imports Warehouse Solution code.

Forbidden top-level import names:

- ``warehouse_web`` / ``django`` / ``apps`` / ``config`` — Warehouse_web
  (Django BFF) code (``apps/`` packages, ``config.settings``).
- ``syncserver`` / ``fastapi`` / ``app`` — SyncServer code (``app/`` package).

Relative imports inside QDE (``qm_engine``, ``qm_backends``, ``qm_cli``) and
stdlib/third-party imports are unaffected.
"""

from __future__ import annotations

import ast
from pathlib import Path

_FORBIDDEN_TOP_LEVEL = frozenset(
    {
        "app",
        "apps",
        "config",
        "django",
        "fastapi",
        "syncserver",
        "warehouse_web",
    }
)

_SOURCE_DIRS = ("engine", "backends", "cli", "scripts")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _py_files() -> list[Path]:
    root = _repo_root()
    files: list[Path] = []
    for dirname in _SOURCE_DIRS:
        src_dir = root / dirname
        if src_dir.is_dir():
            files.extend(sorted(src_dir.rglob("*.py")))
    return files


def _forbidden_imports(path: Path) -> list[str]:
    violations: list[str] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        violations.append(f"{path}: unparseable source: {exc}")
        return violations
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in _FORBIDDEN_TOP_LEVEL:
                    violations.append(f"{path}:{node.lineno}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                top = node.module.split(".")[0]
                if top in _FORBIDDEN_TOP_LEVEL:
                    violations.append(f"{path}:{node.lineno}: from {node.module} import ...")
    return violations


def test_qde_source_has_no_warehouse_imports() -> None:
    """Every QDE source file must stay free of Warehouse Solution imports."""
    files = _py_files()
    assert files, "no QDE source files found; is the bundle root correct?"

    violations: list[str] = []
    for path in files:
        violations.extend(_forbidden_imports(path))

    assert not violations, (
        "ADR-0031 D2 violation: QDE source must not import Warehouse Solution "
        f"code. Offending imports:\n" + "\n".join(violations)
    )
