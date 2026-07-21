"""Archive browsing, deletion, backup, and restore operations."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from reweave.archive import ArchiveStore

ArchiveSource = Literal["chatgpt", "claude"]
ArchiveSort = Literal["newest", "oldest", "messages", "title"]


@dataclass(frozen=True)
class LibraryConversation:
    id: str
    source: str
    title: str
    created_at: str
    updated_at: str | None
    raw_message_count: int
    preview: str


@dataclass(frozen=True)
class ConversationPage:
    results: tuple[LibraryConversation, ...]
    total: int
    offset: int
    limit: int


@dataclass(frozen=True)
class DeletionSummary:
    conversations: int
    messages: int
    embeddings: int
    reports: int


@dataclass(frozen=True)
class RestoreSummary:
    conversations: int
    messages: int
    reports: int
    safety_backup_path: str


class ArchiveManager:
    """Perform privacy-sensitive archive management outside the search store."""

    def __init__(self, db_path: Path):
        self.db_path = db_path

    def list_conversations(
        self,
        *,
        source: str | None = None,
        title: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        sort: str = "newest",
        offset: int = 0,
        limit: int = 50,
    ) -> ConversationPage:
        """Return a filtered page of conversations for archive browsing."""
        if source and source not in {"chatgpt", "claude"}:
            raise ValueError("Source must be chatgpt or claude.")
        order_by = {
            "newest": "COALESCE(NULLIF(c.updated_at, ''), c.created_at) DESC, c.title",
            "oldest": "c.created_at ASC, c.title",
            "messages": "c.raw_message_count DESC, c.title",
            "title": "c.title COLLATE NOCASE ASC, c.created_at DESC",
        }.get(sort)
        if order_by is None:
            raise ValueError("Sort must be newest, oldest, messages, or title.")

        clauses: list[str] = []
        params: list[object] = []
        if source:
            clauses.append("c.source = ?")
            params.append(source)
        if title:
            clauses.append("c.title LIKE ?")
            params.append(f"%{title.strip()}%")
        if date_from:
            clauses.append("c.created_at >= ?")
            params.append(date_from)
        if date_to:
            clauses.append("c.created_at <= ?")
            params.append(date_to)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        page_limit = min(max(limit, 1), 100)
        page_offset = max(offset, 0)

        with closing(self._connect()) as conn:
            total = conn.execute(
                f"SELECT COUNT(*) FROM conversations c {where}", params
            ).fetchone()[0]
            rows = conn.execute(
                f"""
                SELECT c.id, c.source, c.title, c.created_at, c.updated_at,
                       c.raw_message_count,
                       COALESCE((
                           SELECT SUBSTR(
                               REPLACE(REPLACE(m.content, CHAR(13), ' '), CHAR(10), ' '),
                               1,
                               240
                           )
                           FROM messages m
                           WHERE m.conversation_id = c.id AND TRIM(m.content) <> ''
                           ORDER BY m.message_index
                           LIMIT 1
                       ), '') AS preview
                FROM conversations c
                {where}
                ORDER BY {order_by}
                LIMIT ? OFFSET ?
                """,
                [*params, page_limit, page_offset],
            ).fetchall()

        return ConversationPage(
            results=tuple(
                LibraryConversation(
                    id=row["id"],
                    source=row["source"],
                    title=row["title"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    raw_message_count=row["raw_message_count"],
                    preview=row["preview"],
                )
                for row in rows
            ),
            total=total,
            offset=page_offset,
            limit=page_limit,
        )

    def delete_conversation(self, conversation_id: str) -> DeletionSummary:
        """Delete one source conversation and source-bound legacy artifacts.

        Context Items and Briefs retain compact evidence snapshots and nullable source links.
        """
        with closing(self._connect()) as conn, conn:
            exists = conn.execute(
                "SELECT 1 FROM conversations WHERE id = ?", (conversation_id,)
            ).fetchone()
            if exists is None:
                raise LookupError("Conversation not found.")
            return self._delete_conversations(conn, [conversation_id])

    def delete_source(self, source: str) -> DeletionSummary:
        """Delete every conversation imported from one provider."""
        if source not in {"chatgpt", "claude"}:
            raise ValueError("Source must be chatgpt or claude.")
        with closing(self._connect()) as conn, conn:
            ids = [
                row["id"]
                for row in conn.execute(
                    "SELECT id FROM conversations WHERE source = ?", (source,)
                ).fetchall()
            ]
            return self._delete_conversations(conn, ids)

    def backup_to(self, destination: Path) -> Path:
        """Create a consistent SQLite backup without stopping the local app."""
        destination = destination.resolve()
        if destination == self.db_path.resolve():
            raise ValueError("Backup destination must differ from the active archive.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.unlink(missing_ok=True)
        with (
            closing(sqlite3.connect(self.db_path)) as source,
            closing(sqlite3.connect(destination)) as target,
        ):
            source.backup(target)
        return destination

    def restore_from(self, source_path: Path, *, safety_backup_dir: Path) -> RestoreSummary:
        """Replace the archive after validation and keep an automatic rollback backup."""
        source_path = source_path.resolve()
        self._validate_backup(source_path)
        stamp = datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S")
        safety_backup = self.backup_to(
            safety_backup_dir / f"reweave-before-restore-{stamp}.sqlite3"
        )

        try:
            with (
                closing(sqlite3.connect(source_path)) as source,
                closing(sqlite3.connect(self.db_path)) as target,
            ):
                source.backup(target)
            migrated_store = ArchiveStore(self.db_path)
        except Exception:
            with (
                closing(sqlite3.connect(safety_backup)) as source,
                closing(sqlite3.connect(self.db_path)) as target,
            ):
                source.backup(target)
            raise

        stats = migrated_store.stats()
        return RestoreSummary(
            conversations=stats.total_conversations,
            messages=stats.total_messages,
            reports=len(migrated_store.list_insight_reports()),
            safety_backup_path=str(safety_backup),
        )

    def _delete_conversations(
        self, conn: sqlite3.Connection, conversation_ids: list[str]
    ) -> DeletionSummary:
        if not conversation_ids:
            return DeletionSummary(conversations=0, messages=0, embeddings=0, reports=0)

        placeholders = ",".join("?" for _ in conversation_ids)
        messages = conn.execute(
            f"SELECT COUNT(*) FROM messages WHERE conversation_id IN ({placeholders})",
            conversation_ids,
        ).fetchone()[0]
        embeddings = conn.execute(
            f"""
            SELECT COUNT(*)
            FROM chunk_embeddings e
            JOIN search_chunks c ON c.id = e.chunk_id
            WHERE c.conversation_id IN ({placeholders})
            """,
            conversation_ids,
        ).fetchone()[0]
        deleted_reports = 0
        selected_ids = set(conversation_ids)
        for row in conn.execute(
            "SELECT id, selected_conversation_ids FROM insight_reports"
        ).fetchall():
            try:
                report_ids = set(json.loads(row["selected_conversation_ids"]))
            except (TypeError, ValueError, json.JSONDecodeError):
                report_ids = set()
            if selected_ids & report_ids:
                conn.execute("DELETE FROM insight_reports WHERE id = ?", (row["id"],))
                deleted_reports += 1

        for table in ("messages_fts", "messages_fts_trigram"):
            conn.execute(
                f"DELETE FROM {table} WHERE conversation_id IN ({placeholders})",
                conversation_ids,
            )
        conn.execute(f"DELETE FROM conversations WHERE id IN ({placeholders})", conversation_ids)
        return DeletionSummary(
            conversations=len(conversation_ids),
            messages=messages,
            embeddings=embeddings,
            reports=deleted_reports,
        )

    @staticmethod
    def _validate_backup(path: Path) -> None:
        if not path.exists() or not path.is_file():
            raise ValueError("Backup file does not exist.")
        try:
            with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as conn:
                tables = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
                    )
                }
                required = {"conversations", "messages", "insight_reports"}
                if not required.issubset(tables):
                    raise ValueError("This is not a Reweave archive backup.")
                if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise ValueError("The archive backup failed its integrity check.")
        except sqlite3.DatabaseError as exc:
            raise ValueError("The selected file is not a valid SQLite backup.") from exc

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
