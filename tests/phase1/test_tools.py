"""
tests/phase1/test_tools.py

测试 core/tools/base.py：
1. safe_path — 路径逃逸防护
2. run_bash  — 危险命令拦截 + 正常命令执行
3. run_read  — 正常读取 + limit 截断
4. run_write — 写入 + 目录自动创建
5. run_edit  — 正常替换 + 文本不存在时报错
6. ToolRegistry — 注册/分发/未知工具
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from aicode.core.tools.base import (
    _decode_shell_output,
    run_bash,
    run_edit,
    run_read,
    run_write,
    safe_path,
)
from aicode.core.tools.registry import ToolRegistry, build_base_registry


# ---------------------------------------------------------------------------
# safe_path
# ---------------------------------------------------------------------------

class TestSafePath:
    def test_normal_relative_path(self, tmp_path):
        p = safe_path("foo/bar.txt", workdir=tmp_path)
        assert p == tmp_path / "foo" / "bar.txt"

    def test_path_escape_raises(self, tmp_path):
        with pytest.raises(ValueError, match="escapes workspace"):
            safe_path("../../etc/passwd", workdir=tmp_path)

    def test_absolute_path_inside_workdir(self, tmp_path):
        p = safe_path(str(tmp_path / "sub" / "file.py"), workdir=tmp_path)
        assert p.is_relative_to(tmp_path)

    def test_absolute_path_outside_raises(self, tmp_path):
        with pytest.raises(ValueError):
            safe_path("/etc/passwd", workdir=tmp_path)


# ---------------------------------------------------------------------------
# run_bash
# ---------------------------------------------------------------------------

def test_decode_shell_output_gbk():
    raw = "测试输出".encode("gbk")
    assert "测" in _decode_shell_output(raw)


class TestRunBash:
    def test_dangerous_command_blocked(self, tmp_path):
        out = run_bash("sudo rm -rf /", workdir=tmp_path)
        assert out.startswith("Error: Dangerous command blocked")

    def test_normal_echo(self, tmp_path):
        out = run_bash("echo hello", workdir=tmp_path)
        assert "hello" in out

    def test_timeout_returns_error(self, tmp_path, monkeypatch):
        """必须 patch aicode.core.tools.base.subprocess：run_bash 已绑定该模块的 subprocess。"""
        import subprocess

        from aicode.core.tools import base as tools_base

        def fake_run(*_a, **_kw):
            raise subprocess.TimeoutExpired(cmd="cmd", timeout=1)

        monkeypatch.setattr(tools_base.subprocess, "run", fake_run)
        out = run_bash("echo hi", workdir=tmp_path)
        assert "timed out" in out.lower()

    def test_output_truncated_at_50000(self, tmp_path):
        # 用当前解释器，避免 PATH 里 python 指向商店版/弹窗导致卡住
        out = run_bash(
            f'"{sys.executable}" -c "print(\'x\' * 60000)"',
            workdir=tmp_path,
        )
        assert len(out) <= 50000


# ---------------------------------------------------------------------------
# run_read
# ---------------------------------------------------------------------------

class TestRunRead:
    def test_read_existing_file(self, tmp_path):
        (tmp_path / "hello.txt").write_text("line1\nline2\nline3")
        out = run_read("hello.txt", workdir=tmp_path)
        assert "line1" in out and "line3" in out

    def test_read_with_limit(self, tmp_path):
        (tmp_path / "big.txt").write_text("\n".join(f"line{i}" for i in range(100)))
        out = run_read("big.txt", limit=5, workdir=tmp_path)
        assert "more lines" in out
        assert "line4" in out
        assert "line5" not in out

    def test_read_nonexistent_file(self, tmp_path):
        out = run_read("nope.txt", workdir=tmp_path)
        assert out.startswith("Error:")

    def test_read_escape_blocked(self, tmp_path):
        out = run_read("../../etc/hosts", workdir=tmp_path)
        assert out.startswith("Error:")


# ---------------------------------------------------------------------------
# run_write
# ---------------------------------------------------------------------------

class TestRunWrite:
    def test_write_creates_file(self, tmp_path):
        run_write("new.txt", "hello world", workdir=tmp_path)
        assert (tmp_path / "new.txt").read_text() == "hello world"

    def test_write_creates_parent_dirs(self, tmp_path):
        run_write("a/b/c.txt", "deep", workdir=tmp_path)
        assert (tmp_path / "a" / "b" / "c.txt").exists()

    def test_write_escape_blocked(self, tmp_path):
        out = run_write("../../evil.txt", "hacked", workdir=tmp_path)
        assert out.startswith("Error:")


# ---------------------------------------------------------------------------
# run_edit
# ---------------------------------------------------------------------------

class TestRunEdit:
    def test_edit_replaces_first_occurrence(self, tmp_path):
        (tmp_path / "f.txt").write_text("aaa bbb aaa")
        run_edit("f.txt", "aaa", "XXX", workdir=tmp_path)
        assert (tmp_path / "f.txt").read_text() == "XXX bbb aaa"

    def test_edit_text_not_found(self, tmp_path):
        (tmp_path / "f.txt").write_text("hello")
        out = run_edit("f.txt", "nothere", "x", workdir=tmp_path)
        assert out.startswith("Error:")

    def test_edit_escape_blocked(self, tmp_path):
        out = run_edit("../../f.txt", "a", "b", workdir=tmp_path)
        assert out.startswith("Error:")


# ---------------------------------------------------------------------------
# ToolRegistry
# ---------------------------------------------------------------------------

class TestToolRegistry:
    def test_register_and_dispatch(self):
        reg = ToolRegistry()
        reg.register("greet", lambda **kw: f"Hello, {kw['name']}!", {
            "type": "function",
            "function": {"name": "greet", "parameters": {}}
        })
        assert reg.dispatch("greet", {"name": "World"}) == "Hello, World!"

    def test_unknown_tool_returns_error(self):
        reg = ToolRegistry()
        out = reg.dispatch("nonexistent", {})
        assert "unknown tool" in out.lower()

    def test_handler_exception_returns_error(self):
        reg = ToolRegistry()
        reg.register("boom", lambda **kw: (_ for _ in ()).throw(RuntimeError("kaboom")), {
            "type": "function", "function": {"name": "boom", "parameters": {}}
        })
        out = reg.dispatch("boom", {})
        assert "kaboom" in out

    def test_get_schemas_returns_all(self):
        reg = build_base_registry()
        names = [s["function"]["name"] for s in reg.get_schemas()]
        assert set(names) == {"bash", "read_file", "write_file", "edit_file"}

    def test_register_overwrite(self):
        reg = ToolRegistry()
        schema = {"type": "function", "function": {"name": "t", "parameters": {}}}
        reg.register("t", lambda **kw: "v1", schema)
        reg.register("t", lambda **kw: "v2", schema)
        assert reg.dispatch("t", {}) == "v2"
        # schema 不重复
        assert len([s for s in reg.get_schemas() if s["function"]["name"] == "t"]) == 1
