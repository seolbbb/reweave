"""Stage 2: Extraction agent — extract structured knowledge from segments."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import perf_counter

from pydantic import BaseModel, Field, ValidationError
from rich.console import Console

from sbs.config import Config
from sbs.llm.client import LLMClient
from sbs.llm.prompts import EXTRACTION_SYSTEM, EXTRACTION_USER, get_prompt
from sbs.models.extraction import (
    ConceptItem,
    DecisionItem,
    ExtractedKnowledge,
    InsightItem,
    OpenQuestion,
    ReferenceItem,
    TodoItem,
)
from sbs.models.segment import Segment
from sbs.pipeline.progress import StageProgress

console = Console()

# Minimum messages for extraction to be worthwhile
MIN_MESSAGES = 3

EXTRACTION_MAX_TOKENS = 4096

# ---------------------------------------------------------------------------
# Batch schemas
# ---------------------------------------------------------------------------

EXTRACTION_BATCH_SYSTEM = """\
You are a knowledge extraction specialist. For each segment in the input batch, \
extract structured knowledge independently.

For each segment item:
- segment_id: the exact input segment id
- concepts: Key concepts discussed (name + description + importance 1-5)
- decisions: Decisions or conclusions reached (decision + rationale)
- insights: Notable insights or learnings (insight + context)
- todos: Action items mentioned (task + status)
- open_questions: Unresolved questions (question + context)
- references: External resources mentioned (title + author + year + source_type + mention_context)
- summary: A 1-2 sentence summary of the segment

Rules:
- Extract from each segment independently.
- Return exactly one item per input segment_id.
- Be thorough but precise. Only extract what is actually discussed."""

EXTRACTION_BATCH_USER = """\
Extract structured knowledge from each segment in this batch:

{batch_payload}"""


class ExtractionResult(BaseModel):
    """LLM output schema for knowledge extraction."""

    concepts: list[ConceptItem] = Field(default_factory=list)
    decisions: list[DecisionItem] = Field(default_factory=list)
    insights: list[InsightItem] = Field(default_factory=list)
    todos: list[TodoItem] = Field(default_factory=list)
    open_questions: list[OpenQuestion] = Field(default_factory=list)
    references: list[ReferenceItem] = Field(default_factory=list)
    summary: str = ""


class BatchExtractionItem(BaseModel):
    """One segment's extraction result in a batch response."""

    segment_id: str
    concepts: list[ConceptItem] = Field(default_factory=list)
    decisions: list[DecisionItem] = Field(default_factory=list)
    insights: list[InsightItem] = Field(default_factory=list)
    todos: list[TodoItem] = Field(default_factory=list)
    open_questions: list[OpenQuestion] = Field(default_factory=list)
    references: list[ReferenceItem] = Field(default_factory=list)
    summary: str = ""


class BatchExtractionResult(BaseModel):
    """LLM output for batched extraction."""

    items: list[BatchExtractionItem] = Field(default_factory=list)


@dataclass
class _PackedBatch:
    segments: list[Segment]
    estimated_tokens: int


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def extract_knowledge(
    segments: list[Segment],
    llm: LLMClient,
    config: Config,
    progress: StageProgress | None = None,
) -> list[ExtractedKnowledge]:
    """Extract structured knowledge from all segments."""
    if config.stage2_batch_enabled:
        return await _extract_in_micro_batches(segments, llm, config, progress)
    return await _extract_individually(segments, llm, config, progress)


# ---------------------------------------------------------------------------
# Individual extraction (default)
# ---------------------------------------------------------------------------


async def _extract_individually(
    segments: list[Segment],
    llm: LLMClient,
    config: Config,
    progress: StageProgress | None = None,
) -> list[ExtractedKnowledge]:
    """Extract knowledge with one LLM call per segment."""
    concurrency = config.resolve_stage2_concurrency()
    semaphore = asyncio.Semaphore(concurrency)

    async def process_one(seg: Segment) -> ExtractedKnowledge | None:
        async with semaphore:
            result = await _extract_single(seg, llm, config)
            if progress is not None:
                progress.advance(1)
            return result

    tasks = [process_one(seg) for seg in segments]
    results = await asyncio.gather(*tasks)
    return [r for r in results if r is not None]


async def _extract_single(
    segment: Segment,
    llm: LLMClient,
    config: Config | None = None,
) -> ExtractedKnowledge | None:
    """Extract knowledge from a single segment."""
    if len(segment.messages) < MIN_MESSAGES:
        return None

    messages_text = "\n".join(
        f"{msg.role}: {msg.content}" for msg in segment.messages
    )

    system = get_prompt("EXTRACTION_SYSTEM", EXTRACTION_SYSTEM).format(
        topic_label=segment.topic_label
    )
    user = get_prompt("EXTRACTION_USER", EXTRACTION_USER).format(
        topic_label=segment.topic_label, messages=messages_text
    )

    started = perf_counter()
    result, usage = await llm.main_structured_call(
        system=system,
        user=user,
        schema=ExtractionResult,
    )
    elapsed = perf_counter() - started

    if config is not None and config.verbose:
        console.print(
            f"  [dim]extract seg={segment.id[:12]}... "
            f"in={usage.input_tokens} out={usage.output_tokens} "
            f"({elapsed:.1f}s)[/dim]"
        )

    return ExtractedKnowledge(
        segment_id=segment.id,
        conversation_id=segment.conversation_id,
        topic_label=segment.topic_label,
        concepts=result.concepts,
        decisions=result.decisions,
        insights=result.insights,
        todos=result.todos,
        open_questions=result.open_questions,
        references=result.references,
        summary=result.summary,
    )


# ---------------------------------------------------------------------------
# Micro-batch extraction
# ---------------------------------------------------------------------------


async def _extract_in_micro_batches(
    segments: list[Segment],
    llm: LLMClient,
    config: Config,
    progress: StageProgress | None = None,
) -> list[ExtractedKnowledge]:
    """Extract knowledge using token-budget micro-batching."""
    # Filter out too-short segments upfront
    extractable = [s for s in segments if len(s.messages) >= MIN_MESSAGES]
    skipped_count = len(segments) - len(extractable)

    if progress is not None and skipped_count > 0:
        progress.advance(skipped_count)

    if not extractable:
        return []

    batches = _pack_micro_batches(
        extractable,
        max_items=config.stage2_batch_max_items,
        token_budget=config.stage2_batch_input_token_budget,
    )
    concurrency = config.resolve_stage2_concurrency()
    semaphore = asyncio.Semaphore(concurrency)
    lock = asyncio.Lock()
    all_results: list[ExtractedKnowledge] = []

    async def process_batch(batch: list[Segment]) -> None:
        async with semaphore:
            mapped = await _extract_batch_with_split_retry(batch, llm, config)

        async with lock:
            all_results.extend(mapped)
            if progress is not None:
                progress.advance(len(batch))

    await asyncio.gather(*(process_batch(batch) for batch in batches))
    return all_results


async def _extract_batch_with_split_retry(
    segments: list[Segment],
    llm: LLMClient,
    config: Config,
    remaining_splits: int = 3,
) -> list[ExtractedKnowledge]:
    """Extract a micro-batch, recursively splitting on recoverable failures."""
    try:
        return await _extract_batch(segments, llm, config)
    except Exception as exc:
        if len(segments) == 1:
            result = await _extract_single(segments[0], llm, config)
            return [result] if result is not None else []

        if not _is_recoverable_extraction_error(exc):
            raise

        if remaining_splits <= 0:
            results = []
            for seg in segments:
                r = await _extract_single(seg, llm, config)
                if r is not None:
                    results.append(r)
            return results

        midpoint = len(segments) // 2
        left = await _extract_batch_with_split_retry(
            segments[:midpoint], llm, config, remaining_splits - 1
        )
        right = await _extract_batch_with_split_retry(
            segments[midpoint:], llm, config, remaining_splits - 1
        )
        return left + right


async def _extract_batch(
    segments: list[Segment],
    llm: LLMClient,
    config: Config,
) -> list[ExtractedKnowledge]:
    """Extract knowledge from multiple segments in one LLM call."""
    payload = _format_batch_payload(segments)
    system = get_prompt("EXTRACTION_BATCH_SYSTEM", EXTRACTION_BATCH_SYSTEM)
    user = get_prompt("EXTRACTION_BATCH_USER", EXTRACTION_BATCH_USER).format(
        batch_payload=payload
    )

    started = perf_counter()
    result, usage = await llm.main_structured_call(
        system=system,
        user=user,
        schema=BatchExtractionResult,
        max_tokens=EXTRACTION_MAX_TOKENS * min(len(segments), 4),
    )
    elapsed = perf_counter() - started

    if config.verbose:
        console.print(
            f"  [dim]extract batch size={len(segments)} "
            f"in={usage.input_tokens} out={usage.output_tokens} "
            f"({elapsed:.1f}s)[/dim]"
        )

    return _map_batch_result(segments, result)


def _map_batch_result(
    segments: list[Segment],
    result: BatchExtractionResult,
) -> list[ExtractedKnowledge]:
    """Validate and map batch response items to ExtractedKnowledge."""
    by_id = {seg.id: seg for seg in segments}
    expected_ids = set(by_id)
    mapped: dict[str, ExtractedKnowledge] = {}

    for item in result.items:
        seg_id = item.segment_id.strip()
        if not seg_id or seg_id not in by_id:
            raise ValueError(
                f"Extraction batch response has unknown segment_id: {seg_id}"
            )
        if seg_id in mapped:
            raise ValueError(
                f"Extraction batch response has duplicate segment_id: {seg_id}"
            )

        seg = by_id[seg_id]
        mapped[seg_id] = ExtractedKnowledge(
            segment_id=seg.id,
            conversation_id=seg.conversation_id,
            topic_label=seg.topic_label,
            concepts=item.concepts,
            decisions=item.decisions,
            insights=item.insights,
            todos=item.todos,
            open_questions=item.open_questions,
            references=item.references,
            summary=item.summary,
        )

    missing = expected_ids - set(mapped)
    if missing:
        missing_ids = ", ".join(sorted(missing))
        raise ValueError(
            f"Extraction batch response missing segments: {missing_ids}"
        )

    # Preserve input order
    return [mapped[seg.id] for seg in segments]


# ---------------------------------------------------------------------------
# Bin-packing & utilities
# ---------------------------------------------------------------------------


def _pack_micro_batches(
    segments: list[Segment],
    max_items: int,
    token_budget: int,
) -> list[list[Segment]]:
    """Pack segments into token-budget micro-batches (first-fit decreasing)."""
    ranked = [
        (seg, _estimate_segment_tokens(seg), idx)
        for idx, seg in enumerate(segments)
    ]
    ranked.sort(key=lambda item: (-item[1], item[2]))

    packed: list[_PackedBatch] = []
    for seg, estimated_tokens, _original_idx in ranked:
        placed = False
        for batch in packed:
            if len(batch.segments) >= max_items:
                continue
            if batch.estimated_tokens + estimated_tokens > token_budget:
                continue
            batch.segments.append(seg)
            batch.estimated_tokens += estimated_tokens
            placed = True
            break

        if not placed:
            packed.append(
                _PackedBatch(segments=[seg], estimated_tokens=estimated_tokens)
            )

    return [batch.segments for batch in packed]


def _estimate_segment_tokens(seg: Segment) -> int:
    """Estimate prompt tokens for a segment."""
    text = "\n".join(f"{m.role}: {m.content}" for m in seg.messages)
    return max(1, (len(text) + 3) // 4)


def _format_batch_payload(segments: list[Segment]) -> str:
    """Render micro-batch payload with explicit segment boundaries."""
    blocks: list[str] = []
    for seg in segments:
        blocks.append(f"Segment ID: {seg.id}")
        blocks.append(f"Topic: {seg.topic_label}")
        blocks.append("Messages:")
        blocks.append(
            "\n".join(f"{m.role}: {m.content}" for m in seg.messages)
        )
        blocks.append("---")
    return "\n".join(blocks)


def _is_recoverable_extraction_error(exc: Exception) -> bool:
    """Whether extraction can safely fall back to individual calls."""
    if isinstance(exc, ValidationError):
        return True
    if isinstance(exc, ValueError):
        msg = str(exc).lower()
        return (
            "structured json" in msg
            or "parse structured" in msg
            or "no structured json" in msg
            or "could not parse" in msg
            or "extraction batch response" in msg
        )
    return False
