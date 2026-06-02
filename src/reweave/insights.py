"""Source-grounded insight synthesis from selected conversations."""

from __future__ import annotations

from dataclasses import dataclass

from reweave.archive import (
    ArchivedConversation,
    ArchivedMessage,
    ArchiveStore,
    InsightReport,
)
from reweave.llm import LLMProvider, LLMSettings, create_provider

INSIGHT_SECTIONS = [
    "Overview",
    "Concept Map",
    "Connections",
    "New Insights",
    "Uncertainties",
    "Source Index",
]

SYSTEM_PROMPT = """\
You connect ideas across a user's archived AI conversations.

Write a single Markdown insight report with exactly these H2 sections:
## Overview
## Concept Map
## Connections
## New Insights
## Uncertainties
## Source Index

Rules:
- Use source references in the form [conversation_id#mIndex] for every important claim.
- Mark newly inferred connections with "Inference:".
- Put unsupported or uncertain claims under "Uncertainties".
- Do not invent source references.
- Prefer concise, useful synthesis over broad summary.
"""


@dataclass(frozen=True)
class InsightInput:
    conversation: ArchivedConversation
    messages: list[ArchivedMessage]


def generate_insight_report(
    store: ArchiveStore,
    *,
    conversation_ids: list[str],
    settings: LLMSettings,
    title: str = "Connected Insights",
    provider: LLMProvider | None = None,
) -> InsightReport:
    """Generate, save, and return an insight report for selected conversations."""
    if not conversation_ids:
        raise ValueError("At least one conversation must be selected.")

    inputs = _load_inputs(store, conversation_ids)
    if len(inputs) != len(conversation_ids):
        found = {item.conversation.id for item in inputs}
        missing = [
            conversation_id
            for conversation_id in conversation_ids
            if conversation_id not in found
        ]
        raise ValueError(f"Conversation not found: {', '.join(missing)}")

    llm = provider or create_provider(settings)
    documents = [_format_conversation(item) for item in inputs]
    chunks = _pack_chunks(documents, max(10_000, settings.max_context_chars))

    if len(chunks) == 1:
        markdown = llm.generate_text(
            system=SYSTEM_PROMPT,
            user=_final_prompt(chunks[0]),
            model=settings.model,
            temperature=settings.temperature,
            max_tokens=4096,
        )
    else:
        partials = []
        for index, chunk in enumerate(chunks, start=1):
            partials.append(
                llm.generate_text(
                    system=SYSTEM_PROMPT,
                    user=_chunk_prompt(index, len(chunks), chunk),
                    model=settings.model,
                    temperature=settings.temperature,
                    max_tokens=2500,
                )
            )
        markdown = llm.generate_text(
            system=SYSTEM_PROMPT,
            user=_merge_prompt(partials),
            model=settings.model,
            temperature=settings.temperature,
            max_tokens=4096,
        )

    markdown = _ensure_sections(markdown)
    return store.save_insight_report(
        title=title,
        selected_conversation_ids=conversation_ids,
        provider=settings.provider,
        model=settings.model,
        markdown=markdown,
    )


def _load_inputs(store: ArchiveStore, conversation_ids: list[str]) -> list[InsightInput]:
    inputs = []
    for conversation_id in conversation_ids:
        conversation = store.get_conversation(conversation_id)
        if conversation is None:
            continue
        inputs.append(
            InsightInput(
                conversation=conversation,
                messages=store.get_messages(conversation_id),
            )
        )
    return inputs


def _format_conversation(item: InsightInput) -> str:
    lines = [
        f"<conversation id=\"{item.conversation.id}\" source=\"{item.conversation.source}\">",
        f"Title: {item.conversation.title}",
        f"Created: {item.conversation.created_at}",
        "",
    ]
    for message in item.messages:
        timestamp = f" timestamp=\"{message.timestamp}\"" if message.timestamp else ""
        lines.extend(
            [
                f"<message index=\"{message.index}\" role=\"{message.role}\"{timestamp}>",
                message.content,
                "</message>",
                "",
            ]
        )
    lines.append("</conversation>")
    return "\n".join(lines)


def _pack_chunks(documents: list[str], max_chars: int) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    current_size = 0
    for document in documents:
        document_size = len(document)
        if current and current_size + document_size > max_chars:
            chunks.append("\n\n".join(current))
            current = []
            current_size = 0
        if document_size > max_chars:
            chunks.extend(_split_large_document(document, max_chars))
            continue
        current.append(document)
        current_size += document_size
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _split_large_document(document: str, max_chars: int) -> list[str]:
    return [document[i : i + max_chars] for i in range(0, len(document), max_chars)]


def _chunk_prompt(index: int, total: int, chunk: str) -> str:
    return f"""\
This is chunk {index} of {total}. Extract source-grounded concepts, connections,
uncertainties, and possible inferences. Preserve source references exactly.

{chunk}
"""


def _merge_prompt(partials: list[str]) -> str:
    joined = "\n\n--- PARTIAL REPORT ---\n\n".join(partials)
    return f"""\
Merge these partial reports into one final insight report. Deduplicate repeated
ideas and keep source references attached to every important claim.

{joined}
"""


def _final_prompt(chunk: str) -> str:
    return f"""\
Create a source-grounded insight report from these selected conversations:

{chunk}
"""


def _ensure_sections(markdown: str) -> str:
    markdown = markdown.strip()
    missing = [section for section in INSIGHT_SECTIONS if f"## {section}" not in markdown]
    if not missing:
        return markdown + "\n"
    additions = "\n".join(f"\n## {section}\n\n_Not provided._" for section in missing)
    return f"{markdown}\n{additions}\n"
