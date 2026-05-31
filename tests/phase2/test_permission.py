"""
tests/phase2/test_permission.py

测试 security/permission.py + security/validator.py：
1. BashSecurityValidator — severity / describe_failures
2. PermissionManager.check — deny/plan/auto/allow/ask 各路径
3. PermissionManager._matches — tool/path/content glob
4. PermissionMiddleware.pre_tool — 拦截/放行
"""
from __future__ import annotations

import pytest

from aicode.core.types import LoopState, ToolCall
from aicode.security.permission import (
    DEFAULT_RULES,
    PermissionManager,
    PermissionMiddleware,
)
from aicode.security.validator import BashSecurityValidator


# ---------------------------------------------------------------------------
# BashSecurityValidator
# ---------------------------------------------------------------------------

class TestBashSecurityValidator:
    def test_clean_command(self):
        v = BashSecurityValidator()
        assert v.severity("echo hello") == "clean"
        assert v.is_safe("echo hello")

    def test_sudo_is_severe(self):
        v = BashSecurityValidator()
        assert v.severity("sudo apt install vim") == "severe"

    def test_rm_rf_is_severe(self):
        v = BashSecurityValidator()
        assert v.severity("rm -rf /tmp/foo") == "severe"

    def test_shell_metachar_is_warn(self):
        v = BashSecurityValidator()
        # 单独的 ; 属于 warn 级
        assert v.severity("echo a; echo b") == "warn"

    def test_cmd_substitution_is_warn(self):
        v = BashSecurityValidator()
        assert v.severity("echo $(whoami)") == "warn"

    def test_describe_failures_nonempty_when_flagged(self):
        v = BashSecurityValidator()
        desc = v.describe_failures("sudo rm -rf /")
        assert "sudo" in desc or "rm_rf" in desc


# ---------------------------------------------------------------------------
# PermissionManager.check
# ---------------------------------------------------------------------------

class TestPermissionManagerCheck:
    def test_sudo_denied(self):
        pm = PermissionManager()
        r = pm.check("bash", {"command": "sudo apt update"})
        assert r["behavior"] == "deny"

    def test_rm_rf_denied(self):
        pm = PermissionManager()
        r = pm.check("bash", {"command": "rm -rf /tmp"})
        assert r["behavior"] == "deny"

    def test_safe_bash_goes_to_ask_or_allow(self):
        pm = PermissionManager()
        r = pm.check("bash", {"command": "echo hello"})
        # 默认模式下无匹配 allow rule → ask
        assert r["behavior"] in ("ask", "allow")

    def test_read_file_always_allowed(self):
        pm = PermissionManager()
        r = pm.check("read_file", {"path": "README.md"})
        assert r["behavior"] == "allow"

    def test_plan_mode_blocks_write(self):
        pm = PermissionManager(mode="plan")
        r = pm.check("write_file", {"path": "a.txt", "content": "x"})
        assert r["behavior"] == "deny"
        assert "plan mode" in r["reason"].lower()

    def test_plan_mode_allows_read(self):
        pm = PermissionManager(mode="plan")
        r = pm.check("read_file", {"path": "a.txt"})
        assert r["behavior"] == "allow"

    def test_auto_mode_read_approved(self):
        pm = PermissionManager(mode="auto")
        r = pm.check("read_file", {"path": "f.py"})
        assert r["behavior"] == "allow"

    def test_plan_mode_blocks_mcp(self):
        pm = PermissionManager(mode="plan")
        r = pm.check("mcp__srv__anything", {})
        assert r["behavior"] == "deny"

    def test_auto_mode_mcp_read_like(self):
        pm = PermissionManager(mode="auto")
        r = pm.check("mcp__srv__read_file", {})
        assert r["behavior"] == "allow"

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError):
            PermissionManager(mode="superuser")


# ---------------------------------------------------------------------------
# PermissionManager._matches
# ---------------------------------------------------------------------------

class TestPermissionManagerMatches:
    def test_tool_wildcard(self):
        pm = PermissionManager()
        rule = {"tool": "*", "behavior": "deny"}
        assert pm._matches(rule, "bash", {})
        assert pm._matches(rule, "read_file", {})

    def test_tool_exact(self):
        pm = PermissionManager()
        rule = {"tool": "bash", "behavior": "deny"}
        assert pm._matches(rule, "bash", {})
        assert not pm._matches(rule, "read_file", {})

    def test_path_glob(self):
        pm = PermissionManager()
        rule = {"tool": "read_file", "path": "*.py", "behavior": "deny"}
        assert pm._matches(rule, "read_file", {"path": "main.py"})
        assert not pm._matches(rule, "read_file", {"path": "main.txt"})

    def test_content_glob(self):
        pm = PermissionManager()
        rule = {"tool": "bash", "content": "sudo *", "behavior": "deny"}
        assert pm._matches(rule, "bash", {"command": "sudo apt update"})
        assert not pm._matches(rule, "bash", {"command": "echo hi"})


# ---------------------------------------------------------------------------
# ask_user 内容预览
# ---------------------------------------------------------------------------


class TestAskUserWritePreview:
    def test_write_file_shows_content_before_prompt(self, capsys, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _="": "n")
        pm = PermissionManager(mode="default")
        assert not pm.ask_user(
            "write_file",
            {"path": "x.py", "content": "print(1)\nprint(2)\n"},
        )
        out = capsys.readouterr().out
        assert "内容预览" in out
        assert "print(1)" in out

    def test_bash_uses_one_line_summary_not_code_preview(self, capsys, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _="": "n")
        pm = PermissionManager(mode="default")
        assert not pm.ask_user("bash", {"command": "echo hi"})
        out = capsys.readouterr().out
        assert "echo hi" in out
        assert "内容预览" not in out


# ---------------------------------------------------------------------------
# PermissionMiddleware
# ---------------------------------------------------------------------------

class TestPermissionMiddleware:
    def test_deny_returns_tool_result(self):
        pm = PermissionManager(mode="plan")
        mw = PermissionMiddleware(pm)
        call = ToolCall(id="t1", name="write_file", arguments={"path": "a.txt", "content": "x"})
        state = LoopState(messages=[])
        result = mw.pre_tool(call, state)
        assert result is not None
        assert result.status == "denied"
        assert "denied" in result.content.lower()

    def test_allow_returns_none(self):
        pm = PermissionManager(mode="plan")
        mw = PermissionMiddleware(pm)
        call = ToolCall(id="t2", name="read_file", arguments={"path": "f.py"})
        state = LoopState(messages=[])
        result = mw.pre_tool(call, state)
        assert result is None
