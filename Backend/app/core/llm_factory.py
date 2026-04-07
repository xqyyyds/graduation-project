import os
from dataclasses import dataclass

from langchain_openai import ChatOpenAI

from app.core.config import settings


@dataclass(frozen=True)
class LLMConfig:
    model: str
    base_url: str
    api_key: str


def _env(name: str, fallback: str = "") -> str:
    value = os.getenv(name, fallback)
    return value.strip() if isinstance(value, str) else value


def _legacy_config() -> LLMConfig:
    return LLMConfig(
        model=_env("LLM_MODEL", getattr(settings, "LLM_MODEL", "")),
        base_url=_env("LLM_BASE_URL", getattr(settings, "LLM_BASE_URL", "")),
        api_key=_env("ZHIPU_API_KEY", getattr(settings, "ZHIPU_API_KEY", "")),
    )


def resolve_llm_config() -> LLMConfig:
    """单模型模式下统一读取主模型配置。"""
    legacy = _legacy_config()
    return LLMConfig(
        model=_env("FAST_LLM_MODEL") or legacy.model,
        base_url=_env("FAST_LLM_BASE_URL") or legacy.base_url,
        api_key=_env("FAST_LLM_API_KEY") or legacy.api_key,
    )


def build_chat_openai(**kwargs) -> ChatOpenAI:
    config = resolve_llm_config()
    params = {
        "model": config.model,
        "openai_api_key": config.api_key,
        "openai_api_base": config.base_url,
        "temperature": 0,
        "timeout": 60,
        "max_retries": 1,
    }
    params.update(kwargs)
    return ChatOpenAI(**params)


def get_main_llm(**kwargs) -> ChatOpenAI:
    return build_chat_openai(**kwargs)
