"""SQLite-backed local archive for parsed AI conversations."""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal
from uuid import uuid4

from reweave.models.conversation import NormalizedConversation
from reweave.parsers.detector import detect_and_parse
from reweave.source_filters import add_context_source_filter


@dataclass(frozen=True)
class ImportSummary:
    parsed_conversations: int = 0
    inserted_conversations: int = 0
    updated_conversations: int = 0
    inserted_messages: int = 0
    updated_messages: int = 0
    invalidated_embeddings: int = 0
    skipped_files: tuple[Path, ...] = ()
    conversation_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConversationCaptureSummary:
    """Persistence result for one explicitly captured web conversation."""

    conversation_id: str
    outcome: Literal["created", "updated", "unchanged"]
    inserted_messages: int
    updated_messages: int
    invalidated_embeddings: int


@dataclass(frozen=True)
class ArchivedConversation:
    id: str
    source: Literal["chatgpt", "claude"]
    title: str
    created_at: str
    updated_at: str | None
    raw_message_count: int
    source_path: str
    source_id: str | None = None


@dataclass(frozen=True)
class ArchivedMessage:
    id: str
    conversation_id: str
    index: int
    role: str
    content: str
    timestamp: str | None
    source_id: str | None = None
    content_hash: str = ""


@dataclass(frozen=True)
class SearchResult:
    conversation_id: str
    message_id: str
    message_index: int
    source: str
    title: str
    role: str
    timestamp: str | None
    excerpt: str
    match_kind: str = "keyword"
    rank_score: float = 0.0


@dataclass(frozen=True)
class ConversationSearchResult:
    id: str
    source: str
    title: str
    created_at: str
    updated_at: str | None
    raw_message_count: int
    match_count: int
    excerpts: tuple[SearchResult, ...]


@dataclass(frozen=True)
class InsightReport:
    id: str
    title: str
    selected_conversation_ids: tuple[str, ...]
    provider: str
    model: str
    markdown: str
    created_at: str


@dataclass(frozen=True)
class SourceStats:
    source: str
    conversations: int
    messages: int


@dataclass(frozen=True)
class LongConversation:
    id: str
    title: str
    messages: int


@dataclass(frozen=True)
class ArchiveStats:
    total_conversations: int
    total_messages: int
    first_created: str | None
    last_created: str | None
    by_source: tuple[SourceStats, ...]
    longest_conversations: tuple[LongConversation, ...]


class ArchiveStore:
    """SQLite archive with FTS5-backed search."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def import_directory(self, input_dir: Path) -> ImportSummary:
        """Parse and import all supported JSON exports in a directory."""
        if not input_dir.exists() or not input_dir.is_dir():
            raise ValueError(f"Import directory does not exist: {input_dir}")

        parsed = 0
        inserted_conversations = 0
        updated_conversations = 0
        inserted_messages = 0
        updated_messages = 0
        invalidated_embeddings = 0
        skipped_files: list[Path] = []
        conversation_ids: list[str] = []

        with self._connect() as conn:
            for file_path in sorted(input_dir.rglob("*.json")):
                try:
                    conversations = detect_and_parse(file_path)
                except (json.JSONDecodeError, ValueError):
                    skipped_files.append(file_path)
                    continue

                parsed += len(conversations)
                for conversation in conversations:
                    result = self._insert_conversation(conn, conversation, file_path)
                    inserted_conversations += int(result[0])
                    updated_conversations += int(result[1])
                    inserted_messages += result[2]
                    updated_messages += result[3]
                    invalidated_embeddings += result[4]
                    conversation_ids.append(result[5])

        return ImportSummary(
            parsed_conversations=parsed,
            inserted_conversations=inserted_conversations,
            updated_conversations=updated_conversations,
            inserted_messages=inserted_messages,
            updated_messages=updated_messages,
            invalidated_embeddings=invalidated_embeddings,
            skipped_files=tuple(skipped_files),
            conversation_ids=tuple(dict.fromkeys(conversation_ids)),
        )

    def import_path(
        self,
        input_path: Path,
        *,
        extraction_root: Path | None = None,
    ) -> ImportSummary:
        """Import a directory, JSON file, or zip archive."""
        input_path = input_path.expanduser()
        if not input_path.exists():
            raise ValueError(f"Import path does not exist: {input_path}")
        if input_path.is_dir():
            return self.import_directory(input_path)

        suffix = input_path.suffix.lower()
        if suffix == ".json":
            return self._import_json_file(input_path)
        if suffix == ".zip":
            if extraction_root is None:
                with TemporaryDirectory(prefix="reweave-import-") as temp_dir:
                    extracted_dir = _extract_zip_safely(input_path, Path(temp_dir))
                    return self.import_directory(extracted_dir)
            extracted_dir = _extract_zip_safely(input_path, extraction_root)
            return self.import_directory(extracted_dir)

        raise ValueError(f"Unsupported import file type: {input_path.suffix or input_path.name}")

    def capture_conversation(
        self, conversation: NormalizedConversation
    ) -> ConversationCaptureSummary:
        """Persist one validated explicit web capture without a temporary export file."""
        if not conversation.source_id:
            raise ValueError("Captured conversations require a stable external ID.")
        if not conversation.messages:
            raise ValueError("Captured conversations require at least one message.")
        if conversation.raw_message_count != len(conversation.messages):
            raise ValueError("Captured conversation message count does not match its messages.")

        source_path = f"capture://{conversation.source}/{conversation.id}"
        with self._connect() as conn:
            result = self._insert_conversation(
                conn,
                conversation,
                source_path,
                allow_timestamp_fallback=False,
            )
            stored = conn.execute(
                "SELECT id FROM conversations WHERE source = ? AND source_id = ?",
                (conversation.source, conversation.source_id),
            ).fetchone()
            if stored is None:  # pragma: no cover - guarded by the transaction above.
                raise RuntimeError("Captured conversation could not be read after persistence.")

        inserted_conversation, updated_conversation, inserted, updated, invalidated, _ = result
        if inserted_conversation:
            outcome = "created"
        elif updated_conversation or inserted or updated:
            outcome = "updated"
        else:
            outcome = "unchanged"
        return ConversationCaptureSummary(
            conversation_id=stored["id"],
            outcome=outcome,
            inserted_messages=inserted,
            updated_messages=updated,
            invalidated_embeddings=invalidated,
        )

    def _import_json_file(self, file_path: Path) -> ImportSummary:
        parsed = 0
        inserted_conversations = 0
        updated_conversations = 0
        inserted_messages = 0
        updated_messages = 0
        invalidated_embeddings = 0
        skipped_files: list[Path] = []
        conversation_ids: list[str] = []

        with self._connect() as conn:
            try:
                conversations = detect_and_parse(file_path)
            except (json.JSONDecodeError, ValueError):
                skipped_files.append(file_path)
            else:
                parsed += len(conversations)
                for conversation in conversations:
                    result = self._insert_conversation(conn, conversation, file_path)
                    inserted_conversations += int(result[0])
                    updated_conversations += int(result[1])
                    inserted_messages += result[2]
                    updated_messages += result[3]
                    invalidated_embeddings += result[4]
                    conversation_ids.append(result[5])

        return ImportSummary(
            parsed_conversations=parsed,
            inserted_conversations=inserted_conversations,
            updated_conversations=updated_conversations,
            inserted_messages=inserted_messages,
            updated_messages=updated_messages,
            invalidated_embeddings=invalidated_embeddings,
            skipped_files=tuple(skipped_files),
            conversation_ids=tuple(dict.fromkeys(conversation_ids)),
        )

    def search(
        self,
        query: str,
        *,
        provider: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        title: str | None = None,
        space_id: str | None = None,
        item_type: str | None = None,
        limit: int = 20,
    ) -> list[SearchResult]:
        """Search exact, prefix, and substring candidates and fuse their ranks."""
        match_query = _to_fts_query(query)
        if not match_query:
            return []
        candidate_limit = max(20, limit)
        searches = [
            ("messages_fts", match_query, "keyword"),
            ("messages_fts", _to_prefix_fts_query(query), "prefix"),
        ]
        trigram_query = _to_trigram_fts_query(query)
        if trigram_query:
            searches.append(("messages_fts_trigram", trigram_query, "substring"))
        broad_query = _to_broad_fts_query(query)
        if broad_query:
            searches.append(("messages_fts", broad_query, "broad"))

        fused: dict[str, tuple[SearchResult, float, set[str]]] = {}
        with self._connect() as conn:
            for table, fts_query, match_kind in searches:
                if not fts_query:
                    continue
                if match_kind != "keyword" and len(fused) >= limit:
                    continue
                rows = self._search_fts(
                    conn,
                    table=table,
                    match_query=fts_query,
                    provider=provider,
                    date_from=date_from,
                    date_to=date_to,
                    title=title,
                    space_id=space_id,
                    item_type=item_type,
                    limit=candidate_limit,
                )
                for rank, row in enumerate(rows, start=1):
                    score = 1.0 / (60 + rank)
                    existing = fused.get(row["message_id"])
                    kinds = {match_kind}
                    result = SearchResult(
                        conversation_id=row["conversation_id"],
                        message_id=row["message_id"],
                        message_index=row["message_index"],
                        source=row["source"],
                        title=row["title"],
                        role=row["role"],
                        timestamp=row["timestamp"],
                        excerpt=_clean_snippet(row["excerpt"]),
                        match_kind=match_kind,
                        rank_score=score,
                    )
                    if existing is not None:
                        existing_result, existing_score, existing_kinds = existing
                        fused[row["message_id"]] = (
                            existing_result if "keyword" in existing_kinds else result,
                            existing_score + score,
                            existing_kinds | kinds,
                        )
                    else:
                        fused[row["message_id"]] = (result, score, kinds)

        ranked: list[SearchResult] = []
        for result, score, kinds in fused.values():
            ranked.append(
                SearchResult(
                    **{
                        **result.__dict__,
                        "match_kind": "keyword" if "keyword" in kinds else "+".join(sorted(kinds)),
                        "rank_score": score,
                    }
                )
            )
        return sorted(ranked, key=lambda item: item.rank_score, reverse=True)[: max(1, limit)]

    @staticmethod
    def _search_fts(
        conn: sqlite3.Connection,
        *,
        table: str,
        match_query: str,
        provider: str | None,
        date_from: str | None,
        date_to: str | None,
        title: str | None,
        space_id: str | None,
        item_type: str | None,
        limit: int,
    ) -> list[sqlite3.Row]:
        clauses = [f"{table} MATCH ?"]
        params: list[object] = [match_query]
        if provider:
            clauses.append("c.source = ?")
            params.append(provider)
        if date_from:
            clauses.append("c.created_at >= ?")
            params.append(date_from)
        if date_to:
            clauses.append("c.created_at <= ?")
            params.append(date_to)
        if title:
            clauses.append("c.title LIKE ?")
            params.append(f"%{title}%")
        add_context_source_filter(clauses, params, space_id=space_id, item_type=item_type)
        params.append(max(1, limit))
        return conn.execute(
            f"""
            SELECT
                f.conversation_id,
                f.message_id,
                f.message_index,
                c.source,
                c.title,
                f.role,
                f.timestamp,
                snippet({table}, 6, '[', ']', '...', 24) AS excerpt
            FROM {table} f
            JOIN conversations c ON c.id = f.conversation_id
            WHERE {" AND ".join(clauses)}
            ORDER BY bm25({table})
            LIMIT ?
            """,
            params,
        ).fetchall()

    def search_conversations(
        self,
        query: str,
        *,
        provider: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        title: str | None = None,
        space_id: str | None = None,
        item_type: str | None = None,
        limit: int = 20,
        excerpts_per_conversation: int = 3,
    ) -> list[ConversationSearchResult]:
        """Search and group matching messages by conversation."""
        matches = self.search(
            query=query,
            provider=provider,
            date_from=date_from,
            date_to=date_to,
            title=title,
            space_id=space_id,
            item_type=item_type,
            limit=max(limit * excerpts_per_conversation * 2, limit),
        )
        grouped: dict[str, list[SearchResult]] = {}
        for match in matches:
            grouped.setdefault(match.conversation_id, []).append(match)

        results: list[ConversationSearchResult] = []
        for conversation_id, excerpts in grouped.items():
            conversation = self.get_conversation(conversation_id)
            if conversation is None:
                continue
            results.append(
                ConversationSearchResult(
                    id=conversation.id,
                    source=conversation.source,
                    title=conversation.title,
                    created_at=conversation.created_at,
                    updated_at=conversation.updated_at,
                    raw_message_count=conversation.raw_message_count,
                    match_count=len(excerpts),
                    excerpts=tuple(excerpts[:excerpts_per_conversation]),
                )
            )
            if len(results) >= limit:
                break

        return results

    def get_conversation(self, conversation_id: str) -> ArchivedConversation | None:
        """Return one conversation by ID."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, source_id, source, title, created_at, updated_at,
                       raw_message_count, source_path
                FROM conversations
                WHERE id = ?
                """,
                (conversation_id,),
            ).fetchone()

        if row is None:
            return None
        return ArchivedConversation(
            id=row["id"],
            source_id=row["source_id"],
            source=row["source"],
            title=row["title"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            raw_message_count=row["raw_message_count"],
            source_path=row["source_path"],
        )

    def get_messages(self, conversation_id: str) -> list[ArchivedMessage]:
        """Return messages for one conversation in original order."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, source_id, conversation_id, message_index, role, content,
                       content_hash, timestamp
                FROM messages
                WHERE conversation_id = ?
                ORDER BY message_index
                """,
                (conversation_id,),
            ).fetchall()

        return [
            ArchivedMessage(
                id=row["id"],
                source_id=row["source_id"],
                conversation_id=row["conversation_id"],
                index=row["message_index"],
                role=row["role"],
                content=row["content"],
                content_hash=row["content_hash"],
                timestamp=row["timestamp"],
            )
            for row in rows
        ]

    def stats(self) -> ArchiveStats:
        """Return aggregate archive statistics."""
        with self._connect() as conn:
            totals = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_conversations,
                    COALESCE(SUM(raw_message_count), 0) AS total_messages,
                    MIN(NULLIF(created_at, '')) AS first_created,
                    MAX(NULLIF(created_at, '')) AS last_created
                FROM conversations
                """
            ).fetchone()
            by_source_rows = conn.execute(
                """
                SELECT c.source, COUNT(DISTINCT c.id) AS conversations, COUNT(m.id) AS messages
                FROM conversations c
                LEFT JOIN messages m ON m.conversation_id = c.id
                GROUP BY c.source
                ORDER BY c.source
                """
            ).fetchall()
            longest_rows = conn.execute(
                """
                SELECT id, title, raw_message_count AS messages
                FROM conversations
                ORDER BY raw_message_count DESC, title
                LIMIT 5
                """
            ).fetchall()

        return ArchiveStats(
            total_conversations=totals["total_conversations"],
            total_messages=totals["total_messages"],
            first_created=totals["first_created"],
            last_created=totals["last_created"],
            by_source=tuple(
                SourceStats(
                    source=row["source"],
                    conversations=row["conversations"],
                    messages=row["messages"],
                )
                for row in by_source_rows
            ),
            longest_conversations=tuple(
                LongConversation(id=row["id"], title=row["title"], messages=row["messages"])
                for row in longest_rows
            ),
        )

    def save_insight_report(
        self,
        *,
        title: str,
        selected_conversation_ids: list[str],
        provider: str,
        model: str,
        markdown: str,
    ) -> InsightReport:
        """Persist an insight report and return it."""
        report = InsightReport(
            id=uuid4().hex,
            title=title,
            selected_conversation_ids=tuple(selected_conversation_ids),
            provider=provider,
            model=model,
            markdown=markdown,
            created_at=datetime.now(tz=UTC).isoformat(),
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO insight_reports (
                    id, title, selected_conversation_ids, provider, model, markdown, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report.id,
                    report.title,
                    json.dumps(list(report.selected_conversation_ids)),
                    report.provider,
                    report.model,
                    report.markdown,
                    report.created_at,
                ),
            )
        return report

    def list_insight_reports(self) -> list[InsightReport]:
        """Return saved insight reports, newest first."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, title, selected_conversation_ids, provider, model, markdown, created_at
                FROM insight_reports
                ORDER BY created_at DESC
                """
            ).fetchall()
        return [_row_to_insight_report(row) for row in rows]

    def get_insight_report(self, report_id: str) -> InsightReport | None:
        """Return one saved insight report."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, title, selected_conversation_ids, provider, model, markdown, created_at
                FROM insight_reports
                WHERE id = ?
                """,
                (report_id,),
            ).fetchone()
        if row is None:
            return None
        return _row_to_insight_report(row)

    def _insert_conversation(
        self,
        conn: sqlite3.Connection,
        conversation: NormalizedConversation,
        source_path: Path | str,
        *,
        allow_timestamp_fallback: bool = True,
    ) -> tuple[bool, bool, int, int, int, str]:
        existing = None
        id_match = None
        if conversation.source_id:
            existing = conn.execute(
                "SELECT * FROM conversations WHERE source = ? AND source_id = ?",
                (conversation.source, conversation.source_id),
            ).fetchone()
        if existing is None:
            id_match = conn.execute(
                "SELECT * FROM conversations WHERE id = ?",
                (conversation.id,),
            ).fetchone()
            if (
                id_match is not None
                and id_match["source"] == conversation.source
                and not (
                    conversation.source_id
                    and id_match["source_id"]
                    and conversation.source_id != id_match["source_id"]
                )
            ):
                existing = id_match
        if existing is None and allow_timestamp_fallback:
            candidates = conn.execute(
                """
                SELECT * FROM conversations
                WHERE source = ? AND created_at = ?
                    AND (? IS NULL OR source_id IS NULL OR source_id = '')
                ORDER BY rowid
                LIMIT 2
                """,
                (conversation.source, conversation.created_at, conversation.source_id or None),
            ).fetchall()
            # A missing identity can upgrade a unique legacy match, not an arbitrary source.
            existing = candidates[0] if len(candidates) == 1 else None

        inserted_conversation = existing is None
        updated_conversation = False
        archive_id = conversation.id if existing is None else existing["id"]
        if existing is None and id_match is not None:
            # Legacy timestamp-derived IDs can collide after gaining an external identity.
            archive_id = uuid4().hex
        source_id = conversation.source_id or (
            existing["source_id"] if existing is not None else None
        )
        values = (
            source_id,
            conversation.source,
            conversation.title,
            conversation.created_at,
            conversation.updated_at,
            conversation.raw_message_count,
            str(source_path),
        )
        if existing is None:
            conn.execute(
                """
                INSERT INTO conversations (
                    id, source_id, source, title, created_at, updated_at,
                    raw_message_count, source_path
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (archive_id, *values),
            )
        else:
            old_values = (
                existing["source_id"],
                existing["source"],
                existing["title"],
                existing["created_at"],
                existing["updated_at"],
                existing["raw_message_count"],
                existing["source_path"],
            )
            updated_conversation = old_values != values
            conn.execute(
                """
                UPDATE conversations
                SET source_id = ?, source = ?, title = ?, created_at = ?, updated_at = ?,
                    raw_message_count = ?, source_path = ?
                WHERE id = ?
                """,
                (*values, archive_id),
            )
            if existing["title"] != conversation.title:
                conn.execute(
                    "UPDATE messages_fts SET title = ? WHERE conversation_id = ?",
                    (conversation.title, archive_id),
                )
                conn.execute(
                    "UPDATE messages_fts_trigram SET title = ? WHERE conversation_id = ?",
                    (conversation.title, archive_id),
                )

        inserted_messages = 0
        updated_messages = 0
        invalidated_embeddings = 0
        for index, message in enumerate(conversation.messages):
            existing_message = None
            if message.source_id:
                existing_message = conn.execute(
                    """
                    SELECT * FROM messages
                    WHERE conversation_id = ? AND source_id = ?
                    """,
                    (archive_id, message.source_id),
                ).fetchone()
            if existing_message is None:
                existing_message = conn.execute(
                    """
                    SELECT * FROM messages
                    WHERE conversation_id = ? AND message_index = ?
                    """,
                    (archive_id, index),
                ).fetchone()

            message_id = (
                existing_message["id"] if existing_message is not None else f"{archive_id}:{index}"
            )
            content_hash = _message_content_hash(
                message.role,
                message.content,
                message.timestamp,
            )
            if existing_message is None:
                conn.execute(
                    """
                    INSERT INTO messages (
                        id, source_id, conversation_id, message_index, role, content,
                        content_hash, timestamp
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        message_id,
                        message.source_id,
                        archive_id,
                        index,
                        message.role,
                        message.content,
                        content_hash,
                        message.timestamp,
                    ),
                )
                inserted_messages += 1
                self._insert_fts_message(
                    conn,
                    message_id=message_id,
                    conversation_id=archive_id,
                    message_index=index,
                    role=message.role,
                    timestamp=message.timestamp,
                    title=conversation.title,
                    content=message.content,
                )
                continue

            changed = (
                existing_message["source_id"] != message.source_id
                or existing_message["message_index"] != index
                or existing_message["content_hash"] != content_hash
            )
            if not changed:
                continue
            conn.execute(
                """
                UPDATE messages
                SET source_id = ?, message_index = ?, role = ?, content = ?,
                    content_hash = ?, timestamp = ?
                WHERE id = ?
                """,
                (
                    message.source_id,
                    index,
                    message.role,
                    message.content,
                    content_hash,
                    message.timestamp,
                    message_id,
                ),
            )
            updated_messages += 1
            invalidated_embeddings += conn.execute(
                "DELETE FROM chunk_embeddings WHERE chunk_id IN "
                "(SELECT id FROM search_chunks WHERE message_id = ?)",
                (message_id,),
            ).rowcount
            conn.execute("DELETE FROM search_chunks WHERE message_id = ?", (message_id,))
            self._delete_fts_message(conn, message_id)
            self._insert_fts_message(
                conn,
                message_id=message_id,
                conversation_id=archive_id,
                message_index=index,
                role=message.role,
                timestamp=message.timestamp,
                title=conversation.title,
                content=message.content,
            )

        return (
            inserted_conversation,
            updated_conversation,
            inserted_messages,
            updated_messages,
            invalidated_embeddings,
            archive_id,
        )

    @staticmethod
    def _delete_fts_message(conn: sqlite3.Connection, message_id: str) -> None:
        conn.execute("DELETE FROM messages_fts WHERE message_id = ?", (message_id,))
        conn.execute("DELETE FROM messages_fts_trigram WHERE message_id = ?", (message_id,))

    @staticmethod
    def _insert_fts_message(
        conn: sqlite3.Connection,
        *,
        message_id: str,
        conversation_id: str,
        message_index: int,
        role: str,
        timestamp: str | None,
        title: str,
        content: str,
    ) -> None:
        values = (
            message_id,
            conversation_id,
            message_index,
            role,
            timestamp,
            title,
            content,
        )
        for table in ("messages_fts", "messages_fts_trigram"):
            conn.execute(
                f"""
                INSERT INTO {table} (
                    message_id, conversation_id, message_index, role, timestamp, title, content
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    source_id TEXT,
                    source TEXT NOT NULL,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT,
                    raw_message_count INTEGER NOT NULL,
                    source_path TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    source_id TEXT,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    message_index INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL DEFAULT '',
                    timestamp TEXT,
                    UNIQUE(conversation_id, message_index)
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                    message_id UNINDEXED,
                    conversation_id UNINDEXED,
                    message_index UNINDEXED,
                    role UNINDEXED,
                    timestamp UNINDEXED,
                    title,
                    content
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts_trigram USING fts5(
                    message_id UNINDEXED,
                    conversation_id UNINDEXED,
                    message_index UNINDEXED,
                    role UNINDEXED,
                    timestamp UNINDEXED,
                    title,
                    content,
                    tokenize='trigram'
                );

                CREATE INDEX IF NOT EXISTS idx_messages_conversation
                    ON messages(conversation_id, message_index);
                CREATE INDEX IF NOT EXISTS idx_conversations_source
                    ON conversations(source);
                CREATE INDEX IF NOT EXISTS idx_conversations_created
                    ON conversations(created_at);

                CREATE TABLE IF NOT EXISTS insight_reports (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    selected_conversation_ids TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    markdown TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_insight_reports_created
                    ON insight_reports(created_at);

                CREATE TABLE IF NOT EXISTS schema_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS search_chunks (
                    id TEXT PRIMARY KEY,
                    message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    message_index INTEGER NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    UNIQUE(message_id, chunk_index)
                );

                CREATE TABLE IF NOT EXISTS chunk_embeddings (
                    chunk_id TEXT PRIMARY KEY REFERENCES search_chunks(id) ON DELETE CASCADE,
                    model_id TEXT NOT NULL,
                    dimensions INTEGER NOT NULL,
                    embedding BLOB NOT NULL
                );
                """
            )
            self._ensure_column(conn, "conversations", "source_id", "TEXT")
            self._ensure_column(conn, "messages", "source_id", "TEXT")
            self._ensure_column(
                conn,
                "messages",
                "content_hash",
                "TEXT NOT NULL DEFAULT ''",
            )
            conn.executescript(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_conversations_source_id
                    ON conversations(source, source_id) WHERE source_id IS NOT NULL;
                CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_source_id
                    ON messages(conversation_id, source_id) WHERE source_id IS NOT NULL;
                CREATE INDEX IF NOT EXISTS idx_search_chunks_conversation
                    ON search_chunks(conversation_id, message_index);
                INSERT OR REPLACE INTO schema_meta(key, value) VALUES ('schema_version', '2');
                """
            )
            stale_hashes = conn.execute(
                "SELECT id, role, content, timestamp FROM messages WHERE content_hash = ''"
            ).fetchall()
            for row in stale_hashes:
                conn.execute(
                    "UPDATE messages SET content_hash = ? WHERE id = ?",
                    (
                        _message_content_hash(row["role"], row["content"], row["timestamp"]),
                        row["id"],
                    ),
                )
            trigram_count = conn.execute(
                "SELECT COUNT(*) AS count FROM messages_fts_trigram"
            ).fetchone()["count"]
            if trigram_count == 0:
                conn.execute(
                    """
                    INSERT INTO messages_fts_trigram (
                        message_id, conversation_id, message_index, role, timestamp, title, content
                    )
                    SELECT m.id, m.conversation_id, m.message_index, m.role, m.timestamp,
                           c.title, m.content
                    FROM messages m
                    JOIN conversations c ON c.id = m.conversation_id
                    """
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

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()


def export_conversation_markdown(
    output_dir: Path,
    conversation: ArchivedConversation,
    messages: list[ArchivedMessage],
) -> Path:
    """Write one conversation as a source Markdown file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{conversation.id}-{_slugify(conversation.title)}.md"
    path = output_dir / filename
    lines = [
        "---",
        "type: source-conversation",
        f"conversation_id: {conversation.id}",
        f"source: {conversation.source}",
        f"title: {conversation.title!r}",
        f"created_at: {conversation.created_at!r}",
        f"updated_at: {conversation.updated_at!r}",
        f"raw_message_count: {conversation.raw_message_count}",
        f"source_path: {conversation.source_path!r}",
        "---",
        "",
        f"# {conversation.title}",
        "",
        f"- Conversation ID: `{conversation.id}`",
        f"- Source: `{conversation.source}`",
        f"- Created: `{conversation.created_at or '-'}`",
        "",
        "## Messages",
        "",
    ]

    for message in messages:
        timestamp = f" | {message.timestamp}" if message.timestamp else ""
        lines.extend(
            [
                f"### [{message.index}] {message.role}{timestamp}",
                "",
                f"> Source: `{conversation.id}` message `{message.index}`",
                "",
                message.content,
                "",
            ]
        )

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def export_search_markdown(
    output_dir: Path,
    query: str,
    results: list[SearchResult],
) -> Path:
    """Write search results as a source-grounded Markdown dossier."""
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"search-{_slugify(query)}.md"
    path = output_dir / filename
    lines = [
        "---",
        "type: search-dossier",
        f"query: {query!r}",
        f"result_count: {len(results)}",
        "---",
        "",
        f"# Search Dossier: {query}",
        "",
    ]

    for index, result in enumerate(results, start=1):
        timestamp = f" | {result.timestamp}" if result.timestamp else ""
        lines.extend(
            [
                f"## {index}. {result.title}",
                "",
                f"- Conversation ID: `{result.conversation_id}`",
                f"- Message ID: `{result.message_id}`",
                f"- Message index: `{result.message_index}`",
                f"- Source: `{result.source}`",
                f"- Role: `{result.role}`{timestamp}",
                "",
                result.excerpt,
                "",
            ]
        )

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def _to_fts_query(query: str) -> str:
    return " ".join(f'"{_escape_fts_term(term)}"' for term in _query_terms(query))


def _to_prefix_fts_query(query: str) -> str:
    parts = []
    for term, quoted in _query_parts(query):
        escaped = _escape_fts_term(term)
        parts.append(f'"{escaped}"' if quoted else f'"{escaped}"*')
    return " ".join(parts)


def _to_broad_fts_query(query: str) -> str:
    terms = _query_terms(query)
    if len(terms) < 2:
        return ""
    return " OR ".join(f'"{_escape_fts_term(term)}"' for term in terms)


def _to_trigram_fts_query(query: str) -> str:
    terms = [term for term in _query_terms(query) if len(term) >= 3]
    return " ".join(f'"{_escape_fts_term(term)}"' for term in terms)


def _query_terms(query: str) -> list[str]:
    return [term for term, _ in _query_parts(query)]


def _query_parts(query: str) -> list[tuple[str, bool]]:
    parts: list[tuple[str, bool]] = []
    pattern = re.compile(r'"([^\"]+)"|\'([^\']+)\'|([^\s\"\']+)', flags=re.UNICODE)
    for match in pattern.finditer(query.strip()):
        quoted_value = match.group(1) or match.group(2)
        value = quoted_value or match.group(3)
        if value:
            parts.append((value, quoted_value is not None))
    return parts


def _escape_fts_term(term: str) -> str:
    return term.replace('"', '""')


def _message_content_hash(role: str, content: str, timestamp: str | None) -> str:
    value = f"{role}\0{timestamp or ''}\0{content}"
    return sha256(value.encode("utf-8")).hexdigest()


def _clean_snippet(snippet: str) -> str:
    return " ".join(snippet.split())


def _slugify(text: str, max_length: int = 60) -> str:
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug, flags=re.UNICODE)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    slug = slug[:max_length].strip("-")
    return slug or "untitled"


def _extract_zip_safely(zip_path: Path, extraction_root: Path) -> Path:
    """Extract a zip archive under extraction_root without allowing path traversal."""
    if not zipfile.is_zipfile(zip_path):
        raise ValueError(f"Invalid zip archive: {zip_path}")

    extraction_root.mkdir(parents=True, exist_ok=True)
    resolved_root = extraction_root.resolve()
    digest = _file_digest(zip_path)
    target_dir = extraction_root / f"{zip_path.stem}-{digest[:12]}"
    resolved_target = target_dir.resolve()
    if not resolved_target.is_relative_to(resolved_root):
        raise ValueError("Unsafe extraction target.")
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True)

    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            if member.is_dir() or not member.filename.lower().endswith(".json"):
                continue
            member_path = target_dir / member.filename
            resolved_member = member_path.resolve()
            if not resolved_member.is_relative_to(resolved_target):
                raise ValueError(f"Unsafe zip entry: {member.filename}")
            member_path.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, open(member_path, "wb") as destination:
                shutil.copyfileobj(source, destination)

    return target_dir


def _file_digest(path: Path) -> str:
    digest = sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _row_to_insight_report(row: sqlite3.Row) -> InsightReport:
    return InsightReport(
        id=row["id"],
        title=row["title"],
        selected_conversation_ids=tuple(json.loads(row["selected_conversation_ids"])),
        provider=row["provider"],
        model=row["model"],
        markdown=row["markdown"],
        created_at=row["created_at"],
    )
