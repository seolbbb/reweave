"""Conservative analysis allowances and imported-source queue continuity."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from reweave.analysis_policy import (
    AnalysisLimitError,
    AnalysisPolicy,
    AnalysisPolicyStore,
    BudgetedProvider,
)
from reweave.web import create_app


def test_reservation_is_atomic_and_survives_restart(tmp_path):
    path = tmp_path / "archive.db"
    store = AnalysisPolicyStore(path)
    store.save(AnalysisPolicy(daily_attempt_limit=2, daily_token_limit=10_000))

    def reserve():
        try:
            store.reserve(attempts=1, tokens=1000)
            return True
        except AnalysisLimitError:
            return False

    with ThreadPoolExecutor(max_workers=4) as executor:
        assert sum(executor.map(lambda _: reserve(), range(8))) == 2
    restarted = AnalysisPolicyStore(path)
    assert restarted.usage()["reserved_attempts"] == 2
    assert restarted.usage()["reserved_tokens"] == 2000
    assert restarted.usage()["currency_cost"] is None


def test_guard_stops_calls_before_generation_and_counts_failover_ceiling(tmp_path):
    class Provider:
        credentials = (object(), object())
        calls = 0

        def generate_json(self, **kwargs):
            self.calls += 1
            return {"items": []}

    store = AnalysisPolicyStore(tmp_path / "archive.db")
    provider = Provider()
    wrapped = BudgetedProvider(provider, store)
    store.save(AnalysisPolicy(daily_attempt_limit=1))
    with pytest.raises(AnalysisLimitError):
        wrapped.generate_json(system="rules", user="source", max_tokens=50)
    assert provider.calls == 0
    store.save(AnalysisPolicy(daily_attempt_limit=2))
    assert wrapped.generate_json(system="rules", user="source", max_tokens=50) == {"items": []}
    assert store.usage()["reserved_attempts"] == 2
    store.save(AnalysisPolicy(enabled=False))
    with pytest.raises(AnalysisLimitError, match="paused"):
        wrapped.generate_json(system="rules", user="source", max_tokens=50)
    assert provider.calls == 1


def test_import_enqueues_sources_without_key_and_restart_keeps_same_jobs(tmp_path, fixtures_dir):
    db_path = tmp_path / "archive.db"
    with TestClient(create_app(db_path, data_dir=tmp_path)) as client:
        imported = client.post("/api/import/path", json={"path": str(fixtures_dir)})
        assert imported.status_code == 200
        assert imported.json()["queued_conversations"] == 4
        jobs = client.get("/api/context/analysis/queue").json()["results"]
        assert len(jobs) == 4
        assert all(job["status"] == "pending" and job["attempt_count"] == 0 for job in jobs)
        first_ids = {job["id"] for job in jobs}
        assert client.post("/api/import/path", json={"path": str(fixtures_dir)}).status_code == 200
        assert {
            job["id"] for job in client.get("/api/context/analysis/queue").json()["results"]
        } == first_ids
        assert client.get("/api/context/analysis/policy").json()["provider_connected"] is False

    with TestClient(create_app(db_path, data_dir=tmp_path)) as client:
        jobs = client.get("/api/context/analysis/queue").json()["results"]
        assert {job["id"] for job in jobs} == first_ids
        assert all(job["status"] == "pending" for job in jobs)
        invalid = client.post(
            "/api/context/analysis/queue",
            json={"conversation_ids": [jobs[0]["source_record_id"], "missing"]},
        )
        assert invalid.status_code == 404
        assert len(client.get("/api/context/analysis/queue").json()["results"]) == 4


def test_analysis_policy_roundtrip_and_validation(tmp_path):
    with TestClient(create_app(tmp_path / "archive.db", data_dir=tmp_path)) as client:
        result = client.put(
            "/api/context/analysis/policy",
            json={
                "enabled": False,
                "daily_attempt_limit": 3,
                "daily_token_limit": 50_000,
                "analysis_mode": "learning",
                "personal_instructions": "Prefer concise lessons.",
            },
        )
        assert result.status_code == 200
        assert result.json()["policy"]["enabled"] is False
        assert (
            client.get("/api/context/analysis/policy").json()["policy"] == result.json()["policy"]
        )
        assert (
            client.put("/api/context/analysis/policy", json={"daily_attempt_limit": 0}).status_code
            == 422
        )
