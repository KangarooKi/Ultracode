"""
worktrees/git.py — git worktree 列表（供 CLI 与工具共用）
"""
from __future__ import annotations

import subprocess
from pathlib import Path


def list_worktrees(repo_root: Path) -> str:
    """在 repo_root 执行 `git worktree list`，失败则返回 Error 前缀说明。"""
    try:
        r = subprocess.run(
            ["git", "-C", str(repo_root), "worktree", "list"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        return f"Error: cannot run git worktree: {exc}"

    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        return f"Error: git worktree list failed ({r.returncode}): {err or 'unknown'}"

    out = r.stdout.strip()
    return out if out else "(no worktrees)"
