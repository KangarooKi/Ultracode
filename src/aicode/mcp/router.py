"""mcp/router.py — 将 mcp__server__tool 调用路由到对应 MCPClient。"""
from __future__ import annotations

from typing import Any

from .client import MCPClient


class MCPToolRouter:
    def __init__(self) -> None:
        self.clients: dict[str, MCPClient] = {}

    def register_client(self, client: MCPClient) -> None:
        self.clients[client.server_name] = client

    @staticmethod
    def is_mcp_tool(tool_name: str) -> bool:
        return tool_name.startswith("mcp__")

    def call(self, tool_name: str, arguments: dict[str, Any]) -> str:
        parts = tool_name.split("__", 2)
        if len(parts) != 3:
            return f"Error: invalid MCP tool name {tool_name!r}"
        _, server_name, actual = parts
        client = self.clients.get(server_name)
        if not client:
            return f"Error: MCP server not connected: {server_name!r}"
        return client.call_tool(actual, arguments)

    def get_all_tool_schemas(self) -> list[dict[str, Any]]:
        schemas: list[dict[str, Any]] = []
        for c in self.clients.values():
            schemas.extend(c.get_agent_tools())
        return schemas
