"""SQLite-backed local archive for parsed AI conversations."""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal
from uuid import uuid4

from reweave.models.conversation import NormalizedConversation
from reweave.parsers.detector import detect_and_parse


@dataclass(frozen=True)
class ImportSummary:
    parsed_conversations: int = 0
    inserted_conversations: int = 0
    inserted_messages: int = 0
    skipped_files: tuple[Path, ...] = ()


@dataclass(frozen=True)
class ArchivedConversation:
    id: str
    source: Literal["chatgpt", "claude"]
    title: str
    created_at: str
    updated_at: str | None
    raw_message_count: int
    source_path: str


@dataclass(frozen=True)
class ArchivedMessage:
    id: str
    conversation_id: str
    index: int
    role: str
    content: str
    timestamp: str | None


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
        inserted_messages = 0
        skipped_files: list[Path] = []

        with self._connect() as conn:
            for file_path in sorted(input_dir.rglob("*.json")):
                try:
                    conversations = detect_and_parse(file_path)
                except (json.JSONDecodeError, ValueError):
                    skipped_files.append(file_path)
                    continue

                parsed += len(conversations)
                for conversation in conversations:
                    conv_inserted, msg_inserted = self._insert_conversation(
                        conn, conversation, file_path
                    )
                    inserted_conversations += int(conv_inserted)
                    inserted_messages += msg_inserted

        return ImportSummary(
            parsed_conversations=parsed,
            inserted_conversations=inserted_conversations,
            inserted_messages=inserted_messages,
            skipped_files=tuple(skipped_files),
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

    def _import_json_file(self, file_path: Path) -> ImportSummary:
        parsed = 0
        inserted_conversations = 0
        inserted_messages = 0
        skipped_files: list[Path] = []

        with self._connect() as conn:
            try:
                conversations = detect_and_parse(file_path)
            except (json.JSONDecodeError, ValueError):
                skipped_files.append(file_path)
            else:
                parsed += len(conversations)
                for conversation in conversations:
                    conv_inserted, msg_inserted = self._insert_conversation(
                        conn, conversation, file_path
                    )
                    inserted_conversations += int(conv_inserted)
                    inserted_messages += msg_inserted

        return ImportSummary(
            parsed_conversations=parsed,
            inserted_conversations=inserted_conversations,
            inserted_messages=inserted_messages,
            skipped_files=tuple(skipped_files),
        )

    def search(
        self,
        query: str,
        *,
        provider: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        title: str | None = None,
        limit: int = 20,
    ) -> list[SearchResult]:
        """Search messages and conversation titles with optional filters."""
        match_query = _to_fts_query(query)
        if not match_query:
            return []

        clauses = ["messages_fts MATCH ?"]
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

        params.append(max(1, limit))
        sql = f"""
            SELECT
                f.conversation_id,
                f.message_id,
                f.message_index,
                c.source,
                c.title,
                f.role,
                f.timestamp,
                snippet(messages_fts, 6, '[', ']', '...', 24) AS excerpt
            FROM messages_fts f
            JOIN conversations c ON c.id = f.conversation_id
            WHERE {' AND '.join(clauses)}
            ORDER BY bm25(messages_fts)
            LIMIT ?
        """

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        return [
            SearchResult(
                conversation_id=row["conversation_id"],
                message_id=row["message_id"],
                message_index=row["message_index"],
                source=row["source"],
                title=row["title"],
                role=row["role"],
                timestamp=row["timestamp"],
                excerpt=_clean_snippet(row["excerpt"]),
            )
            for row in rows
        ]

    def search_conversations(
        self,
        query: str,
        *,
        provider: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        title: str | None = None,
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
                SELECT id, source, title, created_at, updated_at, raw_message_count, source_path
                FROM conversations
                WHERE id = ?
                """,
                (conversation_id,),
            ).fetchone()

        if row is None:
            return None
        return ArchivedConversation(
            id=row["id"],
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
                SELECT id, conversation_id, message_index, role, content, timestamp
                FROM messages
                WHERE conversation_id = ?
                ORDER BY message_index
                """,
                (conversation_id,),
            ).fetchall()

        return [
            ArchivedMessage(
                id=row["id"],
                conversation_id=row["conversation_id"],
                index=row["message_index"],
                role=row["role"],
                content=row["content"],
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
        source_path: Path,
    ) -> tuple[bool, int]:
        result = conn.execute(
            """
            INSERT OR IGNORE INTO conversations (
                id, source, title, created_at, updated_at, raw_message_count, source_path
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conversation.id,
                conversation.source,
                conversation.title,
                conversation.created_at,
                conversation.updated_at,
                conversation.raw_message_count,
                str(source_path),
            ),
        )
        inserted_conversation = result.rowcount == 1

        inserted_messages = 0
        for index, message in enumerate(conversation.messages):
            message_id = f"{conversation.id}:{index}"
            result = conn.execute(
                """
                INSERT OR IGNORE INTO messages (
                    id, conversation_id, message_index, role, content, timestamp
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    conversation.id,
                    index,
                    message.role,
                    message.content,
                    message.timestamp,
                ),
            )
            if result.rowcount == 1:
                inserted_messages += 1
                conn.execute(
                    """
                    INSERT INTO messages_fts (
                        message_id, conversation_id, message_index, role, timestamp, title, content
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        message_id,
                        conversation.id,
                        index,
                        message.role,
                        message.timestamp,
                        conversation.title,
                        message.content,
                    ),
                )

        return inserted_conversation, inserted_messages

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT,
                    raw_message_count INTEGER NOT NULL,
                    source_path TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    message_index INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
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
                """
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn


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
    tokens = re.findall(r"[^\s\"']+", query, flags=re.UNICODE)
    return " ".join(f'"{token}"' for token in tokens)


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
