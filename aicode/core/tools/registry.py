"""
core/tools/registry.py — 工具注册表

所有工具（base / todo / task / mcp / skill）统一通过此注册表进入 Agent 循环。
设计目标：
- register() 是唯一的工具扩展入口
- dispatch() 执行工具并返回字符串输出
- get_schemas() 返回当前已注册的 OpenAI function 格式 schema 列表
"""
from __future__ import annotations

from typing import Any, Callable


class ToolRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, Callable[..., str]] = {}
        self._schemas: list[dict] = []

    def register(
        self,
        name: str,
        handler: Callable[..., str],
        schema: dict,
    ) -> None:
        """注册一个工具。重复注册会覆盖旧的（方便热更新/测试替换）。"""
        self._handlers[name] = handler
        # 替换已有同名 schema
        self._schemas = [s for s in self._schemas if s["function"]["name"] != name]
        self._schemas.append(schema)

    def get_handler(self, name: str) -> Callable[..., str] | None:
        return self._handlers.get(name)

    def get_schemas(self) -> list[dict]:
        return list(self._schemas)

    def dispatch(self, name: str, arguments: dict[str, Any]) -> str:
        """调用工具并返回字符串结果；工具未找到或抛异常均返回 Error 字符串。"""
        handler = self._handlers.get(name)
        if handler is None:
            return f"Error: unknown tool {name!r}"
        try:
            result = handler(**arguments)
            return str(result)
        except Exception as exc:
            return f"Error: {exc}"

    def names(self) -> list[str]:
        return list(self._handlers.keys())

    def get_handler_and_schema(
        self, name: str
    ) -> tuple[Callable[..., str] | None, dict | None]:
        """同时返回 handler 和 schema，用于工具子集过滤。"""
        handler = self._handlers.get(name)
        schema = next(
            (s for s in self._schemas if s["function"]["name"] == name), None
        )
        return handler, schema

    def __len__(self) -> int:
        return len(self._handlers)


def build_base_registry(workdir=None) -> ToolRegistry:
    """构建只包含基础工具（bash/read/write/edit）的注册表。"""
    from .base import run_bash, run_edit, run_read, run_write
    from .schemas import (
        bash_schema,
        edit_file_schema,
        read_file_schema,
        write_file_schema,
    )

    reg = ToolRegistry()
    if workdir:
        reg.register("bash", lambda **kw: run_bash(kw["command"], workdir), bash_schema())
        reg.register("read_file", lambda **kw: run_read(kw["path"], kw.get("limit"), workdir), read_file_schema())
        reg.register("write_file", lambda **kw: run_write(kw["path"], kw["content"], workdir), write_file_schema())
        reg.register("edit_file", lambda **kw: run_edit(kw["path"], kw["old_text"], kw["new_text"], workdir), edit_file_schema())
    else:
        reg.register("bash", lambda **kw: run_bash(kw["command"]), bash_schema())
        reg.register("read_file", lambda **kw: run_read(kw["path"], kw.get("limit")), read_file_schema())
        reg.register("write_file", lambda **kw: run_write(kw["path"], kw["content"]), write_file_schema())
        reg.register("edit_file", lambda **kw: run_edit(kw["path"], kw["old_text"], kw["new_text"]), edit_file_schema())
    return reg
