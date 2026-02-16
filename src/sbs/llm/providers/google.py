"""Google GenAI SDK provider implementation."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from pydantic import BaseModel

from sbs.models.pipeline import TokenUsage


class GoogleProvider:
    """Google Gemini API provider (AI Studio key auth)."""

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("GOOGLE_API_KEY is required when provider is 'google'")

        from google import genai

        self._client = genai.Client(api_key=api_key).aio

    async def structured_call(
        self,
        model: str,
        system: str,
        user: str,
        schema: type[BaseModel],
        max_tokens: int = 4096,
    ) -> tuple[BaseModel, TokenUsage]:
        """Make an API call expecting JSON output compatible with a Pydantic schema."""
        response = await self._call_with_retry(
            model=model,
            contents=user,
            config={
                "system_instruction": system,
                "max_output_tokens": max_tokens,
                "response_mime_type": "application/json",
                "response_schema": schema.model_json_schema(),
            },
        )

        result_data = self._extract_structured_data(response)
        parsed = schema.model_validate(result_data)
        return parsed, self._build_usage(response, model)

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
            contents=user,
            config={
                "system_instruction": system,
                "max_output_tokens": max_tokens,
            },
        )

        text = self._extract_text(response)
        return text, self._build_usage(response, model)

    async def _call_with_retry(self, *, max_retries: int = 3, **kwargs: Any) -> Any:
        """Call the API with exponential backoff retry."""
        from google.genai import errors

        delays = [1, 4, 16]
        last_error: Exception | None = None

        for attempt in range(max_retries):
            try:
                return await self._client.models.generate_content(**kwargs)
            except errors.APIError as e:
                last_error = e
                status = getattr(e, "status", None)
                code = getattr(e, "code", None)
                status_code = status if isinstance(status, int) else code
                should_retry = isinstance(status_code, int) and (
                    status_code == 429 or status_code >= 500
                )
                if should_retry and attempt < max_retries - 1:
                    await asyncio.sleep(delays[attempt])
                    continue
                raise

        raise last_error if last_error else RuntimeError("Google API call failed")

    @staticmethod
    def _extract_structured_data(response: Any) -> dict[str, Any]:
        """Extract JSON object output from response.parsed or response text."""
        parsed = getattr(response, "parsed", None)
        if parsed is not None:
            if isinstance(parsed, BaseModel):
                return parsed.model_dump()  # type: ignore[return-value]
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, str):
                return json.loads(parsed)
            if hasattr(parsed, "model_dump"):
                return parsed.model_dump()  # type: ignore[no-any-return]

        text = GoogleProvider._extract_text(response)
        if not text:
            raise ValueError("No structured JSON result found in Google response")

        return json.loads(GoogleProvider._strip_code_fences(text))

    @staticmethod
    def _extract_text(response: Any) -> str:
        """Extract text from response, including candidate fallback."""
        text = getattr(response, "text", None)
        if isinstance(text, str) and text:
            return text

        parts_text: list[str] = []
        for candidate in getattr(response, "candidates", []) or []:
            content = getattr(candidate, "content", None)
            for part in getattr(content, "parts", []) or []:
                part_text = getattr(part, "text", None)
                if isinstance(part_text, str):
                    parts_text.append(part_text)

        return "".join(parts_text)

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        """Remove markdown code fences around JSON when present."""
        cleaned = text.strip()
        if not cleaned.startswith("```"):
            return cleaned

        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()

    @staticmethod
    def _build_usage(response: Any, model: str) -> TokenUsage:
        """Map Gemini usage metadata to the shared token usage model."""
        usage = getattr(response, "usage_metadata", None)
        if usage is None:
            return TokenUsage(model=model)

        if isinstance(usage, dict):
            input_tokens = int(usage.get("prompt_token_count") or 0)
            output_tokens = int(usage.get("candidates_token_count") or 0)
            return TokenUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=model,
            )

        return TokenUsage(
            input_tokens=int(getattr(usage, "prompt_token_count", 0) or 0),
            output_tokens=int(getattr(usage, "candidates_token_count", 0) or 0),
            model=model,
        )
