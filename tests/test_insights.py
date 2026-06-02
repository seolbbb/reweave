"""Tests for insight synthesis."""

from reweave.archive import ArchiveStore
from reweave.insights import generate_insight_report
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

Selected conversations discuss linked ideas [abc#0].

## Concept Map

- Concept A -> Concept B [abc#0]

## Connections

- Inference: The ideas reinforce each other [abc#0].

## New Insights

- Inference: This is a reusable synthesis [abc#0].

## Uncertainties

- More source review may be needed.

## Source Index

- [abc#0]
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
    assert "## Source Index" in report.markdown
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
