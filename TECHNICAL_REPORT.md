<p align="right">
English | <a href="TECHNICAL_REPORT.zh-CN.md">简体中文</a>
</p>

# UltraCode Technical Report

Version source: `pyproject.toml` (`0.1.0` at the time of writing)

This report documents the runtime architecture, code layout, Agent loop, middleware contract, tool execution path, permission model, terminal rendering, and extension points for UltraCode.

## 1. Overview

UltraCode is a single-process CLI coding agent. The user enters a prompt in the terminal, the CLI builds a system prompt and conversation state, the Agent loop calls an OpenAI-compatible Chat Completions API, and tool calls are dispatched back into the local workspace under permission checks.

The implementation has five main layers:

| Layer | Role |
|-------|------|
| CLI layer | Parses commands, runs REPL or one-shot mode, and renders terminal output. |
| Core runtime | Loads config, calls the model, owns the Agent loop, and parses tool calls. |
| Middleware layer | Adds permission checks, hooks, compaction, recovery, todo reminders, background notifications, and status output. |
| Tool layer | Registers and executes file tools, Bash, tasks, MCP, background tasks, worktree tools, and subagents. |
| Workspace layer | Reads and writes local project state, memory, task files, runtime logs, and project instructions. |

## 2. Design Goals

| Goal | Detail |
|------|--------|
| Terminal-first workflow | Keep coding, inspection, command execution, and review inside the terminal. |
| Open backend | Use any model provider that implements the OpenAI Chat Completions shape. |
| Composable runtime | Keep the Agent loop small and move optional behavior into middleware. |
| Controlled local actions | Gate writes, edits, Bash commands, and background actions through explicit rules. |
| Markdown-friendly CLI | Make model output readable in a terminal, especially tables and fenced code blocks. |

## 3. System Architecture

<p align="center">
  <img src="assets/ultracode_system_architecture.png" alt="UltraCode system architecture" width="960">
</p>

The diagram splits UltraCode into five runtime areas: terminal entry, Agent runtime, middleware, tool execution, and workspace or external services. The critical path is short: the model proposes a response or tool call; middleware can inspect the call; the registry dispatches the tool; the result goes back into the next model turn.

## 4. Runtime Flow

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

| Step | Description |
|------|-------------|
| 1 | `cli/main.py` selects REPL, one-shot run, task view, worktree view, or version output. |
| 2 | `cli/session.py` builds the shared runtime context for REPL and `run`. |
| 3 | `SystemPromptBuilder` combines core rules, tool schemas, project files, memories, skills, and dynamic context. |
| 4 | `run_agent_loop` calls the model and normalizes streaming and non-streaming responses into the same internal shape. |
| 5 | Tool calls pass through middleware before reaching `ToolRegistry.dispatch`. |
| 6 | Tool results are appended as `role=tool` messages and become input for the next turn. |
| 7 | The loop stops when the model returns a normal assistant reply or `max_turns` is reached. |

## 5. Module Map

| Path | Responsibility |
|------|----------------|
| `src/aicode/cli/` | CLI entry, REPL, session assembly, output formatting, theme. |
| `src/aicode/core/` | Agent loop, config, OpenAI client, wait hints, Markdown stream writer, tool base classes. |
| `src/aicode/core/tools/` | `ToolRegistry`, base file and Bash tools, OpenAI function schemas. |
| `src/aicode/prompt/` | System prompt builder and prompt sections. |
| `src/aicode/security/` | Permission manager, Bash validator, workspace trust. |
| `src/aicode/hooks/` | `.hooks.json` loading and hook middleware. |
| `src/aicode/context/` | Transcript handling, compaction state, compact middleware. |
| `src/aicode/recovery/` | Recovery config, retry policy, continuation middleware. |
| `src/aicode/planning/` | Session todos and persistent `.tasks/` graph. |
| `src/aicode/background/` | Background task manager, runtime task files, background tools. |
| `src/aicode/memory/` | Markdown memory loading and optional memory updates. |
| `src/aicode/mcp/` | MCP config loading, client routing, registry bridge. |
| `src/aicode/subagent/` | Subagent runner and `subagent_call` registration. |
| `src/aicode/worktrees/` | Git worktree inspection tool. |
| `tests/` | Unit tests for loop behavior, tools, permissions, rendering, context, MCP, recovery, and background tasks. |

## 6. Agent Loop

`src/aicode/core/loop.py` owns the runtime contract. `AgentLoopConfig` provides the model client, model name, registry, system prompt callback, middleware list, max token and turn limits, optional recovery config, and stream writer settings.

`LoopState` stores conversation messages, turn count, last stop reason, transition reason, and a metadata dictionary for middleware. Tool calls use the shared `ToolCall` type, and tool outputs use `ToolResult`.

| Concern | Implementation |
|---------|----------------|
| Non-streaming call | Calls `chat.completions.create(...)`, then parses assistant content, tool calls, and finish reason. |
| Streaming call | Accumulates content deltas and tool-call deltas, then returns the same structure as non-streaming mode. |
| Wait hint | Non-streaming mode can show a stderr wait hint. Streaming mode avoids the hint to prevent output interleaving. |
| Recovery | When recovery is enabled, model calls use the recovery path so compaction and retries can handle long prompts or transient errors. |
| Tool turn | Each tool result is appended to messages and can trigger another model turn. |

## 7. Middleware

Middleware lets optional behavior interpose around the Agent loop without copying the loop itself. The contract is defined in `src/aicode/core/loop.py`.

| Hook | When it runs | Typical use |
|------|--------------|-------------|
| `pre_turn` | Before a model turn begins. | Add notifications, status lines, recovery hints, or compacted context. |
| `pre_assistant_output` | Before the first streamed assistant token is printed. | Clear transient thinking UI. |
| `post_model` | After each model call finishes. | Clear temporary status, inspect finish reason. |
| `pre_tool` | Before a tool is dispatched. | Permission checks, hook blocking, safety review. |
| `post_tool` | After a tool returns. | Log results, update todo state, track files for compaction. |
| `post_turn` | After a loop turn completes. | Inject reminders, recovery continuations, background task notifications. |

The default session assembled by `build_repl_context` installs permission, hook, status printing, compaction, optional recovery, todo, and background middleware. Subagents receive a smaller permission and hook chain so they inherit local safety rules without sharing the entire parent UI pipeline.

## 8. Tool System

Tools are registered through `ToolRegistry.register(name, handler, schema)`. The registry exposes OpenAI-compatible function schemas to the model and dispatches selected tool calls to Python handlers.

| Tool group | Details |
|------------|---------|
| Base tools | `bash`, `read_file`, `write_file`, `edit_file` from `core/tools/base.py`. |
| Task tools | Persistent task graph tools backed by `.tasks/`. |
| Todo tool | Session-scoped todo updates used by the model during multi-step work. |
| Background tools | `background_run`, `background_check`, `background_cancel`. |
| MCP tools | Remote or local MCP tools registered with the `mcp__*` prefix. |
| Subagent tool | `subagent_call` starts an isolated child loop with selected tools and optional skill templates. |
| Worktree tool | `git_worktree_list` reports local git worktrees. |

`ToolResult.to_message()` converts a result into the OpenAI `role=tool` message shape. This keeps native tools, MCP tools, and intercepted permission results on the same path.

## 9. Security Model

UltraCode treats local tool execution as the main risk area. The safety design combines command validation, path isolation, permission modes, and preview before writes.

| Mechanism | Details |
|-----------|---------|
| Workspace path isolation | `safe_path` resolves file paths under the configured workdir and rejects escape attempts. |
| Bash validation | `BashSecurityValidator` scans for severe or warning-level patterns before permission rules run. |
| Read-only Bash auto approval | Clearly read-only commands such as `ls`, `rg`, `cat`, and safe `git` inspection commands can be allowed automatically. |
| Permission modes | `default` asks for unknown write actions, `plan` blocks writes, and `auto` allows known read-like actions. |
| Write previews | `write_file` and `edit_file` show content previews before the user approves a change. |
| Workspace trust | Hook execution depends on workspace trust checks. |

The permission path is implemented in `src/aicode/security/permission.py`: Bash validation, deny rules, mode-specific decisions, allow rules, and interactive fallback.

## 10. Terminal Output

The CLI renders assistant output with a lightweight Markdown pipeline rather than a full CommonMark parser. The goal is predictable terminal readability.

| Component | Details |
|-----------|---------|
| `markdown_terminal.py` | Formats headings, lists, quotes, inline code, links, horizontal rules, GFM tables, and fenced code blocks. |
| `AssistantMarkdownStreamWriter` | Buffers table and fence fragments during streaming so incomplete Markdown is not printed too early. |
| Table width | Uses `unicodedata.east_asian_width` for wide and fullwidth CJK characters. |
| Status UI | `PrintingMiddleware` shows transient thinking lines and concise tool progress lines. |
| Color policy | `AICODE_COLOR` can force color, and `NO_COLOR` disables ANSI output when not overridden. |

The renderer avoids broad Markdown features such as nested block parsing. Complex Markdown may still be printed as plain text when a terminal-friendly rendering would be ambiguous.

## 11. Workspace And External Services

UltraCode reads project context from the selected workspace and writes runtime state into a small set of local folders.

| Path or service | Details |
|-----------------|---------|
| `CLAUDE.md` / `AGENTS.md` | Project instructions injected into the system prompt. |
| `.memory/` | Markdown memories loaded by `MemoryManager`. |
| `.tasks/` | Persistent task graph used by task tools. |
| `.runtime-tasks/` | Background task state JSON and logs. |
| `skills/` | Optional subagent skill templates. |
| `.hooks.json` | Hook definitions, guarded by trust. |
| Model API | Any OpenAI-compatible Chat Completions endpoint. |
| MCP servers | Local or remote tool providers bridged into `ToolRegistry`. |

Background tasks are managed by `BackgroundManager`. It starts commands outside the synchronous `bash` call path, records state and logs under `.runtime-tasks/`, and lets `BackgroundMiddleware` notify the next user turn when a task completes.

## 12. Extension Guide

| Extension | Implementation path |
|-----------|---------------------|
| Add a tool | Create a handler, create an OpenAI function schema, and call `registry.register(...)` during session assembly. |
| Add middleware | Implement the needed `LoopMiddleware` hooks and append the instance to `AgentLoopConfig.middleware`. |
| Add MCP support | Add a JSON MCP config or set `AICODE_MCP_CONFIG`, then let `register_mcp_tools` expose discovered tools. |
| Add a subagent skill | Put a `SKILL.md` file under `skills/` and call `subagent_call` with that template when useful. |
| Change prompt behavior | Update `src/aicode/prompt/` sections or the project-level `CLAUDE.md` / `AGENTS.md` files. |

## 13. Tests And Maintenance

The test suite uses pytest and mock model clients. It covers loop behavior, tool calls, permission decisions, context compaction, recovery, Markdown output, MCP bridging, background tasks, and task planning.

```bash
pip install -e ".[dev]"
python -m pytest tests/ -q
```

Maintenance checklist:

| Item | What to check |
|------|---------------|
| API and config | Update README and this report when config variables or model-call behavior changes. |
| Tool schemas | Keep tool schema text aligned with handler behavior. |
| Middleware order | Recheck permission, hook, status, compaction, recovery, todo, and background ordering after runtime changes. |
| Terminal rendering | Add regression tests for tables, fenced code, CJK text, and streaming fragments. |

## 14. Known Limits

| Limit | Details |
|-------|---------|
| Synchronous Bash | The normal `bash` tool waits for command completion. Use `background_run` for long-running servers, games, or GUI programs. |
| Markdown scope | The renderer handles common terminal Markdown, not every CommonMark edge case. |
| Terminal width | CJK wide and fullwidth characters are handled, but ambiguous-width characters still depend on terminal font and settings. |
| Shell portability | The project is tested mainly around Unix-like shell behavior. Windows shell behavior may need extra review. |
