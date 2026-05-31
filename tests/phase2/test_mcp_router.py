"""mcp/router 与 bridge 注册行为（无真实子进程）。"""
from __future__ import annotations

from unittest.mock import MagicMock

from aicode.core.tools.registry import ToolRegistry
from aicode.mcp.bridge import register_mcp_tools
from aicode.mcp.router import MCPToolRouter


def test_router_dispatches_to_client():
    router = MCPToolRouter()
    c = MagicMock()
    c.server_name = "demo"
    c.call_tool.return_value = "result"
    router.register_client(c)
    assert router.call("mcp__demo__hello", {"x": 1}) == "result"
    c.call_tool.assert_called_once_with("hello", {"x": 1})


def test_register_mcp_tools_adds_handlers():
    router = MCPToolRouter()
    c = MagicMock()
    c.server_name = "s"
    c._tools = [{"name": "t", "description": "d", "inputSchema": {"type": "object", "properties": {}}}]
    c.get_agent_tools = MagicMock(
        return_value=[
            {
                "type": "function",
                "function": {
                    "name": "mcp__s__t",
                    "description": "d",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
    )
    router.register_client(c)
    reg = ToolRegistry()
    register_mcp_tools(reg, router)
    assert "mcp__s__t" in reg.names()
    c.call_tool.return_value = "ok"
    assert reg.dispatch("mcp__s__t", {}) == "ok"
