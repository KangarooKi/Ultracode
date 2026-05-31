"""
tests/phase1/test_todo.py

测试 planning/todo.py：
1. TodoManager.update — 正常更新、最多12项、多个 in_progress 报错
2. TodoManager.render — 各状态标记正确
3. TodoManager.reminder — 间隔机制
4. TodoMiddleware.post_turn — 注入提醒消息
"""
from __future__ import annotations

import pytest

from aicode.core.types import LoopState, ToolCall, ToolResult
from aicode.planning.todo import PLAN_REMINDER_INTERVAL, TodoManager, TodoMiddleware


def _items(*pairs):
    """快捷构造 items list。pairs = (content, status)..."""
    return [{"content": c, "status": s} for c, s in pairs]


class TestTodoManagerUpdate:
    def test_normal_update(self):
        mgr = TodoManager()
        result = mgr.update(_items(("write tests", "in_progress"), ("run tests", "pending")))
        assert "[>]" in result
        assert "[ ]" in result

    def test_exceeds_12_items_raises(self):
        mgr = TodoManager()
        with pytest.raises(ValueError, match="max 12"):
            mgr.update(_items(*[(f"task{i}", "pending") for i in range(13)]))

    def test_invalid_status_raises(self):
        mgr = TodoManager()
        with pytest.raises(ValueError, match="invalid status"):
            mgr.update([{"content": "foo", "status": "running"}])

    def test_multiple_in_progress_raises(self):
        mgr = TodoManager()
        with pytest.raises(ValueError, match="Only one"):
            mgr.update(_items(("a", "in_progress"), ("b", "in_progress")))

    def test_empty_content_raises(self):
        mgr = TodoManager()
        with pytest.raises(ValueError, match="content is required"):
            mgr.update([{"content": "  ", "status": "pending"}])

    def test_rounds_since_update_resets(self):
        mgr = TodoManager()
        mgr.state.rounds_since_update = 5
        mgr.update(_items(("x", "pending")))
        assert mgr.state.rounds_since_update == 0


class TestTodoManagerRender:
    def test_markers(self):
        mgr = TodoManager()
        mgr.update(_items(
            ("done", "completed"),
            ("doing", "in_progress"),
            ("todo", "pending"),
        ))
        rendered = mgr.render()
        assert "[x]" in rendered
        assert "[>]" in rendered
        assert "[ ]" in rendered

    def test_active_form_shown(self):
        mgr = TodoManager()
        mgr.update([{"content": "run", "status": "in_progress", "active_form": "Running tests"}])
        assert "Running tests" in mgr.render()

    def test_progress_count(self):
        mgr = TodoManager()
        mgr.update(_items(("a", "completed"), ("b", "pending")))
        assert "(1/2)" in mgr.render()

    def test_empty_plan(self):
        mgr = TodoManager()
        assert "No session plan" in mgr.render()


class TestTodoManagerReminder:
    def test_no_reminder_when_no_plan(self):
        mgr = TodoManager()
        assert mgr.reminder() is None

    def test_no_reminder_before_interval(self):
        mgr = TodoManager()
        mgr.update(_items(("x", "pending")))
        mgr.state.rounds_since_update = PLAN_REMINDER_INTERVAL - 1
        assert mgr.reminder() is None

    def test_reminder_after_interval(self):
        mgr = TodoManager()
        mgr.update(_items(("x", "pending")))
        mgr.state.rounds_since_update = PLAN_REMINDER_INTERVAL
        r = mgr.reminder()
        assert r is not None
        assert "Refresh" in r


class TestTodoMiddleware:
    def test_post_turn_injects_reminder(self):
        mgr = TodoManager()
        mgr.update(_items(("x", "pending")))
        mgr.state.rounds_since_update = PLAN_REMINDER_INTERVAL

        mw = TodoMiddleware(mgr)
        state = LoopState(messages=[])
        mw.post_turn(state)

        injected = [m for m in state.messages if m.get("role") == "user"]
        assert len(injected) == 1
        assert "Refresh" in injected[0]["content"]

    def test_post_tool_todo_resets_counter(self):
        mgr = TodoManager()
        mgr.update(_items(("x", "pending")))
        mgr.state.rounds_since_update = 10

        mw = TodoMiddleware(mgr)
        call = ToolCall(id="id", name="todo", arguments={})
        result = ToolResult(tool_call_id="id", content="ok")
        state = LoopState(messages=[])
        mw.post_tool(call, result, state)

        assert mgr.state.rounds_since_update == 0
