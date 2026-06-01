"""
验证上下文压缩与 transcript 持久化：
1. micro_compact — 保留最近 N 条，旧的替换
2. persist_large_output — 小输出原样，大输出写磁盘
3. write_transcript + load_transcript
4. CompactMiddleware.pre_turn — 大上下文自动压缩
5. CompactMiddleware.post_tool — 追踪文件路径
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from aicode.context.compact import (
    KEEP_RECENT_TOOL_RESULTS,
    PERSIST_THRESHOLD,
    CompactMiddleware,
    CompactState,
    micro_compact,
    persist_large_output,
)
from aicode.context.transcript import load_transcript, save_transcript
from aicode.core.types import LoopState, ToolCall, ToolResult


# ---------------------------------------------------------------------------
# micro_compact
# ---------------------------------------------------------------------------

class TestMicroCompact:
    def _make_tool_msg(self, content: str) -> dict:
        return {"role": "tool", "tool_call_id": "x", "content": content}

    def test_few_results_unchanged(self):
        msgs = [self._make_tool_msg("short") for _ in range(KEEP_RECENT_TOOL_RESULTS)]
        result = micro_compact(msgs)
        assert all(m["content"] == "short" for m in result)

    def test_old_long_results_replaced(self):
        msgs = [self._make_tool_msg("x" * 200) for _ in range(KEEP_RECENT_TOOL_RESULTS + 2)]
        result = micro_compact(msgs)
        compacted = [m for m in result if "compacted" in m.get("content", "").lower()]
        assert len(compacted) == 2

    def test_recent_results_kept_intact(self):
        content_recent = "recent output content"
        msgs = (
            [self._make_tool_msg("x" * 200) for _ in range(3)]
            + [self._make_tool_msg(content_recent) for _ in range(KEEP_RECENT_TOOL_RESULTS)]
        )
        result = micro_compact(msgs)
        recent = result[-KEEP_RECENT_TOOL_RESULTS:]
        assert all(m["content"] == content_recent for m in recent)

    def test_short_old_results_not_replaced(self):
        """内容 ≤120 字符的旧工具结果保留原样（避免破坏短结果）。"""
        msgs = [self._make_tool_msg("short") for _ in range(KEEP_RECENT_TOOL_RESULTS + 2)]
        result = micro_compact(msgs)
        assert all("compacted" not in m.get("content", "") for m in result)

    def test_non_tool_messages_unchanged(self):
        msgs = [
            {"role": "user", "content": "hello"},
            self._make_tool_msg("x" * 200),
            self._make_tool_msg("x" * 200),
            self._make_tool_msg("x" * 200),
            self._make_tool_msg("x" * 200),
        ]
        result = micro_compact(msgs)
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "hello"


# ---------------------------------------------------------------------------
# persist_large_output
# ---------------------------------------------------------------------------

class TestPersistLargeOutput:
    def test_small_output_unchanged(self, tmp_path):
        out = persist_large_output("id1", "small", tmp_path)
        assert out == "small"

    def test_large_output_written_to_disk(self, tmp_path):
        big = "x" * (PERSIST_THRESHOLD + 100)
        out = persist_large_output("id2", big, tmp_path)
        assert "<persisted-output>" in out
        assert (tmp_path / "id2.txt").exists()

    def test_large_output_contains_preview(self, tmp_path):
        big = "A" * (PERSIST_THRESHOLD + 100)
        out = persist_large_output("id3", big, tmp_path)
        assert "AAAA" in out

    def test_idempotent_no_duplicate_file(self, tmp_path):
        big = "y" * (PERSIST_THRESHOLD + 1)
        persist_large_output("id4", big, tmp_path)
        persist_large_output("id4", big, tmp_path)
        assert len(list(tmp_path.glob("id4.txt"))) == 1


# ---------------------------------------------------------------------------
# transcript
# ---------------------------------------------------------------------------

class TestTranscript:
    def test_roundtrip(self, tmp_path):
        msgs = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
        path = save_transcript(msgs, tmp_path)
        loaded = load_transcript(path)
        assert loaded == msgs

    def test_file_created(self, tmp_path):
        save_transcript([{"role": "user", "content": "x"}], tmp_path)
        assert any(tmp_path.glob("transcript_*.jsonl"))


# ---------------------------------------------------------------------------
# CompactMiddleware
# ---------------------------------------------------------------------------

class TestCompactMiddleware:
    def _make_mw(self, tmp_path):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="summary text"))]
        )
        return CompactMiddleware(
            state=CompactState(),
            client=mock_client,
            model="test-model",
            workdir=tmp_path,
        )

    def test_small_context_no_compact(self, tmp_path):
        mw = self._make_mw(tmp_path)
        state = LoopState(messages=[{"role": "user", "content": "hi"}])
        mw.pre_turn(state)
        # messages 不变
        assert len(state.messages) == 1

    def test_tracks_file_path(self, tmp_path):
        mw = self._make_mw(tmp_path)
        call = ToolCall(id="t", name="read_file", arguments={"path": "main.py"})
        result = ToolResult(tool_call_id="t", content="code")
        state = LoopState(messages=[])
        mw.post_tool(call, result, state)
        assert "main.py" in mw.state.recent_files

    def test_large_output_persisted(self, tmp_path):
        mw = self._make_mw(tmp_path)
        big_content = "z" * (PERSIST_THRESHOLD + 1)
        call = ToolCall(id="big", name="bash", arguments={"command": "ls"})
        result = ToolResult(tool_call_id="big", content=big_content)
        state = LoopState(messages=[])
        mw.post_tool(call, result, state)
        assert "<persisted-output>" in result.content
