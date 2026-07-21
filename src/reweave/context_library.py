"""Durable Conversation Brief and Context Item persistence."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from reweave.archive import ArchiveStore

AnalysisMode = Literal["auto", "project", "learning", "research_writing", "context_handoff"]
ContextItemType = Literal[
    "insight",
    "concept",
    "value",
    "preference",
    "decision",
    "lesson",
    "project_fact",
    "open_question",
    "action",
    "follow_up",
]
EpistemicKind = Literal["observed", "inferred", "suggested"]
Sensitivity = Literal["normal", "sensitive"]
ContextStatus = Literal["active", "superseded", "stale", "archived"]
ScopeType = Literal["core_self", "personal", "work", "project", "topic", "destination"]
EvidenceRelationship = Literal["supports", "contradicts", "context"]
BriefAnalysisStatus = Literal["pending", "complete", "failed"]
AnalysisQueueStatus = Literal["pending", "running", "failed", "complete", "superseded"]

ANALYSIS_MODES = {"auto", "project", "learning", "research_writing", "context_handoff"}
CONTEXT_ITEM_TYPES = {
    "insight",
    "concept",
    "value",
    "preference",
    "decision",
    "lesson",
    "project_fact",
    "open_question",
    "action",
    "follow_up",
}
EPISTEMIC_KINDS = {"observed", "inferred", "suggested"}
SENSITIVITIES = {"normal", "sensitive"}
CONTEXT_STATUSES = {"active", "superseded", "stale", "archived"}
SCOPE_TYPES = {"core_self", "personal", "work", "project", "topic", "destination"}
EVIDENCE_RELATIONSHIPS = {"supports", "contradicts", "context"}
BRIEF_ANALYSIS_STATUSES = {"pending", "complete", "failed"}
ANALYSIS_QUEUE_STATUSES = {"pending", "running", "failed", "complete", "superseded"}


@dataclass(frozen=True)
class ScopeInput:
    scope_type: str
    scope_key: str = ""
    confidence: float = 1.0


@dataclass(frozen=True)
class EvidenceInput:
    conversation_id: str
    message_id: str
    relationship: str = "supports"
    excerpt: str = ""


@dataclass(frozen=True)
class ContextScope:
    item_id: str
    scope_type: str
    scope_key: str
    confidence: float
    created_at: str


@dataclass(frozen=True)
class ContextEvidence:
    id: str
    item_id: str
    source_conversation_id: str | None
    source_message_id: str | None
    source_record_id: str
    source_external_id: str | None
    source_message_record_id: str
    source_provider: str
    source_title: str
    source_message_index: int
    source_role: str
    source_timestamp: str | None
    excerpt: str
    relationship: str
    created_at: str


@dataclass(frozen=True)
class ContextItemVersion:
    item_id: str
    version: int
    canonical_text: str
    item_type: str
    epistemic_kind: str
    confidence: float
    sensitivity: str
    status: str
    last_confirmed_at: str | None
    stale_at: str | None
    change_reason: str
    created_at: str


@dataclass(frozen=True)
class ContextItemLink:
    source_item_id: str
    target_item_id: str
    relationship: str
    created_at: str


@dataclass(frozen=True)
class ContextItem:
    id: str
    canonical_text: str
    item_type: str
    epistemic_kind: str
    confidence: float
    sensitivity: str
    status: str
    current_version: int
    created_at: str
    updated_at: str
    last_confirmed_at: str | None
    stale_at: str | None
    scopes: tuple[ContextScope, ...]
    evidence: tuple[ContextEvidence, ...]
    versions: tuple[ContextItemVersion, ...]
    links: tuple[ContextItemLink, ...]


@dataclass(frozen=True)
class ConversationBrief:
    id: str
    source_conversation_id: str | None
    source_record_id: str
    source_external_id: str | None
    source_provider: str
    source_title: str
    source_created_at: str
    source_fingerprint: str
    main_subject: str
    user_goal: str
    important_outcomes: tuple[str, ...]
    decisions: tuple[str, ...]
    lessons: tuple[str, ...]
    unresolved_questions: tuple[str, ...]
    actions: tuple[str, ...]
    analysis_mode: str
    analysis_version: str
    prompt_version: str
    analysis_provider: str
    analysis_model: str
    analysis_status: str
    created_at: str
    updated_at: str
    context_item_ids: tuple[str, ...]


@dataclass(frozen=True)
class ContextAnalysisQueueJob:
    id: str
    source_conversation_id: str | None
    source_record_id: str
    source_fingerprint: str
    analysis_mode: str
    status: str
    attempt_count: int
    last_error_code: str | None
    last_error_summary: str | None
    result_brief_id: str | None
    created_at: str
    updated_at: str
    last_attempt_at: str | None
    completed_at: str | None


class ContextLibraryStore:
    """Persist the linked Context Library in the existing archive database."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        ArchiveStore(db_path)
        self._ensure_schema()

    def save_brief(
        self,
        *,
        conversation_id: str,
        main_subject: str,
        user_goal: str,
        important_outcomes: Sequence[str] = (),
        decisions: Sequence[str] = (),
        lessons: Sequence[str] = (),
        unresolved_questions: Sequence[str] = (),
        actions: Sequence[str] = (),
        analysis_mode: str = "auto",
        analysis_version: str,
        prompt_version: str,
        analysis_provider: str,
        analysis_model: str,
        analysis_status: str = "complete",
        source_fingerprint: str = "",
    ) -> ConversationBrief:
        """Create or update one analysis-versioned brief for an archived conversation."""
        _require_choice("analysis mode", analysis_mode, ANALYSIS_MODES)
        subject = _require_text("main subject", main_subject, 4_000)
        goal = _require_text("user goal", user_goal, 4_000)
        version = _require_text("analysis version", analysis_version, 200)
        prompt = _require_text("prompt version", prompt_version, 200)
        provider = _require_text("analysis provider", analysis_provider, 200)
        model = _require_text("analysis model", analysis_model, 300)
        fingerprint = source_fingerprint.strip()[:128]
        _require_choice("analysis status", analysis_status, BRIEF_ANALYSIS_STATUSES)
        outcome_list = _normalize_text_list(important_outcomes)
        decision_list = _normalize_text_list(decisions)
        lesson_list = _normalize_text_list(lessons)
        question_list = _normalize_text_list(unresolved_questions)
        action_list = _normalize_text_list(actions)
        now = _now()

        with self._connect() as conn:
            source = self._require_conversation(conn, conversation_id)
            existing = conn.execute(
                """
                SELECT id, created_at
                FROM conversation_briefs
                WHERE source_record_id = ? AND analysis_version = ?
                """,
                (source["id"], version),
            ).fetchone()
            brief_id = existing["id"] if existing is not None else uuid4().hex
            created_at = existing["created_at"] if existing is not None else now
            values = (
                source["id"],
                source["id"],
                source["source_id"],
                source["source"],
                source["title"],
                source["created_at"],
                fingerprint,
                subject,
                goal,
                _dump_list(outcome_list),
                _dump_list(decision_list),
                _dump_list(lesson_list),
                _dump_list(question_list),
                _dump_list(action_list),
                analysis_mode,
                version,
                prompt,
                provider,
                model,
                analysis_status,
                created_at,
                now,
            )
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO conversation_briefs (
                        id, source_conversation_id, source_record_id, source_external_id,
                        source_provider, source_title, source_created_at, source_fingerprint,
                        main_subject, user_goal, important_outcomes, decisions, lessons,
                        unresolved_questions, actions, analysis_mode, analysis_version,
                        prompt_version, analysis_provider, analysis_model, analysis_status,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (brief_id, *values),
                )
            else:
                conn.execute(
                    """
                    UPDATE conversation_briefs
                    SET source_conversation_id = ?, source_record_id = ?, source_external_id = ?,
                        source_provider = ?, source_title = ?, source_created_at = ?,
                        source_fingerprint = ?, main_subject = ?, user_goal = ?,
                        important_outcomes = ?, decisions = ?, lessons = ?,
                        unresolved_questions = ?, actions = ?, analysis_mode = ?,
                        analysis_version = ?, prompt_version = ?, analysis_provider = ?,
                        analysis_model = ?, analysis_status = ?, created_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (*values, brief_id),
                )

        brief = self.get_brief(brief_id)
        if brief is None:  # pragma: no cover - guarded by the transaction above.
            raise RuntimeError("The Conversation Brief could not be saved.")
        return brief

    def get_brief(self, brief_id: str) -> ConversationBrief | None:
        """Return one Conversation Brief with its linked Context Item IDs."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM conversation_briefs WHERE id = ?", (brief_id,)
            ).fetchone()
            if row is None:
                return None
            return self._row_to_brief(conn, row)

    def set_brief_analysis_status(self, brief_id: str, analysis_status: str) -> ConversationBrief:
        """Update the durable completion marker for one analysis-versioned Brief."""
        _require_choice("analysis status", analysis_status, BRIEF_ANALYSIS_STATUSES)
        with self._connect() as conn:
            result = conn.execute(
                """
                UPDATE conversation_briefs
                SET analysis_status = ?, updated_at = ?
                WHERE id = ?
                """,
                (analysis_status, _now(), brief_id),
            )
            if result.rowcount == 0:
                raise LookupError("Conversation Brief not found.")
        brief = self.get_brief(brief_id)
        if brief is None:  # pragma: no cover
            raise RuntimeError("The Conversation Brief disappeared while updating status.")
        return brief

    def reset_brief_items(self, brief_id: str) -> None:
        """Remove one Brief's item links and delete items left without any Brief."""
        with self._connect() as conn:
            if (
                conn.execute(
                    "SELECT 1 FROM conversation_briefs WHERE id = ?", (brief_id,)
                ).fetchone()
                is None
            ):
                raise LookupError("Conversation Brief not found.")
            item_ids = [
                row["item_id"]
                for row in conn.execute(
                    "SELECT item_id FROM brief_context_items WHERE brief_id = ?", (brief_id,)
                ).fetchall()
            ]
            conn.execute("DELETE FROM brief_context_items WHERE brief_id = ?", (brief_id,))
            for item_id in item_ids:
                remaining = conn.execute(
                    "SELECT 1 FROM brief_context_items WHERE item_id = ? LIMIT 1", (item_id,)
                ).fetchone()
                if remaining is None:
                    conn.execute("DELETE FROM context_items WHERE id = ?", (item_id,))

    def get_brief_for_analysis(
        self, source_record_id: str, analysis_version: str
    ) -> ConversationBrief | None:
        """Return an existing Brief for an idempotent source/version analysis key."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM conversation_briefs
                WHERE source_record_id = ? AND analysis_version = ?
                """,
                (source_record_id, analysis_version),
            ).fetchone()
            if row is None:
                return None
            return self._row_to_brief(conn, row)

    def list_briefs(self, *, limit: int = 100) -> list[ConversationBrief]:
        """Return Conversation Briefs newest first."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM conversation_briefs ORDER BY updated_at DESC, id LIMIT ?",
                (min(max(limit, 1), 500),),
            ).fetchall()
            return [self._row_to_brief(conn, row) for row in rows]

    def enqueue_analysis(
        self,
        *,
        conversation_id: str,
        source_fingerprint: str,
        analysis_mode: str = "auto",
    ) -> tuple[ContextAnalysisQueueJob, bool]:
        """Persist one pending job for a source version without duplicating unchanged work."""
        _require_choice("analysis mode", analysis_mode, ANALYSIS_MODES)
        fingerprint = _require_text("source fingerprint", source_fingerprint, 128)
        now = _now()
        job_id = uuid4().hex

        with self._connect() as conn:
            source = self._require_conversation(conn, conversation_id)
            existing = conn.execute(
                """
                SELECT * FROM context_analysis_queue
                WHERE source_record_id = ? AND source_fingerprint = ?
                """,
                (source["id"], fingerprint),
            ).fetchone()
            if existing is not None:
                return self._row_to_analysis_queue_job(existing), False

            conn.execute(
                """
                UPDATE context_analysis_queue
                SET status = 'superseded', updated_at = ?, completed_at = ?
                WHERE source_record_id = ?
                  AND source_fingerprint <> ?
                  AND status IN ('pending', 'running', 'failed')
                """,
                (now, now, source["id"], fingerprint),
            )
            conn.execute(
                """
                INSERT INTO context_analysis_queue (
                    id, source_conversation_id, source_record_id, source_fingerprint,
                    analysis_mode, status, attempt_count, last_error_code,
                    last_error_summary, result_brief_id, created_at, updated_at,
                    last_attempt_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, 'pending', 0, NULL, NULL, NULL, ?, ?, NULL, NULL)
                """,
                (job_id, source["id"], source["id"], fingerprint, analysis_mode, now, now),
            )

        job = self.get_analysis_queue_job(job_id)
        if job is None:  # pragma: no cover - guarded by the transaction above.
            raise RuntimeError("The Context analysis queue job could not be saved.")
        return job, True

    def get_analysis_queue_job(self, job_id: str) -> ContextAnalysisQueueJob | None:
        """Return one durable Context analysis queue job."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM context_analysis_queue WHERE id = ?", (job_id,)
            ).fetchone()
            return self._row_to_analysis_queue_job(row) if row is not None else None

    def list_analysis_queue_jobs(
        self,
        *,
        status: str | None = None,
        limit: int = 100,
    ) -> list[ContextAnalysisQueueJob]:
        """Return durable queue jobs newest first, optionally filtered by status."""
        bounded_limit = min(max(limit, 1), 500)
        with self._connect() as conn:
            if status is None:
                rows = conn.execute(
                    """
                    SELECT * FROM context_analysis_queue
                    ORDER BY created_at DESC, id LIMIT ?
                    """,
                    (bounded_limit,),
                ).fetchall()
            else:
                _require_choice("analysis queue status", status, ANALYSIS_QUEUE_STATUSES)
                rows = conn.execute(
                    """
                    SELECT * FROM context_analysis_queue
                    WHERE status = ? ORDER BY created_at DESC, id LIMIT ?
                    """,
                    (status, bounded_limit),
                ).fetchall()
            return [self._row_to_analysis_queue_job(row) for row in rows]

    def start_analysis_queue_job(self, job_id: str) -> ContextAnalysisQueueJob:
        """Move one pending or failed queue job into a new running attempt."""
        now = _now()
        with self._connect() as conn:
            result = conn.execute(
                """
                UPDATE context_analysis_queue
                SET status = 'running', attempt_count = attempt_count + 1,
                    last_error_code = NULL, last_error_summary = NULL,
                    last_attempt_at = ?, completed_at = NULL, updated_at = ?
                WHERE id = ? AND status IN ('pending', 'failed')
                """,
                (now, now, job_id),
            )
            if result.rowcount == 0:
                if conn.execute(
                    "SELECT 1 FROM context_analysis_queue WHERE id = ?", (job_id,)
                ).fetchone() is None:
                    raise LookupError("Context analysis queue job not found.")
                raise ValueError("Context analysis queue job is not retryable.")
        return self._require_analysis_queue_job(job_id)

    def complete_analysis_queue_job(
        self,
        job_id: str,
        *,
        brief_id: str,
    ) -> ContextAnalysisQueueJob:
        """Record the idempotent Brief result for a running queue job."""
        return self._finish_analysis_queue_job(
            job_id,
            status="complete",
            result_brief_id=brief_id,
        )

    def fail_analysis_queue_job(
        self,
        job_id: str,
        *,
        error_code: str,
        error_summary: str,
    ) -> ContextAnalysisQueueJob:
        """Keep a provider failure durable and explicitly retryable."""
        code = _require_text("analysis error code", error_code, 100)
        summary = _require_text("analysis error summary", error_summary, 500)
        return self._finish_analysis_queue_job(
            job_id,
            status="failed",
            error_code=code,
            error_summary=summary,
        )

    def supersede_analysis_queue_job(self, job_id: str) -> ContextAnalysisQueueJob:
        """Mark a stale source-version attempt terminal without analyzing current content."""
        return self._finish_analysis_queue_job(job_id, status="superseded")

    def recover_interrupted_analysis_jobs(self) -> int:
        """Make jobs left running by a previous app process explicitly retryable."""
        interrupted_at = _now()
        with self._connect() as conn:
            result = conn.execute(
                """
                UPDATE context_analysis_queue
                SET status = 'failed', last_error_code = 'interrupted',
                    last_error_summary = 'Analysis was interrupted before completion.',
                    updated_at = ?, completed_at = ?
                WHERE status = 'running'
                """,
                (interrupted_at, interrupted_at),
            )
            return result.rowcount

    def _finish_analysis_queue_job(
        self,
        job_id: str,
        *,
        status: str,
        result_brief_id: str | None = None,
        error_code: str | None = None,
        error_summary: str | None = None,
    ) -> ContextAnalysisQueueJob:
        _require_choice("analysis queue status", status, {"complete", "failed", "superseded"})
        now = _now()
        with self._connect() as conn:
            result = conn.execute(
                """
                UPDATE context_analysis_queue
                SET status = ?, result_brief_id = ?, last_error_code = ?,
                    last_error_summary = ?, completed_at = ?, updated_at = ?
                WHERE id = ? AND status = 'running'
                """,
                (status, result_brief_id, error_code, error_summary, now, now, job_id),
            )
            if result.rowcount == 0:
                if conn.execute(
                    "SELECT 1 FROM context_analysis_queue WHERE id = ?", (job_id,)
                ).fetchone() is None:
                    raise LookupError("Context analysis queue job not found.")
                raise ValueError("Context analysis queue job is not running.")
        return self._require_analysis_queue_job(job_id)

    def create_item(
        self,
        *,
        brief_id: str,
        canonical_text: str,
        item_type: str,
        epistemic_kind: str,
        confidence: float,
        sensitivity: str = "normal",
        status: str = "active",
        scopes: Sequence[ScopeInput],
        evidence: Sequence[EvidenceInput],
        last_confirmed_at: str | None = None,
        stale_at: str | None = None,
        item_id: str | None = None,
    ) -> ContextItem:
        """Create one source-linked Context Item and its initial immutable version."""
        text = _require_text("canonical text", canonical_text, 12_000)
        _require_choice("item type", item_type, CONTEXT_ITEM_TYPES)
        _require_choice("epistemic kind", epistemic_kind, EPISTEMIC_KINDS)
        _require_choice("sensitivity", sensitivity, SENSITIVITIES)
        _require_choice("status", status, CONTEXT_STATUSES)
        score = _require_confidence(confidence)
        normalized_scopes = _normalize_scopes(scopes)
        if not normalized_scopes:
            raise ValueError("Add at least one Context scope.")
        if not evidence:
            raise ValueError("Add at least one source-evidence reference.")
        context_item_id = item_id or uuid4().hex
        now = _now()

        with self._connect() as conn:
            brief = conn.execute(
                "SELECT id FROM conversation_briefs WHERE id = ?", (brief_id,)
            ).fetchone()
            if brief is None:
                raise LookupError("Conversation Brief not found.")
            if conn.execute(
                "SELECT 1 FROM context_items WHERE id = ?", (context_item_id,)
            ).fetchone():
                raise ValueError("Context Item ID already exists.")
            normalized_evidence = [self._normalize_evidence(conn, item) for item in evidence]

            conn.execute(
                """
                INSERT INTO context_items (
                    id, canonical_text, item_type, epistemic_kind, confidence,
                    sensitivity, status, current_version, created_at, updated_at,
                    last_confirmed_at, stale_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
                """,
                (
                    context_item_id,
                    text,
                    item_type,
                    epistemic_kind,
                    score,
                    sensitivity,
                    status,
                    now,
                    now,
                    last_confirmed_at,
                    stale_at,
                ),
            )
            conn.execute(
                """
                INSERT INTO context_item_versions (
                    item_id, version, canonical_text, item_type, epistemic_kind,
                    confidence, sensitivity, status, last_confirmed_at, stale_at,
                    change_reason, created_at
                ) VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, 'initial extraction', ?)
                """,
                (
                    context_item_id,
                    text,
                    item_type,
                    epistemic_kind,
                    score,
                    sensitivity,
                    status,
                    last_confirmed_at,
                    stale_at,
                    now,
                ),
            )
            conn.execute(
                "INSERT INTO brief_context_items (brief_id, item_id, created_at) VALUES (?, ?, ?)",
                (brief_id, context_item_id, now),
            )
            for scope in normalized_scopes:
                conn.execute(
                    """
                    INSERT INTO context_item_scopes (
                        item_id, scope_type, scope_key, confidence, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        context_item_id,
                        scope.scope_type,
                        scope.scope_key,
                        scope.confidence,
                        now,
                    ),
                )
            for source in normalized_evidence:
                conn.execute(
                    """
                    INSERT INTO context_evidence (
                        id, item_id, source_conversation_id, source_message_id,
                        source_record_id, source_external_id, source_message_record_id,
                        source_provider, source_title, source_message_index, source_role,
                        source_timestamp, excerpt, relationship, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        uuid4().hex,
                        context_item_id,
                        source["source_conversation_id"],
                        source["source_message_id"],
                        source["source_record_id"],
                        source["source_external_id"],
                        source["source_message_record_id"],
                        source["source_provider"],
                        source["source_title"],
                        source["source_message_index"],
                        source["source_role"],
                        source["source_timestamp"],
                        source["excerpt"],
                        source["relationship"],
                        now,
                    ),
                )

        item = self.get_item(context_item_id)
        if item is None:  # pragma: no cover - guarded by the transaction above.
            raise RuntimeError("The Context Item could not be created.")
        return item

    def get_item(self, item_id: str) -> ContextItem | None:
        """Return one Context Item with scopes, evidence, versions, and links."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM context_items WHERE id = ?", (item_id,)).fetchone()
            if row is None:
                return None
            return self._row_to_item(conn, row)

    def list_items(self, *, limit: int | None = 200) -> list[ContextItem]:
        """Return current Context Items newest first, or the full library when unbounded."""
        with self._connect() as conn:
            if limit is None:
                rows = conn.execute(
                    "SELECT * FROM context_items ORDER BY updated_at DESC, id"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM context_items ORDER BY updated_at DESC, id LIMIT ?",
                    (min(max(limit, 1), 1_000),),
                ).fetchall()
            return [self._row_to_item(conn, row) for row in rows]

    def revise_item(
        self,
        item_id: str,
        *,
        change_reason: str,
        canonical_text: str | None = None,
        item_type: str | None = None,
        epistemic_kind: str | None = None,
        confidence: float | None = None,
        sensitivity: str | None = None,
        status: str | None = None,
        last_confirmed_at: str | None = None,
        stale_at: str | None = None,
    ) -> ContextItem:
        """Revise a Context Item while preserving an immutable version history."""
        reason = _require_text("change reason", change_reason, 2_000)
        now = _now()
        with self._connect() as conn:
            current = conn.execute(
                "SELECT * FROM context_items WHERE id = ?", (item_id,)
            ).fetchone()
            if current is None:
                raise LookupError("Context Item not found.")
            next_text = (
                current["canonical_text"]
                if canonical_text is None
                else _require_text("canonical text", canonical_text, 12_000)
            )
            next_type = current["item_type"] if item_type is None else item_type
            next_kind = current["epistemic_kind"] if epistemic_kind is None else epistemic_kind
            next_confidence = (
                float(current["confidence"])
                if confidence is None
                else _require_confidence(confidence)
            )
            next_sensitivity = current["sensitivity"] if sensitivity is None else sensitivity
            next_status = current["status"] if status is None else status
            _require_choice("item type", next_type, CONTEXT_ITEM_TYPES)
            _require_choice("epistemic kind", next_kind, EPISTEMIC_KINDS)
            _require_choice("sensitivity", next_sensitivity, SENSITIVITIES)
            _require_choice("status", next_status, CONTEXT_STATUSES)
            next_version = int(current["current_version"]) + 1
            next_confirmed = last_confirmed_at or current["last_confirmed_at"]
            next_stale = stale_at if stale_at is not None else current["stale_at"]

            conn.execute(
                """
                UPDATE context_items
                SET canonical_text = ?, item_type = ?, epistemic_kind = ?, confidence = ?,
                    sensitivity = ?, status = ?, current_version = ?, updated_at = ?,
                    last_confirmed_at = ?, stale_at = ?
                WHERE id = ?
                """,
                (
                    next_text,
                    next_type,
                    next_kind,
                    next_confidence,
                    next_sensitivity,
                    next_status,
                    next_version,
                    now,
                    next_confirmed,
                    next_stale,
                    item_id,
                ),
            )
            conn.execute(
                """
                INSERT INTO context_item_versions (
                    item_id, version, canonical_text, item_type, epistemic_kind,
                    confidence, sensitivity, status, last_confirmed_at, stale_at,
                    change_reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_id,
                    next_version,
                    next_text,
                    next_type,
                    next_kind,
                    next_confidence,
                    next_sensitivity,
                    next_status,
                    next_confirmed,
                    next_stale,
                    reason,
                    now,
                ),
            )

        revised = self.get_item(item_id)
        if revised is None:  # pragma: no cover
            raise RuntimeError("The Context Item disappeared while revising it.")
        return revised

    def link_items(self, source_item_id: str, target_item_id: str, relationship: str) -> None:
        """Create or update a directed relationship between two Context Items."""
        if source_item_id == target_item_id:
            raise ValueError("A Context Item cannot link to itself.")
        relation = _require_text("relationship", relationship, 200)
        now = _now()
        with self._connect() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM context_items WHERE id IN (?, ?)",
                (source_item_id, target_item_id),
            ).fetchone()[0]
            if count != 2:
                raise LookupError("Both Context Items must exist before linking them.")
            conn.execute(
                """
                INSERT INTO context_item_links (
                    source_item_id, target_item_id, relationship, created_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(source_item_id, target_item_id)
                DO UPDATE SET relationship = excluded.relationship
                """,
                (source_item_id, target_item_id, relation, now),
            )

    def _row_to_brief(self, conn: sqlite3.Connection, row: sqlite3.Row) -> ConversationBrief:
        item_ids = tuple(
            item["item_id"]
            for item in conn.execute(
                """
                SELECT item_id FROM brief_context_items
                WHERE brief_id = ? ORDER BY created_at, item_id
                """,
                (row["id"],),
            ).fetchall()
        )
        return ConversationBrief(
            id=row["id"],
            source_conversation_id=row["source_conversation_id"],
            source_record_id=row["source_record_id"],
            source_external_id=row["source_external_id"],
            source_provider=row["source_provider"],
            source_title=row["source_title"],
            source_created_at=row["source_created_at"],
            source_fingerprint=row["source_fingerprint"],
            main_subject=row["main_subject"],
            user_goal=row["user_goal"],
            important_outcomes=_load_list(row["important_outcomes"]),
            decisions=_load_list(row["decisions"]),
            lessons=_load_list(row["lessons"]),
            unresolved_questions=_load_list(row["unresolved_questions"]),
            actions=_load_list(row["actions"]),
            analysis_mode=row["analysis_mode"],
            analysis_version=row["analysis_version"],
            prompt_version=row["prompt_version"],
            analysis_provider=row["analysis_provider"],
            analysis_model=row["analysis_model"],
            analysis_status=row["analysis_status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            context_item_ids=item_ids,
        )

    @staticmethod
    def _row_to_analysis_queue_job(row: sqlite3.Row) -> ContextAnalysisQueueJob:
        return ContextAnalysisQueueJob(
            id=row["id"],
            source_conversation_id=row["source_conversation_id"],
            source_record_id=row["source_record_id"],
            source_fingerprint=row["source_fingerprint"],
            analysis_mode=row["analysis_mode"],
            status=row["status"],
            attempt_count=int(row["attempt_count"]),
            last_error_code=row["last_error_code"],
            last_error_summary=row["last_error_summary"],
            result_brief_id=row["result_brief_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_attempt_at=row["last_attempt_at"],
            completed_at=row["completed_at"],
        )

    def _require_analysis_queue_job(self, job_id: str) -> ContextAnalysisQueueJob:
        job = self.get_analysis_queue_job(job_id)
        if job is None:  # pragma: no cover - guarded by the preceding update.
            raise RuntimeError("The Context analysis queue job disappeared while updating it.")
        return job

    def _row_to_item(self, conn: sqlite3.Connection, row: sqlite3.Row) -> ContextItem:
        scopes = tuple(
            ContextScope(
                item_id=item["item_id"],
                scope_type=item["scope_type"],
                scope_key=item["scope_key"],
                confidence=float(item["confidence"]),
                created_at=item["created_at"],
            )
            for item in conn.execute(
                """
                SELECT * FROM context_item_scopes
                WHERE item_id = ? ORDER BY scope_type, scope_key
                """,
                (row["id"],),
            ).fetchall()
        )
        evidence = tuple(
            ContextEvidence(
                id=item["id"],
                item_id=item["item_id"],
                source_conversation_id=item["source_conversation_id"],
                source_message_id=item["source_message_id"],
                source_record_id=item["source_record_id"],
                source_external_id=item["source_external_id"],
                source_message_record_id=item["source_message_record_id"],
                source_provider=item["source_provider"],
                source_title=item["source_title"],
                source_message_index=int(item["source_message_index"]),
                source_role=item["source_role"],
                source_timestamp=item["source_timestamp"],
                excerpt=item["excerpt"],
                relationship=item["relationship"],
                created_at=item["created_at"],
            )
            for item in conn.execute(
                "SELECT * FROM context_evidence WHERE item_id = ? ORDER BY created_at, id",
                (row["id"],),
            ).fetchall()
        )
        versions = tuple(
            ContextItemVersion(
                item_id=item["item_id"],
                version=int(item["version"]),
                canonical_text=item["canonical_text"],
                item_type=item["item_type"],
                epistemic_kind=item["epistemic_kind"],
                confidence=float(item["confidence"]),
                sensitivity=item["sensitivity"],
                status=item["status"],
                last_confirmed_at=item["last_confirmed_at"],
                stale_at=item["stale_at"],
                change_reason=item["change_reason"],
                created_at=item["created_at"],
            )
            for item in conn.execute(
                """
                SELECT * FROM context_item_versions
                WHERE item_id = ? ORDER BY version
                """,
                (row["id"],),
            ).fetchall()
        )
        links = tuple(
            ContextItemLink(
                source_item_id=item["source_item_id"],
                target_item_id=item["target_item_id"],
                relationship=item["relationship"],
                created_at=item["created_at"],
            )
            for item in conn.execute(
                """
                SELECT * FROM context_item_links
                WHERE source_item_id = ? OR target_item_id = ?
                ORDER BY created_at, source_item_id, target_item_id
                """,
                (row["id"], row["id"]),
            ).fetchall()
        )
        return ContextItem(
            id=row["id"],
            canonical_text=row["canonical_text"],
            item_type=row["item_type"],
            epistemic_kind=row["epistemic_kind"],
            confidence=float(row["confidence"]),
            sensitivity=row["sensitivity"],
            status=row["status"],
            current_version=int(row["current_version"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_confirmed_at=row["last_confirmed_at"],
            stale_at=row["stale_at"],
            scopes=scopes,
            evidence=evidence,
            versions=versions,
            links=links,
        )

    @staticmethod
    def _require_conversation(conn: sqlite3.Connection, conversation_id: str) -> sqlite3.Row:
        row = conn.execute(
            """
            SELECT id, source_id, source, title, created_at
            FROM conversations WHERE id = ?
            """,
            (conversation_id,),
        ).fetchone()
        if row is None:
            raise LookupError("Archived conversation not found.")
        return row

    def _normalize_evidence(
        self, conn: sqlite3.Connection, evidence: EvidenceInput
    ) -> dict[str, object]:
        _require_choice("evidence relationship", evidence.relationship, EVIDENCE_RELATIONSHIPS)
        row = conn.execute(
            """
            SELECT c.id AS conversation_id, c.source_id AS external_id, c.source,
                   c.title, m.id AS message_id, m.message_index, m.role,
                   m.timestamp, m.content
            FROM conversations c
            JOIN messages m ON m.conversation_id = c.id
            WHERE c.id = ? AND m.id = ?
            """,
            (evidence.conversation_id, evidence.message_id),
        ).fetchone()
        if row is None:
            raise LookupError("Source evidence must reference an archived message.")
        source_content = row["content"].strip()
        requested_excerpt = evidence.excerpt.strip()
        if requested_excerpt and requested_excerpt not in source_content:
            raise ValueError("Source evidence excerpt must appear in the archived message.")
        excerpt = requested_excerpt or source_content
        if not excerpt:
            raise ValueError("Source evidence must include a non-empty excerpt.")
        return {
            "source_conversation_id": row["conversation_id"],
            "source_message_id": row["message_id"],
            "source_record_id": row["conversation_id"],
            "source_external_id": row["external_id"],
            "source_message_record_id": row["message_id"],
            "source_provider": row["source"],
            "source_title": row["title"],
            "source_message_index": int(row["message_index"]),
            "source_role": row["role"],
            "source_timestamp": row["timestamp"],
            "excerpt": excerpt[:4_000],
            "relationship": evidence.relationship,
        }

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversation_briefs (
                    id TEXT PRIMARY KEY,
                    source_conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
                    source_record_id TEXT NOT NULL,
                    source_external_id TEXT,
                    source_provider TEXT NOT NULL,
                    source_title TEXT NOT NULL,
                    source_created_at TEXT NOT NULL,
                    source_fingerprint TEXT NOT NULL DEFAULT '',
                    main_subject TEXT NOT NULL,
                    user_goal TEXT NOT NULL,
                    important_outcomes TEXT NOT NULL DEFAULT '[]',
                    decisions TEXT NOT NULL DEFAULT '[]',
                    lessons TEXT NOT NULL DEFAULT '[]',
                    unresolved_questions TEXT NOT NULL DEFAULT '[]',
                    actions TEXT NOT NULL DEFAULT '[]',
                    analysis_mode TEXT NOT NULL,
                    analysis_version TEXT NOT NULL,
                    prompt_version TEXT NOT NULL,
                    analysis_provider TEXT NOT NULL,
                    analysis_model TEXT NOT NULL,
                    analysis_status TEXT NOT NULL DEFAULT 'complete',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(source_record_id, analysis_version)
                );

                CREATE TABLE IF NOT EXISTS context_items (
                    id TEXT PRIMARY KEY,
                    canonical_text TEXT NOT NULL,
                    item_type TEXT NOT NULL,
                    epistemic_kind TEXT NOT NULL,
                    confidence REAL NOT NULL CHECK(confidence >= 0 AND confidence <= 1),
                    sensitivity TEXT NOT NULL,
                    status TEXT NOT NULL,
                    current_version INTEGER NOT NULL CHECK(current_version >= 1),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_confirmed_at TEXT,
                    stale_at TEXT
                );

                CREATE TABLE IF NOT EXISTS context_item_versions (
                    item_id TEXT NOT NULL REFERENCES context_items(id) ON DELETE CASCADE,
                    version INTEGER NOT NULL,
                    canonical_text TEXT NOT NULL,
                    item_type TEXT NOT NULL,
                    epistemic_kind TEXT NOT NULL,
                    confidence REAL NOT NULL CHECK(confidence >= 0 AND confidence <= 1),
                    sensitivity TEXT NOT NULL,
                    status TEXT NOT NULL,
                    last_confirmed_at TEXT,
                    stale_at TEXT,
                    change_reason TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(item_id, version)
                );

                CREATE TABLE IF NOT EXISTS brief_context_items (
                    brief_id TEXT NOT NULL REFERENCES conversation_briefs(id) ON DELETE CASCADE,
                    item_id TEXT NOT NULL REFERENCES context_items(id) ON DELETE CASCADE,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(brief_id, item_id)
                );

                CREATE TABLE IF NOT EXISTS context_item_scopes (
                    item_id TEXT NOT NULL REFERENCES context_items(id) ON DELETE CASCADE,
                    scope_type TEXT NOT NULL,
                    scope_key TEXT NOT NULL DEFAULT '',
                    confidence REAL NOT NULL CHECK(confidence >= 0 AND confidence <= 1),
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(item_id, scope_type, scope_key)
                );

                CREATE TABLE IF NOT EXISTS context_evidence (
                    id TEXT PRIMARY KEY,
                    item_id TEXT NOT NULL REFERENCES context_items(id) ON DELETE CASCADE,
                    source_conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
                    source_message_id TEXT REFERENCES messages(id) ON DELETE SET NULL,
                    source_record_id TEXT NOT NULL,
                    source_external_id TEXT,
                    source_message_record_id TEXT NOT NULL,
                    source_provider TEXT NOT NULL,
                    source_title TEXT NOT NULL,
                    source_message_index INTEGER NOT NULL,
                    source_role TEXT NOT NULL,
                    source_timestamp TEXT,
                    excerpt TEXT NOT NULL,
                    relationship TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(item_id, source_message_record_id, relationship)
                );

                CREATE TABLE IF NOT EXISTS context_item_links (
                    source_item_id TEXT NOT NULL REFERENCES context_items(id) ON DELETE CASCADE,
                    target_item_id TEXT NOT NULL REFERENCES context_items(id) ON DELETE CASCADE,
                    relationship TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(source_item_id, target_item_id),
                    CHECK(source_item_id <> target_item_id)
                );

                CREATE TABLE IF NOT EXISTS context_analysis_queue (
                    id TEXT PRIMARY KEY,
                    source_conversation_id TEXT REFERENCES conversations(id) ON DELETE CASCADE,
                    source_record_id TEXT NOT NULL,
                    source_fingerprint TEXT NOT NULL,
                    analysis_mode TEXT NOT NULL CHECK(
                        analysis_mode IN (
                            'auto', 'project', 'learning', 'research_writing', 'context_handoff'
                        )
                    ),
                    status TEXT NOT NULL CHECK(
                        status IN ('pending', 'running', 'failed', 'complete', 'superseded')
                    ),
                    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count >= 0),
                    last_error_code TEXT,
                    last_error_summary TEXT,
                    result_brief_id TEXT REFERENCES conversation_briefs(id) ON DELETE SET NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_attempt_at TEXT,
                    completed_at TEXT,
                    UNIQUE(source_record_id, source_fingerprint)
                );

                CREATE INDEX IF NOT EXISTS idx_briefs_source
                    ON conversation_briefs(source_conversation_id, updated_at);
                CREATE INDEX IF NOT EXISTS idx_context_items_updated
                    ON context_items(updated_at);
                CREATE INDEX IF NOT EXISTS idx_context_scopes_route
                    ON context_item_scopes(scope_type, scope_key, item_id);
                CREATE INDEX IF NOT EXISTS idx_context_evidence_source
                    ON context_evidence(source_conversation_id, source_message_id);
                CREATE INDEX IF NOT EXISTS idx_context_analysis_queue_status
                    ON context_analysis_queue(status, created_at);
                CREATE INDEX IF NOT EXISTS idx_context_analysis_queue_source
                    ON context_analysis_queue(source_record_id, created_at);
                INSERT OR REPLACE INTO schema_meta(key, value)
                    VALUES ('context_schema_version', '4');
                """
            )
            self._ensure_column(
                conn,
                "conversation_briefs",
                "analysis_status",
                "TEXT NOT NULL DEFAULT 'complete'",
            )
            self._ensure_column(
                conn,
                "conversation_briefs",
                "source_fingerprint",
                "TEXT NOT NULL DEFAULT ''",
            )

    @staticmethod
    def _ensure_column(
        conn: sqlite3.Connection,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn


def _normalize_scopes(scopes: Sequence[ScopeInput]) -> tuple[ScopeInput, ...]:
    normalized: dict[tuple[str, str], ScopeInput] = {}
    for scope in scopes:
        _require_choice("scope type", scope.scope_type, SCOPE_TYPES)
        scope_key = scope.scope_key.strip()[:500]
        if scope.scope_type in {"project", "topic", "destination"} and not scope_key:
            raise ValueError(f"{scope.scope_type} scope requires a scope key.")
        if scope.scope_type in {"core_self", "personal", "work"}:
            scope_key = ""
        normalized[(scope.scope_type, scope_key)] = ScopeInput(
            scope_type=scope.scope_type,
            scope_key=scope_key,
            confidence=_require_confidence(scope.confidence),
        )
    return tuple(normalized.values())


def _normalize_text_list(values: Sequence[str]) -> tuple[str, ...]:
    normalized = []
    for value in values:
        text = str(value).strip()
        if text and text not in normalized:
            normalized.append(text[:4_000])
    return tuple(normalized[:100])


def _require_text(label: str, value: str, limit: int) -> str:
    text = value.strip()
    if not text:
        raise ValueError(f"{label.capitalize()} is required.")
    return text[:limit]


def _require_choice(label: str, value: str, choices: set[str]) -> None:
    if value not in choices:
        raise ValueError(f"Unsupported {label}: {value}")


def _require_confidence(value: float) -> float:
    score = float(value)
    if not 0.0 <= score <= 1.0:
        raise ValueError("Confidence must be between 0 and 1.")
    return score


def _dump_list(values: Sequence[str]) -> str:
    return json.dumps(list(values), ensure_ascii=False)


def _load_list(value: str) -> tuple[str, ...]:
    try:
        loaded = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return ()
    if not isinstance(loaded, list):
        return ()
    return tuple(str(item) for item in loaded if str(item).strip())


def _now() -> str:
    return datetime.now(tz=UTC).isoformat()
