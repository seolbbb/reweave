"""Stage 2: Extraction agent — extract structured knowledge from segments."""

from __future__ import annotations

import asyncio

from pydantic import BaseModel, Field

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

# Minimum messages for extraction to be worthwhile
MIN_MESSAGES = 3


class ExtractionResult(BaseModel):
    """LLM output schema for knowledge extraction."""

    concepts: list[ConceptItem] = Field(default_factory=list)
    decisions: list[DecisionItem] = Field(default_factory=list)
    insights: list[InsightItem] = Field(default_factory=list)
    todos: list[TodoItem] = Field(default_factory=list)
    open_questions: list[OpenQuestion] = Field(default_factory=list)
    references: list[ReferenceItem] = Field(default_factory=list)
    summary: str = ""


async def extract_knowledge(
    segments: list[Segment],
    llm: LLMClient,
    config: Config,
) -> list[ExtractedKnowledge]:
    """Extract structured knowledge from all segments."""
    semaphore = asyncio.Semaphore(config.concurrency)

    async def process_one(seg: Segment) -> ExtractedKnowledge | None:
        async with semaphore:
            return await _extract_single(seg, llm)

    tasks = [process_one(seg) for seg in segments]
    results = await asyncio.gather(*tasks)
    return [r for r in results if r is not None]


async def _extract_single(
    segment: Segment,
    llm: LLMClient,
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

    result, _usage = await llm.main_structured_call(
        system=system,
        user=user,
        schema=ExtractionResult,
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
