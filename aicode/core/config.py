"""
core/config.py — 配置加载

从 .env 或环境变量读取所有运行时配置，统一在此校验。
其他模块通过 get_config() 获取，不直接读取 os.getenv。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# 优先加载项目根目录的 .env（允许用户在工作目录旁放置 .env）
load_dotenv(override=False)


def _env_int(name: str, default: int, *, min_v: int = 1, max_v: int = 2_000_000) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        v = int(str(raw).strip(), 10)
    except ValueError:
        return default
    return max(min_v, min(max_v, v))


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Config:
    """
    recovery_enabled / recovery_max_retries：见环境变量 AICODE_ENABLE_RECOVERY、
    AICODE_RECOVERY_MAX_RETRIES；启用后挂载 RecoveryMiddleware 与 AgentLoopConfig.recovery。
    """

    api_key: str
    model: str
    base_url: str | None
    workdir: Path
    max_tokens: int = 8000
    max_turns: int = 100
    recovery_enabled: bool = False
    recovery_max_retries: int = 3
    # 交互式 CLI 下将 LLM 回复流式打到 stdout（见 AICODE_STREAM）
    stream_llm: bool = True


_config: Config | None = None


def get_config(workdir: Path | None = None) -> Config:
    """
    返回全局配置单例。仅在首次调用时从环境变量初始化。

    workdir 仅在首次初始化时生效；后续调用忽略该参数，仍返回已缓存的实例。
    未传 workdir 时使用当前进程的工作目录（Path.cwd()）。
    """
    global _config
    if _config is not None:
        return _config

    wd = Path(workdir).resolve() if workdir is not None else Path.cwd().resolve()
    load_dotenv(wd / ".env", override=False)

    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY", "")
    model = os.getenv("LLM_MODEL", "")
    base_url = os.getenv("LLM_BASE_URL") or None

    if not api_key:
        raise RuntimeError(
            "缺少 LLM_API_KEY。请在 .env 文件或环境变量中设置。"
        )
    if not model:
        raise RuntimeError(
            "缺少 LLM_MODEL。请在 .env 文件或环境变量中设置。"
        )

    max_tokens = _env_int("LLM_MAX_TOKENS", _env_int("AICODE_MAX_TOKENS", 8000))
    max_turns = _env_int("LLM_MAX_TURNS", _env_int("AICODE_MAX_TURNS", 100), max_v=1_000_000)
    recovery_enabled = _env_bool("AICODE_ENABLE_RECOVERY", False)
    recovery_max_retries = _env_int("AICODE_RECOVERY_MAX_RETRIES", 3, min_v=0, max_v=50)
    stream_llm = _env_bool("AICODE_STREAM", True)

    _config = Config(
        api_key=api_key,
        model=model,
        base_url=base_url,
        workdir=wd,
        max_tokens=max_tokens,
        max_turns=max_turns,
        recovery_enabled=recovery_enabled,
        recovery_max_retries=recovery_max_retries,
        stream_llm=stream_llm,
    )
    return _config


def reset_config() -> None:
    """测试专用：清除缓存的配置单例。"""
    global _config
    _config = None
