"""Tests for agents — segmentation, extraction, synthesis (unit tests, no LLM)."""

import pytest

from sbs.models.conversation import NormalizedConversation, NormalizedMessage
from sbs.models.extraction import ConceptItem, ExtractedKnowledge, InsightItem
from sbs.agents.segmentation import _format_messages, SHORT_CONVERSATION_THRESHOLD
from sbs.agents.synthesis import _slugify, _generate_source_notes


class TestSegmentation:
    def test_format_messages(self):
        messages = [
            NormalizedMessage(role="user", content="Hello"),
            NormalizedMessage(role="assistant", content="Hi there!"),
        ]
        formatted = _format_messages(messages)
        assert "[0] user: Hello" in formatted
        assert "[1] assistant: Hi there!" in formatted

    def test_short_threshold(self):
        """Short conversations (< 20 messages) should get single segment."""
        assert SHORT_CONVERSATION_THRESHOLD == 20

    def test_format_truncates_long_messages(self):
        messages = [NormalizedMessage(role="user", content="x" * 1000)]
        formatted = _format_messages(messages)
        # Content is truncated to 500 chars in the format
        assert len(formatted) < 600


class TestSynthesis:
    def test_slugify_basic(self):
        assert _slugify("Hello World") == "hello-world"

    def test_slugify_special_chars(self):
        assert _slugify("What's the deal?!") == "whats-the-deal"

    def test_slugify_long_text(self):
        slug = _slugify("a" * 100)
        assert len(slug) <= 60

    def test_slugify_spaces_and_underscores(self):
        assert _slugify("hello  world__test") == "hello-world-test"

    def test_generate_source_notes(self):
        convs = [
            NormalizedConversation(
                id="abc123", title="Test Chat", source="chatgpt",
                created_at="2026-01-01T00:00:00Z",
                messages=[NormalizedMessage(role="user", content="hi")],
                raw_message_count=1,
            ),
        ]
        extractions = [
            ExtractedKnowledge(
                segment_id="abc123-seg-0", conversation_id="abc123",
                topic_label="Testing", summary="About testing",
                concepts=[ConceptItem(name="Unit Test", description="Testing units")],
            ),
        ]
        source_notes = _generate_source_notes(convs, extractions)
        assert len(source_notes) == 1
        note = source_notes[0]
        assert note.type == "source"
        assert "Test Chat" in note.body
        assert note.frontmatter.source_type == "chatgpt"

    def test_generate_source_notes_multiple(self):
        convs = [
            NormalizedConversation(
                id="c1", title="Chat 1", source="chatgpt",
                created_at="2026-01-01T00:00:00Z",
                messages=[NormalizedMessage(role="user", content="hi")],
                raw_message_count=1,
            ),
            NormalizedConversation(
                id="c2", title="Chat 2", source="claude",
                created_at="2026-01-02T00:00:00Z",
                messages=[NormalizedMessage(role="user", content="hey")],
                raw_message_count=2,
            ),
        ]
        source_notes = _generate_source_notes(convs, [])
        assert len(source_notes) == 2
        assert source_notes[0].frontmatter.source_type == "chatgpt"
        assert source_notes[1].frontmatter.source_type == "claude"

    def test_source_note_contains_topics(self):
        convs = [
            NormalizedConversation(
                id="x", title="Topic Chat", source="claude",
                created_at="2026-01-01T00:00:00Z",
                messages=[NormalizedMessage(role="user", content="hi")],
                raw_message_count=1,
            ),
        ]
        extractions = [
            ExtractedKnowledge(
                segment_id="x-seg-0", conversation_id="x",
                topic_label="Machine Learning", summary="Discussion about ML"
            ),
            ExtractedKnowledge(
                segment_id="x-seg-1", conversation_id="x",
                topic_label="Deep Learning", summary="Discussion about DL"
            ),
        ]
        notes = _generate_source_notes(convs, extractions)
        assert "Machine Learning" in notes[0].body
        assert "Deep Learning" in notes[0].body


class TestSegmentationShortConversation:
    @pytest.mark.asyncio
    async def test_short_conversation_single_segment(self):
        """Short conversations (< 20 messages) return single segment without LLM."""
        from sbs.agents.segmentation import _segment_single
        from sbs.config import Config

        conv = NormalizedConversation(
            id="test-conv", title="Short Chat", source="chatgpt",
            created_at="2026-01-01T00:00:00Z",
            messages=[
                NormalizedMessage(role="user", content=f"Message {i}")
                for i in range(5)
            ],
            raw_message_count=5,
        )
        config = Config()
        # LLM should not be called — pass None as LLM client
        segments = await _segment_single(conv, None, config)  # type: ignore[arg-type]
        assert len(segments) == 1
        assert segments[0].topic_label == "Short Chat"
        assert len(segments[0].messages) == 5
