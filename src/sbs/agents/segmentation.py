"""Stage 1: Segmentation agent — split conversations into topical segments."""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, Field

from sbs.config import Config
from sbs.llm.client import LLMClient
from sbs.llm.prompts import SEGMENTATION_SYSTEM, SEGMENTATION_USER
from sbs.models.conversation import NormalizedConversation, NormalizedMessage
from sbs.models.segment import Segment

# Threshold: conversations with fewer messages get a single segment
SHORT_CONVERSATION_THRESHOLD = 20
# Chunking parameters for long conversations
WINDOW_SIZE = 30
OVERLAP = 5


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
            return await _segment_single(conv, llm, config)

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

    # Short conversations → single segment (no LLM call)
    if len(messages) < SHORT_CONVERSATION_THRESHOLD:
        return [
            Segment(
                id=f"{conv.id}-seg-0",
                conversation_id=conv.id,
                topic_label=conv.title,
                messages=messages,
                start_index=0,
                end_index=len(messages) - 1,
            )
        ]

    # Long conversations → chunk and ask LLM for topic boundaries
    formatted = _format_messages(messages)
    user_prompt = SEGMENTATION_USER.format(messages=formatted)

    result, _usage = await llm.cheap_structured_call(
        system=SEGMENTATION_SYSTEM,
        user=user_prompt,
        schema=SegmentationResult,
    )

    if not result.segments:
        # Fallback: treat as single segment
        return [
            Segment(
                id=f"{conv.id}-seg-0",
                conversation_id=conv.id,
                topic_label=conv.title,
                messages=messages,
                start_index=0,
                end_index=len(messages) - 1,
            )
        ]

    segments = []
    for i, boundary in enumerate(result.segments):
        start = max(0, boundary.start_index)
        end = min(len(messages) - 1, boundary.end_index)
        segments.append(
            Segment(
                id=f"{conv.id}-seg-{i}",
                conversation_id=conv.id,
                topic_label=boundary.topic_label,
                messages=messages[start : end + 1],
                start_index=start,
                end_index=end,
            )
        )

    return segments


def _format_messages(messages: list[NormalizedMessage]) -> str:
    """Format messages for prompt inclusion."""
    lines = []
    for i, msg in enumerate(messages):
        lines.append(f"[{i}] {msg.role}: {msg.content[:500]}")
    return "\n".join(lines)
