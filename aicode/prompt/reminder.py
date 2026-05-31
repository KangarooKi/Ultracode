"""
prompt/reminder.py — 逐轮动态提醒注入

系统提醒以 user 角色消息注入（不污染稳定的 system prompt）。
供 Middleware 或 REPL 调用。
"""
from __future__ import annotations

import datetime
from pathlib import Path


def build_system_reminder(
    todo_reminder: str | None = None,
    extra: str | None = None,
) -> str | None:
    """
    组装逐轮提醒消息。若无内容则返回 None。
    """
    parts: list[str] = []
    if todo_reminder:
        parts.append(todo_reminder)
    if extra:
        parts.append(extra)
    if not parts:
        return None
    return "\n".join(parts)
