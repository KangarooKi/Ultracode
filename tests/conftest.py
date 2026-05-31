"""
tests/conftest.py — 全局测试夹具

提供：
- tmp_workdir: 隔离的临时工作目录
- mock_llm_client: 可配置响应的 mock OpenAI 客户端
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def pytest_configure(config: pytest.Config) -> None:
    # 测试里 run_bash 真跑子进程：缩短超时，避免 Windows/杀软下偶发挂死占满 120s
    os.environ.setdefault("AICODE_BASH_TIMEOUT", "30")


@pytest.fixture
def tmp_workdir(tmp_path: Path) -> Path:
    """每个测试独立的临时工作目录。"""
    return tmp_path


def _make_assistant_message(content: str | None = None, tool_calls: list | None = None):
    """构造一个 mock assistant 消息对象。"""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls or []

    if tool_calls:
        def model_dump(exclude_none=False):
            d = {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in tool_calls
                ],
            }
            if content is not None:
                d["content"] = content
            return d
        msg.model_dump = model_dump
    else:
        def model_dump(exclude_none=False):
            d = {"role": "assistant", "content": content or ""}
            return d
        msg.model_dump = model_dump

    return msg


def make_tool_call(name: str, arguments: dict, call_id: str = "tc_001"):
    """构造一个 mock ToolCall 对象（OpenAI SDK 格式）。"""
    tc = MagicMock()
    tc.id = call_id
    tc.function = MagicMock()
    tc.function.name = name
    tc.function.arguments = json.dumps(arguments)
    return tc


def make_llm_response(content: str | None = None, tool_calls: list | None = None):
    """构造一个 mock LLM response 对象。"""
    resp = MagicMock()
    choice = MagicMock()
    choice.message = _make_assistant_message(content, tool_calls)
    choice.finish_reason = "stop"
    resp.choices = [choice]
    return resp


def _blocking_response_as_stream(resp):
    """把非流式 mock 响应转成可迭代 chunk 序列（供 stream=True 使用）。"""
    choice0 = resp.choices[0]
    msg = choice0.message
    content = getattr(msg, "content", None)
    tcalls = list(getattr(msg, "tool_calls", None) or [])
    finish = getattr(choice0, "finish_reason", None) or "stop"

    def gen():
        if content:
            d = MagicMock()
            d.content = content
            d.tool_calls = None
            c0 = MagicMock()
            c0.delta = d
            c0.finish_reason = None
            ch = MagicMock()
            ch.choices = [c0]
            yield ch
        for i, tc in enumerate(tcalls):
            d = MagicMock()
            d.content = None
            stc = MagicMock()
            stc.index = i
            stc.id = tc.id
            fn = tc.function
            stc.function = MagicMock()
            stc.function.name = fn.name
            stc.function.arguments = fn.arguments
            d.tool_calls = [stc]
            c0 = MagicMock()
            c0.delta = d
            c0.finish_reason = None
            ch = MagicMock()
            ch.choices = [c0]
            yield ch
        d = MagicMock()
        d.content = None
        d.tool_calls = None
        c0 = MagicMock()
        c0.delta = d
        c0.finish_reason = finish
        ch = MagicMock()
        ch.choices = [c0]
        yield ch

    return gen()


@pytest.fixture
def mock_llm():
    """返回一个 mock OpenAI client，响应序列通过 .set_responses() 配置。"""
    client = MagicMock()
    responses = []

    def create_side_effect(*args, **kwargs):
        stream = kwargs.get("stream", False)
        if responses:
            resp = responses.pop(0)
        else:
            resp = make_llm_response(content="Done.")
        if stream:
            return _blocking_response_as_stream(resp)
        return resp

    client.chat.completions.create.side_effect = create_side_effect
    client._responses = responses  # 供测试注入

    def set_responses(*resps):
        responses.clear()
        responses.extend(resps)

    client.set_responses = set_responses
    return client
