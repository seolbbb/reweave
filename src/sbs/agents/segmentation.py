"""Stage 1: Segmentation agent to split conversations into topical segments."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from pydantic import BaseModel, Field, ValidationError

from sbs.config import Config
from sbs.llm.client import LLMClient
from sbs.llm.prompts import SEGMENTATION_SYSTEM, SEGMENTATION_USER, get_prompt
from sbs.models.conversation import NormalizedConversation, NormalizedMessage
from sbs.models.segment import Segment

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


async def segment_conversations(
    conversations: list[NormalizedConversation],
    llm: LLMClient,
    config: Config,
) -> list[Segment]:
    """Segment all conversations into topical segments."""
    all_segments: list[Segment] = []
    semaphore = asyncio.Semaphore(config.concurrency)

    async def process_one(conv: NormalizedConversation) -> list[Segment]:
        async with semaphore:
            try:
                return await _segment_single(conv, llm, config)
            except Exception as exc:
                if _is_recoverable_segmentation_error(exc):
                    # Keep pipeline progress if model output is malformed.
                    return _fallback_window_segments(conv)
                raise

    tasks = [process_one(conv) for conv in conversations]
    results = await asyncio.gather(*tasks)
    for segments in results:
        all_segments.extend(segments)

    return all_segments


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
        )
    return False



def _format_messages(messages: list[NormalizedMessage]) -> str:
    """Format messages for prompt inclusion."""
    lines = []
    for i, msg in enumerate(messages):
        lines.append(f"[{i}] {msg.role}: {msg.content[:500]}")
    return "\n".join(lines)
