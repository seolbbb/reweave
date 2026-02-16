"""Stage 3: Synthesis agent — transform extracted knowledge into atomic notes."""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from sbs.config import Config
from sbs.llm.client import LLMClient
from sbs.llm.prompts import SYNTHESIS_SYSTEM, SYNTHESIS_USER, get_prompt
from sbs.models.conversation import NormalizedConversation
from sbs.models.extraction import ExtractedKnowledge
from sbs.models.note import DraftNote, NoteFrontmatter


class SynthesizedNote(BaseModel):
    """LLM output schema for a single synthesized note."""

    title: str
    body: str
    recommended_type: Literal["fleeting", "permanent"] = "permanent"
    why_type: str = ""
    tags: list[str] = Field(default_factory=list)
    link_candidates: list[str] = Field(default_factory=list)
    expansion_prompts: list[str] = Field(default_factory=list)


class SynthesisResult(BaseModel):
    """LLM output schema for note synthesis."""

    notes: list[SynthesizedNote] = Field(default_factory=list)


async def synthesize_notes(
    extractions: list[ExtractedKnowledge],
    conversations: list[NormalizedConversation],
    llm: LLMClient,
    config: Config,
) -> tuple[list[DraftNote], list[DraftNote], list[DraftNote]]:
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
    literature_notes = _generate_literature_index(extractions, source_notes)

    return draft_notes, source_notes, literature_notes


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
    references_text = "\n".join(
        (
            f"- {r.title} | author: {r.author or 'unknown'} | year: {r.year or 'unknown'} "
            f"| type: {r.source_type or 'unknown'} | context: {r.mention_context or 'n/a'}"
        )
        for r in ek.references
    ) or "None"

    user_prompt = get_prompt("SYNTHESIS_USER", SYNTHESIS_USER).format(
        topic_label=ek.topic_label,
        summary=ek.summary,
        concepts=concepts_text,
        decisions=decisions_text,
        insights=insights_text,
        references=references_text,
        source_ref=source_ref,
        conversation_date=conversation_date,
    )

    result, _usage = await llm.main_structured_call(
        system=get_prompt("SYNTHESIS_SYSTEM", SYNTHESIS_SYSTEM),
        user=user_prompt,
        schema=SynthesisResult,
    )

    draft_notes = []
    for note_data in result.notes:
        counter[0] += 1
        now = datetime.now(tz=UTC)
        note_id = now.strftime("%Y%m%d%H%M%S") + f"{counter[0]:04d}"
        note_type = _resolve_note_type(note_data, ek)
        slug = _slugify(note_data.title)
        filename = f"{note_id}-{slug}.md"

        frontmatter = NoteFrontmatter(
            type=note_type,
            created=now.isoformat(),
            tags=note_data.tags,
            source_type=conv.source if conv else "chatgpt",
            source_ref=f"[[{source_ref}]]",
            conversation_date=conversation_date,
            participants=["user", "assistant"],
        )

        note_body = note_data.body
        if note_type == "fleeting":
            note_body = _render_fleeting_body(note_data.body, note_data.expansion_prompts)

        draft = DraftNote(
            id=note_id,
            filename=filename,
            type=note_type,
            title=note_data.title,
            frontmatter=frontmatter,
            body=note_body,
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


def _generate_literature_index(
    extractions: list[ExtractedKnowledge],
    source_notes: list[DraftNote],
) -> list[DraftNote]:
    """Generate a literature index note from referenced external materials."""
    if not extractions:
        return []

    source_by_conversation: dict[str, tuple[str, str]] = {}
    for note in source_notes:
        if note.type == "source" and note.frontmatter.source_ref:
            source_by_conversation[note.frontmatter.source_ref] = (
                Path(note.filename).stem,
                note.id,
            )

    merged_refs: dict[str, dict[str, str | set[str]]] = {}
    for ek in extractions:
        for ref in ek.references:
            key = _reference_key(ref.title, ref.year)
            if key not in merged_refs:
                merged_refs[key] = {
                    "title": ref.title,
                    "author": ref.author or "",
                    "year": ref.year or "",
                    "source_type": ref.source_type or "",
                    "contexts": set(),
                    "sources": set(),
                }

            merged_refs[key]["contexts"].add(ref.mention_context or ek.topic_label)  # type: ignore[index]

            source_link_info = source_by_conversation.get(ek.conversation_id)
            if source_link_info:
                link_target, display_id = source_link_info
                merged_refs[key]["sources"].add(  # type: ignore[index]
                    f"[[{link_target}|{display_id}]]"
                )

    body_lines = ["# Literature Index", ""]
    body_lines.append("## Mentioned References")
    if merged_refs:
        for item in merged_refs.values():
            title = item["title"]
            author = item["author"] or "unknown author"
            year = item["year"] or "n/a"
            source_type = item["source_type"] or "reference"
            body_lines.append(f"- **{title}** ({source_type}, {author}, {year})")
    else:
        body_lines.append("- No external references were detected in this run.")

    body_lines.extend(["", "## Suggested Follow-up Reading"])
    if merged_refs:
        for item in merged_refs.values():
            contexts = sorted(item["contexts"])  # type: ignore[arg-type]
            context_line = contexts[0] if contexts else "Investigate applicability to your notes."
            body_lines.append(f"- {item['title']}: {context_line}")
    else:
        body_lines.append("- Add your own books/papers here as you expand the vault.")

    body_lines.extend(["", "## Linked Source Conversations"])
    linked_sources = sorted(
        {
            source_id
            for item in merged_refs.values()
            for source_id in item["sources"]  # type: ignore[index]
        }
    )
    if linked_sources:
        for source_link in linked_sources:
            body_lines.append(f"- {source_link}")
    else:
        body_lines.append("- No source conversations linked to references yet.")

    now = datetime.now(tz=UTC).isoformat()
    literature_note = DraftNote(
        id="literature-index",
        filename="Literature.md",
        type="literature",
        title="Literature Index",
        frontmatter=NoteFrontmatter(
            type="literature",
            created=now,
            tags=["literature", "index"],
            source_ref="",
            conversation_date="",
            participants=["user", "assistant"],
        ),
        body="\n".join(body_lines),
    )
    return [literature_note]


def _resolve_note_type(
    note_data: SynthesizedNote,
    ek: ExtractedKnowledge,
) -> Literal["fleeting", "permanent"]:
    """Resolve final note type with a deterministic guardrail."""
    body_len = len(note_data.body.strip())
    has_supporting_structure = bool(ek.decisions or ek.insights)

    if note_data.recommended_type == "permanent":
        if body_len < 120 and not note_data.link_candidates:
            return "fleeting"
        return "permanent"

    if has_supporting_structure and body_len >= 220:
        return "permanent"

    return "fleeting"


def _render_fleeting_body(body: str, prompts: list[str]) -> str:
    """Add triage guidance for fleeting notes."""
    content = body.strip()
    expansion_prompts = prompts or [
        "What concrete claim should this idea make?",
        "Which existing permanent note should this connect to?",
        "What evidence would make this idea durable?",
    ]

    lines = [content, "", "## Expansion Prompts"]
    for prompt in expansion_prompts[:5]:
        lines.append(f"- {prompt}")
    return "\n".join(lines)


def _reference_key(title: str, year: str) -> str:
    """Build a deterministic key for reference deduplication."""
    normalized_title = " ".join(title.lower().strip().split())
    normalized_year = year.strip()
    return f"{normalized_title}::{normalized_year}"


def _slugify(text: str) -> str:
    """Convert text to a URL-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:60].strip("-")
