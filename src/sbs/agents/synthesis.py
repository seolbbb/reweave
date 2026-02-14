"""Stage 3: Synthesis agent — transform extracted knowledge into atomic notes."""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from sbs.config import Config
from sbs.llm.client import LLMClient
from sbs.llm.prompts import SYNTHESIS_SYSTEM, SYNTHESIS_USER
from sbs.models.conversation import NormalizedConversation
from sbs.models.extraction import ExtractedKnowledge
from sbs.models.note import DraftNote, NoteFrontmatter


class SynthesizedNote(BaseModel):
    """LLM output schema for a single synthesized note."""

    title: str
    body: str
    tags: list[str] = Field(default_factory=list)
    link_candidates: list[str] = Field(default_factory=list)


class SynthesisResult(BaseModel):
    """LLM output schema for note synthesis."""

    notes: list[SynthesizedNote] = Field(default_factory=list)


async def synthesize_notes(
    extractions: list[ExtractedKnowledge],
    conversations: list[NormalizedConversation],
    llm: LLMClient,
    config: Config,
) -> tuple[list[DraftNote], list[DraftNote]]:
    """Synthesize atomic notes + source notes from extracted knowledge."""
    conv_map = {c.id: c for c in conversations}
    semaphore = asyncio.Semaphore(config.concurrency)

    # Counter for unique note IDs
    note_counter = [0]

    async def process_one(ek: ExtractedKnowledge) -> list[DraftNote]:
        async with semaphore:
            return await _synthesize_single(ek, conv_map, llm, note_counter)

    tasks = [process_one(ek) for ek in extractions]
    results = await asyncio.gather(*tasks)

    draft_notes = []
    for notes in results:
        draft_notes.extend(notes)

    # Generate source notes deterministically (no LLM)
    source_notes = _generate_source_notes(conversations, extractions)

    return draft_notes, source_notes


async def _synthesize_single(
    ek: ExtractedKnowledge,
    conv_map: dict[str, NormalizedConversation],
    llm: LLMClient,
    counter: list[int],
) -> list[DraftNote]:
    """Synthesize notes from a single extraction."""
    conv = conv_map.get(ek.conversation_id)
    source_ref = f"SRC-{conv.source}-{conv.id[:8]}" if conv else "unknown"
    conversation_date = conv.created_at if conv else ""

    concepts_text = "\n".join(
        f"- {c.name}: {c.description} (importance: {c.importance})" for c in ek.concepts
    ) or "None"
    decisions_text = "\n".join(
        f"- {d.decision} (rationale: {d.rationale})" for d in ek.decisions
    ) or "None"
    insights_text = "\n".join(
        f"- {i.insight} (context: {i.context})" for i in ek.insights
    ) or "None"

    user_prompt = SYNTHESIS_USER.format(
        topic_label=ek.topic_label,
        summary=ek.summary,
        concepts=concepts_text,
        decisions=decisions_text,
        insights=insights_text,
        source_ref=source_ref,
        conversation_date=conversation_date,
    )

    result, _usage = await llm.main_structured_call(
        system=SYNTHESIS_SYSTEM,
        user=user_prompt,
        schema=SynthesisResult,
    )

    draft_notes = []
    for note_data in result.notes:
        counter[0] += 1
        now = datetime.now(tz=UTC)
        note_id = now.strftime("%Y%m%d%H%M%S") + f"{counter[0]:04d}"
        slug = _slugify(note_data.title)
        filename = f"{note_id}-{slug}.md"

        frontmatter = NoteFrontmatter(
            type="permanent",
            created=now.isoformat(),
            tags=note_data.tags,
            source_type=conv.source if conv else "chatgpt",
            source_ref=f"[[{source_ref}]]",
            conversation_date=conversation_date,
            participants=["user", "assistant"],
        )

        draft = DraftNote(
            id=note_id,
            filename=filename,
            type="permanent",
            title=note_data.title,
            frontmatter=frontmatter,
            body=note_data.body,
            link_candidates=note_data.link_candidates,
            source_segment_ids=[ek.segment_id],
        )
        draft_notes.append(draft)

    return draft_notes


def _generate_source_notes(
    conversations: list[NormalizedConversation],
    extractions: list[ExtractedKnowledge],
) -> list[DraftNote]:
    """Generate source notes deterministically (no LLM needed)."""
    # Group extractions by conversation
    conv_extractions: dict[str, list[ExtractedKnowledge]] = {}
    for ek in extractions:
        conv_extractions.setdefault(ek.conversation_id, []).append(ek)

    source_notes = []
    for conv in conversations:
        source_id = f"SRC-{conv.source}-{conv.id[:8]}"
        slug = _slugify(conv.title)
        filename = f"{source_id}-{slug}.md"

        eks = conv_extractions.get(conv.id, [])
        topics = [ek.topic_label for ek in eks]
        summaries = [ek.summary for ek in eks if ek.summary]

        body_lines = [f"# {conv.title}", ""]
        body_lines.append(f"**Source**: {conv.source}")
        body_lines.append(f"**Date**: {conv.created_at}")
        body_lines.append(f"**Messages**: {conv.raw_message_count}")
        body_lines.append("")

        if topics:
            body_lines.append("## Topics Discussed")
            for topic in topics:
                body_lines.append(f"- {topic}")
            body_lines.append("")

        if summaries:
            body_lines.append("## Summary")
            for s in summaries:
                body_lines.append(f"- {s}")
            body_lines.append("")

        frontmatter = NoteFrontmatter(
            type="source",
            created=conv.created_at,
            tags=["source", conv.source],
            source_type=conv.source,
            source_ref=conv.id,
            conversation_date=conv.created_at,
            participants=["user", "assistant"],
        )

        source_notes.append(
            DraftNote(
                id=source_id,
                filename=filename,
                type="source",
                title=conv.title,
                frontmatter=frontmatter,
                body="\n".join(body_lines),
                source_segment_ids=[ek.segment_id for ek in eks],
            )
        )

    return source_notes


def _slugify(text: str) -> str:
    """Convert text to a URL-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:60].strip("-")
