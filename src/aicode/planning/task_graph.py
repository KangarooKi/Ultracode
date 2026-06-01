"""
planning/task_graph.py — 持久化任务图（TaskManager）

任务以 JSON 文件形式存储在 .tasks/ 目录，跨会话存活。
每个任务携带 blockedBy / blocks 依赖关系。
本模块也负责把任务 CRUD 能力注册为 Agent 可调用工具。
"""
from __future__ import annotations

import json
from pathlib import Path


class TaskManager:
    """
    持久化任务 CRUD。

    任务文件格式：
    {
        "id": 1,
        "subject": "...",
        "description": "...",
        "status": "pending",   # pending | in_progress | completed | deleted
        "blockedBy": [],
        "blocks": [],
        "owner": ""
    }
    """

    def __init__(self, tasks_dir: Path) -> None:
        self.dir = tasks_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self._next_id = self._max_id() + 1

    # ------------------------------------------------------------------
    # 内部 I/O
    # ------------------------------------------------------------------

    def _max_id(self) -> int:
        ids = [int(f.stem.split("_")[1]) for f in self.dir.glob("task_*.json")]
        return max(ids) if ids else 0

    def _path(self, task_id: int) -> Path:
        return self.dir / f"task_{task_id}.json"

    def _load(self, task_id: int) -> dict:
        p = self._path(task_id)
        if not p.exists():
            raise ValueError(f"Task {task_id} not found.")
        return json.loads(p.read_text(encoding="utf-8"))

    def _save(self, task: dict) -> None:
        self._path(task["id"]).write_text(json.dumps(task, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------
    # 公共 API：这些方法会被注册为 Agent 工具处理器
    # ------------------------------------------------------------------

    def create(self, subject: str, description: str = "") -> str:
        task = {
            "id": self._next_id,
            "subject": subject,
            "description": description,
            "status": "pending",
            "blockedBy": [],
            "blocks": [],
            "owner": "",
        }
        self._save(task)
        self._next_id += 1
        return json.dumps(task, indent=2)

    def get(self, task_id: int) -> str:
        return json.dumps(self._load(task_id), indent=2)

    def update(
        self,
        task_id: int,
        status: str | None = None,
        owner: str | None = None,
        add_blocked_by: list[int] | None = None,
        add_blocks: list[int] | None = None,
    ) -> str:
        task = self._load(task_id)

        if owner is not None:
            task["owner"] = owner

        if status is not None:
            valid = {"pending", "in_progress", "completed", "deleted"}
            if status not in valid:
                raise ValueError(f"Invalid status: {status!r}")
            task["status"] = status
            if status == "completed":
                self._clear_dependency(task_id)

        if add_blocked_by:
            task["blockedBy"] = list(set(task["blockedBy"] + add_blocked_by))

        if add_blocks:
            task["blocks"] = list(set(task["blocks"] + add_blocks))
            for blocked_id in add_blocks:
                try:
                    blocked = self._load(blocked_id)
                    if task_id not in blocked["blockedBy"]:
                        blocked["blockedBy"].append(task_id)
                        self._save(blocked)
                except ValueError:
                    pass

        self._save(task)
        return json.dumps(task, indent=2)

    def list_all(self) -> str:
        tasks = [
            json.loads(f.read_text(encoding="utf-8"))
            for f in sorted(self.dir.glob("task_*.json"))
        ]
        if not tasks:
            return "No tasks."
        markers = {
            "pending": "[ ]",
            "in_progress": "[>]",
            "completed": "[x]",
            "deleted": "[-]",
        }
        lines = []
        for t in tasks:
            marker = markers.get(t["status"], "[?]")
            blocked = f" (blocked by: {t['blockedBy']})" if t.get("blockedBy") else ""
            owner = f" owner={t['owner']}" if t.get("owner") else ""
            lines.append(f"{marker} #{t['id']}: {t['subject']}{owner}{blocked}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _clear_dependency(self, completed_id: int) -> None:
        """任务完成时从所有其他任务的 blockedBy 中移除 completed_id。"""
        for f in self.dir.glob("task_*.json"):
            task = json.loads(f.read_text(encoding="utf-8"))
            if completed_id in task.get("blockedBy", []):
                task["blockedBy"].remove(completed_id)
                self._save(task)


def register_task_tools(registry, task_manager: TaskManager) -> None:
    """将任务工具注册到 ToolRegistry。"""
    from aicode.core.tools.schemas import (
        task_create_schema,
        task_get_schema,
        task_list_schema,
        task_update_schema,
    )

    registry.register(
        "task_create",
        lambda **kw: task_manager.create(kw["subject"], kw.get("description", "")),
        task_create_schema(),
    )
    registry.register(
        "task_update",
        lambda **kw: task_manager.update(
            kw["task_id"],
            kw.get("status"),
            kw.get("owner"),
            kw.get("addBlockedBy"),
            kw.get("addBlocks"),
        ),
        task_update_schema(),
    )
    registry.register(
        "task_list",
        lambda **kw: task_manager.list_all(),
        task_list_schema(),
    )
    registry.register(
        "task_get",
        lambda **kw: task_manager.get(kw["task_id"]),
        task_get_schema(),
    )
