"""
cli/repl.py — 交互式终端会话

负责读取用户输入、处理斜杠命令、打印欢迎界面，并把普通请求交给
cli/session.py 组装好的 Agent loop 运行时。
"""
from __future__ import annotations

import shutil
import textwrap
from pathlib import Path

try:
    import readline

    readline.parse_and_bind("set input-meta on")
    readline.parse_and_bind("set output-meta on")
    readline.parse_and_bind("set convert-meta off")
except ImportError:
    pass

from aicode import __version__
from aicode.cli import theme
from aicode.cli.output_fmt import format_assistant_markdown
from aicode.cli.session import build_repl_context, session_cleanup
from aicode.core.loop import extract_last_text, run_agent_loop
from aicode.core.types import LoopState
from aicode.memory.manager import MemoryManager
from aicode.planning.task_graph import TaskManager
from aicode.planning.todo import TodoManager
from aicode.security.permission import PermissionManager


def run_repl(workdir: Path | None = None) -> None:
    ctx = build_repl_context(workdir, quiet_tools=False)
    try:
        cfg = ctx.config
        workdir_resolved = cfg.workdir

        history: list = []
        _print_welcome(workdir_resolved, cfg.model)

        while True:
            try:
                query = input(theme.repl_prompt())
            except (EOFError, KeyboardInterrupt):
                print("\nBye.")
                break

            query = query.strip()
            if not query:
                continue

            if query.lower() == "exit":
                print("Bye.")
                break

            if query.startswith("/"):
                _handle_slash(
                    query,
                    ctx.todo_mgr,
                    ctx.task_mgr,
                    ctx.registry,
                    ctx.perm_mgr,
                    ctx.memory_mgr,
                    history,
                )
                print()
                continue

            history.append({"role": "user", "content": query})
            state = LoopState(messages=history, max_turns=cfg.max_turns)
            if ctx.loop_cfg.stream:
                print(theme.badge("assistant", "primary"))
            try:
                run_agent_loop(ctx.loop_cfg, state)
            except KeyboardInterrupt:
                print(f"\n{theme.warn('[interrupted]')}")

            text = extract_last_text(state)
            if text:
                if state.metadata.get("last_assistant_streamed_chars", 0) > 0:
                    print()
                else:
                    _print_assistant(text)
            print()
    finally:
        session_cleanup(ctx)


def _terminal_width(default: int = 88) -> int:
    width = shutil.get_terminal_size((default, 24)).columns
    return max(60, min(width, 120))


def _brand_rgb(t: float) -> tuple[int, int, int]:
    """Wordmark gradient: bright cyan → soft ice → warm gold."""
    t = max(0.0, min(1.0, t))
    lo = (80, 196, 245)
    mid = (214, 229, 236)
    hi = (244, 202, 104)
    if t < 0.5:
        u = t * 2.0
        return (
            int(lo[0] + (mid[0] - lo[0]) * u),
            int(lo[1] + (mid[1] - lo[1]) * u),
            int(lo[2] + (mid[2] - lo[2]) * u),
        )
    u = (t - 0.5) * 2.0
    return (
        int(mid[0] + (hi[0] - mid[0]) * u),
        int(mid[1] + (hi[1] - mid[1]) * u),
        int(mid[2] + (hi[2] - mid[2]) * u),
    )


def _style_wordmark_line(line: str) -> str:
    """Apply a horizontal truecolor gradient to non-space logo characters."""
    if theme.no_color():
        return line
    n = len(line)
    denom = max(n - 1, 1)
    parts: list[str] = [theme.BOLD]
    for i, c in enumerate(line):
        if c == " ":
            parts.append(" ")
        else:
            r, g, b = _brand_rgb(i / denom)
            parts.append(f"\033[38;2;{r};{g};{b}m{c}")
    parts.append(theme.RESET)
    return "".join(parts)


def _wordmark_lines() -> list[str]:
    """Compact ANSI-style UltraCode wordmark, tuned for 80-column terminals."""
    return [
        "██╗   ██╗██╗  ████████╗██████╗  █████╗   ██████╗ ██████╗ ██████╗ ███████╗",
        "██║   ██║██║  ╚══██╔══╝██╔══██╗██╔══██╗ ██╔════╝██╔═══██╗██╔══██╗██╔════╝",
        "██║   ██║██║     ██║   ██████╔╝███████║ ██║     ██║   ██║██║  ██║█████╗  ",
        "██║   ██║██║     ██║   ██╔══██╗██╔══██║ ██║     ██║   ██║██║  ██║██╔══╝  ",
        "╚██████╔╝███████╗██║   ██║  ██║██║  ██║ ╚██████╗╚██████╔╝██████╔╝███████╗",
        " ╚═════╝ ╚══════╝╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝",
    ]


def _print_wordmark(width: int) -> None:
    lines = _wordmark_lines()
    longest = max(len(line) for line in lines)
    if width < longest + 2:
        print("  " + theme.style("UltraCode", theme.PRIMARY, theme.BOLD))
        print("  " + theme.dim("agentic coding CLI"))
        return
    indent = " " * max(0, (width - longest) // 2)
    for line in lines:
        print(indent + _style_wordmark_line(line))


def _print_meta_box(workdir: Path, model: str, version: str) -> None:
    """Box with light blue border; inside: only the word UltraCode is blue, no fill."""
    tw = _terminal_width()
    max_path = max(24, tw - 10)
    ws = str(workdir)
    if len(ws) > max_path:
        ws = ws[: max_path - 3] + "..."

    r1_plain = f"UltraCode v{version}"
    r2 = f"workspace: {ws}"
    r3 = f"model: {model}"
    content_w = max(len(r1_plain), len(r2), len(r3))
    h_inner = content_w + 2  # " " + text + " " between │

    pad1 = content_w - len(r1_plain)
    line1_inner = (
        f" {theme.style('UltraCode', theme.PRIMARY, theme.BOLD)}"
        f"{theme.dim(f' v{version}')}{' ' * pad1} "
    )
    line2_inner = f" {theme.dim(r2.ljust(content_w))} "
    line3_inner = f" {theme.dim(r3.ljust(content_w))} "

    b = theme.PANEL
    r = theme.RESET
    print(f"{b}┌{'─' * h_inner}┐{r}")
    print(f"{b}│{r}{line1_inner}{b}│{r}")
    print(f"{b}│{r}{line2_inner}{b}│{r}")
    print(f"{b}│{r}{line3_inner}{b}│{r}")
    print(f"{b}└{'─' * h_inner}┘{r}")


def _print_welcome(workdir: Path, model: str) -> None:
    width = _terminal_width()
    rule = "·" * width
    print(theme.dim(rule))
    _print_wordmark(width)
    print()
    print(f"  {theme.gold('ready')} {theme.dim('build with flow, code with focus')}")
    _print_meta_box(workdir, model, __version__)
    _print_chips(["/help", "/todo", "/tasks", "/tools", "/memories", "/clear", "/exit"])
    print(theme.dim(rule) + "\n")


def _print_assistant(text: str) -> None:
    width = _terminal_width()
    wrap_width = max(40, width - 6)
    print(theme.badge("assistant", "primary"))
    border = theme.assistant_left_border_prefix()
    text = format_assistant_markdown(text)
    for raw in text.splitlines() or [""]:
        plain = theme.strip_ansi(raw).strip()
        if (
            plain.startswith("|") and plain.endswith("|")
        ) or plain.startswith(("╭─", "│ ", "╰─")):
            print(f"{border}{raw}")
            continue
        wrapped = textwrap.wrap(raw, width=wrap_width) or [""]
        for line in wrapped:
            print(f"{border}{line}")


def _print_chips(items: list[str]) -> None:
    print("  " + " ".join(theme.badge(item, "muted") for item in items))


def _print_panel(title: str, lines: list[str], tone: str = "primary") -> None:
    width = _terminal_width()
    plain_lines = [theme.strip_ansi(line) for line in lines] or [""]
    content_w = min(
        max([len(title), *(len(line) for line in plain_lines)], default=0),
        width - 6,
    )
    color = theme.PRIMARY if tone == "primary" else theme.PANEL
    print(
        f"{color}┌─ {theme.bold(title)} "
        f"{'─' * max(0, content_w - len(title) - 1)}┐{theme.RESET}"
    )
    for line in lines or [""]:
        clipped = theme.truncate(line, content_w)
        print(
            f"{color}│{theme.RESET} {theme.pad_right(clipped, content_w)} "
            f"{color}│{theme.RESET}"
        )
    print(f"{color}└{'─' * (content_w + 2)}┘{theme.RESET}")


def _print_table(title: str, headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> None:
    if not rows:
        _print_panel(title, [theme.dim("(none)")])
        return
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], theme.visible_len(cell))
    tw = _terminal_width()
    total = sum(widths) + 3 * (len(widths) - 1)
    if total > tw - 4 and widths:
        widths[-1] = max(16, widths[-1] - (total - (tw - 4)))

    header_line = "   ".join(
        theme.pad_right(theme.muted(h), widths[i]) for i, h in enumerate(headers)
    )
    body = [header_line, theme.dim("─" * min(tw - 4, theme.visible_len(header_line)))]
    for row in rows:
        body.append(
            "   ".join(
                theme.pad_right(theme.truncate(cell, widths[i]), widths[i])
                for i, cell in enumerate(row)
            )
        )
    _print_panel(title, body, tone="panel")


def _print_wrapped_text(title: str, text: str) -> None:
    width = _terminal_width()
    lines: list[str] = []
    for raw in text.splitlines() or [""]:
        lines.extend(textwrap.wrap(raw, width=max(40, width - 8)) or [""])
    _print_panel(title, lines)


def _handle_slash(
    query: str,
    todo_mgr: TodoManager,
    task_mgr: TaskManager,
    registry,
    perm_mgr: PermissionManager,
    memory_mgr: MemoryManager,
    history: list,
) -> None:
    cmd = query.lower().split()[0]
    args = query.split()[1:]

    if cmd in ("/exit", "/quit", "/q"):
        raise SystemExit(0)
    elif cmd == "/help":
        _print_table(
            "Commands",
            ("command", "action"),
            [
                (theme.primary("/todo"), "show session plan"),
                (theme.primary("/tasks"), "list persistent tasks"),
                (theme.primary("/tools"), "list registered tools"),
                (theme.primary("/mcp"), "list MCP-prefixed tools"),
                (theme.primary("/memories"), "list loaded memories"),
                (theme.primary("/mode default|plan|auto"), "switch permission mode"),
                (theme.primary("/rules"), "show permission rules"),
                (theme.primary("/clear"), "clear conversation history"),
                (theme.primary("/exit"), "quit"),
            ],
        )
    elif cmd == "/todo":
        _print_wrapped_text("Todo", todo_mgr.render())
    elif cmd == "/tasks":
        _print_wrapped_text("Tasks", task_mgr.list_all())
    elif cmd == "/tools":
        names = sorted(registry.names())
        rows = [(theme.primary(n), _tool_group(n)) for n in names]
        _print_table("Tools", ("name", "group"), rows)
    elif cmd == "/mcp":
        mcp_names = sorted(n for n in registry.names() if n.startswith("mcp__"))
        rows = [(theme.primary(n), _mcp_server_name(n)) for n in mcp_names]
        _print_table(f"MCP Tools ({len(mcp_names)})", ("tool", "server"), rows)
    elif cmd == "/memories":
        if not memory_mgr.memories:
            _print_panel("Memories", [theme.dim("No memories loaded.")])
        else:
            rows = []
            for name, m in memory_mgr.memories.items():
                rows.append((theme.primary(name), str(m["type"]), str(m["description"])))
            _print_table("Memories", ("name", "type", "description"), rows)
    elif cmd == "/mode":
        if args and args[0] in ("default", "plan", "auto"):
            perm_mgr.mode = args[0]
            _print_panel(
                "Mode",
                [f"{theme.status_dot('ok')} permission mode: {theme.gold(args[0])}"],
            )
        else:
            _print_panel(
                "Mode",
                [
                    f"Usage: {theme.primary('/mode <default|plan|auto>')}",
                    f"Current: {theme.gold(perm_mgr.mode)}",
                ],
            )
    elif cmd == "/rules":
        rows = [
            (
                theme.dim(str(i)),
                theme.primary(str(rule.get("tool", "*"))),
                str(rule.get("behavior", "")),
                _rule_match_summary(rule),
            )
            for i, rule in enumerate(perm_mgr.rules)
        ]
        _print_table("Permission Rules", ("#", "tool", "behavior", "match"), rows)
    elif cmd == "/clear":
        history.clear()
        _print_panel("History", [f"{theme.status_dot('ok')} cleared"])
    else:
        _print_panel("Unknown Command", [f"{theme.warn(query)}", "Try /help."])


def _tool_group(name: str) -> str:
    if name.startswith("mcp__"):
        return "mcp"
    if name.startswith("task_"):
        return "tasks"
    if name.startswith("background_"):
        return "background"
    if name in {"read_file", "write_file", "edit_file", "bash"}:
        return "workspace"
    if name in {"todo", "git_worktree_list", "subagent_call"}:
        return "agent"
    return "other"


def _mcp_server_name(name: str) -> str:
    parts = name.split("__", 2)
    return parts[1] if len(parts) == 3 else ""


def _rule_match_summary(rule: dict) -> str:
    bits = []
    if "path" in rule:
        bits.append(f"path={rule['path']}")
    if "content" in rule:
        bits.append(f"content={rule['content']}")
    return ", ".join(bits) or "*"
