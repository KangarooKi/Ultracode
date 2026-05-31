"""
security/validator.py — Bash 命令安全校验器

对教学代码 s07 BashSecurityValidator 的直接移植，独立文件便于单独测试。
"""
from __future__ import annotations

import re


class BashSecurityValidator:
    """
    对 bash 命令做轻量正则扫描，识别高风险模式。

    严重级（直接 deny）: sudo、rm_rf
    警示级（升级为 ask）: shell_metachar、cmd_substitution、ifs_injection
    """

    VALIDATORS: list[tuple[str, str]] = [
        ("shell_metachar",   r"[;&|`]"),          # shell 元字符（管道/分号/反引号）
        ("sudo",             r"\bsudo\b"),          # 提权
        ("rm_rf",            r"\brm\s+(-[a-zA-Z]*f[a-zA-Z]*\s|--force\s)"),  # 强制删除
        ("cmd_substitution", r"\$\("),             # 命令替换
        ("ifs_injection",    r"\bIFS\s*="),         # IFS 注入
    ]

    SEVERE = frozenset({"sudo", "rm_rf"})

    def validate(self, command: str) -> list[tuple[str, str]]:
        """返回触发的 (validator_name, pattern) 列表；空列表表示通过。"""
        return [
            (name, pat)
            for name, pat in self.VALIDATORS
            if re.search(pat, command)
        ]

    def is_safe(self, command: str) -> bool:
        return not self.validate(command)

    def severity(self, command: str) -> str:
        """返回 'clean' | 'warn' | 'severe'。"""
        failures = self.validate(command)
        if not failures:
            return "clean"
        if any(name in self.SEVERE for name, _ in failures):
            return "severe"
        return "warn"

    def describe_failures(self, command: str) -> str:
        failures = self.validate(command)
        if not failures:
            return "No issues detected."
        parts = [f"{name}(pattern={pat!r})" for name, pat in failures]
        return "Security flags: " + ", ".join(parts)
