"""
context/compact.py — 上下文压缩（CompactState + 三种压缩策略）

三种策略：
  1. micro_compact      — 保留最近 N 条工具结果，旧的替换为占位符
  2. persist_large_output — 超大输出（>30KB）写磁盘，返回预览
  3. compact_history    — LLM 摘要整个对话，替换 messages

作为 LoopMiddleware 实现（CompactMiddleware）：
  - pre_turn：检测上下文大小，必要时触发压缩
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from openai import OpenAI

from aicode.core.loop import NoopMiddleware
from aicode.core.types import LoopState

KEEP_RECENT_TOOL_RESULTS = 3
PERSIST_THRESHOLD = 30_000       # 字节：超过此大小的输出持久化
PREVIEW_CHARS = 2_000
CONTEXT_LIMIT = 500_000          # 字符估算阈值
AUTO_COMPACT_THRESHOLD = 400_000 # 字符估算阈值，超过自动压缩


@dataclass
class CompactState:
    has_compacted: bool = False
    last_summary: str = ""
    recent_files: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 工具输出大小管理
# ---------------------------------------------------------------------------

def persist_large_output(
    tool_call_id: str,
    output: str,
    outputs_dir: Path,
) -> str:
    """大输出写磁盘，返回预览字符串。小输出原样返回。"""
    if len(output) <= PERSIST_THRESHOLD:
        return output

    outputs_dir.mkdir(parents=True, exist_ok=True)
    safe_id = re.sub(r"[^a-zA-Z0-9._-]", "_", tool_call_id)[:120]
    stored = outputs_dir / f"{safe_id}.txt"
    if not stored.exists():
        stored.write_text(output, encoding="utf-8")

    preview = output[:PREVIEW_CHARS] + "..."
    rel = stored
    return (
        "<persisted-output>\n"
        f"Full output saved to: {rel}\n"
        "Preview:\n"
        f"{preview}\n"
        "</persisted-output>"
    )


# ---------------------------------------------------------------------------
# 微压缩
# ---------------------------------------------------------------------------

def micro_compact(messages: list) -> list:
    """
    替换除最近 KEEP_RECENT_TOOL_RESULTS 条之外的所有 tool 消息内容为占位符。
    只压缩内容超过 120 字符的工具结果（短结果保留原样）。
    """
    tool_indices = [
        i for i, m in enumerate(messages)
        if isinstance(m, dict) and m.get("role") == "tool"
        and isinstance(m.get("content"), str)
    ]
    if len(tool_indices) <= KEEP_RECENT_TOOL_RESULTS:
        return list(messages)

    keep = set(tool_indices[-KEEP_RECENT_TOOL_RESULTS:])
    out: list = []
    for i, m in enumerate(messages):
        if (
            i in tool_indices
            and i not in keep
            and len(m.get("content", "")) > 120
        ):
            out.append({
                **m,
                "content": "[Earlier tool result compacted. Re-run if needed.]",
            })
        else:
            out.append(m)
    return out


# ---------------------------------------------------------------------------
# 历史摘要压缩
# ---------------------------------------------------------------------------

def write_transcript(messages: list, transcript_dir: Path) -> Path:
    """将对话写为 JSONL 快照，返回路径。"""
    transcript_dir.mkdir(parents=True, exist_ok=True)
    path = transcript_dir / f"transcript_{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for msg in messages:
            f.write(json.dumps(msg, default=str) + "\n")
    return path


def summarize_messages(messages: list, client: OpenAI, model: str) -> str:
    """调用 LLM 摘要整个对话。"""
    conversation = json.dumps(messages, default=str)[:80_000]
    prompt = (
        "Summarize this coding-agent conversation so work can continue.\n"
        "Preserve:\n"
        "1. The current goal\n"
        "2. Important findings and decisions\n"
        "3. Files read or changed\n"
        "4. Remaining work\n"
        "5. User constraints and preferences\n"
        "Be compact but concrete.\n\n"
        f"{conversation}"
    )
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=4000,
    )
    return (resp.choices[0].message.content or "").strip()


def compact_history(
    messages: list,
    state: CompactState,
    client: OpenAI,
    model: str,
    transcript_dir: Path,
    focus: str | None = None,
) -> list:
    """摘要整个对话，返回只含摘要的新 messages 列表。"""
    tp = write_transcript(messages, transcript_dir)
    print(f"[Compact] Transcript saved to {tp.name}")

    summary = summarize_messages(messages, client, model)
    if focus:
        summary += f"\n\nFocus next: {focus}"
    if state.recent_files:
        files = "\n".join(f"- {p}" for p in state.recent_files)
        summary += f"\n\nRecent files:\n{files}"

    state.has_compacted = True
    state.last_summary = summary

    return [{
        "role": "user",
        "content": (
            "This conversation was compacted.\n\n"
            f"{summary}\n\n"
        ),
    }]


def track_recent_file(state: CompactState, path: str) -> None:
    if path in state.recent_files:
        state.recent_files.remove(path)
    state.recent_files.append(path)
    if len(state.recent_files) > 5:
        state.recent_files.pop(0)


# ---------------------------------------------------------------------------
# Middleware 包装
# ---------------------------------------------------------------------------

class CompactMiddleware(NoopMiddleware):
    """
    自动上下文压缩中间件。

    pre_turn：估算上下文大小，超过阈值时先微压缩，仍超则调用 compact_history。
    post_tool：追踪 read/write/edit 操作的文件路径。
    """

    def __init__(
        self,
        state: CompactState,
        client: OpenAI,
        model: str,
        workdir: Path,
    ) -> None:
        self.state = state
        self.client = client
        self.model = model
        self.transcript_dir = workdir / ".transcripts"
        self.outputs_dir = workdir / ".task_outputs" / "tool-results"
        self._auto_threshold = int(
            os.getenv("AICODE_COMPACT_AUTO_THRESHOLD", str(AUTO_COMPACT_THRESHOLD))
        )

    def pre_turn(self, loop_state: LoopState) -> None:
        size = len(str(loop_state.messages))
        if size < self._auto_threshold:
            return

        # 先尝试微压缩
        loop_state.messages = micro_compact(loop_state.messages)
        if len(str(loop_state.messages)) < self._auto_threshold:
            return

        # 仍然太大 → 完整压缩
        print(f"[Compact] Context {size:,} chars — running compact_history…")
        loop_state.messages = compact_history(
            loop_state.messages,
            self.state,
            self.client,
            self.model,
            self.transcript_dir,
        )

    def post_tool(self, call, result, loop_state: LoopState) -> None:
        # 追踪文件操作路径
        if call.name in ("read_file", "write_file", "edit_file"):
            path = call.arguments.get("path", "")
            if path:
                track_recent_file(self.state, path)

        # 大输出持久化
        if len(result.content) > PERSIST_THRESHOLD:
            result.content = persist_large_output(
                call.id, result.content, self.outputs_dir
            )
