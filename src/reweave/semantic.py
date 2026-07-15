"""Optional local semantic indexing and hybrid archive retrieval."""

from __future__ import annotations

import heapq
import shutil
import sqlite3
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path

import numpy as np

from reweave.archive import ArchiveStore, ConversationSearchResult, SearchResult

MODEL_ID = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
MAX_CHUNK_CHARS = 1_500
CHUNK_OVERLAP_CHARS = 200
EMBED_BATCH_SIZE = 64

ProgressCallback = Callable[[str, int, int], None]


class SemanticUnavailableError(RuntimeError):
    """Raised when semantic search is requested before its index is ready."""


@dataclass(frozen=True)
class SemanticStatus:
    model_id: str
    model_downloaded: bool
    indexed_chunks: int
    total_chunks: int
    total_messages: int
    ready: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SemanticHit:
    conversation_id: str
    message_id: str
    message_index: int
    source: str
    title: str
    role: str
    timestamp: str | None
    excerpt: str
    score: float


class SemanticIndex:
    """Build and query local FastEmbed vectors stored in the archive SQLite file."""

    def __init__(
        self,
        db_path: Path,
        models_dir: Path,
        *,
        embedder_factory: Callable[[], object] | None = None,
    ):
        self.db_path = db_path
        self.models_dir = models_dir
        self.embedder_factory = embedder_factory
        self._embedder: object | None = None

    def status(self) -> SemanticStatus:
        with self._connect() as conn:
            total_messages = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            total_chunks = conn.execute("SELECT COUNT(*) FROM search_chunks").fetchone()[0]
            indexed_chunks = conn.execute(
                "SELECT COUNT(*) FROM chunk_embeddings WHERE model_id = ?",
                (MODEL_ID,),
            ).fetchone()[0]
            unchunked_messages = conn.execute(
                """
                SELECT COUNT(*)
                FROM messages m
                WHERE TRIM(m.content) <> ''
                  AND NOT EXISTS (
                      SELECT 1 FROM search_chunks sc WHERE sc.message_id = m.id
                  )
                """
            ).fetchone()[0]
        downloaded = self._model_downloaded()
        return SemanticStatus(
            model_id=MODEL_ID,
            model_downloaded=downloaded,
            indexed_chunks=indexed_chunks,
            total_chunks=total_chunks,
            total_messages=total_messages,
            ready=(
                downloaded
                and indexed_chunks > 0
                and indexed_chunks == total_chunks
                and unchunked_messages == 0
            ),
        )

    def build(
        self,
        *,
        rebuild: bool = False,
        progress: ProgressCallback | None = None,
        embedder: object | None = None,
    ) -> SemanticStatus:
        self.models_dir.mkdir(parents=True, exist_ok=True)
        if rebuild:
            self.delete_index()

        pending: list[tuple[str, str]] = []
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT m.id, m.conversation_id, m.message_index, m.content
                FROM messages m
                ORDER BY m.conversation_id, m.message_index
                """
            ).fetchall()
            for row in rows:
                for chunk_index, content in enumerate(split_message(row["content"])):
                    chunk_id = f"{row['id']}:{chunk_index}"
                    content_hash = sha256(content.encode("utf-8")).hexdigest()
                    existing = conn.execute(
                        "SELECT content_hash FROM search_chunks WHERE id = ?",
                        (chunk_id,),
                    ).fetchone()
                    if existing is None or existing["content_hash"] != content_hash:
                        conn.execute(
                            "DELETE FROM chunk_embeddings WHERE chunk_id = ?",
                            (chunk_id,),
                        )
                        conn.execute(
                            """
                            INSERT INTO search_chunks (
                                id, message_id, conversation_id, message_index,
                                chunk_index, content, content_hash
                            ) VALUES (?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(id) DO UPDATE SET
                                content = excluded.content,
                                content_hash = excluded.content_hash,
                                message_index = excluded.message_index
                            """,
                            (
                                chunk_id,
                                row["id"],
                                row["conversation_id"],
                                row["message_index"],
                                chunk_index,
                                content,
                                content_hash,
                            ),
                        )
                    embedded = conn.execute(
                        """
                        SELECT 1 FROM chunk_embeddings
                        WHERE chunk_id = ? AND model_id = ?
                        """,
                        (chunk_id, MODEL_ID),
                    ).fetchone()
                    if embedded is None:
                        pending.append((chunk_id, content))

        if not pending:
            if progress:
                progress("complete", 1, 1)
            return self.status()

        model = embedder or self._create_embedder()
        total = len(pending)
        for start in range(0, total, EMBED_BATCH_SIZE):
            batch = pending[start : start + EMBED_BATCH_SIZE]
            vectors = list(model.embed([content for _, content in batch]))
            with self._connect() as conn:
                for (chunk_id, _), vector in zip(batch, vectors, strict=True):
                    normalized = _normalize_vector(np.asarray(vector, dtype=np.float32))
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO chunk_embeddings (
                            chunk_id, model_id, dimensions, embedding
                        ) VALUES (?, ?, ?, ?)
                        """,
                        (chunk_id, MODEL_ID, int(normalized.size), normalized.tobytes()),
                    )
            if progress:
                progress("indexing", min(start + len(batch), total), total)
        if progress:
            progress("complete", total, total)
        return self.status()

    def search(
        self,
        query: str,
        *,
        provider: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        title: str | None = None,
        limit: int = 50,
        embedder: object | None = None,
    ) -> list[SemanticHit]:
        status = self.status()
        if not status.ready:
            raise SemanticUnavailableError("Smart search is not indexed yet.")
        model = embedder or self._create_embedder()
        query_vector = _normalize_vector(
            np.asarray(next(iter(model.embed([query]))), dtype=np.float32)
        )
        clauses = ["e.model_id = ?"]
        params: list[object] = [MODEL_ID]
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

        heap: list[tuple[float, int, sqlite3.Row]] = []
        sequence = 0
        with self._connect() as conn:
            cursor = conn.execute(
                f"""
                SELECT sc.content, sc.message_id, sc.conversation_id, sc.message_index,
                       e.embedding, c.source, c.title, m.role, m.timestamp
                FROM chunk_embeddings e
                JOIN search_chunks sc ON sc.id = e.chunk_id
                JOIN messages m ON m.id = sc.message_id
                JOIN conversations c ON c.id = sc.conversation_id
                WHERE {" AND ".join(clauses)}
                """,
                params,
            )
            for row in cursor:
                vector = np.frombuffer(row["embedding"], dtype=np.float32)
                if vector.size != query_vector.size:
                    continue
                score = float(np.dot(query_vector, vector))
                item = (score, sequence, row)
                sequence += 1
                if len(heap) < max(1, limit):
                    heapq.heappush(heap, item)
                elif score > heap[0][0]:
                    heapq.heapreplace(heap, item)

        return [
            SemanticHit(
                conversation_id=row["conversation_id"],
                message_id=row["message_id"],
                message_index=row["message_index"],
                source=row["source"],
                title=row["title"],
                role=row["role"],
                timestamp=row["timestamp"],
                excerpt=_semantic_excerpt(row["content"]),
                score=score,
            )
            for score, _, row in sorted(heap, reverse=True)
        ]

    def delete_index(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM chunk_embeddings")
            conn.execute("DELETE FROM search_chunks")

    def delete_model(self) -> None:
        self._embedder = None
        self.delete_index()
        if self.models_dir.exists():
            shutil.rmtree(self.models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)

    def _create_embedder(self):
        if self._embedder is not None:
            return self._embedder
        if self.embedder_factory is not None:
            self._embedder = self.embedder_factory()
            return self._embedder
        from fastembed import TextEmbedding

        self._embedder = TextEmbedding(model_name=MODEL_ID, cache_dir=str(self.models_dir))
        return self._embedder

    def _model_downloaded(self) -> bool:
        return self.models_dir.exists() and any(self.models_dir.rglob("*.onnx"))

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn


class SearchEngine:
    """Fuse archive keyword results with optional local semantic results."""

    def __init__(self, store: ArchiveStore, semantic_index: SemanticIndex):
        self.store = store
        self.semantic_index = semantic_index

    def search_messages(
        self,
        query: str,
        *,
        mode: str = "auto",
        provider: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        title: str | None = None,
        limit: int = 20,
    ) -> tuple[list[SearchResult], str]:
        if mode not in {"auto", "keyword", "semantic"}:
            raise ValueError("Search mode must be auto, keyword, or semantic.")
        status = self.semantic_index.status()
        use_semantic = mode == "semantic" or (mode == "auto" and status.ready)
        use_keyword = mode != "semantic"
        if mode == "semantic" and not status.ready:
            raise SemanticUnavailableError("Smart search is not indexed yet.")

        keyword_results = (
            self.store.search(
                query,
                provider=provider,
                date_from=date_from,
                date_to=date_to,
                title=title,
                limit=max(50, limit * 3),
            )
            if use_keyword
            else []
        )
        semantic_results = (
            self.semantic_index.search(
                query,
                provider=provider,
                date_from=date_from,
                date_to=date_to,
                title=title,
                limit=max(50, limit * 3),
            )
            if use_semantic
            else []
        )

        fused: dict[str, tuple[SearchResult, float, set[str]]] = {}
        for rank, result in enumerate(keyword_results, start=1):
            fused[result.message_id] = (result, 1.0 / (60 + rank), {"keyword"})
        for rank, hit in enumerate(semantic_results, start=1):
            score = 1.0 / (60 + rank)
            result = SearchResult(
                conversation_id=hit.conversation_id,
                message_id=hit.message_id,
                message_index=hit.message_index,
                source=hit.source,
                title=hit.title,
                role=hit.role,
                timestamp=hit.timestamp,
                excerpt=hit.excerpt,
                match_kind="semantic",
                rank_score=score,
            )
            existing = fused.get(hit.message_id)
            if existing is None:
                fused[hit.message_id] = (result, score, {"semantic"})
            else:
                existing_result, existing_score, kinds = existing
                fused[hit.message_id] = (
                    existing_result,
                    existing_score + score,
                    kinds | {"semantic"},
                )

        ranked = []
        for result, score, kinds in fused.values():
            ranked.append(
                SearchResult(
                    **{
                        **result.__dict__,
                        "match_kind": "both" if len(kinds) > 1 else next(iter(kinds)),
                        "rank_score": score,
                    }
                )
            )
        mode_used = (
            "hybrid"
            if use_keyword and use_semantic
            else ("semantic" if use_semantic else "keyword")
        )
        return (
            sorted(ranked, key=lambda item: item.rank_score, reverse=True)[: max(1, limit)],
            mode_used,
        )

    def search_conversations(
        self,
        query: str,
        *,
        mode: str = "auto",
        provider: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        title: str | None = None,
        limit: int = 20,
        excerpts_per_conversation: int = 3,
    ) -> tuple[list[ConversationSearchResult], str]:
        matches, mode_used = self.search_messages(
            query,
            mode=mode,
            provider=provider,
            date_from=date_from,
            date_to=date_to,
            title=title,
            limit=max(limit * excerpts_per_conversation * 3, 50),
        )
        grouped: dict[str, list[SearchResult]] = {}
        for match in matches:
            grouped.setdefault(match.conversation_id, []).append(match)
        results: list[ConversationSearchResult] = []
        for conversation_id, excerpts in grouped.items():
            conversation = self.store.get_conversation(conversation_id)
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
        return results, mode_used


def split_message(content: str) -> Iterator[str]:
    compact = content.strip()
    if not compact:
        return
    start = 0
    while start < len(compact):
        end = min(len(compact), start + MAX_CHUNK_CHARS)
        if end < len(compact):
            boundary = compact.rfind("\n", start + MAX_CHUNK_CHARS // 2, end)
            if boundary > start:
                end = boundary
        chunk = compact[start:end].strip()
        if chunk:
            yield chunk
        if end >= len(compact):
            break
        start = max(start + 1, end - CHUNK_OVERLAP_CHARS)


def _normalize_vector(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    return vector / norm if norm else vector


def _semantic_excerpt(content: str, max_chars: int = 320) -> str:
    compact = " ".join(content.split())
    return compact if len(compact) <= max_chars else f"{compact[:max_chars].rstrip()}..."
