"""
recovery/middleware.py — max_tokens 续写中间件

职责：
  post_turn : 检测 last_stop_reason == "length"，设置续写标志
  pre_turn  : 若有续写标志，在 messages 末尾注入 continuation 提示

注意：prompt_too_long 和 connection 错误的恢复在 core/loop.py 的
      _call_with_recovery() 函数中处理（因为需要包裹 API 调用本身）。
"""
from __future__ import annotations

from aicode.core.loop import NoopMiddleware
from aicode.core.types import LoopState

from .config import RecoveryConfig

_KEY_NEEDS = "recovery.needs_continuation"
_KEY_COUNT = "recovery.continuation_count"


class RecoveryMiddleware(NoopMiddleware):
    """
    处理 max_tokens 输出截断恢复。

    当 LLM 因 max_tokens 停止输出（finish_reason == "length"）时，
    自动在下一轮注入续写指令，最多重试 config.max_retries 次。
    """

    def __init__(self, config: RecoveryConfig | None = None) -> None:
        self.config = config or RecoveryConfig()

    # ------------------------------------------------------------------

    def pre_turn(self, state: LoopState) -> None:
        if not state.metadata.get(_KEY_NEEDS):
            return

        count = state.metadata.get(_KEY_COUNT, 0) + 1
        if count > self.config.max_retries:
            print(
                f"[Recovery] Continuation limit ({self.config.max_retries}) reached. Stopping."
            )
            state.metadata[_KEY_NEEDS] = False
            return

        state.metadata[_KEY_NEEDS] = False
        state.metadata[_KEY_COUNT] = count
        print(f"[Recovery] max_tokens hit — injecting continuation #{count}")
        state.messages.append({
            "role": "user",
            "content": self.config.continuation_msg,
        })

    def post_turn(self, state: LoopState) -> None:
        if state.last_stop_reason == "length":
            state.metadata[_KEY_NEEDS] = True
        else:
            # 成功完成一个非截断回合，重置计数
            state.metadata[_KEY_COUNT] = 0
