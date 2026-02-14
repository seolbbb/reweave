"""Tests for agents — segmentation, extraction, synthesis, linking (unit tests, no LLM)."""

import pytest

from sbs.models.conversation import NormalizedConversation, NormalizedMessage
from sbs.models.extraction import ConceptItem, ExtractedKnowledge, InsightItem
from sbs.models.note import DraftNote, NoteLink, NoteFrontmatter
from sbs.agents.segmentation import _format_messages, SHORT_CONVERSATION_THRESHOLD
from sbs.agents.synthesis import _slugify, _generate_source_notes
from sbs.agents.linking import _create_mocs, _inject_links, ClusterItem


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


def _make_note(note_id: str, title: str, tags: list[str] | None = None) -> DraftNote:
    fm = NoteFrontmatter(
        type="permanent", created="2026-01-01T00:00:00Z",
        tags=tags or ["test"],
    )
    return DraftNote(
        id=note_id, filename=f"{note_id}-test.md", type="permanent",
        title=title, frontmatter=fm, body="Content",
    )


class TestLinking:
    def test_create_mocs_minimum_3(self):
        notes = {f"n{i}": _make_note(f"n{i}", f"Note {i}") for i in range(5)}
        clusters = [
            ClusterItem(cluster_label="Big Cluster", note_ids=["n0", "n1", "n2", "n3"]),
            ClusterItem(cluster_label="Small Cluster", note_ids=["n4"]),
        ]
        mocs = _create_mocs(clusters, notes)
        assert len(mocs) == 1
        assert mocs[0].title == "Big Cluster"
        assert len(mocs[0].note_ids) == 4

    def test_create_mocs_empty(self):
        mocs = _create_mocs([], {})
        assert mocs == []

    def test_inject_links(self):
        notes = [_make_note("a", "A"), _make_note("b", "B"), _make_note("c", "C")]
        links = [
            NoteLink(source_note_id="a", target_note_id="b",
                     relationship="similar", description="test"),
        ]
        updated = _inject_links(notes, links)
        a_related = updated[0].frontmatter.related
        b_related = updated[1].frontmatter.related
        assert "[[b]]" in a_related
        assert "[[a]]" in b_related
        # C should have no links
        assert updated[2].frontmatter.related == []

    def test_inject_links_bidirectional(self):
        notes = [_make_note("x", "X"), _make_note("y", "Y")]
        links = [
            NoteLink(source_note_id="x", target_note_id="y",
                     relationship="extends", description="test"),
        ]
        updated = _inject_links(notes, links)
        assert "[[y]]" in updated[0].frontmatter.related
        assert "[[x]]" in updated[1].frontmatter.related


class TestValidation:
    def test_check_frontmatter_missing_created(self):
        from sbs.agents.validation import _check_frontmatter
        note = _make_note("v1", "Validation Test")
        note.frontmatter.created = ""
        issues = _check_frontmatter([note])
        assert any(i.category == "frontmatter" and i.severity == "error" for i in issues)

    def test_check_frontmatter_no_tags(self):
        from sbs.agents.validation import _check_frontmatter
        note = _make_note("v2", "No Tags")
        note.frontmatter.tags = []
        issues = _check_frontmatter([note])
        assert any(i.category == "frontmatter" and "tags" in i.message for i in issues)

    def test_check_links_orphans(self):
        from sbs.agents.validation import _check_links
        notes = [_make_note("a", "A"), _make_note("b", "B"), _make_note("c", "C")]
        links = [NoteLink(source_note_id="a", target_note_id="b",
                          relationship="similar", description="test")]
        issues, orphan_count = _check_links(notes, links)
        assert orphan_count == 1  # 'c' is orphan

    def test_check_links_excessive(self):
        from sbs.agents.validation import _check_links, MAX_LINKS_PER_NOTE
        notes = [_make_note("hub", "Hub")]
        links = [
            NoteLink(source_note_id="hub", target_note_id=f"t{i}",
                     relationship="similar", description="test")
            for i in range(MAX_LINKS_PER_NOTE + 5)
        ]
        issues, _ = _check_links(notes, links)
        assert any("links" in i.message for i in issues)
