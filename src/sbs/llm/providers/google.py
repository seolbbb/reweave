"""Google GenAI SDK provider implementation."""

from __future__ import annotations

import asyncio
import json
import random
import re
from time import monotonic
from typing import Any

from pydantic import BaseModel
from rich.console import Console

from sbs.config import Config
from sbs.llm.providers.google_quota import GoogleQuotaLimiter
from sbs.models.pipeline import TokenUsage


class GoogleProvider:
    """Google Gemini API provider (AI Studio key auth)."""

    def __init__(self, api_key: str, config: Config | None = None):
        if not api_key:
            raise ValueError("GOOGLE_API_KEY is required when provider is 'google'")

        from google import genai

        self._client = genai.Client(api_key=api_key).aio
        self._config = config
        self._console = Console()
        self._quota_log_interval_seconds = 30.0
        self._last_quota_log_at = 0.0

        if config is not None and config.google_enforce_quota:
            self._quota_limiter: GoogleQuotaLimiter | None = GoogleQuotaLimiter(
                rpm_limit=config.effective_google_rpm_limit(),
                tpm_limit=config.effective_google_tpm_limit(),
                rpd_limit=config.effective_google_rpd_limit(),
            )
        else:
            self._quota_limiter = None

    async def structured_call(
        self,
        model: str,
        system: str,
        user: str,
        schema: type[BaseModel],
        max_tokens: int = 4096,
    ) -> tuple[BaseModel, TokenUsage]:
        """Make an API call expecting JSON output compatible with a Pydantic schema."""
        reserved_tokens = await self._acquire_quota(
            system=system,
            user=user,
            max_tokens=max_tokens,
        )
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
        usage = self._build_usage(response, model)
        await self._reconcile_quota(reserved_tokens=reserved_tokens, usage=usage)
        await self._maybe_log_quota()
        return parsed, usage

    async def text_call(
        self,
        model: str,
        system: str,
        user: str,
        max_tokens: int = 4096,
    ) -> tuple[str, TokenUsage]:
        """Make a plain text API call."""
        reserved_tokens = await self._acquire_quota(
            system=system,
            user=user,
            max_tokens=max_tokens,
        )
        response = await self._call_with_retry(
            model=model,
            contents=user,
            config={
                "system_instruction": system,
                "max_output_tokens": max_tokens,
            },
        )

        text = self._extract_text(response)
        usage = self._build_usage(response, model)
        await self._reconcile_quota(reserved_tokens=reserved_tokens, usage=usage)
        await self._maybe_log_quota()
        return text, usage

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
                status_code = (
                    code
                    if isinstance(code, int)
                    else status
                    if isinstance(status, int)
                    else getattr(e, "status_code", None)
                )
                if status_code == 404:
                    model = kwargs.get("model", "")
                    raise ValueError(
                        f"Google model '{model}' was not found for generateContent. "
                        "Use an available model such as 'gemini-3-flash-preview', "
                        "or set --model/--cheap-model explicitly."
                    ) from e
                should_retry = isinstance(status_code, int) and (
                    status_code == 429 or status_code >= 500
                )
                if should_retry and attempt < max_retries - 1:
                    retry_delay = self._extract_retry_delay_seconds(e)
                    if retry_delay is not None:
                        await asyncio.sleep(retry_delay)
                        continue

                    delay = delays[min(attempt, len(delays) - 1)]
                    jitter = random.uniform(0, delay)  # noqa: S311
                    await asyncio.sleep(delay + jitter)
                    continue
                raise

        raise last_error if last_error else RuntimeError("Google API call failed")

    async def _acquire_quota(self, *, system: str, user: str, max_tokens: int) -> int:
        """Reserve quota units before making a Google API request."""
        if self._quota_limiter is None:
            return 0
        estimated_tokens = self._estimate_total_tokens(system, user, max_tokens)
        return await self._quota_limiter.acquire(estimated_tokens)

    async def _reconcile_quota(self, *, reserved_tokens: int, usage: TokenUsage) -> None:
        """Adjust quota usage if actual tokens exceeded the reservation estimate."""
        if self._quota_limiter is None or reserved_tokens <= 0:
            return
        actual_tokens = usage.input_tokens + usage.output_tokens
        await self._quota_limiter.reconcile(
            reserved_tokens=reserved_tokens,
            actual_tokens=actual_tokens,
        )

    async def _maybe_log_quota(self) -> None:
        """Emit periodic quota usage diagnostics when verbose mode is enabled."""
        if self._quota_limiter is None or self._config is None or not self._config.verbose:
            return

        now = monotonic()
        if now - self._last_quota_log_at < self._quota_log_interval_seconds:
            return

        self._last_quota_log_at = now
        stats = await self._quota_limiter.snapshot()
        self._console.print(
            "  [dim]Google quota "
            f"rpm={stats['rpm_used']}/{stats['rpm_limit']} "
            f"tpm={stats['tpm_used']}/{stats['tpm_limit']} "
            f"rpd={stats['rpd_used']}/{stats['rpd_limit']} "
            f"wait={stats['total_wait_seconds']:.1f}s[/dim]"
        )

    @staticmethod
    def _estimate_total_tokens(system: str, user: str, max_tokens: int) -> int:
        """Estimate total request token consumption for quota reservation."""
        estimated_input_tokens = max(1, (len(system) + len(user) + 3) // 4)
        return estimated_input_tokens + max(1, max_tokens)

    @staticmethod
    def _extract_retry_delay_seconds(error: Exception) -> float | None:
        """Extract retry delay seconds from Google API error payload/message."""
        payload = GoogleProvider._extract_error_payload(error)
        if isinstance(payload, dict):
            delay = GoogleProvider._extract_retry_delay_from_payload(payload)
            if delay is not None:
                return delay

        message = str(error)
        match = re.search(r"retry in\s+([0-9]+(?:\.[0-9]+)?)s", message, re.IGNORECASE)
        if match:
            return float(match.group(1))
        return None

    @staticmethod
    def _extract_error_payload(error: Exception) -> dict[str, Any] | None:
        """Best-effort extraction of structured error payload from APIError."""
        response_json = getattr(error, "response_json", None)
        if isinstance(response_json, dict):
            return response_json

        details = getattr(error, "details", None)
        if isinstance(details, dict):
            return details

        for arg in getattr(error, "args", ()):
            if isinstance(arg, dict):
                return arg
        return None

    @staticmethod
    def _extract_retry_delay_from_payload(payload: dict[str, Any]) -> float | None:
        """Extract google.rpc.RetryInfo delay from JSON error details."""
        details = payload.get("error", {}).get("details", [])
        if not isinstance(details, list):
            return None

        for detail in details:
            if not isinstance(detail, dict):
                continue
            detail_type = str(detail.get("@type", ""))
            if not detail_type.endswith("google.rpc.RetryInfo"):
                continue
            retry_delay = detail.get("retryDelay")
            parsed = GoogleProvider._parse_duration_seconds(retry_delay)
            if parsed is not None:
                return parsed
        return None

    @staticmethod
    def _parse_duration_seconds(value: Any) -> float | None:
        """Parse protobuf duration strings like '43s' or '43.2s'."""
        if not isinstance(value, str):
            return None
        match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)s\s*", value)
        if not match:
            return None
        return float(match.group(1))

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
