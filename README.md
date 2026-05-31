<p align="center">
  <img src="assets/UltraCode_logo.png" alt="UltraCode logo" width="420">
</p>

# UltraCode

类 **Claude Code** 风格的本地 **AI 辅助编程 CLI**：在指定工作区内通过 OpenAI 兼容 API 调用大模型，使用 **工具调用（function calling）** 完成读文件、写文件、执行命令、任务规划、MCP 集成等操作。

<p align="center">
  <img src="assets/ultracode_demo.gif" alt="UltraCode CLI demo" width="760">
</p>

| 项目 | 说明 |
|------|------|
| PyPI/包名 | `ultracode`（源码目录为 `src/aicode/`） |
| Python | ≥ 3.11 |
| 入口命令 | `ultracode` / `ultra` / `aicode` |

---

## 功能概览

- **交互式 REPL**：多轮对话、会话内历史、流式输出（TTY 下）、Markdown 友好终端渲染（标题、列表、粗体、GFM 表格对齐等）。
- **单次执行**：`ultracode run "你的需求"`，适合脚本或 CI。
- **基础工具**：`read_file`、`write_file`、`edit_file`、`bash`（工作区路径约束 + 危险命令拦截）。
- **后台任务**：`background_run` / `background_check` / `background_cancel`（适合长时间命令或带窗口的 GUI 程序）。
- **任务与待办**：持久化 `.tasks/`、`task_*` 工具；会话内 `todo` 与 `TodoMiddleware` 提醒。
- **记忆**：`.memory/` 下 Markdown 记忆文件，注入系统提示。
- **MCP**：通过配置连接 MCP 服务器，工具以 `mcp__*` 前缀注册。
- **子代理**：`subagent_call`，可选 `skills/` 下模板。
- **权限**：`default` / `plan` / `auto` 模式；`write_file` / `edit_file` 确认前展示**内容预览**。
- **可选恢复**：上下文过长压缩、网络退避（环境变量控制）。
- **钩子**：`.hooks.json` + 工作区信任标记。
- **上下文压缩**：大工具输出落盘、micro-compact、可选 LLM 摘要（CompactMiddleware）。

---

## 安装

```bash
cd /path/to/Ultracode   # 本仓库根目录（含 pyproject.toml）
pip install -e .
```

运行依赖见 `pyproject.toml`（`openai`、`python-dotenv`）。如果要运行测试或参与开发：

```bash
pip install -e ".[dev]"
```

---

## 配置

在项目或通过 `-C DIR` 指定的工作区使用 **`.env`**（或通过环境变量）。首次运行会由 `python-dotenv` 加载（不覆盖已存在的环境变量）。

| 变量 | 含义 | 示例/默认 |
|------|------|-----------|
| `LLM_API_KEY` 或 `OPENAI_API_KEY` | API 密钥 | 必填 |
| `LLM_MODEL` | 模型名 | 必填 |
| `LLM_BASE_URL` | 兼容 OpenAI 的 Base URL | 可选，默认官方 |
| `LLM_MAX_TOKENS` / `AICODE_MAX_TOKENS` | 每轮 max_tokens | 默认 8000 |
| `LLM_MAX_TURNS` / `AICODE_MAX_TURNS` | 最大对话轮次上限 | 默认 100 |
| `AICODE_STREAM` | 是否在 TTY 上流式输出助手正文 | 默认 `1`/`true` |
| `AICODE_ENABLE_RECOVERY` | 是否启用恢复中间件与循环内 recovery | 默认关 |
| `AICODE_RECOVERY_MAX_RETRIES` | recovery 最大重试 | 默认 3 |
| `AICODE_NO_WAIT_HINT` | 关闭 LLM 等待时的 stderr 轮换提示 | `1` 关闭 |
| `AICODE_BASH_TIMEOUT` | `bash` 工具子进程超时（秒） | 默认 120；测试可能设更短 |
| `AICODE_COLOR` | 强制开启/关闭 CLI 颜色 | `1` 开启，`0` 关闭 |
| `AICODE_AUTO_APPROVE_READONLY_BASH` | 自动放行明确只读的 bash 命令 | 默认 `1` |
| `NO_COLOR` | 禁用 ANSI 颜色（含流式 Markdown 粗体等） | 可选 |

工作区根目录默认 **`cwd`**，可用 `-C DIR` 指定。

---

## 使用方式

```bash
# 交互式（默认）
ultracode
ultracode repl
ultracode -C D:\myproject

# 单次提问
ultracode run 用一句话说明当前目录结构
ultracode run -v "带工具摘要的详细任务"

# 从管道读入用户消息
echo 总结 main.py | ultracode run -

# 无需 API 的子命令
ultracode tasks
ultracode worktrees

ultracode --version
```

### REPL 内命令（以 `/` 开头）

| 命令 | 作用 |
|------|------|
| `/help` | 帮助 |
| `/todo` `/tasks` `/tools` `/mcp` `/memories` | 查看计划、任务、工具、MCP、记忆 |
| `/mode default\|plan\|auto` | 权限模式 |
| `/rules` | 权限规则列表 |
| `/clear` | 清空本会话历史 |
| `/exit` | 退出 |

---

## 工作区常见路径

| 路径 | 用途 |
|------|------|
| `.tasks/` | 持久化任务图 |
| `.memory/` | 记忆 Markdown（含索引 `MEMORY.md`） |
| `.runtime-tasks/` | 后台任务状态与日志 |
| `skills/` | 子代理模板（含 `SKILL.md`） |
| `CLAUDE.md` / `AGENTS.md` | 项目与用户规则，注入系统提示 |
| `.hooks.json` | 钩子定义（需配合信任标记） |

---

## 开发与测试

```bash
pip install -e ".[dev]"
# 建议在干净环境下运行；若本机全局 pytest 插件拖慢/卡住，项目已配置禁用部分插件
python -m pytest tests/ -q
```

更完整的架构说明见 **[TECHNICAL_REPORT.md](./TECHNICAL_REPORT.md)**。

---

## 说明

- **GUI / 游戏**：`bash` 会等待进程结束且可能超时；长时间或带窗口的程序请用 **`background_run`**，或在本机终端手动运行。
- **安全**：涉及写盘、执行命令时请在 **`default`** 模式下仔细阅读确认提示与 **`write_file` 内容预览**。
