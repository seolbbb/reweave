"""Tests for output writer, templates, and naming."""

import pytest

from sbs.config import Config
from sbs.models.note import DraftNote, MOC, NoteFrontmatter
from sbs.models.pipeline import PipelineState
from sbs.output.naming import sanitize_filename, slugify
from sbs.output.templates import render_moc, render_permanent_note, render_source_note
from sbs.output.writer import write_vault


class TestNaming:
    def test_slugify(self):
        assert slugify("Hello World") == "hello-world"

    def test_slugify_max_length(self):
        assert len(slugify("a" * 100, max_length=30)) <= 30

    def test_sanitize_filename(self):
        assert sanitize_filename('file<>:"/\\|?*.md') == "file.md"


class TestTemplates:
    @pytest.fixture()
    def sample_note(self):
        fm = NoteFrontmatter(
            type="permanent", created="2026-01-01T00:00:00Z",
            tags=["test", "note"], source_type="chatgpt",
            source_ref="[[SRC-chatgpt-abc]]",
            conversation_date="2026-01-01T00:00:00Z",
            participants=["user", "assistant"],
        )
        return DraftNote(
            id="20260101000000", filename="20260101000000-test-note.md",
            type="permanent", title="Test Note Title",
            frontmatter=fm, body="This is the note content.\n\nSecond paragraph.",
            source_segment_ids=["abc-seg-0"],
        )

    def test_render_permanent_note(self, sample_note):
        rendered = render_permanent_note(sample_note)
        assert "---" in rendered
        assert "# Test Note Title" in rendered
        assert "This is the note content." in rendered
        assert "type: permanent" in rendered
        assert "abc-seg-0" in rendered

    def test_render_source_note(self, sample_note):
        sample_note.frontmatter.type = "source"
        rendered = render_source_note(sample_note)
        assert "---" in rendered
        assert "This is the note content." in rendered

    def test_render_moc(self):
        moc = MOC(
            id="moc-1", title="Test MOC", filename="MOC-test.md",
            tags=["testing"], note_ids=["note-1", "note-2"],
        )
        rendered = render_moc(moc)
        assert "# Test MOC" in rendered
        assert "[[note-1]]" in rendered
        assert "[[note-2]]" in rendered
        assert "type: moc" in rendered


class TestWriter:
    def test_write_vault_creates_directories(self, tmp_path):
        config = Config(output_dir=tmp_path / "vault")
        state = PipelineState(config=config)

        fm = NoteFrontmatter(
            type="permanent", created="2026-01-01T00:00:00Z",
            tags=["test"], source_type="chatgpt",
        )
        state.draft_notes = [
            DraftNote(
                id="n1", filename="n1-test.md", type="permanent",
                title="Test", frontmatter=fm, body="Content",
            )
        ]
        state.source_notes = [
            DraftNote(
                id="s1", filename="s1-source.md", type="source",
                title="Source", frontmatter=NoteFrontmatter(
                    type="source", created="2026-01-01T00:00:00Z",
                    tags=["source"],
                ),
                body="Source content",
            )
        ]
        state.mocs = [
            MOC(id="moc-1", title="MOC", filename="MOC-test.md", note_ids=["n1"])
        ]

        write_vault(state)

        vault = tmp_path / "vault"
        assert (vault / "notes" / "n1-test.md").exists()
        assert (vault / "sources" / "s1-source.md").exists()
        assert (vault / "mocs" / "MOC-test.md").exists()

    def test_write_vault_content(self, tmp_path):
        config = Config(output_dir=tmp_path / "vault")
        state = PipelineState(config=config)

        fm = NoteFrontmatter(
            type="permanent", created="2026-01-01T00:00:00Z", tags=["test"],
        )
        state.draft_notes = [
            DraftNote(
                id="n1", filename="n1-hello.md", type="permanent",
                title="Hello World", frontmatter=fm, body="Hello content",
            )
        ]

        write_vault(state)

        content = (tmp_path / "vault" / "notes" / "n1-hello.md").read_text(encoding="utf-8")
        assert "# Hello World" in content
        assert "Hello content" in content
