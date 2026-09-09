"""Synthetic exception-only review, atomic editorial history, and derived deletion."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from reweave.archive import ArchiveStore
from reweave.archive_management import ArchiveManager
from reweave.context_library import (
    ContextLibraryStore,
    ContextRevisionConflictError,
    EvidenceInput,
    ScopeInput,
)
from reweave.context_review import ContextReviewStore, effective_confidence, review_router
from reweave.maintenance import MaintenanceGate


@pytest.fixture
def sample(tmp_path, fixtures_dir):
    db = tmp_path / "library.db"
    archive = ArchiveStore(db)
    archive.import_directory(fixtures_dir)
    source = archive.search("Obsidian", limit=1)[0]
    library = ContextLibraryStore(db)
    brief = library.save_brief(
        conversation_id=source.conversation_id,
        main_subject="Notes",
        user_goal="Retain decisions",
        analysis_version="test",
        prompt_version="test",
        analysis_provider="synthetic",
        analysis_model="synthetic",
    )
    review = ContextReviewStore(library)

    def create(**overrides):
        args = dict(
            brief_id=brief.id,
            canonical_text="Keep source-backed notes.",
            item_type="decision",
            epistemic_kind="observed",
            confidence=0.98,
            scopes=[ScopeInput("project", "Notes")],
            evidence=[EvidenceInput(source.conversation_id, source.message_id)],
        )
        return library.create_item(**(args | overrides))

    return db, library, review, create, source


def action(row):
    return {"expected_version": row["item"].current_version, "review_key": row["review_key"]}


def scope_values(item):
    return [(s.scope_type, s.scope_key, s.confidence, s.space_id) for s in item.scopes]


def test_normal_items_are_not_an_approval_inbox(sample):
    _, _, review, create, _ = sample
    create()
    assert review.list_review()["results"] == []
    assert review.list_review(state="handled")["results"] == []


def test_dismiss_is_version_bound_persistent_and_never_changes_permissions(sample):
    _, library, review, create, _ = sample
    item = create(epistemic_kind="inferred", sensitivity="sensitive")
    reviewed = review.dismiss(item.id, **action(review.inspect(item)))
    assert reviewed["state"] == "handled"
    assert library.get_item(item.id) == item
    assert ContextReviewStore(library).list_review()["open_count"] == 0
    updated = library.revise_item(
        item.id,
        expected_version=1,
        canonical_text="A corrected private inference.",
        change_reason="Correction",
    )
    assert review.inspect(updated)["state"] == "open"
    assert updated.sensitivity == "sensitive"
    assert scope_values(updated) == scope_values(item)


def test_confirm_creates_user_history_and_can_undo(sample):
    _, library, review, create, _ = sample
    item = create(
        item_type="preference", epistemic_kind="inferred", sensitivity="sensitive", confidence=0.4
    )
    result = review.confirm(item.id, **action(review.inspect(item)))
    updated = result["item"]
    assert updated.current_version == 2 and updated.authority == "user"
    assert updated.confidence == 1 and updated.last_confirmed_at
    assert updated.sensitivity == item.sensitivity and updated.epistemic_kind == item.epistemic_kind
    assert scope_values(updated) == scope_values(item) and result["state"] == "handled"
    undone = review.undo_event(result["history"][0]["id"], expected_version=2)
    assert undone["item"].confidence == item.confidence
    assert undone["item"].last_confirmed_at is None
    assert undone["item"].current_version == 3 and undone["state"] == "open"
    assert len(library.get_item(item.id).versions) == 3


def test_confirmation_rolls_back_when_history_write_fails(sample, monkeypatch):
    _, library, review, create, _ = sample
    item = create(confidence=0.3, item_type="preference")
    monkeypatch.setattr(
        review, "_record", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("synthetic failure"))
    )
    with pytest.raises(RuntimeError):
        review.confirm(item.id, **action(review.inspect(item)))
    assert library.get_item(item.id) == item


def test_deleted_source_with_retained_excerpt_is_not_broken_evidence(sample):
    db, library, review, create, source = sample
    item = create()
    ArchiveManager(db).delete_conversation(source.conversation_id)
    retained = library.get_item(item.id)
    assert retained.evidence[0].source_conversation_id is None
    assert retained.evidence[0].excerpt
    assert review.inspect(retained)["reasons"] == []


def test_source_changes_reopen_dismissed_item_without_new_revision(sample):
    _, library, review, create, source = sample
    item = create(epistemic_kind="inferred", sensitivity="sensitive")
    row = review.inspect(item)
    review.dismiss(item.id, **action(row))
    with library._connect() as conn:
        conn.execute(
            "UPDATE messages SET content = ? WHERE id = ?",
            ("Different synthetic source", source.message_id),
        )
    changed = review.inspect(library.get_item(item.id))
    assert changed["state"] == "open"
    assert "source_changed" in [r["code"] for r in changed["reasons"]]
    with pytest.raises(ContextRevisionConflictError):
        review.confirm(item.id, **action(row))


def test_stale_confidence_is_derived_without_rewriting_history(sample):
    _, library, _, create, _ = sample
    item = create(confidence=0.8)
    now = datetime(2026, 9, 10, tzinfo=UTC)
    old = replace(item, updated_at=(now - timedelta(days=180)).isoformat())
    assert effective_confidence(old, now=now) == 0.4
    assert old.confidence == 0.8 and library.get_item(item.id).confidence == 0.8


def test_failed_analysis_and_changed_decision_are_reviewed(sample):
    _, library, review, create, _ = sample
    first = create()
    second = create(canonical_text="The revised decision.")
    library.link_items(first.id, second.id, "source_update")
    with library._connect() as conn:
        conn.execute("UPDATE conversation_briefs SET analysis_status = 'failed'")
    reasons = {r["code"] for r in review.inspect(library.get_item(first.id))["reasons"]}
    assert reasons == {"failed_evidence", "changed_decision"}


def test_dismiss_and_link_resolution_undo_reopen_without_deleting_history(sample):
    _, library, review, create, _ = sample
    first = create()
    second = create(canonical_text="Another choice.")
    library.link_items(first.id, second.id, "contradicts")
    row = review.inspect(library.get_item(first.id))
    dismissed = review.dismiss(first.id, **action(row))
    reopened = review.undo_event(dismissed["history"][0]["id"], expected_version=1)
    assert reopened["state"] == "open"
    resolved = review.resolve_link(
        first.id,
        **action(reopened),
        related_item_id=second.id,
        related_version=1,
        relationship="contradicts",
        resolution="keep_both",
    )
    restored = review.undo_event(resolved["history"][0]["id"], expected_version=1)
    assert restored["state"] == "open"
    assert len(restored["history"]) == 2
    assert all(event["undone_at"] for event in restored["history"])
    assert library.get_item(first.id).current_version == 1


def test_conflicts_require_explicit_resolution_and_reopen_on_either_revision(sample):
    _, library, review, create, _ = sample
    first = create()
    second = create(canonical_text="Use a different notes system.")
    library.link_items(first.id, second.id, "contradicts")
    row = review.inspect(library.get_item(first.id))
    confirmed = review.confirm(first.id, **action(row))
    assert confirmed["state"] == "open"
    with pytest.raises(ContextRevisionConflictError):
        review.resolve_link(
            first.id,
            **action(confirmed),
            related_item_id=second.id,
            related_version=9,
            relationship="contradicts",
            resolution="keep_both",
        )
    resolved = review.resolve_link(
        first.id,
        **action(confirmed),
        related_item_id=second.id,
        related_version=1,
        relationship="contradicts",
        resolution="prefer_this",
    )
    assert resolved["reasons"] == []
    assert review.inspect(library.get_item(second.id))["reasons"] == []
    assert (
        library.count_items() == 2
        and library.get_item(second.id).canonical_text == second.canonical_text
    )
    library.revise_item(
        second.id,
        expected_version=1,
        canonical_text="A third option.",
        change_reason="New information",
    )
    assert review.inspect(library.get_item(first.id))["state"] == "open"


def test_cross_scope_and_incomplete_evidence_are_concrete_reasons(sample):
    _, library, review, create, _ = sample
    item = create(scopes=[ScopeInput("personal"), ScopeInput("work")])
    assert "cross_scope" in [r["code"] for r in review.inspect(item)["reasons"]]
    with library._connect() as conn:
        conn.execute("UPDATE context_evidence SET excerpt = '' WHERE item_id = ?", (item.id,))
    assert "ambiguous_evidence" in [
        r["code"] for r in review.inspect(library.get_item(item.id))["reasons"]
    ]


def test_library_delete_requires_exact_phrase_preserves_sources_credentials_and_usage(
    sample, tmp_path
):
    db, library, review, create, source = sample
    from reweave.analysis_policy import AnalysisPolicyStore
    from reweave.context_trust import ContextTrustStore

    item = create(sensitivity="sensitive", epistemic_kind="inferred")
    review.dismiss(item.id, **action(review.inspect(item)))
    library.enqueue_analysis(conversation_id=source.conversation_id, source_fingerprint="synthetic")
    policy = AnalysisPolicyStore(db)
    policy.reserve(attempts=1, tokens=400)
    ContextTrustStore(db)
    profiles = tmp_path / "profiles.json"
    profiles.write_text('{"synthetic_credential_reference":"unchanged"}')
    old_profiles = profiles.read_bytes()
    stats = ArchiveStore(db).stats()
    with library._connect() as conn:
        before_usage = [tuple(row) for row in conn.execute("SELECT * FROM analysis_usage")]
    with pytest.raises(ValueError):
        review.delete_library(confirmation="delete library")
    assert library.count_items() == 1
    result = review.delete_library(confirmation="DELETE LIBRARY")
    assert result["deleted"]["items"] == 1 and result["deleted"]["review_events"] == 1
    assert library.count_items() == 0 and library.count_briefs() == 0
    assert ArchiveStore(db).stats() == stats and profiles.read_bytes() == old_profiles
    with library._connect() as conn:
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        assert [tuple(row) for row in conn.execute("SELECT * FROM analysis_usage")] == before_usage
        for table in (
            "context_spaces",
            "context_evidence",
            "context_item_versions",
            "context_analysis_queue",
        ):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_router_conflicts_and_exclusive_delete_callback_failure_report_commit(sample):
    _, library, review, create, _ = sample
    item = create(sensitivity="sensitive", epistemic_kind="inferred")
    gate = MaintenanceGate()
    app = FastAPI()

    def fail_callback():
        raise RuntimeError("Synthetic post-commit failure")

    app.include_router(review_router(review, gate=gate, on_library_deleted=fail_callback))
    with TestClient(app) as client:
        rows = client.get("/api/context/review").json()
        assert rows["open_count"] == 1
        row = rows["results"][0]
        stale = client.post(
            f"/api/context/review/items/{item.id}/dismiss",
            json={"expected_version": 2, "review_key": row["review_key"]},
        )
        assert stale.status_code == 409
        with gate.operation():
            assert (
                client.request(
                    "DELETE", "/api/context/library", json={"confirmation": "DELETE LIBRARY"}
                ).status_code
                == 409
            )
        assert library.count_items() == 1
        deleted = client.request(
            "DELETE", "/api/context/library", json={"confirmation": "DELETE LIBRARY"}
        )
        assert deleted.status_code == 200 and deleted.json()["restart_required"]
        assert library.count_items() == 0


def test_wired_web_delete_clears_derived_queue_and_restart_keeps_sources(sample, tmp_path):
    from reweave.web import create_app

    db, library, _, create, source = sample
    create()
    library.enqueue_analysis(conversation_id=source.conversation_id, source_fingerprint="synthetic")
    before = ArchiveStore(db).stats()
    app = create_app(db, data_dir=tmp_path)
    with TestClient(app) as client:
        # Maintenance correctly refuses a concurrent scheduler policy check.
        app.state.context_analysis_scheduler.stop()
        deleted = client.request(
            "DELETE", "/api/context/library", json={"confirmation": "DELETE LIBRARY"}
        )
        assert deleted.status_code == 200 and not deleted.json()["restart_required"]
        assert client.get("/api/context/review").json()["results"] == []
        assert library.count_items() == 0
        with library._connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM context_analysis_queue").fetchone()[0] == 0
    with TestClient(create_app(db, data_dir=tmp_path)) as client:
        assert client.get("/api/context/review").json()["results"] == []
        with library._connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM context_analysis_queue").fetchone()[0] == 0
    assert ArchiveStore(db).stats() == before
