"""Explicit destination choices and bounded, one-use sensitive Context consent.

Only destination metadata is persisted. Current chat, drafts, preview text and
consent tokens remain in memory and disappear when the app closes or restores.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from threading import RLock

from reweave.context_assembly import (
    AllowedScope,
    ContextAssemblyInput,
    ContextUnavailableError,
    CurrentChatMessage,
    _validate_request,
    assemble_context,
)
from reweave.context_library import ContextLibraryStore, ContextRevisionConflictError
from reweave.context_retrieval import DESTINATION_SCOPE_TYPES, ContextRetriever

CONSENT_TTL_SECONDS = 120
MAX_PREVIEW_ITEMS = 5
MAX_EPHEMERAL_RECORDS = 128


def canonical_identity(provider: str, external_id: str) -> tuple[str, str]:
    """Keep provider namespaces separate and normalize only UUID letter casing."""
    if (
        not isinstance(provider, str)
        or provider not in {"chatgpt", "claude"}
        or not isinstance(external_id, str)
    ):
        raise ValueError("Unsupported conversation identity.")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", external_id):
        raise ValueError("Unsupported conversation identity.")
    if provider == "claude":
        if not re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", external_id):
            raise ValueError("Claude conversation identity must be a UUID.")
        external_id = external_id.lower()
    return provider, external_id


def _digest(value) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class ContextTrustStore:
    """Additive SQLite metadata; revisions also make scope corrections auditable."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS context_destination_preferences (
                    provider TEXT NOT NULL CHECK(provider IN ('chatgpt', 'claude')),
                    external_id TEXT NOT NULL,
                    destination TEXT NOT NULL
                        CHECK(destination IN ('private','work','client','shared')),
                    scope_bindings_json TEXT NOT NULL,
                    revision INTEGER NOT NULL CHECK(revision >= 1),
                    updated_at REAL NOT NULL,
                    PRIMARY KEY(provider, external_id)
                );
                CREATE TABLE IF NOT EXISTS context_destination_events (
                    provider TEXT NOT NULL,
                    external_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    destination TEXT NOT NULL,
                    scope_bindings_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY(provider, external_id, revision)
                );
                """
            )

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def get(self, provider: str, external_id: str) -> dict | None:
        identity = canonical_identity(provider, external_id)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM context_destination_preferences WHERE provider=? AND external_id=?",
                identity,
            ).fetchone()
        if row is None:
            return None
        value = dict(row)
        value["scope_bindings"] = json.loads(value.pop("scope_bindings_json"))
        return value

    def save(self, provider, external_id, destination, scope_bindings, *, expected_revision):
        identity = canonical_identity(provider, external_id)
        if destination not in {"private", "work", "client", "shared"}:
            raise ValueError("Choose an explicit destination.")
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError("An expected destination revision is required.")
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT revision FROM context_destination_preferences "
                "WHERE provider=? AND external_id=?",
                identity,
            ).fetchone()
            if (row[0] if row else 0) != expected_revision:
                raise ContextRevisionConflictError(
                    "Destination changed; review the current choice."
                )
            # Validate and save under one write lock so a simultaneous merge cannot broaden rights.
            for binding in scope_bindings:
                space = conn.execute(
                    "SELECT scope_type, name, revision, merged_into FROM context_spaces WHERE id=?",
                    (binding["space_id"],),
                ).fetchone()
                if not space or space[3] or space[2] != binding["revision"]:
                    raise ContextRevisionConflictError("An allowed space changed; review it again.")
            encoded = json.dumps(scope_bindings, sort_keys=True)
            revision, now = expected_revision + 1, time.time()
            conn.execute(
                "INSERT INTO context_destination_preferences VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(provider,external_id) DO UPDATE SET destination=excluded.destination, "
                "scope_bindings_json=excluded.scope_bindings_json, revision=excluded.revision, "
                "updated_at=excluded.updated_at",
                (*identity, destination, encoded, revision, now),
            )
            conn.execute(
                "INSERT INTO context_destination_events VALUES(?,?,?,?,?,?)",
                (*identity, revision, destination, encoded, now),
            )
        return self.get(*identity)

    def history(self, provider: str, external_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM context_destination_events WHERE provider=? AND external_id=? "
                "ORDER BY revision DESC LIMIT 100",
                canonical_identity(provider, external_id),
            ).fetchall()
        return [dict(row) for row in rows]


class ContextTrustService:
    """Bridge-facing service. Text can suggest a route but cannot authorize one."""

    def __init__(self, store: ContextLibraryStore, retriever=None, *, clock=time.time):
        self.store = store
        self.preferences = ContextTrustStore(store.db_path)
        self.retriever = retriever or ContextRetriever(store)
        self.clock = clock
        self._lock = RLock()
        self._previews: dict[str, dict] = {}
        self._grants: dict[str, dict] = {}

    def clear_ephemeral(self):
        with self._lock:
            self._previews.clear()
            self._grants.clear()

    def _prune(self):
        for cache in (self._previews, self._grants):
            for key in list(cache):
                if cache[key]["expires_at"] <= self.clock():
                    del cache[key]
            while len(cache) >= MAX_EPHEMERAL_RECORDS:
                del cache[next(iter(cache))]

    def handle(self, payload: dict) -> dict:
        """Handle use/save_destination/destination_settings/preview_sensitive/confirm_sensitive.

        Caller must authenticate the bridge before calling. Unknown fields such as
        destination on a use request confer no permissions.
        """
        if not isinstance(payload, dict):
            raise ValueError("Invalid Context request.")
        identity = canonical_identity(payload.get("provider"), payload.get("external_id"))
        action = payload.get("action", "use")
        if not isinstance(action, str):
            raise ValueError("Unsupported Context action.")
        with self._lock:
            self._prune()
            if action == "save_destination":
                return self._save_destination(payload, identity)
            if action not in {
                "use",
                "destination_settings",
                "preview_sensitive",
                "confirm_sensitive",
            }:
                raise ValueError("Unsupported Context action.")
            request = self._parse_request(payload, identity)
            # Hold the archive write reservation through validation and assembly. A
            # source update, deletion, or scope correction cannot split this snapshot.
            with self.store.transaction():
                preference = self.preferences.get(*identity)
                if action == "destination_settings" or not self._valid_preference(preference):
                    return self._destination_review(request, preference)
                request = ContextAssemblyInput(
                    request.provider,
                    request.external_id,
                    request.messages,
                    request.draft,
                    preference["destination"],
                    tuple(
                        AllowedScope(b["scope_type"], b["scope_key"])
                        for b in preference["scope_bindings"]
                    ),
                    request.max_context_chars,
                )
                request_digest = _digest({"request": asdict(request), "preference": preference})
                if action == "preview_sensitive":
                    return self._preview(request, request_digest)
                if action == "confirm_sensitive":
                    return self._confirm(payload, request_digest)
                versions = {}
                token = payload.get("confirmation_token")
                if token:
                    grant = self._grants.pop(_digest(token), None)
                    if not self._valid_consent(grant, request_digest):
                        return self._confirmation_expired()
                    versions = grant["versions"]
                try:
                    result = assemble_context(
                        self.store,
                        request,
                        retriever=self.retriever,
                        sensitive_versions=versions,
                    )
                    response = asdict(result)
                    for item in response["items"]:
                        item["provenance"] = {
                            "provider": item.pop("source_provider"),
                            "title": item.pop("source_title"),
                            "message_index": item.pop("source_message_index"),
                        }
                    response.update(status="ready", reason="context_ready")
                    response["used"] = [
                        {"item_id": item.item_id, "reasons": list(item.reasons)}
                        for item in result.items
                    ]
                except ContextUnavailableError:
                    response = {"status": "error", "reason": "context_unavailable"}
                response["destination"] = preference["destination"]
                response["destination_revision"] = preference["revision"]
                response["sensitive_available"] = bool(self._sensitive_hits(request))
                response["excluded_reasons"] = [
                    "Items outside the approved destination scopes are excluded.",
                    "Sensitive items require a separate preview and one-use confirmation.",
                    "Uncertain, inactive, or unrelated items may be excluded.",
                    "Unresolved conflicts and records kept as competing claims require review; "
                    "only an explicitly preferred record can be used.",
                ]
                return response

    def _parse_request(self, payload, identity):
        messages = payload.get("messages", [])
        if not isinstance(messages, list) or not all(isinstance(row, dict) for row in messages):
            raise ValueError("Invalid current chat.")
        if not isinstance(payload.get("draft"), str):
            raise ValueError("A non-empty current draft is required.")
        budget = payload.get("max_context_chars", 6000)
        if type(budget) is not int:
            raise ValueError("Invalid Context budget.")
        if any(
            not isinstance(row.get("content"), str) or not isinstance(row.get("role"), str)
            for row in messages
        ):
            raise ValueError("Invalid current chat.")
        request = ContextAssemblyInput(
            *identity,
            tuple(CurrentChatMessage(row.get("role"), row["content"]) for row in messages),
            payload["draft"],
            "private",
            (),
            budget,
        )
        _validate_request(request)
        return request

    def _bindings(self, space_ids, destination):
        if not isinstance(space_ids, list) or len(space_ids) > 25:
            raise ValueError("Choose at most 25 allowed spaces.")
        if not all(isinstance(value, str) for value in space_ids) or len(set(space_ids)) != len(
            space_ids
        ):
            raise ValueError("Invalid allowed spaces.")
        if destination != "private" and not space_ids:
            raise ValueError("Work, client, and shared destinations require an explicit allowlist.")
        bindings = []
        for space_id in sorted(space_ids):
            space = self.store.get_space(space_id)
            if (
                not space
                or space.merged_into
                or space.scope_type not in DESTINATION_SCOPE_TYPES.get(destination, set())
            ):
                raise ValueError("This space is not allowed for the selected destination.")
            bindings.append(
                {
                    "space_id": space.id,
                    "revision": space.revision,
                    "scope_type": space.scope_type,
                    "scope_key": space.name
                    if space.scope_type in {"project", "topic", "destination"}
                    else "",
                }
            )
        return bindings

    def _save_destination(self, payload, identity):
        destination = payload.get("destination")
        if not isinstance(destination, str) or destination not in {
            "private",
            "work",
            "client",
            "shared",
        }:
            raise ValueError("Choose an explicit destination.")
        bindings = self._bindings(payload.get("allowed_space_ids", []), destination)
        value = self.preferences.save(
            *identity,
            destination,
            bindings,
            expected_revision=payload.get("expected_revision"),
        )
        # A correction invalidates every outstanding consent for this app session.
        self.clear_ephemeral()
        return {
            "status": "destination_saved",
            "reason": "destination_saved",
            "destination": destination,
            "destination_revision": value["revision"],
        }

    def _valid_preference(self, preference):
        if not preference:
            return False
        try:
            current = self._bindings(
                [binding["space_id"] for binding in preference["scope_bindings"]],
                preference["destination"],
            )
            return current == preference["scope_bindings"]
        except (ValueError, KeyError, TypeError):
            return False

    def _destination_review(self, request, preference):
        inference = self.retriever.infer_destination(
            provider=request.provider,
            external_id=request.external_id,
            query=request.draft + "\n" + "\n".join(m.content for m in request.messages[-8:]),
        )
        suggested = set(inference.suggested_scopes)
        spaces = sorted(
            self.store.list_spaces(),
            key=lambda space: (
                (space.scope_type, space.name) not in suggested,
                space.scope_type,
                space.name,
            ),
        )[:200]
        return {
            "status": "destination_confirmation_required",
            "reason": "destination_review_required",
            "destination": preference["destination"] if preference else "unknown",
            "destination_revision": preference["revision"] if preference else 0,
            "allowed_space_ids": [b["space_id"] for b in preference["scope_bindings"]]
            if preference
            else [],
            "suggested_destination": inference.suggested_destination,
            "reasons": list(inference.reasons)
            + (
                ["Saved spaces changed; review the allowlist."]
                if preference and not self._valid_preference(preference)
                else []
            ),
            "spaces": [
                {
                    "space_id": s.id,
                    "scope_type": s.scope_type,
                    "name": s.name[:120],
                    "suggested": (s.scope_type, s.name) in suggested,
                }
                for s in spaces
            ],
        }

    def _sensitive_hits(self, request):
        return self.retriever.retrieve(
            query=request.draft,
            destination=request.destination,
            allowed_scopes={(s.scope_type, s.scope_key) for s in request.allowed_scopes},
            sensitive_preview=True,
            limit=MAX_PREVIEW_ITEMS,
        ).hits

    def _snapshot(self, item_id):
        """Bind the complete evidence set and live source contents, including deletions."""
        with self.retriever._connect() as conn:
            row = conn.execute("SELECT * FROM context_items WHERE id=?", (item_id,)).fetchone()
            if row is None:
                return None, None
            scopes = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM context_item_scopes WHERE item_id=? "
                    "ORDER BY scope_type, scope_key",
                    (item_id,),
                )
            ]
            evidence = [
                dict(r)
                for r in conn.execute(
                    "SELECT e.*, m.content AS live_content FROM context_evidence e "
                    "LEFT JOIN messages m ON m.id=e.source_message_id "
                    "WHERE e.item_id=? ORDER BY e.id",
                    (item_id,),
                )
            ]
            links = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM context_item_links WHERE source_item_id=? OR target_item_id=? "
                    "ORDER BY source_item_id, target_item_id",
                    (item_id, item_id),
                )
            ]
        snapshot = {"item": dict(row), "scopes": scopes, "evidence": evidence, "links": links}
        preview = {
            "item_id": item_id,
            "version": row["current_version"],
            "text": row["canonical_text"],
            "epistemic_kind": row["epistemic_kind"],
            "confidence": row["confidence"],
            "inference_rationale": row["inference_rationale"],
            "sources": [
                {
                    "provider": e["source_provider"],
                    "title": e["source_title"][:160],
                    "message_index": e["source_message_index"],
                    "excerpt": e["excerpt"][:1200],
                    "source_available": e["live_content"] is not None,
                    "source_changed": e["live_content"] is not None
                    and e["excerpt"] not in e["live_content"],
                }
                for e in evidence[:3]
            ],
        }
        return _digest(snapshot), preview

    def _preview(self, request, request_digest):
        items, snapshots, versions = [], {}, {}
        remaining = 22_000
        for hit in self._sensitive_hits(request):
            fingerprint, preview = self._snapshot(hit.item_id)
            if not preview or preview["version"] != hit.current_version:
                continue
            # Do not let a clipped sensitive claim look like a complete approval.
            size = len(json.dumps(preview, ensure_ascii=False).encode("utf-8"))
            if size > remaining:
                continue
            items.append(preview)
            remaining -= size
            snapshots[hit.item_id], versions[hit.item_id] = fingerprint, hit.current_version
        token = secrets.token_urlsafe(32)
        self._previews[_digest(token)] = {
            "digest": request_digest,
            "versions": versions,
            "snapshots": snapshots,
            "expires_at": self.clock() + CONSENT_TTL_SECONDS,
        }
        return {
            "status": "sensitive_preview",
            "reason": "sensitive_preview_required",
            "preview_token": token,
            "expires_in_seconds": CONSENT_TTL_SECONDS,
            "destination": request.destination,
            "items": items,
        }

    def _valid_consent(self, record, request_digest):
        if not record or record["expires_at"] <= self.clock() or record["digest"] != request_digest:
            return False
        return all(
            self._snapshot(item_id)[0] == fingerprint
            for item_id, fingerprint in record["snapshots"].items()
        )

    def _confirm(self, payload, request_digest):
        token = payload.get("preview_token")
        if not isinstance(token, str) or len(token) > 200:
            return self._confirmation_expired()
        preview = self._previews.pop(_digest(token), None)
        if not self._valid_consent(preview, request_digest):
            return self._confirmation_expired()
        selected = payload.get("selected_items")
        if not isinstance(selected, list) or not 1 <= len(selected) <= MAX_PREVIEW_ITEMS:
            raise ValueError("Select specific sensitive items from the preview.")
        versions = {}
        for item in selected:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("item_id"), str)
                or type(item.get("version")) is not int
                or preview["versions"].get(item["item_id"]) != item["version"]
                or item["item_id"] in versions
            ):
                return self._confirmation_expired()
            versions[item["item_id"]] = item["version"]
        grant = secrets.token_urlsafe(32)
        self._grants[_digest(grant)] = {
            **preview,
            "versions": versions,
            "snapshots": {key: preview["snapshots"][key] for key in versions},
        }
        return {
            "status": "sensitive_confirmed",
            "reason": "sensitive_confirmed",
            "confirmation_token": grant,
            "expires_in_seconds": CONSENT_TTL_SECONDS,
        }

    @staticmethod
    def _confirmation_expired():
        return {
            "status": "error",
            "reason": "confirmation_expired",
            "message": "The request, destination, item, or source changed. Preview again.",
        }
