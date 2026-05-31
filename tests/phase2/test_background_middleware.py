"""background 工具注册与中间件注入通知。"""
from __future__ import annotations

import json

from aicode.background.manager import BackgroundManager
from aicode.background.middleware import BackgroundMiddleware, register_background_tools
from aicode.core.tools.registry import ToolRegistry
from aicode.core.types import LoopState


def test_register_background_tools(tmp_path):
    reg = ToolRegistry()
    mgr = BackgroundManager(tmp_path)
    register_background_tools(reg, mgr)
    assert "background_run" in reg.names()
    assert "background_check" in reg.names()
    assert "background_cancel" in reg.names()


def test_background_middleware_drains_into_messages(tmp_path):
    mgr = BackgroundManager(tmp_path)
    payload = {"task_id": "abc", "status": "completed", "preview": "done"}
    mgr._notification_queue.push(
        json.dumps(payload, ensure_ascii=False),
        priority="high",
        key="bg:test",
    )
    mw = BackgroundMiddleware(mgr)
    state = LoopState(messages=[])
    mw.pre_turn(state)
    assert state.messages
    assert "Background" in state.messages[0]["content"]
    assert "abc" in state.messages[0]["content"]
