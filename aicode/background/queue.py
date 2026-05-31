"""
background/queue.py — 优先级通知队列

设计特性：
  - 优先级：immediate > high > medium > low
  - Key 折叠：相同 key 的旧消息被新消息替换（防止 LLM 上下文被旧通知淹没）
  - 线程安全（threading.Lock）

与参考实现相比的增强：
  - 支持消息过期时间（TTL）
  - 提供 peek()（不消费地查看）
  - push() 返回是否发生了折叠
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


PRIORITIES: dict[str, int] = {
    "immediate": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
}


@dataclass
class _Notification:
    priority: int
    key: str | None
    message: str
    enqueued_at: float = field(default_factory=time.time)
    ttl: float | None = None   # None = 永不过期

    def is_expired(self) -> bool:
        if self.ttl is None:
            return False
        return time.time() > self.enqueued_at + self.ttl


class NotificationQueue:
    """
    线程安全的优先级通知队列。

    push(message, priority, key, ttl)
        添加通知；若 key 非空则折叠旧同 key 条目。
        返回 True 表示发生了折叠（旧条目被替换）。

    drain() → list[str]
        取出并清空所有未过期通知（按优先级排序）。

    peek() → list[str]
        查看内容但不消费。

    __len__() → 当前队列深度。
    """

    def __init__(self) -> None:
        self._queue: list[_Notification] = []
        self._lock = threading.Lock()

    def push(
        self,
        message: str,
        priority: str = "medium",
        key: str | None = None,
        ttl: float | None = None,
    ) -> bool:
        """添加通知，返回是否折叠了旧条目。"""
        prio = PRIORITIES.get(priority, PRIORITIES["medium"])
        folded = False
        with self._lock:
            if key:
                before = len(self._queue)
                self._queue = [n for n in self._queue if n.key != key]
                folded = len(self._queue) < before
            self._queue.append(_Notification(prio, key, message, ttl=ttl))
            self._queue.sort(key=lambda n: (n.priority, n.enqueued_at))
        return folded

    def drain(self) -> list[str]:
        """取出所有有效通知并清空队列。"""
        with self._lock:
            live = [n for n in self._queue if not n.is_expired()]
            self._queue.clear()
        return [n.message for n in live]

    def peek(self) -> list[str]:
        """查看（不消费）所有有效通知。"""
        with self._lock:
            live = [n for n in self._queue if not n.is_expired()]
        return [n.message for n in live]

    def clear(self) -> None:
        with self._lock:
            self._queue.clear()

    def __len__(self) -> int:
        with self._lock:
            return len([n for n in self._queue if not n.is_expired()])
