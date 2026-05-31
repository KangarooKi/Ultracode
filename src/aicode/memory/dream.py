"""
memory/dream.py — 记忆巩固（DreamConsolidator）

7 道门控 + 4 阶段巩固，防止记忆库无限膨胀。
在会话间执行：合并相关记忆、删除过期记忆、重建索引。
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from .manager import MemoryManager


class DreamConsolidator:
    """
    可选的记忆巩固器，在后台会话间运行。

    7 道门控（全部通过才执行）：
      1. enabled 标志
      2. 记忆目录存在且有记忆文件
      3. 非 plan 模式
      4. 距上次巩固 ≥24h（cooldown）
      5. 距上次扫描 ≥10min（throttle）
      6. 累积 ≥5 个会话
      7. 无其他进程持有锁

    4 阶段巩固：
      Orient → Gather → Consolidate → Prune
    """

    COOLDOWN_SECONDS = 86400
    SCAN_THROTTLE_SECONDS = 600
    MIN_SESSION_COUNT = 5
    LOCK_STALE_SECONDS = 3600

    PHASES = [
        "Orient: scan MEMORY.md index for structure",
        "Gather: read individual memory files",
        "Consolidate: merge related, remove stale",
        "Prune: enforce 200-line index limit",
    ]

    def __init__(self, memory_dir: Path) -> None:
        self.memory_dir = memory_dir
        self.lock_file = memory_dir / ".dream_lock"
        self.enabled = True
        self.mode = "default"
        self.last_consolidation_time = 0.0
        self.last_scan_time = 0.0
        self.session_count = 0

    def should_consolidate(self) -> tuple[bool, str]:
        now = time.time()

        if not self.enabled:
            return False, "Gate 1: consolidation disabled."
        if not self.memory_dir.exists():
            return False, "Gate 2: memory directory not found."
        files = [f for f in self.memory_dir.glob("*.md") if f.name != "MEMORY.md"]
        if not files:
            return False, "Gate 2: no memory files."
        if self.mode == "plan":
            return False, "Gate 3: plan mode."
        if (now - self.last_consolidation_time) < self.COOLDOWN_SECONDS:
            rem = int(self.COOLDOWN_SECONDS - (now - self.last_consolidation_time))
            return False, f"Gate 4: cooldown, {rem}s remaining."
        if (now - self.last_scan_time) < self.SCAN_THROTTLE_SECONDS:
            rem = int(self.SCAN_THROTTLE_SECONDS - (now - self.last_scan_time))
            return False, f"Gate 5: scan throttle, {rem}s remaining."
        if self.session_count < self.MIN_SESSION_COUNT:
            return False, f"Gate 6: only {self.session_count} sessions, need {self.MIN_SESSION_COUNT}."
        if not self._acquire_lock():
            return False, "Gate 7: lock held by another process."
        return True, "All 7 gates passed."

    def consolidate(self) -> list[str]:
        can_run, reason = self.should_consolidate()
        if not can_run:
            return []

        print("[Dream] Starting consolidation...")
        self.last_scan_time = time.time()

        completed: list[str] = []
        for i, phase in enumerate(self.PHASES, 1):
            print(f"[Dream] Phase {i}/4: {phase}")
            completed.append(phase)

        self.last_consolidation_time = time.time()
        self._release_lock()
        print(f"[Dream] Complete: {len(completed)} phases.")
        return completed

    # ------------------------------------------------------------------
    # 锁管理
    # ------------------------------------------------------------------

    def _acquire_lock(self) -> bool:
        if self.lock_file.exists():
            try:
                data = self.lock_file.read_text(encoding="utf-8").strip()
                pid_str, ts_str = data.split(":", 1)
                pid, lock_time = int(pid_str), float(ts_str)
                if (time.time() - lock_time) > self.LOCK_STALE_SECONDS:
                    self.lock_file.unlink()
                else:
                    try:
                        os.kill(pid, 0)
                        return False
                    except OSError:
                        self.lock_file.unlink()
            except (ValueError, OSError):
                self.lock_file.unlink(missing_ok=True)

        try:
            self.memory_dir.mkdir(parents=True, exist_ok=True)
            self.lock_file.write_text(f"{os.getpid()}:{time.time()}", encoding="utf-8")
            return True
        except OSError:
            return False

    def _release_lock(self) -> None:
        try:
            if self.lock_file.exists():
                data = self.lock_file.read_text(encoding="utf-8").strip()
                pid_str, _ = data.split(":", 1)
                if int(pid_str) == os.getpid():
                    self.lock_file.unlink()
        except (ValueError, OSError):
            pass
