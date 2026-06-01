<p align="right">
<a href="TECHNICAL_REPORT.md">English</a> | 简体中文
</p>

# UltraCode 技术报告

版本来源：`pyproject.toml`（当前为 `0.1.0`）

本文档说明 UltraCode 的运行时架构、代码目录、Agent 主循环、中间件协议、工具执行路径、权限模型、终端渲染和扩展方式。

## 1. 概述

UltraCode 是一个单进程 CLI 智能代码助手。用户在终端输入请求后，CLI 组装系统提示和对话状态，Agent 主循环调用 OpenAI 兼容的 Chat Completions API，并在权限控制下把工具调用分发到本地工作区。

实现上分为五层：

| 层级 | 职责 |
|------|------|
| CLI 层 | 解析命令，运行 REPL 或单次模式，负责终端输出。 |
| 核心运行时 | 加载配置，调用模型，维护 Agent 主循环和工具调用解析。 |
| 中间件层 | 接入权限、Hook、压缩、恢复、Todo 提醒、后台通知和状态输出。 |
| 工具层 | 注册并执行文件、Bash、任务、MCP、后台任务、worktree 和子代理工具。 |
| 工作区层 | 读写本地项目状态、记忆、任务文件、后台日志和项目规则。 |

## 2. 设计目标

| 目标 | 说明 |
|------|------|
| 终端优先 | 把代码理解、修改、命令执行和确认流程留在终端里。 |
| 开放后端 | 支持任意兼容 OpenAI Chat Completions 形态的模型服务。 |
| 可组合运行时 | 保持主循环克制，把可选能力放入中间件。 |
| 本地操作可控 | 通过明确规则控制写文件、改文件、Bash 命令和后台任务。 |
| Markdown 友好 | 让模型输出在终端里可读，尤其是表格和代码块。 |

## 3. 系统架构

<p align="center">
  <img src="assets/ultracode_system_architecture.png" alt="UltraCode system architecture" width="960">
</p>

上图把 UltraCode 拆成五个运行区域：终端入口、Agent 运行时、中间件、工具执行、本地工作区与外部服务。关键链路很短：模型生成回复或工具调用，中间件检查调用，注册表分发工具，工具结果再回到下一轮模型输入。

## 4. 运行流程

```text
用户请求
  -> CLI 会话
  -> SystemPromptBuilder
  -> LoopState(messages, metadata, turn_count)
  -> run_agent_loop
  -> 携带工具 schema 的 Chat Completions API 调用
  -> assistant message 或 tool_calls
  -> middleware.pre_tool
  -> ToolRegistry.dispatch
  -> middleware.post_tool
  -> tool result message
  -> 下一轮模型调用
```

| 步骤 | 说明 |
|------|------|
| 1 | `cli/main.py` 选择 REPL、单次运行、任务查看、worktree 查看或版本输出。 |
| 2 | `cli/session.py` 为 REPL 和 `run` 构建共享运行时上下文。 |
| 3 | `SystemPromptBuilder` 组合核心规则、工具 schema、项目文件、记忆、技能和动态上下文。 |
| 4 | `run_agent_loop` 调用模型，并把流式与非流式回复归一成同一种内部结构。 |
| 5 | 工具调用先经过中间件，再进入 `ToolRegistry.dispatch`。 |
| 6 | 工具结果以 `role=tool` 消息写入历史，成为下一轮模型输入。 |
| 7 | 当模型返回普通助手回复或达到 `max_turns` 时，循环结束。 |

## 5. 模块映射

| 路径 | 职责 |
|------|------|
| `src/aicode/cli/` | CLI 入口、REPL、会话组装、输出格式化和主题。 |
| `src/aicode/core/` | Agent 主循环、配置、OpenAI 客户端、等待提示、Markdown 流式写入和基础工具。 |
| `src/aicode/core/tools/` | `ToolRegistry`、基础文件和 Bash 工具、OpenAI function schemas。 |
| `src/aicode/prompt/` | 系统提示构建器和提示词分段。 |
| `src/aicode/security/` | 权限管理、Bash 校验和工作区信任。 |
| `src/aicode/hooks/` | `.hooks.json` 加载和 Hook 中间件。 |
| `src/aicode/context/` | transcript 处理、压缩状态和压缩中间件。 |
| `src/aicode/recovery/` | 恢复配置、重试策略和续写中间件。 |
| `src/aicode/planning/` | 会话 Todo 和持久化 `.tasks/` 任务图。 |
| `src/aicode/background/` | 后台任务管理、运行时任务文件和后台工具。 |
| `src/aicode/memory/` | Markdown 记忆加载和可选记忆更新。 |
| `src/aicode/mcp/` | MCP 配置加载、客户端路由和注册表桥接。 |
| `src/aicode/subagent/` | 子代理运行器和 `subagent_call` 注册。 |
| `src/aicode/worktrees/` | Git worktree 检查工具。 |
| `tests/` | 覆盖主循环、工具、权限、渲染、上下文、MCP、恢复和后台任务的单元测试。 |

## 6. Agent 主循环

`src/aicode/core/loop.py` 负责运行时契约。`AgentLoopConfig` 提供模型客户端、模型名称、工具注册表、系统提示回调、中间件列表、token 与轮数限制、可选恢复配置和流式输出设置。

`LoopState` 保存对话消息、循环轮数、上一次停止原因、状态转移原因，以及供中间件使用的 metadata 字典。工具调用使用统一的 `ToolCall` 类型，工具输出使用 `ToolResult`。

| 关注点 | 实现方式 |
|--------|----------|
| 非流式调用 | 调用 `chat.completions.create(...)`，解析助手正文、工具调用和结束原因。 |
| 流式调用 | 累积正文 delta 和工具调用 delta，最后转成与非流式一致的结构。 |
| 等待提示 | 非流式模式可在 stderr 显示等待提示；流式模式关闭该提示，避免输出交错。 |
| 恢复 | 启用恢复后，模型调用走恢复路径，便于在 prompt 过长或连接异常时压缩与重试。 |
| 工具轮次 | 每个工具结果会追加到消息历史，并可能触发下一轮模型调用。 |

## 7. 中间件

中间件让可选能力插入 Agent 主循环，而不需要复制主循环代码。协议定义在 `src/aicode/core/loop.py`。

| 钩子 | 运行时机 | 常见用途 |
|------|----------|----------|
| `pre_turn` | 模型轮次开始前。 | 添加通知、状态行、恢复提示或压缩后的上下文。 |
| `pre_assistant_output` | 第一段流式助手正文打印前。 | 清除临时“思考中”状态。 |
| `post_model` | 每次模型调用结束后。 | 清除临时状态，检查结束原因。 |
| `pre_tool` | 工具分发前。 | 权限检查、Hook 阻断、安全审查。 |
| `post_tool` | 工具返回后。 | 记录结果、更新 Todo 状态、追踪压缩相关文件。 |
| `post_turn` | 一轮循环结束后。 | 注入提醒、恢复续写、后台任务通知。 |

`build_repl_context` 默认安装权限、Hook、状态输出、压缩、可选恢复、Todo 和后台任务中间件。子代理使用较小的权限与 Hook 链路，继承本地安全规则，但不复用完整父级 UI 管线。

## 8. 工具系统

工具通过 `ToolRegistry.register(name, handler, schema)` 注册。注册表向模型暴露 OpenAI 兼容的 function schema，并把模型选择的工具调用分发到 Python 处理函数。

| 工具组 | 说明 |
|--------|------|
| 基础工具 | 来自 `core/tools/base.py` 的 `bash`、`read_file`、`write_file`、`edit_file`。 |
| 任务工具 | 基于 `.tasks/` 的持久化任务图工具。 |
| Todo 工具 | 会话级 Todo 更新工具，供模型执行多步骤任务时使用。 |
| 后台工具 | `background_run`、`background_check`、`background_cancel`。 |
| MCP 工具 | 以 `mcp__*` 前缀注册远程或本地 MCP 工具。 |
| 子代理工具 | `subagent_call` 启动隔离的子循环，可传入部分工具和技能模板。 |
| Worktree 工具 | `git_worktree_list` 查看本地 git worktree。 |

`ToolResult.to_message()` 会把工具结果转成 OpenAI `role=tool` 消息。这样原生工具、MCP 工具和被权限中间件拦截的结果都走同一条路径。

## 9. 安全模型

UltraCode 把本地工具执行视为主要风险点。安全设计由命令校验、路径隔离、权限模式和写入前预览组成。

| 机制 | 说明 |
|------|------|
| 工作区路径隔离 | `safe_path` 把文件路径限制在配置的 workdir 内，并拒绝逃逸路径。 |
| Bash 校验 | `BashSecurityValidator` 会在权限规则前扫描严重或警示级命令模式。 |
| 只读 Bash 自动放行 | 明确只读的命令，如 `ls`、`rg`、`cat` 和安全的 `git` 查看命令，可以自动放行。 |
| 权限模式 | `default` 对未知写操作询问，`plan` 阻止写操作，`auto` 放行已知只读操作。 |
| 写入预览 | `write_file` 和 `edit_file` 会在用户确认前展示内容预览。 |
| 工作区信任 | Hook 执行依赖工作区信任检查。 |

权限路径实现于 `src/aicode/security/permission.py`：先做 Bash 校验，再检查 deny 规则、模式决策、allow 规则，最后回退到交互式确认。

## 10. 终端输出

CLI 使用轻量 Markdown 管线渲染助手输出，而不是完整 CommonMark 解析器。目标是让终端显示稳定、清楚。

| 组件 | 说明 |
|------|------|
| `markdown_terminal.py` | 渲染标题、列表、引用、行内代码、链接、分隔线、GFM 表格和代码块。 |
| `AssistantMarkdownStreamWriter` | 流式输出时缓存表格和代码块片段，避免不完整 Markdown 提前打印。 |
| 表格宽度 | 通过 `unicodedata.east_asian_width` 处理中文等双宽字符。 |
| 状态 UI | `PrintingMiddleware` 显示临时思考状态和简洁工具进度。 |
| 颜色策略 | `AICODE_COLOR` 可强制颜色，`NO_COLOR` 在未被覆盖时禁用 ANSI 输出。 |

渲染器有意避开复杂 Markdown 功能，例如深层嵌套块解析。遇到复杂结构时，如果终端渲染不稳定，会尽量保留为普通文本。

## 11. 工作区与外部服务

UltraCode 从选定工作区读取项目上下文，并把运行状态写入少量本地目录。

| 路径或服务 | 说明 |
|------------|------|
| `CLAUDE.md` / `AGENTS.md` | 注入系统提示的项目规则。 |
| `.memory/` | 由 `MemoryManager` 加载的 Markdown 记忆。 |
| `.tasks/` | 任务工具使用的持久化任务图。 |
| `.runtime-tasks/` | 后台任务状态 JSON 和日志。 |
| `skills/` | 可选子代理技能模板。 |
| `.hooks.json` | Hook 定义，受信任机制保护。 |
| 模型 API | 任意 OpenAI 兼容 Chat Completions 接口。 |
| MCP 服务 | 桥接进 `ToolRegistry` 的本地或远程工具服务。 |

后台任务由 `BackgroundManager` 管理。它在同步 `bash` 路径之外启动命令，把状态和日志写入 `.runtime-tasks/`，并由 `BackgroundMiddleware` 在后续用户轮次提示任务完成情况。

## 12. 扩展方式

| 扩展 | 实现路径 |
|------|----------|
| 添加工具 | 创建处理函数和 OpenAI function schema，并在会话组装时调用 `registry.register(...)`。 |
| 添加中间件 | 实现需要的 `LoopMiddleware` 钩子，并把实例加入 `AgentLoopConfig.middleware`。 |
| 添加 MCP 支持 | 添加 JSON MCP 配置或设置 `AICODE_MCP_CONFIG`，再由 `register_mcp_tools` 暴露发现的工具。 |
| 添加子代理技能 | 在 `skills/` 下放置 `SKILL.md`，需要时通过 `subagent_call` 使用该模板。 |
| 修改提示词行为 | 修改 `src/aicode/prompt/` 分段，或调整项目级 `CLAUDE.md` / `AGENTS.md`。 |

## 13. 测试与维护

测试使用 pytest 和模拟模型客户端，覆盖主循环、工具调用、权限决策、上下文压缩、恢复、Markdown 输出、MCP 桥接、后台任务和任务规划。

```bash
pip install -e ".[dev]"
python -m pytest tests/ -q
```

维护时建议同步检查：

| 项目 | 检查点 |
|------|--------|
| API 和配置 | 配置变量或模型调用行为变化时，同步更新 README 和本报告。 |
| 工具 schema | 保持工具 schema 描述与处理函数行为一致。 |
| 中间件顺序 | 运行时变更后，重新检查权限、Hook、状态、压缩、恢复、Todo 和后台任务中间件顺序。 |
| 终端渲染 | 为表格、代码块、中文文本和流式片段补充回归测试。 |

## 14. 已知限制

| 限制 | 说明 |
|------|------|
| 同步 Bash | 普通 `bash` 工具会等待命令结束。长时间服务、游戏或 GUI 程序建议用 `background_run`。 |
| Markdown 范围 | 渲染器覆盖常见终端 Markdown，不追求完整 CommonMark 边界情况。 |
| 终端宽度 | 中文等双宽字符已处理，但歧义宽度字符仍受终端字体和设置影响。 |
| Shell 可移植性 | 项目主要按类 Unix shell 行为测试，Windows shell 行为仍需要额外检查。 |
