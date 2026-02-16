"""Stage 1: Segmentation agent to split conversations into topical segments."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from time import perf_counter

from pydantic import BaseModel, Field, ValidationError
from rich.console import Console

from sbs.config import Config
from sbs.llm.client import LLMClient
from sbs.llm.prompts import (
    SEGMENTATION_BATCH_SYSTEM,
    SEGMENTATION_BATCH_USER,
    SEGMENTATION_SYSTEM,
    SEGMENTATION_USER,
    get_prompt,
)
from sbs.models.conversation import NormalizedConversation, NormalizedMessage
from sbs.models.segment import Segment

console = Console()

# Threshold: conversations with fewer messages get a single segment.
SHORT_CONVERSATION_THRESHOLD = 20
# Chunking parameters for long conversations.
WINDOW_SIZE = 30
OVERLAP = 5
# Structured segmentation output can be long for large threads.
SEGMENTATION_MAX_TOKENS = 8192


class SegmentBoundary(BaseModel):
    """A single segment boundary from LLM output."""

    start_index: int
    end_index: int
    topic_label: str


class SegmentationResult(BaseModel):
    """LLM output for segmentation."""

    segments: list[SegmentBoundary] = Field(default_factory=list)


class ConversationSegmentationResult(BaseModel):
    """Segmentation output for one conversation in a batch."""

    conversation_id: str
    segments: list[SegmentBoundary] = Field(default_factory=list)


class SegmentationBatchResult(BaseModel):
    """LLM output for batched segmentation."""

    items: list[ConversationSegmentationResult] = Field(default_factory=list)


@dataclass
class _PackedBatch:
    conversations: list[NormalizedConversation]
    estimated_tokens: int


async def segment_conversations(
    conversations: list[NormalizedConversation],
    llm: LLMClient,
    config: Config,
) -> list[Segment]:
    """Segment all conversations into topical segments."""
    long_conversations: list[NormalizedConversation] = []
    by_conversation: dict[str, list[Segment]] = {}

    for conv in conversations:
        if len(conv.messages) < SHORT_CONVERSATION_THRESHOLD:
            by_conversation[conv.id] = [_single_segment(conv)]
        else:
            long_conversations.append(conv)

    if not long_conversations:
        return _flatten_segments_in_order(conversations, by_conversation)

    if not config.stage1_batch_enabled:
        llm_segments = await _segment_individually(long_conversations, llm, config)
        by_conversation.update(llm_segments)
        return _flatten_segments_in_order(conversations, by_conversation)

    llm_segments = await _segment_in_micro_batches(long_conversations, llm, config)
    by_conversation.update(llm_segments)
    return _flatten_segments_in_order(conversations, by_conversation)


async def _segment_single(
    conv: NormalizedConversation,
    llm: LLMClient,
    config: Config,
) -> list[Segment]:
    """Segment a single conversation."""
    messages = conv.messages

    # Short conversations become one segment (no LLM call).
    if len(messages) < SHORT_CONVERSATION_THRESHOLD:
        return [_single_segment(conv)]

    formatted = _format_messages(messages)
    user_prompt = get_prompt("SEGMENTATION_USER", SEGMENTATION_USER).format(messages=formatted)

    result, _usage = await llm.cheap_structured_call(
        system=get_prompt("SEGMENTATION_SYSTEM", SEGMENTATION_SYSTEM),
        user=user_prompt,
        schema=SegmentationResult,
        max_tokens=SEGMENTATION_MAX_TOKENS,
    )

    segments = _segments_from_boundaries(conv, result.segments)
    if not segments:
        return _fallback_window_segments(conv)
    return segments


async def _segment_individually(
    conversations: list[NormalizedConversation],
    llm: LLMClient,
    config: Config,
) -> dict[str, list[Segment]]:
    """Segment conversations with one LLM call per conversation."""
    semaphore = asyncio.Semaphore(config.concurrency)

    async def process_one(conv: NormalizedConversation) -> tuple[str, list[Segment]]:
        async with semaphore:
            segments, _used_fallback = await _segment_single_with_recovery(conv, llm, config)
            return conv.id, segments

    tasks = [process_one(conv) for conv in conversations]
    results = await asyncio.gather(*tasks)
    return {conv_id: segments for conv_id, segments in results}


async def _segment_in_micro_batches(
    conversations: list[NormalizedConversation],
    llm: LLMClient,
    config: Config,
) -> dict[str, list[Segment]]:
    """Segment conversations using token-budget micro-batching."""
    batches = _pack_micro_batches(
        conversations=conversations,
        max_items=config.stage1_batch_max_items,
        token_budget=config.stage1_batch_input_token_budget,
    )
    semaphore = asyncio.Semaphore(config.concurrency)
    lock = asyncio.Lock()
    by_conversation: dict[str, list[Segment]] = {}

    processed_conversations = 0
    completed_batches = 0
    split_retry_count = 0
    fallback_count = 0
    total_batch_latency = 0.0

    async def process_batch(batch: list[NormalizedConversation]) -> None:
        nonlocal processed_conversations, completed_batches
        nonlocal split_retry_count, fallback_count, total_batch_latency

        async with semaphore:
            started = perf_counter()
            mapped, split_retries, batch_fallbacks = await _segment_batch_with_split_retry(
                batch,
                llm,
                config,
                remaining_splits=config.stage1_batch_split_retries,
            )
            elapsed = perf_counter() - started

        async with lock:
            by_conversation.update(mapped)
            processed_conversations += len(batch)
            completed_batches += 1
            split_retry_count += split_retries
            fallback_count += batch_fallbacks
            total_batch_latency += elapsed

            if config.verbose:
                avg_latency = total_batch_latency / completed_batches
                console.print(
                    "  [dim]Stage 1 batch progress:"
                    f" {processed_conversations}/{len(conversations)} conversations,"
                    f" {completed_batches}/{len(batches)} batches,"
                    f" avg_batch={avg_latency:.2f}s,"
                    f" split_retries={split_retry_count},"
                    f" fallbacks={fallback_count}[/dim]"
                )

    await asyncio.gather(*(process_batch(batch) for batch in batches))
    return by_conversation


async def _segment_batch_with_split_retry(
    conversations: list[NormalizedConversation],
    llm: LLMClient,
    config: Config,
    remaining_splits: int,
) -> tuple[dict[str, list[Segment]], int, int]:
    """Segment a micro-batch, recursively splitting on recoverable failures."""
    try:
        mapped = await _segment_batch(conversations, llm)
        return mapped, 0, 0
    except Exception as exc:
        if len(conversations) == 1:
            conv = conversations[0]
            segments, used_fallback = await _segment_single_with_recovery(conv, llm, config)
            return {conv.id: segments}, 0, int(used_fallback)

        if not _is_recoverable_segmentation_error(exc):
            raise

        if remaining_splits <= 0:
            mapped: dict[str, list[Segment]] = {}
            fallback_count = 0
            for conv in conversations:
                segments, used_fallback = await _segment_single_with_recovery(conv, llm, config)
                mapped[conv.id] = segments
                fallback_count += int(used_fallback)
            return mapped, 0, fallback_count

        midpoint = len(conversations) // 2
        left = conversations[:midpoint]
        right = conversations[midpoint:]
        left_map, left_splits, left_fallbacks = await _segment_batch_with_split_retry(
            left, llm, config, remaining_splits=remaining_splits - 1
        )
        right_map, right_splits, right_fallbacks = await _segment_batch_with_split_retry(
            right, llm, config, remaining_splits=remaining_splits - 1
        )
        merged = dict(left_map)
        merged.update(right_map)
        return merged, left_splits + right_splits + 1, left_fallbacks + right_fallbacks


async def _segment_batch(
    conversations: list[NormalizedConversation],
    llm: LLMClient,
) -> dict[str, list[Segment]]:
    """Segment multiple conversations in one structured LLM call."""
    payload = _format_batch_payload(conversations)
    user_prompt = get_prompt("SEGMENTATION_BATCH_USER", SEGMENTATION_BATCH_USER).format(
        batch_payload=payload
    )
    result, _usage = await llm.cheap_structured_call(
        system=get_prompt("SEGMENTATION_BATCH_SYSTEM", SEGMENTATION_BATCH_SYSTEM),
        user=user_prompt,
        schema=SegmentationBatchResult,
        max_tokens=SEGMENTATION_MAX_TOKENS,
    )
    return _map_batch_result(conversations, result)


async def _segment_single_with_recovery(
    conv: NormalizedConversation,
    llm: LLMClient,
    config: Config,
) -> tuple[list[Segment], bool]:
    """Segment one conversation with deterministic fallback on recoverable errors."""
    try:
        return await _segment_single(conv, llm, config), False
    except Exception as exc:
        if _is_recoverable_segmentation_error(exc):
            return _fallback_window_segments(conv), True
        raise


def _flatten_segments_in_order(
    conversations: list[NormalizedConversation],
    by_conversation: dict[str, list[Segment]],
) -> list[Segment]:
    """Preserve original conversation order in flattened segment list."""
    all_segments: list[Segment] = []
    for conv in conversations:
        all_segments.extend(by_conversation.get(conv.id, []))
    return all_segments


def _pack_micro_batches(
    conversations: list[NormalizedConversation],
    max_items: int,
    token_budget: int,
) -> list[list[NormalizedConversation]]:
    """Pack conversations into token-budget micro-batches (first-fit decreasing)."""
    ranked = [
        (conv, _estimate_conversation_tokens(conv), idx)
        for idx, conv in enumerate(conversations)
    ]
    ranked.sort(key=lambda item: (-item[1], item[2]))

    packed: list[_PackedBatch] = []
    for conv, estimated_tokens, _original_idx in ranked:
        placed = False
        for batch in packed:
            if len(batch.conversations) >= max_items:
                continue
            if batch.estimated_tokens + estimated_tokens > token_budget:
                continue
            batch.conversations.append(conv)
            batch.estimated_tokens += estimated_tokens
            placed = True
            break

        if not placed:
            packed.append(
                _PackedBatch(
                    conversations=[conv],
                    estimated_tokens=estimated_tokens,
                )
            )

    return [batch.conversations for batch in packed]


def _estimate_conversation_tokens(conv: NormalizedConversation) -> int:
    """Estimate prompt tokens for a conversation using message text length."""
    formatted = _format_messages(conv.messages)
    return max(1, (len(formatted) + 3) // 4)


def _format_batch_payload(conversations: list[NormalizedConversation]) -> str:
    """Render micro-batch payload with explicit conversation boundaries."""
    blocks: list[str] = []
    for conv in conversations:
        blocks.append(f"Conversation ID: {conv.id}")
        blocks.append(f"Title: {conv.title}")
        blocks.append("Messages:")
        blocks.append(_format_messages(conv.messages))
        blocks.append("---")
    return "\n".join(blocks)


def _map_batch_result(
    conversations: list[NormalizedConversation],
    result: SegmentationBatchResult,
) -> dict[str, list[Segment]]:
    """Validate and map batch response items to conversation segments."""
    by_id = {conv.id: conv for conv in conversations}
    expected_ids = set(by_id)
    mapped: dict[str, list[Segment]] = {}

    for item in result.items:
        conv_id = item.conversation_id.strip()
        if not conv_id:
            raise ValueError("Segmentation batch response missing conversation_id")
        if conv_id not in by_id:
            raise ValueError(f"Segmentation batch response has unknown conversation_id: {conv_id}")
        if conv_id in mapped:
            raise ValueError(
                f"Segmentation batch response has duplicate conversation_id: {conv_id}"
            )

        conv = by_id[conv_id]
        segments = _segments_from_boundaries(conv, item.segments)
        mapped[conv_id] = segments or _fallback_window_segments(conv)

    missing = expected_ids - set(mapped)
    if missing:
        missing_ids = ", ".join(sorted(missing))
        raise ValueError(f"Segmentation batch response missing conversations: {missing_ids}")

    return mapped



def _single_segment(conv: NormalizedConversation) -> Segment:
    """Create a single segment spanning the whole conversation."""
    return Segment(
        id=f"{conv.id}-seg-0",
        conversation_id=conv.id,
        topic_label=conv.title,
        messages=conv.messages,
        start_index=0,
        end_index=len(conv.messages) - 1,
    )



def _segments_from_boundaries(
    conv: NormalizedConversation,
    boundaries: Sequence[SegmentBoundary],
) -> list[Segment]:
    """Convert raw LLM boundaries to validated segments."""
    if not boundaries or not conv.messages:
        return []

    max_index = len(conv.messages) - 1
    segments: list[Segment] = []
    for boundary in boundaries:
        start = max(0, min(max_index, boundary.start_index))
        end = max(0, min(max_index, boundary.end_index))
        if end < start:
            continue

        topic_label = boundary.topic_label.strip() or conv.title
        segments.append(
            Segment(
                id=f"{conv.id}-seg-{len(segments)}",
                conversation_id=conv.id,
                topic_label=topic_label,
                messages=conv.messages[start : end + 1],
                start_index=start,
                end_index=end,
            )
        )

    return segments



def _fallback_window_segments(conv: NormalizedConversation) -> list[Segment]:
    """Fallback splitter for long conversations when LLM segmentation fails."""
    total = len(conv.messages)
    if total == 0:
        return []
    if total < SHORT_CONVERSATION_THRESHOLD:
        return [_single_segment(conv)]

    step = max(1, WINDOW_SIZE - OVERLAP)
    segments: list[Segment] = []
    start = 0
    part = 1

    while start < total:
        end = min(total - 1, start + WINDOW_SIZE - 1)
        segments.append(
            Segment(
                id=f"{conv.id}-seg-{len(segments)}",
                conversation_id=conv.id,
                topic_label=f"{conv.title} (part {part})",
                messages=conv.messages[start : end + 1],
                start_index=start,
                end_index=end,
            )
        )

        if end >= total - 1:
            break

        start += step
        part += 1

    return segments


def _is_recoverable_segmentation_error(exc: Exception) -> bool:
    """Whether segmentation can safely fallback to deterministic window splits."""
    if isinstance(exc, ValidationError):
        return True
    if isinstance(exc, ValueError):
        msg = str(exc).lower()
        return (
            "structured json" in msg
            or "parse structured" in msg
            or "no structured json" in msg
            or "could not parse" in msg
            or "segmentation batch response" in msg
        )
    return False



def _format_messages(messages: list[NormalizedMessage]) -> str:
    """Format messages for prompt inclusion."""
    lines = []
    for i, msg in enumerate(messages):
        lines.append(f"[{i}] {msg.role}: {msg.content[:500]}")
    return "\n".join(lines)
