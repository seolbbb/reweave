"""Tests for Google Gemini provider adapter (no real API calls)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

from sbs.llm.providers.google import GoogleProvider


class Payload(BaseModel):
    title: str
    count: int


@pytest.mark.asyncio
async def test_structured_call_parses_response(monkeypatch):
    provider = GoogleProvider(api_key="test-key")

    class FakeUsage:
        prompt_token_count = 12
        candidates_token_count = 5

    class FakeResponse:
        parsed = {"title": "Gemini", "count": 3}
        usage_metadata = FakeUsage()

    async def fake_call_with_retry(**kwargs: Any) -> Any:
        assert kwargs["model"] == "gemini-3-pro-preview"
        config = kwargs["config"]
        assert "response_schema" in config
        assert "response_json_schema" not in config
        return FakeResponse()

    monkeypatch.setattr(provider, "_call_with_retry", fake_call_with_retry)

    result, usage = await provider.structured_call(
        model="gemini-3-pro-preview",
        system="You are a test runner",
        user="Return payload",
        schema=Payload,
    )

    assert result == Payload(title="Gemini", count=3)
    assert usage.input_tokens == 12
    assert usage.output_tokens == 5
    assert usage.model == "gemini-3-pro-preview"


@pytest.mark.asyncio
async def test_structured_call_text_fallback(monkeypatch):
    provider = GoogleProvider(api_key="test-key")

    class FakeResponse:
        parsed = None
        text = '```json\n{"title":"Fallback","count":1}\n```'
        usage_metadata = None

    async def fake_call_with_retry(**_: Any) -> Any:
        return FakeResponse()

    monkeypatch.setattr(provider, "_call_with_retry", fake_call_with_retry)

    result, usage = await provider.structured_call(
        model="gemini-3-pro-preview",
        system="sys",
        user="user",
        schema=Payload,
    )

    assert result == Payload(title="Fallback", count=1)
    assert usage.input_tokens == 0
    assert usage.output_tokens == 0


@pytest.mark.asyncio
async def test_structured_call_recovers_trailing_comma_json(monkeypatch):
    provider = GoogleProvider(api_key="test-key")

    class FakeResponse:
        parsed = None
        text = 'Result:\n```json\n{"title":"Recovered","count":2,}\n```'
        usage_metadata = None

    async def fake_call_with_retry(**_: Any) -> Any:
        return FakeResponse()

    monkeypatch.setattr(provider, "_call_with_retry", fake_call_with_retry)

    result, _usage = await provider.structured_call(
        model="gemini-3-pro-preview",
        system="sys",
        user="user",
        schema=Payload,
    )

    assert result == Payload(title="Recovered", count=2)


@pytest.mark.asyncio
async def test_structured_call_uses_valid_candidate_part(monkeypatch):
    provider = GoogleProvider(api_key="test-key")

    class Part:
        def __init__(self, text: str):
            self.text = text

    class Content:
        def __init__(self, texts: list[str]):
            self.parts = [Part(t) for t in texts]

    class Candidate:
        def __init__(self, texts: list[str]):
            self.content = Content(texts)

    class FakeResponse:
        parsed = None
        text = None
        usage_metadata = None
        candidates = [
            Candidate(["not json"]),
            Candidate(['{"title":"FromCandidate","count":7}']),
        ]

    async def fake_call_with_retry(**_: Any) -> Any:
        return FakeResponse()

    monkeypatch.setattr(provider, "_call_with_retry", fake_call_with_retry)

    result, _usage = await provider.structured_call(
        model="gemini-3-pro-preview",
        system="sys",
        user="user",
        schema=Payload,
    )

    assert result == Payload(title="FromCandidate", count=7)


@pytest.mark.asyncio
async def test_text_call_maps_usage_dict(monkeypatch):
    provider = GoogleProvider(api_key="test-key")

    class FakeResponse:
        text = "plain text"
        usage_metadata = {"prompt_token_count": 9, "candidates_token_count": 2}

    async def fake_call_with_retry(**_: Any) -> Any:
        return FakeResponse()

    monkeypatch.setattr(provider, "_call_with_retry", fake_call_with_retry)

    text, usage = await provider.text_call(
        model="gemini-3-flash-preview",
        system="sys",
        user="user",
    )

    assert text == "plain text"
    assert usage.input_tokens == 9
    assert usage.output_tokens == 2
    assert usage.model == "gemini-3-flash-preview"


@pytest.mark.asyncio
async def test_call_with_retry_retries_on_429(monkeypatch):
    provider = GoogleProvider(api_key="test-key")

    from google.genai import errors

    class FakeModels:
        def __init__(self):
            self.calls = 0

        async def generate_content(self, **_: Any) -> Any:
            self.calls += 1
            if self.calls < 3:
                raise errors.APIError(429, {"error": {"message": "rate limited"}})
            return {"ok": True}

    class FakeClient:
        def __init__(self):
            self.models = FakeModels()

    async def fake_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("sbs.llm.providers.google.asyncio.sleep", fake_sleep)
    monkeypatch.setattr(provider, "_client", FakeClient())

    result = await provider._call_with_retry(model="gemini-3-flash-preview", contents="hello")
    assert result == {"ok": True}


def test_requires_google_api_key():
    with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
        GoogleProvider(api_key="")
