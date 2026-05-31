"""
prompt/builder.py — 模块化系统提示构建器（SystemPromptBuilder）

管线顺序（稳定 → 动态）：
  1. core
  2. tool_listing
  3. skill_listing
  4. memory
  5. claude_md
  6. agents_md
  7. dynamic_context

DYNAMIC_BOUNDARY 之后的内容每轮重建；之前的内容相对稳定，可缓存。
"""
from __future__ import annotations

from pathlib import Path

from aicode.core.tools.registry import ToolRegistry
from .sections import (
    build_agents_md,
    build_claude_md,
    build_core,
    build_dynamic_context,
    build_memory_section,
    build_skill_listing,
    build_tool_listing,
)

DYNAMIC_BOUNDARY = "=== DYNAMIC_BOUNDARY ==="


class SystemPromptBuilder:
    """
    组装系统提示。调用 build() 获取完整提示字符串。
    """

    def __init__(
        self,
        workdir: Path,
        registry: ToolRegistry | None = None,
        memory_dir: Path | None = None,
        skills_dir: Path | None = None,
    ) -> None:
        self.workdir = workdir
        self.registry = registry
        self.memory_dir = memory_dir or (workdir / ".memory")
        self.skills_dir = skills_dir or (workdir / "skills")

    def build(self) -> str:
        """返回完整的系统提示字符串。"""
        parts: list[str] = []

        # 1. 核心指令
        core = build_core(self.workdir)
        if core:
            parts.append(core)

        # 2. 工具列表
        if self.registry:
            tool_listing = build_tool_listing(self.registry.get_schemas())
            if tool_listing:
                parts.append(tool_listing)

        # 3. 技能列表
        skill_listing = build_skill_listing(self.skills_dir)
        if skill_listing:
            parts.append(skill_listing)

        # 4. 记忆
        memory_section = build_memory_section(self.memory_dir)
        if memory_section:
            parts.append(memory_section)

        # 5. CLAUDE.md 链
        claude_md = build_claude_md(self.workdir)
        if claude_md:
            parts.append(claude_md)

        # 5b. AGENTS.md（项目级规则）
        agents_md = build_agents_md(self.workdir)
        if agents_md:
            parts.append(agents_md)

        # 稳定/动态分界
        parts.append(DYNAMIC_BOUNDARY)

        # 6. 动态上下文
        parts.append(build_dynamic_context(self.workdir))

        return "\n\n".join(parts)
