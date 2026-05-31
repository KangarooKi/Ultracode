"""
subagent — 子 Agent 委派模块

允许主 Agent 将子任务委派给拥有独立上下文和工具子集的子 Agent。

核心概念：
  AgentTemplate  : 从 skills/ 目录 SKILL.md frontmatter 加载的模板
  spawn_subagent : 使用当前 llm_client + model 启动一个一次性子 Agent 循环
  register_subagent_tool : 向 ToolRegistry 注册 "subagent_call" 工具
"""
from .runner import spawn_subagent
from .template import AgentTemplate, load_templates
from .tools import register_subagent_tool

__all__ = [
    "AgentTemplate",
    "load_templates",
    "spawn_subagent",
    "register_subagent_tool",
]
