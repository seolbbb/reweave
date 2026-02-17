"""Tests for Google Gemini provider adapter (no real API calls)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

from sbs.config import Config
from sbs.llm.providers.google import GoogleProvider
from sbs.llm.providers.google_quota import GoogleQuotaLimiter


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
    monkeypatch.setattr("sbs.llm.providers.google.random.uniform", lambda _a, _b: 0.0)
    monkeypatch.setattr(provider, "_client", FakeClient())

    result = await provider._call_with_retry(model="gemini-3-flash-preview", contents="hello")
    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_call_with_retry_uses_retry_info_delay(monkeypatch):
    provider = GoogleProvider(api_key="test-key")
    delays: list[float] = []

    from google.genai import errors

    class FakeModels:
        def __init__(self):
            self.calls = 0

        async def generate_content(self, **_: Any) -> Any:
            self.calls += 1
            if self.calls == 1:
                raise errors.APIError(
                    429,
                    {
                        "error": {
                            "message": "quota exceeded",
                            "details": [
                                {
                                    "@type": "type.googleapis.com/google.rpc.RetryInfo",
                                    "retryDelay": "43s",
                                }
                            ],
                        }
                    },
                )
            return {"ok": True}

    class FakeClient:
        def __init__(self):
            self.models = FakeModels()

    async def fake_sleep(seconds: float) -> None:
        delays.append(seconds)

    monkeypatch.setattr("sbs.llm.providers.google.asyncio.sleep", fake_sleep)
    monkeypatch.setattr(provider, "_client", FakeClient())

    result = await provider._call_with_retry(model="gemini-3-flash-preview", contents="hello")
    assert result == {"ok": True}
    assert delays and delays[0] == 43.0


@pytest.mark.asyncio
async def test_structured_call_uses_quota_limiter(monkeypatch):
    config = Config(
        provider="google",
        google_enforce_quota=True,
        google_rpm_limit=1000,
        google_tpm_limit=1_000_000,
        google_rpd_limit=10_000,
    )
    provider = GoogleProvider(api_key="test-key", config=config)

    class FakeLimiter:
        def __init__(self):
            self.acquired: list[int] = []
            self.reconciled: list[tuple[int, int]] = []

        async def acquire(self, estimated_tokens: int) -> int:
            self.acquired.append(estimated_tokens)
            return estimated_tokens

        async def reconcile(self, *, reserved_tokens: int, actual_tokens: int) -> None:
            self.reconciled.append((reserved_tokens, actual_tokens))

        async def snapshot(self) -> dict[str, float | int]:
            return {
                "rpm_used": 1,
                "rpm_limit": 1,
                "tpm_used": 1,
                "tpm_limit": 1,
                "rpd_used": 1,
                "rpd_limit": 1,
                "total_wait_seconds": 0.0,
            }

    class FakeUsage:
        prompt_token_count = 12
        candidates_token_count = 5

    class FakeResponse:
        parsed = {"title": "Gemini", "count": 3}
        usage_metadata = FakeUsage()

    async def fake_call_with_retry(**_: Any) -> Any:
        return FakeResponse()

    limiter = FakeLimiter()
    monkeypatch.setattr(provider, "_quota_limiter", limiter)
    monkeypatch.setattr(provider, "_call_with_retry", fake_call_with_retry)

    _result, _usage = await provider.structured_call(
        model="gemini-3-flash-preview",
        system="sys",
        user="user",
        schema=Payload,
        max_tokens=100,
    )

    assert len(limiter.acquired) == 1
    assert limiter.acquired[0] > 0
    assert limiter.reconciled == [(limiter.acquired[0], 17)]


class _Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.mark.asyncio
async def test_quota_limiter_waits_for_rpm(monkeypatch):
    clock = _Clock()
    limiter = GoogleQuotaLimiter(rpm_limit=2, tpm_limit=1000, rpd_limit=1000, time_fn=clock)
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock.now += seconds

    monkeypatch.setattr("sbs.llm.providers.google_quota.asyncio.sleep", fake_sleep)

    await limiter.acquire(estimated_tokens=10)
    await limiter.acquire(estimated_tokens=10)
    await limiter.acquire(estimated_tokens=10)

    assert sleeps
    assert sleeps[0] >= 60.0


@pytest.mark.asyncio
async def test_quota_limiter_waits_for_tpm(monkeypatch):
    clock = _Clock()
    limiter = GoogleQuotaLimiter(rpm_limit=1000, tpm_limit=100, rpd_limit=1000, time_fn=clock)
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock.now += seconds

    monkeypatch.setattr("sbs.llm.providers.google_quota.asyncio.sleep", fake_sleep)

    await limiter.acquire(estimated_tokens=80)
    await limiter.acquire(estimated_tokens=50)

    assert sleeps
    assert sleeps[0] >= 60.0


@pytest.mark.asyncio
async def test_quota_limiter_waits_for_rpd(monkeypatch):
    clock = _Clock()
    limiter = GoogleQuotaLimiter(rpm_limit=1000, tpm_limit=1000, rpd_limit=2, time_fn=clock)
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock.now += seconds

    monkeypatch.setattr("sbs.llm.providers.google_quota.asyncio.sleep", fake_sleep)

    await limiter.acquire(estimated_tokens=10)
    await limiter.acquire(estimated_tokens=10)
    await limiter.acquire(estimated_tokens=10)

    assert sleeps
    assert sleeps[0] >= 86_400.0


@pytest.mark.asyncio
async def test_quota_limiter_reconcile_adds_extra_tokens():
    clock = _Clock()
    limiter = GoogleQuotaLimiter(rpm_limit=1000, tpm_limit=1000, rpd_limit=1000, time_fn=clock)

    reserved = await limiter.acquire(estimated_tokens=100)
    await limiter.reconcile(reserved_tokens=reserved, actual_tokens=150)
    snapshot = await limiter.snapshot()

    assert snapshot["tpm_used"] == 150


def test_requires_google_api_key():
    with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
        GoogleProvider(api_key="")
