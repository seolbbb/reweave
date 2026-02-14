"""Tests for Pydantic data models."""

from sbs.models import (
    ConceptItem,
    CostSummary,
    DraftNote,
    ExtractedKnowledge,
    MOC,
    NormalizedConversation,
    NormalizedMessage,
    NoteLink,
    NoteFrontmatter,
    PipelineState,
    Segment,
    ValidationReport,
)
from sbs.config import Config


class TestNormalizedMessage:
    def test_basic_message(self):
        msg = NormalizedMessage(role="user", content="hello")
        assert msg.role == "user"
        assert msg.content == "hello"
        assert msg.timestamp is None
        assert msg.metadata == {}

    def test_message_with_metadata(self):
        msg = NormalizedMessage(
            role="assistant", content="hi", timestamp="2026-01-01T00:00:00Z",
            metadata={"model": "gpt-4"}
        )
        assert msg.timestamp == "2026-01-01T00:00:00Z"
        assert msg.metadata["model"] == "gpt-4"


class TestNormalizedConversation:
    def test_basic_conversation(self):
        msgs = [NormalizedMessage(role="user", content="hi")]
        conv = NormalizedConversation(
            id="abc123", title="Test Chat", source="chatgpt",
            created_at="2026-01-01T00:00:00Z", messages=msgs, raw_message_count=1
        )
        assert conv.id == "abc123"
        assert conv.source == "chatgpt"
        assert len(conv.messages) == 1

    def test_serialization_roundtrip(self):
        msgs = [NormalizedMessage(role="user", content="test")]
        conv = NormalizedConversation(
            id="x", title="T", source="claude",
            created_at="2026-01-01T00:00:00Z", messages=msgs, raw_message_count=1
        )
        data = conv.model_dump()
        restored = NormalizedConversation.model_validate(data)
        assert restored == conv


class TestSegment:
    def test_segment_creation(self):
        seg = Segment(
            id="conv1-seg-0", conversation_id="conv1", topic_label="intro",
            messages=[], start_index=0, end_index=5
        )
        assert seg.topic_label == "intro"


class TestExtractedKnowledge:
    def test_with_concepts(self):
        ek = ExtractedKnowledge(
            segment_id="s1", conversation_id="c1", topic_label="test",
            concepts=[ConceptItem(name="Zettelkasten", description="Note method")],
            summary="About notes"
        )
        assert len(ek.concepts) == 1
        assert ek.concepts[0].name == "Zettelkasten"


class TestDraftNote:
    def test_permanent_note(self):
        fm = NoteFrontmatter(
            type="permanent", created="2026-01-01T00:00:00Z",
            tags=["test"], source_type="chatgpt", source_ref="SRC-1"
        )
        note = DraftNote(
            id="20260101000000", filename="20260101000000-test.md",
            type="permanent", title="Test Note", frontmatter=fm, body="Content"
        )
        assert note.type == "permanent"
        assert note.frontmatter.status == "seedling"


class TestNoteLink:
    def test_link(self):
        link = NoteLink(
            source_note_id="a", target_note_id="b",
            relationship="supports", description="A supports B"
        )
        assert link.relationship == "supports"


class TestMOC:
    def test_moc(self):
        moc = MOC(id="moc1", title="Test MOC", filename="MOC-test.md", note_ids=["a", "b"])
        assert len(moc.note_ids) == 2


class TestPipelineState:
    def test_default_state(self):
        config = Config()
        state = PipelineState(config=config)
        assert state.completed_stages == []
        assert state.conversations == []
        assert state.cost.total_input_tokens == 0


class TestValidationReport:
    def test_empty_report(self):
        report = ValidationReport()
        assert report.score == 0.0
        assert report.issues == []


class TestCostSummary:
    def test_defaults(self):
        cost = CostSummary()
        assert cost.estimated_cost_usd == 0.0
