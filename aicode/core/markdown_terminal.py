"""
将常见 Markdown 结构转为终端 ANSI（非完整 MD 解析器）。

- ATX 标题 #～######：整行显示为加粗正文（去掉前缀 # 与可选尾部 #）
- 无序列表 -/*/+ ：行首标记换为暗淡的 •
- 有序列表 1. / 1) ：序号部分用暗淡样式
- 引用 > ：前缀 │
- 行内 **粗体**：与历史行为一致
- 行内 `code`：暗底高亮（轻量）
- 分隔线 ---/***：暗淡横线
- GFM 表格（| 列 | + |---| 分隔行）：按列宽补空格对齐竖线
- ``` 围栏：渲染为代码块面板；内部原样保留
"""
from __future__ import annotations

import re
import unicodedata

_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_UNDERLINE = "\033[4m"

_FENCE_RE = re.compile(r"```[\s\S]*?```", re.MULTILINE)
_ANSI_RE = re.compile(r"\033\[[0-9;]*m")
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_CODE_RE = re.compile(r"`([^`]+)`")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_STRIKE_RE = re.compile(r"~~([^~]+)~~")

_HEADER_RE = re.compile(r"^(#{1,6})\s+(.+)$")
# 常见列表前缀：-, *, +, en-dash, em-dash, minus sign, fullwidth hyphen
_UL_RE = re.compile(r"^(\s*)[-*+\u2013\u2014\u2212\uff0d]\s+(.+)$")
_OL_RE = re.compile(r"^(\s*)(\d+)([.)])\s+(.+)$")
_QUOTE_RE = re.compile(r"^(\s*)>\s?(.*)$")
_HR_RE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
# GFM 表头分隔行：| --- | :---: | ---: |
_SEP_CELL_RE = re.compile(r"^:?-{3,}:?$")


def apply_inline_bold(s: str) -> str:
    return _BOLD_RE.sub(lambda m: f"{_BOLD}{m.group(1)}{_RESET}", s)


def apply_inline_markdown(s: str) -> str:
    """行内渲染：常见 Markdown inline 语法到 ANSI。"""
    s = apply_inline_bold(s)
    s = _STRIKE_RE.sub(lambda m: f"{_DIM}{m.group(1)}{_RESET}", s)
    s = _LINK_RE.sub(
        lambda m: f"{_UNDERLINE}{m.group(1)}{_RESET}{_DIM} ({m.group(2)}){_RESET}",
        s,
    )
    # 轻量 code 样式：dim + 反显背景，兼容多数终端主题。
    return _CODE_RE.sub(lambda m: f"\033[2;48;5;236m {m.group(1)} {_RESET}", s)


def format_markdown_line(core: str) -> str:
    """单行（不含换行符）：结构语法 + 行内样式。"""
    if not core:
        return core

    if _HR_RE.match(core):
        return f"{_DIM}{'─' * 28}{_RESET}"

    m = _HEADER_RE.match(core)
    if m:
        title = m.group(2).rstrip().rstrip("#").strip()
        return f"{_BOLD}{apply_inline_markdown(title)}{_RESET}"

    m = _QUOTE_RE.match(core)
    if m:
        ind, body = m.group(1), m.group(2)
        return f"{ind}{_DIM}│{_RESET} {apply_inline_markdown(body)}"

    m = _UL_RE.match(core)
    if m:
        ind, body = m.group(1), m.group(2)
        return f"{ind}{_DIM}•{_RESET} {apply_inline_markdown(body)}"

    m = _OL_RE.match(core)
    if m:
        ind, num, punct, body = m.group(1), m.group(2), m.group(3), m.group(4)
        return f"{ind}{_DIM}{num}{punct}{_RESET} {apply_inline_markdown(body)}"

    return apply_inline_markdown(core)


def _is_table_row_line(line: str) -> bool:
    s = line.strip()
    return bool(s.startswith("|") and s.endswith("|") and s.count("|") >= 2)


def _is_gfm_separator_row(line: str) -> bool:
    if not _is_table_row_line(line):
        return False
    s = line.strip()
    inner = s[1:-1]
    cells = [c.strip() for c in inner.split("|")]
    if not cells:
        return False
    return all(_SEP_CELL_RE.match(c) for c in cells if c)


def _split_gfm_table_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _plain_width(cell: str) -> str:
    """用于测宽的纯文本（去掉行内 markdown/ANSI 标记）。"""
    cell = _ANSI_RE.sub("", cell)
    no_bold = _BOLD_RE.sub(r"\1", cell)
    no_strike = _STRIKE_RE.sub(r"\1", no_bold)
    no_links = _LINK_RE.sub(lambda m: f"{m.group(1)} ({m.group(2)})", no_strike)
    return _CODE_RE.sub(r" \1 ", no_links)


def _display_width(s: str) -> int:
    """
    终端显示宽度估算：
    - East Asian Wide/Fullwidth 记为 2
    - 组合字符记为 0
    - 其余记为 1
    """
    w = 0
    for ch in s:
        if unicodedata.combining(ch):
            continue
        if unicodedata.east_asian_width(ch) in ("W", "F"):
            w += 2
        else:
            w += 1
    return w


def format_fenced_code(raw: str) -> str:
    """Render a fenced code block while preserving code text exactly."""
    if not raw.startswith("```"):
        return raw

    inner = raw[3:]
    if inner.endswith("```"):
        inner = inner[:-3]

    header, sep, body = inner.partition("\n")
    lang = header.strip() if sep else ""
    if not sep:
        body = ""
    label = lang or "code"

    code_lines = body.splitlines()
    if not code_lines:
        code_lines = [""]

    label_plain = label[:32]
    top = f"{_DIM}╭─ {_BOLD}{label_plain}{_RESET}"
    bottom = f"{_DIM}╰─{_RESET}"
    rendered = [top]
    for line in code_lines:
        rendered.append(f"{_DIM}│{_RESET} {line.expandtabs(4)}")
    rendered.append(bottom)
    return "\n".join(rendered)


def _format_gfm_tables(text: str) -> str:
    """
    将连续的 GFM 表格块（表头 + |---| + 数据行）转为列对齐的终端行。
    避免 | 工具 | 描述 | 因半角/全角混用或内容长短导致竖线错位。
    """
    if "|" not in text:
        return text
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        if (
            i + 1 < len(lines)
            and _is_table_row_line(lines[i])
            and _is_gfm_separator_row(lines[i + 1])
        ):
            header = _split_gfm_table_row(lines[i])
            j = i + 2
            body: list[list[str]] = []
            while j < len(lines) and _is_table_row_line(lines[j]) and not _is_gfm_separator_row(
                lines[j]
            ):
                body.append(_split_gfm_table_row(lines[j]))
                j += 1
            ncols = max(len(header), max((len(r) for r in body), default=0))
            if ncols == 0:
                out.append(lines[i])
                i += 1
                continue

            def _norm(row: list[str]) -> list[str]:
                r = row[:ncols] + [""] * (ncols - len(row))
                return r[:ncols]

            header = _norm(header)
            body = [_norm(r) for r in body]
            widths = [0] * ncols
            for row in [header] + body:
                for ci, cell in enumerate(row):
                    widths[ci] = max(widths[ci], _display_width(_plain_width(cell)))

            def _fmt_row(row: list[str]) -> str:
                parts: list[str] = []
                for ci, cell in enumerate(row):
                    plain = _plain_width(cell)
                    pad = max(0, widths[ci] - _display_width(plain))
                    parts.append(apply_inline_markdown(cell) + " " * pad)
                return "| " + " | ".join(parts) + " |"

            sep_inner = " | ".join("-" * max(3, w) for w in widths)
            out.append(_fmt_row(header))
            out.append("| " + sep_inner + " |")
            for row in body:
                out.append(_fmt_row(row))
            i = j
        else:
            out.append(lines[i])
            i += 1
    return "\n".join(out)


def format_plain_segment(text: str) -> str:
    """围栏外片段：GFM 表格对齐 → 按行处理标题/列表/引用/粗体。"""
    if not text:
        return text
    text = _format_gfm_tables(text)
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    for line in lines:
        if line.endswith("\n"):
            core, nl = line[:-1], "\n"
        else:
            core, nl = line, ""
        out.append(format_markdown_line(core) + nl)
    return "".join(out)


def format_assistant_markdown(text: str) -> str:
    """
    将 Markdown 常见结构转为终端样式；```...``` 渲染为代码块面板。
    """
    if not text:
        return text
    parts: list[str] = []
    pos = 0
    for m in _FENCE_RE.finditer(text):
        parts.append(format_plain_segment(text[pos : m.start()]))
        parts.append(format_fenced_code(m.group(0)))
        pos = m.end()
    parts.append(format_plain_segment(text[pos:]))
    return "".join(parts)
