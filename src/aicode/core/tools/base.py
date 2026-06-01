"""
core/tools/base.py — 四个基础工具实现

bash / read_file / write_file / edit_file
safe_path() 保证所有文件操作不逃出工作目录。
"""
from __future__ import annotations

import os
import subprocess
import sys
import locale
from pathlib import Path

# 默认工作目录用于未显式传入 workdir 的工具调用。
WORKDIR: Path = Path.cwd().resolve()

# 慢速工具（写磁盘/子进程），调用方可据此加延迟
SLOW_TOOLS: frozenset[str] = frozenset({"bash", "write_file", "edit_file"})

# 基础 Bash 拦截只处理显而易见的高风险片段；完整审查在 permission 模块中完成。
_DANGEROUS = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]


def _decode_shell_output(data: bytes) -> str:
    """Decode subprocess stdout/stderr with UTF-8 first and locale fallbacks."""
    if not data:
        return ""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass

    candidates = [
        locale.getpreferredencoding(False),
        sys.getfilesystemencoding(),
        "gbk",
        "cp936",
    ]
    seen: set[str] = set()
    best = data.decode("utf-8", errors="replace")
    best_bad = best.count("\ufffd")

    for enc in candidates:
        if not enc:
            continue
        key = enc.lower()
        if key in seen or key in {"utf-8", "utf8"}:
            continue
        seen.add(key)
        try:
            text = data.decode(enc, errors="replace")
        except (LookupError, UnicodeDecodeError):
            continue
        bad = text.count("\ufffd")
        if bad < best_bad:
            best = text
            best_bad = bad
            if best_bad == 0:
                break

    return best


def safe_path(path_str: str, workdir: Path | None = None) -> Path:
    """将相对/绝对路径解析到工作目录内，路径逃逸时抛 ValueError。"""
    base = workdir or WORKDIR
    resolved = (base / path_str).resolve()
    if not resolved.is_relative_to(base):
        raise ValueError(f"Path escapes workspace: {path_str!r}")
    return resolved


def _bash_timeout_s() -> int:
    try:
        return max(5, min(600, int(os.environ.get("AICODE_BASH_TIMEOUT", "120"))))
    except ValueError:
        return 120


def run_bash(command: str, workdir: Path | None = None) -> str:
    if any(d in command for d in _DANGEROUS):
        return "Error: Dangerous command blocked."
    cwd = workdir or WORKDIR
    try:
        r = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=False,
            timeout=_bash_timeout_s(),
        )
        blob = (r.stdout or b"") + (r.stderr or b"")
        out = _decode_shell_output(blob).strip()
        return out[:50000] if out else "(no output)"
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out ({_bash_timeout_s()}s)."
    except (FileNotFoundError, OSError) as exc:
        return f"Error: {exc}"


def run_read(path: str, limit: int | None = None, workdir: Path | None = None) -> str:
    try:
        fp = safe_path(path, workdir)
        lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"... ({len(lines) - limit} more lines)"]
        return "\n".join(lines)[:50000]
    except Exception as exc:
        return f"Error: {exc}"


def run_write(path: str, content: str, workdir: Path | None = None) -> str:
    try:
        fp = safe_path(path, workdir)
        fp.parent.mkdir(parents=True, exist_ok=True)
        with fp.open("w", encoding="utf-8", newline="") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as exc:
        return f"Error: {exc}"


def run_edit(path: str, old_text: str, new_text: str, workdir: Path | None = None) -> str:
    try:
        fp = safe_path(path, workdir)
        content = fp.read_text(encoding="utf-8", errors="replace")
        if old_text not in content:
            return f"Error: Text not found in {path}"
        new_content = content.replace(old_text, new_text, 1)
        with fp.open("w", encoding="utf-8", newline="") as f:
            f.write(new_content)
            f.flush()
            os.fsync(f.fileno())
        return f"Edited {path}"
    except Exception as exc:
        return f"Error: {exc}"
