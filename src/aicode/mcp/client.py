"""
mcp/client.py — stdio JSON-RPC MCP 客户端

负责启动 MCP server 子进程、完成 initialize 握手、列出工具并转发
tools/call 请求。当前实现使用按行分隔的 JSON-RPC stdio 传输。
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any


class MCPClient:
    def __init__(
        self,
        server_name: str,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        *,
        cwd: Path | None = None,
    ) -> None:
        self.server_name = server_name
        self.command = command
        self.args = list(args or [])
        base = dict(os.environ)
        if env:
            base.update({str(k): str(v) for k, v in env.items()})
        self.env = base
        self.cwd = cwd
        self.process: subprocess.Popen[str] | None = None
        self._request_id = 0
        self._tools: list[dict[str, Any]] = []

    def connect(self) -> bool:
        try:
            self.process = subprocess.Popen(
                [self.command, *self.args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env=self.env,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(self.cwd) if self.cwd else None,
            )
            self._send_request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "ultracode", "version": "0.1"},
                },
            )
            response = self._recv()
            if response and "result" in response:
                self._send_notification("notifications/initialized", {})
                return True
        except FileNotFoundError:
            print(f"[MCP] Command not found: {self.command!r}")
        except Exception as exc:
            print(f"[MCP] Connect {self.server_name!r} failed: {exc}")
        return False

    def list_tools(self) -> list[dict[str, Any]]:
        self._send_request("tools/list", {})
        response = self._recv()
        if response and "result" in response:
            self._tools = response["result"].get("tools", [])
        return self._tools

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        self._send_request(
            "tools/call",
            {"name": tool_name, "arguments": arguments or {}},
        )
        response = self._recv()
        if response and "result" in response:
            content = response["result"].get("content", [])
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict):
                    parts.append(block.get("text", str(block)))
                else:
                    parts.append(str(block))
            return "\n".join(parts) if parts else "(no content)"
        if response and "error" in response:
            err = response["error"]
            msg = err.get("message", "unknown") if isinstance(err, dict) else str(err)
            return f"MCP Error: {msg}"
        return "MCP Error: no response"

    def get_agent_tools(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for tool in self._tools:
            prefixed = f"mcp__{self.server_name}__{tool['name']}"
            schema = (
                tool.get("inputSchema")
                or tool.get("input_schema")
                or {"type": "object", "properties": {}}
            )
            out.append({
                "type": "function",
                "function": {
                    "name": prefixed,
                    "description": tool.get("description", "") or f"MCP tool {tool['name']}",
                    "parameters": schema,
                },
            })
        return out

    def disconnect(self) -> None:
        if not self.process:
            return
        try:
            self._send_notification("shutdown", {})
        except Exception:
            pass
        try:
            self.process.terminate()
            self.process.wait(timeout=5)
        except Exception:
            try:
                self.process.kill()
            except Exception:
                pass
        self.process = None

    def _send_request(self, method: str, params: dict[str, Any] | None) -> None:
        if not self.process or self.process.poll() is not None:
            return
        self._request_id += 1
        envelope: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
        }
        if params is not None:
            envelope["params"] = params
        line = json.dumps(envelope, ensure_ascii=False) + "\n"
        assert self.process.stdin is not None
        self.process.stdin.write(line)
        self.process.stdin.flush()

    def _send_notification(self, method: str, params: dict[str, Any] | None = None) -> None:
        if not self.process or self.process.poll() is not None:
            return
        envelope: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            envelope["params"] = params
        line = json.dumps(envelope, ensure_ascii=False) + "\n"
        assert self.process.stdin is not None
        self.process.stdin.write(line)
        self.process.stdin.flush()

    def _recv(self) -> dict[str, Any] | None:
        if not self.process or self.process.poll() is not None:
            return None
        assert self.process.stdout is not None
        try:
            line = self.process.stdout.readline()
            if not line.strip():
                return None
            return json.loads(line)
        except (json.JSONDecodeError, OSError):
            return None
