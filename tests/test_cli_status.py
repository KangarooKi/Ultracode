"""CLI status output around model turns and tool execution."""
from __future__ import annotations

import io

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


class _TtyBuffer(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_model_status_is_transient_on_tty(monkeypatch):
    buf = _TtyBuffer()
    monkeypatch.setattr("sys.stdout", buf)
    mw = PrintingMiddleware()

    mw.pre_turn(LoopState(messages=[{"role": "user", "content": "hi"}]))
    mw.post_model(LoopState(messages=[]))

    out = _plain(buf.getvalue())
    assert "思考中" in out
    assert "\r" in out
    assert "\033[2K" in buf.getvalue()


def test_stream_output_clears_model_status(mock_llm, monkeypatch):
    from aicode.core.loop import AgentLoopConfig, run_agent_loop
    from aicode.core.tools.registry import ToolRegistry
    from tests.conftest import make_llm_response

    buf = _TtyBuffer()
    monkeypatch.setattr("sys.stdout", buf)
    mock_llm.set_responses(make_llm_response(content="Hello"))
    cfg = AgentLoopConfig(
        llm_client=mock_llm,
        model="m",
        registry=ToolRegistry(),
        system_prompt_fn=lambda: "s",
        middleware=[PrintingMiddleware()],
        stream=True,
    )

    run_agent_loop(cfg, LoopState(messages=[{"role": "user", "content": "hi"}]))

    out = _plain(buf.getvalue())
    assert "思考中" in out
    assert "Hello" in out
    assert "\r\033[2K" in buf.getvalue()
