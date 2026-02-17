"""Tests for LLM client and cost tracking (no actual API calls)."""

from sbs.llm.cost import estimate_call_cost, track_usage
from sbs.models.pipeline import CostSummary


class TestCostTracking:
    def test_estimate_sonnet_cost(self):
        cost = estimate_call_cost("claude-sonnet-4-5-20250929", 1000, 500)
        expected = (1000 / 1_000_000) * 3.0 + (500 / 1_000_000) * 15.0
        assert abs(cost - expected) < 1e-10

    def test_estimate_haiku_cost(self):
        cost = estimate_call_cost("claude-haiku-4-5-20251001", 1000, 500)
        expected = (1000 / 1_000_000) * 0.80 + (500 / 1_000_000) * 4.0
        assert abs(cost - expected) < 1e-10

    def test_estimate_gpt4o_cost(self):
        cost = estimate_call_cost("gpt-4o", 1000, 500)
        expected = (1000 / 1_000_000) * 2.50 + (500 / 1_000_000) * 10.0
        assert abs(cost - expected) < 1e-10

    def test_estimate_gemini_pro_cost(self):
        cost = estimate_call_cost("gemini-3-pro-preview", 1000, 500)
        expected = (1000 / 1_000_000) * 3.5 + (500 / 1_000_000) * 10.5
        assert abs(cost - expected) < 1e-10

    def test_estimate_gemini_flash_cost(self):
        cost = estimate_call_cost("gemini-3-flash-preview", 1000, 500)
        expected = (1000 / 1_000_000) * 0.30 + (500 / 1_000_000) * 2.5
        assert abs(cost - expected) < 1e-10

    def test_unknown_model_defaults(self):
        cost = estimate_call_cost("unknown-model", 1000, 500)
        # Should default to Sonnet pricing
        expected = (1000 / 1_000_000) * 3.0 + (500 / 1_000_000) * 15.0
        assert abs(cost - expected) < 1e-10

    def test_track_usage(self):
        summary = CostSummary()
        track_usage(summary, "claude-sonnet-4-5-20250929", 1000, 500)
        assert summary.total_input_tokens == 1000
        assert summary.total_output_tokens == 500
        assert len(summary.calls) == 1
        assert summary.estimated_cost_usd > 0

    def test_track_multiple_calls(self):
        summary = CostSummary()
        track_usage(summary, "claude-haiku-4-5-20251001", 500, 200)
        track_usage(summary, "claude-sonnet-4-5-20250929", 2000, 1000)
        assert summary.total_input_tokens == 2500
        assert summary.total_output_tokens == 1200
        assert len(summary.calls) == 2


class TestLLMClientInit:
    def test_create_anthropic_client(self):
        from sbs.config import Config

        config = Config(provider="anthropic", anthropic_api_key="test-key")
        from sbs.llm.client import LLMClient

        client = LLMClient(config)
        assert client._config.provider == "anthropic"

    def test_create_openai_client(self):
        from sbs.config import Config

        config = Config(provider="openai", openai_api_key="test-key")
        from sbs.llm.client import LLMClient

        client = LLMClient(config)
        assert client._config.provider == "openai"

    def test_create_google_client(self):
        from sbs.config import Config

        config = Config(provider="google", google_api_key="test-key")
        from sbs.llm.client import LLMClient

        client = LLMClient(config)
        assert client._config.provider == "google"

    def test_shared_cost_summary(self):
        from sbs.config import Config

        config = Config(provider="anthropic", anthropic_api_key="test-key")
        cost = CostSummary()
        from sbs.llm.client import LLMClient

        client = LLMClient(config, cost_summary=cost)
        assert client.cost is cost


class TestConfigDefaults:
    def test_google_provider_defaults(self, monkeypatch):
        from sbs.config import Config

        monkeypatch.delenv("SBS_MODEL", raising=False)
        monkeypatch.delenv("SBS_CHEAP_MODEL", raising=False)

        config = Config(provider="google")
        assert config.model == "gemini-3-pro-preview"
        assert config.cheap_model == "gemini-3-flash-preview"

    def test_model_env_overrides_provider_defaults(self, monkeypatch):
        from sbs.config import Config

        monkeypatch.setenv("SBS_MODEL", "my-main")
        monkeypatch.setenv("SBS_CHEAP_MODEL", "my-cheap")

        config = Config(provider="google")
        assert config.model == "my-main"
        assert config.cheap_model == "my-cheap"

    def test_google_legacy_model_aliases(self, monkeypatch):
        from sbs.config import Config

        monkeypatch.setenv("SBS_MODEL", "gemini-3-pro")
        monkeypatch.setenv("SBS_CHEAP_MODEL", "gemini-3-flash")

        config = Config(provider="google")
        assert config.model == "gemini-3-pro-preview"
        assert config.cheap_model == "gemini-3-flash-preview"

    def test_provider_default_concurrency_when_omitted(self):
        from sbs.config import Config

        assert Config(provider="anthropic").concurrency == 10
        assert Config(provider="openai").concurrency == 15
        assert Config(provider="google").concurrency == 15

    def test_explicit_concurrency_is_preserved(self):
        from sbs.config import Config

        assert Config(provider="openai", concurrency=3).concurrency == 3
        assert Config(provider="anthropic", concurrency=7).concurrency == 7
