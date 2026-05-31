"""
core/client.py — LLM 客户端工厂

封装 OpenAI 兼容客户端，支持依赖注入（测试可替换）。
"""
from __future__ import annotations

from openai import OpenAI

from .config import get_config

_client: OpenAI | None = None


def get_client() -> OpenAI:
    """返回全局单例客户端（懒加载）。"""
    global _client
    if _client is not None:
        return _client
    cfg = get_config()
    kwargs: dict = {"api_key": cfg.api_key}
    if cfg.base_url:
        kwargs["base_url"] = cfg.base_url
    _client = OpenAI(**kwargs)
    return _client


def build_client(api_key: str, base_url: str | None = None) -> OpenAI:
    """构造一个独立客户端（不影响全局单例，用于子 Agent 或测试）。"""
    kwargs: dict = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs)


def reset_client() -> None:
    """测试专用：清除缓存的客户端单例。"""
    global _client
    _client = None
