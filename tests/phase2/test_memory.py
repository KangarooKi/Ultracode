"""
验证记忆管理与 DreamConsolidator 门控：
1. save_memory — 文件写入 + frontmatter 格式
2. load_all    — 扫描目录
3. load_memory_prompt — 分类输出
4. delete_memory
5. _rebuild_index
6. DreamConsolidator 的时间与锁文件条件
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from aicode.memory.dream import DreamConsolidator
from aicode.memory.manager import MemoryManager


@pytest.fixture
def mem(tmp_path):
    return MemoryManager(tmp_path / ".memory")


# ---------------------------------------------------------------------------
# save_memory
# ---------------------------------------------------------------------------

class TestSaveMemory:
    def test_creates_file(self, mem, tmp_path):
        mem.save_memory("prefer_tabs", "Use tabs", "feedback", "Always indent with tabs.")
        assert (tmp_path / ".memory" / "prefer_tabs.md").exists()

    def test_frontmatter_present(self, mem, tmp_path):
        mem.save_memory("style", "Code style", "feedback", "Body content here.")
        text = (tmp_path / ".memory" / "style.md").read_text()
        assert "name: style" in text
        assert "type: feedback" in text
        assert "Body content here." in text

    def test_invalid_type_returns_error(self, mem):
        r = mem.save_memory("x", "d", "invalid_type", "c")
        assert r.startswith("Error:")

    def test_memory_in_index_after_save(self, mem, tmp_path):
        mem.save_memory("key", "desc", "project", "content")
        index = (tmp_path / ".memory" / "MEMORY.md").read_text()
        assert "key" in index

    def test_special_chars_sanitized_in_filename(self, mem, tmp_path):
        mem.save_memory("my memory!", "d", "user", "c")
        files = list((tmp_path / ".memory").glob("my_memory*.md"))
        assert len(files) == 1


# ---------------------------------------------------------------------------
# load_all
# ---------------------------------------------------------------------------

class TestLoadAll:
    def test_loads_saved_memories(self, mem):
        mem.save_memory("a", "desc a", "user", "content a")
        mem.save_memory("b", "desc b", "project", "content b")
        mem2 = MemoryManager(mem.memory_dir)
        mem2.load_all()
        assert "a" in mem2.memories
        assert "b" in mem2.memories

    def test_skips_memory_md(self, mem, tmp_path):
        mem.save_memory("m", "d", "user", "c")
        mem2 = MemoryManager(mem.memory_dir)
        mem2.load_all()
        assert "MEMORY" not in mem2.memories

    def test_empty_dir_returns_no_memories(self, tmp_path):
        m = MemoryManager(tmp_path / ".empty")
        m.load_all()
        assert m.memories == {}


# ---------------------------------------------------------------------------
# load_memory_prompt
# ---------------------------------------------------------------------------

class TestLoadMemoryPrompt:
    def test_prompt_contains_type_headers(self, mem):
        mem.save_memory("pref", "d", "feedback", "use tabs")
        mem.load_all()
        prompt = mem.load_memory_prompt()
        assert "[feedback]" in prompt
        assert "use tabs" in prompt

    def test_empty_memories_returns_empty_string(self, mem):
        assert mem.load_memory_prompt() == ""


# ---------------------------------------------------------------------------
# delete_memory
# ---------------------------------------------------------------------------

class TestDeleteMemory:
    def test_delete_removes_file_and_entry(self, mem, tmp_path):
        mem.save_memory("to_del", "d", "user", "c")
        mem.delete_memory("to_del")
        assert "to_del" not in mem.memories
        assert not (tmp_path / ".memory" / "to_del.md").exists()

    def test_delete_nonexistent_returns_error(self, mem):
        r = mem.delete_memory("ghost")
        assert r.startswith("Error:")


# ---------------------------------------------------------------------------
# DreamConsolidator 门控测试
# ---------------------------------------------------------------------------

class TestDreamConsolidator:
    def test_gate1_disabled(self, tmp_path):
        d = DreamConsolidator(tmp_path / ".memory")
        d.enabled = False
        ok, reason = d.should_consolidate()
        assert not ok
        assert "Gate 1" in reason

    def test_gate2_no_dir(self, tmp_path):
        d = DreamConsolidator(tmp_path / ".memory_nonexistent")
        ok, reason = d.should_consolidate()
        assert not ok
        assert "Gate 2" in reason

    def test_gate3_plan_mode(self, tmp_path):
        mem_dir = tmp_path / ".memory"
        mem_dir.mkdir()
        (mem_dir / "x.md").write_text("---\nname: x\ndescription: d\ntype: user\n---\nc\n")
        d = DreamConsolidator(mem_dir)
        d.mode = "plan"
        ok, reason = d.should_consolidate()
        assert not ok
        assert "Gate 3" in reason

    def test_gate4_cooldown(self, tmp_path):
        mem_dir = tmp_path / ".memory"
        mem_dir.mkdir()
        (mem_dir / "x.md").write_text("---\nname: x\ndescription: d\ntype: user\n---\nc\n")
        d = DreamConsolidator(mem_dir)
        d.last_consolidation_time = time.time()  # 刚刚巩固过
        ok, reason = d.should_consolidate()
        assert not ok
        assert "Gate 4" in reason

    def test_gate6_not_enough_sessions(self, tmp_path):
        mem_dir = tmp_path / ".memory"
        mem_dir.mkdir()
        (mem_dir / "x.md").write_text("---\nname: x\ndescription: d\ntype: user\n---\nc\n")
        d = DreamConsolidator(mem_dir)
        d.session_count = 2  # < MIN_SESSION_COUNT=5
        ok, reason = d.should_consolidate()
        assert not ok
        assert "Gate 6" in reason
