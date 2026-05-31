"""
subagent/runner.py — 子 Agent 执行器

spawn_subagent() 创建一个独立上下文的子 Agent 循环：
  - 新建 LoopState（隔离对话历史）
  - 可限制可用工具子集
  - 可覆盖 system prompt
  - 继承父 Agent 的 llm_client 和 model
  - 返回最终文本输出

与参考实现相比的增强：
  - 支持 AgentTemplate（从 skills/ 加载配置）
  - 支持深度限制（防止无限递归）
  - 子 Agent 内部使用完整 middleware 协议（支持 permission/compact 等）
  - 详细的执行日志
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openai import OpenAI

from aicode.core.loop import AgentLoopConfig, NoopMiddleware, run_agent_loop
from aicode.core.tools.base import WORKDIR
from aicode.core.tools.registry import ToolRegistry, build_base_registry
from aicode.core.types import LoopState

from .template import AgentTemplate

# 防止子 Agent 嵌套过深（每次 spawn 将此计数 +1）
_MAX_DEPTH = 5
_DEPTH_KEY = "_subagent_depth"


@dataclass
class SubAgentResult:
    """spawn_subagent 的完整返回值。"""
    output: str                        # 最终文本
    turn_count: int = 0
    messages: list = field(default_factory=list)
    success: bool = True
    error: str | None = None


def spawn_subagent(
    task: str,
    *,
    client: OpenAI,
    model: str,
    parent_registry: ToolRegistry | None = None,
    allowed_tools: list[str] | None = None,
    system_prompt: str | None = None,
    template: AgentTemplate | None = None,
    max_turns: int = 10,
    max_tokens: int = 8000,
    workdir: Path | None = None,
    parent_depth: int = 0,
    middleware: list | None = None,
) -> SubAgentResult:
    """
    启动子 Agent，独立上下文，返回文本结果。

    参数：
      task          : 子 Agent 的任务描述（将作为第一条 user 消息）
      client        : OpenAI 兼容客户端
      model         : 模型名
      parent_registry: 父 Agent 的工具注册表（用于工具继承）
      allowed_tools : 白名单工具名列表（None = 继承全部）
      system_prompt : 覆盖系统提示（None = 使用 template.system 或默认）
      template      : AgentTemplate 对象（优先级低于直接参数）
      max_turns     : 最大轮次
      max_tokens    : 每轮最大 token
      workdir       : 工作目录
      parent_depth  : 父调用嵌套深度（防止无限递归）
      middleware    : 额外中间件列表
    """
    # 深度防护
    depth = parent_depth + 1
    if depth > _MAX_DEPTH:
        return SubAgentResult(
            output="",
            success=False,
            error=f"Subagent depth limit ({_MAX_DEPTH}) exceeded",
        )

    # 合并 template 配置（直接参数优先）
    if template:
        if allowed_tools is None and template.tools:
            allowed_tools = template.tools
        if system_prompt is None and template.system:
            system_prompt = template.system
        max_turns = max_turns if max_turns != 10 else template.max_turns

    # 构建工具注册表（父 registry 的子集 或 全新基础 registry）
    if parent_registry and allowed_tools:
        registry = _filtered_registry(parent_registry, allowed_tools, workdir)
    elif parent_registry:
        registry = parent_registry
    else:
        registry = build_base_registry(workdir or WORKDIR)

    # 构建 system prompt
    wdir = workdir or WORKDIR
    sp = system_prompt or (
        f"You are a specialized sub-agent working at {wdir}. "
        f"Complete the given task precisely and concisely using available tools."
    )

    # 子 Agent 深度信息注入 metadata
    state = LoopState(
        messages=[{"role": "user", "content": task}],
        max_turns=max_turns,
    )
    state.metadata[_DEPTH_KEY] = depth

    cfg = AgentLoopConfig(
        llm_client=client,
        model=model,
        registry=registry,
        system_prompt_fn=lambda: sp,
        middleware=middleware or [],
        max_turns=max_turns,
        max_tokens=max_tokens,
        stream=False,
    )

    print(f"[Subagent] Spawning depth={depth}, tools={list(registry.names())}, task={task[:80]}")

    try:
        final_state = run_agent_loop(cfg, state)
    except Exception as exc:
        return SubAgentResult(
            output="",
            success=False,
            error=str(exc),
            messages=state.messages,
            turn_count=state.turn_count,
        )

    # 提取最终回复文本
    from aicode.core.loop import extract_last_text
    output = extract_last_text(final_state)

    print(f"[Subagent] Depth={depth} finished in {final_state.turn_count} turns.")
    return SubAgentResult(
        output=output,
        turn_count=final_state.turn_count,
        messages=final_state.messages,
        success=True,
    )


def _filtered_registry(
    source: ToolRegistry,
    allowed: list[str],
    workdir: Path | None,
) -> ToolRegistry:
    """
    从 source 中筛选出 allowed 列表中的工具，返回新 ToolRegistry。
    如果某工具在 source 中不存在，则静默跳过。
    """
    new_reg = ToolRegistry()
    for name in allowed:
        handler, schema = source.get_handler_and_schema(name)
        if handler and schema:
            new_reg.register(name, handler, schema)
    return new_reg
