"""LLM 调用结果（流式与非流式统一）。"""
from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any


@dataclass
class LLMCallResult:
    """供 run_agent_loop 使用的单次 LLM 返回。"""

    assistant_dict: dict[str, Any]
    tool_calls: list[Any]  # 元素含 .id, .function.name, .function.arguments
    finish_reason: str
    streamed_chars: int = 0


def tool_calls_from_stream_dicts(
    indexed: dict[int, dict[str, str]],
) -> list[Any]:
    """把流式累积的 {index: {id,name,arguments}} 转成可迭代的 tool 对象。"""
    out: list[Any] = []
    for i in sorted(indexed.keys()):
        row = indexed[i]
        tid = row.get("id") or ""
        name = row.get("name") or ""
        args = row.get("arguments") or "{}"
        out.append(
            SimpleNamespace(
                id=tid,
                function=SimpleNamespace(name=name, arguments=args),
            )
        )
    return out
