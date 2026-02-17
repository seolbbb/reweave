"""Stage 3: Synthesis agent — transform extracted knowledge into atomic notes."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Literal

from pydantic import BaseModel, Field, ValidationError
from rich.console import Console

from sbs.config import Config
from sbs.llm.client import LLMClient
from sbs.llm.prompts import SYNTHESIS_SYSTEM, SYNTHESIS_USER, get_prompt
from sbs.models.conversation import NormalizedConversation
from sbs.models.extraction import ExtractedKnowledge
from sbs.models.note import DraftNote, NoteFrontmatter
from sbs.pipeline.progress import StageProgress

console = Console()

SYNTHESIS_MAX_TOKENS = 8192

# ---------------------------------------------------------------------------
# Batch schemas & prompts
# ---------------------------------------------------------------------------

SYNTHESIS_BATCH_SYSTEM = """\
You are a Zettelkasten note writer and triage editor. For each extraction item \
in the input batch, transform the extracted knowledge into atomic notes.

For each item:
- extraction_id: the exact input extraction_id
- notes: list of synthesized notes, each with:
  - title: A declarative statement or descriptive phrase (not a question)
  - body: The note content in Markdown (2-5 paragraphs)
  - recommended_type: "fleeting" or "permanent"
  - why_type: one sentence rationale for your type choice
  - tags: 2-5 relevant tags (lowercase, hyphenated)
  - link_candidates: Names of other concepts this note could link to
  - expansion_prompts: 2-4 prompts that would help evolve the note (required for fleeting notes)

Rules:
- ONE idea per note — the note should be about exactly one concept or insight.
- Self-contained — a reader should understand the note without other context.
- Rephrase, don't copy — rewrite in your own words.
- Return exactly one item per input extraction_id."""

SYNTHESIS_BATCH_USER = """\
Create atomic Zettelkasten notes from each extraction in this batch:

{batch_payload}"""


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


class BatchSynthesisItem(BaseModel):
    """One extraction's synthesis result in a batch response."""

    extraction_id: str
    notes: list[SynthesizedNote] = Field(default_factory=list)


class BatchSynthesisResult(BaseModel):
    """LLM output for batched synthesis."""

    items: list[BatchSynthesisItem] = Field(default_factory=list)


@dataclass
class _PackedBatch:
    extractions: list[ExtractedKnowledge]
    estimated_tokens: int


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def synthesize_notes(
    extractions: list[ExtractedKnowledge],
    conversations: list[NormalizedConversation],
    llm: LLMClient,
    config: Config,
    progress: StageProgress | None = None,
) -> tuple[list[DraftNote], list[DraftNote], list[DraftNote]]:
    """Synthesize atomic notes + source notes from extracted knowledge."""
    conv_map = {c.id: c for c in conversations}

    # Thread-safe counter for unique note IDs
    counter_lock = asyncio.Lock()
    counter_value = [0]

    async def next_counter() -> int:
        async with counter_lock:
            counter_value[0] += 1
            return counter_value[0]

    if config.stage3_batch_enabled:
        draft_notes = await _synthesize_in_micro_batches(
            extractions, conv_map, llm, config, next_counter, progress
        )
    else:
        draft_notes = await _synthesize_individually(
            extractions, conv_map, llm, config, next_counter, progress
        )

    # Generate source notes deterministically (no LLM)
    source_notes = _generate_source_notes(conversations, extractions)
    literature_notes = _generate_literature_index(extractions, source_notes)

    return draft_notes, source_notes, literature_notes


# ---------------------------------------------------------------------------
# Individual synthesis (default)
# ---------------------------------------------------------------------------

async def _synthesize_individually(
    extractions: list[ExtractedKnowledge],
    conv_map: dict[str, NormalizedConversation],
    llm: LLMClient,
    config: Config,
    next_counter: object,
    progress: StageProgress | None = None,
) -> list[DraftNote]:
    """Synthesize with one LLM call per extraction."""
    concurrency = config.resolve_stage3_concurrency()
    semaphore = asyncio.Semaphore(concurrency)

    async def process_one(ek: ExtractedKnowledge) -> list[DraftNote]:
        async with semaphore:
            result = await _synthesize_single(ek, conv_map, llm, next_counter, config)
            if progress is not None:
                progress.advance(1)
            return result

    tasks = [process_one(ek) for ek in extractions]
    results = await asyncio.gather(*tasks)

    draft_notes: list[DraftNote] = []
    for notes in results:
        draft_notes.extend(notes)
    return draft_notes


async def _synthesize_single(
    ek: ExtractedKnowledge,
    conv_map: dict[str, NormalizedConversation],
    llm: LLMClient,
    next_counter: object,
    config: Config | None = None,
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

    started = perf_counter()
    result, usage = await llm.main_structured_call(
        system=get_prompt("SYNTHESIS_SYSTEM", SYNTHESIS_SYSTEM),
        user=user_prompt,
        schema=SynthesisResult,
    )
    elapsed = perf_counter() - started

    if config is not None and config.verbose:
        console.print(
            f"  [dim]synth seg={ek.segment_id[:12]}... "
            f"in={usage.input_tokens} out={usage.output_tokens} "
            f"({elapsed:.1f}s)[/dim]"
        )

    draft_notes: list[DraftNote] = []
    for note_data in result.notes:
        ctr = await next_counter()  # type: ignore[operator]
        now = datetime.now(tz=UTC)
        note_id = now.strftime("%Y%m%d%H%M%S") + f"{ctr:04d}"
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


# ---------------------------------------------------------------------------
# Micro-batch synthesis
# ---------------------------------------------------------------------------


async def _synthesize_in_micro_batches(
    extractions: list[ExtractedKnowledge],
    conv_map: dict[str, NormalizedConversation],
    llm: LLMClient,
    config: Config,
    next_counter: object,
    progress: StageProgress | None = None,
) -> list[DraftNote]:
    """Synthesize notes using token-budget micro-batching."""
    batches = _pack_micro_batches(
        extractions,
        max_items=config.stage3_batch_max_items,
        token_budget=config.stage3_batch_input_token_budget,
    )
    concurrency = config.resolve_stage3_concurrency()
    semaphore = asyncio.Semaphore(concurrency)
    lock = asyncio.Lock()
    all_notes: list[DraftNote] = []

    async def process_batch(batch: list[ExtractedKnowledge]) -> None:
        async with semaphore:
            notes = await _synthesize_batch_with_split_retry(
                batch, conv_map, llm, config, next_counter
            )

        async with lock:
            all_notes.extend(notes)
            if progress is not None:
                progress.advance(len(batch))

    await asyncio.gather(*(process_batch(batch) for batch in batches))
    return all_notes


async def _synthesize_batch_with_split_retry(
    extractions: list[ExtractedKnowledge],
    conv_map: dict[str, NormalizedConversation],
    llm: LLMClient,
    config: Config,
    next_counter: object,
    remaining_splits: int = 3,
) -> list[DraftNote]:
    """Synthesize a micro-batch, recursively splitting on recoverable failures."""
    try:
        return await _synthesize_batch(
            extractions, conv_map, llm, config, next_counter
        )
    except Exception as exc:
        if len(extractions) == 1:
            return await _synthesize_single(
                extractions[0], conv_map, llm, next_counter, config
            )

        if not _is_recoverable_synthesis_error(exc):
            raise

        if remaining_splits <= 0:
            results: list[DraftNote] = []
            for ek in extractions:
                notes = await _synthesize_single(ek, conv_map, llm, next_counter, config)
                results.extend(notes)
            return results

        midpoint = len(extractions) // 2
        left = await _synthesize_batch_with_split_retry(
            extractions[:midpoint], conv_map, llm, config, next_counter,
            remaining_splits - 1,
        )
        right = await _synthesize_batch_with_split_retry(
            extractions[midpoint:], conv_map, llm, config, next_counter,
            remaining_splits - 1,
        )
        return left + right


async def _synthesize_batch(
    extractions: list[ExtractedKnowledge],
    conv_map: dict[str, NormalizedConversation],
    llm: LLMClient,
    config: Config,
    next_counter: object,
) -> list[DraftNote]:
    """Synthesize notes from multiple extractions in one LLM call."""
    payload = _format_synthesis_batch_payload(extractions)
    system = get_prompt("SYNTHESIS_BATCH_SYSTEM", SYNTHESIS_BATCH_SYSTEM)
    user = get_prompt("SYNTHESIS_BATCH_USER", SYNTHESIS_BATCH_USER).format(
        batch_payload=payload
    )

    started = perf_counter()
    result, usage = await llm.main_structured_call(
        system=system,
        user=user,
        schema=BatchSynthesisResult,
        max_tokens=SYNTHESIS_MAX_TOKENS * min(len(extractions), 3),
    )
    elapsed = perf_counter() - started

    if config.verbose:
        console.print(
            f"  [dim]synth batch size={len(extractions)} "
            f"in={usage.input_tokens} out={usage.output_tokens} "
            f"({elapsed:.1f}s)[/dim]"
        )

    return await _map_synthesis_batch_result(
        extractions, conv_map, result, next_counter
    )


async def _map_synthesis_batch_result(
    extractions: list[ExtractedKnowledge],
    conv_map: dict[str, NormalizedConversation],
    result: BatchSynthesisResult,
    next_counter: object,
) -> list[DraftNote]:
    """Validate and map batch response items to DraftNotes."""
    by_id = {ek.segment_id: ek for ek in extractions}
    expected_ids = set(by_id)
    seen: set[str] = set()
    all_notes: list[DraftNote] = []

    for item in result.items:
        ek_id = item.extraction_id.strip()
        if not ek_id or ek_id not in by_id:
            raise ValueError(
                f"Synthesis batch response has unknown extraction_id: {ek_id}"
            )
        if ek_id in seen:
            raise ValueError(
                f"Synthesis batch response has duplicate extraction_id: {ek_id}"
            )
        seen.add(ek_id)

        ek = by_id[ek_id]
        conv = conv_map.get(ek.conversation_id)
        source_ref = f"SRC-{conv.source}-{conv.id[:8]}" if conv else "unknown"
        conversation_date = conv.created_at if conv else ""

        for note_data in item.notes:
            ctr = await next_counter()  # type: ignore[operator]
            now = datetime.now(tz=UTC)
            note_id = now.strftime("%Y%m%d%H%M%S") + f"{ctr:04d}"
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
                note_body = _render_fleeting_body(
                    note_data.body, note_data.expansion_prompts
                )

            all_notes.append(
                DraftNote(
                    id=note_id,
                    filename=filename,
                    type=note_type,
                    title=note_data.title,
                    frontmatter=frontmatter,
                    body=note_body,
                    link_candidates=note_data.link_candidates,
                    source_segment_ids=[ek.segment_id],
                )
            )

    missing = expected_ids - seen
    if missing:
        missing_ids = ", ".join(sorted(missing))
        raise ValueError(
            f"Synthesis batch response missing extractions: {missing_ids}"
        )

    return all_notes


# ---------------------------------------------------------------------------
# Bin-packing & utilities
# ---------------------------------------------------------------------------


def _pack_micro_batches(
    extractions: list[ExtractedKnowledge],
    max_items: int,
    token_budget: int,
) -> list[list[ExtractedKnowledge]]:
    """Pack extractions into token-budget micro-batches (first-fit decreasing)."""
    ranked = [
        (ek, _estimate_extraction_tokens(ek), idx)
        for idx, ek in enumerate(extractions)
    ]
    ranked.sort(key=lambda item: (-item[1], item[2]))

    packed: list[_PackedBatch] = []
    for ek, estimated_tokens, _original_idx in ranked:
        placed = False
        for batch in packed:
            if len(batch.extractions) >= max_items:
                continue
            if batch.estimated_tokens + estimated_tokens > token_budget:
                continue
            batch.extractions.append(ek)
            batch.estimated_tokens += estimated_tokens
            placed = True
            break

        if not placed:
            packed.append(
                _PackedBatch(extractions=[ek], estimated_tokens=estimated_tokens)
            )

    return [batch.extractions for batch in packed]


def _estimate_extraction_tokens(ek: ExtractedKnowledge) -> int:
    """Estimate prompt tokens for an extraction."""
    parts = [ek.topic_label, ek.summary]
    for c in ek.concepts:
        parts.append(f"{c.name}: {c.description}")
    for d in ek.decisions:
        parts.append(f"{d.decision}: {d.rationale}")
    for i in ek.insights:
        parts.append(f"{i.insight}: {i.context}")
    text = "\n".join(parts)
    return max(1, (len(text) + 3) // 4)


def _format_synthesis_batch_payload(
    extractions: list[ExtractedKnowledge],
) -> str:
    """Render micro-batch payload with explicit extraction boundaries."""
    blocks: list[str] = []
    for ek in extractions:
        blocks.append(f"Extraction ID: {ek.segment_id}")
        blocks.append(f"Topic: {ek.topic_label}")
        blocks.append(f"Summary: {ek.summary}")

        concepts_text = "\n".join(
            f"- {c.name}: {c.description} (importance: {c.importance})"
            for c in ek.concepts
        ) or "None"
        decisions_text = "\n".join(
            f"- {d.decision} (rationale: {d.rationale})" for d in ek.decisions
        ) or "None"
        insights_text = "\n".join(
            f"- {i.insight} (context: {i.context})" for i in ek.insights
        ) or "None"
        references_text = "\n".join(
            (
                f"- {r.title} | author: {r.author or 'unknown'} "
                f"| year: {r.year or 'unknown'} | type: {r.source_type or 'unknown'}"
            )
            for r in ek.references
        ) or "None"

        blocks.append(f"Concepts:\n{concepts_text}")
        blocks.append(f"Decisions:\n{decisions_text}")
        blocks.append(f"Insights:\n{insights_text}")
        blocks.append(f"References:\n{references_text}")
        blocks.append("---")
    return "\n".join(blocks)


def _is_recoverable_synthesis_error(exc: Exception) -> bool:
    """Whether synthesis can safely fall back to individual calls."""
    if isinstance(exc, ValidationError):
        return True
    if isinstance(exc, ValueError):
        msg = str(exc).lower()
        return (
            "structured json" in msg
            or "parse structured" in msg
            or "no structured json" in msg
            or "could not parse" in msg
            or "synthesis batch response" in msg
        )
    return False


# ---------------------------------------------------------------------------
# Deterministic helpers (unchanged)
# ---------------------------------------------------------------------------


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
