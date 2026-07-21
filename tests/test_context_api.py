"""Context analysis and durable read API tests."""

from time import sleep

import pytest
from fastapi.testclient import TestClient

import reweave.context_extraction
import reweave.llm_profiles
import reweave.web
from reweave.archive import ArchiveStore
from reweave.context_extraction import (
    CONTEXT_EXTRACTION_PROMPT_VERSION,
    ContextExtractionResult,
)
from reweave.llm import ProviderRequestError
from reweave.web import create_app


class FakeJsonProvider:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def generate_json(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


def _wait_for_job(client: TestClient, job_id: str) -> dict:
    for _ in range(100):
        response = client.get(f"/api/context/analysis/jobs/{job_id}")
        assert response.status_code == 200
        job = response.json()
        if job["status"] in {"completed", "failed"}:
            return job
        sleep(0.01)
    pytest.fail("Context analysis job did not reach a terminal state.")


def _seed_archive(db_path, fixtures_dir):
    archive = ArchiveStore(db_path)
    archive.import_directory(fixtures_dir)
    conversation_id = archive.search("Obsidian", provider="claude", limit=1)[0].conversation_id
    return archive, conversation_id


def _provider_response():
    return {
        "brief": {
            "main_subject": "Organizing an Obsidian vault",
            "user_goal": "Choose a maintainable structure for notes.",
            "important_outcomes": ["Links should carry specific relationships."],
            "decisions": [],
            "lessons": ["Folders and links serve different navigation needs."],
            "unresolved_questions": ["How much metadata should be required?"],
            "actions": ["Try the structure with one project."],
        },
        "items": [
            {
                "canonical_text": "The user is organizing an Obsidian vault.",
                "type": "project_fact",
                "epistemic_kind": "observed",
                "confidence": 0.96,
                "sensitivity": "normal",
                "scopes": [{"type": "project", "key": "Obsidian", "confidence": 0.95}],
                "evidence": [
                    {
                        "message_index": 0,
                        "excerpt": "How should I organize my Obsidian vault?",
                        "relationship": "supports",
                    }
                ],
            }
        ],
    }


def _analysis_request(conversation_id: str, **settings):
    return {
        "conversation_id": conversation_id,
        "analysis_mode": "project",
        "settings": {
            "provider": "openai",
            "model": "test-model",
            "api_key": "test-key",
            **settings,
        },
    }


def test_context_analysis_job_reuses_results_and_exposes_durable_source_linked_reads(
    monkeypatch, tmp_path, fixtures_dir
):
    db_path = tmp_path / "archive.db"
    _, conversation_id = _seed_archive(db_path, fixtures_dir)
    provider = FakeJsonProvider(_provider_response())
    monkeypatch.setattr(reweave.context_extraction, "create_provider", lambda settings: provider)
    client = TestClient(create_app(db_path, data_dir=tmp_path / "app-data"))

    response = client.post("/api/context/analysis/jobs", json=_analysis_request(conversation_id))

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    first_job = _wait_for_job(client, response.json()["id"])
    assert first_job["status"] == "completed"
    assert first_job["progress"] == 100
    assert first_job["result"]["reused_existing"] is False
    assert first_job["result"]["brief"]["analysis_mode"] == "project"
    assert first_job["result"]["brief"]["analysis_status"] == "complete"
    assert first_job["result"]["brief"]["item_count"] == 1
    assert first_job["result"]["items"][0]["evidence"][0]["source_available"] is True
    assert len(provider.calls) == 1

    second_response = client.post(
        "/api/context/analysis/jobs", json=_analysis_request(conversation_id)
    )
    second_job = _wait_for_job(client, second_response.json()["id"])
    assert second_job["status"] == "completed"
    assert second_job["result"]["reused_existing"] is True
    assert len(provider.calls) == 1

    brief_id = first_job["result"]["brief"]["id"]
    item_id = first_job["result"]["items"][0]["id"]
    brief_list = client.get("/api/context/briefs").json()["results"]
    item_list = client.get("/api/context/items").json()["results"]
    brief = client.get(f"/api/context/briefs/{brief_id}").json()
    item = client.get(f"/api/context/items/{item_id}").json()
    assert [entry["id"] for entry in brief_list] == [brief_id]
    assert [entry["id"] for entry in item_list] == [item_id]
    assert brief["items"][0]["id"] == item_id
    assert item["scopes"][0]["scope_key"] == "Obsidian"
    assert item["versions"][0]["change_reason"] == "initial extraction"
    assert item["evidence"][0]["excerpt"] == "How should I organize my Obsidian vault?"

    assert client.delete(f"/api/conversations/{conversation_id}").status_code == 200
    restarted = TestClient(create_app(db_path, data_dir=tmp_path / "app-data"))
    durable_brief = restarted.get(f"/api/context/briefs/{brief_id}").json()
    durable_item = restarted.get(f"/api/context/items/{item_id}").json()
    assert durable_brief["source_conversation_id"] is None
    assert durable_brief["source_record_id"] == conversation_id
    assert durable_item["evidence"][0]["source_available"] is False
    assert durable_item["evidence"][0]["source_record_id"] == conversation_id
    assert durable_item["evidence"][0]["excerpt"] == ("How should I organize my Obsidian vault?")


def test_context_analysis_job_uses_saved_profile_credentials(monkeypatch, tmp_path, fixtures_dir):
    secrets = {}
    monkeypatch.setattr(
        reweave.llm_profiles.keyring,
        "set_password",
        lambda service, name, value: secrets.__setitem__((service, name), value),
    )
    monkeypatch.setattr(
        reweave.llm_profiles.keyring,
        "get_password",
        lambda service, name: secrets.get((service, name)),
    )
    monkeypatch.setattr(
        reweave.llm_profiles.keyring,
        "delete_password",
        lambda service, name: secrets.pop((service, name), None),
    )
    db_path = tmp_path / "archive.db"
    _, conversation_id = _seed_archive(db_path, fixtures_dir)
    client = TestClient(create_app(db_path, data_dir=tmp_path / "app-data"))
    profile = next(
        profile
        for profile in client.get("/api/llm/profiles").json()["profiles"]
        if profile["provider"] == "openai"
    )
    client.post(
        f"/api/llm/profiles/{profile['id']}/keys",
        json={"label": "Primary", "api_key": "profile-secret", "priority": 0},
    )
    captured = {}

    def fake_extract(
        archive_store,
        context_store,
        *,
        conversation_id,
        settings,
        analysis_mode,
        provider,
    ):
        captured.update(settings=settings, provider=provider)
        brief = context_store.save_brief(
            conversation_id=conversation_id,
            main_subject="Profile-backed analysis",
            user_goal="Use stored credentials without exposing them.",
            analysis_mode=analysis_mode,
            analysis_version=f"{CONTEXT_EXTRACTION_PROMPT_VERSION}:{analysis_mode}",
            prompt_version=CONTEXT_EXTRACTION_PROMPT_VERSION,
            analysis_provider=settings.provider,
            analysis_model=settings.model,
        )
        return ContextExtractionResult(
            brief=brief,
            items=(),
            analysis_version=brief.analysis_version,
            prompt_version=brief.prompt_version,
            reused_existing=False,
            dropped_items=0,
            deduplicated_items=0,
        )

    monkeypatch.setattr(reweave.web, "extract_context_from_conversation", fake_extract)
    response = client.post(
        "/api/context/analysis/jobs",
        json={
            "conversation_id": conversation_id,
            "analysis_mode": "auto",
            "settings": {"profile_id": profile["id"], "model": "profile-model"},
        },
    )
    job = _wait_for_job(client, response.json()["id"])

    assert job["status"] == "completed"
    assert captured["settings"].provider == "openai"
    assert captured["settings"].model == "profile-model"
    assert captured["provider"].credentials[0].api_key == "profile-secret"
    assert "profile-secret" not in str(job)


def test_context_analysis_api_reports_terminal_failures_and_not_found_resources(
    monkeypatch, tmp_path, fixtures_dir
):
    db_path = tmp_path / "archive.db"
    _, conversation_id = _seed_archive(db_path, fixtures_dir)
    provider = FakeJsonProvider(error=ProviderRequestError("Model rejected request."))
    monkeypatch.setattr(reweave.context_extraction, "create_provider", lambda settings: provider)
    client = TestClient(create_app(db_path, data_dir=tmp_path / "app-data"))

    response = client.post("/api/context/analysis/jobs", json=_analysis_request(conversation_id))
    job = _wait_for_job(client, response.json()["id"])

    assert job["status"] == "failed"
    assert job["stage"] == "failed"
    assert job["error"] == "Model rejected request."
    assert client.get("/api/context/briefs").json()["results"] == []
    assert client.get("/api/context/analysis/jobs/missing").status_code == 404
    assert client.get("/api/context/briefs/missing").status_code == 404
    assert client.get("/api/context/items/missing").status_code == 404

    missing_conversation = client.post(
        "/api/context/analysis/jobs", json=_analysis_request("missing")
    )
    assert missing_conversation.status_code == 404
    missing_profile = client.post(
        "/api/context/analysis/jobs",
        json=_analysis_request(conversation_id, profile_id="missing"),
    )
    assert missing_profile.status_code == 400
    invalid_mode = _analysis_request(conversation_id)
    invalid_mode["analysis_mode"] = "unsupported"
    assert client.post("/api/context/analysis/jobs", json=invalid_mode).status_code == 422
