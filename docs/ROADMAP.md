# UltraCode 路线图

目标：把 UltraCode 做成可日常使用的终端智能代码助手。核心方向是稳定的 Agent 主循环、清晰的模块边界、可组合中间件、安全的本地工具执行，以及对 OpenAI 兼容模型和 MCP 工具的开放适配。

## 阶段 0（当前基线）

- [x] `core/loop.py` + `AgentLoopConfig` + 中间件栈
- [x] `cli/session.py` 统一组装会话；`repl` / `run` 共用
- [x] `cli/main.py`：`--version`、`-C/--cwd`、`repl`（默认）、`run`
- [x] `get_config(workdir=)` 首次初始化工作区
- [x] 基础工具经 `build_base_registry(workdir=)` 绑定配置工作区

## 阶段 1 — CLI 与工程体验

- [x] `run` 支持从 stdin 读入 prompt（`aicode run -`）
- [x] `aicode -v/--verbose run ...` 打印工具调用摘要
- [x] `aicode tasks` / `aicode worktrees`（无需 API 密钥）
- [ ] 结构化日志 / changelog 发布流程

## 阶段 2 — 恢复与韧性

- [x] `session` 在 `AICODE_ENABLE_RECOVERY=1` 时挂载 `RecoveryMiddleware` 与 `AgentLoopConfig.recovery`
- [x] `LLM_MAX_TOKENS` / `AICODE_MAX_TOKENS`、`LLM_MAX_TURNS` / `AICODE_MAX_TURNS`、`AICODE_RECOVERY_MAX_RETRIES`
- [ ] bash / API 调用超时等更细粒度环境变量（`core/tools/base` 仍为固定超时）

## 阶段 3 — 上下文与记忆

- [x] 压缩触发阈值环境变量 `AICODE_COMPACT_AUTO_THRESHOLD`
- [x] 项目根 `AGENTS.md` 注入（`prompt/sections.build_agents_md`）；`skills/` 扫描已存在

## 阶段 4 — 子 Agent 与后台

- [x] `subagent_call` 注册；子循环携带与主会话相同的 `PermissionMiddleware` + `HookMiddleware`
- [x] `background_run` / `background_check` / `background_cancel` + `BackgroundMiddleware`（完成通知注入对话）
- [x] 持久化任务 CLI：`aicode tasks`

## 阶段 5 — MCP 与工作区

- [x] `mcp/`：`.aicode/mcp.json`、`AICODE_MCP_CONFIG`、`.claude-plugin/plugin.json` 合并；stdio JSON-RPC；工具前缀 `mcp__server__tool`；退出时 `session_cleanup`
- [x] `worktrees/`：`git worktree list` + 工具 `git_worktree_list`
- [ ] 非 stdio 传输、MCP 重连与市场级插件流程（留作扩展）

## 模块职责速查

| 能力 | 代码位置 |
|------|----------|
| 工具与注册表 | `core/tools/` |
| 主循环与中间件协议 | `core/loop.py` |
| 权限与钩子 | `security/`、`hooks/` |
| 压缩与上下文 | `context/` |
| 记忆与系统提示 | `memory/`、`prompt/` |
| 规划与 Todo | `planning/` |
| MCP 扩展 | `mcp/` |
