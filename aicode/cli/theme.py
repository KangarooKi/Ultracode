"""
REPL / 流式输出共用的终端配色（与提示符、助手左边框一致）。
"""
from __future__ import annotations

import os

_RESET = "\033[0m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
# 与历史版本一致：亮青提示符 + 助手左侧竖条
_CYAN_PRIMARY = "\033[38;5;45m"


def repl_prompt() -> str:
    """input() 用的 ❯ 提示符（青蓝加粗）。"""
    return f"{_CYAN_PRIMARY}{_BOLD}❯{_RESET} "


def assistant_left_border_prefix() -> str:
    """
    每一行正文前的左边框：重竖线 + 空格。
    NO_COLOR 时退化为 ASCII。
    """
    if os.environ.get("NO_COLOR", "").strip():
        return "│ "
    return f"{_CYAN_PRIMARY}┃{_RESET} "
