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

    def test_shared_cost_summary(self):
        from sbs.config import Config

        config = Config(provider="anthropic", anthropic_api_key="test-key")
        cost = CostSummary()
        from sbs.llm.client import LLMClient

        client = LLMClient(config, cost_summary=cost)
        assert client.cost is cost
