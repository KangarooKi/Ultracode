"""
subagent/tools.py — 向 ToolRegistry 注册 subagent_call 工具

LLM 可通过 subagent_call 工具委派子任务给独立上下文的子 Agent。
"""
from __future__ import annotations

import json
from pathlib import Path

from openai import OpenAI

from aicode.core.tools.registry import ToolRegistry


def subagent_call_schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "subagent_call",
            "description": (
                "Delegate a subtask to a specialized sub-agent with its own context. "
                "The sub-agent runs independently and returns a text result. "
                "Use this for long, isolated subtasks that don't need the main conversation history."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "Full description of what the sub-agent should accomplish.",
                    },
                    "tools": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Optional: whitelist of tool names the sub-agent may use. "
                            "Omit to allow all tools."
                        ),
                    },
                    "template": {
                        "type": "string",
                        "description": (
                            "Optional: name of a skill template (from skills/ directory) "
                            "to configure the sub-agent."
                        ),
                    },
                    "max_turns": {
                        "type": "integer",
                        "description": "Maximum turns the sub-agent may use (default 10).",
                    },
                },
                "required": ["task"],
            },
        },
    }


def register_subagent_tool(
    registry: ToolRegistry,
    client: OpenAI,
    model: str,
    parent_registry: ToolRegistry | None = None,
    workdir: Path | None = None,
    skills_dir: Path | None = None,
    parent_depth: int = 0,
    middleware: list | None = None,
) -> None:
    """
    将 subagent_call 工具注册到 registry。

    handler 是一个闭包，捕获 client/model/parent_registry 等运行时依赖。
    """
    from .runner import spawn_subagent
    from .template import load_templates

    templates: dict = {}
    if skills_dir:
        templates = load_templates(skills_dir)

    def _handler(**kw):
        task: str = kw["task"]
        allowed: list[str] | None = kw.get("tools") or None
        tmpl_name: str | None = kw.get("template")
        max_turns: int = int(kw.get("max_turns") or 10)

        tmpl = templates.get(tmpl_name) if tmpl_name else None

        result = spawn_subagent(
            task,
            client=client,
            model=model,
            parent_registry=parent_registry,
            allowed_tools=allowed,
            template=tmpl,
            max_turns=max_turns,
            workdir=workdir,
            parent_depth=parent_depth,
            middleware=middleware,
        )

        if not result.success:
            return f"Error: subagent failed — {result.error}"

        return json.dumps({
            "output": result.output,
            "turns": result.turn_count,
        }, ensure_ascii=False)

    registry.register("subagent_call", _handler, subagent_call_schema())
