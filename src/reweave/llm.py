"""LLM provider adapters for insight synthesis."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

import httpx


class LLMProvider(Protocol):
    """Provider interface used by insight generation."""

    def generate_text(
        self,
        *,
        system: str,
        user: str,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> str:
        """Generate a text response."""

    def generate_json(
        self,
        *,
        system: str,
        user: str,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """Generate and parse a JSON response."""


@dataclass(frozen=True)
class LLMSettings:
    provider: str
    model: str
    api_key: str
    base_url: str = ""
    max_context_chars: int = 80_000
    temperature: float = 0.2


class ProviderConfigurationError(ValueError):
    """Raised when provider settings are incomplete or unsupported."""


class OpenAICompatibleProvider:
    """OpenAI chat-completions compatible provider."""

    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1"):
        if not api_key:
            raise ProviderConfigurationError("API key is required.")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def generate_text(
        self,
        *,
        system: str,
        user: str,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> str:
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    def generate_json(
        self,
        *,
        system: str,
        user: str,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        text = self.generate_text(
            system=system,
            user=user,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return _parse_json_response(text)


class AnthropicProvider:
    """Anthropic Messages API provider."""

    def __init__(self, api_key: str, base_url: str = "https://api.anthropic.com/v1"):
        if not api_key:
            raise ProviderConfigurationError("API key is required.")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def generate_text(
        self,
        *,
        system: str,
        user: str,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> str:
        response = httpx.post(
            f"{self.base_url}/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "system": system,
                "messages": [{"role": "user", "content": user}],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        return "".join(block.get("text", "") for block in data.get("content", []))

    def generate_json(
        self,
        *,
        system: str,
        user: str,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        text = self.generate_text(
            system=system,
            user=user,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return _parse_json_response(text)


class GeminiProvider:
    """Google Gemini generateContent provider."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
    ):
        if not api_key:
            raise ProviderConfigurationError("API key is required.")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def generate_text(
        self,
        *,
        system: str,
        user: str,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> str:
        response = httpx.post(
            f"{self.base_url}/models/{model}:generateContent",
            params={"key": self.api_key},
            json={
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {
                    "temperature": temperature,
                    "maxOutputTokens": max_tokens,
                },
            },
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(part.get("text", "") for part in parts)

    def generate_json(
        self,
        *,
        system: str,
        user: str,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        text = self.generate_text(
            system=system,
            user=user,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return _parse_json_response(text)


def create_provider(settings: LLMSettings) -> LLMProvider:
    """Build an LLM provider from settings."""
    provider = settings.provider.lower().strip()
    if provider == "openai":
        return OpenAICompatibleProvider(
            api_key=settings.api_key,
            base_url=settings.base_url or "https://api.openai.com/v1",
        )
    if provider in {"openai-compatible", "compatible", "openrouter", "kimi"}:
        if not settings.base_url:
            raise ProviderConfigurationError("Base URL is required for compatible providers.")
        return OpenAICompatibleProvider(api_key=settings.api_key, base_url=settings.base_url)
    if provider == "anthropic":
        return AnthropicProvider(
            api_key=settings.api_key,
            base_url=settings.base_url or "https://api.anthropic.com/v1",
        )
    if provider == "gemini":
        return GeminiProvider(
            api_key=settings.api_key,
            base_url=settings.base_url or "https://generativelanguage.googleapis.com/v1beta",
        )
    raise ProviderConfigurationError(f"Unsupported provider: {settings.provider}")


def _parse_json_response(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    return json.loads(text)
