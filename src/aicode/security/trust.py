"""
security/trust.py — 工作区信任检查

工作区需显式标记为 trusted 后 hooks 才会执行。
标记文件: <workdir>/.claude/.claude_trusted
"""
from __future__ import annotations

from pathlib import Path


def is_workspace_trusted(workdir: Path) -> bool:
    """检查工作区是否已被明确信任。"""
    return (workdir / ".claude" / ".claude_trusted").exists()


def mark_workspace_trusted(workdir: Path) -> None:
    """将工作区标记为 trusted（创建标记文件）。"""
    marker = workdir / ".claude" / ".claude_trusted"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()
