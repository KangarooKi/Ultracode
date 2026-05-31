"""
hooks/manager.py — 钩子系统（HookManager + HookMiddleware）

配置文件：<workdir>/.hooks.json
退出码约定：
  0 → 继续（stdout 可选 JSON 扩展）
  1 → 阻止工具调用（stderr 作为原因）
  2 → 注入消息到 tool result（stderr 内容）
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from aicode.core.loop import NoopMiddleware
from aicode.core.types import LoopState, ToolCall, ToolResult
from aicode.security.trust import is_workspace_trusted
from .events import HOOK_EVENTS, HOOK_TIMEOUT


class HookManager:
    """加载并执行 .hooks.json 中定义的钩子命令。"""

    def __init__(
        self,
        workdir: Path,
        config_path: Path | None = None,
        sdk_mode: bool = False,
    ) -> None:
        self.workdir = workdir
        self._sdk_mode = sdk_mode
        self.hooks: dict[str, list[dict]] = {e: [] for e in HOOK_EVENTS}

        cfg_path = config_path or (workdir / ".hooks.json")
        if cfg_path.exists():
            try:
                raw = json.loads(cfg_path.read_text(encoding="utf-8", errors="replace"))
                for event in HOOK_EVENTS:
                    self.hooks[event] = raw.get("hooks", {}).get(event, [])
                print(f"[Hooks loaded from {cfg_path.name}]")
            except Exception as exc:
                print(f"[Hook config error: {exc}]")

    def _trusted(self) -> bool:
        return self._sdk_mode or is_workspace_trusted(self.workdir)

    def run_hooks(self, event: str, context: dict | None = None) -> dict:
        """
        执行某事件下所有匹配的钩子。

        返回: {
          "blocked": bool,
          "block_reason": str,
          "messages": list[str],       # exit-code 2 的 stderr
          "permission_override": str,  # 可选，钩子 JSON 输出中的 permissionDecision
        }
        """
        result: dict = {"blocked": False, "block_reason": "", "messages": []}

        if not self._trusted():
            return result

        for hook_def in self.hooks.get(event, []):
            matcher = hook_def.get("matcher")
            if matcher and context:
                tool_name = context.get("tool_name", "")
                if matcher != "*" and matcher != tool_name:
                    continue

            command = hook_def.get("command", "")
            if not command:
                continue

            env = dict(os.environ)
            if context:
                env["HOOK_EVENT"] = event
                env["HOOK_TOOL_NAME"] = context.get("tool_name", "")
                env["HOOK_TOOL_INPUT"] = json.dumps(
                    context.get("tool_input", {}), ensure_ascii=False
                )[:10000]
                if "tool_output" in context:
                    env["HOOK_TOOL_OUTPUT"] = str(context["tool_output"])[:10000]

            try:
                r = subprocess.run(
                    command,
                    shell=True,
                    cwd=self.workdir,
                    env=env,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=HOOK_TIMEOUT,
                )

                if r.returncode == 0:
                    if r.stdout.strip():
                        print(f"  [hook:{event}] {r.stdout.strip()[:100]}")
                    try:
                        hook_out = json.loads(r.stdout)
                        if "updatedInput" in hook_out and context:
                            context["tool_input"] = hook_out["updatedInput"]
                        if "additionalContext" in hook_out:
                            result["messages"].append(hook_out["additionalContext"])
                        if "permissionDecision" in hook_out:
                            result["permission_override"] = hook_out["permissionDecision"]
                    except (json.JSONDecodeError, TypeError):
                        pass

                elif r.returncode == 1:
                    result["blocked"] = True
                    result["block_reason"] = r.stderr.strip() or "Blocked by hook."
                    print(f"  [hook:{event}] BLOCKED: {result['block_reason'][:200]}")

                elif r.returncode == 2:
                    msg = r.stderr.strip()
                    if msg:
                        result["messages"].append(msg)
                        print(f"  [hook:{event}] INJECT: {msg[:200]}")

            except subprocess.TimeoutExpired:
                print(f"  [hook:{event}] Timeout ({HOOK_TIMEOUT}s)")
            except Exception as exc:
                print(f"  [hook:{event}] Error: {exc}")

        return result


# ---------------------------------------------------------------------------
# Middleware 包装
# ---------------------------------------------------------------------------

class HookMiddleware(NoopMiddleware):
    """
    将 HookManager 接入循环：
    - pre_tool  → PreToolUse 钩子；blocked 则拦截
    - post_tool → PostToolUse 钩子；messages 追加到 result.content
    """

    def __init__(self, manager: HookManager) -> None:
        self.manager = manager

    def pre_tool(self, call: ToolCall, state: LoopState) -> ToolResult | None:
        ctx = {"tool_name": call.name, "tool_input": dict(call.arguments)}
        r = self.manager.run_hooks("PreToolUse", ctx)

        # 更新 call.arguments（钩子可能修改 updatedInput）
        call.arguments.update(ctx.get("tool_input", {}))

        pre_msgs = [f"[Hook]: {m}" for m in r.get("messages", [])]

        if r.get("blocked"):
            reason = r.get("block_reason", "Blocked by PreToolUse hook.")
            body = "\n".join([*pre_msgs, f"Tool blocked: {reason}"]) if pre_msgs else f"Tool blocked: {reason}"
            return ToolResult(call.id, body, "blocked")

        # 有 pre_msgs 但未阻止 → 存到 state.metadata 供 post_tool 追加
        if pre_msgs:
            state.metadata.setdefault("hook_pre_msgs", {})[call.id] = pre_msgs

        return None

    def post_tool(self, call: ToolCall, result: ToolResult, state: LoopState) -> None:
        ctx = {
            "tool_name": call.name,
            "tool_input": call.arguments,
            "tool_output": result.content,
        }
        r = self.manager.run_hooks("PostToolUse", ctx)

        pre_msgs = state.metadata.get("hook_pre_msgs", {}).pop(call.id, [])
        post_msgs = [f"[Hook]: {m}" for m in r.get("messages", [])]
        extra = "\n".join(pre_msgs + post_msgs)
        if extra:
            result.content = result.content + "\n" + extra
