"""LLM provider adapters for insight synthesis."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
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


class LLMCredential(Protocol):
    key_id: str
    label: str
    api_key: str


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


class ProviderRequestError(ValueError):
    """Raised when a provider request fails and should not be retried."""


class ProviderAuthenticationError(ProviderRequestError):
    """Raised when all enabled API keys are rejected by the provider."""


class ProviderPermissionError(ProviderRequestError):
    """Raised when a credential cannot list the provider's models."""


class ProviderRateLimitError(ProviderRequestError):
    """Raised when the provider rate limits model discovery."""


@dataclass(frozen=True)
class ModelDiscoveryResult:
    models: tuple[str, ...]
    credential_label: str


class FailoverLLMProvider:
    """Try multiple API keys for the same provider in priority order."""

    def __init__(self, settings: LLMSettings, credentials: tuple[LLMCredential, ...]):
        if not credentials:
            raise ProviderConfigurationError("At least one enabled API key is required.")
        self.settings = settings
        self.credentials = credentials

    def generate_text(
        self,
        *,
        system: str,
        user: str,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> str:
        return self._try_keys(
            "generate_text",
            system=system,
            user=user,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def generate_json(
        self,
        *,
        system: str,
        user: str,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        return self._try_keys(
            "generate_json",
            system=system,
            user=user,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def _try_keys(self, method_name: str, **kwargs):
        failures: list[str] = []
        for credential in self.credentials:
            provider = create_provider(
                replace(self.settings, api_key=credential.api_key)
            )
            try:
                method = getattr(provider, method_name)
                return method(**kwargs)
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                if not _is_retryable_provider_error(exc):
                    raise ProviderRequestError(_provider_error_summary(exc)) from exc
                failures.append(f"{credential.label}: {_provider_error_summary(exc)}")
        failure_text = "; ".join(failures) if failures else "No keys were attempted."
        raise ProviderConfigurationError(f"All enabled API keys failed: {failure_text}")


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
    if provider == "openrouter":
        return OpenAICompatibleProvider(
            api_key=settings.api_key,
            base_url=settings.base_url or "https://openrouter.ai/api/v1",
        )
    if provider in {"openai-compatible", "compatible", "kimi"}:
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


def create_failover_provider(
    settings: LLMSettings,
    credentials: tuple[LLMCredential, ...],
) -> LLMProvider:
    """Build a provider that retries across saved API keys."""
    provider = settings.provider.lower().strip()
    if provider in {"openai-compatible", "compatible", "kimi"}:
        if not settings.base_url:
            raise ProviderConfigurationError("Base URL is required for compatible providers.")
    elif provider not in {"openai", "anthropic", "gemini", "openrouter"}:
        raise ProviderConfigurationError(f"Unsupported provider: {settings.provider}")
    return FailoverLLMProvider(settings, credentials)


def discover_available_models(
    settings: LLMSettings,
    credentials: tuple[LLMCredential, ...],
) -> ModelDiscoveryResult:
    """Fetch models available to the first enabled credential accepted by the provider."""
    if not credentials:
        raise ProviderConfigurationError(
            "Add and enable an API key before loading models."
        )

    authentication_failures = 0
    permission_failures = 0
    for credential in credentials:
        try:
            models = _fetch_available_models(settings, credential.api_key)
        except ProviderConfigurationError:
            raise
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 401:
                authentication_failures += 1
                continue
            if exc.response.status_code == 403:
                permission_failures += 1
                continue
            if exc.response.status_code == 429:
                raise ProviderRateLimitError(
                    "The provider rate limit was reached. Wait a moment and try again."
                ) from exc
            raise ProviderRequestError(
                f"Provider model listing failed with HTTP {exc.response.status_code}."
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderRequestError(
                "Could not reach the provider. Check your connection and try again."
            ) from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderRequestError(
                "The provider returned an invalid model list."
            ) from exc

        return ModelDiscoveryResult(
            models=tuple(sorted(set(models), key=str.casefold)),
            credential_label=credential.label,
        )

    if authentication_failures:
        raise ProviderAuthenticationError(
            "That API key was not accepted. Check it and try again."
        )
    if permission_failures:
        raise ProviderPermissionError(
            "The API key is valid, but it does not have permission to list models."
        )
    raise ProviderConfigurationError("No enabled API keys are available.")


def _fetch_available_models(settings: LLMSettings, api_key: str) -> list[str]:
    provider = settings.provider.lower().strip()
    headers: dict[str, str]
    params: dict[str, str] | None = None

    if provider == "openai":
        base_url = settings.base_url or "https://api.openai.com/v1"
        headers = {"Authorization": f"Bearer {api_key}"}
    elif provider in {"openai-compatible", "compatible", "kimi"}:
        if not settings.base_url:
            raise ProviderConfigurationError(
                "Save a base URL before loading models for this provider."
            )
        base_url = settings.base_url
        headers = {"Authorization": f"Bearer {api_key}"}
    elif provider == "openrouter":
        base_url = settings.base_url or "https://openrouter.ai/api/v1"
        headers = {"Authorization": f"Bearer {api_key}"}
    elif provider == "anthropic":
        base_url = settings.base_url or "https://api.anthropic.com/v1"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
    elif provider == "gemini":
        base_url = settings.base_url or "https://generativelanguage.googleapis.com/v1beta"
        headers = {}
        params = {"key": api_key}
    else:
        raise ProviderConfigurationError(f"Unsupported provider: {settings.provider}")

    response = httpx.get(
        f"{base_url.rstrip('/')}/models",
        headers=headers,
        params=params,
        timeout=30,
    )
    response.raise_for_status()
    return _extract_model_ids(provider, response.json())


def _extract_model_ids(provider: str, data: dict[str, Any]) -> list[str]:
    if provider == "gemini":
        models = []
        for item in data.get("models", []):
            supported_methods = item.get("supportedGenerationMethods", [])
            if "generateContent" not in supported_methods:
                continue
            model_id = str(item["name"]).removeprefix("models/").strip()
            if model_id:
                models.append(model_id)
        return models

    return [
        model_id
        for item in data.get("data", [])
        if (model_id := str(item["id"]).strip())
    ]


def _is_retryable_provider_error(exc: httpx.HTTPStatusError | httpx.RequestError) -> bool:
    if isinstance(exc, httpx.RequestError) and not isinstance(exc, httpx.HTTPStatusError):
        return True
    status_code = exc.response.status_code
    return status_code in {401, 403, 429} or status_code >= 500


def _provider_error_summary(exc: httpx.HTTPStatusError | httpx.RequestError) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    return exc.__class__.__name__


def _parse_json_response(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    return json.loads(text)
