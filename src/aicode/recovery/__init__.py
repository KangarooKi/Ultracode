"""
recovery — 错误恢复模块

三种恢复策略：
  1. max_tokens (length)   — 注入 continuation 消息，继续输出
  2. prompt_too_long       — 压缩上下文后重试
  3. 连接 / 限速错误        — 指数退避重试

使用方式：
  1. 在 AgentLoopConfig 设置 recovery=RecoveryConfig()
  2. 在 middleware 列表加入 RecoveryMiddleware(config)
"""
from .config import RecoveryConfig
from .middleware import RecoveryMiddleware
from .strategies import RecoveryType, backoff_delay, is_connection_error, is_prompt_too_long_error

__all__ = [
    "RecoveryConfig",
    "RecoveryMiddleware",
    "RecoveryType",
    "backoff_delay",
    "is_connection_error",
    "is_prompt_too_long_error",
]
