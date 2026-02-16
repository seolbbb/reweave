"""Provider-agnostic LLM client wrapper."""

from __future__ import annotations

from pydantic import BaseModel

from sbs.config import Config
from sbs.llm.cost import track_usage
from sbs.models.pipeline import CostSummary, TokenUsage


class LLMClient:
    """Unified LLM client that delegates to provider-specific implementations."""

    def __init__(self, config: Config, cost_summary: CostSummary | None = None):
        self._config = config
        self._cost = cost_summary or CostSummary()
        self._provider = self._create_provider()

    @property
    def cost(self) -> CostSummary:
        return self._cost

    def _create_provider(self):
        if self._config.provider == "anthropic":
            from sbs.llm.providers.anthropic import AnthropicProvider

            return AnthropicProvider(api_key=self._config.anthropic_api_key)
        elif self._config.provider == "openai":
            from sbs.llm.providers.openai import OpenAIProvider

            return OpenAIProvider(api_key=self._config.openai_api_key)
        elif self._config.provider == "google":
            from sbs.llm.providers.google import GoogleProvider

            return GoogleProvider(api_key=self._config.google_api_key)
        else:
            raise ValueError(f"Unknown provider: {self._config.provider}")

    async def structured_call(
        self,
        model: str,
        system: str,
        user: str,
        schema: type[BaseModel],
        max_tokens: int = 4096,
    ) -> tuple[BaseModel, TokenUsage]:
        """Make a structured output LLM call."""
        result, usage = await self._provider.structured_call(
            model=model, system=system, user=user, schema=schema, max_tokens=max_tokens
        )
        track_usage(self._cost, usage.model, usage.input_tokens, usage.output_tokens)
        return result, usage

    async def text_call(
        self,
        model: str,
        system: str,
        user: str,
        max_tokens: int = 4096,
    ) -> tuple[str, TokenUsage]:
        """Make a plain text LLM call."""
        text, usage = await self._provider.text_call(
            model=model, system=system, user=user, max_tokens=max_tokens
        )
        track_usage(self._cost, usage.model, usage.input_tokens, usage.output_tokens)
        return text, usage

    async def cheap_structured_call(
        self,
        system: str,
        user: str,
        schema: type[BaseModel],
        max_tokens: int = 4096,
    ) -> tuple[BaseModel, TokenUsage]:
        """Structured call using the cheap/lightweight model."""
        return await self.structured_call(
            model=self._config.cheap_model,
            system=system, user=user, schema=schema, max_tokens=max_tokens,
        )

    async def main_structured_call(
        self,
        system: str,
        user: str,
        schema: type[BaseModel],
        max_tokens: int = 4096,
    ) -> tuple[BaseModel, TokenUsage]:
        """Structured call using the main/powerful model."""
        return await self.structured_call(
            model=self._config.model,
            system=system, user=user, schema=schema, max_tokens=max_tokens,
        )

    async def cheap_text_call(
        self, system: str, user: str, max_tokens: int = 4096
    ) -> tuple[str, TokenUsage]:
        """Text call using the cheap model."""
        return await self.text_call(
            model=self._config.cheap_model, system=system, user=user, max_tokens=max_tokens
        )

    async def main_text_call(
        self, system: str, user: str, max_tokens: int = 4096
    ) -> tuple[str, TokenUsage]:
        """Text call using the main model."""
        return await self.text_call(
            model=self._config.model, system=system, user=user, max_tokens=max_tokens
        )
