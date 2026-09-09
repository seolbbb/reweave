"""Disconnect and provider changes stop the next unsent saved-profile call."""

import httpx
import pytest

from reweave import llm
from reweave.analysis_policy import AnalysisPolicyStore, BudgetedProvider
from reweave.llm import LLMSettings, ProviderConnectionChangedError
from reweave.llm_profiles import KeyInput, LLMProfileStore, ProfileInput
from reweave.web import _guarded_saved_provider


def test_disconnect_during_first_key_failure_stops_failover(tmp_path, monkeypatch):
    store = LLMProfileStore(tmp_path / "profiles.json")
    profile = store.create(
        ProfileInput(
            name="Synthetic",
            provider="openai",
            default_model="test",
            keys=(KeyInput("one", "test-one"), KeyInput("two", "test-two")),
        )
    )
    settings = LLMSettings(provider="openai", model="test", api_key="")
    provider = _guarded_saved_provider(
        store,
        profile,
        settings,
        store.credentials_for(profile.id),
        require_active=True,
    )
    calls = []

    class DisconnectedDuringResponse:
        def generate_json(self, **kwargs):
            calls.append("sent")
            store.clear_keys(profile.id)
            response = httpx.Response(429, request=httpx.Request("POST", "https://invalid.test"))
            raise httpx.HTTPStatusError(
                "Synthetic limit", request=response.request, response=response
            )

    monkeypatch.setattr(llm, "create_provider", lambda settings: DisconnectedDuringResponse())
    policy = AnalysisPolicyStore(tmp_path / "usage.db")
    wrapped = BudgetedProvider(provider, policy)
    with pytest.raises(ProviderConnectionChangedError):
        wrapped.generate_json(system="rules", user="synthetic", model="test", max_tokens=10)
    assert calls == ["sent"]
    usage = policy.usage()
    with pytest.raises(ProviderConnectionChangedError):
        wrapped.generate_json(system="rules", user="synthetic", model="test", max_tokens=10)
    assert policy.usage() == usage
    assert calls == ["sent"]
