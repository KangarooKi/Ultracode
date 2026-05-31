"""worktrees/tools.py — 向 ToolRegistry 注册 git_worktree_list。"""
from __future__ import annotations

from pathlib import Path

from aicode.core.tools.registry import ToolRegistry

from .git import list_worktrees


def register_worktree_tool(registry: ToolRegistry, workdir: Path) -> None:
    from aicode.core.tools.schemas import git_worktree_list_schema

    def _handler(**_kw: object) -> str:
        return list_worktrees(workdir)

    registry.register("git_worktree_list", _handler, git_worktree_list_schema())
