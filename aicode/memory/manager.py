"""
memory/manager.py — 跨会话记忆系统（MemoryManager）

存储布局：
  .memory/
    MEMORY.md          ← 索引（≤200行）
    prefer_tabs.md     ← 单条记忆文件（frontmatter + body）
    review_style.md
    ...

每条记忆是一个带 YAML frontmatter 的 Markdown 文件。
MemoryManager 负责加载、保存、索引重建。
"""
from __future__ import annotations

import re
from pathlib import Path

from .schema import MAX_INDEX_LINES, MEMORY_TYPES


class MemoryManager:
    """持久化记忆 CRUD。"""

    def __init__(self, memory_dir: Path) -> None:
        self.memory_dir = memory_dir
        # name -> {description, type, content, file}
        self.memories: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # 加载
    # ------------------------------------------------------------------

    def load_all(self) -> None:
        """扫描 .memory/ 目录，加载所有记忆文件。"""
        self.memories = {}
        if not self.memory_dir.exists():
            return

        for md_file in sorted(self.memory_dir.glob("*.md")):
            if md_file.name == "MEMORY.md":
                continue
            parsed = self._parse_frontmatter(
                md_file.read_text(encoding="utf-8", errors="replace")
            )
            if parsed:
                name = parsed.get("name", md_file.stem)
                self.memories[name] = {
                    "description": parsed.get("description", ""),
                    "type": parsed.get("type", "project"),
                    "content": parsed.get("content", ""),
                    "file": md_file.name,
                }

        if self.memories:
            print(f"[Memory: {len(self.memories)} memories loaded]")

    # ------------------------------------------------------------------
    # 生成系统提示片段
    # ------------------------------------------------------------------

    def load_memory_prompt(self) -> str:
        """构建注入系统提示的记忆文本块。"""
        if not self.memories:
            return ""

        sections = ["# Memories (persistent across sessions)", ""]
        for mem_type in MEMORY_TYPES:
            typed = {k: v for k, v in self.memories.items() if v["type"] == mem_type}
            if not typed:
                continue
            sections.append(f"## [{mem_type}]")
            for name, mem in typed.items():
                sections.append(f"### {name}: {mem['description']}")
                if mem["content"].strip():
                    sections.append(mem["content"].strip())
                sections.append("")
        return "\n".join(sections)

    # ------------------------------------------------------------------
    # 保存
    # ------------------------------------------------------------------

    def save_memory(
        self,
        name: str,
        description: str,
        mem_type: str,
        content: str,
    ) -> str:
        """保存一条记忆到磁盘，返回状态消息。"""
        if mem_type not in MEMORY_TYPES:
            return f"Error: type must be one of {MEMORY_TYPES}"

        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", name.lower())
        if not safe_name:
            return "Error: invalid memory name."

        self.memory_dir.mkdir(parents=True, exist_ok=True)
        file_name = f"{safe_name}.md"
        file_path = self.memory_dir / file_name

        text = (
            f"---\n"
            f"name: {name}\n"
            f"description: {description}\n"
            f"type: {mem_type}\n"
            f"---\n"
            f"{content}\n"
        )
        file_path.write_text(text, encoding="utf-8")

        self.memories[name] = {
            "description": description,
            "type": mem_type,
            "content": content,
            "file": file_name,
        }
        self._rebuild_index()
        rel = file_path.relative_to(self.memory_dir.parent)
        return f"Saved memory '{name}' [{mem_type}] to {rel}"

    def delete_memory(self, name: str) -> str:
        """删除一条记忆（文件 + 索引）。"""
        if name not in self.memories:
            return f"Error: memory '{name}' not found."
        file_path = self.memory_dir / self.memories[name]["file"]
        file_path.unlink(missing_ok=True)
        del self.memories[name]
        self._rebuild_index()
        return f"Deleted memory '{name}'."

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _rebuild_index(self) -> None:
        lines = ["# Memory Index", ""]
        for name, mem in self.memories.items():
            lines.append(f"- [{mem['type']}] {name}: {mem['description']}")
            if len(lines) >= MAX_INDEX_LINES:
                lines.append(f"... (truncated at {MAX_INDEX_LINES} lines)")
                break
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        (self.memory_dir / "MEMORY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _parse_frontmatter(self, text: str) -> dict | None:
        """解析 --- frontmatter + body。"""
        m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", text, re.DOTALL)
        if not m:
            return None
        result: dict = {"content": m.group(2).strip()}
        for line in m.group(1).splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                result[k.strip()] = v.strip()
        return result
