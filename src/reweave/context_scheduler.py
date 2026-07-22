"""Bounded local scheduler for durable Context analysis work."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass
from threading import Event, Thread
from typing import Any

from reweave.context_library import ContextLibraryStore
from reweave.llm import LLMSettings


@dataclass(frozen=True)
class SchedulerRuntime:
    """One connected saved-profile runtime resolved only when work is claimed."""

    settings: LLMSettings
    provider: Any


@dataclass(frozen=True)
class SchedulerRun:
    """Observable result from one deterministic bounded scheduler pass."""

    profile_available: bool
    claimed_job_ids: tuple[str, ...]


class ContextAnalysisScheduler:
    """Wake-driven scheduler that serializes durable jobs through the shared executor."""

    def __init__(
        self,
        context_store: ContextLibraryStore,
        *,
        resolve_runtime: Callable[[], SchedulerRuntime | None],
        submit_job: Callable[[str, LLMSettings, Any], Future[Any]],
        batch_size: int = 3,
        poll_seconds: float = 30.0,
    ) -> None:
        self.context_store = context_store
        self.resolve_runtime = resolve_runtime
        self.submit_job = submit_job
        self.batch_size = min(max(int(batch_size), 1), 20)
        self.poll_seconds = max(float(poll_seconds), 1.0)
        self._wake_event = Event()
        self._stop_event = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        """Start one daemon worker and immediately schedule the startup pass."""
        if self._thread is not None and self._thread.is_alive():
            self.wake()
            return
        self._stop_event.clear()
        self._thread = Thread(
            target=self._run_loop,
            name="reweave-context-scheduler",
            daemon=True,
        )
        self._thread.start()
        self.wake()

    def stop(self) -> None:
        """Stop future passes without blocking shutdown on a provider request."""
        self._stop_event.set()
        self._wake_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    def wake(self) -> None:
        """Request a scheduler pass after capture or saved-profile connection."""
        self._wake_event.set()

    def run_once(self) -> SchedulerRun:
        """Resolve one saved profile, atomically claim one batch, and wait for serialized work."""
        runtime = self.resolve_runtime()
        if runtime is None:
            return SchedulerRun(profile_available=False, claimed_job_ids=())
        jobs = self.context_store.claim_ready_analysis_queue_jobs(limit=self.batch_size)
        for job in jobs:
            self.submit_job(job.id, runtime.settings, runtime.provider).result()
        return SchedulerRun(
            profile_available=True,
            claimed_job_ids=tuple(job.id for job in jobs),
        )

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            self._wake_event.wait(timeout=self.poll_seconds)
            self._wake_event.clear()
            if self._stop_event.is_set():
                break
            try:
                result = self.run_once()
            except Exception:
                continue
            if len(result.claimed_job_ids) == self.batch_size:
                self._wake_event.set()
