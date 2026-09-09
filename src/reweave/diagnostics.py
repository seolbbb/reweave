"""Allowlisted local support metadata without source text, identities, or secrets."""

from __future__ import annotations

import json
import platform
import sqlite3
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version

from fastapi import APIRouter
from fastapi.responses import Response


def diagnostics_router(context_store, policy_store, profile_store):
    router = APIRouter(prefix="/api/diagnostics")

    def report():
        try:
            app_version = version("reweave")
        except PackageNotFoundError:
            app_version = "unavailable"
        with context_store._connect() as conn:
            counts = {}
            for table in (
                "conversations",
                "messages",
                "context_items",
                "conversation_briefs",
                "context_spaces",
                "context_evidence",
            ):
                counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            queue = {
                row[0]: row[1]
                for row in conn.execute(
                    "SELECT status, COUNT(*) FROM context_analysis_queue GROUP BY status"
                )
                if row[0] in {"pending", "running", "complete", "failed", "superseded"}
            }
            schema = conn.execute(
                "SELECT value FROM schema_meta WHERE key = 'context_schema_version'"
            ).fetchone()
        policy = policy_store.get()
        profiles = profile_store.list()
        return {
            "format_version": 1,
            "created_at": datetime.now(UTC).isoformat(),
            "application_version": app_version,
            "platform": platform.system(),
            "python_version": platform.python_version(),
            "sqlite_version": sqlite3.sqlite_version,
            "context_schema_version": int(schema[0])
            if schema and str(schema[0]).isdigit()
            else None,
            "counts": counts,
            "analysis_queue": queue,
            "analysis_enabled": policy.enabled,
            "daily_attempt_limit": policy.daily_attempt_limit,
            "daily_token_limit": policy.daily_token_limit,
            "profile_count": len(profiles.profiles),
            "has_active_profile": profiles.active_profile_id is not None,
            "privacy": "Allowlisted counts and runtime versions only. "
            "No source text, Context text, source or profile names, identifiers, paths, "
            "provider addresses, prompts, or credentials.",
        }

    @router.get("")
    def preview():
        return report()

    @router.get("/export")
    def export():
        return Response(
            json.dumps(report(), indent=2),
            media_type="application/json",
            headers={
                "Content-Disposition": 'attachment; filename="reweave-diagnostics.json"',
                "Cache-Control": "no-store",
            },
        )

    return router
