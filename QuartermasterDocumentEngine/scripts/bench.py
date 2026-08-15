"""Phase 2 T10 performance benchmark harness (TZ-PHASE2-BACKEND-SPIKE §14).

Drives ``qm-render render`` as a black-box subprocess for the WeasyPrint and
Typst backends, across three datasets (waybill-20, waybill-500, fuel-1500)
and four scenarios (cold, 10 sequential, 10 parallel, 50 pool=4). Records
wall time, CPU time, peak RSS and output size for every render, plus an
in-process WeasyPrint baseline for the CLI-overhead delta.

Output:
    spike-out/bench/<cell>.json         — raw per-cell metrics (gitignored)
    spike-out/bench/<cell>.runs.json    — per-run wall time series
    spike-out/bench/distribution.json   — disk-usage snapshot
    spike-out/bench/runtime-deps.json   — pip packages relevant to rendering
    doc/spike/PERF-REPORT.md            — human-readable report
    doc/spike/perf-summary.json         — machine-readable summary

The script must run from any working directory; all paths are resolved
relative to the repo root.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import psutil  # type: ignore[import-untyped]  # no stubs in this project

REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_BIN = REPO_ROOT / ".venv" / "bin"
QM_RENDER = VENV_BIN / "qm-render"
VENV_PYTHON = VENV_BIN / "python"

OUT_ROOT = REPO_ROOT / "spike-out" / "bench"
TEMPLATES_DIR = REPO_ROOT / "templates"
DOC_DIR = REPO_ROOT / "doc" / "spike"

# --- scenario / dataset constants ------------------------------------------

DATASETS: dict[str, dict[str, Path]] = {
    "waybill-20": {
        "weasyprint": REPO_ROOT / "tests" / "fixtures" / "waybill" / "waybill-20.weasy.json",
        "typst": REPO_ROOT / "tests" / "fixtures" / "waybill" / "waybill-20.typst.json",
    },
    "waybill-500": {
        "weasyprint": REPO_ROOT / "tests" / "fixtures" / "waybill" / "waybill-500.weasy.json",
        "typst": REPO_ROOT / "tests" / "fixtures" / "waybill" / "waybill-500.typst.json",
    },
    "fuel-1500": {
        "weasyprint": REPO_ROOT / "tests" / "fixtures" / "fuel" / "fuel-report-1500.weasy.json",
        "typst": REPO_ROOT / "tests" / "fixtures" / "fuel" / "fuel-report-1500.typst.json",
    },
}

# §14 reference targets (SPEC: 4 vCPU / 8 GB reference machine).
TARGETS: dict[str, dict[str, int]] = {
    "cold_waybill20_ms": {"target": 1500, "hard": 2500},
    "cold_waybill500_ms": {"target": 4000, "hard": 7000},
    "cold_fuel1500_ms": {"target": 8000, "hard": 15000},
    "warm_ms": {"target": 700, "hard": 1200},
    "warm_waybill500_ms": {"target": 4000, "hard": 7000},
    "warm_fuel1500_ms": {"target": 8000, "hard": 15000},
    "pool_ms": {"target": 30000, "hard": 60000},
    "worker_rss_bytes": {"target": 400 * 1024 * 1024, "hard": 700 * 1024 * 1024},
}

# Number of warm runs per scenario. 50 pool is configurable via CLI.
DEFAULT_SEQ_RUNS = 10
DEFAULT_PAR_RUNS = 10
DEFAULT_POOL_RUNS = 50
DEFAULT_POOL_WORKERS = 4
DEFAULT_ITERATIONS: dict[str, int] = {
    "cold": 1,
    "10 sequential": DEFAULT_SEQ_RUNS,
    "10 parallel": DEFAULT_PAR_RUNS,
    "50 pool=4": DEFAULT_POOL_RUNS,
}

POLL_INTERVAL_S = 0.01  # 10 ms RSS polling
TYPST_TIMESTAMP = 1700000000  # fixed per TZ §14


@dataclasses.dataclass
class RunMetrics:
    """Wall/CPU/RSS metrics for a single subprocess invocation."""

    wall_ms: float
    cpu_user_ms: float
    cpu_system_ms: float
    peak_rss_bytes: int
    output_size_bytes: int
    returncode: int
    duration_ms: float = 0.0  # monotonic wall (kept for parity)


def _build_env() -> dict[str, str]:
    env = os.environ.copy()
    env["TYPST_TIMESTAMP"] = str(TYPST_TIMESTAMP)
    # Keep WeasyPrint output deterministic; clear any locale overrides.
    env.setdefault("LC_ALL", "C.UTF-8")
    env.setdefault("LANG", "C.UTF-8")
    return env


def _rss_from_proc_status(pid: int) -> int:
    """Read VmRSS from /proc/<pid>/status when the process still exists."""

    try:
        with open(f"/proc/{pid}/status", encoding="ascii") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError):
        return 0
    return 0


def _peak_rss_for_pid(pid: int) -> tuple[int, int, tuple[float, float]]:
    """Track peak RSS and CPU time for a single process and its children.

    Returns (peak_rss_bytes, last_observed_rss_bytes, (cpu_user_s,
    cpu_system_s)) sampled at process exit. Polls psutil while the
    process is alive so CPU time is captured before the kernel reaps the
    task (after which psutil cpu_times returns zero).
    """

    peak = 0
    last = 0
    cpu_user_s = 0.0
    cpu_system_s = 0.0
    try:
        root = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return (0, 0, (0.0, 0.0))
    while True:
        try:
            current = root.memory_info().rss
            for child in root.children(recursive=True):
                try:
                    current += child.memory_info().rss
                except psutil.NoSuchProcess:
                    continue
            peak = max(peak, current)
            last = current
            cpu = root.cpu_times()
            cpu_user_s = cpu.user
            cpu_system_s = cpu.system
            for child in root.children(recursive=True):
                try:
                    ccpu = child.cpu_times()
                    cpu_user_s += ccpu.user
                    cpu_system_s += ccpu.system
                except psutil.NoSuchProcess:
                    continue
        except psutil.NoSuchProcess:
            break
        try:
            if root.status() == psutil.STATUS_ZOMBIE:
                break
        except psutil.NoSuchProcess:
            break
        time.sleep(POLL_INTERVAL_S)
    if peak == 0:
        peak = _rss_from_proc_status(pid)
        last = max(last, peak)
    return (peak, last, (cpu_user_s, cpu_system_s))


def _run_subprocess(cmd: Sequence[str], env: dict[str, str], output_path: Path) -> RunMetrics:
    """Spawn a single render, track wall/CPU/RSS, persist PDF bytes."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()
    started = time.perf_counter()
    proc = subprocess.Popen(
        list(cmd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    peak_rss, _last, (cpu_user_s, cpu_system_s) = _peak_rss_for_pid(proc.pid)
    proc.wait()
    wall_ms = (time.perf_counter() - started) * 1000.0
    output_size = output_path.stat().st_size if output_path.exists() else 0
    return RunMetrics(
        wall_ms=wall_ms,
        cpu_user_ms=cpu_user_s * 1000.0,
        cpu_system_ms=cpu_system_s * 1000.0,
        peak_rss_bytes=peak_rss,
        output_size_bytes=output_size,
        returncode=proc.returncode,
        duration_ms=wall_ms,
    )


def _render_command(fixture: Path, output: Path) -> list[str]:
    return [
        str(QM_RENDER),
        "--templates-dir",
        str(TEMPLATES_DIR),
        "render",
        "--input",
        str(fixture),
        "--output",
        str(output),
        "--format",
        "pdf",
    ]


def _scenario_cold(
    backend: str, dataset: str, fixture: Path, env: dict[str, str]
) -> dict[str, Any]:
    """One fresh subprocess — captures full interpreter + backend startup."""

    with tempfile.TemporaryDirectory(prefix="qm-cold-") as tmp:
        output = Path(tmp) / "out.pdf"
        cmd = _render_command(fixture, output)
        run = _run_subprocess(cmd, env, output)
        return {
            "wall_ms": run.wall_ms,
            "cpu_user_ms": run.cpu_user_ms,
            "cpu_system_ms": run.cpu_system_ms,
            "peak_rss_bytes": run.peak_rss_bytes,
            "output_size_bytes": run.output_size_bytes,
            "returncode": run.returncode,
        }


def _scenario_sequential(
    backend: str,
    dataset: str,
    fixture: Path,
    env: dict[str, str],
    n: int,
    runs_dir: Path,
) -> dict[str, Any]:
    """N sequential subprocess invocations in one session."""

    runs: list[RunMetrics] = []
    for i in range(n):
        output = runs_dir / f"run-{i}.pdf"
        cmd = _render_command(fixture, output)
        runs.append(_run_subprocess(cmd, env, output))
    return _aggregate_runs(runs)


def _scenario_parallel(
    backend: str,
    dataset: str,
    fixture: Path,
    env: dict[str, str],
    n: int,
    runs_dir: Path,
) -> dict[str, Any]:
    """N simultaneous Popen instances launched in the same event loop tick.

    Per-process wall time is measured from ``Popen`` start to that
    process's ``wait()`` completion. The aggregated "total wall" is the
    end-to-end span from first spawn to last completion.
    """

    procs: list[subprocess.Popen[bytes]] = []
    outputs: list[Path] = []
    starts: list[float] = []
    runs_dir.mkdir(parents=True, exist_ok=True)
    spawn_started = time.perf_counter()
    for i in range(n):
        output = runs_dir / f"run-{i}.pdf"
        if output.exists():
            output.unlink()
        cmd = _render_command(fixture, output)
        starts.append(time.perf_counter())
        procs.append(
            subprocess.Popen(
                list(cmd),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        )
        outputs.append(output)
    runs: list[RunMetrics] = []
    for proc, output, start_ts in zip(procs, outputs, starts, strict=True):
        peak_rss, _last, (cpu_user_s, cpu_system_s) = _peak_rss_for_pid(proc.pid)
        proc.wait()
        wall_ms = (time.perf_counter() - start_ts) * 1000.0
        runs.append(
            RunMetrics(
                wall_ms=wall_ms,
                cpu_user_ms=cpu_user_s * 1000.0,
                cpu_system_ms=cpu_system_s * 1000.0,
                peak_rss_bytes=peak_rss,
                output_size_bytes=output.stat().st_size if output.exists() else 0,
                returncode=proc.returncode,
            )
        )
    total_wall_ms = (time.perf_counter() - spawn_started) * 1000.0
    aggregated = _aggregate_runs(runs)
    aggregated["total_wall_ms"] = total_wall_ms
    return aggregated


def _scenario_pool(
    backend: str,
    dataset: str,
    fixture: Path,
    env: dict[str, str],
    n: int,
    workers: int,
    runs_dir: Path,
) -> dict[str, Any]:
    """N renders dispatched across ``workers`` processes via ProcessPoolExecutor.

    Each pool worker spawns one ``qm-render`` invocation; the executor
    enforces concurrency. ``total_wall_ms`` captures the end-to-end span
    from submit to last completion.
    """

    runs_dir.mkdir(parents=True, exist_ok=True)
    pool_started = time.perf_counter()
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as pool:
        results = list(
            pool.map(
                _pool_task,
                [(idx, fixture, env, runs_dir) for idx in range(n)],
            )
        )
    total_wall_ms = (time.perf_counter() - pool_started) * 1000.0
    runs = [RunMetrics(**r) for r in results]
    aggregated = _aggregate_runs(runs)
    aggregated["total_wall_ms"] = total_wall_ms
    return aggregated


def _pool_task(args: tuple[int, Path, dict[str, str], Path]) -> dict[str, Any]:
    idx, fixture, env, runs_dir = args
    output = runs_dir / f"run-{idx}.pdf"
    cmd = _render_command(fixture, output)
    run = _run_subprocess(cmd, env, output)
    return dataclasses.asdict(run)


def _aggregate_runs(runs: list[RunMetrics]) -> dict[str, Any]:
    """Aggregate per-run metrics into p50/p95/cpu/rss/output summary."""

    walls = sorted(r.wall_ms for r in runs)
    cpus = [r.cpu_user_ms + r.cpu_system_ms for r in runs]
    rss = [r.peak_rss_bytes for r in runs]
    outputs = [r.output_size_bytes for r in runs]
    failures = sum(1 for r in runs if r.returncode != 0)
    return {
        "n": len(runs),
        "failures": failures,
        "wall_ms": {
            "min": walls[0] if walls else 0.0,
            "max": walls[-1] if walls else 0.0,
            "mean": statistics.fmean(walls) if walls else 0.0,
            "p50": _percentile(walls, 50),
            "p95": _percentile(walls, 95),
        },
        "cpu_ms": {
            "sum_user": sum(r.cpu_user_ms for r in runs),
            "sum_system": sum(r.cpu_system_ms for r in runs),
            "sum_total": sum(cpus),
            "mean_total": statistics.fmean(cpus) if cpus else 0.0,
        },
        "rss_bytes": {
            "peak_max": max(rss) if rss else 0,
            "peak_mean": int(statistics.fmean(rss)) if rss else 0,
            "peak_sum": sum(rss),
        },
        "output_bytes": {
            "mean": int(statistics.fmean(outputs)) if outputs else 0,
            "min": min(outputs) if outputs else 0,
            "max": max(outputs) if outputs else 0,
        },
        "returncodes": sorted({r.returncode for r in runs}),
    }


def _percentile(sorted_values: Sequence[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    k = (len(sorted_values) - 1) * (pct / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = k - lo
    return sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac


def _measure_in_process_weasy(dataset: str, fixture: Path, n: int) -> dict[str, Any]:
    """Run ``engine.qm_engine.render.render_envelope`` directly for WeasyPrint.

    This isolates the per-render cost without the Python interpreter /
    venv / font-config subprocess wrapper. ``typst-py`` (PyPI) is not
    installed and out of scope; the in-process measurement therefore
    covers only the WeasyPrint backend. Output mirrors the sequential
    scenario schema.
    """

    sys.path.insert(0, str(REPO_ROOT / "src"))
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    # The engine package layout puts ``qm_engine`` under ``engine/qm_engine``,
    # so we add ``engine`` to sys.path rather than relying on a src layout.
    engine_parent = REPO_ROOT / "engine"
    if str(engine_parent) not in sys.path:
        sys.path.insert(0, str(engine_parent))
    backends_parent = REPO_ROOT / "backends"
    if str(backends_parent) not in sys.path:
        sys.path.insert(0, str(backends_parent))

    from qm_engine.envelope import parse_envelope  # type: ignore[import-not-found]
    from qm_engine.render import render_envelope  # type: ignore[import-not-found]

    envelope = parse_envelope(fixture.read_text(encoding="utf-8"))
    walls: list[float] = []
    cpu: list[float] = []
    rss: list[int] = []
    sizes: list[int] = []
    failures = 0
    proc = psutil.Process()
    for _ in range(n):
        start = time.perf_counter()
        try:
            result = render_envelope(envelope, TEMPLATES_DIR, output_format="pdf")
        except Exception:
            failures += 1
            continue
        wall_ms = (time.perf_counter() - start) * 1000.0
        walls.append(wall_ms)
        cpu.append(sum(proc.cpu_times()))
        rss.append(proc.memory_info().rss)
        sizes.append(len(result.data))
    runs_metrics = [
        RunMetrics(
            wall_ms=w,
            cpu_user_ms=0.0,
            cpu_system_ms=c,
            peak_rss_bytes=r,
            output_size_bytes=s,
            returncode=0 if f == 0 else 1,
        )
        for w, c, r, s, f in zip(walls, cpu, rss, sizes, [0] * len(walls), strict=True)
    ]
    aggregated = _aggregate_runs(runs_metrics)
    aggregated["failures"] = failures
    aggregated["note"] = (
        "In-process render_envelope call. CPU time is cumulative over the "
        "loop (psutil.Process().cpu_times() returns deltas only via "
        "Process.oneshot(); aggregated as cumulative values)."
    )
    return aggregated


def _cell_filename(backend: str, dataset: str, scenario: str) -> str:
    safe = scenario.replace(" ", "_").replace("=", "eq")
    return f"{backend}__{dataset}__{safe}"


def _run_cell(
    backend: str,
    dataset: str,
    scenario: str,
    iterations: dict[str, int],
    pool_workers: int,
    env: dict[str, str],
) -> dict[str, Any]:
    fixture = DATASETS[dataset][backend]
    if not fixture.is_file():
        return {
            "backend": backend,
            "dataset": dataset,
            "scenario": scenario,
            "status": "skipped",
            "reason": f"fixture not found: {fixture}",
        }
    runs_dir = OUT_ROOT / _cell_filename(backend, dataset, scenario)
    if scenario == "cold":
        metrics = _scenario_cold(backend, dataset, fixture, env)
    elif scenario == "10 sequential":
        metrics = _scenario_sequential(
            backend, dataset, fixture, env, iterations[scenario], runs_dir
        )
    elif scenario == "10 parallel":
        metrics = _scenario_parallel(backend, dataset, fixture, env, iterations[scenario], runs_dir)
    elif scenario == "50 pool=4":
        metrics = _scenario_pool(
            backend,
            dataset,
            fixture,
            env,
            iterations[scenario],
            pool_workers,
            runs_dir,
        )
    else:
        return {
            "backend": backend,
            "dataset": dataset,
            "scenario": scenario,
            "status": "skipped",
            "reason": f"unknown scenario: {scenario}",
        }
    return {
        "backend": backend,
        "dataset": dataset,
        "scenario": scenario,
        "status": "ok",
        "metrics": metrics,
    }


# --- distribution / runtime deps -------------------------------------------


def _measure_distribution() -> dict[str, Any]:
    """Disk usage snapshot for WeasyPrint and Typst."""

    def du(path: Path) -> int | None:
        if not path.exists():
            return None
        result = subprocess.run(
            ["du", "-sb", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return None
        return int(result.stdout.split()[0])

    weasy_pkg_dir = subprocess.run(
        [
            str(VENV_PYTHON),
            "-c",
            "import os, weasyprint; print(os.path.dirname(weasyprint.__file__))",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    weasy_pkg_path = Path(weasy_pkg_dir.stdout.strip()) if weasy_pkg_dir.returncode == 0 else None
    typst_root = REPO_ROOT / ".spike" / "typst-0.15.1" / "typst-x86_64-unknown-linux-musl" / "typst"

    venv = du(REPO_ROOT / ".venv")
    spike = du(REPO_ROOT / ".spike")
    typst_binary = du(typst_root)
    weasy_pkg = du(weasy_pkg_path) if weasy_pkg_path else None

    def fmt(value: int | None) -> str:
        return "n/a" if value is None else f"{value / (1024 * 1024):.1f} MB"

    return {
        "weasyprint_venv_bytes": venv,
        "weasyprint_venv_mb": None if venv is None else round(venv / (1024 * 1024), 1),
        "weasyprint_package_bytes": weasy_pkg,
        "weasyprint_package_mb": None if weasy_pkg is None else round(weasy_pkg / (1024 * 1024), 1),
        "typst_root_bytes": spike,
        "typst_root_mb": None if spike is None else round(spike / (1024 * 1024), 1),
        "typst_binary_bytes": typst_binary,
        "typst_binary_mb": None if typst_binary is None else round(typst_binary / (1024 * 1024), 1),
        "paths": {
            "venv": str(REPO_ROOT / ".venv"),
            "weasyprint_package": str(weasy_pkg_path) if weasy_pkg_path else None,
            "typst_root": str(typst_root.parent.parent),
            "typst_binary": str(typst_root),
        },
        "display": {
            "venv": fmt(venv),
            "weasyprint_package": fmt(weasy_pkg),
            "typst_root": fmt(spike),
            "typst_binary": fmt(typst_binary),
        },
    }


def _runtime_dependencies() -> dict[str, str]:
    """pip list filtered to packages relevant to rendering."""

    names = {
        "weasyprint",
        "jinja2",
        "pypdf",
        "psutil",
        "PyMuPDF",
        "Pillow",
        "fonttools",
        "cffi",
        "tinycss2",
        "cssselect2",
        "pydyf",
        "cairocffi",
        "click",
        "jsonschema",
        "PyYAML",
    }
    result = subprocess.run(
        [str(VENV_PIP), "list", "--format=json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return {}
    payload = json.loads(result.stdout)
    by_name = {row["name"].lower(): row["version"] for row in payload}
    return {name: by_name[name.lower()] for name in sorted(names) if name.lower() in by_name}


VENV_PIP = VENV_BIN / "pip"


def _machine_header() -> dict[str, Any]:
    return {
        "os": platform.platform(),
        "uname": platform.uname()._asdict(),
        "cpu_cores_logical": os.cpu_count(),
        "cpu_cores_physical": psutil.cpu_count(logical=False),
        "ram_bytes": psutil.virtual_memory().total,
        "ram_gb": round(psutil.virtual_memory().total / (1024**3), 1),
        "python": platform.python_version(),
        "psutil": psutil.__version__,
        "pypdf": _version_of("pypdf"),
        "pymupdf": _version_of("PyMuPDF"),
        "weasyprint": _version_of("weasyprint"),
        "typst": _typst_version(),
        "typst_timestamp": TYPST_TIMESTAMP,
    }


def _version_of(name: str) -> str | None:
    try:
        import importlib.metadata as md

        return md.version(name)
    except md.PackageNotFoundError:
        return None


def _typst_version() -> str:
    binary = REPO_ROOT / ".spike" / "typst-0.15.1" / "typst-x86_64-unknown-linux-musl" / "typst"
    if not binary.is_file():
        return "unknown"
    proc = subprocess.run([str(binary), "--version"], capture_output=True, text=True, check=False)
    return proc.stdout.strip() or "unknown"


# --- CLI argument plumbing ------------------------------------------------


SCENARIO_CHOICES = ["cold", "10 sequential", "10 parallel", "50 pool=4"]


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--scenarios",
        default=",".join(SCENARIO_CHOICES),
        help=f"Comma list of scenarios (default: {','.join(SCENARIO_CHOICES)}).",
    )
    parser.add_argument(
        "--datasets",
        default=",".join(DATASETS),
        help=f"Comma list of datasets (default: {','.join(DATASETS)}).",
    )
    parser.add_argument(
        "--backends",
        default="weasyprint,typst",
        help="Comma list of backends (default: weasyprint,typst).",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=None,
        help="Override iteration count for the 50-pool scenario (default 50).",
    )
    parser.add_argument(
        "--pool-workers",
        type=int,
        default=DEFAULT_POOL_WORKERS,
        help=f"Concurrency for the pool scenario (default {DEFAULT_POOL_WORKERS}).",
    )
    parser.add_argument(
        "--skip-in-process",
        action="store_true",
        help="Skip the in-process WeasyPrint benchmark (informational).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional JSON path to write the raw run summary (default: stdout).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Reduce per-cell progress output.",
    )
    return parser.parse_args(argv)


def _select(values: Iterable[str], requested: str) -> list[str]:
    wanted = [s.strip() for s in requested.split(",") if s.strip()]
    return [v for v in values if v in wanted]


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    OUT_ROOT.mkdir(parents=True, exist_ok=True)

    backends = _select(["weasyprint", "typst"], args.backends)
    datasets = _select(list(DATASETS), args.datasets)
    scenarios = _select(SCENARIO_CHOICES, args.scenarios)
    iterations = dict(DEFAULT_ITERATIONS)
    if args.iterations is not None:
        iterations["50 pool=4"] = args.iterations

    if not (backends and datasets and scenarios):
        raise SystemExit("No backends/datasets/scenarios matched the filters.")

    env = _build_env()
    cells: list[dict[str, Any]] = []
    cell_count = len(backends) * len(datasets) * len(scenarios)
    if not args.quiet:
        print(
            f"[bench] cells={cell_count} (backends={backends}, datasets={datasets}, "
            f"scenarios={scenarios})",
            flush=True,
        )
    for backend in backends:
        for dataset in datasets:
            for scenario in scenarios:
                if not args.quiet:
                    print(f"[bench] -> {backend}/{dataset}/{scenario}", flush=True)
                cell = _run_cell(backend, dataset, scenario, iterations, args.pool_workers, env)
                cells.append(cell)
                (OUT_ROOT / f"{_cell_filename(backend, dataset, scenario)}.json").write_text(
                    json.dumps(cell, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )

    in_process: dict[str, Any] = {}
    if not args.skip_in_process and "weasyprint" in backends and "waybill-20" in datasets:
        fixture = DATASETS["waybill-20"]["weasyprint"]
        if fixture.is_file():
            if not args.quiet:
                print("[bench] in-process weasyprint (waybill-20)", flush=True)
            in_process = {
                "backend": "weasyprint",
                "dataset": "waybill-20",
                "scenario": "in-process",
                "iterations": iterations["10 sequential"],
                "metrics": _measure_in_process_weasy(
                    "waybill-20", fixture, iterations["10 sequential"]
                ),
            }
    elif "waybill-20" not in datasets:
        in_process = {
            "status": "skipped",
            "reason": "waybill-20 dataset not selected; cannot run in-process comparison",
        }
    else:
        in_process = {"status": "skipped", "reason": "weasyprint backend not selected"}

    in_process["in_process_typst"] = {
        "status": "not-measured",
        "reason": (
            "PyPI typst-py is not installed; Typst 0.15.1 ships CLI only. "
            "In-process measurement would require a separate evaluation "
            "(tracked as future work)."
        ),
    }

    summary: dict[str, Any] = {
        "machine": _machine_header(),
        "versions": {
            "weasyprint": _version_of("weasyprint"),
            "typst": _typst_version(),
            "pymupdf": _version_of("PyMuPDF"),
            "psutil": _version_of("psutil"),
            "pypdf": _version_of("pypdf"),
            "python": platform.python_version(),
        },
        "filters": {
            "backends": backends,
            "datasets": datasets,
            "scenarios": scenarios,
            "iterations": iterations,
            "pool_workers": args.pool_workers,
        },
        "targets": TARGETS,
        "results": cells,
        "in_process": in_process,
        "distribution": _measure_distribution(),
        "runtime_dependencies": _runtime_dependencies(),
    }

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
