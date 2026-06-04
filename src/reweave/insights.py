"""Source-grounded insight synthesis from selected conversations."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

from reweave.archive import (
    ArchivedConversation,
    ArchivedMessage,
    ArchiveStore,
    InsightReport,
)
from reweave.llm import LLMProvider, LLMSettings, create_provider

ENGLISH_SECTIONS = [
    "Overview",
    "Key concepts",
    "Connections between conversations",
    "Agreements, contradictions, and patterns",
    "New or surprising insights",
    "Suggested follow-up questions",
    "Source references",
]

KOREAN_SECTIONS = [
    "개요",
    "핵심 개념",
    "대화 간 연결",
    "합의점·모순·패턴",
    "새롭거나 놀라운 인사이트",
    "후속 질문 제안",
    "출처 참조",
]

MAX_MESSAGE_CHARS = 12_000
MAX_PARALLEL_CHUNKS = 4

ProgressCallback = Callable[[str, str, int, int], None]


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
    progress: ProgressCallback | None = None,
    metrics: dict[str, Any] | None = None,
) -> InsightReport:
    """Generate, save, and return an insight report for selected conversations."""
    started = time.perf_counter()
    measurements = metrics if metrics is not None else {}
    conversation_ids = list(dict.fromkeys(conversation_ids))
    if not conversation_ids:
        raise ValueError("At least one conversation must be selected.")

    _notify(progress, "loading", "Loading selected conversations", 0, len(conversation_ids))
    phase_started = time.perf_counter()
    inputs = _load_inputs(store, conversation_ids)
    measurements["loading_ms"] = _elapsed_ms(phase_started)
    if len(inputs) != len(conversation_ids):
        found = {item.conversation.id for item in inputs}
        missing = [
            conversation_id
            for conversation_id in conversation_ids
            if conversation_id not in found
        ]
        raise ValueError(f"Conversation not found: {', '.join(missing)}")

    _notify(progress, "preparing", "Detecting language and preparing source context", 0, 1)
    phase_started = time.perf_counter()
    language = detect_report_language(inputs)
    documents = [_format_conversation(item) for item in inputs]
    chunks = _pack_chunks(documents, max(10_000, settings.max_context_chars))
    system_prompt = _system_prompt(language)
    measurements["preprocessing_ms"] = _elapsed_ms(phase_started)
    measurements["language"] = language
    measurements["source_count"] = len(inputs)
    measurements["chunk_count"] = len(chunks)
    measurements["source_chars"] = sum(
        len(message.content) for item in inputs for message in item.messages
    )
    measurements["context_chars"] = sum(len(chunk) for chunk in chunks)

    llm = provider or create_provider(settings)
    model_call_durations: list[float] = []
    prompt_started = time.perf_counter()
    model_wall_started = time.perf_counter()

    if len(chunks) == 1:
        user_prompt = _final_prompt(chunks[0], language)
        measurements["prompt_construction_ms"] = _elapsed_ms(prompt_started)
        _notify(progress, "synthesizing", "Synthesizing the report", 0, 1)
        markdown, duration = _generate(
            llm,
            system=system_prompt,
            user=user_prompt,
            settings=settings,
            max_tokens=3200,
        )
        model_call_durations.append(duration)
    else:
        chunk_prompts = [
            _chunk_prompt(index, len(chunks), chunk, language)
            for index, chunk in enumerate(chunks, start=1)
        ]
        measurements["prompt_construction_ms"] = _elapsed_ms(prompt_started)
        _notify(
            progress,
            "analyzing",
            f"Analyzing {len(chunks)} source groups in parallel",
            0,
            len(chunks),
        )
        partials, durations = _generate_partials(
            llm,
            system_prompt=system_prompt,
            prompts=chunk_prompts,
            settings=settings,
            progress=progress,
        )
        model_call_durations.extend(durations)
        merge_prompt_started = time.perf_counter()
        merge_prompt = _merge_prompt(partials, language)
        measurements["prompt_construction_ms"] += _elapsed_ms(merge_prompt_started)
        _notify(progress, "synthesizing", "Connecting findings into the final report", 0, 1)
        markdown, duration = _generate(
            llm,
            system=system_prompt,
            user=merge_prompt,
            settings=settings,
            max_tokens=3200,
        )
        model_call_durations.append(duration)

    measurements["model_call_count"] = len(model_call_durations)
    measurements["model_call_durations_ms"] = [round(value, 2) for value in model_call_durations]
    measurements["model_wall_ms"] = _elapsed_ms(model_wall_started)
    measurements["parallel_workers"] = min(len(chunks), MAX_PARALLEL_CHUNKS)

    _notify(progress, "saving", "Saving the finished report", 0, 1)
    phase_started = time.perf_counter()
    markdown = _ensure_sections(markdown, language)
    report = store.save_insight_report(
        title=title,
        selected_conversation_ids=conversation_ids,
        provider=settings.provider,
        model=settings.model,
        markdown=markdown,
    )
    measurements["saving_ms"] = _elapsed_ms(phase_started)
    measurements["total_ms"] = _elapsed_ms(started)
    _notify(progress, "complete", "Insight report ready", 1, 1)
    return report


def detect_report_language(inputs: list[InsightInput]) -> str:
    """Return the dominant supported report language for selected conversations."""
    hangul = 0
    latin = 0
    for item in inputs:
        for text in [item.conversation.title, *(message.content for message in item.messages)]:
            hangul += len(re.findall(r"[가-힣]", text))
            latin += len(re.findall(r"[A-Za-z]", text))
    return "ko" if hangul and hangul >= latin * 0.35 else "en"


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
        f'<conversation id="{item.conversation.id}" source="{item.conversation.source}">',
        f"Title: {item.conversation.title}",
        f"Created: {item.conversation.created_at}",
        "",
    ]
    for message in item.messages:
        timestamp = f' timestamp="{message.timestamp}"' if message.timestamp else ""
        lines.extend(
            [
                f'<message index="{message.index}" role="{message.role}"{timestamp}>',
                f"Source reference: [{item.conversation.id}#m{message.index}]",
                _compact_message(message.content),
                "</message>",
                "",
            ]
        )
    lines.append("</conversation>")
    return "\n".join(lines)


def _compact_message(content: str) -> str:
    compact = re.sub(r"\n{3,}", "\n\n", content.strip())
    if len(compact) <= MAX_MESSAGE_CHARS:
        return compact
    head_chars = MAX_MESSAGE_CHARS * 2 // 3
    tail_chars = MAX_MESSAGE_CHARS - head_chars
    return (
        f"{compact[:head_chars]}\n\n"
        "[...middle of long message omitted for a faster focused synthesis...]\n\n"
        f"{compact[-tail_chars:]}"
    )


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
    blocks = document.split("\n\n")
    chunks: list[str] = []
    current: list[str] = []
    current_size = 0
    for block in blocks:
        if len(block) > max_chars:
            if current:
                chunks.append("\n\n".join(current))
                current = []
                current_size = 0
            chunks.extend(block[i : i + max_chars] for i in range(0, len(block), max_chars))
            continue
        if current and current_size + len(block) + 2 > max_chars:
            chunks.append("\n\n".join(current))
            current = []
            current_size = 0
        current.append(block)
        current_size += len(block) + 2
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _generate_partials(
    llm: LLMProvider,
    *,
    system_prompt: str,
    prompts: list[str],
    settings: LLMSettings,
    progress: ProgressCallback | None,
) -> tuple[list[str], list[float]]:
    partials = [""] * len(prompts)
    durations = [0.0] * len(prompts)
    workers = min(len(prompts), MAX_PARALLEL_CHUNKS)
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="reweave-insight") as executor:
        futures = {
            executor.submit(
                _generate,
                llm,
                system=system_prompt,
                user=user_prompt,
                settings=settings,
                max_tokens=1800,
            ): index
            for index, user_prompt in enumerate(prompts)
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            index = futures[future]
            partials[index], durations[index] = future.result()
            _notify(
                progress,
                "analyzing",
                f"Analyzed {completed} of {len(prompts)} source groups",
                completed,
                len(prompts),
            )
    return partials, durations


def _generate(
    llm: LLMProvider,
    *,
    system: str,
    user: str,
    settings: LLMSettings,
    max_tokens: int,
) -> tuple[str, float]:
    started = time.perf_counter()
    text = llm.generate_text(
        system=system,
        user=user,
        model=settings.model,
        temperature=settings.temperature,
        max_tokens=max_tokens,
    )
    return text, _elapsed_ms(started)


def _system_prompt(language: str) -> str:
    sections = KOREAN_SECTIONS if language == "ko" else ENGLISH_SECTIONS
    language_name = "Korean" if language == "ko" else "English"
    section_list = "\n".join(f"## {section}" for section in sections)
    return f"""\
You connect ideas across a user's archived AI conversations.

Write the entire report in {language_name}. Use exactly these H2 sections:
{section_list}

Rules:
- Use source references in the form [conversation_id#mIndex] after every important claim.
- Compare conversations explicitly, naming agreements, contradictions, recurring patterns, and gaps.
- Mark genuinely new deductions as an inference and explain which sources support them.
- Make key concepts and connections easy to scan with concise lists.
- Suggest useful follow-up questions grounded in unresolved source material.
- Do not invent source references or unsupported facts.
- Prefer a focused, readable report over a broad recap.
"""


def _chunk_prompt(index: int, total: int, chunk: str, language: str) -> str:
    instruction = (
        "이 소스 그룹에서 근거가 있는 개념, 연결점, 합의점, 모순, 패턴, "
        "놀라운 인사이트와 후속 질문을 추출하세요."
        if language == "ko"
        else (
            "Extract source-grounded concepts, connections, agreements, contradictions, "
            "patterns, surprising insights, and follow-up questions from this source group."
        )
    )
    return f"""\
This is source group {index} of {total}. {instruction}
Preserve every source reference exactly so the final report can link back to evidence.

{chunk}
"""


def _merge_prompt(partials: list[str], language: str) -> str:
    joined = "\n\n--- PARTIAL FINDINGS ---\n\n".join(partials)
    instruction = (
        "아래 부분 분석을 중복 없이 하나의 완성도 높은 한국어 인사이트 보고서로 통합하세요."
        if language == "ko"
        else (
            "Merge these partial findings into one polished English insight report "
            "without repetition."
        )
    )
    return f"""\
{instruction}
Keep source references attached to every important claim and emphasize cross-conversation links.

{joined}
"""


def _final_prompt(chunk: str, language: str) -> str:
    instruction = (
        "선택한 대화를 바탕으로 근거 중심의 한국어 인사이트 보고서를 작성하세요."
        if language == "ko"
        else "Create a source-grounded English insight report from the selected conversations."
    )
    return f"""\
{instruction}

{chunk}
"""


def _ensure_sections(markdown: str, language: str) -> str:
    markdown = markdown.strip()
    sections = KOREAN_SECTIONS if language == "ko" else ENGLISH_SECTIONS
    missing = [section for section in sections if f"## {section}" not in markdown]
    if not missing:
        return markdown + "\n"
    fallback = "_제공되지 않음._" if language == "ko" else "_Not provided._"
    additions = "\n".join(f"\n## {section}\n\n{fallback}" for section in missing)
    return f"{markdown}\n{additions}\n"


def _notify(
    callback: ProgressCallback | None,
    stage: str,
    message: str,
    completed: int,
    total: int,
) -> None:
    if callback is not None:
        callback(stage, message, completed, total)


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 2)
