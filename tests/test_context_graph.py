"""Canonical graph edges, redaction boundaries, and preview-bound one-use exports."""

import xml.etree.ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from reweave.archive import ArchiveStore
from reweave.context_graph import ContextGraphService, GraphShareRequest
from reweave.context_library import ContextLibraryStore, EvidenceInput, ScopeInput
from reweave.web import create_app


@pytest.fixture
def graph_library(tmp_path, fixtures_dir):
    db = tmp_path / "library.db"
    archive = ArchiveStore(db)
    archive.import_directory(fixtures_dir)
    source = archive.search("Obsidian")[0]
    store = ContextLibraryStore(db)
    brief = store.save_brief(
        conversation_id=source.conversation_id,
        main_subject="Private project title",
        user_goal="Keep decisions",
        analysis_version="fixture",
        prompt_version="fixture",
        analysis_provider="fixture",
        analysis_model="fixture",
    )

    def item(text, scopes, sensitivity="normal"):
        return store.create_item(
            brief_id=brief.id,
            canonical_text=text,
            item_type="decision",
            epistemic_kind="observed",
            confidence=0.95,
            scopes=scopes,
            sensitivity=sensitivity,
            evidence=[EvidenceInput(source.conversation_id, source.message_id)],
        )

    allowed = item(
        "RAW-PRIVATE-TEXT never export automatically", [ScopeInput("project", "SECRET-NAME")]
    )
    second = item("Another original decision", [ScopeInput("project", "SECRET-NAME")])
    mixed = item("Personal detail", [ScopeInput("project", "SECRET-NAME"), ScopeInput("personal")])
    sensitive = item("Sensitive secret", [ScopeInput("project", "SECRET-NAME")], "sensitive")
    unselected = item(
        "Other project secret",
        [ScopeInput("project", "SECRET-NAME"), ScopeInput("project", "OTHER")],
    )
    store.link_items(allowed.id, second.id, "supports")
    project = next(space for space in store.list_spaces() if space.name == "SECRET-NAME")
    return store, project, (allowed, second, mixed, sensitive, unselected)


def test_local_graph_uses_canonical_edges_and_bounded_scope(graph_library):
    store, project, items = graph_library
    graph = ContextGraphService(store).graph(space_id=project.id, limit=2)
    assert graph["total_items"] == 5
    assert graph["shown_items"] == 2
    assert graph["truncated"]
    full = ContextGraphService(store).graph()
    assert any(
        edge == {"source": items[0].id, "target": items[1].id, "relationship": "supports"}
        for edge in full["edges"]
    )
    assert any(node["id"] == f"space:{project.id}" for node in full["nodes"])


def test_preview_excludes_source_names_sensitive_personal_and_other_scopes(graph_library):
    store, project, items = graph_library
    service = ContextGraphService(store)
    preview = service.preview(GraphShareRequest(space_ids=[project.id]))
    assert preview["excluded_count"] == 3
    assert preview["node_count"] == 3
    for raw in [item.canonical_text for item in items] + [project.name, "Obsidian"]:
        assert raw not in preview["svg"]
    ET.fromstring(preview["svg"])
    assert "Project 1" in preview["svg"]
    assert service.export(preview["preview_token"]) == preview["svg"]
    with pytest.raises(RuntimeError, match="expired"):
        service.export(preview["preview_token"])


def test_custom_labels_are_escaped_and_library_change_invalidates_preview(graph_library):
    store, project, items = graph_library
    service = ContextGraphService(store)
    preview = service.preview(
        GraphShareRequest(
            space_ids=[project.id], labels={items[0].id: '<script>alert("x")</script>'}
        )
    )
    ET.fromstring(preview["svg"])
    assert "<script>" not in preview["svg"]
    assert preview["warnings"]
    store.revise_item(items[0].id, sensitivity="sensitive", change_reason="New privacy decision")
    with pytest.raises(RuntimeError, match="changed"):
        service.export(preview["preview_token"])


def test_api_requires_scope_preview_and_explicit_export(graph_library, tmp_path):
    store, project, _ = graph_library
    with TestClient(create_app(store.db_path, data_dir=tmp_path)) as client:
        assert client.get("/api/context/graph").status_code == 200
        assert (
            client.post("/api/context/graph/share/preview", json={"space_ids": []}).status_code
            == 422
        )
        preview = client.post(
            "/api/context/graph/share/preview", json={"space_ids": [project.id]}
        ).json()
        token = preview["preview_token"]
        assert (
            client.post(
                "/api/context/graph/share/export",
                json={"preview_token": token, "confirmation": "no"},
            ).status_code
            == 400
        )
        exported = client.post(
            "/api/context/graph/share/export",
            json={"preview_token": token, "confirmation": "EXPORT"},
        )
        assert exported.status_code == 200
        assert exported.text == preview["svg"]
        assert "image/svg+xml" in exported.headers["content-type"]
