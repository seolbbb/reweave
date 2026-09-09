"""Conversation Brief and Context Item persistence tests."""

import sqlite3

import pytest

from reweave.archive import ArchiveStore
from reweave.archive_management import ArchiveManager
from reweave.context_library import ContextLibraryStore, EvidenceInput, ScopeInput
from reweave.web import create_app


def _seed_context(db_path, fixtures_dir):
    archive = ArchiveStore(db_path)
    archive.import_directory(fixtures_dir)
    search_result = archive.search("Obsidian", provider="claude", limit=1)[0]
    conversation = archive.get_conversation(search_result.conversation_id)
    messages = archive.get_messages(search_result.conversation_id)
    assert conversation is not None

    context = ContextLibraryStore(db_path)
    brief = context.save_brief(
        conversation_id=conversation.id,
        main_subject="Building an Obsidian knowledge system",
        user_goal="Choose a durable structure for linked project notes.",
        important_outcomes=["Prefer links over deeply nested folders."],
        decisions=["Start with a flat folder structure."],
        lessons=["Navigation and storage structure solve different problems."],
        unresolved_questions=["Which metadata should remain optional?"],
        actions=["Test the structure with one active project."],
        analysis_mode="project",
        analysis_version="context-v1",
        prompt_version="brief-v1",
        analysis_provider="openai",
        analysis_model="test-model",
    )
    item = context.create_item(
        brief_id=brief.id,
        canonical_text="The user is organizing an Obsidian vault.",
        item_type="project_fact",
        epistemic_kind="observed",
        confidence=0.92,
        scopes=[ScopeInput("project", "Obsidian"), ScopeInput("work")],
        evidence=[
            EvidenceInput(
                conversation_id=conversation.id,
                message_id=messages[0].id,
                excerpt="How should I organize my Obsidian vault?",
            )
        ],
        last_confirmed_at="2026-07-21T00:00:00+00:00",
    )
    return archive, context, conversation, messages, brief, item


def test_context_round_trip_survives_store_restart(tmp_path, fixtures_dir):
    db_path = tmp_path / "archive.db"
    _, context, conversation, messages, brief, item = _seed_context(db_path, fixtures_dir)
    second = context.create_item(
        brief_id=brief.id,
        canonical_text="Project structure should stay lightweight.",
        item_type="lesson",
        epistemic_kind="inferred",
        confidence=0.74,
        sensitivity="normal",
        scopes=[ScopeInput("project", "Obsidian", 0.9)],
        evidence=[EvidenceInput(conversation.id, messages[2].id, "context")],
    )
    context.link_items(item.id, second.id, "supports")

    reopened = ContextLibraryStore(db_path)
    stored_brief = reopened.get_brief(brief.id)
    stored_item = reopened.get_item(item.id)
    stored_second = reopened.get_item(second.id)

    assert stored_brief is not None
    assert stored_brief.source_conversation_id == conversation.id
    assert stored_brief.context_item_ids == (item.id, second.id)
    assert stored_brief.important_outcomes == ("Prefer links over deeply nested folders.",)
    assert stored_item is not None
    assert stored_item.current_version == 1
    assert stored_item.epistemic_kind == "observed"
    assert {(scope.scope_type, scope.scope_key) for scope in stored_item.scopes} == {
        ("project", "Obsidian"),
        ("work", ""),
    }
    assert stored_item.evidence[0].source_message_id == messages[0].id
    assert stored_item.evidence[0].source_title == conversation.title
    assert stored_item.evidence[0].excerpt == "How should I organize my Obsidian vault?"
    assert stored_item.versions[0].change_reason == "initial extraction"
    assert stored_second is not None
    assert stored_second.links[0].source_item_id == item.id
    assert stored_second.links[0].target_item_id == second.id

    with sqlite3.connect(db_path) as conn:
        context_schema_version = conn.execute(
            "SELECT value FROM schema_meta WHERE key = 'context_schema_version'"
        ).fetchone()[0]
    assert context_schema_version == "7"


def test_save_brief_is_idempotent_for_one_analysis_version(tmp_path, fixtures_dir):
    db_path = tmp_path / "archive.db"
    _, context, conversation, _, brief, _ = _seed_context(db_path, fixtures_dir)

    updated = context.save_brief(
        conversation_id=conversation.id,
        main_subject="Updated Obsidian structure",
        user_goal="Keep linked notes maintainable.",
        analysis_version="context-v1",
        prompt_version="brief-v2",
        analysis_provider="anthropic",
        analysis_model="test-model-2",
    )

    assert updated.id == brief.id
    assert updated.created_at == brief.created_at
    assert updated.main_subject == "Updated Obsidian structure"
    assert updated.prompt_version == "brief-v2"
    assert len(context.list_briefs()) == 1


def test_context_item_revision_preserves_immutable_history(tmp_path, fixtures_dir):
    db_path = tmp_path / "archive.db"
    _, context, _, _, _, item = _seed_context(db_path, fixtures_dir)

    revised = context.revise_item(
        item.id,
        change_reason="Direct user correction",
        canonical_text="The user is organizing an Obsidian vault for project notes.",
        confidence=1.0,
        epistemic_kind="observed",
        last_confirmed_at="2026-07-21T12:00:00+00:00",
    )

    assert revised.current_version == 2
    assert revised.canonical_text.endswith("for project notes.")
    assert revised.last_confirmed_at == "2026-07-21T12:00:00+00:00"
    assert [version.version for version in revised.versions] == [1, 2]
    assert revised.versions[0].canonical_text != revised.versions[1].canonical_text
    assert revised.versions[1].change_reason == "Direct user correction"


def test_source_deletion_preserves_context_and_evidence_snapshot(tmp_path, fixtures_dir):
    db_path = tmp_path / "archive.db"
    _, context, conversation, messages, brief, item = _seed_context(db_path, fixtures_dir)

    summary = ArchiveManager(db_path).delete_conversation(conversation.id)

    stored_brief = context.get_brief(brief.id)
    stored_item = context.get_item(item.id)
    assert summary.conversations == 1
    assert stored_brief is not None
    assert stored_brief.source_conversation_id is None
    assert stored_brief.source_record_id == conversation.id
    assert stored_brief.source_title == conversation.title
    assert stored_item is not None
    assert stored_item.evidence[0].source_conversation_id is None
    assert stored_item.evidence[0].source_message_id is None
    assert stored_item.evidence[0].source_message_record_id == messages[0].id
    assert stored_item.evidence[0].excerpt == "How should I organize my Obsidian vault?"


def test_context_store_rejects_unsafe_or_untraceable_metadata(tmp_path, fixtures_dir):
    db_path = tmp_path / "archive.db"
    _, context, conversation, messages, brief, _ = _seed_context(db_path, fixtures_dir)

    with pytest.raises(ValueError, match="between 0 and 1"):
        context.create_item(
            brief_id=brief.id,
            canonical_text="Invalid confidence",
            item_type="insight",
            epistemic_kind="observed",
            confidence=1.1,
            scopes=[ScopeInput("personal")],
            evidence=[EvidenceInput(conversation.id, messages[0].id)],
        )

    with pytest.raises(ValueError, match="project scope requires"):
        context.create_item(
            brief_id=brief.id,
            canonical_text="Missing project key",
            item_type="insight",
            epistemic_kind="observed",
            confidence=0.8,
            scopes=[ScopeInput("project")],
            evidence=[EvidenceInput(conversation.id, messages[0].id)],
        )

    with pytest.raises(LookupError, match="archived message"):
        context.create_item(
            brief_id=brief.id,
            canonical_text="Missing evidence",
            item_type="insight",
            epistemic_kind="observed",
            confidence=0.8,
            scopes=[ScopeInput("personal")],
            evidence=[EvidenceInput(conversation.id, "missing-message")],
        )

    with pytest.raises(ValueError, match="must appear"):
        context.create_item(
            brief_id=brief.id,
            canonical_text="Fabricated evidence excerpt",
            item_type="insight",
            epistemic_kind="inferred",
            confidence=0.5,
            scopes=[ScopeInput("personal")],
            evidence=[
                EvidenceInput(
                    conversation.id,
                    messages[0].id,
                    excerpt="This sentence is not in the source message.",
                )
            ],
        )


def test_app_startup_initializes_context_schema(tmp_path):
    db_path = tmp_path / "archive.db"

    app = create_app(db_path, data_dir=tmp_path / "app-data")

    assert isinstance(app.state.context_library, ContextLibraryStore)
    with sqlite3.connect(db_path) as conn:
        assert (
            conn.execute(
                "SELECT value FROM schema_meta WHERE key = 'context_schema_version'"
            ).fetchone()[0]
            == "7"
        )


def test_context_schema_v1_migrates_analysis_metadata_without_losing_briefs(tmp_path, fixtures_dir):
    db_path = tmp_path / "archive.db"
    archive = ArchiveStore(db_path)
    archive.import_directory(fixtures_dir)
    conversation = archive.get_conversation(
        archive.search("Obsidian", provider="claude", limit=1)[0].conversation_id
    )
    assert conversation is not None
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE conversation_briefs (
                id TEXT PRIMARY KEY,
                source_conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
                source_record_id TEXT NOT NULL,
                source_external_id TEXT,
                source_provider TEXT NOT NULL,
                source_title TEXT NOT NULL,
                source_created_at TEXT NOT NULL,
                main_subject TEXT NOT NULL,
                user_goal TEXT NOT NULL,
                important_outcomes TEXT NOT NULL DEFAULT '[]',
                decisions TEXT NOT NULL DEFAULT '[]',
                lessons TEXT NOT NULL DEFAULT '[]',
                unresolved_questions TEXT NOT NULL DEFAULT '[]',
                actions TEXT NOT NULL DEFAULT '[]',
                analysis_mode TEXT NOT NULL,
                analysis_version TEXT NOT NULL,
                prompt_version TEXT NOT NULL,
                analysis_provider TEXT NOT NULL,
                analysis_model TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(source_record_id, analysis_version)
            );
            INSERT OR REPLACE INTO schema_meta(key, value)
                VALUES ('context_schema_version', '1');
            """
        )
        conn.execute(
            """
            INSERT INTO conversation_briefs (
                id, source_conversation_id, source_record_id, source_external_id,
                source_provider, source_title, source_created_at, main_subject, user_goal,
                analysis_mode, analysis_version, prompt_version, analysis_provider,
                analysis_model, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy-brief",
                conversation.id,
                conversation.id,
                conversation.source_id,
                conversation.source,
                conversation.title,
                conversation.created_at,
                "Legacy subject",
                "Preserve the existing Brief.",
                "auto",
                "legacy-v1",
                "legacy-prompt-v1",
                "openai",
                "legacy-model",
                "2026-07-21T00:00:00+00:00",
                "2026-07-21T00:00:00+00:00",
            ),
        )

    migrated = ContextLibraryStore(db_path)
    brief = migrated.get_brief("legacy-brief")

    assert brief is not None
    assert brief.main_subject == "Legacy subject"
    assert brief.analysis_status == "complete"
    assert brief.source_fingerprint == ""
    with sqlite3.connect(db_path) as conn:
        assert (
            conn.execute(
                "SELECT value FROM schema_meta WHERE key = 'context_schema_version'"
            ).fetchone()[0]
            == "7"
        )
