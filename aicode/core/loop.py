"""
core/loop.py — Agent 主循环

核心设计：
1. LoopMiddleware 协议 —— 所有功能模块（权限/钩子/记忆/压缩）通过实现此协议
   叠加到同一个 run_agent_loop，不各自写独立的循环。
2. AgentLoopConfig —— 组合依赖的数据类，CLI 层组装后传入。
3. run_agent_loop —— 单一的主循环实现，按 middleware 顺序调用生命周期钩子。

错误恢复（可选，需设置 AgentLoopConfig.recovery）：
  - prompt_too_long  → 自动压缩 messages 后重试当轮 LLM 调用
  - connection/rate  → 指数退避重试
  - max_tokens       → 由 RecoveryMiddleware 注入续写消息

读取顺序：
1. LoopMiddleware（接口契约）
2. AgentLoopConfig（依赖组合）
3. run_agent_loop（主循环）
4. NoopMiddleware（默认空实现，方便继承）
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

from openai import OpenAI

from .assistant_markdown_stream import AssistantMarkdownStreamWriter
from .llm_types import LLMCallResult, tool_calls_from_stream_dicts
from .tools.registry import ToolRegistry
from .types import LoopState, ToolCall, ToolResult
from .wait_hint import llm_wait_context

if TYPE_CHECKING:
    from aicode.recovery.config import RecoveryConfig


# ---------------------------------------------------------------------------
# Middleware 协议
# ---------------------------------------------------------------------------

class LoopMiddleware:
    """
    Agent 循环中间件接口。

    生命周期：
    - pre_turn : 每轮开始前（可修改 state）
    - pre_tool : 工具调用前（返回 ToolResult 则拦截，返回 None 则放行）
    - post_tool: 工具调用后（可记录/压缩/统计）
    - post_turn: 每轮结束后（可发送提醒消息）
    """

    def pre_turn(self, state: LoopState) -> None: ...

    def pre_tool(self, call: ToolCall, state: LoopState) -> ToolResult | None: ...

    def post_tool(
        self, call: ToolCall, result: ToolResult, state: LoopState
    ) -> None: ...

    def post_turn(self, state: LoopState) -> None: ...


class NoopMiddleware:
    """空实现基类，子类只需覆盖需要的方法。"""

    def pre_turn(self, state: LoopState) -> None:
        pass

    def pre_tool(self, call: ToolCall, state: LoopState) -> ToolResult | None:
        return None

    def post_tool(self, call: ToolCall, result: ToolResult, state: LoopState) -> None:
        pass

    def post_turn(self, state: LoopState) -> None:
        pass


# ---------------------------------------------------------------------------
# 循环配置
# ---------------------------------------------------------------------------

@dataclass
class AgentLoopConfig:
    llm_client: OpenAI
    model: str
    registry: ToolRegistry
    system_prompt_fn: Callable[[], str]
    middleware: list = field(default_factory=list)   # list[LoopMiddleware]
    max_turns: int = 100
    max_tokens: int = 8000
    # 可选：错误恢复配置（None = 不启用）
    recovery: "RecoveryConfig | None" = None
    # 流式输出（recovery 开启时自动关闭，走非流式）
    stream: bool = False
    stream_writer: Callable[[str], None] | None = None
    # 流式正文每一行前的左边框前缀（如青色 ┃ ）；仅 stream_writer 为默认时生效
    stream_line_prefix: str | None = None


# ---------------------------------------------------------------------------
# 内部：流式行前缀（左侧竖条）
# ---------------------------------------------------------------------------


class _PrefixedLineWriter:
    """在换行边界为每行加上前缀，flush 时处理末尾无换行片段。"""

    __slots__ = ("_prefix", "_inner", "_buf")

    def __init__(self, prefix: str, inner: Callable[[str], None]) -> None:
        self._prefix = prefix
        self._inner = inner
        self._buf = ""

    def write(self, s: str) -> None:
        if not s:
            return
        self._buf += s
        while "\n" in self._buf:
            line, _, self._buf = self._buf.partition("\n")
            self._inner(self._prefix + line + "\n")

    def flush_tail(self) -> None:
        if self._buf:
            self._inner(self._prefix + self._buf)
            self._buf = ""


# ---------------------------------------------------------------------------
# 内部：LLM 响应解析
# ---------------------------------------------------------------------------

def _blocking_to_result(response) -> LLMCallResult:
    choice = response.choices[0]
    assistant_msg = choice.message
    assistant_dict = assistant_msg.model_dump(exclude_none=True)
    fr = getattr(choice, "finish_reason", None) or "stop"
    tcs = list(assistant_msg.tool_calls or [])
    return LLMCallResult(assistant_dict, tcs, fr, 0)


def _stream_to_result(
    client: OpenAI,
    kwargs: dict,
    writer: Callable[[str], None],
    *,
    markdown_stream: AssistantMarkdownStreamWriter | None = None,
    line_prefix_sink: _PrefixedLineWriter | None = None,
) -> LLMCallResult:
    content_parts: list[str] = []
    tool_acc: dict[int, dict[str, str]] = {}
    finish_reason = "stop"
    streamed = 0

    try:
        stream = client.chat.completions.create(**kwargs, stream=True)
        for chunk in stream:
            if not chunk.choices:
                continue
            c0 = chunk.choices[0]
            fr = getattr(c0, "finish_reason", None)
            if fr:
                finish_reason = fr
            d = c0.delta
            if d is None:
                continue
            piece = getattr(d, "content", None)
            if piece:
                content_parts.append(piece)
                streamed += len(piece)
                writer(piece)
            tcs = getattr(d, "tool_calls", None)
            if tcs:
                for tc in tcs:
                    i = int(tc.index)
                    if i not in tool_acc:
                        tool_acc[i] = {"id": "", "name": "", "arguments": ""}
                    if getattr(tc, "id", None):
                        tool_acc[i]["id"] = tc.id
                    fn = getattr(tc, "function", None)
                    if fn is not None:
                        if getattr(fn, "name", None):
                            tool_acc[i]["name"] = fn.name
                        arg = getattr(fn, "arguments", None)
                        if arg:
                            tool_acc[i]["arguments"] += arg
    finally:
        if markdown_stream is not None:
            markdown_stream.flush()
        if line_prefix_sink is not None:
            line_prefix_sink.flush_tail()

    full_content = "".join(content_parts) if content_parts else None
    if full_content == "":
        full_content = None
    assistant_dict: dict = {"role": "assistant"}
    if full_content is not None:
        assistant_dict["content"] = full_content
    tco = tool_calls_from_stream_dicts(tool_acc)
    if tco:
        assistant_dict["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments or "{}",
                },
            }
            for tc in tco
        ]
    return LLMCallResult(assistant_dict, tco, finish_reason, streamed)


def _call_llm(config: AgentLoopConfig, api_messages: list, state: LoopState) -> LLMCallResult:
    """
    调用 LLM。recovery 非空时仅非流式（便于重试逻辑）。
    stream=True 且 recovery is None 时使用 SSE 流式，并通过 stream_writer 写出正文 delta。
    """
    kwargs = {
        "model": config.model,
        "messages": api_messages,
        "tools": config.registry.get_schemas(),
        "tool_choice": "auto",
        "max_tokens": config.max_tokens,
    }

    recovery = config.recovery

    if config.stream and recovery is None:
        writer = config.stream_writer
        if writer is None:

            def _w(s: str) -> None:
                sys.stdout.write(s)
                sys.stdout.flush()

            writer = _w

        chain: Callable[[str], None] = writer
        prefix_sink: _PrefixedLineWriter | None = None
        if config.stream_line_prefix and config.stream_writer is None:
            prefix_sink = _PrefixedLineWriter(config.stream_line_prefix, chain)
            chain = prefix_sink.write

        md_stream: AssistantMarkdownStreamWriter | None = None
        if config.stream_writer is None and not os.environ.get("NO_COLOR", "").strip():
            md_stream = AssistantMarkdownStreamWriter(chain)
            chain = md_stream.write

        writer = chain
        return _stream_to_result(
            config.llm_client,
            kwargs,
            writer,
            markdown_stream=md_stream,
            line_prefix_sink=prefix_sink,
        )

    if recovery is None:
        resp = config.llm_client.chat.completions.create(**kwargs)
        return _blocking_to_result(resp)

    # ---------- 有 recovery 配置：带重试（非流式）----------
    from aicode.recovery.strategies import (
        auto_compact_for_recovery,
        backoff_delay,
        is_connection_error,
        is_prompt_too_long_error,
    )

    current_messages = list(api_messages)
    kwargs = {**kwargs, "messages": current_messages}

    for attempt in range(recovery.max_retries + 1):
        try:
            resp = config.llm_client.chat.completions.create(**kwargs)
            return _blocking_to_result(resp)
        except Exception as exc:
            # 策略 2：上下文超长 → 压缩后重试
            if recovery.compact_on_too_long and is_prompt_too_long_error(exc):
                print(f"[Recovery] Prompt too long. Compacting… (attempt {attempt + 1})")
                # 只压缩 state.messages（不含 system prompt）
                compacted = auto_compact_for_recovery(
                    state.messages, config.llm_client, config.model
                )
                state.messages = compacted
                current_messages = [
                    {"role": "system", "content": config.system_prompt_fn()},
                    *state.messages,
                ]
                kwargs = {
                    **kwargs,
                    "messages": current_messages,
                }
                continue

            # 策略 3：网络/限速 → 退避重试
            if recovery.backoff_enabled and is_connection_error(exc):
                if attempt < recovery.max_retries:
                    delay = backoff_delay(
                        attempt, recovery.backoff_base, recovery.backoff_max
                    )
                    print(
                        f"[Recovery] Connection error: {exc}. "
                        f"Retry in {delay:.1f}s ({attempt + 1}/{recovery.max_retries})"
                    )
                    recovery.sleep(delay)
                    continue
                print(f"[Recovery] Connection failed after {recovery.max_retries} retries.")
                raise

            # 其他错误 / 重试耗尽 → 直接抛出
            raise

    raise RuntimeError("_call_llm: retry loop exhausted without returning")  # pragma: no cover


# ---------------------------------------------------------------------------
# 主循环
# ---------------------------------------------------------------------------

def run_agent_loop(config: AgentLoopConfig, state: LoopState) -> LoopState:
    """
    执行 Agent 主循环，直到 LLM 不再返回工具调用或达到最大轮次。

    消息流：
      user → [system_prompt + messages] → LLM
        → tool_calls → [middleware.pre_tool] → dispatch → [middleware.post_tool]
        → append tool results → next turn
    """
    while state.turn_count < config.max_turns:
        # --- pre_turn ---
        for mw in config.middleware:
            mw.pre_turn(state)

        # --- LLM 调用（含可选的错误恢复）---
        api_messages = [
            {"role": "system", "content": config.system_prompt_fn()},
            *state.messages,
        ]
        # 流式时关闭 stderr 等待动画，否则与 stdout 流式正文在终端里交错成乱码
        with llm_wait_context(show_hint=not config.stream):
            result = _call_llm(config, api_messages, state)

        state.messages.append(result.assistant_dict)
        state.metadata["streamed_assistant_total"] = (
            state.metadata.get("streamed_assistant_total", 0) + result.streamed_chars
        )
        state.metadata["last_assistant_streamed_chars"] = result.streamed_chars

        # 记录 finish_reason，供 RecoveryMiddleware 等使用
        finish_reason = result.finish_reason
        state.last_stop_reason = finish_reason
        state.metadata["recovery.last_stop_reason"] = finish_reason

        tool_calls = result.tool_calls
        if not tool_calls:
            state.transition_reason = None
            break

        # --- 处理工具调用 ---
        had_tool_call = False
        for tc in tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            call = ToolCall(id=tc.id, name=name, arguments=args)

            # pre_tool：第一个返回非 None 的 middleware 拦截此工具调用
            intercepted: ToolResult | None = None
            for mw in config.middleware:
                intercepted = mw.pre_tool(call, state)
                if intercepted is not None:
                    break

            if intercepted is not None:
                result = intercepted
            else:
                output = config.registry.dispatch(name, args)
                result = ToolResult(
                    tool_call_id=tc.id,
                    content=output,
                    status="error" if output.startswith("Error:") else "ok",
                )

            # post_tool
            for mw in config.middleware:
                mw.post_tool(call, result, state)

            state.messages.append(result.to_message())
            had_tool_call = True

        if had_tool_call:
            state.turn_count += 1
            state.transition_reason = "tool_use"

        # --- post_turn ---
        for mw in config.middleware:
            mw.post_turn(state)

    return state


def extract_last_text(state: LoopState) -> str:
    """从最后一条 assistant 消息中提取纯文本内容。"""
    for msg in reversed(state.messages):
        if msg.get("role") == "assistant":
            content = msg.get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()
    return ""
