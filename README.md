<p align="center">
  <img src="assets/UltraCode_logo.png" alt="UltraCode logo" width="640">
</p>

# UltraCode

UltraCode is a terminal-first coding agent for developers. It runs a multi-turn Agent loop on top of OpenAI-compatible Chat Completions APIs, connects the model to local tools through a unified registry, and keeps file writes, shell commands, context compaction, and background tasks under explicit workspace rules.

UltraCode 是一个面向开发者的终端智能代码助手。它基于 OpenAI 兼容的 Chat Completions API 构建多轮 Agent 循环，通过统一工具注册表连接本地代码操作，并把写文件、执行命令、上下文压缩和后台任务放在可控的工作区规则之内。

<p align="center">
  <img src="assets/ultracode_demo.gif" alt="UltraCode CLI demo" width="760">
</p>

## Quick View / 快速了解

| Item | English | 中文 |
|------|---------|------|
| Package | `ultracode` | Python 包名为 `ultracode` |
| Source layout | `src/aicode/` | 源码采用 `src/aicode/` 布局 |
| Python | `>=3.11` | 需要 Python 3.11 或更高版本 |
| CLI commands | `ultracode`, `ultra`, `aicode` | 提供三个命令入口 |
| Model API | OpenAI-compatible Chat Completions | 兼容 OpenAI Chat Completions 格式 |
| Main loop | Agent loop with tool calls | 支持工具调用的多轮 Agent 主循环 |

## Why UltraCode / 项目定位

UltraCode focuses on the part of AI coding that happens inside a real repository: reading files, editing code, running commands, tracking context, and asking for permission when an action can change the workspace. The interaction model follows the familiar Claude Code style, while the backend remains open to any OpenAI-compatible model service.

UltraCode 更关注真实代码仓库里的终端工作流：读文件、改代码、跑命令、管理上下文，并在可能修改工作区时请求确认。交互体验参考 Claude Code 的核心方式，但模型后端可以切换到任意 OpenAI 兼容服务。

## Architecture / 架构

<p align="center">
  <img src="assets/ultracode_system_architecture.png" alt="UltraCode system architecture" width="920">
</p>

The core architecture is built around three pieces: the Agent loop, the middleware pipeline, and the tool registry.

核心架构由三部分组成：Agent 主循环、中间件管线和统一工具注册表。

```text
User prompt
  -> UltraCode CLI
  -> Agent loop
  -> Chat Completions API with tool schemas
  -> tool_calls
  -> middleware checks
  -> ToolRegistry dispatch
  -> local tool execution
  -> tool result
  -> next model turn
```

| Layer | English | 中文 |
|-------|---------|------|
| Terminal layer | REPL mode, one-shot run mode, slash commands, streaming Markdown output. | REPL、单次运行、斜杠命令和流式 Markdown 输出。 |
| Core runtime | Config loading, system prompt building, conversation state, model calls, tool-call parsing. | 配置加载、系统提示构建、对话状态、模型调用和工具调用解析。 |
| Middleware | Permission, hooks, compaction, recovery, todos, background notifications, status printing. | 权限、Hook、压缩、恢复、Todo、后台通知和状态输出。 |
| Tool execution | File tools, Bash, task tools, memory tools, background tasks, MCP tools, subagents. | 文件工具、Bash、任务工具、记忆工具、后台任务、MCP 和子代理。 |
| Workspace and services | Local repository files, `.tasks/`, `.memory/`, `.runtime-tasks/`, MCP servers, model APIs. | 本地仓库文件、任务、记忆、后台日志、MCP 服务和模型接口。 |

## Features / 功能

| Capability | English | 中文 |
|------------|---------|------|
| Interactive sessions | Multi-turn REPL with session history and streaming assistant output. | 支持带历史记录的多轮 REPL 和助手流式输出。 |
| One-shot runs | `ultracode run "..."` for scripts, quick checks, and automation. | 支持单次请求，适合脚本化和快速检查。 |
| Local tools | `read_file`, `write_file`, `edit_file`, `bash`, task tools, background tools, MCP tools, and subagents. | 集成文件、命令、任务、后台任务、MCP 和子代理工具。 |
| Permission modes | `default`, `plan`, and `auto`, with write/edit previews before approval. | 提供 `default`、`plan`、`auto` 三种权限模式，写入前展示预览。 |
| Safer Bash | Bash validation, read-only auto approval, and workspace-aware command review. | 提供 Bash 校验、只读命令自动放行和工作区范围审查。 |
| Context handling | Memory files, project rules, transcript compaction, and recovery retries. | 支持记忆文件、项目规则、上下文压缩和异常恢复。 |
| Terminal rendering | Tables, fenced code blocks, inline code, lists, quotes, and headings render cleanly in the CLI. | 表格、代码块、行内代码、列表、引用和标题会在终端里做轻量渲染。 |

## Installation / 安装

```bash
cd /path/to/Ultracode
pip install -e .
```

For development:

开发环境安装：

```bash
pip install -e ".[dev]"
```

Runtime dependencies are listed in [pyproject.toml](./pyproject.toml).

运行依赖见 [pyproject.toml](./pyproject.toml)。

## Configuration / 配置

Create a `.env` file in the project or workspace, or provide the same values through environment variables. UltraCode loads `.env` without overwriting variables that are already set.

可以在项目目录或工作区目录放置 `.env`，也可以直接使用环境变量。UltraCode 会加载 `.env`，但不会覆盖已经存在的环境变量。

| Variable | English | 中文 |
|----------|---------|------|
| `LLM_API_KEY` or `OPENAI_API_KEY` | API key, required. | API 密钥，必填。 |
| `LLM_MODEL` | Model name, required. | 模型名称，必填。 |
| `LLM_BASE_URL` | OpenAI-compatible base URL. | OpenAI 兼容接口地址。 |
| `LLM_MAX_TOKENS` / `AICODE_MAX_TOKENS` | Max tokens per model turn, default `8000`. | 每轮最大 token，默认 `8000`。 |
| `LLM_MAX_TURNS` / `AICODE_MAX_TURNS` | Max Agent loop turns, default `100`. | Agent 最大循环轮数，默认 `100`。 |
| `AICODE_STREAM` | Stream assistant output in TTY mode, default on. | TTY 下启用助手流式输出，默认开启。 |
| `AICODE_ENABLE_RECOVERY` | Enable recovery middleware. | 启用异常恢复中间件。 |
| `AICODE_RECOVERY_MAX_RETRIES` | Max recovery retries, default `3`. | 最大恢复重试次数，默认 `3`。 |
| `AICODE_COMPACT_AUTO_THRESHOLD` | Threshold for automatic context compaction. | 自动上下文压缩阈值。 |
| `AICODE_BASH_TIMEOUT` | Bash tool timeout in seconds, default `120`. | Bash 工具超时时间，默认 `120` 秒。 |
| `AICODE_AUTO_APPROVE_READONLY_BASH` | Auto-approve clearly read-only shell commands, default `1`. | 自动放行明确只读的 shell 命令，默认 `1`。 |
| `AICODE_MCP_CONFIG` | Path to an MCP JSON config file. | MCP JSON 配置文件路径。 |
| `AICODE_NO_WAIT_HINT` | Disable the non-streaming wait hint. | 关闭非流式等待提示。 |
| `AICODE_COLOR` | Force color on or off with `1` or `0`. | 用 `1` 或 `0` 强制开启或关闭颜色。 |
| `NO_COLOR` | Disable ANSI colors when set. | 设置后禁用 ANSI 颜色。 |

The workspace defaults to the current directory. Use `-C DIR` or `--cwd DIR` to choose another workspace.

工作区默认是当前目录。可以用 `-C DIR` 或 `--cwd DIR` 指定其他工作区。

## Usage / 使用

```bash
# Interactive mode
ultracode
ultracode repl
ultracode -C /path/to/project

# One-shot request
ultracode run "Summarize this repository structure"
ultracode run -v "Inspect the codebase and suggest the next cleanup step"

# Read a prompt from stdin
echo "Summarize main.py" | ultracode run -

# Commands that do not require an API key
ultracode tasks
ultracode worktrees

ultracode --version
```

## REPL Commands / REPL 命令

| Command | English | 中文 |
|---------|---------|------|
| `/help` | Show help. | 查看帮助。 |
| `/todo` | Show session todos. | 查看当前会话计划。 |
| `/tasks` | Show persistent tasks. | 查看持久化任务。 |
| `/tools` | List registered tools. | 查看已注册工具。 |
| `/mcp` | Show MCP status. | 查看 MCP 状态。 |
| `/memories` | Show loaded memories. | 查看已加载记忆。 |
| `/mode default\|plan\|auto` | Change permission mode. | 切换权限模式。 |
| `/rules` | Show permission rules. | 查看权限规则。 |
| `/clear` | Clear session history. | 清空当前会话历史。 |
| `/exit` | Quit. | 退出。 |

## Workspace Files / 工作区文件

| Path | English | 中文 |
|------|---------|------|
| `.tasks/` | Persistent task graph. | 持久化任务图。 |
| `.memory/` | Markdown memories, including `MEMORY.md`. | Markdown 记忆文件。 |
| `.runtime-tasks/` | Background task state and logs. | 后台任务状态与日志。 |
| `skills/` | Subagent templates with `SKILL.md`. | 子代理技能模板。 |
| `CLAUDE.md` / `AGENTS.md` | Project rules injected into the system prompt. | 注入系统提示的项目规则。 |
| `.hooks.json` | Hook definitions, guarded by workspace trust. | Hook 配置，受工作区信任机制保护。 |

## Extending / 扩展

| Extension point | English | 中文 |
|-----------------|---------|------|
| New tool | Register a handler and schema with `ToolRegistry.register(...)`. | 通过 `ToolRegistry.register(...)` 注册处理函数和 schema。 |
| New middleware | Implement the `LoopMiddleware` methods used by the Agent loop. | 实现 Agent 主循环使用的 `LoopMiddleware` 方法。 |
| MCP tools | Add MCP server config and expose tools through the `mcp__*` naming pattern. | 添加 MCP 服务配置后，以 `mcp__*` 命名方式暴露工具。 |
| Subagent skill | Add a `SKILL.md` template under `skills/`. | 在 `skills/` 下添加 `SKILL.md` 子代理模板。 |

## Technical Report / 技术报告

Read the full architecture notes in [TECHNICAL_REPORT.md](./TECHNICAL_REPORT.md).

完整架构说明见 [TECHNICAL_REPORT.md](./TECHNICAL_REPORT.md)。

## Development / 开发

```bash
pip install -e ".[dev]"
python -m pytest tests/ -q
```

## Notes / 说明

| Topic | English | 中文 |
|-------|---------|------|
| GUI apps and games | The `bash` tool waits for commands to finish. Use `background_run` for long-running or windowed programs, or run them manually in a local terminal. | `bash` 工具会等待命令结束。长时间运行或带窗口的程序建议使用 `background_run`，也可以在本机终端手动运行。 |
| Safety | In `default` mode, review permission prompts before allowing writes or command execution. `write_file` and `edit_file` show previews before changes are applied. | 在 `default` 模式下，执行写文件或命令前请确认权限提示。`write_file` 和 `edit_file` 会在真正修改前展示内容预览。 |
