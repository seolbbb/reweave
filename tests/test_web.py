"""FastAPI backend tests."""

import zipfile

from fastapi.testclient import TestClient

import reweave.web
from reweave.archive import ArchiveStore
from reweave.web import create_app


def test_api_search_groups_by_conversation(tmp_path, fixtures_dir):
    db = tmp_path / "archive.db"
    store = ArchiveStore(db)
    store.import_directory(fixtures_dir)
    client = TestClient(create_app(db))

    response = client.get("/api/search", params={"q": "Obsidian"})

    assert response.status_code == 200
    data = response.json()
    assert data["results"]
    result = data["results"][0]
    assert "excerpts" in result
    assert result["id"]


def test_api_conversation_detail_preserves_messages(tmp_path, fixtures_dir):
    db = tmp_path / "archive.db"
    store = ArchiveStore(db)
    store.import_directory(fixtures_dir)
    conversation_id = store.search("Python")[0].conversation_id
    client = TestClient(create_app(db))

    response = client.get(f"/api/conversations/{conversation_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["conversation"]["id"] == conversation_id
    assert data["messages"][0]["index"] == 0
    assert data["messages"][0]["timestamp"] is not None


def test_api_import(tmp_path, fixtures_dir):
    db = tmp_path / "archive.db"
    client = TestClient(create_app(db))

    response = client.post("/api/import", json={"input_dir": str(fixtures_dir)})

    assert response.status_code == 200
    assert response.json()["inserted_conversations"] == 4


def test_api_import_path_zip(tmp_path, fixtures_dir):
    db = tmp_path / "archive.db"
    zip_path = tmp_path / "export.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        for json_path in fixtures_dir.glob("*.json"):
            archive.write(json_path, arcname=json_path.name)
    client = TestClient(create_app(db, data_dir=tmp_path / "app-data"))

    response = client.post("/api/import/path", json={"path": str(zip_path)})

    assert response.status_code == 200
    assert response.json()["inserted_conversations"] == 4


def test_api_import_upload_json(tmp_path, chatgpt_sample_path):
    db = tmp_path / "archive.db"
    client = TestClient(create_app(db, data_dir=tmp_path / "app-data"))

    with open(chatgpt_sample_path, "rb") as file:
        response = client.post(
            "/api/import/upload",
            files=[("files", ("chatgpt_sample.json", file, "application/json"))],
        )

    assert response.status_code == 200
    data = response.json()
    assert data["inserted_conversations"] == 2
    assert (tmp_path / "app-data" / "imports").exists()


def test_api_import_upload_rejects_bad_extension(tmp_path):
    db = tmp_path / "archive.db"
    client = TestClient(create_app(db, data_dir=tmp_path / "app-data"))

    response = client.post(
        "/api/import/upload",
        files=[("files", ("notes.txt", b"hello", "text/plain"))],
    )

    assert response.status_code == 400
    assert "Unsupported import file type" in response.json()["detail"]


def test_api_create_and_get_insight_with_fake_generator(monkeypatch, tmp_path, fixtures_dir):
    db = tmp_path / "archive.db"
    store = ArchiveStore(db)
    store.import_directory(fixtures_dir)
    conversation_id = store.search("Zettelkasten")[0].conversation_id

    def fake_generate(
        store, *, conversation_ids, settings, title="Connected Insights", provider=None
    ):
        return store.save_insight_report(
            title=title,
            selected_conversation_ids=conversation_ids,
            provider=settings.provider,
            model=settings.model,
            markdown="## Overview\n\nFake\n\n## Source Index\n\n- ref\n",
        )

    monkeypatch.setattr(reweave.web, "generate_insight_report", fake_generate)
    client = TestClient(create_app(db))

    response = client.post(
        "/api/insights",
        json={
            "conversation_ids": [conversation_id],
            "title": "Fake Insight",
            "settings": {
                "provider": "openai",
                "model": "fake-model",
                "api_key": "fake-key",
            },
        },
    )

    assert response.status_code == 200
    report = response.json()
    assert report["title"] == "Fake Insight"
    assert "## Overview" in report["markdown"]

    list_response = client.get("/api/insights")
    assert list_response.status_code == 200
    assert list_response.json()["results"][0]["id"] == report["id"]

    get_response = client.get(f"/api/insights/{report['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["markdown"] == report["markdown"]
