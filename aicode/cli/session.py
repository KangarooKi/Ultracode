"""
cli/session.py — REPL / 单次 run 共用的会话组装

集成：基础工具、todo/task、memory、后台任务、MCP、worktree、子 Agent、
权限、钩子、压缩、恢复、Todo 计划。
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from openai import OpenAI

from aicode.cli import theme
from aicode.background.manager import BackgroundManager
from aicode.background.middleware import BackgroundMiddleware, register_background_tools
from aicode.context.compact import CompactMiddleware, CompactState
from aicode.core.client import get_client
from aicode.core.config import Config, get_config
from aicode.core.loop import AgentLoopConfig, NoopMiddleware, extract_last_text, run_agent_loop
from aicode.core.tools.registry import ToolRegistry, build_base_registry
from aicode.core.types import LoopState, ToolCall, ToolResult
from aicode.hooks.manager import HookManager, HookMiddleware
from aicode.memory.manager import MemoryManager
from aicode.mcp.bridge import register_mcp_tools, shutdown_mcp_clients
from aicode.mcp.loader import connect_servers
from aicode.mcp.router import MCPToolRouter
from aicode.planning.task_graph import TaskManager, register_task_tools
from aicode.planning.todo import TodoManager, TodoMiddleware
from aicode.prompt.builder import SystemPromptBuilder
from aicode.recovery.config import RecoveryConfig
from aicode.recovery.middleware import RecoveryMiddleware
from aicode.security.permission import PermissionManager, PermissionMiddleware
from aicode.subagent.tools import register_subagent_tool
from aicode.worktrees.tools import register_worktree_tool


@dataclass
class ReplContext:
    """一次 CLI 会话所需的全部依赖（交互 REPL 与非交互 run 共用）。"""

    config: Config
    client: OpenAI
    registry: ToolRegistry
    todo_mgr: TodoManager
    task_mgr: TaskManager
    memory_mgr: MemoryManager
    prompt_builder: SystemPromptBuilder
    perm_mgr: PermissionManager
    hook_mgr: HookManager
    bg_manager: BackgroundManager
    mcp_clients: list
    loop_cfg: AgentLoopConfig


class PrintingMiddleware(NoopMiddleware):
    """实时打印工具结果预览（低对比度，避免抢助手正文）。"""

    def __init__(self) -> None:
        self._max_preview = 360

    def post_tool(self, call: ToolCall, result: ToolResult, state: LoopState) -> None:
        raw = (result.content or "").strip()
        status = result.status or "ok"
        label = {
            "ok": "done",
            "error": "error",
            "denied": "denied",
            "blocked": "blocked",
        }.get(status, status)
        if not raw:
            tail = theme.dim("(no output)")
        else:
            one_line = raw[: self._max_preview].replace("\r", "").replace("\n", " · ")
            if len(raw) > self._max_preview:
                one_line += "…"
            tail = theme.dim(one_line)
        print(
            f"  {theme.status_dot(status)} {theme.primary(call.name)} "
            f"{theme.badge(label, _status_tone(status))} {tail}"
        )


def _status_tone(status: str) -> str:
    return {
        "ok": "green",
        "error": "error",
        "denied": "warn",
        "blocked": "warn",
    }.get(status, "muted")


def session_cleanup(ctx: ReplContext) -> None:
    """释放 MCP 子进程等资源；REPL / run 退出时应调用。"""
    shutdown_mcp_clients(ctx.mcp_clients)


def build_repl_context(
    workdir: Path | None = None,
    *,
    quiet_tools: bool = False,
) -> ReplContext:
    cfg = get_config(workdir)
    client = get_client()
    wd = cfg.workdir

    registry = build_base_registry(workdir=wd)

    todo_mgr = TodoManager()
    from aicode.core.tools.schemas import todo_schema

    registry.register("todo", lambda **kw: todo_mgr.update(kw["items"]), todo_schema())

    task_mgr = TaskManager(wd / ".tasks")
    register_task_tools(registry, task_mgr)

    bg_manager = BackgroundManager(wd)
    register_background_tools(registry, bg_manager)

    mcp_router = MCPToolRouter()
    mcp_clients = connect_servers(wd, mcp_router)
    register_mcp_tools(registry, mcp_router)

    register_worktree_tool(registry, wd)

    memory_mgr = MemoryManager(wd / ".memory")
    memory_mgr.load_all()

    prompt_builder = SystemPromptBuilder(
        workdir=wd,
        registry=registry,
        memory_dir=wd / ".memory",
        skills_dir=wd / "skills",
    )

    perm_mgr = PermissionManager(mode="default")
    hook_mgr = HookManager(workdir=wd)

    sub_middleware = [
        PermissionMiddleware(perm_mgr),
        HookMiddleware(hook_mgr),
    ]
    register_subagent_tool(
        registry,
        client,
        cfg.model,
        parent_registry=registry,
        workdir=wd,
        skills_dir=wd / "skills",
        middleware=sub_middleware,
    )

    compact_state = CompactState()
    compact_mw = CompactMiddleware(
        state=compact_state,
        client=client,
        model=cfg.model,
        workdir=wd,
    )

    recovery_conf: RecoveryConfig | None = None
    middleware: list = [
        PermissionMiddleware(perm_mgr),
        HookMiddleware(hook_mgr),
        compact_mw,
    ]
    if cfg.recovery_enabled:
        recovery_conf = RecoveryConfig(max_retries=cfg.recovery_max_retries)
        middleware.append(RecoveryMiddleware(recovery_conf))
    middleware.append(TodoMiddleware(todo_mgr))
    middleware.append(BackgroundMiddleware(bg_manager))

    if not quiet_tools:
        middleware.insert(0, PrintingMiddleware())

    stream_on = cfg.stream_llm and sys.stdout.isatty()
    loop_cfg = AgentLoopConfig(
        llm_client=client,
        model=cfg.model,
        registry=registry,
        system_prompt_fn=prompt_builder.build,
        middleware=middleware,
        max_turns=cfg.max_turns,
        max_tokens=cfg.max_tokens,
        recovery=recovery_conf,
        stream=stream_on,
        stream_line_prefix=theme.assistant_left_border_prefix() if stream_on else None,
    )

    return ReplContext(
        config=cfg,
        client=client,
        registry=registry,
        todo_mgr=todo_mgr,
        task_mgr=task_mgr,
        memory_mgr=memory_mgr,
        prompt_builder=prompt_builder,
        perm_mgr=perm_mgr,
        hook_mgr=hook_mgr,
        bg_manager=bg_manager,
        mcp_clients=mcp_clients,
        loop_cfg=loop_cfg,
    )


def run_agent_turn(ctx: ReplContext, messages: list) -> tuple[str, bool]:
    """
    执行一轮 Agent 循环，返回 (最后一条 assistant 文本, 是否已在流式中输出该正文)。

    第二项为 True 时，调用方不应再整段 print，以免重复。
    """
    state = LoopState(messages=messages, max_turns=ctx.config.max_turns)
    run_agent_loop(ctx.loop_cfg, state)
    text = extract_last_text(state) or ""
    streamed_last = state.metadata.get("last_assistant_streamed_chars", 0) > 0
    return text, streamed_last
