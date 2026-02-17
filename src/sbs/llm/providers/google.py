"""Google GenAI SDK provider implementation."""

from __future__ import annotations

import asyncio
import json
import random
import re
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

    async def _call_with_retry(self, *, max_retries: int = 5, **kwargs: Any) -> Any:
        """Call the API with exponential backoff + jitter retry."""
        from google.genai import errors

        delays = [1, 2, 4, 8, 16]
        last_error: Exception | None = None

        for attempt in range(max_retries):
            try:
                return await self._client.models.generate_content(**kwargs)
            except errors.APIError as e:
                last_error = e
                status = getattr(e, "status", None)
                code = getattr(e, "code", None)
                status_code = status if isinstance(status, int) else code
                if status_code == 404:
                    model = kwargs.get("model", "")
                    raise ValueError(
                        f"Google model '{model}' was not found for generateContent. "
                        "Use an available model such as 'gemini-3-pro-preview' (main) and "
                        "'gemini-3-flash-preview' (cheap), or set --model/--cheap-model explicitly."
                    ) from e
                should_retry = isinstance(status_code, int) and (
                    status_code == 429 or status_code >= 500
                )
                if should_retry and attempt < max_retries - 1:
                    delay = delays[min(attempt, len(delays) - 1)]
                    jitter = random.uniform(0, delay)  # noqa: S311
                    await asyncio.sleep(delay + jitter)
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
                parsed_obj = GoogleProvider._parse_json_object(parsed)
                if parsed_obj is not None:
                    return parsed_obj
            if hasattr(parsed, "model_dump"):
                return parsed.model_dump()  # type: ignore[no-any-return]

        texts = GoogleProvider._collect_text_candidates(response)
        for text in texts:
            parsed_obj = GoogleProvider._parse_json_object(text)
            if parsed_obj is not None:
                return parsed_obj

        if not texts:
            raise ValueError("No structured JSON result found in Google response")
        snippet = texts[0].replace("\n", " ")[:280]
        raise ValueError(f"Could not parse structured JSON from Google response: {snippet}")

    @staticmethod
    def _extract_text(response: Any) -> str:
        """Extract text from response, including candidate fallback."""
        texts = GoogleProvider._collect_text_candidates(response)
        return texts[0] if texts else ""

    @staticmethod
    def _collect_text_candidates(response: Any) -> list[str]:
        """Collect possible text payloads in parse priority order."""
        candidates: list[str] = []

        primary_text = getattr(response, "text", None)
        if isinstance(primary_text, str) and primary_text.strip():
            candidates.append(primary_text)

        for candidate in getattr(response, "candidates", []) or []:
            content = getattr(candidate, "content", None)
            part_texts: list[str] = []
            for part in getattr(content, "parts", []) or []:
                part_text = getattr(part, "text", None)
                if isinstance(part_text, str) and part_text.strip():
                    part_texts.append(part_text)
                    candidates.append(part_text)
            if part_texts:
                candidates.append("".join(part_texts))

        deduped: list[str] = []
        seen: set[str] = set()
        for item in candidates:
            trimmed = item.strip()
            if not trimmed or trimmed in seen:
                continue
            seen.add(trimmed)
            deduped.append(trimmed)
        return deduped

    @staticmethod
    def _parse_json_object(text: str) -> dict[str, Any] | None:
        """Parse a JSON object from model output with light recovery heuristics."""
        cleaned = GoogleProvider._strip_code_fences(text).strip()
        if not cleaned:
            return None

        attempts: list[str] = [cleaned]

        extracted = GoogleProvider._extract_first_json_object(cleaned)
        if extracted is not None and extracted != cleaned:
            attempts.append(extracted)

        for candidate in list(attempts):
            normalized = GoogleProvider._remove_trailing_commas(candidate)
            if normalized != candidate:
                attempts.append(normalized)

        seen: set[str] = set()
        for candidate in attempts:
            if candidate in seen:
                continue
            seen.add(candidate)
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
        return None

    @staticmethod
    def _extract_first_json_object(text: str) -> str | None:
        """Extract the first balanced JSON object in a text blob."""
        start: int | None = None
        depth = 0
        in_string = False
        escaped = False

        for idx, ch in enumerate(text):
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
                continue

            if ch == "{":
                if depth == 0:
                    start = idx
                depth += 1
                continue

            if ch == "}" and depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    return text[start : idx + 1]

        return None

    @staticmethod
    def _remove_trailing_commas(text: str) -> str:
        """Remove trailing commas before closing braces/brackets."""
        return re.sub(r",\s*([}\]])", r"\1", text)

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
