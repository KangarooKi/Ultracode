"""
background — 后台任务执行模块

核心概念：
  NotificationQueue  : 优先级队列 + same-key 折叠
  BackgroundManager  : 线程化后台任务管理（运行/查询/停止）
  BackgroundMiddleware: LoopMiddleware，pre_turn 时注入完成通知

架构：
  主线程 (agent loop) ──pre_turn 拉取通知──> LLM 感知结果
       └──LLM 调用 background_run──> BackgroundManager
                                          └──后台线程执行──> NotificationQueue
"""
from .manager import BackgroundManager
from .middleware import BackgroundMiddleware, register_background_tools
from .queue import NotificationQueue

__all__ = [
    "BackgroundManager",
    "BackgroundMiddleware",
    "NotificationQueue",
    "register_background_tools",
]
