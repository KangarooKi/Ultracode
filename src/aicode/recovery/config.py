"""
recovery/config.py — 恢复策略配置

所有常量都可在 RecoveryConfig 中覆盖，便于测试和调参。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RecoveryConfig:
    """
    错误恢复参数配置。

    max_retries        : 最大重试次数（适用于所有三种策略）
    backoff_base       : 指数退避基础延迟（秒）
    backoff_max        : 退避最大延迟上限（秒）
    token_threshold    : 触发主动压缩的 token 估算阈值（chars / 4）
    continuation_msg   : max_tokens 命中时注入的延续提示语
    backoff_enabled    : 是否启用网络层退避重试
    compact_on_too_long: prompt_too_long 时是否自动压缩
    """

    max_retries: int = 3
    backoff_base: float = 1.0
    backoff_max: float = 30.0
    token_threshold: int = 50_000        # chars / 4 ≈ tokens
    continuation_msg: str = (
        "Output limit hit. Continue directly from where you stopped — "
        "no recap, no repetition. Pick up mid-sentence if needed."
    )
    backoff_enabled: bool = True
    compact_on_too_long: bool = True
    # 内部：是否在测试中跳过真实 sleep
    _sleep_fn: object = field(default=None, repr=False, compare=False)

    def sleep(self, seconds: float) -> None:
        """可在测试中注入 mock sleep。"""
        if self._sleep_fn is not None:
            self._sleep_fn(seconds)
        else:
            import time
            time.sleep(seconds)
