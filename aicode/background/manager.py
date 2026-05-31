"""
background/manager.py — 后台任务管理器

BackgroundManager 负责：
  - run(command)         : 在后台线程中执行命令，立即返回 task_id
  - check(task_id)       : 查询单任务状态，或列出全部
  - cancel(task_id)      : 标记取消（尽力，无法中断已运行的子进程）
  - drain_notifications(): 取出完成通知列表（由 BackgroundMiddleware 在 pre_turn 消费）
  - detect_stalled()     : 返回超时未完成的 task_id 列表

任务记录持久化到 <workdir>/.runtime-tasks/<task_id>.json。
任务输出持久化到 <workdir>/.runtime-tasks/<task_id>.log。

与参考实现相比的增强：
  - 支持 cancel（软取消 + process 终止尝试）
  - 持久化 start/finish 时间戳
  - 更丰富的状态字段
"""
from __future__ import annotations

import json
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .queue import NotificationQueue

STALL_THRESHOLD_S: float = 45.0


class BackgroundManager:
    """线程化后台任务管理器。"""

    def __init__(self, workdir: Path) -> None:
        self.workdir = workdir
        self.runtime_dir = workdir / ".runtime-tasks"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)

        self._tasks: dict[str, dict[str, Any]] = {}
        self._processes: dict[str, subprocess.Popen] = {}
        self._notification_queue = NotificationQueue()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def run(self, command: str, label: str | None = None) -> str:
        """
        在后台线程中执行命令。立即返回描述字符串（含 task_id）。
        """
        task_id = str(uuid.uuid4())[:8]
        output_file = self.runtime_dir / f"{task_id}.log"
        label = label or command[:60]

        with self._lock:
            self._tasks[task_id] = {
                "id": task_id,
                "label": label,
                "command": command,
                "status": "running",
                "result": None,
                "result_preview": "",
                "started_at": time.time(),
                "finished_at": None,
                "output_file": str(output_file.relative_to(self.workdir)),
            }

        self._persist_task(task_id)
        thread = threading.Thread(
            target=self._execute,
            args=(task_id, command, output_file),
            daemon=True,
        )
        thread.start()

        rel = output_file.relative_to(self.workdir)
        return (
            f"Background task {task_id!r} started: {command[:80]} "
            f"(output → {rel})"
        )

    def check(self, task_id: str | None = None) -> str:
        """查询单任务状态，或不传 task_id 列出全部。"""
        with self._lock:
            if task_id:
                t = self._tasks.get(task_id)
                if not t:
                    return f"Error: unknown task {task_id!r}"
                return json.dumps(
                    {k: t[k] for k in ("id", "label", "status", "command", "result_preview", "output_file")},
                    indent=2,
                    ensure_ascii=False,
                )
            if not self._tasks:
                return "No background tasks."
            lines = [
                f"{t['id']}: [{t['status']}] {t['label'][:60]} "
                f"→ {t.get('result_preview') or '(running)'}"
                for t in self._tasks.values()
            ]
            return "\n".join(lines)

    def cancel(self, task_id: str) -> str:
        """
        软取消任务。若仍在运行则尝试 terminate 子进程。
        """
        with self._lock:
            t = self._tasks.get(task_id)
            if not t:
                return f"Error: unknown task {task_id!r}"
            if t["status"] != "running":
                return f"Task {task_id} is already {t['status']}."
            t["status"] = "cancelled"
            t["finished_at"] = time.time()
            proc = self._processes.get(task_id)

        if proc:
            try:
                proc.terminate()
            except OSError:
                pass

        self._persist_task(task_id)
        return f"Task {task_id} cancelled."

    def drain_notifications(self) -> list[dict]:
        """
        取出所有后台任务完成通知（由 BackgroundMiddleware 在 pre_turn 消费）。
        """
        raw = self._notification_queue.drain()
        result = []
        for msg in raw:
            try:
                result.append(json.loads(msg))
            except json.JSONDecodeError:
                result.append({"message": msg})
        return result

    def detect_stalled(self) -> list[str]:
        """返回超过 STALL_THRESHOLD_S 仍在运行的 task_id 列表。"""
        now = time.time()
        with self._lock:
            return [
                tid for tid, t in self._tasks.items()
                if t["status"] == "running"
                and (now - t.get("started_at", now)) > STALL_THRESHOLD_S
            ]

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _execute(self, task_id: str, command: str, output_file: Path) -> None:
        """后台线程目标：运行子进程，持久化输出，推送通知。"""
        proc = None
        try:
            proc = subprocess.Popen(
                command,
                shell=True,
                cwd=self.workdir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            with self._lock:
                self._processes[task_id] = proc

            stdout, _ = proc.communicate(timeout=300)
            output = (stdout or "").strip()[:50_000] or "(no output)"
            status = "completed" if proc.returncode == 0 else "error"
        except subprocess.TimeoutExpired:
            output = "Error: Timeout (300s)"
            status = "timeout"
            if proc:
                proc.kill()
        except Exception as exc:
            output = f"Error: {exc}"
            status = "error"
        finally:
            with self._lock:
                self._processes.pop(task_id, None)

        preview = " ".join(output.split())[:500]
        output_file.write_text(output, encoding="utf-8")

        with self._lock:
            t = self._tasks.get(task_id, {})
            # 若任务已被取消，不覆盖 cancelled 状态
            if t.get("status") != "cancelled":
                t["status"] = status
            t["result"] = output
            t["result_preview"] = preview
            t["finished_at"] = time.time()

        self._persist_task(task_id)

        # 推送通知
        notif = {
            "task_id": task_id,
            "status": status,
            "command": command[:80],
            "preview": preview,
            "output_file": str(output_file.relative_to(self.workdir)),
        }
        self._notification_queue.push(
            json.dumps(notif, ensure_ascii=False),
            priority="high",
            key=f"bg:{task_id}",
        )

    def _persist_task(self, task_id: str) -> None:
        with self._lock:
            t = self._tasks.get(task_id)
            if not t:
                return
            snapshot = dict(t)

        record_path = self.runtime_dir / f"{task_id}.json"
        try:
            record_path.write_text(
                json.dumps(snapshot, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass
