"""Golden regression artifacts for Quartermaster Document Engine (TZ §13.6).

This package stores structural + semantic expectations for the
acceptance matrix. Each entry in ``index.json`` points at an
``<template>-<version>/<fixture>.expected.json`` file with the values
that the harness must reproduce.

The package is read by ``tests/unit/test_golden.py`` and regenerated
by ``scripts/golden_update.py``. PNG/PDF golden artefacts live under
``spike-out/golden/`` as CI/local artefacts only — the git-lfs fallback
in ``doc/spike/INVESTIGATION.md`` §2.3 is in effect.
"""
