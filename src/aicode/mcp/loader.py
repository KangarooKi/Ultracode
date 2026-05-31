"""
mcp/loader.py — 从配置文件与 .claude-plugin 合并 MCP 服务器定义

优先级（后者覆盖同名）：
  1. <workdir>/.aicode/mcp.json
  2. 环境变量 AICODE_MCP_CONFIG 指向的 JSON 文件
  3. <workdir>/.claude-plugin/plugin.json 中的 mcpServers（键前缀 plugin__server）
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError):
        return None


def load_mcp_server_configs(workdir: Path) -> dict[str, dict[str, Any]]:
    """
    返回 server_name -> {command, args, env}。

    mcp.json 格式示例：
    {"servers": {"fs": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "."], "env": {}}}}
    """
    merged: dict[str, dict[str, Any]] = {}

    cfg_path = os.getenv("AICODE_MCP_CONFIG", "").strip()
    if cfg_path:
        raw = _read_json(Path(cfg_path))
        if raw:
            merged.update(_normalize_servers(raw))

    project = workdir / ".aicode" / "mcp.json"
    raw = _read_json(project)
    if raw:
        merged.update(_normalize_servers(raw))

    plugin = workdir / ".claude-plugin" / "plugin.json"
    praw = _read_json(plugin)
    if praw:
        plugin_name = str(praw.get("name", "plugin"))
        for sname, cfg in (praw.get("mcpServers") or {}).items():
            if isinstance(cfg, dict):
                key = f"{plugin_name}__{sname}"
                merged[key] = _normalize_one_server(cfg)

    return merged


def _normalize_servers(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    servers = raw.get("servers") or raw.get("mcpServers") or {}
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(servers, dict):
        return out
    for name, cfg in servers.items():
        if isinstance(cfg, dict):
            out[str(name)] = _normalize_one_server(cfg)
    return out


def _normalize_one_server(cfg: dict[str, Any]) -> dict[str, Any]:
    cmd = cfg.get("command") or cfg.get("cmd") or ""
    args = cfg.get("args", [])
    if not isinstance(args, list):
        args = []
    env = cfg.get("env", {})
    if not isinstance(env, dict):
        env = {}
    return {"command": str(cmd), "args": [str(a) for a in args], "env": {str(k): str(v) for k, v in env.items()}}


def connect_servers(
    workdir: Path,
    router: Any,
) -> list[Any]:
    """
    连接 loader 中所有服务器并注册到 router；返回已连接的 MCPClient 列表。
    """
    from .client import MCPClient

    clients: list[MCPClient] = []
    configs = load_mcp_server_configs(workdir)
    for name, cfg in configs.items():
        cmd = cfg.get("command", "")
        if not cmd:
            print(f"[MCP] Skip {name!r}: missing command")
            continue
        client = MCPClient(
            name,
            cmd,
            cfg.get("args", []),
            cfg.get("env"),
            cwd=workdir,
        )
        if client.connect():
            client.list_tools()
            router.register_client(client)
            clients.append(client)
            n_tools = len(client._tools)
            print(f"[MCP] {name}: connected, {n_tools} tools")
        else:
            client.disconnect()
    return clients
