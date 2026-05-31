"""mcp/bridge.py — 将 MCP 工具注册进 ToolRegistry。"""
from __future__ import annotations

from typing import Any

from aicode.core.tools.registry import ToolRegistry

from .router import MCPToolRouter


def _make_mcp_handler(tool_name: str, router: MCPToolRouter):
    def _handler(**kw: Any) -> str:
        return router.call(tool_name, kw)

    return _handler


def register_mcp_tools(registry: ToolRegistry, router: MCPToolRouter) -> None:
    """把已连接服务器暴露的工具写入 registry（名称 mcp__server__tool）。"""
    for schema in router.get_all_tool_schemas():
        fn = schema.get("function", schema)
        name = fn.get("name")
        if not name:
            continue
        registry.register(name, _make_mcp_handler(name, router), schema)


def shutdown_mcp_clients(clients: list[Any]) -> None:
    for c in clients:
        try:
            c.disconnect()
        except Exception:
            pass
