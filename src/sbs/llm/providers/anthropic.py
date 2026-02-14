"""Anthropic SDK provider implementation."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from pydantic import BaseModel

from sbs.models.pipeline import TokenUsage


class AnthropicProvider:
    """Anthropic Claude API provider."""

    def __init__(self, api_key: str):
        import anthropic

        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    async def structured_call(
        self,
        model: str,
        system: str,
        user: str,
        schema: type[BaseModel],
        max_tokens: int = 4096,
    ) -> tuple[BaseModel, TokenUsage]:
        """Make an API call expecting structured output via tool_use."""
        tool_schema = self._pydantic_to_tool(schema)

        response = await self._call_with_retry(
            model=model,
            system=system,
            messages=[{"role": "user", "content": user}],
            tools=[tool_schema],
            tool_choice={"type": "tool", "name": schema.__name__},
            max_tokens=max_tokens,
        )

        # Extract tool use result
        result_data = self._extract_tool_result(response)
        parsed = schema.model_validate(result_data)

        usage = TokenUsage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=model,
        )
        return parsed, usage

    async def text_call(
        self,
        model: str,
        system: str,
        user: str,
        max_tokens: int = 4096,
    ) -> tuple[str, TokenUsage]:
        """Make a plain text API call."""
        response = await self._call_with_retry(
            model=model,
            system=system,
            messages=[{"role": "user", "content": user}],
            max_tokens=max_tokens,
        )

        text = ""
        for block in response.content:
            if block.type == "text":
                text += block.text

        usage = TokenUsage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=model,
        )
        return text, usage

    async def _call_with_retry(self, *, max_retries: int = 3, **kwargs: Any) -> Any:
        """Call the API with exponential backoff retry."""
        import anthropic

        delays = [1, 4, 16]
        last_error: Exception | None = None

        for attempt in range(max_retries):
            try:
                return await self._client.messages.create(**kwargs)
            except anthropic.RateLimitError as e:
                last_error = e
                if attempt < max_retries - 1:
                    await asyncio.sleep(delays[attempt])
            except anthropic.APIError as e:
                last_error = e
                if attempt < max_retries - 1:
                    await asyncio.sleep(delays[attempt])

        raise last_error  # type: ignore[misc]

    @staticmethod
    def _pydantic_to_tool(schema: type[BaseModel]) -> dict[str, Any]:
        """Convert a Pydantic model to an Anthropic tool definition."""
        json_schema = schema.model_json_schema()
        return {
            "name": schema.__name__,
            "description": f"Output structured data as {schema.__name__}",
            "input_schema": json_schema,
        }

    @staticmethod
    def _extract_tool_result(response: Any) -> dict[str, Any]:
        """Extract the tool use input from a response."""
        for block in response.content:
            if block.type == "tool_use":
                return block.input  # type: ignore[no-any-return]
        # Fallback: try to parse text as JSON
        for block in response.content:
            if block.type == "text":
                return json.loads(block.text)
        raise ValueError("No tool_use result found in response")
