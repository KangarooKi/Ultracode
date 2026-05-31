"""
context/transcript.py — 会话转写工具函数（薄层封装）

供外部模块直接调用，不依赖 CompactState。
"""
from __future__ import annotations

import json
import time
from pathlib import Path


def save_transcript(messages: list, transcript_dir: Path) -> Path:
    """将 messages 写为带时间戳的 JSONL 文件，返回路径。"""
    transcript_dir.mkdir(parents=True, exist_ok=True)
    path = transcript_dir / f"transcript_{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for msg in messages:
            f.write(json.dumps(msg, default=str) + "\n")
    return path


def load_transcript(path: Path) -> list:
    """从 JSONL 文件恢复 messages 列表。"""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return [json.loads(line) for line in lines if line.strip()]
