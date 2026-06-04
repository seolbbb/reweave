"""FastAPI backend tests."""

import zipfile

import pytest
from fastapi.testclient import TestClient

import reweave.llm
import reweave.llm_profiles
import reweave.web
from reweave.archive import ArchiveStore
from reweave.web import create_app


def fake_keyring(monkeypatch):
    secrets = {}

    def set_password(service, name, value):
        secrets[(service, name)] = value

    def get_password(service, name):
        return secrets.get((service, name))

    def delete_password(service, name):
        secrets.pop((service, name), None)

    monkeypatch.setattr(reweave.llm_profiles.keyring, "set_password", set_password)
    monkeypatch.setattr(reweave.llm_profiles.keyring, "get_password", get_password)
    monkeypatch.setattr(reweave.llm_profiles.keyring, "delete_password", delete_password)
    return secrets


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


def test_api_import_path_directory(tmp_path, fixtures_dir):
    db = tmp_path / "archive.db"
    client = TestClient(create_app(db, data_dir=tmp_path / "app-data"))

    response = client.post("/api/import/path", json={"path": str(fixtures_dir)})

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


def test_api_llm_profile_key_crud_keeps_secret_out_of_json(monkeypatch, tmp_path):
    fake_keyring(monkeypatch)
    client = TestClient(create_app(tmp_path / "archive.db", data_dir=tmp_path / "app-data"))
    profile_id = client.get("/api/llm/profiles").json()["profiles"][0]["id"]

    response = client.post(
        f"/api/llm/profiles/{profile_id}/keys",
        json={"label": "Primary", "api_key": "secret-value", "priority": 0},
    )

    assert response.status_code == 200
    assert response.json()["has_secret"] is True
    profiles_response = client.get("/api/llm/profiles")
    assert profiles_response.status_code == 200
    profile = profiles_response.json()["profiles"][0]
    assert profile["keys"][0]["label"] == "Primary"
    assert profile["keys"][0]["has_secret"] is True

    profiles_file = tmp_path / "app-data" / "llm_profiles.json"
    assert "secret-value" not in profiles_file.read_text(encoding="utf-8")


def test_api_llm_profiles_adds_new_default_provider_without_replacing_existing(
    monkeypatch, tmp_path
):
    fake_keyring(monkeypatch)
    data_dir = tmp_path / "app-data"
    client = TestClient(create_app(tmp_path / "archive.db", data_dir=data_dir))
    profiles = client.get("/api/llm/profiles").json()["profiles"]
    openrouter = next(profile for profile in profiles if profile["provider"] == "openrouter")

    client.put(
        f"/api/llm/profiles/{openrouter['id']}",
        json={
            "name": "My OpenRouter",
            "provider": "openrouter",
            "default_model": "openrouter/model",
        },
    )
    restarted = TestClient(create_app(tmp_path / "archive.db", data_dir=data_dir))
    refreshed = restarted.get("/api/llm/profiles").json()["profiles"]

    assert len([profile for profile in refreshed if profile["provider"] == "openrouter"]) == 1
    assert next(profile for profile in refreshed if profile["provider"] == "openrouter")[
        "name"
    ] == "My OpenRouter"


def test_api_llm_models_uses_provider_response_and_saved_key(monkeypatch, tmp_path):
    fake_keyring(monkeypatch)
    client = TestClient(create_app(tmp_path / "archive.db", data_dir=tmp_path / "app-data"))
    profile = next(
        item
        for item in client.get("/api/llm/profiles").json()["profiles"]
        if item["provider"] == "openai"
    )
    client.post(
        f"/api/llm/profiles/{profile['id']}/keys",
        json={"label": "Primary", "api_key": "secret-value", "priority": 0},
    )

    def fake_get(url, *, headers, params, timeout):
        assert url == "https://api.openai.com/v1/models"
        assert headers["Authorization"] == "Bearer secret-value"
        assert params is None
        assert timeout == 30
        request = reweave.llm.httpx.Request("GET", url)
        return reweave.llm.httpx.Response(
            200,
            json={"data": [{"id": "provider-model-b"}, {"id": "provider-model-a"}]},
            request=request,
        )

    monkeypatch.setattr(reweave.llm.httpx, "get", fake_get)

    response = client.get(f"/api/llm/profiles/{profile['id']}/models")

    assert response.status_code == 200
    assert response.json() == {
        "models": ["provider-model-a", "provider-model-b"],
        "validated_key_label": "Primary",
    }
    assert "secret-value" not in response.text
    assert profile["default_model"] not in response.json()["models"]


def test_api_llm_models_reports_invalid_key_without_exposing_secret(monkeypatch, tmp_path):
    fake_keyring(monkeypatch)
    client = TestClient(create_app(tmp_path / "archive.db", data_dir=tmp_path / "app-data"))
    profile = client.get("/api/llm/profiles").json()["profiles"][0]
    client.post(
        f"/api/llm/profiles/{profile['id']}/keys",
        json={"label": "Primary", "api_key": "secret-value", "priority": 0},
    )

    def fake_get(url, *, headers, params, timeout):
        request = reweave.llm.httpx.Request("GET", url)
        return reweave.llm.httpx.Response(401, request=request)

    monkeypatch.setattr(reweave.llm.httpx, "get", fake_get)

    response = client.get(f"/api/llm/profiles/{profile['id']}/models")

    assert response.status_code == 401
    assert "not accepted" in response.json()["detail"]
    assert "secret-value" not in response.text


def test_api_llm_connect_validates_before_saving_and_selects_model(monkeypatch, tmp_path):
    secrets = fake_keyring(monkeypatch)
    client = TestClient(create_app(tmp_path / "archive.db", data_dir=tmp_path / "app-data"))
    profile = next(
        item
        for item in client.get("/api/llm/profiles").json()["profiles"]
        if item["provider"] == "openai"
    )

    def fake_get(url, *, headers, params, timeout):
        assert headers["Authorization"] == "Bearer new-secret"
        request = reweave.llm.httpx.Request("GET", url)
        return reweave.llm.httpx.Response(
            200,
            json={"data": [{"id": "gpt-audio"}, {"id": "gpt-current-mini"}]},
            request=request,
        )

    monkeypatch.setattr(reweave.llm.httpx, "get", fake_get)
    response = client.post(
        f"/api/llm/profiles/{profile['id']}/connect",
        json={"api_key": "new-secret"},
    )

    assert response.status_code == 200
    assert response.json()["selected_model"] == "gpt-current-mini"
    assert response.json()["profile"]["masked_key"] == "************"
    assert "new-secret" not in response.text
    assert list(secrets.values()) == ["new-secret"]


def test_api_llm_connect_uses_openrouter_default_base_url(monkeypatch, tmp_path):
    fake_keyring(monkeypatch)
    client = TestClient(create_app(tmp_path / "archive.db", data_dir=tmp_path / "app-data"))
    profile = next(
        item
        for item in client.get("/api/llm/profiles").json()["profiles"]
        if item["provider"] == "openrouter"
    )

    def fake_get(url, *, headers, params, timeout):
        assert url == "https://openrouter.ai/api/v1/models"
        request = reweave.llm.httpx.Request("GET", url)
        return reweave.llm.httpx.Response(
            200,
            json={"data": [{"id": "openrouter/model"}]},
            request=request,
        )

    monkeypatch.setattr(reweave.llm.httpx, "get", fake_get)
    response = client.post(
        f"/api/llm/profiles/{profile['id']}/connect",
        json={"api_key": "arbitrary-openrouter-key"},
    )

    assert response.status_code == 200
    assert response.json()["profile"]["provider"] == "openrouter"
    assert response.json()["profile"]["base_url"] == ""


def test_api_llm_connect_rejects_invalid_key_without_saving_it(monkeypatch, tmp_path):
    secrets = fake_keyring(monkeypatch)
    client = TestClient(create_app(tmp_path / "archive.db", data_dir=tmp_path / "app-data"))
    profile = client.get("/api/llm/profiles").json()["profiles"][0]

    def fake_get(url, *, headers, params, timeout):
        request = reweave.llm.httpx.Request("GET", url)
        return reweave.llm.httpx.Response(401, request=request)

    monkeypatch.setattr(reweave.llm.httpx, "get", fake_get)
    response = client.post(
        f"/api/llm/profiles/{profile['id']}/connect",
        json={"api_key": "invalid-secret"},
    )

    assert response.status_code == 401
    assert secrets == {}
    assert "invalid-secret" not in response.text
    refreshed = client.get("/api/llm/profiles").json()["profiles"][0]
    assert refreshed["connected"] is False


@pytest.mark.parametrize(
    ("provider_status", "response_status", "message"),
    [
        (403, 403, "does not have permission"),
        (429, 429, "rate limit was reached"),
    ],
)
def test_api_llm_connect_reports_actionable_provider_errors(
    monkeypatch, tmp_path, provider_status, response_status, message
):
    fake_keyring(monkeypatch)
    client = TestClient(create_app(tmp_path / "archive.db", data_dir=tmp_path / "app-data"))
    profile = client.get("/api/llm/profiles").json()["profiles"][0]

    def fake_get(url, *, headers, params, timeout):
        request = reweave.llm.httpx.Request("GET", url)
        return reweave.llm.httpx.Response(provider_status, request=request)

    monkeypatch.setattr(reweave.llm.httpx, "get", fake_get)
    response = client.post(
        f"/api/llm/profiles/{profile['id']}/connect",
        json={"api_key": "provider-secret"},
    )

    assert response.status_code == response_status
    assert message in response.json()["detail"]
    assert "provider-secret" not in response.text


def test_api_llm_connect_reports_network_error_without_exposing_secret(monkeypatch, tmp_path):
    fake_keyring(monkeypatch)
    client = TestClient(create_app(tmp_path / "archive.db", data_dir=tmp_path / "app-data"))
    profile = client.get("/api/llm/profiles").json()["profiles"][0]

    def fake_get(url, *, headers, params, timeout):
        request = reweave.llm.httpx.Request("GET", url)
        raise reweave.llm.httpx.ConnectError("socket failed", request=request)

    monkeypatch.setattr(reweave.llm.httpx, "get", fake_get)
    response = client.post(
        f"/api/llm/profiles/{profile['id']}/connect",
        json={"api_key": "provider-secret"},
    )

    assert response.status_code == 502
    assert response.json()["detail"] == (
        "Could not reach the provider. Check your connection and try again."
    )
    assert "provider-secret" not in response.text


def test_api_llm_connect_can_change_and_remove_saved_key(monkeypatch, tmp_path):
    secrets = fake_keyring(monkeypatch)
    client = TestClient(create_app(tmp_path / "archive.db", data_dir=tmp_path / "app-data"))
    profile = client.get("/api/llm/profiles").json()["profiles"][0]

    def fake_get(url, *, headers, params, timeout):
        request = reweave.llm.httpx.Request("GET", url)
        return reweave.llm.httpx.Response(
            200,
            json={"data": [{"id": "provider-model"}]},
            request=request,
        )

    monkeypatch.setattr(reweave.llm.httpx, "get", fake_get)
    for api_key in ("first-secret", "replacement-secret"):
        response = client.post(
            f"/api/llm/profiles/{profile['id']}/connect",
            json={"api_key": api_key},
        )
        assert response.status_code == 200

    refreshed = client.get("/api/llm/profiles").json()["profiles"][0]
    assert len(refreshed["keys"]) == 1
    assert list(secrets.values()) == ["replacement-secret"]

    response = client.delete(f"/api/llm/profiles/{profile['id']}/connection")
    assert response.status_code == 200
    assert secrets == {}
    refreshed = client.get("/api/llm/profiles").json()["profiles"][0]
    assert refreshed["connected"] is False


def test_api_llm_selected_model_is_persisted(monkeypatch, tmp_path):
    fake_keyring(monkeypatch)
    client = TestClient(create_app(tmp_path / "archive.db", data_dir=tmp_path / "app-data"))
    profile = client.get("/api/llm/profiles").json()["profiles"][0]

    response = client.put(
        f"/api/llm/profiles/{profile['id']}/model",
        json={"model": "provider-model-b"},
    )

    assert response.status_code == 200
    assert response.json()["default_model"] == "provider-model-b"
    refreshed = client.get("/api/llm/profiles").json()["profiles"][0]
    assert refreshed["default_model"] == "provider-model-b"


def test_api_insight_uses_profile_key_failover(monkeypatch, tmp_path, fixtures_dir):
    fake_keyring(monkeypatch)
    db = tmp_path / "archive.db"
    store = ArchiveStore(db)
    store.import_directory(fixtures_dir)
    conversation_id = store.search("Zettelkasten")[0].conversation_id
    client = TestClient(create_app(db, data_dir=tmp_path / "app-data"))
    profile = next(
        item for item in client.get("/api/llm/profiles").json()["profiles"]
        if item["provider"] == "openai"
    )
    for label, api_key, priority in [
        ("First", "first-key", 0),
        ("Second", "second-key", 1),
    ]:
        client.post(
            f"/api/llm/profiles/{profile['id']}/keys",
            json={"label": label, "api_key": api_key, "priority": priority},
        )
    calls = []

    def fake_post(url, *, headers, json, timeout):
        calls.append(headers["Authorization"])
        request = reweave.llm.httpx.Request("POST", url)
        if len(calls) == 1:
            return reweave.llm.httpx.Response(401, request=request)
        return reweave.llm.httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                "## Overview\n\nOk\n\n"
                                "## Concept Map\n\nOk\n\n"
                                "## Connections\n\nOk\n\n"
                                "## New Insights\n\nOk\n\n"
                                "## Uncertainties\n\nOk\n\n"
                                "## Source Index\n\n- ref\n"
                            )
                        }
                    }
                ]
            },
            request=request,
        )

    monkeypatch.setattr(reweave.llm.httpx, "post", fake_post)

    response = client.post(
        "/api/insights",
        json={
            "conversation_ids": [conversation_id],
            "title": "Profile Insight",
            "settings": {
                "profile_id": profile["id"],
                "model": "gpt-4o-mini",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Profile Insight"
    assert calls == ["Bearer first-key", "Bearer second-key"]


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
