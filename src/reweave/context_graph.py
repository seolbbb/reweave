"""Canonical local graph browsing and explicit redacted image previews."""

from __future__ import annotations

import hashlib
import json
import math
import secrets
import time
from collections import Counter, OrderedDict
from html import escape
from threading import Lock

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from reweave.context_library import ContextLibraryStore

SHARE_SCOPE_TYPES = {"work", "project", "topic", "destination"}


class GraphShareRequest(BaseModel):
    space_ids: list[str] = Field(min_length=1, max_length=50)
    item_ids: list[str] | None = Field(default=None, max_length=200)
    labels: dict[str, str] = Field(default_factory=dict, max_length=500)


class GraphExportRequest(BaseModel):
    preview_token: str = Field(min_length=1, max_length=128)
    confirmation: str


class ContextGraphService:
    def __init__(self, store: ContextLibraryStore):
        self.store = store
        self._lock = Lock()
        self._previews = OrderedDict()

    def clear_previews(self):
        with self._lock:
            self._previews.clear()

    def graph(self, *, space_id=None, limit=200):
        with self.store._connect() as conn:
            spaces = [
                dict(row)
                for row in conn.execute(
                    "SELECT id, name, scope_type FROM context_spaces "
                    "WHERE merged_into IS NULL ORDER BY scope_type, name"
                )
            ]
            if space_id and not any(space["id"] == space_id for space in spaces):
                raise LookupError("Context space not found.")
            conditions = "i.status IN ('active', 'stale', 'superseded')"
            params = []
            if space_id:
                conditions += " AND EXISTS (SELECT 1 FROM context_item_scopes s "
                conditions += "WHERE s.item_id = i.id AND s.space_id = ?)"
                params.append(space_id)
            total = conn.execute(
                f"SELECT COUNT(*) FROM context_items i WHERE {conditions}", params
            ).fetchone()[0]
            items = [
                dict(row)
                for row in conn.execute(
                    "SELECT i.id, i.canonical_text, i.item_type, i.epistemic_kind, "
                    "i.sensitivity, i.status, i.current_version FROM context_items i "
                    f"WHERE {conditions} ORDER BY i.updated_at DESC, i.id LIMIT ?",
                    [*params, limit],
                )
            ]
            ids = {item["id"] for item in items}
            membership = [
                dict(row)
                for row in conn.execute("SELECT item_id, space_id FROM context_item_scopes")
                if row["item_id"] in ids
            ]
            links = [
                dict(row)
                for row in conn.execute(
                    "SELECT source_item_id, target_item_id, relationship FROM context_item_links"
                )
                if row["source_item_id"] in ids and row["target_item_id"] in ids
            ]
        counts = Counter(row["space_id"] for row in membership)
        nodes = [
            {
                "id": item["id"],
                "kind": "item",
                "label": item["canonical_text"][:140],
                "item_type": item["item_type"],
                "epistemic_kind": item["epistemic_kind"],
                "sensitivity": item["sensitivity"],
                "status": item["status"],
            }
            for item in items
        ]
        nodes += [
            {
                "id": f"space:{space['id']}",
                "kind": "space",
                "label": space["name"],
                "scope_type": space["scope_type"],
                "item_count": counts[space["id"]],
            }
            for space in spaces
            if counts[space["id"]]
        ]
        edges = [
            {
                "source": row["item_id"],
                "target": f"space:{row['space_id']}",
                "relationship": "in_space",
            }
            for row in membership
        ]
        edges += [
            {
                "source": row["source_item_id"],
                "target": row["target_item_id"],
                "relationship": row["relationship"],
            }
            for row in links
        ]
        return {
            "nodes": nodes,
            "edges": edges,
            "spaces": spaces,
            "total_items": total,
            "shown_items": len(items),
            "truncated": total > len(items),
        }

    def _revision(self):
        with self.store._connect() as conn:
            parts = []
            for table, columns, order in (
                ("context_items", "id, current_version, sensitivity, status", "id"),
                ("context_item_scopes", "item_id, space_id", "item_id, space_id"),
                (
                    "context_item_links",
                    "source_item_id, target_item_id, relationship",
                    "source_item_id, target_item_id, relationship",
                ),
                ("context_spaces", "id, name, revision, merged_into", "id"),
            ):
                parts.append(
                    [
                        tuple(row)
                        for row in conn.execute(f"SELECT {columns} FROM {table} ORDER BY {order}")
                    ]
                )
        return hashlib.sha256(json.dumps(parts).encode()).hexdigest()

    def preview(self, request: GraphShareRequest):
        selected = set(request.space_ids)
        spaces = {space.id: space for space in self.store.list_spaces()}
        if any(space_id not in spaces for space_id in selected):
            raise ValueError("Choose existing Context spaces.")
        if any(spaces[space_id].scope_type not in SHARE_SCOPE_TYPES for space_id in selected):
            raise ValueError("Personal and Core Self are excluded from graph sharing.")
        if any(
            len(label) > 80 or any(ord(char) < 32 for char in label)
            for label in request.labels.values()
        ):
            raise ValueError(
                "Public labels must be at most 80 characters without control characters."
            )
        revision = self._revision()
        with self.store._connect() as conn:
            rows = [
                dict(row)
                for row in conn.execute(
                    "SELECT i.id, i.item_type, i.sensitivity, i.status, s.space_id, s.scope_type "
                    "FROM context_items i JOIN context_item_scopes s ON s.item_id = i.id "
                    "ORDER BY i.id, s.space_id"
                )
            ]
            candidates = {row["id"] for row in rows if row["space_id"] in selected}
            if request.item_ids is not None:
                candidates &= set(request.item_ids)
            denied = {
                row["id"]
                for row in rows
                if row["id"] in candidates
                and (
                    row["sensitivity"] != "normal"
                    or row["status"] != "active"
                    or row["scope_type"] not in SHARE_SCOPE_TYPES
                    or (
                        row["scope_type"] in {"project", "topic", "destination"}
                        and row["space_id"] not in selected
                    )
                )
            }
            allowed = candidates - denied
            if len(allowed) > 200:
                raise ValueError("Choose a smaller scope or at most 200 items for one image.")
            if not allowed:
                raise ValueError("No active, non-sensitive items fit all selected sharing scopes.")
            memberships = [
                row for row in rows if row["id"] in allowed and row["space_id"] in selected
            ]
            links = [
                dict(row)
                for row in conn.execute(
                    "SELECT source_item_id, target_item_id, relationship FROM context_item_links"
                )
                if row["source_item_id"] in allowed and row["target_item_id"] in allowed
            ]
        type_counts = Counter()
        nodes = []
        present_spaces = {row["space_id"] for row in memberships}
        for space_id in sorted(present_spaces):
            kind = spaces[space_id].scope_type
            type_counts[kind] += 1
            nodes.append(
                {
                    "id": f"space:{space_id}",
                    "kind": "space",
                    "label": f"{kind.title()} {type_counts[kind]}",
                }
            )
        item_types = {row["id"]: row["item_type"] for row in memberships}
        for item_id in sorted(allowed):
            kind = item_types[item_id]
            type_counts[kind] += 1
            nodes.append(
                {
                    "id": item_id,
                    "kind": "item",
                    "label": f"{kind.replace('_', ' ').title()} {type_counts[kind]}",
                }
            )
        custom = False
        for node in nodes:
            label = request.labels.get(node["id"], "").strip()
            if label:
                node["label"] = label
                custom = True
        edges = [
            {"source": row["id"], "target": f"space:{row['space_id']}", "relationship": "in_space"}
            for row in memberships
        ]
        edges += [
            {
                "source": row["source_item_id"],
                "target": row["target_item_id"],
                "relationship": row["relationship"],
            }
            for row in links
        ]
        if self._revision() != revision:
            raise RuntimeError("The library changed. Generate a new preview before sharing.")
        svg = _render_share_svg(nodes, edges)
        warnings = []
        if custom:
            warnings.append(
                "You added public labels. Check them for private information before export."
            )
        if len(selected) > 1:
            warnings.append(
                "This image combines selected spaces. "
                "Check whether their relationship is safe to share."
            )
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._previews[token] = (time.monotonic() + 600, revision, svg)
            while len(self._previews) > 10:
                self._previews.popitem(last=False)
        return {
            "preview_token": token,
            "svg": svg,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "excluded_count": len(denied),
            "warnings": warnings,
            "expires_in_seconds": 600,
        }

    def export(self, token):
        with self._lock:
            saved = self._previews.pop(token, None)
        if saved is None or saved[0] <= time.monotonic() or saved[1] != self._revision():
            raise RuntimeError(
                "The preview expired or the library changed. Preview again before export."
            )
        return saved[2]


def _render_share_svg(nodes, edges):
    columns = 4
    height = max(700, math.ceil(len(nodes) / columns) * 115 + 120)
    points = {
        node["id"]: (140 + (index % columns) * 240, 140 + (index // columns) * 115)
        for index, node in enumerate(nodes)
    }
    body = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="{height}" '
        f'viewBox="0 0 1000 {height}" role="img">',
        "<title>Selected Context connections</title>",
        "<desc>Redacted graph. Original item text, source titles, "
        "and evidence are excluded.</desc>",
        f'<rect width="1000" height="{height}" fill="#F7F6F2"/>',
        '<text x="40" y="48" fill="#242A28" font-family="Segoe UI, sans-serif" '
        'font-size="25">Selected Context connections</text>',
        '<text x="40" y="76" fill="#5E6762" font-family="Segoe UI, sans-serif" '
        'font-size="14">Original text and source evidence excluded</text>',
    ]
    for edge in edges:
        source, target = points[edge["source"]], points[edge["target"]]
        body.append(
            f'<line x1="{source[0]}" y1="{source[1]}" x2="{target[0]}" y2="{target[1]}" '
            'stroke="#B5C6BD" stroke-width="1.5"/>'
        )
    for node in nodes:
        x, y = points[node["id"]]
        fill = "#E9F0EB" if node["kind"] == "space" else "#FFFFFF"
        body.append(
            f'<rect x="{x - 103}" y="{y - 33}" width="206" height="66" rx="10" '
            f'fill="{fill}" stroke="#31584B"/>'
        )
        label = node["label"]
        lines = [label[index : index + 26] for index in range(0, len(label), 26)][:3]
        for index, line in enumerate(lines):
            line_y = y - (len(lines) - 1) * 8 + index * 16
            body.append(
                f'<text x="{x}" y="{line_y}" text-anchor="middle" dominant-baseline="middle" '
                'font-family="Segoe UI, sans-serif" font-size="13" fill="#242A28">'
                f"{escape(line)}</text>"
            )
    body.append("</svg>")
    return "".join(body)


def graph_router(service: ContextGraphService):
    router = APIRouter(prefix="/api/context/graph")

    @router.get("")
    def graph(space_id: str | None = None, limit: int = Query(default=200, ge=1, le=500)):
        try:
            return service.graph(space_id=space_id, limit=limit)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.post("/share/preview")
    def preview(request: GraphShareRequest):
        try:
            return service.preview(request)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.post("/share/export")
    def export(request: GraphExportRequest):
        if request.confirmation != "EXPORT":
            raise HTTPException(400, "Preview the redacted graph and explicitly confirm EXPORT.")
        try:
            svg = service.export(request.preview_token)
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc
        return Response(
            svg,
            media_type="image/svg+xml",
            headers={
                "Content-Disposition": 'attachment; filename="reweave-connections.svg"',
                "Cache-Control": "no-store",
            },
        )

    return router
