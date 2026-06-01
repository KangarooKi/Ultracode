# UltraCode Technical Report / 技术报告

Version source: `pyproject.toml` (`0.1.0` at the time of writing)

版本来源：`pyproject.toml`（当前为 `0.1.0`）

This report documents the runtime architecture, code layout, Agent loop, middleware contract, tool execution path, permission model, terminal rendering, and extension points for UltraCode.

本文档说明 UltraCode 的运行时架构、代码目录、Agent 主循环、中间件协议、工具执行路径、权限模型、终端渲染和扩展方式。

## 1. Overview / 概述

UltraCode is a single-process CLI coding agent. The user enters a prompt in the terminal, the CLI builds a system prompt and conversation state, the Agent loop calls an OpenAI-compatible Chat Completions API, and tool calls are dispatched back into the local workspace under permission checks.

UltraCode 是一个单进程 CLI 智能代码助手。用户在终端输入请求后，CLI 组装系统提示和对话状态，Agent 主循环调用 OpenAI 兼容的 Chat Completions API，并在权限控制下把工具调用分发到本地工作区。

The implementation uses a layered design:

实现上采用分层设计：

| Layer | English | 中文 |
|-------|---------|------|
| CLI layer | Parses commands, runs REPL or one-shot mode, renders terminal output. | 解析命令，运行 REPL 或单次模式，负责终端输出。 |
| Core runtime | Loads config, calls the model, owns the Agent loop and tool-call parsing. | 加载配置，调用模型，维护 Agent 主循环和工具调用解析。 |
| Middleware layer | Adds permission, hooks, compaction, recovery, todo, background notifications, and status output. | 通过中间件接入权限、Hook、压缩、恢复、Todo、后台通知和状态输出。 |
| Tool layer | Registers and executes file tools, Bash, tasks, MCP, background tasks, worktree tools, and subagents. | 注册并执行文件、Bash、任务、MCP、后台任务、worktree 和子代理工具。 |
| Workspace layer | Reads and writes local project state, memory, task files, runtime logs, and project instructions. | 读写本地项目状态、记忆、任务文件、后台日志和项目规则。 |

## 2. Design Goals / 设计目标

| Goal | English | 中文 |
|------|---------|------|
| Terminal-first workflow | Keep coding, inspection, command execution, and review inside the terminal. | 把代码理解、修改、命令执行和确认流程留在终端里。 |
| Open backend | Use any model provider that implements the OpenAI Chat Completions shape. | 支持任意兼容 OpenAI Chat Completions 形态的模型后端。 |
| Composable runtime | Keep the Agent loop small and move optional behavior into middleware. | 保持主循环克制，把可选能力放入中间件。 |
| Controlled local actions | Gate writes, edits, Bash commands, and background actions through explicit rules. | 通过明确规则控制写文件、改文件、Bash 命令和后台任务。 |
| Markdown-friendly CLI | Make model output readable in a terminal, including tables and fenced code blocks. | 让模型输出在终端里可读，尤其是表格和代码块。 |

## 3. System Architecture / 系统架构

<p align="center">
  <img src="assets/ultracode_system_architecture.png" alt="UltraCode system architecture" width="960">
</p>

The diagram splits UltraCode into five runtime areas: terminal entry, Agent runtime, middleware, tool execution, and workspace or external services. The critical path is short: the model proposes a response or tool call; middleware can inspect the call; the registry dispatches the tool; the result goes back into the next model turn.

上图把 UltraCode 拆成五个运行区域：终端入口、Agent 运行时、中间件、工具执行、本地工作区与外部服务。关键链路很短：模型生成回复或工具调用，中间件检查调用，注册表分发工具，工具结果再回到下一轮模型输入。

## 4. Runtime Flow / 运行流程

```text
user prompt
  -> CLI session
  -> SystemPromptBuilder
  -> LoopState(messages, metadata, turn_count)
  -> run_agent_loop
  -> Chat Completions API with tool schemas
  -> assistant message or tool_calls
  -> middleware.pre_tool
  -> ToolRegistry.dispatch
  -> middleware.post_tool
  -> tool result message
  -> next model turn
```

| Step | English | 中文 |
|------|---------|------|
| 1 | `cli/main.py` selects REPL, one-shot run, task view, worktree view, or version output. | `cli/main.py` 选择 REPL、单次运行、任务查看、worktree 查看或版本输出。 |
| 2 | `cli/session.py` builds the shared runtime context for REPL and `run`. | `cli/session.py` 为 REPL 和 `run` 构建共享运行时上下文。 |
| 3 | `SystemPromptBuilder` combines core rules, tool schemas, project files, memories, skills, and dynamic context. | `SystemPromptBuilder` 组合核心规则、工具 schema、项目文件、记忆、技能和动态上下文。 |
| 4 | `run_agent_loop` calls the model and normalizes streaming and non-streaming responses into the same internal shape. | `run_agent_loop` 调用模型，并把流式与非流式回复归一成同一种内部结构。 |
| 5 | Tool calls pass through middleware before reaching `ToolRegistry.dispatch`. | 工具调用先经过中间件，再进入 `ToolRegistry.dispatch`。 |
| 6 | Tool results are appended as `role=tool` messages and become input for the next turn. | 工具结果以 `role=tool` 消息写入历史，成为下一轮模型输入。 |
| 7 | The loop stops when the model returns a normal assistant reply or `max_turns` is reached. | 当模型返回普通助手回复或达到 `max_turns` 时，循环结束。 |

## 5. Module Map / 模块映射

| Path | English | 中文 |
|------|---------|------|
| `src/aicode/cli/` | CLI entry, REPL, session assembly, output formatting, theme. | CLI 入口、REPL、会话组装、输出格式化和主题。 |
| `src/aicode/core/` | Agent loop, config, OpenAI client, wait hints, Markdown stream writer, tool base classes. | Agent 主循环、配置、OpenAI 客户端、等待提示、Markdown 流式写入和基础工具。 |
| `src/aicode/core/tools/` | `ToolRegistry`, base file and Bash tools, OpenAI function schemas. | `ToolRegistry`、基础文件和 Bash 工具、OpenAI function schemas。 |
| `src/aicode/prompt/` | System prompt builder and prompt sections. | 系统提示构建器和提示词分段。 |
| `src/aicode/security/` | Permission manager, Bash validator, workspace trust. | 权限管理、Bash 校验和工作区信任。 |
| `src/aicode/hooks/` | `.hooks.json` loading and hook middleware. | `.hooks.json` 加载和 Hook 中间件。 |
| `src/aicode/context/` | Transcript handling, compaction state, compact middleware. | transcript 处理、压缩状态和压缩中间件。 |
| `src/aicode/recovery/` | Recovery config, retry policy, continuation middleware. | 恢复配置、重试策略和续写中间件。 |
| `src/aicode/planning/` | Session todos and persistent `.tasks/` graph. | 会话 Todo 和持久化 `.tasks/` 任务图。 |
| `src/aicode/background/` | Background task manager, runtime task files, background tools. | 后台任务管理、运行时任务文件和后台工具。 |
| `src/aicode/memory/` | Markdown memory loading and optional memory updates. | Markdown 记忆加载和可选记忆更新。 |
| `src/aicode/mcp/` | MCP config loading, client routing, registry bridge. | MCP 配置加载、客户端路由和注册表桥接。 |
| `src/aicode/subagent/` | Subagent runner and `subagent_call` registration. | 子代理运行器和 `subagent_call` 注册。 |
| `src/aicode/worktrees/` | Git worktree inspection tool. | Git worktree 检查工具。 |
| `tests/` | Unit tests for loop behavior, tools, permissions, rendering, context, MCP, recovery, and background tasks. | 覆盖主循环、工具、权限、渲染、上下文、MCP、恢复和后台任务的单元测试。 |

## 6. Agent Loop / Agent 主循环

`src/aicode/core/loop.py` owns the runtime contract. `AgentLoopConfig` provides the model client, model name, registry, system prompt callback, middleware list, max token and turn limits, optional recovery config, and stream writer settings.

`src/aicode/core/loop.py` 负责运行时契约。`AgentLoopConfig` 提供模型客户端、模型名称、工具注册表、系统提示回调、中间件列表、token 与轮数限制、可选恢复配置和流式输出设置。

`LoopState` stores conversation messages, turn count, last stop reason, transition reason, and a metadata dictionary for middleware. Tool calls use the shared `ToolCall` type, and tool outputs use `ToolResult`.

`LoopState` 保存对话消息、循环轮数、上一次停止原因、状态转移原因，以及供中间件使用的 metadata 字典。工具调用使用统一的 `ToolCall` 类型，工具输出使用 `ToolResult`。

| Concern | English | 中文 |
|---------|---------|------|
| Non-streaming call | Calls `chat.completions.create(...)`, parses assistant content, tool calls, and finish reason. | 调用 `chat.completions.create(...)`，解析助手正文、工具调用和结束原因。 |
| Streaming call | Accumulates content deltas and tool-call deltas, then returns the same structure as non-streaming mode. | 累积正文 delta 和工具调用 delta，最后转成与非流式一致的结构。 |
| Wait hint | Non-streaming mode can show a stderr wait hint. Streaming mode avoids the hint to prevent output interleaving. | 非流式模式可在 stderr 显示等待提示；流式模式关闭该提示，避免输出交错。 |
| Recovery | When recovery is enabled, model calls use the recovery path so compaction and retries can react to long prompts or transient errors. | 启用恢复后，模型调用走恢复路径，便于在 prompt 过长或连接异常时压缩与重试。 |
| Tool turn | Each tool result is appended to messages and can trigger another model turn. | 每个工具结果会追加到消息历史，并可能触发下一轮模型调用。 |

## 7. Middleware / 中间件

Middleware lets optional behavior interpose around the Agent loop without copying the loop itself. The contract is defined in `src/aicode/core/loop.py`.

中间件让可选能力插入 Agent 主循环，而不需要复制主循环代码。协议定义在 `src/aicode/core/loop.py`。

| Hook | When it runs | Typical use |
|------|--------------|-------------|
| `pre_turn` | Before a model turn begins. | Add notifications, status lines, recovery hints, or compacted context. |
| `pre_assistant_output` | Before the first streamed assistant token is printed. | Clear transient "thinking" UI. |
| `post_model` | After each model call finishes. | Clear temporary status, inspect finish reason. |
| `pre_tool` | Before a tool is dispatched. | Permission checks, hook blocking, safety review. |
| `post_tool` | After a tool returns. | Log results, update todo state, track files for compaction. |
| `post_turn` | After a loop turn completes. | Inject reminders, recovery continuations, background task notifications. |

The default session assembled by `build_repl_context` installs permission, hook, status printing, compaction, optional recovery, todo, and background middleware. Subagents receive a smaller permission and hook chain so they inherit local safety rules without sharing the entire parent UI pipeline.

`build_repl_context` 默认安装权限、Hook、状态输出、压缩、可选恢复、Todo 和后台任务中间件。子代理使用较小的权限与 Hook 链路，继承本地安全规则，但不复用完整父级 UI 管线。

## 8. Tool System / 工具系统

Tools are registered through `ToolRegistry.register(name, handler, schema)`. The registry exposes OpenAI-compatible function schemas to the model and dispatches selected tool calls to Python handlers.

工具通过 `ToolRegistry.register(name, handler, schema)` 注册。注册表向模型暴露 OpenAI 兼容的 function schema，并把模型选择的工具调用分发到 Python 处理函数。

| Tool group | English | 中文 |
|------------|---------|------|
| Base tools | `bash`, `read_file`, `write_file`, `edit_file` from `core/tools/base.py`. | 来自 `core/tools/base.py` 的 `bash`、`read_file`、`write_file`、`edit_file`。 |
| Task tools | Persistent task graph tools backed by `.tasks/`. | 基于 `.tasks/` 的持久化任务图工具。 |
| Todo tool | Session-scoped todo updates used by the model during multi-step work. | 会话级 Todo 更新工具，供模型执行多步骤任务时使用。 |
| Background tools | `background_run`, `background_check`, `background_cancel`. | `background_run`、`background_check`、`background_cancel`。 |
| MCP tools | Remote or local MCP tools registered with the `mcp__*` prefix. | 以 `mcp__*` 前缀注册远程或本地 MCP 工具。 |
| Subagent tool | `subagent_call` starts an isolated child loop with selected tools and optional skill templates. | `subagent_call` 启动隔离的子循环，可传入部分工具和技能模板。 |
| Worktree tool | `git_worktree_list` reports local git worktrees. | `git_worktree_list` 查看本地 git worktree。 |

`ToolResult.to_message()` converts a result into the OpenAI `role=tool` message shape. This keeps native tools, MCP tools, and intercepted permission results on the same path.

`ToolResult.to_message()` 会把工具结果转成 OpenAI `role=tool` 消息。这样原生工具、MCP 工具和被权限中间件拦截的结果都走同一条路径。

## 9. Security Model / 安全模型

UltraCode treats local tool execution as the main risk area. The safety design combines command validation, path isolation, permission modes, and preview before writes.

UltraCode 把本地工具执行视为主要风险点。安全设计由命令校验、路径隔离、权限模式和写入前预览组成。

| Mechanism | English | 中文 |
|-----------|---------|------|
| Workspace path isolation | `safe_path` resolves file paths under the configured workdir and rejects escape attempts. | `safe_path` 把文件路径限制在配置的 workdir 内，并拒绝逃逸路径。 |
| Bash validation | `BashSecurityValidator` scans for severe or warning-level patterns before permission rules run. | `BashSecurityValidator` 会在权限规则前扫描严重或警示级命令模式。 |
| Read-only Bash auto approval | Clearly read-only commands such as `ls`, `rg`, `cat`, and safe `git` inspection commands can be allowed automatically. | 明确只读的命令，如 `ls`、`rg`、`cat` 和安全的 `git` 查看命令，可以自动放行。 |
| Permission modes | `default` asks for unknown write actions, `plan` blocks writes, and `auto` allows known read-like actions. | `default` 对未知写操作询问，`plan` 阻止写操作，`auto` 放行已知只读操作。 |
| Write previews | `write_file` and `edit_file` show content previews before the user approves a change. | `write_file` 和 `edit_file` 会在用户确认前展示内容预览。 |
| Workspace trust | Hook execution depends on workspace trust checks. | Hook 执行依赖工作区信任检查。 |

The permission path is implemented in `src/aicode/security/permission.py`: Bash validation, deny rules, mode-specific decisions, allow rules, and interactive fallback.

权限路径实现于 `src/aicode/security/permission.py`：先做 Bash 校验，再检查 deny 规则、模式决策、allow 规则，最后回退到交互式确认。

## 10. Terminal Output / 终端输出

The CLI renders assistant output with a lightweight Markdown pipeline rather than a full CommonMark parser. The goal is predictable terminal readability.

CLI 使用轻量 Markdown 管线渲染助手输出，而不是完整 CommonMark 解析器。目标是让终端显示稳定、清楚。

| Component | English | 中文 |
|-----------|---------|------|
| `markdown_terminal.py` | Formats headings, lists, quotes, inline code, links, horizontal rules, GFM tables, and fenced code blocks. | 渲染标题、列表、引用、行内代码、链接、分隔线、GFM 表格和代码块。 |
| `AssistantMarkdownStreamWriter` | Buffers table and fence fragments during streaming so incomplete Markdown is not printed too early. | 流式输出时缓存表格和代码块片段，避免不完整 Markdown 提前打印。 |
| Table width | Uses `unicodedata.east_asian_width` for wide and fullwidth CJK characters. | 通过 `unicodedata.east_asian_width` 处理中文等双宽字符。 |
| Status UI | `PrintingMiddleware` shows transient thinking lines and concise tool progress lines. | `PrintingMiddleware` 显示临时思考状态和简洁工具进度。 |
| Color policy | `AICODE_COLOR` can force color, and `NO_COLOR` disables ANSI output when not overridden. | `AICODE_COLOR` 可强制颜色，`NO_COLOR` 在未被覆盖时禁用 ANSI 输出。 |

The renderer intentionally avoids broad Markdown features such as nested block parsing. Complex Markdown may still be printed as plain text when a terminal-friendly rendering would be ambiguous.

渲染器有意避开复杂 Markdown 功能，例如深层嵌套块解析。遇到复杂结构时，如果终端渲染不稳定，会尽量保留为普通文本。

## 11. Workspace And External Services / 工作区与外部服务

UltraCode reads project context from the selected workspace and writes runtime state into a small set of local folders.

UltraCode 从选定工作区读取项目上下文，并把运行状态写入少量本地目录。

| Path or service | English | 中文 |
|-----------------|---------|------|
| `CLAUDE.md` / `AGENTS.md` | Project instructions injected into the system prompt. | 注入系统提示的项目规则。 |
| `.memory/` | Markdown memories loaded by `MemoryManager`. | 由 `MemoryManager` 加载的 Markdown 记忆。 |
| `.tasks/` | Persistent task graph used by task tools. | 任务工具使用的持久化任务图。 |
| `.runtime-tasks/` | Background task state JSON and logs. | 后台任务状态 JSON 和日志。 |
| `skills/` | Optional subagent skill templates. | 可选子代理技能模板。 |
| `.hooks.json` | Hook definitions, guarded by trust. | Hook 定义，受信任机制保护。 |
| Model API | Any OpenAI-compatible Chat Completions endpoint. | 任意 OpenAI 兼容 Chat Completions 接口。 |
| MCP servers | Local or remote tool providers bridged into `ToolRegistry`. | 桥接进 `ToolRegistry` 的本地或远程工具服务。 |

Background tasks are managed by `BackgroundManager`. It starts commands outside the synchronous `bash` call path, records state and logs under `.runtime-tasks/`, and lets `BackgroundMiddleware` notify the next user turn when a task completes.

后台任务由 `BackgroundManager` 管理。它在同步 `bash` 路径之外启动命令，把状态和日志写入 `.runtime-tasks/`，并由 `BackgroundMiddleware` 在后续用户轮次提示任务完成情况。

## 12. Extension Guide / 扩展方式

| Extension | English | 中文 |
|-----------|---------|------|
| Add a tool | Create a handler, create an OpenAI function schema, and call `registry.register(...)` during session assembly. | 创建处理函数和 OpenAI function schema，并在会话组装时调用 `registry.register(...)`。 |
| Add middleware | Implement the needed `LoopMiddleware` hooks and append the instance to `AgentLoopConfig.middleware`. | 实现需要的 `LoopMiddleware` 钩子，并把实例加入 `AgentLoopConfig.middleware`。 |
| Add MCP support | Add a JSON MCP config or set `AICODE_MCP_CONFIG`, then let `register_mcp_tools` expose discovered tools. | 添加 JSON MCP 配置或设置 `AICODE_MCP_CONFIG`，再由 `register_mcp_tools` 暴露发现的工具。 |
| Add a subagent skill | Put a `SKILL.md` file under `skills/` and call `subagent_call` with that template when useful. | 在 `skills/` 下放置 `SKILL.md`，需要时通过 `subagent_call` 使用该模板。 |
| Change prompt behavior | Update `src/aicode/prompt/` sections or the project-level `CLAUDE.md` / `AGENTS.md` files. | 修改 `src/aicode/prompt/` 分段，或调整项目级 `CLAUDE.md` / `AGENTS.md`。 |

## 13. Tests And Maintenance / 测试与维护

The test suite uses pytest and mock model clients. It covers loop behavior, tool calls, permission decisions, context compaction, recovery, Markdown output, MCP bridging, background tasks, and task planning.

测试使用 pytest 和模拟模型客户端，覆盖主循环、工具调用、权限决策、上下文压缩、恢复、Markdown 输出、MCP 桥接、后台任务和任务规划。

```bash
pip install -e ".[dev]"
python -m pytest tests/ -q
```

Maintenance checklist:

维护时建议同步检查：

| Item | English | 中文 |
|------|---------|------|
| API and config | Update README and this report when config variables or model-call behavior changes. | 配置变量或模型调用行为变化时，同步更新 README 和本报告。 |
| Tool schemas | Keep tool schema text aligned with handler behavior. | 保持工具 schema 描述与处理函数行为一致。 |
| Middleware order | Recheck permission, hook, status, compaction, recovery, todo, and background ordering after runtime changes. | 运行时变更后，重新检查权限、Hook、状态、压缩、恢复、Todo 和后台任务中间件顺序。 |
| Terminal rendering | Add regression tests for tables, fenced code, CJK text, and streaming fragments. | 为表格、代码块、中文文本和流式片段补充回归测试。 |

## 14. Known Limits / 已知限制

| Limit | English | 中文 |
|-------|---------|------|
| Synchronous Bash | The normal `bash` tool waits for command completion. Use `background_run` for long-running servers, games, or GUI programs. | 普通 `bash` 工具会等待命令结束。长时间服务、游戏或 GUI 程序建议用 `background_run`。 |
| Markdown scope | The renderer handles common terminal Markdown, not every CommonMark edge case. | 渲染器覆盖常见终端 Markdown，不追求完整 CommonMark 边界情况。 |
| Terminal width | CJK wide and fullwidth characters are handled, but ambiguous-width characters still depend on terminal font and settings. | 中文等双宽字符已处理，但歧义宽度字符仍受终端字体和设置影响。 |
| Shell portability | The project is tested mainly around Unix-like shell behavior. Windows shell behavior may need extra review. | 项目主要按类 Unix shell 行为测试，Windows shell 行为仍需要额外检查。 |
