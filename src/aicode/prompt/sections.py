"""
prompt/sections.py — 系统提示各段落构建函数

每个函数独立负责一段，单独测试。
段落：core / tool_listing / skill_listing / memory / claude_md / agents_md / dynamic
"""
from __future__ import annotations

import datetime
import platform
import re
from pathlib import Path


def build_core(workdir: Path) -> str:
    return (
        f"You are UltraCode, an AI coding assistant. Your workspace root is:\n"
        f"  {workdir}\n"
        "Treat paths as relative to this root unless the user specifies an absolute path.\n\n"
        "## How you work\n"
        "- Use the provided tools to explore, read, search, run commands, and edit files. "
        "Prefer tools over guessing; open or search the codebase before you claim how it works.\n"
        "- Read enough context to make correct edits: open the files you will change, "
        "check call sites and tests when relevant.\n"
        "- Make focused, minimal changes that solve the task. Match existing style, naming, "
        "and patterns in the repo.\n"
        "- After substantive edits, sanity-check: imports, obvious syntax issues, and whether "
        "tests or build steps the user cares about still make sense.\n\n"
        "## Communication\n"
        "- Be direct and structured. Use short headings or bullets when it helps.\n"
        "- Mention concrete file paths and symbols when you refer to code.\n"
        "- If you are unsure, say what you assumed and what would confirm it.\n"
        "- **After you create or substantially edit a file that contains code**, your reply must "
        "**show the user that code** (or the changed parts) in the message body—do not only "
        "describe tools or ask for confirmation without any visible code. Put excerpts in fenced "
        "markdown code blocks (```) with a language tag when helpful.\n"
        "- **If the file is long**, show a leading excerpt (e.g. first ~35–50 lines or ~2500 "
        "characters), then a single summary line such as `… (N more lines)` so the user sees "
        "substance without dumping the whole file.\n"
        "- Do not end your turn asking to write/save when the user already asked for code, "
        "without having shown what you intend to write.\n"
        "- **`write_file` must include the complete `content` string** you want on disk (not a "
        "placeholder). The CLI shows a **content preview** from that payload **before** the user "
        "can approve the write—so they always see what will be written, even if your reply text "
        "is short.\n\n"
        "## Rules and priorities\n"
        "- Follow project rules in AGENTS.md, CLAUDE.md, and injected memories when they apply.\n"
        "- Honor the user's intent and constraints (language, frameworks, 'do not change X').\n"
        "- Do not exfiltrate secrets or run destructive commands unless the user clearly asks.\n"
        "- When tools require approval or are denied, adapt: suggest a safer alternative or "
        "narrower scope.\n\n"
        "## Tools and planning\n"
        "- Use todo / task tools for multi-step work so progress stays visible.\n"
        "- Prefer reading and small exploratory commands before large refactors.\n"
        "Act first when safe, then summarize what you did and what remains."
    )


def build_tool_listing(schemas: list[dict]) -> str:
    if not schemas:
        return ""
    lines = ["# Available tools"]
    for tool in schemas:
        fn = tool.get("function", tool)
        name = fn.get("name", "?")
        desc = fn.get("description", "")
        props = fn.get("parameters", {}).get("properties", {})
        params = ", ".join(props.keys())
        lines.append(f"- {name}({params}): {desc}")
    return "\n".join(lines)


def build_skill_listing(skills_dir: Path) -> str:
    if not skills_dir.exists():
        return ""
    skills = []
    for skill_dir in sorted(skills_dir.iterdir()):
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        text = skill_md.read_text(encoding="utf-8", errors="replace")
        m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
        if not m:
            continue
        meta = {}
        for line in m.group(1).splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                meta[k.strip()] = v.strip()
        name = meta.get("name", skill_dir.name)
        desc = meta.get("description", "")
        skills.append(f"- {name}: {desc}")
    if not skills:
        return ""
    return "# Available skills\n" + "\n".join(skills)


def build_memory_section(memory_dir: Path) -> str:
    if not memory_dir.exists():
        return ""
    memories = []
    for md_file in sorted(memory_dir.glob("*.md")):
        if md_file.name == "MEMORY.md":
            continue
        text = md_file.read_text(encoding="utf-8", errors="replace")
        m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", text, re.DOTALL)
        if not m:
            continue
        header, body = m.group(1), m.group(2).strip()
        meta = {}
        for line in header.splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                meta[k.strip()] = v.strip()
        name = meta.get("name", md_file.stem)
        mem_type = meta.get("type", "project")
        desc = meta.get("description", "")
        memories.append(f"[{mem_type}] {name}: {desc}\n{body}")
    if not memories:
        return ""
    return "# Memories (persistent)\n\n" + "\n\n".join(memories)


def build_claude_md(workdir: Path) -> str:
    """
    链式加载 CLAUDE.md：
      1. ~/.claude/CLAUDE.md
      2. <workdir>/CLAUDE.md
      3. <cwd>/CLAUDE.md（若与 workdir 不同）
    """
    sources: list[tuple[str, str]] = []

    user_claude = Path.home() / ".claude" / "CLAUDE.md"
    if user_claude.exists():
        sources.append(("user global", user_claude.read_text(encoding="utf-8", errors="replace")))

    project_claude = workdir / "CLAUDE.md"
    if project_claude.exists():
        sources.append(("project root", project_claude.read_text(encoding="utf-8", errors="replace")))

    cwd = Path.cwd()
    if cwd != workdir:
        sub = cwd / "CLAUDE.md"
        if sub.exists():
            sources.append((f"subdir ({cwd.name})", sub.read_text(encoding="utf-8", errors="replace")))

    if not sources:
        return ""
    parts = ["# CLAUDE.md instructions"]
    for label, content in sources:
        parts.append(f"## From {label}")
        parts.append(content.strip())
    return "\n\n".join(parts)


def build_agents_md(workdir: Path) -> str:
    """加载项目根 AGENTS.md（与 Cursor / Claude Code 常见约定对齐）。"""
    agents = workdir / "AGENTS.md"
    if not agents.exists():
        return ""
    body = agents.read_text(encoding="utf-8", errors="replace").strip()
    if not body:
        return ""
    return "# AGENTS.md (project rules)\n\n" + body


def build_dynamic_context(workdir: Path) -> str:
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    sys_info = f"{platform.system()} {platform.release()}"
    return (
        f"# Dynamic context\n"
        f"- Date/time: {now}\n"
        f"- OS: {sys_info}\n"
        f"- Workspace: {workdir}"
    )
