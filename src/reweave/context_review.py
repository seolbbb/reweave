"""Version-bound exception review and explicit derived-library deletion.

Review acknowledgments are local editorial history, never destination consent.
Link resolutions preserve both records and are invalidated by either revision.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from reweave.context_library import ContextItem, ContextLibraryStore, ContextRevisionConflictError
from reweave.maintenance import MaintenanceBusyError, MaintenanceGate


def _time(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed
    except (AttributeError, TypeError, ValueError):
        return None


def effective_confidence(item: ContextItem, *, now: datetime | None = None) -> float:
    """Apply a 180-day half-life at read time; historical confidence stays intact."""
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    recorded = _time(item.last_confirmed_at or item.updated_at or item.created_at)
    if recorded is None:
        return 0.0
    age_days = max(0.0, (now - recorded).total_seconds() / 86400)
    value = item.confidence * 0.5 ** (age_days / 180)
    stale = _time(item.stale_at)
    if stale and stale <= now and stale >= recorded:
        value *= 0.5
    return round(max(0.0, min(1.0, value)), 4)


def _key(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


class ContextReviewStore:
    def __init__(self, library: ContextLibraryStore):
        self.library = library
        with library._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS context_review_events (
                    id TEXT PRIMARY KEY,
                    item_id TEXT NOT NULL REFERENCES context_items(id) ON DELETE CASCADE,
                    item_version INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    review_key TEXT NOT NULL,
                    reasons_json TEXT NOT NULL,
                    previous_version INTEGER,
                    related_item_id TEXT REFERENCES context_items(id) ON DELETE CASCADE,
                    related_version INTEGER,
                    resolution TEXT,
                    created_at TEXT NOT NULL,
                    undone_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_context_review_item
                    ON context_review_events(item_id, item_version, created_at);
                CREATE INDEX IF NOT EXISTS idx_context_review_resolution
                    ON context_review_events(review_key, action, undone_at, created_at DESC);
            """)

    def history(self, item_id):
        with self.library._connect() as conn:
            return [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM context_review_events WHERE item_id = ? "
                    "OR related_item_id = ? ORDER BY created_at DESC, id DESC",
                    (item_id, item_id),
                )
            ]

    @staticmethod
    def _link_key(item, other, relationship):
        return _key(
            [
                sorted([(item.id, item.current_version), (other.id, other.current_version)]),
                relationship,
            ]
        )

    def link_resolution(self, item, other, relationship):
        """Return an explicit current-version resolution, or None; never infer a merge."""
        with self.library._connect() as conn:
            row = conn.execute(
                "SELECT * FROM context_review_events WHERE action = 'resolve_link' "
                "AND review_key = ? AND undone_at IS NULL ORDER BY created_at DESC LIMIT 1",
                (self._link_key(item, other, relationship),),
            ).fetchone()
        return dict(row) if row else None

    def inspect(self, item: ContextItem, *, now=None):
        reasons, related = [], []

        def add(code, label, detail):
            if not any(reason["code"] == code for reason in reasons):
                reasons.append({"code": code, "label": label, "detail": detail})

        confidence = effective_confidence(item, now=now)
        if item.status in {"active", "stale"}:
            scopes = {scope.scope_type for scope in item.scopes}
            if item.sensitivity == "sensitive" and item.epistemic_kind != "observed":
                add(
                    "sensitive_inference",
                    "Sensitive inference",
                    "This sensitive item is inferred or suggested rather than directly observed.",
                )
            if ("personal" in scopes and scopes & {"work", "project", "destination"}) or (
                item.sensitivity == "sensitive" and "core_self" in scopes
            ):
                add(
                    "cross_scope",
                    "Scope boundary",
                    "This item crosses personal and work or destination scopes. "
                    "Check its scope labels.",
                )
            if (
                item.item_type in {"preference", "value"} or "core_self" in scopes
            ) and confidence < 0.75:
                add(
                    "low_confidence",
                    "Uncertain personalization",
                    "The recorded confidence, adjusted for time since confirmation, is below 75%.",
                )
            if not item.evidence or any(
                not ev.excerpt.strip() or not ev.source_record_id for ev in item.evidence
            ):
                add(
                    "ambiguous_evidence",
                    "Incomplete evidence",
                    "A compact source excerpt or its provenance is missing. "
                    "Check the evidence before relying on it.",
                )
            with self.library._connect() as conn:
                failed = conn.execute(
                    "SELECT 1 FROM brief_context_items bi "
                    "JOIN conversation_briefs b ON b.id = bi.brief_id "
                    "WHERE bi.item_id = ? AND b.analysis_status = 'failed' LIMIT 1",
                    (item.id,),
                ).fetchone()
            if failed:
                add(
                    "failed_evidence",
                    "Failed source analysis",
                    "An analysis attached to this item failed. Check its retained evidence "
                    "and retry the source analysis if needed.",
                )
            if any(ev.source_changed for ev in item.evidence):
                add(
                    "source_changed",
                    "Source changed",
                    "A retained source message changed after this item was recorded. "
                    "Its saved excerpt is preserved.",
                )
            for link in item.links:
                other_id = (
                    link.target_item_id if link.source_item_id == item.id else link.source_item_id
                )
                other = self.library.get_item(other_id)
                if not other or other.status == "archived":
                    continue
                relationship = link.relationship.casefold()
                conflict = relationship in {
                    "contradicts",
                    "contradiction",
                    "conflicts_with",
                    "conflict",
                    "possible_contradiction",
                }
                ambiguous = relationship in {"possible_duplicate", "possible_expansion"}
                changed = (
                    relationship == "source_update"
                    and (item.item_type == "decision" or other.item_type == "decision")
                    and item.canonical_text != other.canonical_text
                )
                if (conflict or changed or ambiguous) and not self.link_resolution(
                    item, other, link.relationship
                ):
                    add(
                        "contradiction"
                        if conflict
                        else "ambiguous_link"
                        if ambiguous
                        else "changed_decision",
                        "Unresolved contradiction"
                        if conflict
                        else "Uncertain relationship"
                        if ambiguous
                        else "Changed decision",
                        "These records may repeat, expand, or disagree with one another. "
                        "Inspect both before keeping both or choosing the preferred record. "
                        "Both records and their history remain available.",
                    )
                    related.append(
                        {
                            "id": other.id,
                            "version": other.current_version,
                            "canonical_text": other.canonical_text,
                            "relationship": link.relationship,
                        }
                    )
        signature = _key(
            [
                item.id,
                item.current_version,
                sorted(r["code"] for r in reasons),
                sorted((r["id"], r["version"], r["relationship"]) for r in related),
                sorted(ev.id for ev in item.evidence if ev.source_changed),
            ]
        )
        history = self.history(item.id)
        handled = any(
            event["action"] in {"dismiss", "confirm"}
            and event["item_id"] == item.id
            and event["item_version"] == item.current_version
            and event["review_key"] == signature
            and not event["undone_at"]
            for event in history
        )
        return {
            "item": item,
            "reasons": reasons,
            "related_items": related,
            "effective_confidence": confidence,
            "review_key": signature,
            "state": "handled" if handled or not reasons else "open",
            "history": history,
        }

    def list_review(self, *, state="open", reason=None, limit=100, offset=0):
        rows = [self.inspect(item) for item in self.library.list_items(limit=None)]
        exceptions = [row for row in rows if row["reasons"] or row["history"]]
        counts = Counter(
            reason["code"]
            for row in exceptions
            if row["state"] == "open"
            for reason in row["reasons"]
        )
        filtered = [
            row
            for row in exceptions
            if row["state"] == state
            and (not reason or any(r["code"] == reason for r in row["reasons"]))
        ]
        return {
            "results": filtered[offset : offset + limit],
            "total": len(filtered),
            "open_count": sum(row["state"] == "open" for row in exceptions),
            "reason_counts": dict(counts),
        }

    def _checked(self, item_id, expected_version, review_key):
        item = self.library.get_item(item_id)
        if item is None:
            raise LookupError("Context item not found.")
        row = self.inspect(item)
        if item.current_version != expected_version or row["review_key"] != review_key:
            raise ContextRevisionConflictError(
                "This item or its evidence changed. Refresh Review before acting."
            )
        if not row["reasons"]:
            raise ValueError("This item has no exception to review.")
        return row

    def _record(
        self, conn, row, action, *, previous_version=None, related=None, resolution=None, key=None
    ):
        event_id = str(uuid4())
        conn.execute(
            "INSERT INTO context_review_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
            (
                event_id,
                row["item"].id,
                row["item"].current_version,
                action,
                key or row["review_key"],
                json.dumps(row["reasons"]),
                previous_version,
                related.id if related else None,
                related.current_version if related else None,
                resolution,
                datetime.now(UTC).isoformat(),
            ),
        )
        return event_id

    def dismiss(self, item_id, *, expected_version, review_key):
        with self.library.transaction(), self.library._connect() as conn:
            row = self._checked(item_id, expected_version, review_key)
            self._record(conn, row, "dismiss")
            return self.inspect(row["item"])

    def confirm(self, item_id, *, expected_version, review_key):
        with self.library.transaction(), self.library._connect() as conn:
            row = self._checked(item_id, expected_version, review_key)
            item = self.library.revise_item(
                item_id,
                expected_version=expected_version,
                confidence=1.0,
                last_confirmed_at=datetime.now(UTC).isoformat(),
                authority="user",
                status="active" if row["item"].status == "stale" else row["item"].status,
                change_reason="Accuracy confirmed in Review; external-use permissions unchanged.",
            )
            updated = self.inspect(item)
            # Accuracy confirmation cannot settle a disagreement between two records.
            action = "confirm_accuracy" if updated["related_items"] else "confirm"
            self._record(conn, updated, action, previous_version=expected_version)
            return self.inspect(item)

    def resolve_link(
        self,
        item_id,
        *,
        expected_version,
        review_key,
        related_item_id,
        related_version,
        relationship,
        resolution,
    ):
        if resolution not in {"keep_both", "prefer_this", "prefer_other"}:
            raise ValueError("Choose an explicit link resolution.")
        with self.library.transaction(), self.library._connect() as conn:
            row = self._checked(item_id, expected_version, review_key)
            other = self.library.get_item(related_item_id)
            if not other or other.current_version != related_version:
                raise ContextRevisionConflictError(
                    "The linked item changed. Refresh Review before resolving it."
                )
            if not any(
                r["id"] == other.id and r["relationship"] == relationship
                for r in row["related_items"]
            ):
                raise ValueError("This unresolved relationship is not available for review.")
            self._record(
                conn,
                row,
                "resolve_link",
                related=other,
                resolution=resolution,
                key=self._link_key(row["item"], other, relationship),
            )
            return self.inspect(row["item"])

    def undo_event(self, event_id, *, expected_version):
        with self.library.transaction(), self.library._connect() as conn:
            event = conn.execute(
                "SELECT * FROM context_review_events WHERE id = ?", (event_id,)
            ).fetchone()
            if not event:
                raise LookupError("Review event not found.")
            item = self.library.get_item(event["item_id"])
            if event["undone_at"] or item.current_version != expected_version:
                raise ContextRevisionConflictError(
                    "The item or review event changed. Refresh before undoing."
                )
            if event["action"] in {"confirm", "confirm_accuracy"}:
                if item.current_version != event["item_version"]:
                    raise ContextRevisionConflictError(
                        "A later correction exists. Use the item history to restore it explicitly."
                    )
                item = self.library.undo_item(
                    item.id, version=event["previous_version"], expected_version=expected_version
                )
            conn.execute(
                "UPDATE context_review_events SET undone_at = ? WHERE id = ?",
                (datetime.now(UTC).isoformat(), event_id),
            )
            return self.inspect(item)

    def delete_library(self, *, confirmation):
        if confirmation != "DELETE LIBRARY":
            raise ValueError("Type DELETE LIBRARY exactly to delete derived context.")
        tables = {
            "items": "context_items",
            "evidence": "context_evidence",
            "versions": "context_item_versions",
            "briefs": "conversation_briefs",
            "spaces": "context_spaces",
            "review_events": "context_review_events",
            "queued_analyses": "context_analysis_queue",
        }
        with self.library.transaction(), self.library._connect() as conn:
            conn.execute("PRAGMA secure_delete = ON")
            counts = {
                name: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for name, table in tables.items()
            }
            if conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'context_chunk_runs'"
            ).fetchone():
                counts["analysis_checkpoints"] = conn.execute(
                    "SELECT COUNT(*) FROM context_chunk_checkpoints"
                ).fetchone()[0]
                conn.execute("DELETE FROM context_chunk_checkpoints")
                conn.execute("DELETE FROM context_chunk_runs")
            for table in (
                "context_analysis_queue",
                "context_review_events",
                "context_items",
                "conversation_briefs",
                "context_space_events",
                "context_space_aliases",
            ):
                conn.execute(f"DELETE FROM {table}")
            conn.execute("UPDATE context_spaces SET merged_into = NULL")
            conn.execute("DELETE FROM context_spaces")
            remaining = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
        return {
            "deleted": counts,
            "retained_sources": remaining,
            "notice": "Derived Library deleted. Raw sources, provider credentials, "
            "destination preferences, and usage records remain.",
        }


class ReviewAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    review_key: str = Field(min_length=64, max_length=64)


class LinkResolution(ReviewAction):
    related_item_id: str = Field(min_length=1, max_length=128)
    related_version: int = Field(ge=1)
    relationship: str = Field(min_length=1, max_length=200)
    resolution: Literal["keep_both", "prefer_this", "prefer_other"]


class ReviewUndo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)


class LibraryDelete(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation: str = Field(max_length=100)


def review_router(
    store: ContextReviewStore,
    *,
    gate: MaintenanceGate,
    serialize_item: Callable = asdict,
    on_library_deleted: Callable | None = None,
):
    """Exclude DELETE /api/context/library from the ordinary middleware lease."""
    router = APIRouter(prefix="/api/context")

    def serialize(row):
        return {**row, "item": serialize_item(row["item"])}

    def mutate(operation):
        try:
            return operation()
        except (ContextRevisionConflictError, MaintenanceBusyError) as exc:
            raise HTTPException(409, str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.get("/review")
    def list_review(
        state: Literal["open", "handled"] = "open",
        reason: str | None = None,
        limit: int = Query(100, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ):
        result = store.list_review(state=state, reason=reason, limit=limit, offset=offset)
        return {**result, "results": [serialize(row) for row in result["results"]]}

    @router.post("/review/items/{item_id}/dismiss")
    def dismiss(item_id: str, request: ReviewAction):
        return mutate(lambda: serialize(store.dismiss(item_id, **request.model_dump())))

    @router.post("/review/items/{item_id}/confirm")
    def confirm(item_id: str, request: ReviewAction):
        return mutate(lambda: serialize(store.confirm(item_id, **request.model_dump())))

    @router.post("/review/items/{item_id}/resolve")
    def resolve(item_id: str, request: LinkResolution):
        return mutate(lambda: serialize(store.resolve_link(item_id, **request.model_dump())))

    @router.post("/review/events/{event_id}/undo")
    def undo(event_id: str, request: ReviewUndo):
        return mutate(lambda: serialize(store.undo_event(event_id, **request.model_dump())))

    @router.delete("/library")
    def delete_library(request: LibraryDelete):
        def perform():
            with gate.exclusive():
                result = store.delete_library(confirmation=request.confirmation)
                result["restart_required"] = False
                if on_library_deleted:
                    try:
                        on_library_deleted()
                    except Exception:
                        gate.block_until_restart(
                            "Library deletion completed. Restart Reweave before continuing."
                        )
                        result["restart_required"] = True
                        result["notice"] = (
                            "Library deletion completed. Restart Reweave before continuing."
                        )
                return result

        return mutate(perform)

    return router
