# aicode 架构说明

## 依赖方向（自上而下）

```
cli/          → 解析参数、启动 repl/run；只负责调用 session 与 core
cli/session.py → 组装 ReplContext（工具、中间件、AgentLoopConfig）
core/loop.py  → 唯一 Agent 主循环；不依赖 cli
core/tools/   → 工具实现与 schema；registry 为扩展点
planning/     → Todo、任务图；通过 register 挂到 registry
memory/       → 持久记忆加载；prompt 构建时注入
prompt/       → 系统提示拼装
security/     → PermissionMiddleware
hooks/        → HookMiddleware
context/      → CompactMiddleware
recovery/     → 可选恢复策略（由 AgentLoopConfig 引用）
subagent/     → `subagent_call` + `spawn_subagent`（与主会话共享权限/钩子中间件）
background/   → `BackgroundManager` + `BackgroundMiddleware` + 三工具
mcp/          → stdio MCP 客户端、路由、载入 `.aicode/mcp.json` 等
worktrees/    → `git worktree list` 与 `git_worktree_list` 工具
```

## 环境变量（节选）

| 变量 | 作用 |
|------|------|
| `LLM_API_KEY` / `OPENAI_API_KEY` | API 密钥 |
| `LLM_MODEL` | 模型名 |
| `LLM_BASE_URL` | OpenAI 兼容网关 |
| `LLM_MAX_TOKENS` / `AICODE_MAX_TOKENS` | 传给 API 的 `max_tokens`（前者优先） |
| `LLM_MAX_TURNS` / `AICODE_MAX_TURNS` | 主循环轮次上限 |
| `AICODE_ENABLE_RECOVERY` | `1`/`true`/`yes`/`on` 时启用 `recovery/`（退避、超长压缩、续写中间件） |
| `AICODE_RECOVERY_MAX_RETRIES` | 恢复相关重试次数上限 |
| `AICODE_COMPACT_AUTO_THRESHOLD` | 触发自动压缩的上下文字符数阈值 |
| `AICODE_MCP_CONFIG` | 指向额外 MCP 配置文件（JSON，与 `.aicode/mcp.json` 同结构） |

**MCP 配置示例**（`<workdir>/.aicode/mcp.json`）：

```json
{
  "servers": {
    "demo": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
      "env": {}
    }
  }
}
```

## 与 Claude Code CLI 的对照（能力级）

| 能力 | aicode 现状 | 说明 |
|------|------------|------|
| 交互会话 | `aicode` / `repl` | 斜杠命令见 `cli/repl.py` |
| 单次非交互 | `aicode run ...` / `aicode run -`（stdin） | 默认安静；`-v` 打印工具摘要 |
| 工作区根 | `-C` + `Config.workdir` + `build_base_registry(workdir)` | 与进程 cwd 可分离 |
| 项目规则 | 根目录 `AGENTS.md` | 由 `prompt/sections.build_agents_md` 注入系统提示 |
| 工具调用 | bash / 读写 / edit / todo / task / background_* / subagent_call / git_worktree_list / mcp__* | 见 `cli/session.py` 组装顺序 |
| MCP | stdio、工具名 `mcp__<server>__<tool>` | `mcp/`；plan 模式拒绝全部 MCP；auto 对 read 类 MCP 自动放行 |
| Git worktree | `aicode worktrees`、工具 `git_worktree_list` | `worktrees/git.py` |
| 后台命令 | `background_run` 等 | `background/`；完成通知由中间件注入 |

## 扩展新功能的约定

1. **新中间件**：实现 `LoopMiddleware`（或继承 `NoopMiddleware`），在 `build_repl_context` 中插入合适顺序。
2. **新工具**：在独立模块中实现 handler + schema，`registry.register(...)`；勿在 `loop.py` 写分支。
3. **新 CLI 子命令**：在 `cli/main.py` 增加 subparser，复用 `build_repl_context`，避免复制组装代码。
