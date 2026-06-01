"""
验证系统提示构建流程：
1. build_core — 包含 workdir
2. build_tool_listing — 列出工具
3. build_skill_listing — 扫描 SKILL.md
4. build_memory_section — 读取 .memory/
5. build_claude_md — 读取 CLAUDE.md
6. SystemPromptBuilder.build — 完整管线
"""
from __future__ import annotations

from pathlib import Path

import pytest

from aicode.core.tools.registry import build_base_registry
from aicode.prompt.builder import DYNAMIC_BOUNDARY, SystemPromptBuilder
from aicode.prompt.sections import (
    build_agents_md,
    build_claude_md,
    build_core,
    build_memory_section,
    build_skill_listing,
    build_tool_listing,
)


# ---------------------------------------------------------------------------
# build_core
# ---------------------------------------------------------------------------

def test_build_core_contains_workdir(tmp_path):
    result = build_core(tmp_path)
    assert str(tmp_path) in result


# ---------------------------------------------------------------------------
# build_tool_listing
# ---------------------------------------------------------------------------

def test_build_tool_listing_lists_names():
    reg = build_base_registry()
    result = build_tool_listing(reg.get_schemas())
    assert "bash" in result
    assert "read_file" in result

def test_build_tool_listing_empty():
    assert build_tool_listing([]) == ""


# ---------------------------------------------------------------------------
# build_skill_listing
# ---------------------------------------------------------------------------

def test_build_skill_listing_finds_skill(tmp_path):
    skill_dir = tmp_path / "skills" / "git-commit"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: git-commit\ndescription: Create git commits\n---\nBody.\n"
    )
    result = build_skill_listing(tmp_path / "skills")
    assert "git-commit" in result
    assert "Create git commits" in result

def test_build_skill_listing_no_dir(tmp_path):
    assert build_skill_listing(tmp_path / "no_skills") == ""


# ---------------------------------------------------------------------------
# build_memory_section
# ---------------------------------------------------------------------------

def test_build_memory_section_reads_memories(tmp_path):
    mem_dir = tmp_path / ".memory"
    mem_dir.mkdir()
    (mem_dir / "style.md").write_text(
        "---\nname: style\ndescription: code style\ntype: feedback\n---\nUse tabs.\n"
    )
    result = build_memory_section(mem_dir)
    assert "Use tabs" in result
    assert "feedback" in result

def test_build_memory_section_empty(tmp_path):
    mem_dir = tmp_path / ".memory"
    mem_dir.mkdir()
    assert build_memory_section(mem_dir) == ""

def test_build_memory_section_no_dir(tmp_path):
    assert build_memory_section(tmp_path / ".no_memory") == ""


# ---------------------------------------------------------------------------
# build_claude_md
# ---------------------------------------------------------------------------

def test_build_claude_md_reads_project_claude_md(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("Always write tests.\n")
    result = build_claude_md(tmp_path)
    assert "Always write tests" in result

def test_build_claude_md_no_file(tmp_path):
    # 无 CLAUDE.md 且 home 下也没有（不能保证，用空目录）
    result = build_claude_md(tmp_path)
    # 可能来自 ~/.claude/CLAUDE.md，只要不崩溃就行
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# build_agents_md
# ---------------------------------------------------------------------------

def test_build_agents_md_reads_file(tmp_path):
    (tmp_path / "AGENTS.md").write_text("Use ruff.\n", encoding="utf-8")
    result = build_agents_md(tmp_path)
    assert "AGENTS.md" in result
    assert "Use ruff" in result


def test_build_agents_md_missing(tmp_path):
    assert build_agents_md(tmp_path) == ""


# ---------------------------------------------------------------------------
# SystemPromptBuilder.build
# ---------------------------------------------------------------------------

class TestSystemPromptBuilder:
    def test_build_contains_core(self, tmp_path):
        builder = SystemPromptBuilder(workdir=tmp_path)
        prompt = builder.build()
        assert str(tmp_path) in prompt

    def test_build_contains_dynamic_boundary(self, tmp_path):
        builder = SystemPromptBuilder(workdir=tmp_path)
        prompt = builder.build()
        assert DYNAMIC_BOUNDARY in prompt

    def test_build_contains_tool_listing(self, tmp_path):
        reg = build_base_registry()
        builder = SystemPromptBuilder(workdir=tmp_path, registry=reg)
        prompt = builder.build()
        assert "bash" in prompt

    def test_build_contains_memory(self, tmp_path):
        mem_dir = tmp_path / ".memory"
        mem_dir.mkdir()
        (mem_dir / "pref.md").write_text(
            "---\nname: pref\ndescription: d\ntype: user\n---\nprefer dark mode\n"
        )
        builder = SystemPromptBuilder(workdir=tmp_path, memory_dir=mem_dir)
        prompt = builder.build()
        assert "prefer dark mode" in prompt

    def test_build_no_crash_on_empty_dirs(self, tmp_path):
        builder = SystemPromptBuilder(workdir=tmp_path)
        prompt = builder.build()
        assert len(prompt) > 0

    def test_build_contains_agents_md(self, tmp_path):
        (tmp_path / "AGENTS.md").write_text("Run pytest before commit.\n", encoding="utf-8")
        builder = SystemPromptBuilder(workdir=tmp_path)
        prompt = builder.build()
        assert "pytest" in prompt
        assert "AGENTS.md" in prompt
