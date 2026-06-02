"""Tests for LLM provider configuration."""

import pytest

from reweave.llm import LLMSettings, ProviderConfigurationError, create_provider


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
