"""Complete source partitioning and resumable, bounded sequential analysis.

The caller owns provider configuration, normalization, and the final Library commit.
Only validated derived results are checkpointed. No provider call holds a DB lock.
Callers must serialize executions of the same source job. A committed checkpoint is
reused; a crash between provider completion and checkpoint commit is an unknown
attempt and can require another call.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from reweave.analysis_policy import AnalysisLimitError
from reweave.llm import ProviderConnectionChangedError, provider_attempt_recording

CHUNKING_VERSION = "context-chunking-v1"
BRIEF_TEXT_FIELDS = ("main_subject", "user_goal")
BRIEF_LIST_FIELDS = (
    "important_outcomes",
    "decisions",
    "lessons",
    "unresolved_questions",
    "actions",
)
MAX_RESULT_BYTES = 2 * 1024 * 1024
MAX_SEGMENTS = 512


def _json(value) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _digest(value) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SourcePiece:
    message_id: str
    message_index: int
    role: str
    timestamp: str | None
    start: int
    end: int
    content: str


@dataclass(frozen=True)
class SourceSegment:
    index: int
    pieces: tuple[SourcePiece, ...]

    def to_dict(self):
        return {"segment_index": self.index, "pieces": [asdict(piece) for piece in self.pieces]}

    @property
    def json_text(self):
        return _json(self.to_dict())

    @property
    def fingerprint(self):
        return _digest(self.to_dict())

    @property
    def covered_characters(self):
        return sum(len(piece.content) for piece in self.pieces)


@dataclass(frozen=True)
class AnalysisCoverage:
    run_key: str
    total_messages: int
    total_characters: int
    total_segments: int
    completed_segments: int
    completed_messages: int
    covered_characters: int
    completed_synthesis_steps: int
    provider_calls: int
    complete: bool
    state: str

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class ChunkAnalysisResult:
    chunks: tuple[dict, ...]
    synthesis: dict
    coverage: AnalysisCoverage
    complete: bool = True


class PartialAnalysisError(RuntimeError):
    def __init__(self, reason: str, coverage: AnalysisCoverage):
        self.reason = reason
        self.coverage = coverage
        super().__init__(
            f"Analysis is incomplete ({reason}): {coverage.completed_segments} of "
            f"{coverage.total_segments} source segments are checkpointed."
        )


def partition_messages(
    messages: Sequence[Any], *, max_payload_chars: int
) -> tuple[SourceSegment, ...]:
    """Partition every original character once within the exact serialized JSON limit.

    Offsets are Python Unicode character positions in the original message content.
    The caller must subtract its own system/source wrapper overhead from the budget.
    Both ArchivedMessage objects and matching dictionaries are accepted.
    """
    if type(max_payload_chars) is not int or not 512 <= max_payload_chars <= 2_000_000:
        raise ValueError("Source payload budget must be between 512 and 2,000,000 characters.")
    if not messages:
        raise ValueError("A source must contain messages.")
    segments, current = [], []
    seen_ids, seen_indices = set(), set()

    def flush():
        nonlocal current
        if current:
            segments.append(SourceSegment(len(segments), tuple(current)))
            current = []
            if len(segments) > MAX_SEGMENTS:
                raise ValueError("This source exceeds the supported segment count.")

    for message in messages:
        get = (
            message.get if isinstance(message, Mapping) else lambda key, m=message: getattr(m, key)
        )
        message_id, index, role, timestamp, content = (
            get("id"),
            get("index"),
            get("role"),
            get("timestamp"),
            get("content"),
        )
        if not isinstance(message_id, str) or not message_id or len(message_id) > 256:
            raise ValueError("A source message needs a bounded stable ID.")
        if type(index) is not int or index < 0 or message_id in seen_ids or index in seen_indices:
            raise ValueError("Source message identities and indices must be unique.")
        if (
            not isinstance(content, str)
            or not content
            or role not in {"user", "assistant", "system", "tool"}
        ):
            raise ValueError("Source messages need supported roles and non-empty content.")
        if timestamp is not None and (not isinstance(timestamp, str) or len(timestamp) > 100):
            raise ValueError("Source message timestamps must be bounded text.")
        seen_ids.add(message_id)
        seen_indices.add(index)
        offset = 0
        while offset < len(content):

            def piece(
                length,
                message_id=message_id,
                index=index,
                role=role,
                timestamp=timestamp,
                offset=offset,
                content=content,
            ):
                return SourcePiece(
                    message_id,
                    index,
                    role,
                    timestamp,
                    offset,
                    offset + length,
                    content[offset : offset + length],
                )

            def fits(length):
                return (
                    len(SourceSegment(len(segments), tuple([*current, piece(length)])).json_text)
                    <= max_payload_chars
                )

            remaining = len(content) - offset
            if fits(remaining):
                current.append(piece(remaining))
                offset += remaining
                continue
            low, high = 0, remaining
            while low < high:
                middle = (low + high + 1) // 2
                if fits(middle):
                    low = middle
                else:
                    high = middle - 1
            if low:
                current.append(piece(low))
                offset += low
                flush()
            elif current:
                flush()
            else:
                raise ValueError(
                    "The payload budget cannot contain one source character and its identity."
                )
    flush()
    return tuple(segments)


def _validated_brief(value):
    value = json.loads(_json(value))
    if not isinstance(value, dict) or set(value) != set(BRIEF_TEXT_FIELDS + BRIEF_LIST_FIELDS):
        raise ValueError("A normalized Brief must have exactly the supported fields.")
    for field in BRIEF_TEXT_FIELDS:
        if (
            not isinstance(value[field], str)
            or not value[field].strip()
            or len(value[field]) > 4000
        ):
            raise ValueError("A normalized Brief needs bounded subject and goal text.")
    for field in BRIEF_LIST_FIELDS:
        entries = value[field]
        if (
            not isinstance(entries, list)
            or len(entries) > 100
            or any(
                not isinstance(entry, str) or not entry.strip() or len(entry) > 4000
                for entry in entries
            )
        ):
            raise ValueError("Normalized Brief lists must contain bounded text.")
    return value


def _validated_chunk(value, segment):
    """Validate the checkpoint shape and exact evidence boundaries after normalization."""
    value = json.loads(_json(value))
    if not isinstance(value, dict) or set(value) != {
        "brief",
        "items",
        "dropped_items",
        "deduplicated_items",
    }:
        raise ValueError(
            "A normalized chunk must contain Brief, items, and normalization counts only."
        )
    _validated_brief(value["brief"])
    if not isinstance(value["items"], list) or len(value["items"]) > 50:
        raise ValueError("A normalized chunk has too many Context items.")
    for field in ("dropped_items", "deduplicated_items"):
        if type(value[field]) is not int or value[field] < 0:
            raise ValueError("Normalization counts must be nonnegative integers.")
    item_fields = {
        "canonical_text",
        "item_type",
        "epistemic_kind",
        "confidence",
        "sensitivity",
        "scopes",
        "evidence",
        "last_confirmed_at",
        "inference_rationale",
    }
    evidence_fields = {
        "message_id",
        "message_index",
        "message_role",
        "message_timestamp",
        "excerpt",
        "relationship",
    }
    for item in value["items"]:
        if not isinstance(item, dict) or set(item) != item_fields:
            raise ValueError("Checkpoint items must be normalized Context records.")
        if not isinstance(item["canonical_text"], str) or not item["canonical_text"].strip():
            raise ValueError("Checkpoint items need canonical text.")
        if (
            len(item["canonical_text"]) > 12000
            or item["item_type"]
            not in {
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
            or item["epistemic_kind"] not in {"observed", "inferred", "suggested"}
        ):
            raise ValueError("Checkpoint Context type or canonical text is invalid.")
        if (
            item["sensitivity"] not in {"normal", "sensitive"}
            or type(item["confidence"]) not in {int, float}
            or not 0 <= item["confidence"] <= 1
        ):
            raise ValueError("Checkpoint Context confidence or sensitivity is invalid.")
        if (
            not isinstance(item["inference_rationale"], str)
            or len(item["inference_rationale"]) > 4000
        ):
            raise ValueError("Checkpoint inference rationale must be bounded text.")
        if item["last_confirmed_at"] is not None and (
            not isinstance(item["last_confirmed_at"], str) or len(item["last_confirmed_at"]) > 100
        ):
            raise ValueError("Checkpoint confirmation time must be bounded text.")
        if not isinstance(item["scopes"], list) or not 1 <= len(item["scopes"]) <= 20:
            raise ValueError("Checkpoint Context needs bounded scopes.")
        for scope in item["scopes"]:
            if not isinstance(scope, dict) or set(scope) != {
                "scope_type",
                "scope_key",
                "confidence",
            }:
                raise ValueError("Checkpoint scopes must be normalized scope records.")
            if (
                scope["scope_type"]
                not in {"core_self", "personal", "work", "project", "topic", "destination"}
                or not isinstance(scope["scope_key"], str)
                or len(scope["scope_key"]) > 500
            ):
                raise ValueError("Checkpoint scope identity is invalid.")
            if type(scope["confidence"]) not in {int, float} or not 0 <= scope["confidence"] <= 1:
                raise ValueError("Checkpoint scope confidence is invalid.")
        if not isinstance(item["evidence"], list) or not 1 <= len(item["evidence"]) <= 5:
            raise ValueError("Checkpoint items need bounded exact evidence.")
        for evidence in item["evidence"]:
            if not isinstance(evidence, dict) or set(evidence) != evidence_fields:
                raise ValueError("Checkpoint evidence must be normalized source references.")
            if evidence["relationship"] not in {"supports", "contradicts", "context"}:
                raise ValueError("Checkpoint evidence relationship is invalid.")
            excerpt = evidence["excerpt"]
            if (
                not isinstance(excerpt, str)
                or not excerpt
                or not any(
                    p.message_id == evidence["message_id"]
                    and p.message_index == evidence["message_index"]
                    and p.role == evidence["message_role"]
                    and p.timestamp == evidence["message_timestamp"]
                    and excerpt in p.content
                    for p in segment.pieces
                )
            ):
                raise ValueError(
                    "Checkpoint evidence must occur in a source piece actually analyzed."
                )
    if len(_json(value).encode("utf-8")) > MAX_RESULT_BYTES:
        raise ValueError("The normalized chunk exceeds the checkpoint size limit.")
    return value


def _brief_fragments(briefs, budget):
    """Split only normalized Brief fields; every summary string remains represented."""
    fragments = []
    for brief in briefs:
        if len(_json([brief, brief])) <= budget:
            fragments.append(brief)
            continue
        # Text fragments are input summaries, not independently completed Briefs.
        for field in BRIEF_TEXT_FIELDS + BRIEF_LIST_FIELDS:
            entries = [brief[field]] if field in BRIEF_TEXT_FIELDS else brief[field]
            for entry in entries:
                fragment = {field: entry if field in BRIEF_TEXT_FIELDS else [entry]}
                if len(_json([fragment, fragment])) > budget:
                    raise ValueError(
                        "The synthesis budget is too small for a normalized summary field."
                    )
                fragments.append(fragment)
    return fragments


def _synthesis_groups(values, budget):
    groups, current = [], []
    for value in values:
        if current and len(_json([*current, value])) > budget:
            groups.append(current)
            current = []
        current.append(value)
    if current:
        groups.append(current)
    return groups


class ChunkAnalysisRunner:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self._invocation_calls = 0
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS context_chunk_runs (
                    run_key TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    source_fingerprint TEXT NOT NULL,
                    analysis_config_key TEXT NOT NULL,
                    explicit_generation TEXT NOT NULL,
                    total_messages INTEGER NOT NULL,
                    total_characters INTEGER NOT NULL,
                    total_segments INTEGER NOT NULL,
                    provider_calls INTEGER NOT NULL DEFAULT 0,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS context_chunk_checkpoints (
                    run_key TEXT NOT NULL REFERENCES context_chunk_runs(run_key) ON DELETE CASCADE,
                    checkpoint_key TEXT NOT NULL,
                    input_fingerprint TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    covered_characters INTEGER NOT NULL,
                    completed_messages INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(run_key, checkpoint_key)
                );
                CREATE INDEX IF NOT EXISTS idx_context_chunk_source
                    ON context_chunk_runs(source_id, updated_at);
            """)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def coverage(self, run_key):
        with self._connect() as conn:
            run = conn.execute(
                "SELECT * FROM context_chunk_runs WHERE run_key = ?", (run_key,)
            ).fetchone()
            if not run:
                raise LookupError("Analysis checkpoint run not found.")
            chunks, characters, messages = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(covered_characters),0), "
                "COALESCE(SUM(completed_messages),0) FROM context_chunk_checkpoints "
                "WHERE run_key = ? AND stage = 'chunk'",
                (run_key,),
            ).fetchone()
            steps = conn.execute(
                "SELECT COUNT(*) FROM context_chunk_checkpoints "
                "WHERE run_key = ? AND stage = 'synthesis'",
                (run_key,),
            ).fetchone()[0]
        return AnalysisCoverage(
            run_key,
            run["total_messages"],
            run["total_characters"],
            run["total_segments"],
            chunks,
            messages,
            characters,
            steps,
            run["provider_calls"],
            run["state"] == "complete",
            run["state"],
        )

    def progress_for_source(
        self, source_record_id, source_fingerprint, analysis_generation, *, analysis_config_key=None
    ):
        """Read only coverage counters, never deserialize stored analysis content."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT run_key FROM context_chunk_runs WHERE source_id = ? "
                "AND source_fingerprint = ? AND explicit_generation = ? "
                "AND (? IS NULL OR analysis_config_key = ?) "
                "ORDER BY updated_at DESC, run_key DESC LIMIT 1",
                (
                    source_record_id,
                    source_fingerprint,
                    str(analysis_generation),
                    analysis_config_key,
                    analysis_config_key,
                ),
            ).fetchone()
        return self.coverage(row["run_key"]).to_dict() if row else None

    def _state(self, run_key, state):
        with self._connect() as conn:
            conn.execute(
                "UPDATE context_chunk_runs SET state = ?, updated_at = ? WHERE run_key = ?",
                (state, datetime.now(UTC).isoformat(), run_key),
            )

    def _counted_call(self, run_key, call, normalize, invocation_limit, total_limit):
        """Count real sends, including failed keys, without refunding a sent attempt."""
        sent_attempts = 0

        def pause(reason):
            self._state(run_key, reason)
            raise PartialAnalysisError(reason, self.coverage(run_key))

        def reserve():
            nonlocal sent_attempts
            if self._invocation_calls >= invocation_limit:
                pause("invocation_limit")
            with self._connect() as conn:
                reserved = conn.execute(
                    "UPDATE context_chunk_runs SET provider_calls=provider_calls+1, "
                    "state='running',updated_at=? WHERE run_key=? AND provider_calls<?",
                    (datetime.now(UTC).isoformat(), run_key, total_limit),
                ).rowcount
            if not reserved:
                pause("total_call_limit")
            self._invocation_calls += 1
            sent_attempts += 1

        # Legacy synthetic callbacks do not expose a send boundary. Check their slot
        # before calling, then count one attempt unless they report a pre-send denial.
        if self._invocation_calls >= invocation_limit:
            pause("invocation_limit")
        if self.coverage(run_key).provider_calls >= total_limit:
            pause("total_call_limit")
        try:
            with provider_attempt_recording(reserve):
                result = normalize(call())
            if sent_attempts == 0:
                reserve()
            encoded = _json(result)
            if len(encoded.encode("utf-8")) > MAX_RESULT_BYTES:
                raise ValueError("The normalized result exceeds the checkpoint size limit.")
            return result, encoded
        except PartialAnalysisError:
            raise
        except (AnalysisLimitError, ProviderConnectionChangedError) as exc:
            # A later key's guard can fail after an earlier key was sent. Preserve
            # those reservations; an initial pre-send denial has reserved nothing.
            pause("allowance" if isinstance(exc, AnalysisLimitError) else "connection_changed")
        except BaseException:
            if sent_attempts == 0:
                reserve()
            self._state(run_key, "interrupted")
            raise

    def run_followup(
        self,
        *,
        run_key: str,
        input_fingerprint: str,
        call: Callable,
        normalize: Callable,
        max_total_calls: int = 256,
        max_calls_per_invocation: int = 8,
    ):
        """Checkpoint one relationship verification after complete source analysis.

        Callers reserve one invocation slot for this stage. The single fixed key prevents
        a retry from silently comparing a different candidate set in the same generation.
        """
        if (
            not isinstance(input_fingerprint, str)
            or not input_fingerprint
            or len(input_fingerprint) > 256
        ):
            raise ValueError("Follow-up input fingerprint must be a bounded identifier.")
        if type(max_total_calls) is not int or not 1 <= max_total_calls <= 2048:
            raise ValueError("Source call limit must be between 1 and 2048.")
        if type(max_calls_per_invocation) is not int or not 1 <= max_calls_per_invocation <= 64:
            raise ValueError("Invocation call limit must be between 1 and 64.")
        progress = self.coverage(run_key)
        if progress.completed_segments != progress.total_segments:
            raise ValueError("Relationship verification requires complete source coverage.")
        key = "relationships:v1"
        with self._connect() as conn:
            row = conn.execute(
                "SELECT input_fingerprint,result_json FROM context_chunk_checkpoints "
                "WHERE run_key=? AND checkpoint_key=?",
                (run_key, key),
            ).fetchone()
        if row:
            if row["input_fingerprint"] != input_fingerprint:
                raise ValueError(
                    "Relationship candidates changed; start a new analysis generation."
                )
            result = normalize(json.loads(row["result_json"]))
            self._state(run_key, "complete")
            return result
        result, encoded = self._counted_call(
            run_key, call, normalize, max_calls_per_invocation, max_total_calls
        )
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO context_chunk_checkpoints "
                "VALUES (?, ?, ?, 'relationships', ?, 0, 0, ?)",
                (run_key, key, input_fingerprint, encoded, datetime.now(UTC).isoformat()),
            )
        self._state(run_key, "complete")
        return result

    def run(
        self,
        *,
        source_id: str,
        source_fingerprint: str,
        analysis_config_key: str,
        explicit_generation: str | int,
        messages: Sequence[Any],
        max_payload_chars: int,
        call_chunk: Callable,
        normalize_chunk: Callable,
        call_synthesis: Callable,
        normalize_synthesis: Callable,
        max_calls_per_invocation: int = 8,
        max_total_calls: int = 256,
        on_progress: Callable | None = None,
    ) -> ChunkAnalysisResult:
        if any(
            not isinstance(value, str) or not value or len(value) > 256
            for value in (source_id, source_fingerprint, analysis_config_key)
        ):
            raise ValueError("Checkpoint identity fields must be bounded non-secret identifiers.")
        if not isinstance(explicit_generation, (str, int)) or isinstance(explicit_generation, bool):
            raise ValueError("Explicit analysis generation must be an identifier.")
        generation = str(explicit_generation)
        if not generation or len(generation) > 128:
            raise ValueError("Explicit analysis generation must be bounded.")
        if type(max_calls_per_invocation) is not int or not 1 <= max_calls_per_invocation <= 64:
            raise ValueError("Invocation call limit must be between 1 and 64.")
        if type(max_total_calls) is not int or not 1 <= max_total_calls <= 2048:
            raise ValueError("Source call limit must be between 1 and 2048.")
        segments = partition_messages(messages, max_payload_chars=max_payload_chars)
        run_key = _digest(
            [
                CHUNKING_VERSION,
                source_id,
                source_fingerprint,
                analysis_config_key,
                generation,
                max_payload_chars,
                [s.fingerprint for s in segments],
            ]
        )
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO context_chunk_runs "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 'pending', ?, ?)",
                (
                    run_key,
                    source_id,
                    source_fingerprint,
                    analysis_config_key,
                    generation,
                    len(messages),
                    sum(s.covered_characters for s in segments),
                    len(segments),
                    now,
                    now,
                ),
            )
        self._invocation_calls = 0
        message_lengths = {p.message_id: p.end for s in segments for p in s.pieces}

        def progress():
            value = self.coverage(run_key)
            if on_progress:
                on_progress(value)
            return value

        def pause(reason):
            self._state(run_key, reason)
            raise PartialAnalysisError(reason, progress())

        def stage(key, fingerprint, kind, call, normalize, characters=0, completed_messages=0):
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT result_json, input_fingerprint FROM context_chunk_checkpoints "
                    "WHERE run_key = ? AND checkpoint_key = ?",
                    (run_key, key),
                ).fetchone()
            if row:
                if row["input_fingerprint"] != fingerprint:
                    raise ValueError("Analysis checkpoint input no longer matches this run.")
                return json.loads(row["result_json"])
            try:
                normalized, encoded = self._counted_call(
                    run_key, call, normalize, max_calls_per_invocation, max_total_calls
                )
            except BaseException:
                progress()
                raise
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO context_chunk_checkpoints VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        run_key,
                        key,
                        fingerprint,
                        kind,
                        encoded,
                        characters,
                        completed_messages,
                        datetime.now(UTC).isoformat(),
                    ),
                )
            progress()
            return normalized

        progress()
        chunks = []
        for segment in segments:
            value = stage(
                f"chunk:{segment.index}",
                segment.fingerprint,
                "chunk",
                lambda s=segment: call_chunk(s),
                lambda raw, s=segment: _validated_chunk(normalize_chunk(raw, s), s),
                segment.covered_characters,
                sum(p.end == message_lengths[p.message_id] for p in segment.pieces),
            )
            chunks.append(_validated_chunk(value, segment))
        if len(chunks) == 1:
            synthesis = chunks[0]["brief"]
        else:
            values = _brief_fragments([chunk["brief"] for chunk in chunks], max_payload_chars)
            depth = 0
            while len(values) > 1:
                groups = _synthesis_groups(values, max_payload_chars)
                if len(groups) >= len(values):
                    raise ValueError(
                        "The synthesis budget cannot combine two normalized summary fields."
                    )
                next_values = []
                for index, group in enumerate(groups):
                    if len(group) == 1:
                        next_values.append(group[0])
                        continue
                    fingerprint = _digest(group)
                    value = stage(
                        f"synthesis:{depth}:{index}",
                        fingerprint,
                        "synthesis",
                        lambda g=group: call_synthesis(g),
                        lambda raw, g=group: _validated_brief(normalize_synthesis(raw, g)),
                    )
                    next_values.append(_validated_brief(value))
                values = _brief_fragments(next_values, max_payload_chars)
                depth += 1
                if depth > 32:
                    pause("synthesis_limit")
            synthesis = _validated_brief(values[0])
        self._state(run_key, "complete")
        return ChunkAnalysisResult(tuple(chunks), synthesis, progress())


ChunkStore = ChunkAnalysisRunner
ChunkAnalysisPaused = PartialAnalysisError
