"""Corrections, optimistic conflict handling, space aliases, and restart through the API."""

from fastapi.testclient import TestClient

from reweave.archive import ArchiveStore
from reweave.context_library import ContextLibraryStore, EvidenceInput, ScopeInput
from reweave.web import create_app


def test_correction_conflict_undo_and_space_alias_survive_restart(tmp_path, fixtures_dir):
    db = tmp_path / "library.db"
    archive = ArchiveStore(db)
    archive.import_directory(fixtures_dir)
    source = archive.search("Obsidian", provider="claude", limit=1)[0]
    library = ContextLibraryStore(db)
    brief = library.save_brief(
        conversation_id=source.conversation_id,
        main_subject="Notes",
        user_goal="Retain decisions",
        analysis_version="test",
        prompt_version="test",
        analysis_provider="test",
        analysis_model="test",
    )
    item = library.create_item(
        brief_id=brief.id,
        canonical_text="Use connected notes.",
        item_type="decision",
        epistemic_kind="observed",
        confidence=0.9,
        scopes=[ScopeInput("project", "Notes")],
        evidence=[EvidenceInput(source.conversation_id, source.message_id)],
    )
    with TestClient(create_app(db, data_dir=tmp_path)) as client:
        updated = client.patch(
            f"/api/context/items/{item.id}",
            json={
                "expected_version": 1,
                "change_reason": "Direct correction",
                "canonical_text": "Use a small set of linked notes.",
                "scopes": [{"scope_type": "project", "scope_key": "Notes"}, {"scope_type": "work"}],
            },
        )
        assert updated.status_code == 200
        current = updated.json()
        assert current["current_version"] == 2
        assert current["authority"] == "user"
        assert current["versions"][0]["canonical_text"] == item.canonical_text
        assert current["versions"][0]["scopes"][0]["scope_key"] == "Notes"
        conflict = client.patch(
            f"/api/context/items/{item.id}",
            json={
                "expected_version": 1,
                "change_reason": "Stale editor",
                "canonical_text": "Wrong",
            },
        )
        assert conflict.status_code == 409
        restored = client.post(
            f"/api/context/items/{item.id}/undo", json={"version": 1, "expected_version": 2}
        )
        assert restored.status_code == 200
        assert restored.json()["canonical_text"] == item.canonical_text
        assert len(restored.json()["scopes"]) == 1
        space = next(
            s for s in client.get("/api/context/spaces").json()["results"] if s["name"] == "Notes"
        )
        renamed = client.patch(
            f"/api/context/spaces/{space['id']}",
            json={"name": "Writing", "expected_revision": space["revision"]},
        )
        assert renamed.status_code == 200
        assert "Notes" in renamed.json()["aliases"]
        assert (
            client.patch(
                f"/api/context/spaces/{space['id']}",
                json={"name": "Lost edit", "expected_revision": space["revision"]},
            ).status_code
            == 409
        )

    with TestClient(create_app(db, data_dir=tmp_path)) as client:
        persisted = client.get(f"/api/context/items/{item.id}").json()
        assert persisted["canonical_text"] == item.canonical_text
        assert persisted["scopes"][0]["scope_key"] == "Writing"
        assert persisted["evidence"][0]["source_available"]
        assert len(persisted["versions"]) >= 3


def test_paged_context_has_no_silent_truncation(tmp_path, fixtures_dir):
    db = tmp_path / "library.db"
    archive = ArchiveStore(db)
    archive.import_directory(fixtures_dir)
    library = ContextLibraryStore(db)
    source = archive.search("Obsidian", provider="claude", limit=1)[0]
    for index in range(3):
        library.save_brief(
            conversation_id=source.conversation_id,
            main_subject=f"Notes {index}",
            user_goal="Read",
            analysis_version=f"test-{index}",
            prompt_version="test",
            analysis_provider="test",
            analysis_model="test",
        )
    with TestClient(create_app(db, data_dir=tmp_path)) as client:
        first = client.get("/api/context/briefs?limit=2").json()
        second = client.get("/api/context/briefs?limit=2&offset=2").json()
        assert first["has_more"] is True
        assert second["has_more"] is False
        assert len({b["id"] for b in first["results"] + second["results"]}) == 3
        assert client.get("/api/context/items?limit=0").status_code == 422
