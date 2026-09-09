"""Read-only global Context retrieval with scope checks before ranking or expansion."""

from __future__ import annotations

import math
import re
import sqlite3
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from types import SimpleNamespace
from unicodedata import normalize

from reweave.context_library import ContextLibraryStore, ContextScope

RETRIEVAL_POLICY_VERSION = "context-retrieval-v1"
INFERRED_USE_CONFIDENCE = 0.85
SUMMARY_CHARS = 800
SEMANTIC_THRESHOLD = 0.55
TOKEN_PATTERN = re.compile(r"[\w]+(?:[-./:#][\w]+)*", re.UNICODE)
IDENTIFIER_PATTERN = re.compile(r"(?:\w+[-_./:#])+\w+|\b\w*\d\w*\b", re.UNICODE)
STOP_TERMS = {
    "and",
    "are",
    "for",
    "from",
    "has",
    "have",
    "into",
    "its",
    "that",
    "the",
    "their",
    "this",
    "use",
    "user",
    "was",
    "were",
    "with",
    "you",
    "your",
    "please",
    "about",
    "what",
    "would",
    "could",
    "should",
    "explain",
    "tell",
}
DESTINATION_SCOPE_TYPES = {
    "private": {"core_self", "personal", "work", "project", "topic", "destination"},
    "work": {"core_self", "work", "project", "topic", "destination"},
    "client": {"core_self", "project", "topic", "destination"},
    "shared": {"core_self", "project", "topic", "destination"},
    "unknown": {"core_self", "project", "topic", "destination"},
}
GRAPH_RELATIONSHIPS = {"supports", "related", "expands", "shared_evidence"}
_MODEL_CACHE: dict[str, object] = {}
_MODEL_LOCK = Lock()


@dataclass(frozen=True)
class RetrievalHit:
    item_id: str
    summary: str
    item_type: str
    epistemic_kind: str
    confidence: float
    current_version: int
    score: float
    reasons: tuple[str, ...]
    matched_terms: tuple[str, ...] = ()
    exact_identifiers: tuple[str, ...] = ()
    via_item_id: str | None = None


@dataclass(frozen=True)
class RetrievalDiagnostics:
    policy_version: str
    strategy: str
    allowed_candidates: int
    excluded_candidates: int
    stages: tuple[str, ...]
    fallback_used: bool
    semantic_available: bool
    semantic_status: str


@dataclass(frozen=True)
class ContextRetrievalResult:
    hits: tuple[RetrievalHit, ...]
    diagnostics: RetrievalDiagnostics


@dataclass(frozen=True)
class RetrievalEvidence:
    source_provider: str
    source_title: str
    source_message_index: int
    source_changed: bool


@dataclass(frozen=True)
class RetrievedContextItem:
    id: str
    canonical_text: str
    item_type: str
    epistemic_kind: str
    confidence: float
    current_version: int
    scopes: tuple[ContextScope, ...]
    evidence: tuple[RetrievalEvidence, ...]


@dataclass(frozen=True)
class DestinationInference:
    destination: str
    allowed_scopes: tuple[tuple[str, str], ...]
    suggested_scopes: tuple[tuple[str, str], ...]
    confidence: float
    needs_confirmation: bool
    reasons: tuple[str, ...]
    suggested_destination: str | None = None


def terms(value: str) -> tuple[str, ...]:
    return tuple(
        term
        for match in TOKEN_PATTERN.finditer(value.casefold())
        if len(term := match.group()) >= 2 and term not in STOP_TERMS
    )


def _key(value: str) -> str:
    return " ".join(normalize("NFKC", value).casefold().split())


def _identifiers(query: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(match.group() for match in IDENTIFIER_PATTERN.finditer(query)))[:20]


def _exact_identifier(identifier: str, text: str) -> bool:
    return re.search(r"(?<![\w./:#-])" + re.escape(identifier) + r"(?![\w./:#-])", text) is not None


def scope_is_allowed(
    *,
    sensitivity: str,
    status: str,
    epistemic_kind: str,
    confidence: float,
    scopes: tuple[ContextScope, ...],
    destination: str,
    allowed_scopes: set[tuple[str, str]],
) -> bool:
    """All protective routes must be authorized; a matching project cannot mask Personal."""
    safe_types = DESTINATION_SCOPE_TYPES.get(destination, set())
    if status != "active" or sensitivity != "normal" or confidence <= 0:
        return False
    if epistemic_kind not in {"observed", "inferred", "suggested"}:
        return False
    if epistemic_kind == "inferred" and confidence < INFERRED_USE_CONFIDENCE:
        return False
    if not scopes or any(
        scope.confidence <= 0 or scope.scope_type not in safe_types for scope in scopes
    ):
        return False
    if destination == "private" and not allowed_scopes:
        return True
    if not allowed_scopes:
        return False
    if any(scope.confidence < INFERRED_USE_CONFIDENCE for scope in scopes):
        return False
    allowed = {(kind, _key(key)) for kind, key in allowed_scopes}
    scope_pairs = {(scope.scope_type, _key(scope.scope_key)) for scope in scopes}
    protective = {pair for pair in scope_pairs if pair[0] != "topic"}
    return protective.issubset(allowed) and bool(scope_pairs.intersection(allowed))


def local_context_embedder(models_dir: Path | None) -> object | None:
    """Use existing local model files only; retrieval never downloads an embedding model."""
    if models_dir is None or not models_dir.is_dir() or not any(models_dir.rglob("*.onnx")):
        return None
    cache_key = str(models_dir.resolve())
    with _MODEL_LOCK:
        if cache_key in _MODEL_CACHE:
            return _MODEL_CACHE[cache_key]
        from fastembed import TextEmbedding

        from reweave.semantic import MODEL_ID

        model = TextEmbedding(
            model_name=MODEL_ID,
            cache_dir=cache_key,
            local_files_only=True,
            threads=1,
            providers=["CPUExecutionProvider"],
            cuda=False,
        )
        _MODEL_CACHE[cache_key] = model
        return model


class ContextRetriever:
    """Query current summaries globally, expanding only within the same permission predicate."""

    def __init__(
        self, store: ContextLibraryStore, *, embedder=None, models_dir: Path | None = None
    ):
        self.store = store
        self.embedder = embedder
        self.models_dir = models_dir
        self._vector_cache: dict[tuple[str, int], tuple[float, ...]] = {}

    def clear_cache(self) -> None:
        """Invalidate vectors after restore, which can reuse IDs and versions for different text."""
        self._vector_cache.clear()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.store.db_path.resolve().as_uri() + "?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        from reweave.context_review import ContextReviewStore, effective_confidence

        now = datetime.now(UTC)
        conn.create_function(
            "context_effective_confidence",
            5,
            lambda confidence, confirmed, updated, created, stale: effective_confidence(
                SimpleNamespace(
                    confidence=confidence,
                    last_confirmed_at=confirmed,
                    updated_at=updated,
                    created_at=created,
                    stale_at=stale,
                ),
                now=now,
            ),
        )
        conn.create_function(
            "context_link_review_key",
            5,
            lambda first_id, first_version, second_id, second_version, relationship: (
                ContextReviewStore._link_key(
                    SimpleNamespace(id=first_id, current_version=first_version),
                    SimpleNamespace(id=second_id, current_version=second_version),
                    relationship,
                )
            ),
        )
        try:
            yield conn
        finally:
            conn.close()

    def canonical_allowed_scopes(self, scopes: set[tuple[str, str]]) -> set[tuple[str, str]]:
        with self._connect() as conn:
            return self._canonical_scopes(conn, scopes)

    def _canonical_scopes(self, conn, scopes):
        result = set()
        for kind, key in scopes:
            row = conn.execute(
                "SELECT s.name FROM context_space_aliases a "
                "JOIN context_spaces s ON s.id = a.space_id "
                "WHERE a.scope_type = ? AND a.alias_key = ?",
                (kind, _key(key)),
            ).fetchone()
            result.add((kind, row[0] if row and key else key))
        return result

    def _policy(
        self,
        destination,
        scopes,
        for_external_use=True,
        *,
        sensitive_versions=None,
        sensitive_preview=False,
        connection=None,
    ):
        if not for_external_use:
            return "1", []
        safe_types = DESTINATION_SCOPE_TYPES.get(destination, set())
        if not safe_types or (destination != "private" and not scopes):
            return "0", []
        approved = sorted((sensitive_versions or {}).items())
        consent_clause = " OR ".join("(i.id = ? AND i.current_version = ?)" for _ in approved)
        consent_clause = consent_clause or "0"
        consent_params = [value for pair in approved for value in pair]
        sensitivity = (
            "i.sensitivity = 'sensitive'"
            if sensitive_preview
            else "(i.sensitivity = 'normal' OR (i.sensitivity = 'sensitive' AND ("
            + consent_clause
            + ")))"
        )
        confidence = (
            "1"
            if sensitive_preview
            else "(i.epistemic_kind <> 'inferred' OR context_effective_confidence("
            "i.confidence, i.last_confirmed_at, i.updated_at, i.created_at, i.stale_at) >= ? OR "
            "(i.sensitivity = 'sensitive' AND (" + consent_clause + ")))"
        )
        params: list[object] = (
            []
            if sensitive_preview
            else [
                *consent_params,
                INFERRED_USE_CONFIDENCE,
                *consent_params,
            ]
        )
        preferred = "0"
        if (
            connection is not None
            and connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='context_review_events'"
            ).fetchone()
        ):
            preferred = (
                "COALESCE((SELECT CASE WHEN "
                "(r.resolution='prefer_this' AND r.item_id=i.id) OR "
                "(r.resolution='prefer_other' AND r.related_item_id=i.id) THEN 1 ELSE 0 END "
                "FROM context_review_events r WHERE r.action='resolve_link' "
                "AND r.undone_at IS NULL AND r.review_key=context_link_review_key("
                "i.id,i.current_version,disputed.id,disputed.current_version,l.relationship) "
                "ORDER BY r.created_at DESC LIMIT 1),0)"
            )
        predicates = [
            "i.status = 'active'",
            sensitivity,
            "i.confidence > 0",
            "i.epistemic_kind IN ('observed', 'inferred', 'suggested')",
            confidence,
            "EXISTS (SELECT 1 FROM context_evidence e WHERE e.item_id = i.id)",
            "EXISTS (SELECT 1 FROM context_item_scopes s WHERE s.item_id = i.id)",
            "NOT EXISTS (SELECT 1 FROM context_item_links l "
            "JOIN context_items disputed ON disputed.id = CASE WHEN l.source_item_id = i.id "
            "THEN l.target_item_id ELSE l.source_item_id END "
            "WHERE (l.source_item_id = i.id OR l.target_item_id = i.id) "
            "AND (l.relationship IN ('contradicts', 'contradiction', 'conflicts_with', 'conflict', "
            "'possible_contradiction') "
            "OR (l.relationship='source_update' AND (i.item_type='decision' "
            "OR disputed.item_type='decision') AND i.canonical_text<>disputed.canonical_text)) "
            "AND disputed.status = 'active' AND " + preferred + " <> 1)",
        ]
        types = sorted(safe_types)
        predicates.append(
            "NOT EXISTS (SELECT 1 FROM context_item_scopes s WHERE s.item_id = i.id "
            "AND (s.confidence <= 0 OR s.scope_type NOT IN (" + ",".join("?" for _ in types) + ")))"
        )
        params.extend(types)
        if destination == "private" and not scopes:
            return " AND ".join(predicates), params
        predicates.append(
            "NOT EXISTS (SELECT 1 FROM context_item_scopes s "
            "WHERE s.item_id = i.id AND s.confidence < ?)"
        )
        params.append(INFERRED_USE_CONFIDENCE)
        pairs = sorted(scopes)
        authorized = " OR ".join("(s.scope_type = ? AND s.scope_key = ?)" for _ in pairs)
        pair_params = [value for pair in pairs for value in pair]
        predicates.append(
            "EXISTS (SELECT 1 FROM context_item_scopes s WHERE s.item_id = i.id AND ("
            + authorized
            + "))"
        )
        params.extend(pair_params)
        predicates.append(
            "NOT EXISTS (SELECT 1 FROM context_item_scopes s WHERE s.item_id = i.id "
            "AND s.scope_type <> 'topic' AND NOT (" + authorized + "))"
        )
        params.extend(pair_params)
        return " AND ".join(predicates), params

    def retrieve(
        self,
        *,
        query: str,
        destination: str,
        allowed_scopes: set[tuple[str, str]],
        query_weights: Counter[str] | None = None,
        excluded_ids: set[str] | None = None,
        limit: int = 32,
        for_external_use: bool = True,
        sensitive_versions: dict[str, int] | None = None,
        sensitive_preview: bool = False,
        space_id: str | None = None,
        item_type: str | None = None,
    ) -> ContextRetrievalResult:
        weights = query_weights or Counter(terms(query))
        # The query stays in memory and bound SQL arguments only.
        weights = Counter(dict(weights.most_common(80)))
        identifiers = _identifiers(query)
        limit = min(max(limit, 1), 100)
        excluded = {value.casefold() for value in (excluded_ids or set())}
        stages = ["scope_filter", "compact_global_keyword"]
        semantic_status = "not_loaded"
        semantic_available = False
        with self._connect() as conn:
            scopes = self._canonical_scopes(conn, allowed_scopes)
            predicate, params = self._policy(
                destination,
                scopes,
                for_external_use,
                sensitive_versions=sensitive_versions,
                sensitive_preview=sensitive_preview,
                connection=conn,
            )
            if space_id:
                predicate += " AND EXISTS (SELECT 1 FROM context_item_scopes filter_scope "
                predicate += "WHERE filter_scope.item_id = i.id AND filter_scope.space_id = ?)"
                params.append(space_id)
            if item_type:
                predicate += " AND i.item_type = ?"
                params.append(item_type)
            total = conn.execute("SELECT COUNT(*) FROM context_items").fetchone()[0]
            allowed = conn.execute(
                "SELECT COUNT(*) FROM context_items i WHERE " + predicate, params
            ).fetchone()[0]
            if excluded:
                conn.create_function(
                    "context_excluded", 1, lambda value: value.casefold() in excluded
                )
                predicate += " AND context_excluded(i.id) = 0"
            features: dict[str, tuple[float, tuple[str, ...], tuple[str, ...]]] = {}

            def lexical(item_id, text, scope_keys):
                counts = Counter(terms(text))
                scope_terms = set(terms(scope_keys or ""))
                for term in weights:
                    if re.search(r"[가-힣ぁ-んァ-ン一-龯]", term) and term in text.casefold():
                        counts[term] = max(counts[term], text.casefold().count(term))
                matched = tuple(sorted(set(counts).intersection(weights)))
                exact = tuple(
                    identifier for identifier in identifiers if _exact_identifier(identifier, text)
                )
                overlap = sum(weights[term] * min(counts[term], 2) for term in matched)
                route_bonus = sum(weights[term] * 0.4 for term in scope_terms.intersection(weights))
                score = float(overlap) + route_bonus + len(exact) * 30
                features[item_id] = (score, matched, exact)
                return score

            conn.create_function("context_lexical", 3, lexical)
            rows = self._keyword_rows(conn, predicate, params, SUMMARY_CHARS, limit * 4)
            ranked = self._hits(rows, features, excluded, "Keyword match in current context")
            top_coverage = len(ranked[0].matched_terms) / max(1, len(weights)) if ranked else 0
            fallback = len(ranked) < 3 or top_coverage < 0.4 or bool(identifiers)
            if fallback:
                stages.append("full_allowed_library_fallback")
                rows = self._keyword_rows(conn, predicate, params, 12_000, limit * 4)
                ranked = self._hits(rows, features, excluded, "Global full-text match")
            try:
                model = self.embedder or local_context_embedder(self.models_dir)
                if model is not None:
                    semantic_available = True
                    semantic_status = "ready"
                    stages.append("local_semantic")
                    ranked = self._semantic_hits(
                        conn, predicate, params, query, model, ranked, excluded
                    )
            except Exception:
                # Local cache/model failures cannot trigger a download or discard keyword results.
                semantic_status = "unavailable"
                semantic_available = False
            ranked.sort(key=lambda hit: (-hit.score, -hit.confidence, hit.item_id))
            if ranked:
                stages.append("allowed_graph_expansion")
                ranked = self._expand_graph(conn, predicate, params, ranked, excluded, features)
            ranked.sort(key=lambda hit: (-hit.score, -hit.confidence, hit.item_id))
            return ContextRetrievalResult(
                hits=tuple(ranked[:limit]),
                diagnostics=RetrievalDiagnostics(
                    policy_version=RETRIEVAL_POLICY_VERSION
                    + ("" if for_external_use else ":local"),
                    strategy="hybrid_local" if semantic_available else "global_keyword",
                    allowed_candidates=allowed,
                    excluded_candidates=total - allowed,
                    stages=tuple(stages),
                    fallback_used=fallback,
                    semantic_available=semantic_available,
                    semantic_status=semantic_status,
                ),
            )

    def search_library(
        self,
        query: str,
        *,
        limit: int = 50,
        space_id: str | None = None,
        item_type: str | None = None,
    ) -> ContextRetrievalResult:
        """Local browsing includes sensitive and uncertain context; it grants no Use permission."""
        return self.retrieve(
            query=query,
            destination="private",
            allowed_scopes=set(),
            limit=limit,
            for_external_use=False,
            space_id=space_id,
            item_type=item_type,
        )

    def _keyword_rows(self, conn, predicate, params, chars, limit):
        return conn.execute(
            "SELECT i.id, substr(i.canonical_text, 1, ?) AS summary, i.item_type, "
            "i.epistemic_kind, i.confidence, i.current_version, "
            "context_lexical(i.id, substr(i.canonical_text, 1, ?), "
            "(SELECT group_concat(s.scope_key, ' ') FROM context_item_scopes s "
            "WHERE s.item_id = i.id)) AS lexical_score "
            "FROM context_items i WHERE " + predicate + " ORDER BY lexical_score DESC, "
            "i.confidence DESC, i.id LIMIT ?",
            [SUMMARY_CHARS, chars, *params, limit],
        ).fetchall()

    def _hits(self, rows, features, excluded, reason):
        result = []
        for row in rows:
            if row["id"].casefold() in excluded:
                continue
            score, matched, exact = features.get(row["id"], (0, (), ()))
            if not matched and not exact:
                # A route name alone is not evidence that this particular item is useful.
                continue
            score += float(row["confidence"]) * 0.5
            score += {"observed": 0.3, "inferred": 0.15, "suggested": 0}.get(
                row["epistemic_kind"], 0
            )
            result.append(
                self._hit(
                    row, score, ("Exact identifier match" if exact else reason,), matched, exact
                )
            )
        return result

    @staticmethod
    def _hit(row, score, reasons, matched=(), exact=(), via=None):
        return RetrievalHit(
            item_id=row["id"],
            summary=row["summary"],
            item_type=row["item_type"],
            epistemic_kind=row["epistemic_kind"],
            confidence=float(row["confidence"]),
            current_version=row["current_version"],
            score=round(float(score), 6),
            reasons=reasons,
            matched_terms=matched,
            exact_identifiers=exact,
            via_item_id=via,
        )

    def _semantic_hits(self, conn, predicate, params, query, model, ranked, excluded):
        query_vector = _unit_vector(next(iter(model.embed([query]))))
        if not query_vector:
            return ranked
        by_id = {hit.item_id: hit for hit in ranked}
        cursor = conn.execute(
            "SELECT i.id, substr(i.canonical_text, 1, ?) AS summary, i.item_type, "
            "i.epistemic_kind, i.confidence, i.current_version FROM context_items i WHERE "
            + predicate
            + " ORDER BY i.id",
            [SUMMARY_CHARS, *params],
        )
        while rows := cursor.fetchmany(32):
            rows = [row for row in rows if row["id"].casefold() not in excluded]
            pending = [
                row for row in rows if (row["id"], row["current_version"]) not in self._vector_cache
            ]
            if pending:
                vectors = list(model.embed([row["summary"] for row in pending]))
                for row, vector in zip(pending, vectors, strict=True):
                    self._vector_cache[(row["id"], row["current_version"])] = _unit_vector(vector)
            for row in rows:
                vector = self._vector_cache[(row["id"], row["current_version"])]
                if len(vector) != len(query_vector):
                    continue
                similarity = sum(
                    left * right for left, right in zip(vector, query_vector, strict=True)
                )
                if not math.isfinite(similarity) or similarity < SEMANTIC_THRESHOLD:
                    continue
                existing = by_id.get(row["id"])
                semantic_score = similarity * 8
                by_id[row["id"]] = self._hit(
                    row,
                    (existing.score if existing else 0) + semantic_score,
                    (*existing.reasons, "Similar meaning in local model")
                    if existing
                    else ("Similar meaning in local model",),
                    existing.matched_terms if existing else (),
                    existing.exact_identifiers if existing else (),
                )
        if len(self._vector_cache) > 5000:
            self._vector_cache.clear()
        return list(by_id.values())

    def _expand_graph(self, conn, predicate, params, ranked, excluded, features):
        by_id = {hit.item_id: hit for hit in ranked}
        for seed in ranked[:8]:
            rows = conn.execute(
                "SELECT DISTINCT i.id, substr(i.canonical_text, 1, ?) AS summary, "
                "i.item_type, i.epistemic_kind, i.confidence, i.current_version, l.relationship "
                "FROM context_item_links l JOIN context_items i ON "
                "i.id = CASE WHEN l.source_item_id = ? THEN l.target_item_id "
                "ELSE l.source_item_id END "
                "WHERE (l.source_item_id = ? OR l.target_item_id = ?) AND (" + predicate + ") "
                "ORDER BY i.id LIMIT 24",
                [SUMMARY_CHARS, seed.item_id, seed.item_id, seed.item_id, *params],
            ).fetchall()
            for row in rows:
                if row["id"].casefold() in excluded or row["id"] in by_id:
                    continue
                if row["relationship"] not in GRAPH_RELATIONSHIPS:
                    continue
                _, matched, exact = features.get(row["id"], (0, (), ()))
                if row["relationship"] == "shared_evidence" and not matched:
                    continue
                by_id[row["id"]] = self._hit(
                    row,
                    seed.score * 0.35 * float(row["confidence"]),
                    ("Linked context: " + row["relationship"],),
                    matched,
                    exact,
                    seed.item_id,
                )
        return list(by_id.values())

    def load_item(
        self,
        hit: RetrievalHit,
        *,
        destination: str,
        allowed_scopes: set[tuple[str, str]],
        sensitive_versions: dict[str, int] | None = None,
    ) -> RetrievedContextItem | None:
        """Recheck scope and version, then load only current text and one provenance record."""
        with self._connect() as conn:
            scopes = self._canonical_scopes(conn, allowed_scopes)
            predicate, params = self._policy(
                destination,
                scopes,
                sensitive_versions=sensitive_versions,
                connection=conn,
            )
            row = conn.execute(
                "SELECT i.* FROM context_items i WHERE i.id = ? AND i.current_version = ? AND "
                + predicate,
                [hit.item_id, hit.current_version, *params],
            ).fetchone()
            if row is None:
                return None
            item_scopes = tuple(
                ContextScope(**dict(scope))
                for scope in conn.execute(
                    "SELECT * FROM context_item_scopes WHERE item_id = ? "
                    "ORDER BY scope_type, scope_key",
                    (hit.item_id,),
                )
            )
            evidence = conn.execute(
                "SELECT e.source_provider, e.source_title, e.source_message_index, "
                "CASE WHEN m.content IS NOT NULL AND instr(m.content, e.excerpt) = 0 "
                "THEN 1 ELSE 0 END AS source_changed FROM context_evidence e "
                "LEFT JOIN messages m ON m.id = e.source_message_id "
                "WHERE e.item_id = ? ORDER BY source_changed, e.created_at DESC, e.id LIMIT 1",
                (hit.item_id,),
            ).fetchone()
            if evidence is None:
                return None
            return RetrievedContextItem(
                id=row["id"],
                canonical_text=row["canonical_text"],
                item_type=row["item_type"],
                epistemic_kind=row["epistemic_kind"],
                confidence=float(row["confidence"]),
                current_version=row["current_version"],
                scopes=item_scopes,
                evidence=(
                    RetrievalEvidence(
                        evidence["source_provider"],
                        evidence["source_title"],
                        evidence["source_message_index"],
                        bool(evidence["source_changed"]),
                    ),
                ),
            )

    def infer_destination(
        self,
        *,
        provider: str,
        external_id: str,
        query: str = "",
        declared_destination: str | None = None,
        explicit_scopes: set[tuple[str, str]] | None = None,
    ) -> DestinationInference:
        """Suggest known routes; matching names never grant external-use rights."""
        explicit = explicit_scopes or set()
        declared = (
            declared_destination if declared_destination in DESTINATION_SCOPE_TYPES else "unknown"
        )
        with self._connect() as conn:
            authorized = self._canonical_scopes(conn, explicit)
            known = {
                (row[0], row[1])
                for row in conn.execute(
                    "SELECT DISTINCT s.scope_type, s.scope_key FROM context_item_scopes s "
                    "JOIN context_evidence e ON e.item_id = s.item_id "
                    "WHERE e.source_provider = ? AND e.source_external_id = ?",
                    (provider, external_id),
                )
            }
            query_names = {_key(query)}
            for row in conn.execute(
                "SELECT a.alias, s.scope_type, s.name FROM context_space_aliases a "
                "JOIN context_spaces s ON s.id = a.space_id "
                "WHERE s.scope_type IN ('project', 'topic')"
            ):
                if len(row[0]) >= 3 and any(
                    re.search(r"(?<!\w)" + re.escape(_key(row[0])) + r"(?!\w)", text)
                    for text in query_names
                ):
                    known.add((row[1], row[2]))
        safe_types = DESTINATION_SCOPE_TYPES[declared]
        invalid_explicit = any(kind not in safe_types for kind, _ in authorized)
        confirmed = declared == "private" or bool(authorized)
        if invalid_explicit:
            declared, authorized, confirmed = "unknown", set(), False
        return DestinationInference(
            destination=declared,
            allowed_scopes=tuple(sorted(authorized)),
            suggested_scopes=tuple(sorted(known)),
            confidence=1.0 if confirmed else 0.0,
            needs_confirmation=not confirmed,
            reasons=(
                "Explicit destination boundary"
                if confirmed
                else "Destination permissions are unknown; local matches are suggestions only",
            ),
            suggested_destination=(
                "work"
                if any(kind == "work" for kind, _ in known)
                and not any(kind == "personal" for kind, _ in known)
                else "private"
                if any(kind == "personal" for kind, _ in known)
                and not any(kind == "work" for kind, _ in known)
                else None
            ),
        )


def _unit_vector(vector) -> tuple[float, ...]:
    result = tuple(float(value) for value in vector)
    norm = math.sqrt(sum(value * value for value in result))
    if not norm or not math.isfinite(norm):
        return ()
    return tuple(value / norm for value in result)
