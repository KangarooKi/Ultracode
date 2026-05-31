"""
tests/phase2/test_hooks.py

测试 hooks/manager.py：
1. 工作区不受信任 → 钩子不执行
2. 退出码 0 → 正常通过
3. 退出码 1 → blocked=True
4. 退出码 2 → message 注入
5. HookMiddleware.pre_tool 拦截
6. HookMiddleware.post_tool 追加消息
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aicode.core.types import LoopState, ToolCall, ToolResult
from aicode.hooks.manager import HookManager, HookMiddleware
from aicode.security.trust import mark_workspace_trusted


@pytest.fixture
def trusted_workdir(tmp_path):
    mark_workspace_trusted(tmp_path)
    return tmp_path


def _make_hooks_json(workdir: Path, hooks: dict) -> Path:
    p = workdir / ".hooks.json"
    p.write_text(json.dumps({"hooks": hooks}), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# 工作区信任检查
# ---------------------------------------------------------------------------

class TestWorkspaceTrust:
    def test_untrusted_hooks_not_run(self, tmp_path):
        _make_hooks_json(tmp_path, {"PreToolUse": [{"command": "exit 1"}]})
        mgr = HookManager(workdir=tmp_path)
        r = mgr.run_hooks("PreToolUse", {"tool_name": "bash"})
        assert not r["blocked"]

    def test_sdk_mode_bypasses_trust(self, tmp_path):
        """sdk_mode=True 时即使没有信任标记也执行钩子。"""
        _make_hooks_json(tmp_path, {"PreToolUse": [{"command": "exit 0"}]})
        mgr = HookManager(workdir=tmp_path, sdk_mode=True)
        r = mgr.run_hooks("PreToolUse", {"tool_name": "bash"})
        assert not r["blocked"]


# ---------------------------------------------------------------------------
# 退出码语义
# ---------------------------------------------------------------------------

class TestHookExitCodes:
    def test_exit_0_continues(self, trusted_workdir):
        _make_hooks_json(trusted_workdir, {
            "PreToolUse": [{"command": "exit 0"}]
        })
        mgr = HookManager(workdir=trusted_workdir)
        r = mgr.run_hooks("PreToolUse", {"tool_name": "bash"})
        assert not r["blocked"]
        assert r["messages"] == []

    def test_exit_1_blocks(self, trusted_workdir):
        # 用 python 子进程，避免 Windows cmd 对 >&2; exit 1 的解析与 bash 不一致
        _make_hooks_json(trusted_workdir, {
            "PreToolUse": [{
                "command": "python -c \"import sys; print('forbidden', file=sys.stderr); sys.exit(1)\"",
            }]
        })
        mgr = HookManager(workdir=trusted_workdir)
        r = mgr.run_hooks("PreToolUse", {"tool_name": "bash"})
        assert r["blocked"]
        assert "forbidden" in r["block_reason"]

    def test_exit_2_injects_message(self, trusted_workdir):
        _make_hooks_json(trusted_workdir, {
            "PreToolUse": [{
                "command": "python -c \"import sys; print('note this', file=sys.stderr); sys.exit(2)\"",
            }]
        })
        mgr = HookManager(workdir=trusted_workdir)
        r = mgr.run_hooks("PreToolUse", {"tool_name": "bash"})
        assert not r["blocked"]
        assert any("note this" in m for m in r["messages"])

    def test_matcher_filters_by_tool(self, trusted_workdir):
        """matcher='read_file' 时，bash 调用不触发该钩子。"""
        _make_hooks_json(trusted_workdir, {
            "PreToolUse": [{
                "matcher": "read_file",
                "command": "python -c \"import sys; sys.exit(1)\"",
            }]
        })
        mgr = HookManager(workdir=trusted_workdir)
        r = mgr.run_hooks("PreToolUse", {"tool_name": "bash"})
        assert not r["blocked"]


# ---------------------------------------------------------------------------
# HookMiddleware
# ---------------------------------------------------------------------------

class TestHookMiddleware:
    def test_pre_tool_blocked_returns_tool_result(self, trusted_workdir):
        _make_hooks_json(trusted_workdir, {
            "PreToolUse": [{
                "command": "python -c \"import sys; print('stop', file=sys.stderr); sys.exit(1)\"",
            }]
        })
        mgr = HookManager(workdir=trusted_workdir)
        mw = HookMiddleware(mgr)
        call = ToolCall(id="x", name="bash", arguments={"command": "ls"})
        state = LoopState(messages=[])
        result = mw.pre_tool(call, state)
        assert result is not None
        assert result.status == "blocked"
        assert "stop" in result.content

    def test_pre_tool_allowed_returns_none(self, trusted_workdir):
        _make_hooks_json(trusted_workdir, {
            "PreToolUse": [{"command": "exit 0"}]
        })
        mgr = HookManager(workdir=trusted_workdir)
        mw = HookMiddleware(mgr)
        call = ToolCall(id="y", name="bash", arguments={"command": "ls"})
        state = LoopState(messages=[])
        result = mw.pre_tool(call, state)
        assert result is None

    def test_post_tool_appends_message(self, trusted_workdir):
        _make_hooks_json(trusted_workdir, {
            "PostToolUse": [{
                "command": "python -c \"import sys; print('post note', file=sys.stderr); sys.exit(2)\"",
            }]
        })
        mgr = HookManager(workdir=trusted_workdir)
        mw = HookMiddleware(mgr)
        call = ToolCall(id="z", name="bash", arguments={"command": "ls"})
        result = ToolResult(tool_call_id="z", content="output")
        state = LoopState(messages=[])
        mw.post_tool(call, result, state)
        assert "post note" in result.content
