"""
subagent/template.py — AgentTemplate 加载

从 skills/<name>/SKILL.md 的 YAML frontmatter 解析模板。

frontmatter 字段（全部可选）：
  name        : 模板名称（默认为目录名）
  description : 一行描述（用于 LLM 工具 listing）
  tools       : 允许工具列表（默认 = 所有工具）
  system      : 覆盖 system prompt（默认 = 读取整个 SKILL.md body）
  max_turns   : 子 Agent 最大轮次（默认 10）

示例 SKILL.md：
  ---
  name: code-review
  description: Review code for correctness and style issues
  tools: [read_file, bash]
  max_turns: 5
  ---
  You are a code review specialist...
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AgentTemplate:
    name: str
    description: str = ""
    tools: list[str] = field(default_factory=list)   # 空列表 = 允许所有
    system: str = ""
    max_turns: int = 10
    source_path: Path | None = None


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)", re.DOTALL)


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """解析 YAML frontmatter（简易 key: value 解析，无 pyyaml 依赖）。"""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text

    raw_fm, body = m.group(1), m.group(2)
    meta: dict = {}
    for line in raw_fm.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        # 处理 YAML 列表 [a, b, c]
        if val.startswith("[") and val.endswith("]"):
            items = [x.strip().strip("'\"") for x in val[1:-1].split(",") if x.strip()]
            meta[key] = items
        elif val.isdigit():
            meta[key] = int(val)
        else:
            meta[key] = val.strip("'\"")

    return meta, body.strip()


def load_templates(skills_dir: Path) -> dict[str, AgentTemplate]:
    """
    扫描 skills_dir 中所有子目录的 SKILL.md，返回 name → AgentTemplate 映射。

    如果 SKILL.md 不含 frontmatter，则整个文件内容作为 system prompt。
    """
    templates: dict[str, AgentTemplate] = {}
    if not skills_dir.is_dir():
        return templates

    for skill_md in skills_dir.glob("*/SKILL.md"):
        text = skill_md.read_text(encoding="utf-8")
        meta, body = _parse_frontmatter(text)

        dir_name = skill_md.parent.name
        name = str(meta.get("name", dir_name))
        tmpl = AgentTemplate(
            name=name,
            description=str(meta.get("description", "")),
            tools=list(meta.get("tools", [])),
            system=str(meta.get("system", body)) if meta.get("system") else body,
            max_turns=int(meta.get("max_turns", 10)),
            source_path=skill_md,
        )
        templates[name] = tmpl

    return templates
