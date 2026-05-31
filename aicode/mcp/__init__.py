"""
aicode.mcp — MCP（Model Context Protocol）stdio 客户端与工具桥接

配置：
  - <workdir>/.aicode/mcp.json
  - 或环境变量 AICODE_MCP_CONFIG 指向 JSON 文件
  - 可选合并 .claude-plugin/plugin.json 的 mcpServers

工具名格式：mcp__<server>__<tool>，与主循环权限/钩子一致。
"""

from .bridge import register_mcp_tools, shutdown_mcp_clients
from .client import MCPClient
from .loader import connect_servers, load_mcp_server_configs
from .router import MCPToolRouter

__all__ = [
    "MCPClient",
    "MCPToolRouter",
    "connect_servers",
    "load_mcp_server_configs",
    "register_mcp_tools",
    "shutdown_mcp_clients",
]
