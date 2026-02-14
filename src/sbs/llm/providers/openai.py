"""OpenAI SDK provider implementation."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from pydantic import BaseModel

from sbs.models.pipeline import TokenUsage


class OpenAIProvider:
    """OpenAI API provider."""

    def __init__(self, api_key: str):
        import openai

        self._client = openai.AsyncOpenAI(api_key=api_key)

    async def structured_call(
        self,
        model: str,
        system: str,
        user: str,
        schema: type[BaseModel],
        max_tokens: int = 4096,
    ) -> tuple[BaseModel, TokenUsage]:
        """Make an API call expecting structured output via response_format."""
        json_schema = schema.model_json_schema()

        response = await self._call_with_retry(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "schema": json_schema,
                    "strict": False,
                },
            },
            max_tokens=max_tokens,
        )

        content = response.choices[0].message.content or "{}"
        data = json.loads(content)
        parsed = schema.model_validate(data)

        usage = TokenUsage(
            input_tokens=response.usage.prompt_tokens if response.usage else 0,
            output_tokens=response.usage.completion_tokens if response.usage else 0,
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
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
        )

        text = response.choices[0].message.content or ""
        usage = TokenUsage(
            input_tokens=response.usage.prompt_tokens if response.usage else 0,
            output_tokens=response.usage.completion_tokens if response.usage else 0,
            model=model,
        )
        return text, usage

    async def _call_with_retry(self, *, max_retries: int = 3, **kwargs: Any) -> Any:
        """Call the API with exponential backoff retry."""
        import openai

        delays = [1, 4, 16]
        last_error: Exception | None = None

        for attempt in range(max_retries):
            try:
                return await self._client.chat.completions.create(**kwargs)
            except openai.RateLimitError as e:
                last_error = e
                if attempt < max_retries - 1:
                    await asyncio.sleep(delays[attempt])
            except openai.APIError as e:
                last_error = e
                if attempt < max_retries - 1:
                    await asyncio.sleep(delays[attempt])

        raise last_error  # type: ignore[misc]
