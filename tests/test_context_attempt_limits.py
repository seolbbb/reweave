"""Actual provider-send limits with synthetic HTTP and isolated checkpoint databases."""

import json
from types import SimpleNamespace

import httpx
import pytest

from reweave.analysis_policy import (
    AnalysisLimitError,
    AnalysisPolicyStore,
    BudgetedProvider,
    InterruptibleProvider,
)
from reweave.archive import ArchiveStore
from reweave.context_chunking import ChunkStore, PartialAnalysisError
from reweave.llm import FailoverLLMProvider, LLMSettings, ProviderConnectionChangedError


def brief():
    return {
        "main_subject": "Synthetic source",
        "user_goal": "Retain decisions",
        "important_outcomes": [],
        "decisions": [],
        "lessons": [],
        "unresolved_questions": [],
        "actions": [],
    }


@pytest.fixture
def runtime(tmp_path, fixtures_dir, monkeypatch):
    archive = ArchiveStore(tmp_path / "archive.db")
    archive.import_directory(fixtures_dir)
    source_id = archive.search("Obsidian", limit=1)[0].conversation_id
    sent = []
    success_key = {"value": "last"}

    def post(url, **kwargs):
        key = kwargs.get("headers", {}).get("Authorization", "").removeprefix("Bearer ")
        key = key or kwargs.get("headers", {}).get("x-api-key")
        key = key or kwargs.get("params", {}).get("key")
        sent.append(key)
        request = httpx.Request("POST", "https://synthetic.invalid")
        if key != success_key["value"]:
            return httpx.Response(429, request=request)
        value = json.dumps({"brief": brief(), "items": []})
        if ":generateContent" in url:
            result = {"candidates": [{"content": {"parts": [{"text": value}]}}]}
        elif url.endswith("/messages"):
            result = {"content": [{"text": value}]}
        else:
            result = {"choices": [{"message": {"content": value}}]}
        return httpx.Response(200, request=request, json=result)

    monkeypatch.setattr(httpx, "post", post)
    runner = ChunkStore(archive.db_path)
    args = dict(
        source_id=source_id,
        source_fingerprint="synthetic-source-v1",
        analysis_config_key="synthetic-config-v1",
        explicit_generation=1,
        messages=[
            SimpleNamespace(id="message", index=0, role="user", timestamp=None, content="Atlas.")
        ],
        max_payload_chars=2000,
        normalize_chunk=lambda raw, _: {
            **raw,
            "dropped_items": 0,
            "deduplicated_items": 0,
        },
        call_synthesis=lambda _: pytest.fail("One segment never needs synthesis"),
        normalize_synthesis=lambda raw, _: raw,
    )
    return runner, args, sent, success_key


def provider(keys, provider_name="openai"):
    return FailoverLLMProvider(
        LLMSettings(provider=provider_name, model="synthetic", api_key=""),
        tuple(SimpleNamespace(key_id=key, label=key, api_key=key) for key in keys),
    )


def call(value):
    return lambda *_: value.generate_json(
        system="Synthetic rules", user="Synthetic source", model="synthetic", max_tokens=20
    )


@pytest.mark.parametrize("provider_name", ["openai", "anthropic", "gemini"])
def test_every_failed_and_successful_key_counts_once(runtime, provider_name):
    runner, args, sent, _ = runtime
    value = provider(["first", "second", "last"], provider_name)
    policy = AnalysisPolicyStore(runner.db_path)
    value = BudgetedProvider(InterruptibleProvider(value, lambda: False), policy)
    result = runner.run(**args, call_chunk=call(value))
    assert sent == ["first", "second", "last"]
    assert result.coverage.provider_calls == 3
    assert policy.usage()["reserved_attempts"] == 3
    cached = runner.run(**args, call_chunk=lambda _: pytest.fail("Reuse completed checkpoint"))
    assert cached.coverage.provider_calls == 3


def test_source_and_relationship_share_eight_send_invocation_limit(runtime):
    runner, args, sent, _ = runtime
    first = provider([*(f"failed-{i}" for i in range(6)), "last"])
    completed = runner.run(**args, call_chunk=call(first), max_calls_per_invocation=7)
    assert completed.coverage.provider_calls == len(sent) == 7
    followup = dict(
        run_key=completed.coverage.run_key,
        input_fingerprint="synthetic-pairs",
        call=call(provider(["failed-match", "last"])),
        normalize=lambda _: {"matches": []},
    )
    with pytest.raises(PartialAnalysisError) as paused:
        runner.run_followup(**followup)
    assert paused.value.reason == "invocation_limit"
    assert paused.value.coverage.provider_calls == len(sent) == 8
    assert not paused.value.coverage.complete
    restarted = ChunkStore(runner.db_path)
    restarted.run(**args, call_chunk=lambda _: pytest.fail("Source checkpoint must survive"))
    assert restarted.run_followup(**followup) == {"matches": []}
    assert restarted.coverage(completed.coverage.run_key).provider_calls == len(sent) == 10


def test_source_limit_blocks_a_later_key_before_send(runtime):
    runner, args, sent, _ = runtime
    value = provider(["first", "second", "last"])
    with pytest.raises(PartialAnalysisError) as paused:
        runner.run(**args, call_chunk=call(value), max_total_calls=2)
    assert paused.value.reason == "total_call_limit"
    assert paused.value.coverage.provider_calls == len(sent) == 2
    assert paused.value.coverage.completed_segments == 0
    with pytest.raises(PartialAnalysisError):
        ChunkStore(runner.db_path).run(**args, call_chunk=call(value), max_total_calls=2)
    assert len(sent) == 2


def test_relationship_cannot_send_attempt_257_after_restart(runtime):
    runner, args, sent, _ = runtime
    completed = runner.run(**args, call_chunk=call(provider(["last"])))
    # Represent 255 previously sent attempts, including earlier interrupted invocations.
    with runner._connect() as conn:
        conn.execute(
            "UPDATE context_chunk_runs SET provider_calls=255 WHERE run_key=?",
            (completed.coverage.run_key,),
        )
    followup = dict(
        run_key=completed.coverage.run_key,
        input_fingerprint="synthetic-pairs",
        call=call(provider(["failed-match", "last"])),
        normalize=lambda _: {"matches": []},
    )
    with pytest.raises(PartialAnalysisError) as paused:
        ChunkStore(runner.db_path).run_followup(**followup)
    assert paused.value.reason == "total_call_limit"
    assert paused.value.coverage.provider_calls == 256
    assert sent == ["last", "failed-match"]
    with pytest.raises(PartialAnalysisError):
        ChunkStore(runner.db_path).run_followup(**followup)
    assert len(sent) == 2


@pytest.mark.parametrize("error", [AnalysisLimitError, ProviderConnectionChangedError])
@pytest.mark.parametrize("deny_after", [0, 1])
def test_pre_send_denials_preserve_prior_sent_key_attempts(runtime, error, deny_after):
    runner, args, sent, _ = runtime
    value = provider(["first", "last"])

    def guard():
        if len(sent) >= deny_after:
            raise error("Synthetic pre-send denial")

    value.before_attempt = guard
    with pytest.raises(PartialAnalysisError) as paused:
        runner.run(**args, call_chunk=call(value))
    assert paused.value.coverage.provider_calls == len(sent) == deny_after
    assert paused.value.coverage.completed_segments == 0
    assert not paused.value.coverage.complete

