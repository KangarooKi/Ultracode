"""
recovery/strategies.py — 恢复工具函数

包含：
- RecoveryType 枚举
- backoff_delay       : 指数退避时间计算
- is_prompt_too_long_error : 判断是否为上下文超长错误
- is_connection_error  : 判断是否为网络/限速错误
- auto_compact_for_recovery : 不依赖 compact.py 的轻量压缩
- estimate_tokens      : 字符估算 token 数
"""
from __future__ import annotations

import json
import random
from enum import Enum


class RecoveryType(str, Enum):
    MAX_TOKENS = "max_tokens"        # length finish_reason
    PROMPT_TOO_LONG = "prompt_too_long"  # API 400 error
    CONNECTION = "connection"        # 网络/限速错误


# ---------------------------------------------------------------------------
# 退避计算
# ---------------------------------------------------------------------------

def backoff_delay(attempt: int, base: float = 1.0, max_delay: float = 30.0) -> float:
    """
    指数退避 + 随机抖动：base * 2^attempt + U(0,1)

    >>> backoff_delay(0) >= 1.0
    True
    >>> backoff_delay(10) <= 31.0  # capped at max_delay + 1
    True
    """
    delay = min(base * (2 ** attempt), max_delay)
    jitter = random.uniform(0, 1)
    return delay + jitter


# ---------------------------------------------------------------------------
# 错误分类
# ---------------------------------------------------------------------------

def is_prompt_too_long_error(error: Exception) -> bool:
    """
    判断是否为"上下文超长"错误。

    OpenAI: BadRequestError 含 "context_length_exceeded"
    其他兼容 API: 也可能含 "too long" + "prompt" 或 "max_tokens"
    """
    msg = str(error).lower()
    return (
        "context_length_exceeded" in msg
        or ("too long" in msg and "prompt" in msg)
        or "maximum context length" in msg
        or "prompt is too long" in msg
    )


def is_connection_error(error: Exception) -> bool:
    """判断是否为网络层 / 限速错误，适合退避重试。"""
    try:
        import openai
        if isinstance(error, (openai.APIConnectionError, openai.RateLimitError)):
            return True
    except ImportError:
        pass
    return isinstance(error, (ConnectionError, TimeoutError, OSError))


# ---------------------------------------------------------------------------
# 轻量压缩（不依赖 context/compact.py，避免循环导入）
# ---------------------------------------------------------------------------

def estimate_tokens(messages: list) -> int:
    """粗略 token 估算：每 4 字符约 1 token。"""
    return len(json.dumps(messages, default=str)) // 4


def auto_compact_for_recovery(messages: list, client, model: str) -> list:
    """
    调用 LLM 将对话摘要为简短延续提示，替换原始 messages。

    与 context/compact.py 中的 compact_history 独立，不写磁盘，
    专为 recovery 路径中的快速恢复设计。
    """
    conversation = json.dumps(messages, default=str)[:80_000]
    prompt = (
        "Summarize this agent conversation for continuity. Include:\n"
        "1. Task overview and success criteria\n"
        "2. Current state: completed work, files touched\n"
        "3. Key decisions and failed approaches\n"
        "4. Remaining next steps\n"
        "Be concise but preserve critical details.\n\n"
        + conversation
    )
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4000,
        )
        summary = (response.choices[0].message.content or "").strip()
    except Exception as exc:
        summary = f"(compact failed: {exc}). Previous context may be incomplete."

    return [{
        "role": "user",
        "content": (
            "This session continues from a prior conversation that was compacted.\n\n"
            f"{summary}\n\n"
            "Continue from where we left off."
        ),
    }]
