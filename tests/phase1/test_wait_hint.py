"""core/wait_hint.py — LLM 等待提示开关与上下文安全。"""
from __future__ import annotations

import sys

from aicode.core.wait_hint import llm_wait_context, wait_hint_enabled


def test_wait_hint_disabled_by_env(monkeypatch):
    monkeypatch.setenv("AICODE_NO_WAIT_HINT", "1")
    assert wait_hint_enabled() is False


def test_llm_wait_context_no_crash_when_disabled(monkeypatch):
    monkeypatch.setenv("AICODE_NO_WAIT_HINT", "1")
    with llm_wait_context():
        pass


def test_llm_wait_context_no_crash_non_tty(monkeypatch):
    monkeypatch.delenv("AICODE_NO_WAIT_HINT", raising=False)
    monkeypatch.setattr(sys.stderr, "isatty", lambda: False)
    with llm_wait_context():
        pass


def test_llm_wait_context_show_hint_false_no_spinner(monkeypatch):
    """流式场景关闭提示，避免与 stdout 交错（此处仅保证可安全进入/退出）。"""
    monkeypatch.delenv("AICODE_NO_WAIT_HINT", raising=False)
    monkeypatch.setattr(sys.stderr, "isatty", lambda: True)
    with llm_wait_context(show_hint=False):
        pass
