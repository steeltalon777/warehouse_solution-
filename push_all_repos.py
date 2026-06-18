#!/usr/bin/env python3
"""
push_all_repos.py

Push the dev branch to all configured remotes in nested Git repositories.

Usage:
    python push_all_repos.py                              # dry-run, root=., branch=dev
    python push_all_repos.py --root .                     # same as above
    python push_all_repos.py --root . --include-root      # include root repo too
    python push_all_repos.py --branch main                # push main instead of dev
    python push_all_repos.py --execute                    # actually push (no --execute = dry-run)
    python push_all_repos.py --execute --force            # push with --force-with-lease
    python push_all_repos.py --output report.txt          # write report to file
    python push_all_repos.py --json                       # JSON output
    python push_all_repos.py --json --output push.json    # JSON output to file

Safety:
- Dry-run by default; --execute required for actual pushes.
- Dirty repos are skipped.
- Repos without upstream are skipped.
- Repos already up to date are skipped.
- GIT_TERMINAL_PROMPT=0 prevents credential prompts.
- --force uses --force-with-lease, not --force, and prints a big warning.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_EXCLUDE_DIRS = {
    ".git",
    ".idea",
    ".vscode",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".gradle",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class GitResult:
    ok: bool
    stdout: str
    stderr: str
    returncode: int


@dataclass
class PushOutcome:
    remote: str
    ok: bool
    stdout: str
    stderr: str
    returncode: int


@dataclass
class RepoPlan:
    name: str
    path: str
    current_branch: str
    upstream: str | None
    ahead: int | None
    behind: int | None
    is_dirty: bool
    remotes: dict[str, str]
    eligible: bool
    skip_reason: str
    outcomes: list[PushOutcome] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def git_env() -> dict[str, str]:
    """Environment dict that prevents interactive prompts."""
    import os

    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_EDITOR"] = "true"
    env["GIT_PAGER"] = "cat"
    return env


def run_git(repo: Path, args: list[str], timeout: int = 30) -> GitResult:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=repo,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout,
            env=git_env(),
        )
        return GitResult(
            ok=completed.returncode == 0,
            stdout=completed.stdout.strip(),
            stderr=completed.stderr.strip(),
            returncode=completed.returncode,
        )
    except FileNotFoundError:
        return GitResult(False, "", "git executable not found", 127)
    except subprocess.TimeoutExpired:
        return GitResult(
            False, "", f"git command timed out: {' '.join(args)}", 124
        )


def has_git_marker(path: Path) -> bool:
    """True when path/.git exists (dir or file, covers worktrees and submodules)."""
    return (path / ".git").exists()


def is_git_worktree(path: Path) -> bool:
    """True when path is inside any Git worktree."""
    result = run_git(path, ["rev-parse", "--is-inside-work-tree"])
    return result.ok and result.stdout.strip() == "true"


def get_current_branch(repo: Path) -> str | None:
    """Return current branch name, or None if detached HEAD."""
    result = run_git(repo, ["rev-parse", "--abbrev-ref", "HEAD"])
    if not result.ok or not result.stdout:
        return None
    name = result.stdout.strip()
    if name == "HEAD":
        return None
    return name


def get_ahead_behind(repo: Path) -> tuple[int, int] | None:
    """Return (ahead, behind) counts, or None if no upstream is configured."""
    result = run_git(
        repo, ["rev-list", "--left-right", "--count", "@{upstream}...HEAD"]
    )
    if not result.ok:
        return None
    parts = result.stdout.split("\t")
    if len(parts) != 2:
        return None
    try:
        return int(parts[1]), int(parts[0])
    except ValueError:
        return None


def is_dirty(repo: Path) -> bool:
    """True if working tree has unstaged/staged/untracked changes."""
    result = run_git(repo, ["status", "--porcelain"])
    if not result.ok:
        return True
    return bool(result.stdout.strip())


def get_remotes(repo: Path) -> dict[str, str]:
    """Return dict of {remote_name: fetch_url}."""
    result = run_git(repo, ["remote", "-v"])
    remotes: dict[str, str] = {}
    if not result.ok or not result.stdout:
        return remotes
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            name = parts[0]
            url = parts[1]
            if name not in remotes:
                remotes[name] = url
    return remotes


def has_upstream(repo: Path) -> bool:
    """True if the current branch has an upstream tracking branch."""
    result = run_git(
        repo, ["rev-parse", "--abbrev-ref", "@{upstream}"], timeout=10
    )
    return result.ok and result.stdout.strip() != ""


# ---------------------------------------------------------------------------
# Repo discovery
# ---------------------------------------------------------------------------


def find_repos(root: Path, include_root: bool) -> list[Path]:
    """Scan direct child folders for Git repos. Optionally include root."""
    repos: list[Path] = []

    if include_root and is_git_worktree(root):
        repos.append(root)

    try:
        children = sorted(root.iterdir(), key=lambda p: p.name.lower())
    except PermissionError:
        children = []

    for child in children:
        if not child.is_dir():
            continue
        if child.name in DEFAULT_EXCLUDE_DIRS:
            continue
        if has_git_marker(child):
            repos.append(child)

    return repos


# ---------------------------------------------------------------------------
# Plan building
# ---------------------------------------------------------------------------


def build_plan(repo: Path, root: Path, target_branch: str) -> RepoPlan:
    name = repo.name if repo != root else root.resolve().name
    rel_path = repo.relative_to(root).as_posix() if repo != root else "."

    current_branch = get_current_branch(repo)
    if current_branch is None:
        return RepoPlan(
            name=name,
            path=rel_path,
            current_branch="DETACHED",
            upstream=None,
            ahead=None,
            behind=None,
            is_dirty=False,
            remotes={},
            eligible=False,
            skip_reason="detached HEAD",
        )

    if current_branch != target_branch:
        return RepoPlan(
            name=name,
            path=rel_path,
            current_branch=current_branch,
            upstream=None,
            ahead=None,
            behind=None,
            is_dirty=False,
            remotes={},
            eligible=False,
            skip_reason=f"current branch '{current_branch}' != target '{target_branch}'",
        )

    dirty = is_dirty(repo)
    if dirty:
        remotes = get_remotes(repo)
        return RepoPlan(
            name=name,
            path=rel_path,
            current_branch=current_branch,
            upstream=None,
            ahead=None,
            behind=None,
            is_dirty=True,
            remotes=remotes,
            eligible=False,
            skip_reason="working tree is dirty",
        )

    if not has_upstream(repo):
        remotes = get_remotes(repo)
        return RepoPlan(
            name=name,
            path=rel_path,
            current_branch=current_branch,
            upstream=None,
            ahead=None,
            behind=None,
            is_dirty=False,
            remotes=remotes,
            eligible=False,
            skip_reason="no upstream configured",
        )

    ahead_behind = get_ahead_behind(repo)
    if ahead_behind is None:
        remotes = get_remotes(repo)
        return RepoPlan(
            name=name,
            path=rel_path,
            current_branch=current_branch,
            upstream=None,
            ahead=None,
            behind=None,
            is_dirty=False,
            remotes=remotes,
            eligible=False,
            skip_reason="could not determine ahead/behind count",
        )

    ahead, behind = ahead_behind
    upstream_result = run_git(
        repo, ["rev-parse", "--abbrev-ref", "@{upstream}"], timeout=10
    )
    upstream = upstream_result.stdout.strip() if upstream_result.ok else None

    remotes = get_remotes(repo)
    if not remotes:
        return RepoPlan(
            name=name,
            path=rel_path,
            current_branch=current_branch,
            upstream=upstream,
            ahead=ahead,
            behind=behind,
            is_dirty=False,
            remotes={},
            eligible=False,
            skip_reason="no remotes configured",
        )

    if ahead <= 0:
        return RepoPlan(
            name=name,
            path=rel_path,
            current_branch=current_branch,
            upstream=upstream,
            ahead=ahead,
            behind=behind,
            is_dirty=False,
            remotes=remotes,
            eligible=False,
            skip_reason="already up to date (ahead=0)",
        )

    return RepoPlan(
        name=name,
        path=rel_path,
        current_branch=current_branch,
        upstream=upstream,
        ahead=ahead,
        behind=behind,
        is_dirty=False,
        remotes=remotes,
        eligible=True,
        skip_reason="",
    )


# ---------------------------------------------------------------------------
# Push execution
# ---------------------------------------------------------------------------


def push_branch(
    repo: Path, remote: str, branch: str, force: bool
) -> PushOutcome:
    args = ["push", remote, branch]
    if force:
        args.append("--force-with-lease")

    result = run_git(repo, args, timeout=60)
    return PushOutcome(
        remote=remote,
        ok=result.ok,
        stdout=result.stdout,
        stderr=result.stderr,
        returncode=result.returncode,
    )


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------


def _emit(lines: list[str], *parts: str) -> None:
    lines.append(" ".join(parts))


def _separator(lines: list[str], char: str = "-", width: int = 60) -> None:
    lines.append(char * width)


def render_report(
    plans: list[RepoPlan],
    branch: str,
    dry_run: bool,
    force: bool,
) -> str:
    lines: list[str] = []
    mode = "DRY-RUN" if dry_run else "EXECUTE"
    if force:
        mode += " (force-with-lease)"

    eligible = [p for p in plans if p.eligible]
    skipped = [p for p in plans if not p.eligible]
    pushed_count = sum(
        1 for p in plans if p.eligible and p.outcomes and all(o.ok for o in p.outcomes)
    )
    failed_count = sum(
        1
        for p in plans
        if p.eligible
        and p.outcomes
        and any(not o.ok for o in p.outcomes)
    )

    _separator(lines, "=")
    _emit(lines, "PUSH ALL REPOS — REPORT")
    _separator(lines, "=")
    lines.append(f"  Mode:       {mode}")
    lines.append(f"  Branch:     {branch}")
    lines.append(f"  Total:      {len(plans)} repos")
    lines.append(f"  Skipped:    {len(skipped)} repos")
    lines.append(f"  Eligible:   {len(eligible)} repos")
    if not dry_run:
        lines.append(f"  Pushed OK:  {pushed_count} repos")
        lines.append(f"  Failed:     {failed_count} repos")
    _separator(lines, "=")
    lines.append("")

    for plan in plans:
        _emit(lines, f"Repo:", plan.name, f"({plan.path})")
        _emit(lines, f"  Branch:", plan.current_branch)
        if plan.is_dirty:
            _emit(lines, "  Status: DIRTY")
        if plan.upstream:
            _emit(lines, f"  Upstream:", plan.upstream)
        if plan.ahead is not None:
            _emit(lines, f"  Ahead:", str(plan.ahead))
        if plan.behind is not None:
            _emit(lines, f"  Behind:", str(plan.behind))

        if not plan.eligible:
            _emit(lines, f"  SKIPPED:", plan.skip_reason)
            lines.append("")
            continue

        remotes_str = ", ".join(plan.remotes.keys())
        _emit(lines, f"  Remotes: [{remotes_str}]")

        if dry_run:
            for remote in plan.remotes:
                _emit(lines, f"    [DRY-RUN] would push {remote}/{plan.current_branch}")
        else:
            for outcome in plan.outcomes:
                status = "OK" if outcome.ok else "FAILED"
                detail = outcome.stderr.strip() if outcome.stderr else outcome.stdout.strip()
                if detail:
                    _emit(lines, f"    {status} push {outcome.remote}:", detail[:120])
                else:
                    _emit(lines, f"    {status} push {outcome.remote}")

        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_json(
    plans: list[RepoPlan],
    branch: str,
    dry_run: bool,
    force: bool,
) -> str:
    mode = "dry-run" if dry_run else "execute"
    eligible = [p for p in plans if p.eligible]
    skipped = [p for p in plans if not p.eligible]
    pushed_count = sum(
        1 for p in plans if p.eligible and p.outcomes and all(o.ok for o in p.outcomes)
    )
    failed_count = sum(
        1
        for p in plans
        if p.eligible
        and p.outcomes
        and any(not o.ok for o in p.outcomes)
    )

    payload: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": mode,
        "force": force,
        "branch": branch,
        "summary": {
            "total_repos": len(plans),
            "skipped": len(skipped),
            "eligible": len(eligible),
            "pushed_ok": pushed_count,
            "failed": failed_count,
        },
        "repositories": [asdict(plan) for plan in plans],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Push a branch to all remotes in nested Git repositories"
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Root directory containing nested repos (default: .)",
    )
    parser.add_argument(
        "--branch",
        default="dev",
        help="Target branch to push (default: dev)",
    )
    parser.add_argument(
        "--include-root",
        action="store_true",
        help="Also include the root repo if it is a Git worktree",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually execute git push. Without this flag, runs in dry-run mode.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Use --force-with-lease when pushing (WARNING: overwrites remote if local has diverged)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Write report to a file instead of stdout",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output report in JSON format",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()

    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Root directory not found: {root}")

    # --force warning
    if args.force:
        print(
            "============================================================================",
            file=sys.stderr,
        )
        print(
            " WARNING: --force flag is set. Will use --force-with-lease on every push.",
            file=sys.stderr,
        )
        print(
            " This can overwrite remote refs if local and remote histories have diverged.",
            file=sys.stderr,
        )
        print(
            "============================================================================",
            file=sys.stderr,
        )
        print(file=sys.stderr)

    # Discover repos
    repos = find_repos(root=root, include_root=args.include_root)

    if not repos:
        print("No Git repositories found.", file=sys.stderr)
        return 1

    # Build plans
    plans = [build_plan(repo=repo, root=root, target_branch=args.branch) for repo in repos]

    # Execute pushes if not dry-run
    if args.execute:
        for plan in plans:
            if not plan.eligible:
                continue
            repo_path = root / plan.path if plan.path != "." else root
            for remote in list(plan.remotes.keys()):
                outcome = push_branch(
                    repo=repo_path,
                    remote=remote,
                    branch=plan.current_branch,
                    force=args.force,
                )
                plan.outcomes.append(outcome)

    # Render report
    dry_run = not args.execute
    if args.json:
        output_text = render_json(
            plans=plans, branch=args.branch, dry_run=dry_run, force=args.force
        )
    else:
        output_text = render_report(
            plans=plans, branch=args.branch, dry_run=dry_run, force=args.force
        )

    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = root / output_path
        output_path.write_text(output_text, encoding="utf-8")
        print(f"Report written to: {output_path}")
    else:
        print(output_text)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
