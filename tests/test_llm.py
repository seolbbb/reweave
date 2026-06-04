"""Tests for LLM provider configuration."""

import pytest

import reweave.llm
from reweave.llm import (
    LLMSettings,
    ProviderConfigurationError,
    ProviderRequestError,
    create_failover_provider,
    create_provider,
)


class Credential:
    def __init__(self, label, api_key):
        self.key_id = label
        self.label = label
        self.api_key = api_key


def test_openai_requires_api_key():
    with pytest.raises(ProviderConfigurationError):
        create_provider(LLMSettings(provider="openai", model="gpt-4o-mini", api_key=""))


def test_compatible_requires_base_url():
    with pytest.raises(ProviderConfigurationError):
        create_provider(
            LLMSettings(provider="openai-compatible", model="model", api_key="key")
        )


def test_unsupported_provider():
    with pytest.raises(ProviderConfigurationError):
        create_provider(LLMSettings(provider="unknown", model="model", api_key="key"))


def test_failover_provider_uses_next_key_for_retryable_error(monkeypatch):
    calls = []

    def fake_post(url, *, headers, json, timeout):
        calls.append(headers["Authorization"])
        request = reweave.llm.httpx.Request("POST", url)
        if len(calls) == 1:
            return reweave.llm.httpx.Response(401, request=request)
        return reweave.llm.httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}}]},
            request=request,
        )

    monkeypatch.setattr(reweave.llm.httpx, "post", fake_post)
    provider = create_failover_provider(
        LLMSettings(provider="openai", model="gpt-4o-mini", api_key=""),
        (Credential("first", "first-key"), Credential("second", "second-key")),
    )

    text = provider.generate_text(system="s", user="u", model="gpt-4o-mini")

    assert text == "ok"
    assert calls == ["Bearer first-key", "Bearer second-key"]


def test_failover_provider_does_not_retry_non_retryable_error(monkeypatch):
    calls = []

    def fake_post(url, *, headers, json, timeout):
        calls.append(headers["Authorization"])
        request = reweave.llm.httpx.Request("POST", url)
        return reweave.llm.httpx.Response(400, request=request)

    monkeypatch.setattr(reweave.llm.httpx, "post", fake_post)
    provider = create_failover_provider(
        LLMSettings(provider="openai", model="gpt-4o-mini", api_key=""),
        (Credential("first", "first-key"), Credential("second", "second-key")),
    )

    with pytest.raises(ProviderRequestError):
        provider.generate_text(system="s", user="u", model="gpt-4o-mini")

    assert calls == ["Bearer first-key"]
