"""Facade over the configured model provider (see backend/providers)."""
from __future__ import annotations

from . import config
from .providers import Provider

_instances: dict[str, Provider] = {}


def provider() -> Provider:
    name = config.PROVIDER
    if name not in _instances:
        if name == "ollama":
            from .providers.ollama_provider import OllamaProvider
            _instances[name] = OllamaProvider()
        elif name == "anthropic":
            from .providers.anthropic_provider import AnthropicProvider
            _instances[name] = AnthropicProvider()
        else:
            raise ValueError(f"Unknown TEACHER_PROVIDER '{name}' (use 'ollama' or 'anthropic')")
    return _instances[name]


def friendly_error(exc: Exception) -> str:
    try:
        return provider().friendly_error(exc)
    except ValueError as bad_config:
        return str(bad_config)


def health() -> dict:
    if config.MOCK:
        return {"ready": True, "problem": None}
    try:
        return provider().health()
    except ValueError as bad_config:
        return {"ready": False, "problem": str(bad_config)}
