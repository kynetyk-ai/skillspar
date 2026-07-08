"""Provider adapters — vendor API boundary for the eval engine."""

from __future__ import annotations

import os
from typing import Any

from skill_evaluator.providers.base import Provider, ProviderError

DEFAULT_API_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}


def missing_api_key_error(provider_name: str, api_key_env: str | None = None) -> str | None:
    """Return a user-facing error message if the provider's API key env var is unset."""
    env_name = api_key_env or DEFAULT_API_KEY_ENV.get(provider_name)
    if env_name and not os.environ.get(env_name):
        return (
            f"Error: {env_name} environment variable is not set. Set it or add it to a .env file."
        )
    return None


def get_provider(
    name: str,
    *,
    client: Any | None = None,
    base_url: str | None = None,
    api_key_env: str | None = None,
    max_retries: int = 2,
) -> Provider:
    """Build a provider adapter by name, optionally wrapping an injected SDK client."""
    if name == "anthropic":
        from skill_evaluator.providers.anthropic import AnthropicProvider

        return AnthropicProvider(client, max_retries=max_retries, api_key_env=api_key_env)
    if name == "openai":
        from skill_evaluator.providers.openai_compat import OpenAICompatProvider

        return OpenAICompatProvider(
            client, base_url=base_url, api_key_env=api_key_env, max_retries=max_retries
        )
    raise ProviderError(f"Unknown provider: {name!r} (expected 'anthropic' or 'openai')")


__all__ = [
    "DEFAULT_API_KEY_ENV",
    "Provider",
    "ProviderError",
    "get_provider",
    "missing_api_key_error",
]
