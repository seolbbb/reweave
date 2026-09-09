"""Synthetic persistence, correction, canonical-space and reconciliation regressions."""

import sqlite3
from dataclasses import replace

import pytest

from reweave.archive import ArchiveStore
from reweave.context_library import (
    ContextItemInput,
    ContextLibraryStore,
    ContextRevisionConflict,
    EvidenceInput,
    ScopeInput,
)


@pytest.fixture
def library(tmp_path, fixtures_dir):
    archive = ArchiveStore(tmp_path / "archive.db")
    archive.import_directory(fixtures_dir)
    source_id = archive.search("Obsidian", provider="claude", limit=1)[0].conversation_id
    messages = archive.get_messages(source_id)
    store = ContextLibraryStore(archive.db_path)
    brief = store.save_brief(
        conversation_id=source_id,
        main_subject="Synthetic note structure",
        user_goal="Keep source-linked context",
        analysis_version="test-v1",
        prompt_version="test-v1",
        analysis_provider="test",
        analysis_model="test",
    )
    candidate = ContextItemInput(
        canonical_text="The user is organizing an Obsidian vault.",
        item_type="project_fact",
        epistemic_kind="observed",
        confidence=0.9,
        sensitivity="normal",
        scopes=(ScopeInput("project", "Obsidian"),),
        evidence=(EvidenceInput(source_id, messages[0].id),),
    )
    return archive, store, brief, candidate, messages


def test_reanalysis_keeps_corrected_identity_scopes_history_and_undo(library):
    archive, store, brief, candidate, messages = library
    original = store.reconcile_brief_items(brief.id, [candidate])[0]
    edited = store.revise_item(
        original.id,
        expected_version=1,
        change_reason="Owner correction",
        canonical_text="I use a private vault only.",
        scopes=[ScopeInput("personal")],
    )
    after = store.reconcile_brief_items(brief.id, [candidate])[0]
    assert after.id == original.id
    assert after.canonical_text == edited.canonical_text
    assert after.authority == "user"
    assert after.current_version == 2
    assert after.scopes[0].scope_type == "personal"
    assert after.versions[0].scopes[0].scope_key == "Obsidian"
    with pytest.raises(ContextRevisionConflict):
        store.revise_item(original.id, expected_version=1, change_reason="Stale editor")
    with pytest.raises(ContextRevisionConflict):
        store.revise_item(original.id, authority="extraction", change_reason="Model rewrite")
    restored = store.undo_item(original.id, version=1, expected_version=2)
    assert restored.current_version == 3
    assert restored.canonical_text == original.canonical_text
    assert restored.scopes[0].space_id == original.scopes[0].space_id
    assert restored.authority == "user"
    reopened = ContextLibraryStore(archive.db_path)
    assert reopened.get_item(original.id) == restored


def test_exact_duplicate_attaches_new_source_without_mutating_old_snapshot(library):
    archive, store, brief, candidate, messages = library
    original = store.reconcile_brief_items(brief.id, [candidate])[0]
    source_id = archive.search("Python", provider="chatgpt", limit=1)[0].conversation_id
    source_messages = archive.get_messages(source_id)
    other_brief = store.save_brief(
        conversation_id=source_id,
        main_subject="Other synthetic source",
        user_goal="Reuse context",
        analysis_version="test-v1",
        prompt_version="test-v1",
        analysis_provider="test",
        analysis_model="test",
    )
    repeat = replace(
        candidate,
        canonical_text="  THE USER IS ORGANIZING AN OBSIDIAN VAULT. ",
        scopes=(ScopeInput("project", "obsidian"),),
        evidence=(EvidenceInput(source_id, source_messages[0].id),),
    )
    combined = store.reconcile_brief_items(other_brief.id, [repeat])[0]
    assert combined.id == original.id
    assert len(combined.evidence) == 2
    assert combined.versions[0].evidence_ids == original.versions[0].evidence_ids
    assert len(combined.versions[-1].evidence_ids) == 2
    assert store.reconcile_brief_items(other_brief.id, [repeat])[0].current_version == 2
    assert store.count_items() == 1


def test_same_text_in_other_scope_or_epistemic_kind_is_not_merged(library):
    _, store, brief, candidate, _ = library
    result = store.reconcile_brief_items(
        brief.id,
        [
            candidate,
            replace(candidate, scopes=(ScopeInput("project", "Another client"),)),
            replace(
                candidate, epistemic_kind="inferred", inference_rationale="Synthetic rationale"
            ),
        ],
    )
    assert len({item.id for item in result}) == 3
    assert result[-1].inference_rationale == "Synthetic rationale"
    assert result[-1].versions[0].inference_rationale == "Synthetic rationale"


def test_space_rename_and_merge_remember_old_routes_and_reject_stale_edits(library):
    archive, store, brief, candidate, _ = library
    original = store.reconcile_brief_items(brief.id, [candidate])[0]
    space_id = original.scopes[0].space_id
    renamed = store.rename_space(space_id, name="Private notes", expected_revision=1)
    assert renamed.id == space_id
    assert set(renamed.aliases) == {"Obsidian", "Private notes"}
    after = store.reconcile_brief_items(brief.id, [candidate])[0]
    assert after.id == original.id
    assert after.scopes[0].scope_key == "Private notes"
    assert after.versions[0].scopes[0].scope_key == "Obsidian"
    with pytest.raises(ContextRevisionConflict):
        store.rename_space(space_id, name="Stale name", expected_revision=1)
    another = store.reconcile_brief_items(
        brief.id,
        [
            candidate,
            replace(
                candidate, canonical_text="Other context", scopes=(ScopeInput("project", "Notes"),)
            ),
        ],
    )[1]
    other_id = another.scopes[0].space_id
    merged = store.merge_spaces(
        other_id,
        space_id,
        expected_source_revision=1,
        expected_target_revision=2,
    )
    assert set(merged.aliases) == {"Obsidian", "Private notes", "Notes"}
    assert store.get_item(another.id).scopes[0].space_id == space_id
    assert store.get_space(other_id).merged_into == space_id
    reopened = ContextLibraryStore(archive.db_path)
    assert reopened.get_space(space_id) == merged
    assert reopened.get_item(original.id).scopes[0].scope_key == "Private notes"


def test_merge_collapses_duplicate_membership_but_keeps_version_history(library):
    _, store, brief, candidate, _ = library
    item = store.reconcile_brief_items(
        brief.id, [replace(candidate, scopes=(ScopeInput("topic", "A"), ScopeInput("topic", "B")))]
    )[0]
    first, second = item.scopes
    store.merge_spaces(
        first.space_id, second.space_id, expected_source_revision=1, expected_target_revision=1
    )
    updated = store.get_item(item.id)
    assert len(updated.scopes) == 1
    assert len(updated.versions[0].scopes) == 2
    assert len(updated.versions[-1].scopes) == 1


def test_privacy_space_boundaries_and_sensitive_core_self(library):
    _, store, brief, candidate, _ = library
    personal = next(space for space in store.list_spaces() if space.scope_type == "personal")
    with pytest.raises(ValueError, match="Built-in"):
        store.rename_space(personal.id, name="Work", expected_revision=1)
    item = store.reconcile_brief_items(
        brief.id, [replace(candidate, sensitivity="sensitive", scopes=(ScopeInput("core_self"),))]
    )[0]
    assert {scope.scope_type for scope in item.scopes} == {"personal"}
    store.revise_item(item.id, change_reason="Scope correction", scopes=[ScopeInput("core_self")])
    assert {scope.scope_type for scope in store.get_item(item.id).scopes} == {"personal"}


def test_failed_reconciliation_rolls_back_all_changes(library, monkeypatch):
    _, store, brief, candidate, _ = library
    original = store.reconcile_brief_items(brief.id, [candidate])[0]
    before = store.get_brief(brief.id)
    real_create = store.create_item
    attempts = 0

    def fail_second(**kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            raise RuntimeError("Synthetic disk failure")
        return real_create(**kwargs)

    monkeypatch.setattr(store, "create_item", fail_second)
    with pytest.raises(RuntimeError, match="Synthetic"):
        store.reconcile_brief_items(
            brief.id,
            [
                replace(candidate, canonical_text="New A"),
                replace(candidate, canonical_text="New B"),
            ],
        )
    assert store.get_brief(brief.id) == before
    assert store.get_item(original.id) == original
    assert store.count_items() == 1
    with sqlite3.connect(store.db_path) as conn:
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_zero_reanalysis_keeps_history_and_user_corrections(library):
    _, store, brief, candidate, _ = library
    old = store.reconcile_brief_items(brief.id, [candidate])[0]
    assert store.reconcile_brief_items(brief.id, []) == ()
    assert store.get_brief(brief.id).context_item_ids == ()
    assert store.get_item(old.id).status == "stale"
    restored = store.reconcile_brief_items(brief.id, [candidate])[0]
    assert restored.id == old.id
    assert restored.status == "active"
    assert restored.stale_at is None
    store.revise_item(old.id, change_reason="Keep this context", status="active")
    store.reconcile_brief_items(brief.id, [])
    assert store.get_item(old.id).status == "active"


def test_repeated_source_excerpt_changes_keep_historical_evidence(library):
    archive, store, brief, candidate, messages = library
    original = store.reconcile_brief_items(brief.id, [candidate])[0]
    with sqlite3.connect(archive.db_path) as conn:
        conn.execute(
            "UPDATE messages SET content = ? WHERE id = ?",
            ("A changed source statement.", messages[0].id),
        )
    changed = replace(
        candidate,
        evidence=(
            EvidenceInput(
                brief.source_record_id, messages[0].id, excerpt="A changed source statement."
            ),
        ),
    )
    result = store.reconcile_brief_items(brief.id, [changed])[0]
    assert result.id == original.id
    assert len(result.evidence) == 2
    assert len(result.versions[0].evidence_ids) == 1
    assert len(result.versions[-1].evidence_ids) == 2
    assert sum(evidence.source_changed for evidence in result.evidence) == 1


def test_pagination_has_stable_nonoverlapping_pages(library):
    _, store, brief, candidate, _ = library
    store.reconcile_brief_items(
        brief.id, [replace(candidate, canonical_text=f"Item {i}") for i in range(5)]
    )
    first = store.list_items(limit=2)
    second = store.list_items(limit=2, offset=2)
    assert len({item.id for item in first + second}) == 4
    assert store.count_items() == 5
    assert store.count_briefs() == 1
    assert store.list_briefs(offset=1) == []


def test_legacy_columns_and_evidence_migrate_without_losing_corrections(library):
    archive, store, brief, candidate, messages = library
    original = store.reconcile_brief_items(brief.id, [candidate])[0]
    corrected = store.revise_item(
        original.id,
        change_reason="Legacy correction",
        canonical_text="User-corrected legacy context",
    )
    with sqlite3.connect(archive.db_path) as conn:
        evidence_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'context_evidence'"
        ).fetchone()[0]
        conn.execute("ALTER TABLE context_evidence RENAME TO legacy_evidence")
        conn.execute(
            evidence_sql.replace(
                "UNIQUE(item_id, source_message_record_id, relationship, excerpt)",
                "UNIQUE(item_id, source_message_record_id, relationship)",
            )
        )
        conn.execute("INSERT INTO context_evidence SELECT * FROM legacy_evidence")
        conn.execute("DROP TABLE legacy_evidence")
        for table in ("context_items", "context_item_versions"):
            for column in ("authority", "inference_rationale"):
                conn.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
        for column in ("scopes_json", "evidence_ids_json"):
            conn.execute(f"ALTER TABLE context_item_versions DROP COLUMN {column}")
        conn.execute("UPDATE context_item_scopes SET space_id = NULL")
        conn.execute("UPDATE schema_meta SET value = '5' WHERE key = 'context_schema_version'")
    reopened = ContextLibraryStore(archive.db_path)
    migrated = reopened.get_item(original.id)
    assert migrated.canonical_text == corrected.canonical_text
    assert migrated.authority == "user"
    assert migrated.current_version == 2
    assert migrated.evidence[0].id == original.evidence[0].id
    assert migrated.versions[-1].scopes[0].scope_key == "Obsidian"
    with sqlite3.connect(archive.db_path) as conn:
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        conn.execute(
            "UPDATE messages SET content = ? WHERE id = ?", ("New source evidence", messages[0].id)
        )
    new_source = replace(
        candidate,
        evidence=(
            EvidenceInput(brief.source_record_id, messages[0].id, excerpt="New source evidence"),
        ),
    )
    result = reopened.reconcile_brief_items(brief.id, [new_source])[0]
    assert result.canonical_text == corrected.canonical_text
    assert len(result.evidence) == 2


def test_explicit_requeue_changes_mode_without_weakening_automatic_idempotency(library):
    _, store, brief, _, _ = library
    job, created = store.enqueue_analysis(
        conversation_id=brief.source_record_id, source_fingerprint="synthetic-source"
    )
    assert created
    same, created = store.enqueue_analysis(
        conversation_id=brief.source_record_id,
        source_fingerprint="synthetic-source",
        analysis_mode="learning",
    )
    assert not created and same.analysis_mode == "auto"
    store.start_analysis_queue_job(job.id)
    with pytest.raises(ContextRevisionConflict):
        store.requeue_analysis(job.id, analysis_mode="learning")
    store.complete_analysis_queue_job(job.id, brief_id=brief.id)
    requeued = store.requeue_analysis(job.id, analysis_mode="learning")
    assert requeued.analysis_mode == "learning"
    assert requeued.status == "pending"
    assert requeued.completed_at is None
    assert requeued.result_brief_id is None
    assert requeued.attempt_count == 1


def test_space_merge_keeps_a_correction_even_after_its_scope_was_moved(library):
    _, store, brief, candidate, _ = library
    original = store.reconcile_brief_items(brief.id, [candidate])[0]
    other = store.reconcile_brief_items(
        brief.id,
        [
            candidate,
            replace(
                candidate, canonical_text="Other project", scopes=(ScopeInput("project", "Other"),)
            ),
        ],
    )[1]
    store.revise_item(
        original.id,
        change_reason="Personal scope correction",
        canonical_text="Corrected private context",
        scopes=[ScopeInput("personal")],
    )
    store.merge_spaces(
        original.scopes[0].space_id,
        other.scopes[0].space_id,
        expected_source_revision=1,
        expected_target_revision=1,
    )
    after = store.reconcile_brief_items(brief.id, [candidate])[0]
    assert after.id == original.id
    assert after.canonical_text == "Corrected private context"
    assert after.scopes[0].scope_type == "personal"
