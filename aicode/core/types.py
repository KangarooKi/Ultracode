"""
core/types.py — 全局共享类型

所有模块通过这里的类型进行通信，避免循环导入。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# OpenAI 消息格式（dict），保持与教学代码兼容
Message = dict[str, Any]


@dataclass
class ToolCall:
    """LLM 返回的工具调用请求。"""
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolResult:
    """工具执行结果。"""
    tool_call_id: str
    content: str
    status: str = "ok"      # "ok" | "error" | "denied" | "blocked"
    source: str = "native"  # "native" | "mcp"

    def to_message(self) -> Message:
        return {"role": "tool", "tool_call_id": self.tool_call_id, "content": self.content}


@dataclass
class LoopState:
    """Agent 主循环的运行时状态。"""
    messages: list[Message]
    turn_count: int = 0
    max_turns: int = 100
    transition_reason: str | None = None
    # LLM 上一次回复的 finish_reason（"stop"/"length"/"tool_calls" 等）
    last_stop_reason: str | None = None
    # 供 middleware 附加任意元数据（键名需加模块前缀防冲突）
    metadata: dict[str, Any] = field(default_factory=dict)
