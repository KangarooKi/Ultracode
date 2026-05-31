"""
cli/repl.py — 交互式 REPL（Phase 1+2 集成）

中间件叠加顺序（外→内）见 cli/session.py 中 build_repl_context。
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

_DIM = "\033[2m"
_BLUE_ACCENT = "\033[38;5;33m"
_RESET = "\033[0m"


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
                print(f"{_DIM}assistant{_RESET}")
            try:
                run_agent_loop(ctx.loop_cfg, state)
            except KeyboardInterrupt:
                print("\n[interrupted]")

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


def _nanocode_rgb(t: float) -> tuple[int, int, int]:
    """Horizontal gradient like NanoCode banner: sky blue → grey-white → pale gold."""
    t = max(0.0, min(1.0, t))
    lo = (96, 188, 255)
    mid = (218, 222, 230)
    hi = (255, 236, 160)
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


def _nanocode_style_pixel_line(line: str) -> str:
    """Dark panel + bold block glyphs with per-column truecolor gradient (NanoCode-like)."""
    bg = (24, 26, 32)
    n = len(line)
    denom = max(n - 1, 1)
    parts: list[str] = [
        f"\033[48;2;{bg[0]};{bg[1]};{bg[2]}m\033[1m",
    ]
    for i, c in enumerate(line):
        if c == "█":
            r, g, b = _nanocode_rgb(i / denom)
            parts.append(f"\033[38;2;{r};{g};{b}m█")
        else:
            parts.append(" ")
    parts.append(_RESET)
    return "".join(parts)


def _pixel_ultracode_lines() -> list[str]:
    """5-line block-pixel spelling of ULTRACODE (█), for terminal banner."""
    g: dict[str, tuple[str, str, str, str, str]] = {
        "U": ("█   █", "█   █", "█   █", "█   █", " ███ "),
        "L": ("█    ", "█    ", "█    ", "█    ", "████ "),
        "T": ("█████", "  █  ", "  █  ", "  █  ", "  █  "),
        "R": ("████ ", "█   █", "████ ", "█ █  ", "█  █ "),
        "A": (" ███ ", "█   █", "█████", "█   █", "█   █"),
        "C": (" ███ ", "█    ", "█    ", "█    ", " ███ "),
        "O": (" ███ ", "█   █", "█   █", "█   █", " ███ "),
        "D": ("████ ", "█   █", "█   █", "█   █", "████ "),
        "E": ("█████", "█    ", "████ ", "█    ", "█████"),
    }
    word = "ULTRACODE"
    pad = "  "
    out = [""] * 5
    for ch in word:
        rows = g.get(ch, ("     ", "     ", "  ?  ", "     ", "     "))
        for i in range(5):
            out[i] += rows[i] + pad
    return out


def _print_meta_box(workdir: Path, model: str, version: str) -> None:
    """Box with light blue border; inside: only the word UltraCode is blue, no fill."""
    bc = (92, 178, 220)  # 浅蓝框线
    name_blue = (58, 132, 220)  # UltraCode 字样

    def esc_fg(rgb: tuple[int, int, int]) -> str:
        return f"\033[38;2;{rgb[0]};{rgb[1]};{rgb[2]}m"

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

    b = esc_fg(bc)
    nb = esc_fg(name_blue)
    r = _RESET

    pad1 = content_w - len(r1_plain)
    line1_inner = (
        f" {nb}UltraCode{r}{_DIM} v{version}{r}{' ' * pad1} "
    )
    line2_inner = f" {_DIM}{r2.ljust(content_w)}{r} "
    line3_inner = f" {_DIM}{r3.ljust(content_w)}{r} "

    print(f"{b}┌{'─' * h_inner}┐{r}")
    print(f"{b}│{r}{line1_inner}{b}│{r}")
    print(f"{b}│{r}{line2_inner}{b}│{r}")
    print(f"{b}│{r}{line3_inner}{b}│{r}")
    print(f"{b}└{'─' * h_inner}┘{r}")


def _print_welcome(workdir: Path, model: str) -> None:
    width = _terminal_width()
    rule = "·" * width
    print(f"{_DIM}{rule}{_RESET}")
    for line in _pixel_ultracode_lines():
        print(_nanocode_style_pixel_line(line))
    print()
    print(f"{_BLUE_ACCENT}  > build with flow, code with focus{_RESET}")
    _print_meta_box(workdir, model, __version__)
    print(f"{_DIM}/help  /todo  /tasks  /tools  /memories  /clear  /exit{_RESET}")
    print(f"{_DIM}{rule}{_RESET}\n")


def _print_assistant(text: str) -> None:
    width = _terminal_width()
    wrap_width = max(40, width - 6)
    print(f"{_DIM}assistant{_RESET}")
    border = theme.assistant_left_border_prefix()
    text = format_assistant_markdown(text)
    for raw in text.splitlines() or [""]:
        wrapped = textwrap.wrap(raw, width=wrap_width) or [""]
        for line in wrapped:
            print(f"{border}{line}")


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
        print(
            "/todo              — show session plan\n"
            "/tasks             — list persistent tasks\n"
            "/tools             — list registered tools\n"
            "/mcp               — list MCP-prefixed tools\n"
            "/memories          — list loaded memories\n"
            "/mode <default|plan|auto>  — switch permission mode\n"
            "/rules             — show permission rules\n"
            "/clear             — clear conversation history\n"
            "/exit              — quit"
        )
    elif cmd == "/todo":
        print(todo_mgr.render())
    elif cmd == "/tasks":
        print(task_mgr.list_all())
    elif cmd == "/tools":
        print("Registered tools:", ", ".join(registry.names()))
    elif cmd == "/mcp":
        mcp_names = [n for n in registry.names() if n.startswith("mcp__")]
        print(f"MCP tools ({len(mcp_names)}):", ", ".join(mcp_names) if mcp_names else "(none)")
    elif cmd == "/memories":
        if not memory_mgr.memories:
            print("No memories loaded.")
        else:
            for name, m in memory_mgr.memories.items():
                print(f"  [{m['type']}] {name}: {m['description']}")
    elif cmd == "/mode":
        if args and args[0] in ("default", "plan", "auto"):
            perm_mgr.mode = args[0]
            print(f"[Mode: {args[0]}]")
        else:
            print(f"Usage: /mode <default|plan|auto>  (current: {perm_mgr.mode})")
    elif cmd == "/rules":
        for i, rule in enumerate(perm_mgr.rules):
            print(f"  {i}: {rule}")
    elif cmd == "/clear":
        history.clear()
        print("History cleared.")
    else:
        print(f"Unknown command: {query}")
