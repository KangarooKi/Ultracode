"""
security/permission.py — 权限管理（PermissionManager + PermissionMiddleware）

决策管线（四步，按顺序）：
  Step 0: Bash 安全校验（严重 → deny，警示 → ask）
  Step 1: deny_rules（第一匹配胜出）
  Step 2: 模式决策（plan / auto）
  Step 3: allow_rules
  Step 4: ask_user（默认回退）

作为 LoopMiddleware 实现，在 pre_tool 拦截不允许的调用。
"""
from __future__ import annotations

import json
import os
import re
import shlex
from fnmatch import fnmatch
from pathlib import Path

from aicode.core.loop import NoopMiddleware
from aicode.core.types import LoopState, ToolCall, ToolResult
from .validator import BashSecurityValidator

MODES = ("default", "plan", "auto")
WRITE_TOOLS = frozenset({
    "bash",
    "write_file",
    "edit_file",
    "background_run",
    "background_cancel",
    "subagent_call",
    "task_create",
    "task_update",
})
READ_ONLY_TOOLS = frozenset({
    "read_file",
    "bash_readonly",
    "task_list",
    "task_get",
    "background_check",
    "git_worktree_list",
})

DEFAULT_RULES: list[dict] = [
    {"tool": "bash", "content": "sudo *", "behavior": "deny"},
    {"tool": "read_file", "path": "*", "behavior": "allow"},
]

_validator = BashSecurityValidator()

_READONLY_BASH_COMMANDS = frozenset({
    "cat",
    "cut",
    "du",
    "file",
    "find",
    "grep",
    "head",
    "ls",
    "nl",
    "pwd",
    "rg",
    "sort",
    "stat",
    "tail",
    "tree",
    "uniq",
    "wc",
})
_READONLY_GIT_SUBCOMMANDS = frozenset({
    "branch",
    "diff",
    "grep",
    "log",
    "ls-files",
    "remote",
    "rev-parse",
    "show",
    "status",
    "tag",
    "worktree",
})

# write_file 确认前内容预览（避免只看 path/字节数）
_WRITE_PREVIEW_MAX_LINES = 56
_WRITE_PREVIEW_MAX_CHARS = 18_000

# 终端样式（权限提示）
_T_DIM = "\033[2m"
_T_MUTED = "\033[38;2;130;150;175m"
_T_ACCENT = "\033[38;2;100;180;220m"
_T_WARN = "\033[38;2;220;120;100m"
_T_RESET = "\033[0m"


def _print_write_file_preview(tool_input: dict) -> None:
    """在询问是否写入前，打印将写入的正文预览（过长则截断并注明）。"""
    path = tool_input.get("path", "")
    content = tool_input.get("content")
    if not isinstance(content, str):
        content = "" if content is None else str(content)
    n_bytes = len(content.encode("utf-8", errors="replace"))
    lines = content.splitlines()
    n_lines = len(lines) if content else 0
    print(
        f"  {_T_MUTED}path{_T_RESET} {_T_DIM}{path}{_T_RESET}  "
        f"{_T_MUTED}·{_T_RESET}  {_T_DIM}{n_bytes} bytes{_T_RESET}"
        f"{_T_MUTED} · {_T_DIM}{n_lines} lines{_T_RESET}"
    )
    print(f"  {_T_ACCENT}内容预览{_T_RESET} {_T_DIM}(写入前可核对){_T_RESET}")
    if not content:
        print(f"  {_T_DIM}│{_T_RESET} {_T_MUTED}(空文件){_T_RESET}")
        return

    line_cap = lines[:_WRITE_PREVIEW_MAX_LINES]
    blob = "\n".join(line_cap)
    truncated_by_lines = len(lines) > len(line_cap)
    if len(blob) > _WRITE_PREVIEW_MAX_CHARS:
        blob = blob[:_WRITE_PREVIEW_MAX_CHARS]
        cut = blob.rfind("\n")
        if cut >= 40:
            blob = blob[:cut]
        truncated_by_chars = blob != "\n".join(line_cap)
    else:
        truncated_by_chars = False

    for ln in blob.splitlines():
        print(f"  {_T_DIM}│{_T_RESET} {ln}")

    notes: list[str] = []
    if truncated_by_lines:
        notes.append(f"另有 {len(lines) - len(line_cap)} 行未显示")
    if truncated_by_chars:
        notes.append("预览已按长度截断")
    if notes:
        print(
            f"  {_T_MUTED}… {'；'.join(notes)}"
            f"（全文 {n_lines} 行，{n_bytes} 字节）{_T_RESET}"
        )


def _print_edit_file_preview(tool_input: dict) -> None:
    """edit_file 确认前展示将要替换的片段。"""
    path = tool_input.get("path", "")
    old_t = tool_input.get("old_text", "")
    new_t = tool_input.get("new_text", "")
    if not isinstance(old_t, str):
        old_t = "" if old_t is None else str(old_t)
    if not isinstance(new_t, str):
        new_t = "" if new_t is None else str(new_t)
    print(f"  {_T_MUTED}path{_T_RESET} {_T_DIM}{path}{_T_RESET}")
    o_prev = old_t[:400] + ("…" if len(old_t) > 400 else "")
    print(f"  {_T_MUTED}old_text{_T_RESET} {_T_DIM}({len(old_t)} chars){_T_RESET}")
    for line in o_prev.splitlines() or [o_prev]:
        print(f"  {_T_DIM}│{_T_RESET} {line}")
    print(f"  {_T_ACCENT}new_text 预览{_T_RESET} {_T_DIM}({len(new_t)} chars){_T_RESET}")
    char_used = 0
    shown = 0
    for line in new_t.splitlines():
        if shown >= _WRITE_PREVIEW_MAX_LINES:
            break
        if char_used + len(line) > _WRITE_PREVIEW_MAX_CHARS and shown > 0:
            break
        print(f"  {_T_DIM}│{_T_RESET} {line}")
        char_used += len(line) + 1
        shown += 1
    total_lines = new_t.count("\n") + (1 if new_t else 0)
    if shown < total_lines:
        print(
            f"  {_T_MUTED}… new_text 另省略 {total_lines - shown} 行"
            f"（共 {total_lines} 行）{_T_RESET}"
        )


def _format_permission_preview(tool_name: str, tool_input: dict) -> str:
    """可读摘要，避免 write_file 把整段 JSON 糊在屏幕上。"""
    if tool_name == "write_file":
        p = tool_input.get("path", "")
        c = tool_input.get("content", "")
        return f"path: {p}  ·  {len(c)} bytes"
    if tool_name == "edit_file":
        return f"path: {tool_input.get('path', '')}  ·  edit"
    if tool_name == "bash":
        cmd = tool_input.get("command", "") or ""
        cmd = cmd.replace("\n", " ").strip()
        if len(cmd) > 140:
            return cmd[:137] + "…"
        return cmd
    try:
        line = json.dumps(tool_input, ensure_ascii=False)
    except (TypeError, ValueError):
        line = str(tool_input)
    if len(line) > 180:
        return line[:177] + "…"
    return line


def _mcp_tool_read_like(tool_name: str) -> bool:
    parts = tool_name.split("__", 2)
    inner = parts[2].lower() if len(parts) == 3 else tool_name.lower()
    return any(inner.startswith(p) for p in ("read", "list", "get", "fetch", "search", "query", "show"))


def _auto_approve_readonly_bash() -> bool:
    raw = os.environ.get("AICODE_AUTO_APPROVE_READONLY_BASH", "1").strip().lower()
    return raw not in {"0", "false", "no", "off", "never"}


def _is_readonly_bash(command: str) -> bool:
    if not _auto_approve_readonly_bash():
        return False
    if _validator.severity(command) == "severe":
        return False
    if re.search(r"[;&`<>]|\$\(|\bIFS\s*=", command):
        return False

    segments = [seg.strip() for seg in command.split("|")]
    if not segments or any(not seg for seg in segments):
        return False
    return all(_is_readonly_simple_command(seg) for seg in segments)


def _is_readonly_simple_command(command: str) -> bool:
    try:
        parts = shlex.split(command)
    except ValueError:
        return False
    if not parts:
        return False

    exe = Path(parts[0]).name
    args = parts[1:]
    if exe == "git":
        if not args:
            return False
        subcmd = args[0]
        if subcmd == "-C" and len(args) >= 3:
            subcmd = args[2]
        return subcmd in _READONLY_GIT_SUBCOMMANDS

    if exe not in _READONLY_BASH_COMMANDS:
        return False
    if exe == "sed" and any(a == "-i" or a.startswith("-i.") for a in args):
        return False
    if exe == "find" and any(a in {"-delete", "-exec", "-execdir", "-ok"} for a in args):
        return False
    return True


class PermissionManager:
    """
    管理工具调用的权限决策。

    check() 返回: {"behavior": "allow"|"deny"|"ask", "reason": str}
    """

    def __init__(self, mode: str = "default", rules: list | None = None) -> None:
        if mode not in MODES:
            raise ValueError(f"Unknown mode {mode!r}. Choose from {MODES}")
        self.mode = mode
        self.rules: list[dict] = list(rules or DEFAULT_RULES)
        self.consecutive_denials = 0
        self.max_consecutive_denials = 3

    def check(self, tool_name: str, tool_input: dict) -> dict:
        # Step 0: bash 校验
        if tool_name == "bash":
            command = tool_input.get("command", "")
            sev = _validator.severity(command)
            if sev == "severe":
                return {"behavior": "deny", "reason": _validator.describe_failures(command)}
            if sev == "warn" and not _is_readonly_bash(command):
                return {"behavior": "ask", "reason": _validator.describe_failures(command)}

        # Step 1: deny rules（总是最先检查）
        for rule in self.rules:
            if rule["behavior"] != "deny":
                continue
            if self._matches(rule, tool_name, tool_input):
                return {"behavior": "deny", "reason": f"Blocked by deny rule: {rule}"}

        # Step 2: 模式
        if self.mode == "plan":
            if tool_name.startswith("mcp__"):
                return {"behavior": "deny", "reason": "Plan mode: MCP tools blocked."}
            if tool_name == "bash" and _is_readonly_bash(tool_input.get("command", "")):
                return {"behavior": "allow", "reason": "Plan mode: read-only bash allowed."}
            if tool_name in WRITE_TOOLS:
                return {"behavior": "deny", "reason": "Plan mode: write operations blocked."}
            return {"behavior": "allow", "reason": "Plan mode: read-only allowed."}

        if self.mode == "auto":
            if tool_name == "bash" and _is_readonly_bash(tool_input.get("command", "")):
                return {"behavior": "allow", "reason": "Auto mode: read-only bash auto-approved."}
            if tool_name in READ_ONLY_TOOLS or tool_name == "read_file":
                return {"behavior": "allow", "reason": "Auto mode: read-only auto-approved."}
            if tool_name.startswith("mcp__") and _mcp_tool_read_like(tool_name):
                return {"behavior": "allow", "reason": "Auto mode: read-like MCP auto-approved."}

        if tool_name == "bash" and _is_readonly_bash(tool_input.get("command", "")):
            return {"behavior": "allow", "reason": "Read-only bash auto-approved."}

        # Step 3: allow rules
        for rule in self.rules:
            if rule["behavior"] != "allow":
                continue
            if self._matches(rule, tool_name, tool_input):
                self.consecutive_denials = 0
                return {"behavior": "allow", "reason": f"Matched allow rule: {rule}"}

        # Step 4: ask
        return {"behavior": "ask", "reason": f"No rule matched for {tool_name!r}, asking user."}

    def ask_user(self, tool_name: str, tool_input: dict) -> bool:
        """交互式用户确认。返回 True 表示批准。"""
        print(
            f"\n  {_T_ACCENT}●{_T_RESET} {_T_MUTED}待确认{_T_RESET} "
            f"{_T_ACCENT}{tool_name}{_T_RESET}"
        )
        if tool_name == "write_file":
            _print_write_file_preview(tool_input)
        elif tool_name == "edit_file":
            _print_edit_file_preview(tool_input)
        else:
            preview = _format_permission_preview(tool_name, tool_input)
            print(f"  {_T_DIM}{preview}{_T_RESET}")
        try:
            answer = input(
                f"  {_T_DIM}允许执行？{_T_RESET} "
                f"{_T_MUTED}[y{_T_DIM} 是 · {_T_MUTED}n{_T_DIM} 否 · "
                f"{_T_MUTED}always{_T_DIM} 始终允许此工具]{_T_RESET} "
            ).strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False

        if answer == "always":
            self.rules.append({"tool": tool_name, "path": "*", "behavior": "allow"})
            self.consecutive_denials = 0
            return True
        if answer in ("y", "yes"):
            self.consecutive_denials = 0
            return True

        self.consecutive_denials += 1
        if self.consecutive_denials >= self.max_consecutive_denials:
            print(
                f"  {_T_DIM}已连续拒绝 {self.consecutive_denials} 次，"
                f"可尝试 {_T_MUTED}/mode plan{_T_RESET}{_T_DIM} 仅浏览{_T_RESET}"
            )
        return False

    def _matches(self, rule: dict, tool_name: str, tool_input: dict) -> bool:
        # 工具名匹配
        t = rule.get("tool", "*")
        if t != "*" and t != tool_name:
            return False
        # 路径 glob 匹配
        if "path" in rule and rule["path"] != "*":
            if not fnmatch(tool_input.get("path", ""), rule["path"]):
                return False
        # bash 内容 glob 匹配
        if "content" in rule:
            if not fnmatch(tool_input.get("command", ""), rule["content"]):
                return False
        return True


# ---------------------------------------------------------------------------
# Middleware 包装
# ---------------------------------------------------------------------------

class PermissionMiddleware(NoopMiddleware):
    """
    将 PermissionManager 接入循环的中间件。

    pre_tool：
      - deny  → 返回 ToolResult(denied) 拦截调用
      - ask   → 询问用户；拒绝则拦截
      - allow → 返回 None 放行
    """

    def __init__(self, manager: PermissionManager) -> None:
        self.manager = manager

    def pre_tool(self, call: ToolCall, state: LoopState) -> ToolResult | None:
        decision = self.manager.check(call.name, call.arguments)

        if decision["behavior"] == "deny":
            print(
                f"  {_T_WARN}✗ 已拦截{_T_RESET} {_T_DIM}{call.name}{_T_RESET} — "
                f"{_T_DIM}{decision['reason']}{_T_RESET}"
            )
            return ToolResult(call.id, f"Permission denied: {decision['reason']}", "denied")

        if decision["behavior"] == "ask":
            if not self.manager.ask_user(call.name, call.arguments):
                return ToolResult(call.id, f"Denied by user: {call.name}", "denied")

        return None  # allow
