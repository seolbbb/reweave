"""Tests for insight synthesis."""

import time

from reweave.archive import ArchivedConversation, ArchivedMessage, ArchiveStore
from reweave.insights import InsightInput, detect_report_language, generate_insight_report
from reweave.llm import LLMSettings


class FakeProvider:
    def __init__(self):
        self.calls = []

    def generate_text(self, *, system, user, model, temperature=0.2, max_tokens=4096):
        self.calls.append(
            {
                "system": system,
                "user": user,
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        return """# Connected Insights

## Overview

Selected conversations discuss linked ideas [abc#m0].

## Key concepts

- Concept A -> Concept B [abc#m0]

## Connections between conversations

- Inference: The ideas reinforce each other [abc#m0].

## Agreements, contradictions, and patterns

- The sources agree [abc#m0].

## New or surprising insights

- Inference: This is a reusable synthesis [abc#m0].

## Suggested follow-up questions

- What should be explored next?

## Source references

- [abc#m0]
"""

    def generate_json(self, *, system, user, model, temperature=0.2, max_tokens=4096):
        return {"ok": True}


def test_generate_insight_report_saves_markdown(tmp_path, fixtures_dir):
    store = ArchiveStore(tmp_path / "archive.db")
    store.import_directory(fixtures_dir)
    selected = [store.search("Zettelkasten")[0].conversation_id]
    provider = FakeProvider()

    report = generate_insight_report(
        store,
        conversation_ids=selected,
        title="Test Insight",
        settings=LLMSettings(
            provider="fake",
            model="fake-model",
            api_key="",
            max_context_chars=80_000,
        ),
        provider=provider,
    )

    assert report.title == "Test Insight"
    assert report.selected_conversation_ids == tuple(selected)
    assert "## Source references" in report.markdown
    assert store.get_insight_report(report.id) is not None


def test_generate_insight_report_chunks_large_selection(tmp_path, fixtures_dir):
    store = ArchiveStore(tmp_path / "archive.db")
    with store._connect() as conn:
        for idx in range(2):
            conv_id = f"long-{idx}"
            conn.execute(
                """
                INSERT INTO conversations (
                    id, source, title, created_at, updated_at, raw_message_count, source_path
                )
                VALUES (?, 'chatgpt', ?, '2026-01-01T00:00:00Z', NULL, 1, 'fixture')
                """,
                (conv_id, f"Long Conversation {idx}"),
            )
            conn.execute(
                """
                INSERT INTO messages (id, conversation_id, message_index, role, content, timestamp)
                VALUES (?, ?, 0, 'user', ?, '2026-01-01T00:00:00Z')
                """,
                (f"{conv_id}:0", conv_id, "biology chemistry mitochondria " * 400),
            )
    selected = ["long-0", "long-1"]
    provider = FakeProvider()

    generate_insight_report(
        store,
        conversation_ids=selected,
        settings=LLMSettings(
            provider="fake",
            model="fake-model",
            api_key="",
            max_context_chars=10_000,
        ),
        provider=provider,
    )

    assert len(provider.calls) >= 3


def test_generate_insight_report_parallelizes_chunk_analysis(tmp_path):
    store = ArchiveStore(tmp_path / "archive.db")
    with store._connect() as conn:
        for idx in range(4):
            conv_id = f"parallel-{idx}"
            conn.execute(
                """
                INSERT INTO conversations (
                    id, source, title, created_at, updated_at, raw_message_count, source_path
                )
                VALUES (?, 'chatgpt', ?, '2026-01-01T00:00:00Z', NULL, 1, 'fixture')
                """,
                (conv_id, f"Parallel Conversation {idx}"),
            )
            conn.execute(
                """
                INSERT INTO messages (id, conversation_id, message_index, role, content, timestamp)
                VALUES (?, ?, 0, 'user', ?, '2026-01-01T00:00:00Z')
                """,
                (f"{conv_id}:0", conv_id, "biology chemistry mitochondria " * 350),
            )

    class SlowProvider(FakeProvider):
        def generate_text(self, **kwargs):
            time.sleep(0.08)
            return super().generate_text(**kwargs)

    provider = SlowProvider()
    metrics = {}
    started = time.perf_counter()
    generate_insight_report(
        store,
        conversation_ids=[f"parallel-{idx}" for idx in range(4)],
        settings=LLMSettings(
            provider="fake",
            model="fake-model",
            api_key="",
            max_context_chars=10_000,
        ),
        provider=provider,
        metrics=metrics,
    )
    elapsed = time.perf_counter() - started

    assert metrics["chunk_count"] >= 4
    assert metrics["model_call_count"] == metrics["chunk_count"] + 1
    assert metrics["parallel_workers"] == 4
    assert elapsed < metrics["model_call_count"] * 0.08 * 0.7


def test_detect_report_language_for_korean_sources():
    inputs = [make_input("ko", "한국어 대화 내용과 핵심 인사이트 " * 20)]
    assert detect_report_language(inputs) == "ko"


def test_detect_report_language_for_english_sources():
    inputs = [make_input("en", "English conversation and key insights " * 20)]
    assert detect_report_language(inputs) == "en"


def test_detect_report_language_for_mixed_sources_uses_dominant_language():
    inputs = [
        make_input("ko", "한국어가 더 많은 혼합 언어 대화입니다 " * 30),
        make_input("en", "A shorter English source " * 5),
    ]

    assert detect_report_language(inputs) == "ko"


def test_detect_report_language_for_mixed_sources_can_choose_english():
    inputs = [
        make_input("en", "A much longer English source about models and evidence " * 30),
        make_input("ko", "짧은 한국어 소스 " * 3),
    ]

    assert detect_report_language(inputs) == "en"


def test_generate_insight_report_explicitly_prompts_for_korean(tmp_path):
    store = ArchiveStore(tmp_path / "archive.db")
    with store._connect() as conn:
        conn.execute(
            """
            INSERT INTO conversations (
                id, source, title, created_at, updated_at, raw_message_count, source_path
            )
            VALUES ('korean', 'chatgpt', '한국어 대화', '2026-01-01T00:00:00Z', NULL, 1, 'fixture')
            """
        )
        conn.execute(
            """
            INSERT INTO messages (id, conversation_id, message_index, role, content, timestamp)
            VALUES ('korean:0', 'korean', 0, 'user', ?, '2026-01-01T00:00:00Z')
            """,
            ("한국어로 작성된 대화와 인사이트 " * 20,),
        )
    provider = FakeProvider()

    report = generate_insight_report(
        store,
        conversation_ids=["korean"],
        settings=LLMSettings(provider="fake", model="fake-model", api_key=""),
        provider=provider,
    )

    assert "Write the entire report in Korean" in provider.calls[0]["system"]
    assert "## 개요" in report.markdown


def test_generate_insight_report_rejects_missing_conversation(tmp_path):
    store = ArchiveStore(tmp_path / "archive.db")

    try:
        generate_insight_report(
            store,
            conversation_ids=["missing"],
            settings=LLMSettings(provider="fake", model="fake-model", api_key=""),
            provider=FakeProvider(),
        )
    except ValueError as exc:
        assert "Conversation not found" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def make_input(conversation_id: str, content: str) -> InsightInput:
    return InsightInput(
        conversation=ArchivedConversation(
            id=conversation_id,
            source="chatgpt",
            title=content[:20],
            created_at="2026-01-01T00:00:00Z",
            updated_at=None,
            raw_message_count=1,
            source_path="fixture",
        ),
        messages=[
            ArchivedMessage(
                id=f"{conversation_id}:0",
                conversation_id=conversation_id,
                index=0,
                role="user",
                content=content,
                timestamp="2026-01-01T00:00:00Z",
            )
        ],
    )
