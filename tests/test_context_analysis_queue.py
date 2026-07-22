"""Durable Context analysis queue persistence tests."""

import sqlite3

import pytest

from reweave.archive import ArchiveStore
from reweave.context_extraction import conversation_source_fingerprint
from reweave.context_library import ContextLibraryStore


def _seed_queue(tmp_path, fixtures_dir):
    db_path = tmp_path / "archive.db"
    archive = ArchiveStore(db_path)
    archive.import_directory(fixtures_dir)
    conversation_id = archive.search("Obsidian", provider="claude", limit=1)[0].conversation_id
    context = ContextLibraryStore(db_path)
    fingerprint = conversation_source_fingerprint(archive, conversation_id)
    return db_path, context, conversation_id, fingerprint


def test_queue_is_idempotent_per_source_version_and_supersedes_stale_work(
    tmp_path, fixtures_dir
):
    _, context, conversation_id, fingerprint = _seed_queue(tmp_path, fixtures_dir)

    first, created = context.enqueue_analysis(
        conversation_id=conversation_id,
        source_fingerprint=fingerprint,
    )
    repeated, repeated_created = context.enqueue_analysis(
        conversation_id=conversation_id,
        source_fingerprint=fingerprint,
    )
    repeated_with_another_mode, another_mode_created = context.enqueue_analysis(
        conversation_id=conversation_id,
        source_fingerprint=fingerprint,
        analysis_mode="project",
    )
    replacement, replacement_created = context.enqueue_analysis(
        conversation_id=conversation_id,
        source_fingerprint="new-source-version",
    )

    assert created is True
    assert repeated_created is False
    assert repeated.id == first.id
    assert another_mode_created is False
    assert repeated_with_another_mode.id == first.id
    assert replacement_created is True
    assert context.get_analysis_queue_job(first.id).status == "superseded"
    assert replacement.status == "pending"
    assert len(context.list_analysis_queue_jobs()) == 2


def test_running_queue_work_recovers_as_retryable_without_storing_credentials(
    tmp_path, fixtures_dir
):
    db_path, context, conversation_id, fingerprint = _seed_queue(tmp_path, fixtures_dir)
    pending, _ = context.enqueue_analysis(
        conversation_id=conversation_id,
        source_fingerprint=fingerprint,
        analysis_mode="project",
    )

    running = context.start_analysis_queue_job(pending.id)
    assert running.status == "running"
    assert running.attempt_count == 1

    restarted = ContextLibraryStore(db_path)
    assert restarted.get_analysis_queue_job(pending.id).status == "running"
    assert restarted.recover_interrupted_analysis_jobs() == 1
    recovered = restarted.get_analysis_queue_job(pending.id)
    assert recovered.status == "failed"
    assert recovered.last_error_code == "interrupted"
    assert recovered.attempt_count == 1

    retried = restarted.start_analysis_queue_job(pending.id)
    failed = restarted.fail_analysis_queue_job(
        retried.id,
        error_code="provider_request",
        error_summary="The provider request failed.",
    )
    assert failed.status == "failed"
    assert failed.attempt_count == 2

    with sqlite3.connect(db_path) as conn:
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(context_analysis_queue)").fetchall()
        }
        schema_version = conn.execute(
            "SELECT value FROM schema_meta WHERE key = 'context_schema_version'"
        ).fetchone()[0]
    assert schema_version == "5"
    assert "api_key" not in columns
    assert "profile_id" not in columns
    assert {
        "next_retry_at",
        "estimated_input_characters",
        "estimated_input_tokens",
    } <= columns


def test_scheduler_claims_are_bounded_atomic_and_keep_offline_deferral_attempt_free(
    tmp_path, fixtures_dir
):
    db_path = tmp_path / "archive.db"
    archive = ArchiveStore(db_path)
    archive.import_directory(fixtures_dir)
    conversation_ids = [
        archive.search(query, limit=1)[0].conversation_id
        for query in ("Obsidian", "Zettelkasten")
    ]
    context = ContextLibraryStore(db_path)
    queued = [
        context.enqueue_analysis(
            conversation_id=conversation_id,
            source_fingerprint=conversation_source_fingerprint(archive, conversation_id),
        )[0]
        for conversation_id in conversation_ids
    ]

    first_batch = context.claim_ready_analysis_queue_jobs(limit=1)
    second_batch = context.claim_ready_analysis_queue_jobs(limit=1)

    assert len(first_batch) == 1
    assert len(second_batch) == 1
    assert {first_batch[0].id, second_batch[0].id} == {job.id for job in queued}
    assert context.claim_ready_analysis_queue_jobs(limit=1) == []
    with pytest.raises(ValueError):
        context.start_analysis_queue_job(first_batch[0].id)

    deferred = context.defer_analysis_queue_job(
        first_batch[0].id,
        error_code="offline",
        error_summary="The provider could not be reached.",
        next_retry_at="2099-01-01T00:00:00+00:00",
    )
    assert deferred.status == "pending"
    assert deferred.attempt_count == 0
    assert deferred.next_retry_at == "2099-01-01T00:00:00+00:00"
    assert (
        context.claim_ready_analysis_queue_jobs(
            limit=1,
            ready_at="2098-12-31T23:59:59+00:00",
        )
        == []
    )

    reclaimed = context.claim_ready_analysis_queue_jobs(
        limit=1,
        ready_at="2099-01-01T00:00:00+00:00",
    )[0]
    estimated = context.record_analysis_queue_input_estimate(
        reclaimed.id,
        input_characters=12_345,
        input_tokens=3_456,
    )
    assert estimated.attempt_count == 1
    assert estimated.estimated_input_characters == 12_345
    assert estimated.estimated_input_tokens == 3_456

    failed = context.fail_analysis_queue_job(
        reclaimed.id,
        error_code="provider_rate_limit",
        error_summary="The provider rate limit interrupted analysis.",
        next_retry_at="2099-01-01T00:01:00+00:00",
    )
    assert failed.status == "failed"
    assert failed.next_retry_at == "2099-01-01T00:01:00+00:00"


def test_schema_v4_queue_migrates_scheduler_metadata_without_losing_pending_work(
    tmp_path, fixtures_dir
):
    db_path = tmp_path / "archive.db"
    archive = ArchiveStore(db_path)
    archive.import_directory(fixtures_dir)
    conversation_id = archive.search("Obsidian", limit=1)[0].conversation_id
    fingerprint = conversation_source_fingerprint(archive, conversation_id)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE context_analysis_queue (
                id TEXT PRIMARY KEY,
                source_conversation_id TEXT,
                source_record_id TEXT NOT NULL,
                source_fingerprint TEXT NOT NULL,
                analysis_mode TEXT NOT NULL,
                status TEXT NOT NULL,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                last_error_code TEXT,
                last_error_summary TEXT,
                result_brief_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_attempt_at TEXT,
                completed_at TEXT,
                UNIQUE(source_record_id, source_fingerprint)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO context_analysis_queue (
                id, source_conversation_id, source_record_id, source_fingerprint,
                analysis_mode, status, attempt_count, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'auto', 'pending', 0, ?, ?)
            """,
            (
                "legacy-pending",
                conversation_id,
                conversation_id,
                fingerprint,
                "2026-07-21T00:00:00+00:00",
                "2026-07-21T00:00:00+00:00",
            ),
        )
        conn.execute(
            "INSERT OR REPLACE INTO schema_meta(key, value) VALUES (?, ?)",
            ("context_schema_version", "4"),
        )

    migrated = ContextLibraryStore(db_path)
    job = migrated.get_analysis_queue_job("legacy-pending")

    assert job is not None
    assert job.status == "pending"
    assert job.attempt_count == 0
    assert job.next_retry_at is None
    assert job.estimated_input_characters is None
    assert job.estimated_input_tokens is None
    with sqlite3.connect(db_path) as conn:
        schema_version = conn.execute(
            "SELECT value FROM schema_meta WHERE key = 'context_schema_version'"
        ).fetchone()[0]
    assert schema_version == "5"
