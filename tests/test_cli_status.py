"""CLI status output around model turns and tool execution."""
from __future__ import annotations

from aicode.cli import theme
from aicode.cli.session import PrintingMiddleware
from aicode.core.types import LoopState, ToolCall, ToolResult


def _plain(text: str) -> str:
    return theme.strip_ansi(text)


def test_printing_middleware_announces_model_turn(capsys):
    mw = PrintingMiddleware()
    mw.pre_turn(LoopState(messages=[{"role": "user", "content": "hi"}]))

    out = _plain(capsys.readouterr().out)

    assert "思考中" in out
    assert "正在理解你的请求" in out


def test_printing_middleware_announces_tool_action_and_result(capsys):
    mw = PrintingMiddleware()
    call = ToolCall("tc_1", "read_file", {"path": "README.md", "limit": 20})

    mw.pre_tool(call, LoopState(messages=[]))
    mw.post_tool(call, ToolResult("tc_1", "file contents", "ok"), LoopState(messages=[]))

    out = _plain(capsys.readouterr().out)

    assert "read_file" in out
    assert "正在读取 README.md" in out
    assert "done" in out
    assert "file contents" in out
