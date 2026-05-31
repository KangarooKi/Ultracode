"""环境变量对 Config 的覆盖（需 reset_config 隔离）。"""
from __future__ import annotations

from pathlib import Path

import pytest

from aicode.core import config as config_mod


@pytest.fixture(autouse=True)
def _reset_config():
    config_mod.reset_config()
    yield
    config_mod.reset_config()


def test_config_env_max_tokens_and_turns(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_MODEL", "m")
    monkeypatch.setenv("LLM_MAX_TOKENS", "4096")
    monkeypatch.setenv("AICODE_MAX_TOKENS", "2048")  # LLM_ 优先
    monkeypatch.setenv("AICODE_MAX_TURNS", "50")
    c = config_mod.get_config(tmp_path)
    assert c.max_tokens == 4096
    assert c.max_turns == 50


def test_config_aicode_max_tokens_fallback(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_MODEL", "m")
    monkeypatch.delenv("LLM_MAX_TOKENS", raising=False)
    monkeypatch.setenv("AICODE_MAX_TOKENS", "6000")
    c = config_mod.get_config(tmp_path)
    assert c.max_tokens == 6000


def test_config_recovery_flags(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_MODEL", "m")
    monkeypatch.setenv("AICODE_ENABLE_RECOVERY", "true")
    monkeypatch.setenv("AICODE_RECOVERY_MAX_RETRIES", "5")
    c = config_mod.get_config(tmp_path)
    assert c.recovery_enabled is True
    assert c.recovery_max_retries == 5


def test_config_invalid_int_uses_default(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_MODEL", "m")
    monkeypatch.setenv("LLM_MAX_TOKENS", "not-a-number")
    c = config_mod.get_config(tmp_path)
    assert c.max_tokens == 8000


def test_config_loads_env_from_explicit_workdir(monkeypatch, tmp_path: Path):
    for name in (
        "LLM_API_KEY",
        "OPENAI_API_KEY",
        "LLM_MODEL",
        "LLM_BASE_URL",
        "LLM_MAX_TOKENS",
        "AICODE_MAX_TOKENS",
    ):
        monkeypatch.delenv(name, raising=False)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "LLM_API_KEY=from-workdir",
                "LLM_MODEL=workdir-model",
                "LLM_BASE_URL=https://example.test/v1",
                "AICODE_MAX_TOKENS=1234",
            ]
        ),
        encoding="utf-8",
    )

    c = config_mod.get_config(tmp_path)

    assert c.api_key == "from-workdir"
    assert c.model == "workdir-model"
    assert c.base_url == "https://example.test/v1"
    assert c.max_tokens == 1234
