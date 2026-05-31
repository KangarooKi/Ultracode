"""
流式助手正文：``` 围栏内原样；围栏外按行渲染标题/列表/引用 + 未完成行上的增量 ** 粗体。

flush 时对剩余缓冲调用 format_assistant_markdown。
"""
from __future__ import annotations

from collections.abc import Callable

from aicode.core.markdown_terminal import (
    _BOLD,
    _BOLD_RE,
    _RESET,
    format_assistant_markdown,
    format_markdown_line,
    format_plain_segment,
)


def _fence_hold_suffix_len(s: str) -> int:
    if s.endswith("``"):
        return 2
    if s.endswith("`"):
        return 1
    return 0


def _emit_bold_prefix(s: str) -> tuple[str, str]:
    """未完成行内仅做 **…** 的增量展开（与 markdown_terminal 语义一致）。"""
    out: list[str] = []
    rest = s
    while rest:
        m = _BOLD_RE.match(rest)
        if m:
            out.append(f"{_BOLD}{m.group(1)}{_RESET}")
            rest = rest[m.end() :]
            continue
        star = rest.find("*")
        if star < 0:
            out.append(rest)
            return "".join(out), ""
        if star > 0:
            out.append(rest[:star])
            rest = rest[star:]
            continue
        if not rest.startswith("**"):
            out.append(rest[0])
            rest = rest[1:]
            continue
        close = rest.find("**", 2)
        if close < 0:
            return "".join(out), rest
        inner = rest[2:close]
        if "*" not in inner:
            if inner:
                out.append(f"{_BOLD}{inner}{_RESET}")
            else:
                out.append("****")
            rest = rest[close + 2 :]
            continue
        out.append("**")
        rest = rest[2:]
        continue
    return "".join(out), ""


def _emit_partial_line_no_nl(s: str) -> tuple[str, str]:
    """
    尚未以 \\n 结束的片段：无 * 则整段保留（等待标题/列表等行级规则）；
    含 * 则按 **…** 尽量写出前缀。
    """
    if not s:
        return "", ""
    if "*" not in s:
        return "", s
    return _emit_bold_prefix(s)


class AssistantMarkdownStreamWriter:
    """
    包装底层 write；流结束后必须调用 flush()。
    """

    __slots__ = ("_write", "_buf", "_in_fence")

    def __init__(self, write: Callable[[str], None]) -> None:
        self._write = write
        self._buf = ""
        self._in_fence = False

    def write(self, piece: str) -> None:
        if not piece:
            return
        self._buf += piece
        self._emit_ready()

    def flush(self) -> None:
        if self._in_fence:
            if self._buf:
                self._write(self._buf)
                self._buf = ""
            return
        if self._buf:
            self._write(format_assistant_markdown(self._buf))
            self._buf = ""

    def _emit_ready(self) -> None:
        while True:
            if self._in_fence:
                idx = self._buf.find("```")
                if idx < 0:
                    h = _fence_hold_suffix_len(self._buf)
                    if h and len(self._buf) > h:
                        self._write(self._buf[:-h])
                        self._buf = self._buf[-h:]
                    return
                self._write(self._buf[: idx + 3])
                self._buf = self._buf[idx + 3 :]
                self._in_fence = False
                continue

            idx = self._buf.find("```")
            if idx < 0:
                last_nl = self._buf.rfind("\n")
                if last_nl >= 0:
                    complete = self._buf[: last_nl + 1]
                    self._buf = self._buf[last_nl + 1 :]
                    self._write(format_plain_segment(complete))
                    continue
                em, tail = _emit_partial_line_no_nl(self._buf)
                self._buf = tail
                if em:
                    self._write(em)
                return

            before = self._buf[:idx]
            after = self._buf[idx + 3 :]
            if before:
                last_nl = before.rfind("\n")
                if last_nl >= 0:
                    complete = before[: last_nl + 1]
                    tail = before[last_nl + 1 :]
                    self._write(format_plain_segment(complete))
                    if tail:
                        self._write(format_markdown_line(tail))
                    self._write("```")
                    self._buf = after
                else:
                    self._write(format_markdown_line(before))
                    self._write("```")
                    self._buf = after
            else:
                self._write("```")
                self._buf = after
            self._in_fence = True
            continue
