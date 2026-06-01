<p align="right">
<a href="README.md">English</a> | 简体中文
</p>

<p align="center">
  <img src="assets/UltraCode_logo.png" alt="UltraCode logo" width="640">
</p>

# UltraCode

UltraCode 是一个面向开发者的终端智能代码助手。它基于 OpenAI 兼容的 Chat Completions API 构建多轮 Agent 循环，通过统一工具注册表连接本地代码操作，并把写文件、执行命令、上下文压缩和后台任务放在可控的工作区规则之内。

<p align="center">
  <img src="assets/ultracode_demo.gif" alt="UltraCode CLI demo" width="760">
</p>

## 快速了解

| 项目 | 说明 |
|------|------|
| 包名 | `ultracode` |
| 源码布局 | `src/aicode/` |
| Python | `>=3.11` |
| 命令入口 | `ultracode`、`ultra`、`aicode` |
| 模型接口 | OpenAI 兼容 Chat Completions |
| 运行方式 | 支持工具调用的多轮 Agent 主循环 |

## 项目定位

UltraCode 更关注真实代码仓库里的终端工作流：读文件、改代码、跑命令、管理上下文，并在可能修改工作区时请求确认。交互体验参考 Claude Code 的核心方式，但模型后端可以切换到任意 OpenAI 兼容服务。

## 架构

<p align="center">
  <img src="assets/ultracode_system_architecture.png" alt="UltraCode system architecture" width="920">
</p>

核心架构由三部分组成：Agent 主循环、中间件管线和统一工具注册表。

```text
用户请求
  -> UltraCode CLI
  -> Agent 主循环
  -> 携带工具 schema 的 Chat Completions API 调用
  -> tool_calls
  -> 中间件检查
  -> ToolRegistry 分发
  -> 本地工具执行
  -> 工具结果
  -> 下一轮模型调用
```

| 层级 | 职责 |
|------|------|
| 终端层 | REPL、单次运行、斜杠命令和流式 Markdown 输出。 |
| 核心运行时 | 配置加载、系统提示构建、对话状态、模型调用和工具调用解析。 |
| 中间件 | 权限、Hook、压缩、恢复、Todo、后台通知和状态输出。 |
| 工具执行 | 文件工具、Bash、任务工具、记忆工具、后台任务、MCP 和子代理。 |
| 工作区与服务 | 本地仓库文件、`.tasks/`、`.memory/`、`.runtime-tasks/`、MCP 服务和模型接口。 |

## 功能

| 能力 | 说明 |
|------|------|
| 交互式会话 | 支持带历史记录的多轮 REPL 和助手流式输出。 |
| 单次运行 | `ultracode run "..."` 适合脚本化、快速检查和自动化。 |
| 本地工具 | 集成 `read_file`、`write_file`、`edit_file`、`bash`、任务工具、后台工具、MCP 工具和子代理。 |
| 权限模式 | 提供 `default`、`plan`、`auto` 三种模式，写入前展示预览。 |
| Bash 安全 | 提供 Bash 校验、只读命令自动放行和工作区范围审查。 |
| 上下文处理 | 支持记忆文件、项目规则、上下文压缩和异常恢复。 |
| 终端渲染 | 表格、代码块、行内代码、列表、引用和标题会在终端里做轻量渲染。 |

## 安装

```bash
cd /path/to/Ultracode
pip install -e .
```

开发环境安装：

```bash
pip install -e ".[dev]"
```

运行依赖见 [pyproject.toml](./pyproject.toml)。

## 配置

可以在项目目录或工作区目录放置 `.env`，也可以直接使用环境变量。UltraCode 会加载 `.env`，但不会覆盖已经存在的环境变量。

| 变量 | 说明 |
|------|------|
| `LLM_API_KEY` 或 `OPENAI_API_KEY` | API 密钥，必填。 |
| `LLM_MODEL` | 模型名称，必填。 |
| `LLM_BASE_URL` | OpenAI 兼容接口地址。 |
| `LLM_MAX_TOKENS` / `AICODE_MAX_TOKENS` | 每轮最大 token，默认 `8000`。 |
| `LLM_MAX_TURNS` / `AICODE_MAX_TURNS` | Agent 最大循环轮数，默认 `100`。 |
| `AICODE_STREAM` | TTY 下启用助手流式输出，默认开启。 |
| `AICODE_ENABLE_RECOVERY` | 启用异常恢复中间件。 |
| `AICODE_RECOVERY_MAX_RETRIES` | 最大恢复重试次数，默认 `3`。 |
| `AICODE_COMPACT_AUTO_THRESHOLD` | 自动上下文压缩阈值。 |
| `AICODE_BASH_TIMEOUT` | Bash 工具超时时间，默认 `120` 秒。 |
| `AICODE_AUTO_APPROVE_READONLY_BASH` | 自动放行明确只读的 shell 命令，默认 `1`。 |
| `AICODE_MCP_CONFIG` | MCP JSON 配置文件路径。 |
| `AICODE_NO_WAIT_HINT` | 关闭非流式等待提示。 |
| `AICODE_COLOR` | 用 `1` 或 `0` 强制开启或关闭颜色。 |
| `NO_COLOR` | 设置后禁用 ANSI 颜色。 |

工作区默认是当前目录。可以用 `-C DIR` 或 `--cwd DIR` 指定其他工作区。

## 使用

```bash
# 交互模式
ultracode
ultracode repl
ultracode -C /path/to/project

# 单次请求
ultracode run "Summarize this repository structure"
ultracode run -v "Inspect the codebase and suggest the next cleanup step"

# 从 stdin 读取 prompt
echo "Summarize main.py" | ultracode run -

# 不需要 API key 的命令
ultracode tasks
ultracode worktrees

ultracode --version
```

## REPL 命令

| 命令 | 作用 |
|------|------|
| `/help` | 查看帮助。 |
| `/todo` | 查看当前会话计划。 |
| `/tasks` | 查看持久化任务。 |
| `/tools` | 查看已注册工具。 |
| `/mcp` | 查看 MCP 状态。 |
| `/memories` | 查看已加载记忆。 |
| `/mode default\|plan\|auto` | 切换权限模式。 |
| `/rules` | 查看权限规则。 |
| `/clear` | 清空当前会话历史。 |
| `/exit` | 退出。 |

## 工作区文件

| 路径 | 用途 |
|------|------|
| `.tasks/` | 持久化任务图。 |
| `.memory/` | Markdown 记忆文件，包括 `MEMORY.md`。 |
| `.runtime-tasks/` | 后台任务状态与日志。 |
| `skills/` | 包含 `SKILL.md` 的子代理模板。 |
| `CLAUDE.md` / `AGENTS.md` | 注入系统提示的项目规则。 |
| `.hooks.json` | Hook 配置，受工作区信任机制保护。 |

## 扩展

| 扩展点 | 添加方式 |
|--------|----------|
| 新工具 | 通过 `ToolRegistry.register(...)` 注册处理函数和 schema。 |
| 新中间件 | 实现 Agent 主循环使用的 `LoopMiddleware` 方法。 |
| MCP 工具 | 添加 MCP 服务配置后，以 `mcp__*` 命名方式暴露工具。 |
| 子代理技能 | 在 `skills/` 下添加 `SKILL.md` 模板。 |

## 技术报告

完整架构说明见 [TECHNICAL_REPORT.zh-CN.md](./TECHNICAL_REPORT.zh-CN.md)。

## 开发

```bash
pip install -e ".[dev]"
python -m pytest tests/ -q
```

## 说明

| 主题 | 说明 |
|------|------|
| GUI 应用和游戏 | `bash` 工具会等待命令结束。长时间运行或带窗口的程序建议使用 `background_run`，也可以在本机终端手动运行。 |
| 安全 | 在 `default` 模式下，执行写文件或命令前请确认权限提示。`write_file` 和 `edit_file` 会在真正修改前展示内容预览。 |
