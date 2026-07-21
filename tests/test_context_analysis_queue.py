"""Durable Context analysis queue persistence tests."""

import sqlite3

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
    assert schema_version == "4"
    assert "api_key" not in columns
    assert "profile_id" not in columns
