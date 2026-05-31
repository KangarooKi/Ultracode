"""
CLI 输出格式化：Markdown 常见结构 → 终端 ANSI（实现见 core.markdown_terminal）。
"""
from __future__ import annotations

from aicode.core.assistant_markdown_stream import AssistantMarkdownStreamWriter
from aicode.core.markdown_terminal import format_assistant_markdown

__all__ = ["format_assistant_markdown", "AssistantMarkdownStreamWriter"]
