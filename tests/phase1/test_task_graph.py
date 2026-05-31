"""
tests/phase1/test_task_graph.py

测试 planning/task_graph.py：
1. create — 任务创建、ID 自增
2. update — 状态变更、owner、依赖关系
3. _clear_dependency — 完成任务时清除 blockedBy
4. list_all — 格式输出
5. register_task_tools — 工具注册到 ToolRegistry
"""
from __future__ import annotations

import json

import pytest

from aicode.core.tools.registry import ToolRegistry
from aicode.planning.task_graph import TaskManager, register_task_tools


@pytest.fixture
def tm(tmp_path):
    return TaskManager(tmp_path / ".tasks")


class TestTaskManagerCreate:
    def test_creates_task_file(self, tm, tmp_path):
        tm.create("Fix bug")
        assert (tmp_path / ".tasks" / "task_1.json").exists()

    def test_id_auto_increments(self, tm):
        r1 = json.loads(tm.create("A"))
        r2 = json.loads(tm.create("B"))
        assert r2["id"] == r1["id"] + 1

    def test_default_status_pending(self, tm):
        t = json.loads(tm.create("X"))
        assert t["status"] == "pending"
        assert t["blockedBy"] == []

    def test_id_continues_after_reload(self, tmp_path):
        tm1 = TaskManager(tmp_path / ".tasks")
        tm1.create("A")
        tm1.create("B")
        tm2 = TaskManager(tmp_path / ".tasks")
        t = json.loads(tm2.create("C"))
        assert t["id"] == 3


class TestTaskManagerUpdate:
    def test_update_status(self, tm):
        tm.create("Task")
        t = json.loads(tm.update(1, status="in_progress"))
        assert t["status"] == "in_progress"

    def test_invalid_status_raises(self, tm):
        tm.create("Task")
        with pytest.raises(ValueError, match="Invalid status"):
            tm.update(1, status="running")

    def test_nonexistent_task_raises(self, tm):
        with pytest.raises(ValueError, match="not found"):
            tm.update(999, status="completed")

    def test_update_owner(self, tm):
        tm.create("Task")
        t = json.loads(tm.update(1, owner="alice"))
        assert t["owner"] == "alice"

    def test_add_blocked_by(self, tm):
        tm.create("A")
        tm.create("B")
        t = json.loads(tm.update(2, add_blocked_by=[1]))
        assert 1 in t["blockedBy"]

    def test_add_blocks_bidirectional(self, tm):
        tm.create("A")
        tm.create("B")
        tm.update(1, add_blocks=[2])
        b_task = json.loads(tm.get(2))
        assert 1 in b_task["blockedBy"]


class TestClearDependency:
    def test_completing_task_clears_blocked_by(self, tm):
        tm.create("A")
        tm.create("B")
        tm.update(2, add_blocked_by=[1])
        tm.update(1, status="completed")
        b_task = json.loads(tm.get(2))
        assert 1 not in b_task["blockedBy"]


class TestListAll:
    def test_empty(self, tm):
        assert tm.list_all() == "No tasks."

    def test_markers(self, tm):
        tm.create("Pending task")
        tm.update(1, status="in_progress")
        out = tm.list_all()
        assert "[>]" in out
        assert "#1" in out

    def test_blocked_shown(self, tm):
        tm.create("A")
        tm.create("B")
        tm.update(2, add_blocked_by=[1])
        out = tm.list_all()
        assert "blocked by" in out


class TestRegisterTaskTools:
    def test_tools_registered(self, tm):
        reg = ToolRegistry()
        register_task_tools(reg, tm)
        names = set(reg.names())
        assert {"task_create", "task_update", "task_list", "task_get"}.issubset(names)

    def test_task_create_via_dispatch(self, tm):
        reg = ToolRegistry()
        register_task_tools(reg, tm)
        out = reg.dispatch("task_create", {"subject": "hello"})
        assert "hello" in out

    def test_task_list_via_dispatch(self, tm):
        reg = ToolRegistry()
        register_task_tools(reg, tm)
        reg.dispatch("task_create", {"subject": "T1"})
        out = reg.dispatch("task_list", {})
        assert "T1" in out
