"""
cli/main.py — 命令行入口

- ultracode / ultracode repl    交互式 REPL
- ultracode run …                单条用户消息（可加 -v 打印工具）
- ultracode tasks / worktrees    仅查磁盘与 git，不需要 LLM 密钥
- ultracode --version / -C DIR
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _workspace(args: argparse.Namespace) -> Path:
    if args.cwd is not None:
        return args.cwd.resolve()
    return Path.cwd().resolve()


def main(argv: list[str] | None = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(
        prog="ultracode",
        description="UltraCode - 类 Claude Code 的本地 AI 辅助编程 CLI",
    )
    parser.add_argument(
        "-C",
        "--cwd",
        type=Path,
        default=None,
        metavar="DIR",
        help="工作区根目录（文件工具、.tasks/.memory 等相对此目录；默认当前目录）",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="打印版本号并退出",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="与 run 联用：打印工具调用摘要（默认仅输出最终助手回复）",
    )
    sub = parser.add_subparsers(dest="cmd", help="子命令")
    sub.add_parser("repl", help="启动交互式 REPL（可省略，默认即 repl）")
    sub.add_parser("tasks", help="列出持久化任务目录 .tasks（无需 API 密钥）")
    sub.add_parser("worktrees", help="在工作区执行 git worktree list（无需 API 密钥）")
    run_p = sub.add_parser("run", help="执行单条用户消息后退出")
    run_p.add_argument(
        "prompt",
        nargs=argparse.REMAINDER,
        help="用户消息；多词拼接为一行。单独传 - 则从 stdin 读取全文",
    )

    args = parser.parse_args(argv)

    if args.version:
        from aicode import __version__

        print(__version__)
        return

    workdir_arg: Path | None = args.cwd
    if workdir_arg is not None:
        workdir_arg = workdir_arg.resolve()

    cmd = args.cmd

    if cmd == "tasks":
        from aicode.planning.task_graph import TaskManager

        wd = _workspace(args)
        print(TaskManager(wd / ".tasks").list_all())
        return

    if cmd == "worktrees":
        from aicode.worktrees.git import list_worktrees

        print(list_worktrees(_workspace(args)))
        return

    if cmd is None or cmd == "repl":
        from aicode.cli.repl import run_repl

        run_repl(workdir_arg)
        return

    if cmd == "run":
        parts = list(args.prompt)
        if len(parts) == 1 and parts[0] == "-":
            text = sys.stdin.read().strip()
        else:
            text = " ".join(parts).strip()
        if not text:
            run_p.error(
                "需要 prompt，例如: ultracode run \"说明 src 目录结构\"，或 echo hi | ultracode run -"
            )

        from aicode.cli.output_fmt import format_assistant_markdown
        from aicode.cli.session import build_repl_context, run_agent_turn, session_cleanup

        ctx = build_repl_context(workdir_arg, quiet_tools=not args.verbose)
        try:
            messages: list = [{"role": "user", "content": text}]
            out, streamed = run_agent_turn(ctx, messages)
            if out and not streamed:
                print(format_assistant_markdown(out))
            elif streamed:
                print()
        finally:
            session_cleanup(ctx)
        return

    parser.error(f"未知子命令: {cmd}")


if __name__ == "__main__":
    main()
