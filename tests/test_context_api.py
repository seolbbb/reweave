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
    conversation_source_fingerprint,
)
from reweave.context_library import ContextLibraryStore
from reweave.llm import ModelDiscoveryResult, ProviderRateLimitError, ProviderRequestError
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


def _wait_for_queue_job(client: TestClient, job_id: str) -> dict:
    for _ in range(100):
        response = client.get(f"/api/context/analysis/queue/{job_id}")
        assert response.status_code == 200
        job = response.json()
        if job["status"] in {"complete", "failed", "superseded"}:
            return job
        sleep(0.01)
    pytest.fail("Durable Context analysis queue job did not reach a terminal state.")


def _wait_for_queue_condition(client: TestClient, job_id: str, predicate) -> dict:
    for _ in range(100):
        response = client.get(f"/api/context/analysis/queue/{job_id}")
        assert response.status_code == 200
        job = response.json()
        if predicate(job):
            return job
        sleep(0.01)
    pytest.fail("Durable Context analysis queue job did not reach the expected state.")


def _seed_archive(db_path, fixtures_dir):
    archive = ArchiveStore(db_path)
    archive.import_directory(fixtures_dir)
    conversation_id = archive.search("Obsidian", provider="claude", limit=1)[0].conversation_id
    return archive, conversation_id


def _seed_analysis_queue(db_path, fixtures_dir, *, analysis_mode="project"):
    archive, conversation_id = _seed_archive(db_path, fixtures_dir)
    context = ContextLibraryStore(db_path)
    job, _ = context.enqueue_analysis(
        conversation_id=conversation_id,
        source_fingerprint=conversation_source_fingerprint(archive, conversation_id),
        analysis_mode=analysis_mode,
    )
    return conversation_id, job


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


def _fake_keyring(monkeypatch):
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
    return secrets


def _save_fake_extraction(
    archive_store,
    context_store,
    *,
    conversation_id,
    settings,
    analysis_mode,
    provider,
):
    brief = context_store.save_brief(
        conversation_id=conversation_id,
        main_subject="Scheduled Context analysis",
        user_goal="Process durable work through the saved provider profile.",
        analysis_mode=analysis_mode,
        analysis_version=f"{CONTEXT_EXTRACTION_PROMPT_VERSION}:{analysis_mode}",
        prompt_version=CONTEXT_EXTRACTION_PROMPT_VERSION,
        analysis_provider=settings.provider,
        analysis_model=settings.model,
        source_fingerprint=conversation_source_fingerprint(archive_store, conversation_id),
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


def test_durable_queue_retry_completes_idempotent_extraction_without_storing_key(
    monkeypatch, tmp_path, fixtures_dir
):
    db_path = tmp_path / "archive.db"
    _, queued = _seed_analysis_queue(db_path, fixtures_dir)
    provider = FakeJsonProvider(_provider_response())
    monkeypatch.setattr(reweave.context_extraction, "create_provider", lambda settings: provider)
    client = TestClient(create_app(db_path, data_dir=tmp_path / "app-data"))

    response = client.post(
        f"/api/context/analysis/queue/{queued.id}/retry",
        json={
            "settings": {
                "provider": "openai",
                "model": "test-model",
                "api_key": "queue-test-secret",
            }
        },
    )

    assert response.status_code == 202
    assert response.json()["status"] == "running"
    completed = _wait_for_queue_job(client, queued.id)
    assert completed["status"] == "complete"
    assert completed["attempt_count"] == 1
    assert completed["result_brief_id"]
    assert len(provider.calls) == 1
    assert b"queue-test-secret" not in db_path.read_bytes()
    assert (
        client.post(
            f"/api/context/analysis/queue/{queued.id}/retry",
            json={"settings": {"api_key": "queue-test-secret"}},
        ).status_code
        == 409
    )


def test_durable_queue_preserves_sanitized_provider_failure_across_restart_and_retries(
    monkeypatch, tmp_path, fixtures_dir
):
    db_path = tmp_path / "archive.db"
    _, queued = _seed_analysis_queue(db_path, fixtures_dir)
    failing = FakeJsonProvider(error=ProviderRequestError("secret-bearing provider detail"))
    monkeypatch.setattr(reweave.context_extraction, "create_provider", lambda settings: failing)
    data_dir = tmp_path / "app-data"
    client = TestClient(create_app(db_path, data_dir=data_dir))

    first_response = client.post(
        f"/api/context/analysis/queue/{queued.id}/retry",
        json={"settings": {"api_key": "first-secret", "model": "test-model"}},
    )
    assert first_response.status_code == 202
    failed = _wait_for_queue_job(client, queued.id)
    assert failed["status"] == "failed"
    assert failed["attempt_count"] == 1
    assert failed["last_error_code"] == "provider_request"
    assert failed["last_error_summary"] == "The provider request failed."
    assert "secret-bearing" not in str(failed)

    restarted = TestClient(create_app(db_path, data_dir=data_dir))
    assert restarted.get(f"/api/context/analysis/queue/{queued.id}").json() == failed
    succeeding = FakeJsonProvider(_provider_response())
    monkeypatch.setattr(reweave.context_extraction, "create_provider", lambda settings: succeeding)
    retry_response = restarted.post(
        f"/api/context/analysis/queue/{queued.id}/retry",
        json={"settings": {"api_key": "second-secret", "model": "test-model"}},
    )
    assert retry_response.status_code == 202
    completed = _wait_for_queue_job(restarted, queued.id)
    assert completed["status"] == "complete"
    assert completed["attempt_count"] == 2
    assert completed["last_error_code"] is None


def test_durable_queue_missing_key_failure_remains_readable_and_retryable(
    tmp_path, fixtures_dir
):
    db_path = tmp_path / "archive.db"
    _, queued = _seed_analysis_queue(db_path, fixtures_dir, analysis_mode="auto")
    client = TestClient(create_app(db_path, data_dir=tmp_path / "app-data"))

    response = client.post(f"/api/context/analysis/queue/{queued.id}/retry", json={})

    assert response.status_code == 202
    failed = _wait_for_queue_job(client, queued.id)
    assert failed["status"] == "failed"
    assert failed["last_error_code"] == "provider_configuration"
    assert failed["last_error_summary"] == "A connected provider is required for analysis."
    assert failed["result_brief_id"] is None


def test_durable_queue_retry_uses_current_saved_profile_without_persisting_secret(
    monkeypatch, tmp_path, fixtures_dir
):
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
    _, queued = _seed_analysis_queue(db_path, fixtures_dir, analysis_mode="auto")
    client = TestClient(create_app(db_path, data_dir=tmp_path / "app-data"))
    profile = next(
        profile
        for profile in client.get("/api/llm/profiles").json()["profiles"]
        if profile["provider"] == "openai"
    )
    client.post(
        f"/api/llm/profiles/{profile['id']}/keys",
        json={"label": "Primary", "api_key": "queue-profile-secret", "priority": 0},
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
            main_subject="Profile-backed queue analysis",
            user_goal="Use the current stored profile at retry time.",
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
        f"/api/context/analysis/queue/{queued.id}/retry",
        json={"settings": {"profile_id": profile["id"], "model": "profile-model"}},
    )
    completed = _wait_for_queue_job(client, queued.id)

    assert response.status_code == 202
    assert completed["status"] == "complete"
    assert captured["settings"].provider == "openai"
    assert captured["provider"].credentials[0].api_key == "queue-profile-secret"
    assert "queue-profile-secret" not in str(completed)
    assert b"queue-profile-secret" not in db_path.read_bytes()


def test_scheduler_processes_pending_work_on_startup_with_local_estimates(
    monkeypatch, tmp_path, fixtures_dir
):
    _fake_keyring(monkeypatch)
    db_path = tmp_path / "archive.db"
    data_dir = tmp_path / "app-data"
    _, queued = _seed_analysis_queue(db_path, fixtures_dir, analysis_mode="auto")
    bootstrap = TestClient(create_app(db_path, data_dir=data_dir))
    profile = next(
        item
        for item in bootstrap.get("/api/llm/profiles").json()["profiles"]
        if item["provider"] == "openai"
    )
    bootstrap.post(
        f"/api/llm/profiles/{profile['id']}/keys",
        json={"label": "Primary", "api_key": "startup-secret", "priority": 0},
    )
    bootstrap.post("/api/llm/profiles/active", json={"profile_id": profile["id"]})
    observed = {}

    def scheduled_extract(
        archive_store,
        context_store,
        *,
        conversation_id,
        settings,
        analysis_mode,
        provider,
    ):
        running = context_store.list_analysis_queue_jobs(status="running")[0]
        observed["characters"] = running.estimated_input_characters
        observed["tokens"] = running.estimated_input_tokens
        return _save_fake_extraction(
            archive_store,
            context_store,
            conversation_id=conversation_id,
            settings=settings,
            analysis_mode=analysis_mode,
            provider=provider,
        )

    monkeypatch.setattr(reweave.web, "extract_context_from_conversation", scheduled_extract)
    app = create_app(db_path, data_dir=data_dir)
    with TestClient(app) as client:
        completed = _wait_for_queue_job(client, queued.id)

    assert completed["status"] == "complete"
    assert completed["attempt_count"] == 1
    assert completed["next_retry_at"] is None
    assert observed["characters"] == completed["estimated_input_characters"]
    assert observed["tokens"] == completed["estimated_input_tokens"]
    assert observed["characters"] > 0
    assert observed["tokens"] > 0
    assert b"startup-secret" not in db_path.read_bytes()


def test_scheduler_defers_without_key_then_wakes_after_profile_connection(
    monkeypatch, tmp_path, fixtures_dir
):
    _fake_keyring(monkeypatch)
    db_path = tmp_path / "archive.db"
    data_dir = tmp_path / "app-data"
    _, queued = _seed_analysis_queue(db_path, fixtures_dir)
    monkeypatch.setattr(reweave.web, "extract_context_from_conversation", _save_fake_extraction)
    monkeypatch.setattr(
        reweave.web,
        "discover_available_models",
        lambda settings, credentials: ModelDiscoveryResult(
            models=("gpt-scheduled",),
            credential_label=credentials[0].label,
        ),
    )
    app = create_app(db_path, data_dir=data_dir)

    with TestClient(app) as client:
        pending = client.get(f"/api/context/analysis/queue/{queued.id}").json()
        assert pending["status"] == "pending"
        assert pending["attempt_count"] == 0
        profile = next(
            item
            for item in client.get("/api/llm/profiles").json()["profiles"]
            if item["provider"] == "openai"
        )
        response = client.post(
            f"/api/llm/profiles/{profile['id']}/connect",
            json={"api_key": "connected-secret"},
        )
        completed = _wait_for_queue_job(client, queued.id)

    assert response.status_code == 200
    assert completed["status"] == "complete"
    assert completed["attempt_count"] == 1


def test_automatic_scheduler_offline_deferral_does_not_consume_an_attempt(
    monkeypatch, tmp_path, fixtures_dir
):
    _fake_keyring(monkeypatch)
    db_path = tmp_path / "archive.db"
    data_dir = tmp_path / "app-data"
    _, queued = _seed_analysis_queue(db_path, fixtures_dir)
    bootstrap = TestClient(create_app(db_path, data_dir=data_dir))
    profile = bootstrap.get("/api/llm/profiles").json()["profiles"][0]
    bootstrap.post(
        f"/api/llm/profiles/{profile['id']}/keys",
        json={"label": "Primary", "api_key": "offline-secret", "priority": 0},
    )
    bootstrap.post("/api/llm/profiles/active", json={"profile_id": profile["id"]})

    def offline_extract(*args, **kwargs):
        request = reweave.web.httpx.Request("POST", "https://provider.invalid")
        raise reweave.web.httpx.ConnectError("offline detail", request=request)

    monkeypatch.setattr(reweave.web, "extract_context_from_conversation", offline_extract)
    app = create_app(db_path, data_dir=data_dir)
    with TestClient(app) as client:
        deferred = _wait_for_queue_condition(
            client,
            queued.id,
            lambda job: job["status"] == "pending" and job["last_error_code"] == "offline",
        )

    assert deferred["attempt_count"] == 0
    assert deferred["last_error_summary"] == (
        "The provider could not be reached; analysis remains pending."
    )
    assert deferred["next_retry_at"] is not None
    assert deferred["estimated_input_characters"] > 0
    assert "offline detail" not in str(deferred)


def test_automatic_scheduler_applies_bounded_backoff_and_retries_due_work(
    monkeypatch, tmp_path, fixtures_dir
):
    _fake_keyring(monkeypatch)
    db_path = tmp_path / "archive.db"
    data_dir = tmp_path / "app-data"
    _, queued = _seed_analysis_queue(db_path, fixtures_dir)
    app = create_app(db_path, data_dir=data_dir)
    client = TestClient(app)
    profile = client.get("/api/llm/profiles").json()["profiles"][0]
    client.post(
        f"/api/llm/profiles/{profile['id']}/keys",
        json={"label": "Primary", "api_key": "retry-secret", "priority": 0},
    )
    client.post("/api/llm/profiles/active", json={"profile_id": profile["id"]})
    attempts = []

    def scheduled_extract(
        archive_store,
        context_store,
        *,
        conversation_id,
        settings,
        analysis_mode,
        provider,
    ):
        attempts.append(conversation_id)
        if len(attempts) == 1:
            raise ProviderRateLimitError("secret provider detail")
        return _save_fake_extraction(
            archive_store,
            context_store,
            conversation_id=conversation_id,
            settings=settings,
            analysis_mode=analysis_mode,
            provider=provider,
        )

    monkeypatch.setattr(reweave.web, "extract_context_from_conversation", scheduled_extract)
    monkeypatch.setattr(
        reweave.web,
        "_context_queue_retry_at",
        lambda attempt_count: "2000-01-01T00:00:00+00:00",
    )

    first_run = app.state.context_analysis_scheduler.run_once()
    failed = client.get(f"/api/context/analysis/queue/{queued.id}").json()
    second_run = app.state.context_analysis_scheduler.run_once()
    completed = client.get(f"/api/context/analysis/queue/{queued.id}").json()

    assert first_run.claimed_job_ids == (queued.id,)
    assert failed["status"] == "failed"
    assert failed["attempt_count"] == 1
    assert failed["last_error_code"] == "provider_rate_limit"
    assert failed["last_error_summary"] == "The provider rate limit interrupted analysis."
    assert failed["next_retry_at"] == "2000-01-01T00:00:00+00:00"
    assert "secret provider detail" not in str(failed)
    assert second_run.claimed_job_ids == (queued.id,)
    assert completed["status"] == "complete"
    assert completed["attempt_count"] == 2
    assert completed["next_retry_at"] is None
