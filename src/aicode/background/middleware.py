"""
background/middleware.py — LoopMiddleware + 工具注册

pre_turn：将后台任务完成通知注入为 user 消息，便于模型感知异步结果。
"""
from __future__ import annotations

import json

from aicode.core.loop import NoopMiddleware
from aicode.core.tools.registry import ToolRegistry
from aicode.core.types import LoopState

from .manager import BackgroundManager


class BackgroundMiddleware(NoopMiddleware):
    def __init__(self, manager: BackgroundManager) -> None:
        self._manager = manager

    def pre_turn(self, state: LoopState) -> None:
        for item in self._manager.drain_notifications():
            line = json.dumps(item, ensure_ascii=False)
            state.messages.append({
                "role": "user",
                "content": (
                    "[Background task finished]\n"
                    f"{line}\n"
                    "Summarize or continue as appropriate."
                ),
            })


def register_background_tools(registry: ToolRegistry, manager: BackgroundManager) -> None:
    from aicode.core.tools.schemas import (
        background_cancel_schema,
        background_check_schema,
        background_run_schema,
    )

    registry.register(
        "background_run",
        lambda **kw: manager.run(kw["command"], kw.get("label")),
        background_run_schema(),
    )
    registry.register(
        "background_check",
        lambda **kw: manager.check(kw.get("task_id")),
        background_check_schema(),
    )
    registry.register(
        "background_cancel",
        lambda **kw: manager.cancel(kw["task_id"]),
        background_cancel_schema(),
    )
