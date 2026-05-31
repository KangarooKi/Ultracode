"""
REPL / 流式输出共用的终端配色（与提示符、助手左边框一致）。
"""
from __future__ import annotations

import os
import re

from dotenv import load_dotenv

load_dotenv(override=False)

_ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def no_color() -> bool:
    forced = os.environ.get("AICODE_COLOR", "").strip().lower()
    if forced in {"1", "true", "yes", "on", "always"}:
        return False
    if forced in {"0", "false", "no", "off", "never"}:
        return True
    return bool(os.environ.get("NO_COLOR", "").strip())


def ansi(code: str) -> str:
    return "" if no_color() else f"\033[{code}m"


RESET = ansi("0")
DIM = ansi("2")
BOLD = ansi("1")
MUTED = ansi("38;2;128;146;168")
PRIMARY = ansi("38;2;88;190;235")
PRIMARY_SOFT = ansi("38;2;128;210;238")
GOLD = ansi("38;2;236;198;107")
GREEN = ansi("38;2;116;208;156")
WARN = ansi("38;2;240;174;92")
ERROR = ansi("38;2;235;118;106")
PANEL = ansi("38;2;80;118;148")
CODE_BG = ansi("2;48;5;236")


def style(text: str, *codes: str) -> str:
    if no_color() or not codes:
        return text
    return "".join(codes) + text + RESET


def dim(text: str) -> str:
    return style(text, DIM)


def bold(text: str) -> str:
    return style(text, BOLD)


def primary(text: str) -> str:
    return style(text, PRIMARY)


def muted(text: str) -> str:
    return style(text, MUTED)


def gold(text: str) -> str:
    return style(text, GOLD)


def green(text: str) -> str:
    return style(text, GREEN)


def warn(text: str) -> str:
    return style(text, WARN)


def error(text: str) -> str:
    return style(text, ERROR)


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def visible_len(text: str) -> int:
    return len(strip_ansi(text))


def pad_right(text: str, width: int) -> str:
    return text + " " * max(0, width - visible_len(text))


def truncate(text: str, width: int) -> str:
    plain = strip_ansi(text)
    if len(plain) <= width:
        return text
    if width <= 1:
        return "…" if width else ""
    return plain[: width - 1] + "…"


def badge(text: str, tone: str = "primary") -> str:
    if no_color():
        return f"[{text}]"
    colors = {
        "primary": PRIMARY,
        "muted": MUTED,
        "gold": GOLD,
        "green": GREEN,
        "warn": WARN,
        "error": ERROR,
    }
    return f"{DIM}[{RESET}{style(text, colors.get(tone, PRIMARY), BOLD)}{DIM}]{RESET}"


def status_dot(status: str) -> str:
    status = status.lower()
    if no_color():
        return {"ok": "+", "error": "!", "denied": "x", "blocked": "x"}.get(status, "-")
    color = {
        "ok": GREEN,
        "error": ERROR,
        "denied": WARN,
        "blocked": WARN,
    }.get(status, MUTED)
    return style("●", color)


def repl_prompt() -> str:
    """input() 用的 ❯ 提示符（青蓝加粗）。"""
    if no_color():
        return "> "
    return f"{PRIMARY}{BOLD}❯{RESET} "


def assistant_left_border_prefix() -> str:
    """
    每一行正文前的左边框：重竖线 + 空格。
    NO_COLOR 时退化为 ASCII。
    """
    if no_color():
        return "│ "
    return f"{PRIMARY}┃{RESET} "
