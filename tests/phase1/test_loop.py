"""
tests/phase1/test_loop.py

测试 core/loop.py：
1. 无工具调用 → 循环立即结束
2. 一次工具调用 → dispatch → 结果追加到 messages
3. middleware.pre_tool 拦截工具调用
4. middleware 生命周期调用顺序
5. max_turns 防止无限循环
"""
from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from aicode.core.loop import AgentLoopConfig, NoopMiddleware, run_agent_loop
from aicode.core.tools.registry import ToolRegistry
from aicode.core.types import LoopState, ToolCall, ToolResult

from tests.conftest import make_llm_response, make_tool_call


def _make_config(mock_llm, registry=None, middleware=None):
    if registry is None:
        registry = ToolRegistry()
        registry.register(
            "echo",
            lambda **kw: f"echoed: {kw.get('msg', '')}",
            {"type": "function", "function": {"name": "echo", "parameters": {}}},
        )
    return AgentLoopConfig(
        llm_client=mock_llm,
        model="test-model",
        registry=registry,
        system_prompt_fn=lambda: "You are a test agent.",
        middleware=middleware or [],
        max_turns=10,
    )


# ---------------------------------------------------------------------------
# 基础流程
# ---------------------------------------------------------------------------

class TestLoopBasic:
    def test_no_tool_call_exits_immediately(self, mock_llm):
        mock_llm.set_responses(make_llm_response(content="Hello!"))
        state = LoopState(messages=[{"role": "user", "content": "hi"}])
        run_agent_loop(_make_config(mock_llm), state)
        # LLM 只调用了一次
        assert mock_llm.chat.completions.create.call_count == 1
        # assistant 消息追加到 messages
        roles = [m["role"] for m in state.messages]
        assert "assistant" in roles

    def test_tool_call_dispatched_and_result_appended(self, mock_llm):
        tc = make_tool_call("echo", {"msg": "world"})
        mock_llm.set_responses(
            make_llm_response(tool_calls=[tc]),
            make_llm_response(content="Done"),
        )
        state = LoopState(messages=[{"role": "user", "content": "test"}])
        run_agent_loop(_make_config(mock_llm), state)

        # messages 中应包含 tool result
        tool_results = [m for m in state.messages if m.get("role") == "tool"]
        assert len(tool_results) == 1
        assert "echoed: world" in tool_results[0]["content"]

    def test_turn_count_increments(self, mock_llm):
        tc = make_tool_call("echo", {"msg": "x"})
        mock_llm.set_responses(
            make_llm_response(tool_calls=[tc]),
            make_llm_response(content="Done"),
        )
        state = LoopState(messages=[{"role": "user", "content": "go"}])
        run_agent_loop(_make_config(mock_llm), state)
        assert state.turn_count == 1

    def test_max_turns_prevents_infinite_loop(self, mock_llm):
        """每次响应都有工具调用，max_turns 应中断循环。"""
        tc = make_tool_call("echo", {"msg": "loop"})
        # 无限返回工具调用
        mock_llm.chat.completions.create.return_value = make_llm_response(tool_calls=[tc])
        mock_llm.chat.completions.create.side_effect = None

        state = LoopState(messages=[{"role": "user", "content": "loop"}], max_turns=3)
        cfg = _make_config(mock_llm)
        cfg = AgentLoopConfig(
            llm_client=mock_llm,
            model="test-model",
            registry=cfg.registry,
            system_prompt_fn=lambda: "test",
            middleware=[],
            max_turns=3,
        )
        run_agent_loop(cfg, state)
        assert state.turn_count <= 3


# ---------------------------------------------------------------------------
# Middleware 测试
# ---------------------------------------------------------------------------

class TestMiddleware:
    def test_pre_tool_intercept_blocks_dispatch(self, mock_llm):
        """pre_tool 返回 ToolResult 时，dispatch 不应被调用。"""
        tc = make_tool_call("echo", {"msg": "blocked"})
        mock_llm.set_responses(
            make_llm_response(tool_calls=[tc]),
            make_llm_response(content="Done"),
        )

        dispatched = []

        reg = ToolRegistry()
        reg.register(
            "echo",
            lambda **kw: dispatched.append(kw) or "ok",
            {"type": "function", "function": {"name": "echo", "parameters": {}}},
        )

        class BlockMiddleware(NoopMiddleware):
            def pre_tool(self, call, state):
                return ToolResult(call.id, "BLOCKED", "denied")

        state = LoopState(messages=[{"role": "user", "content": "test"}])
        cfg = AgentLoopConfig(
            llm_client=mock_llm, model="m", registry=reg,
            system_prompt_fn=lambda: "s",
            middleware=[BlockMiddleware()], max_turns=5,
        )
        run_agent_loop(cfg, state)
        assert len(dispatched) == 0
        tool_results = [m for m in state.messages if m.get("role") == "tool"]
        assert tool_results[0]["content"] == "BLOCKED"

    def test_middleware_lifecycle_order(self, mock_llm):
        """验证 pre_turn → pre_tool → post_tool → post_turn 的调用顺序。"""
        tc = make_tool_call("echo", {"msg": "order"})
        mock_llm.set_responses(
            make_llm_response(tool_calls=[tc]),
            make_llm_response(content="Done"),
        )
        events = []

        class TrackMiddleware(NoopMiddleware):
            def pre_turn(self, state): events.append("pre_turn")
            def pre_tool(self, call, state): events.append("pre_tool"); return None
            def post_tool(self, call, result, state): events.append("post_tool")
            def post_turn(self, state): events.append("post_turn")

        reg = ToolRegistry()
        reg.register("echo", lambda **kw: "ok", {
            "type": "function", "function": {"name": "echo", "parameters": {}}
        })
        state = LoopState(messages=[{"role": "user", "content": "go"}])
        cfg = AgentLoopConfig(
            llm_client=mock_llm, model="m", registry=reg,
            system_prompt_fn=lambda: "s",
            middleware=[TrackMiddleware()], max_turns=5,
        )
        run_agent_loop(cfg, state)

        # 第一轮（有工具调用）：pre_turn, pre_tool, post_tool, post_turn
        assert events[:4] == ["pre_turn", "pre_tool", "post_tool", "post_turn"]
