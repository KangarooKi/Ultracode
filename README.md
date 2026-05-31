<p align="center">
  <img src="assets/UltraCode_logo.png" alt="UltraCode logo" width="640">
</p>

# UltraCode

UltraCode is a local AI-assisted coding CLI inspired by Claude Code. It works inside a chosen workspace, talks to any OpenAI-compatible model API, and uses tool calling to read files, edit code, run commands, manage tasks, connect MCP servers, and keep project context.

<p align="center">
  <img src="assets/ultracode_demo.gif" alt="UltraCode CLI demo" width="760">
</p>

| Item | Details |
|------|---------|
| Package | `ultracode` |
| Source layout | `src/aicode/` |
| Python | `>=3.11` |
| CLI commands | `ultracode` / `ultra` / `aicode` |

---

## Features

- **Interactive REPL**: multi-turn sessions, in-session history, streaming output in TTYs, and terminal-friendly Markdown rendering.
- **One-shot runs**: `ultracode run "your request"` for scripts, automation, and CI-style usage.
- **Core tools**: `read_file`, `write_file`, `edit_file`, and `bash`, all scoped to the selected workspace.
- **Background tasks**: `background_run`, `background_check`, and `background_cancel` for long-running commands or GUI/game workflows.
- **Task planning**: persistent `.tasks/` plus session-level `todo` updates and reminders.
- **Memory**: Markdown memory files under `.memory/`, injected into the system prompt.
- **MCP support**: connect MCP servers and expose tools with the `mcp__*` prefix.
- **Subagents**: `subagent_call` with optional templates under `skills/`.
- **Permissions**: `default`, `plan`, and `auto` modes; write/edit tools show content previews before approval.
- **Recovery**: optional context compaction, retry/backoff, and continuation helpers.
- **Hooks**: `.hooks.json` support with workspace trust checks.
- **Context compaction**: large tool outputs can be written to disk and summarized when needed.

---

## Installation

```bash
cd /path/to/Ultracode   # repository root, containing pyproject.toml
pip install -e .
```

Runtime dependencies are listed in `pyproject.toml` (`openai`, `python-dotenv`). For development and tests:

```bash
pip install -e ".[dev]"
```

---

## Configuration

Create a `.env` file in the project/workspace, or provide the same values through environment variables. UltraCode loads `.env` with `python-dotenv` and does not overwrite variables that are already set.

| Variable | Meaning | Example / Default |
|----------|---------|-------------------|
| `LLM_API_KEY` or `OPENAI_API_KEY` | API key | Required |
| `LLM_MODEL` | Model name | Required |
| `LLM_BASE_URL` | OpenAI-compatible base URL | Optional; defaults to the official OpenAI endpoint |
| `LLM_MAX_TOKENS` / `AICODE_MAX_TOKENS` | Max tokens per turn | `8000` |
| `LLM_MAX_TURNS` / `AICODE_MAX_TURNS` | Max loop turns | `100` |
| `AICODE_STREAM` | Stream assistant text in TTY mode | `1` / `true` |
| `AICODE_ENABLE_RECOVERY` | Enable recovery middleware | Off by default |
| `AICODE_RECOVERY_MAX_RETRIES` | Max recovery retries | `3` |
| `AICODE_NO_WAIT_HINT` | Disable stderr wait hints | Set `1` to disable |
| `AICODE_BASH_TIMEOUT` | `bash` tool timeout, in seconds | `120` |
| `AICODE_COLOR` | Force CLI color on/off | `1` on, `0` off |
| `AICODE_AUTO_APPROVE_READONLY_BASH` | Auto-approve clearly read-only shell commands | `1` |
| `NO_COLOR` | Disable ANSI colors | Optional |

The workspace defaults to the current directory. Use `-C DIR` / `--cwd DIR` to choose another workspace.

---

## Usage

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

### REPL Commands

| Command | Action |
|---------|--------|
| `/help` | Show help |
| `/todo` `/tasks` `/tools` `/mcp` `/memories` | Inspect plans, tasks, tools, MCP status, and memories |
| `/mode default\|plan\|auto` | Change permission mode |
| `/rules` | Show permission rules |
| `/clear` | Clear the current session history |
| `/exit` | Quit |

---

## Workspace Files

| Path | Purpose |
|------|---------|
| `.tasks/` | Persistent task graph |
| `.memory/` | Markdown memories, including `MEMORY.md` |
| `.runtime-tasks/` | Background task state and logs |
| `skills/` | Subagent templates with `SKILL.md` |
| `CLAUDE.md` / `AGENTS.md` | Project rules injected into the system prompt |
| `.hooks.json` | Hook definitions, guarded by workspace trust |

---

## Development

```bash
pip install -e ".[dev]"
python -m pytest tests/ -q
```

The full architecture notes are in [TECHNICAL_REPORT.md](./TECHNICAL_REPORT.md).

---

## Notes

- **GUI apps and games**: the `bash` tool waits for commands to finish and may time out. Use `background_run` for long-running or windowed programs, or run them manually in a local terminal.
- **Safety**: in `default` mode, review permission prompts carefully before allowing writes or command execution. `write_file` and `edit_file` show previews before changes are applied.
