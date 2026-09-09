"""Automatic analysis waits for an idle interval or a useful bounded batch."""

from concurrent.futures import Future
from datetime import UTC, datetime, timedelta

from reweave.archive import ArchiveStore
from reweave.context_library import ContextLibraryStore
from reweave.context_scheduler import ContextAnalysisScheduler, SchedulerRuntime
from reweave.llm import LLMSettings


def test_idle_interval_and_explicit_reanalysis(tmp_path, fixtures_dir):
    archive = ArchiveStore(tmp_path / "archive.db")
    archive.import_directory(fixtures_dir)
    library = ContextLibraryStore(archive.db_path)
    source = archive.search("Obsidian", limit=1)[0].conversation_id
    job, _ = library.enqueue_analysis(conversation_id=source, source_fingerprint="current")
    now = datetime.now(UTC)
    with library._connect() as conn:
        conn.execute("UPDATE context_analysis_queue SET created_at=?", (now.isoformat(),))
    submitted = []

    def submit(job_id, settings, provider):
        submitted.append(job_id)
        future = Future()
        future.set_result(None)
        return future

    scheduler = ContextAnalysisScheduler(
        library,
        resolve_runtime=lambda: SchedulerRuntime(
            LLMSettings(provider="openai", model="synthetic", api_key="test"), object()
        ),
        submit_job=submit,
        clock=lambda: now,
    )
    assert scheduler.run_once().claimed_job_ids == ()
    assert not submitted
    now += timedelta(seconds=29)
    assert scheduler.run_once().claimed_job_ids == ()
    now += timedelta(seconds=1)
    assert scheduler.run_once().claimed_job_ids == (job.id,)
    library.fail_analysis_queue_job(job.id, error_code="test", error_summary="synthetic")
    assert not scheduler._batch_ready()
    with library._connect() as conn:
        conn.execute(
            "UPDATE context_analysis_queue SET status='pending', analysis_generation=1, "
            "created_at=?",
            (now.isoformat(),),
        )
    assert scheduler.run_once().claimed_job_ids == (job.id,)


def test_three_fresh_sources_start_one_batch(tmp_path, fixtures_dir):
    archive = ArchiveStore(tmp_path / "archive.db")
    archive.import_directory(fixtures_dir)
    library = ContextLibraryStore(archive.db_path)
    with archive._connect() as conn:
        ids = [row[0] for row in conn.execute("SELECT id FROM conversations LIMIT 3")]
    for source in ids:
        library.enqueue_analysis(conversation_id=source, source_fingerprint=source)
    future = Future()
    future.set_result(None)
    scheduler = ContextAnalysisScheduler(
        library,
        resolve_runtime=lambda: SchedulerRuntime(
            LLMSettings(provider="openai", model="synthetic", api_key="test"), object()
        ),
        submit_job=lambda *args: future,
    )
    assert set(scheduler.run_once().claimed_job_ids) == {
        job.id for job in library.list_analysis_queue_jobs()
    }


def test_disconnect_after_first_source_defers_unstarted_batch_jobs(tmp_path, fixtures_dir):
    archive = ArchiveStore(tmp_path / "archive.db")
    archive.import_directory(fixtures_dir)
    library = ContextLibraryStore(archive.db_path)
    with archive._connect() as conn:
        ids = [row[0] for row in conn.execute("SELECT id FROM conversations LIMIT 3")]
    for source in ids:
        library.enqueue_analysis(conversation_id=source, source_fingerprint=source)
    runtime = SchedulerRuntime(
        LLMSettings(provider="openai", model="test", api_key="test"),
        object(),
    )
    connected = [True]
    submitted = []

    def submit(job_id, *args):
        submitted.append(job_id)
        connected[0] = False
        future = Future()
        future.set_result(None)
        return future

    scheduler = ContextAnalysisScheduler(
        library,
        resolve_runtime=lambda: runtime if connected[0] else None,
        submit_job=submit,
    )
    scheduler.run_once()
    assert len(submitted) == 1
    pending = library.list_analysis_queue_jobs(status="pending")
    assert len(pending) == 2
    assert all(
        job.attempt_count == 0 and job.last_error_code == "connection_changed" for job in pending
    )
