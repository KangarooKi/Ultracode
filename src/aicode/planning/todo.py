"""
planning/todo.py — 会话级任务规划（TodoManager）

管理当前对话中的短期执行计划，不跨会话持久化。
对应教学代码 s03_todo_write.py 的 TodoManager / PlanningState。

作为 LoopMiddleware 实现，在 post_turn 注入计划提醒。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from aicode.core.loop import NoopMiddleware
from aicode.core.types import LoopState, ToolCall, ToolResult

PLAN_REMINDER_INTERVAL = 3  # 超过多少轮没更新则提醒 LLM 刷新计划


@dataclass
class PlanItem:
    content: str
    status: str = "pending"        # pending | in_progress | completed
    active_form: str = ""          # 进行时描述


@dataclass
class PlanningState:
    items: list[PlanItem] = field(default_factory=list)
    rounds_since_update: int = 0


class TodoManager:
    """管理会话级执行计划。"""

    def __init__(self) -> None:
        self.state = PlanningState()

    # ------------------------------------------------------------------
    # 工具处理器（注册到 ToolRegistry 的 handler）
    # ------------------------------------------------------------------

    def update(self, items: list) -> str:
        """接收 LLM 传来的 items 列表，校验并更新计划。"""
        if len(items) > 12:
            raise ValueError("Session plan too long (max 12 items).")

        normalized: list[PlanItem] = []
        in_progress_count = 0

        for idx, raw in enumerate(items):
            content = str(raw.get("content", "")).strip()
            status = str(raw.get("status", "pending")).lower()
            active_form = str(raw.get("active_form", "")).strip()

            if not content:
                raise ValueError(f"Item {idx}: content is required.")
            if status not in {"pending", "in_progress", "completed"}:
                raise ValueError(f"Item {idx}: invalid status {status!r}.")
            if status == "in_progress":
                in_progress_count += 1

            normalized.append(PlanItem(content=content, status=status, active_form=active_form))

        if in_progress_count > 1:
            raise ValueError("Only one plan item can be in_progress at a time.")

        self.state.items = normalized
        self.state.rounds_since_update = 0
        return self.render()

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def note_round_without_update(self) -> None:
        self.state.rounds_since_update += 1

    def reminder(self) -> str | None:
        if not self.state.items:
            return None
        if self.state.rounds_since_update < PLAN_REMINDER_INTERVAL:
            return None
        return "<reminder>Refresh your current plan before continuing.</reminder>"

    def render(self) -> str:
        if not self.state.items:
            return "No session plan yet."
        lines = []
        for item in self.state.items:
            marker = {"pending": "[ ]", "in_progress": "[>]", "completed": "[x]"}[item.status]
            line = f"{marker} {item.content}"
            if item.status == "in_progress" and item.active_form:
                line += f" ({item.active_form})"
            lines.append(line)
        completed = sum(1 for i in self.state.items if i.status == "completed")
        lines.append(f"\n({completed}/{len(self.state.items)})")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Middleware 包装（注入计划提醒）
# ---------------------------------------------------------------------------

class TodoMiddleware(NoopMiddleware):
    """
    将 TodoManager 接入循环。
    - post_turn: 若计划长时间未更新，向 messages 注入提醒。
    """

    def __init__(self, manager: TodoManager) -> None:
        self.manager = manager

    def post_tool(self, call: ToolCall, result: ToolResult, state: LoopState) -> None:
        if call.name == "todo":
            self.manager.state.rounds_since_update = 0

    def post_turn(self, state: LoopState) -> None:
        self.manager.note_round_without_update()
        reminder = self.manager.reminder()
        if reminder:
            state.messages.append({"role": "user", "content": reminder})
            self.manager.state.rounds_since_update = 0
