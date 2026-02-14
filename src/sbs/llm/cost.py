"""Token usage and cost tracking."""

from __future__ import annotations

from sbs.models.pipeline import CostSummary, TokenUsage

# Pricing per 1M tokens (USD) — as of early 2026
PRICING: dict[str, tuple[float, float]] = {
    # Anthropic: (input_per_1M, output_per_1M)
    "claude-sonnet-4-5-20250929": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (0.80, 4.0),
    # OpenAI
    "gpt-4o": (2.50, 10.0),
    "gpt-4o-mini": (0.15, 0.60),
}


def estimate_call_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate cost in USD for a single LLM call."""
    pricing = PRICING.get(model, (3.0, 15.0))  # Default to Sonnet pricing
    input_cost = (input_tokens / 1_000_000) * pricing[0]
    output_cost = (output_tokens / 1_000_000) * pricing[1]
    return input_cost + output_cost


def track_usage(
    cost_summary: CostSummary, model: str, input_tokens: int, output_tokens: int
) -> None:
    """Record a single LLM call's usage into the cost summary."""
    usage = TokenUsage(input_tokens=input_tokens, output_tokens=output_tokens, model=model)
    cost_summary.calls.append(usage)
    cost_summary.total_input_tokens += input_tokens
    cost_summary.total_output_tokens += output_tokens
    cost_summary.estimated_cost_usd += estimate_call_cost(model, input_tokens, output_tokens)
