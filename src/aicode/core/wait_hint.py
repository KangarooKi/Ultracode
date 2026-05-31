"""
阻塞等待 LLM 时在 stderr 显示轮换状态（Planning / 思考中等）。

- 仅当 stderr 为 TTY 时启用（pytest 捕获输出时自动关闭）。
- 设置环境变量 AICODE_NO_WAIT_HINT=1 可关闭。
- 遵守 NO_COLOR：不发送颜色序列，但仍轮换文案。
- 流式输出到 stdout 时不要启用：与 stderr 轮换行在终端里会交错，破坏正文（由 loop 传入 show_hint=False）。
"""
from __future__ import annotations

import os
import sys
import threading
from contextlib import contextmanager
from typing import Iterator

_MESSAGES = (
    "Planning…",
    "思考中…",
    "Thinking…",
    "Calling model…",
    "Working…",
    "请稍候…",
)


def wait_hint_enabled() -> bool:
    if os.environ.get("AICODE_NO_WAIT_HINT", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return False
    return sys.stderr.isatty()


def _use_ansi() -> bool:
    return bool(sys.stderr.isatty() and not os.environ.get("NO_COLOR", "").strip())


def _clear_line() -> None:
    if sys.stderr.isatty():
        if _use_ansi():
            sys.stderr.write("\r\033[2K")
        else:
            sys.stderr.write("\r" + " " * 48 + "\r")
    sys.stderr.flush()


class _LlmWaitHint:
    """在独立线程里刷新 stderr 状态行，直到 stop。"""

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _spin(self) -> None:
        i = 0
        dim = "\033[2m"
        reset = "\033[0m"
        color = _use_ansi()
        while not self._stop.is_set():
            msg = _MESSAGES[i % len(_MESSAGES)]
            if color:
                line = f"\r{dim}{msg}{reset}"
            else:
                line = f"\r{msg}"
            sys.stderr.write(line)
            sys.stderr.flush()
            if self._stop.wait(0.45):
                break
            i += 1

    def __enter__(self) -> None:
        if not wait_hint_enabled():
            self._thread = None
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def __exit__(self, *args: object) -> None:
        if self._thread is None:
            return
        self._stop.set()
        self._thread.join(timeout=3.0)
        _clear_line()
        self._thread = None


@contextmanager
def llm_wait_context(*, show_hint: bool = True) -> Iterator[None]:
    """包住一次可能较久的 LLM 请求。流式模式下请传 show_hint=False，避免 stderr 与 stdout 交错。"""
    if not show_hint or not wait_hint_enabled():
        yield
        return
    hint = _LlmWaitHint()
    hint.__enter__()
    try:
        yield
    finally:
        hint.__exit__(None, None, None)
