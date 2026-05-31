"""
core/tools/schemas.py — OpenAI function calling 格式的工具 schema 定义

每个工具独立定义为一个函数，返回标准 dict。
ToolRegistry 在注册时调用这些函数获取 schema。
"""
from __future__ import annotations


def bash_schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Run a shell command in the current workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute."},
                },
                "required": ["command"],
            },
        },
    }


def read_file_schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read file contents, optionally limiting lines.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path from workspace root."},
                    "limit": {"type": "integer", "description": "Max lines to return."},
                },
                "required": ["path"],
            },
        },
    }


def write_file_schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write (overwrite) a file with the given content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    }


def edit_file_schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace the first occurrence of old_text with new_text in a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_text": {"type": "string"},
                    "new_text": {"type": "string"},
                },
                "required": ["path", "old_text", "new_text"],
            },
        },
    }


def todo_schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "todo",
            "description": (
                "Rewrite the current session plan for multi-step work. "
                "Keep exactly one step in_progress at a time."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "content": {"type": "string"},
                                "status": {
                                    "type": "string",
                                    "enum": ["pending", "in_progress", "completed"],
                                },
                                "active_form": {
                                    "type": "string",
                                    "description": "Present-continuous description when in_progress.",
                                },
                            },
                            "required": ["content", "status"],
                        },
                    },
                },
                "required": ["items"],
            },
        },
    }


def task_create_schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "task_create",
            "description": "Create a new persistent task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["subject"],
            },
        },
    }


def task_update_schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "task_update",
            "description": "Update a task's status, owner, or dependencies.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "integer"},
                    "status": {
                        "type": "string",
                        "enum": ["pending", "in_progress", "completed", "deleted"],
                    },
                    "owner": {"type": "string"},
                    "addBlockedBy": {"type": "array", "items": {"type": "integer"}},
                    "addBlocks": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["task_id"],
            },
        },
    }


def task_list_schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "task_list",
            "description": "List all tasks with status summary.",
            "parameters": {"type": "object", "properties": {}},
        },
    }


def task_get_schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "task_get",
            "description": "Get full details of a task by ID.",
            "parameters": {
                "type": "object",
                "properties": {"task_id": {"type": "integer"}},
                "required": ["task_id"],
            },
        },
    }


def background_run_schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "background_run",
            "description": (
                "Run a shell command in the workspace in a background thread. "
                "Returns immediately with a task id; use background_check to poll. "
                "Completion is also injected into the conversation when the task finishes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to run."},
                    "label": {
                        "type": "string",
                        "description": "Short label for task list (optional).",
                    },
                },
                "required": ["command"],
            },
        },
    }


def background_check_schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "background_check",
            "description": "Query one background task by id, or list all tasks if task_id omitted.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "Task id returned by background_run. Omit to list all.",
                    },
                },
            },
        },
    }


def background_cancel_schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "background_cancel",
            "description": "Request cancellation of a running background task (best-effort).",
            "parameters": {
                "type": "object",
                "properties": {"task_id": {"type": "string"}},
                "required": ["task_id"],
            },
        },
    }


def git_worktree_list_schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "git_worktree_list",
            "description": (
                "List git worktrees for the workspace repo (git worktree list). "
                "Returns paths and checked-out branches when available."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    }
