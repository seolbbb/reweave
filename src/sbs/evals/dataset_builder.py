"""Build stage-wise evaluation datasets from pipeline inputs and checkpoints."""

from __future__ import annotations

import json
from pathlib import Path

from sbs.models.evals import EvalCase
from sbs.parsers.detector import parse_directory
from sbs.pipeline.checkpoint import CheckpointManager

DEFAULT_STAGE_FILES = {
    "segmentation": "segmentation_cases.jsonl",
    "extraction": "extraction_cases.jsonl",
    "synthesis": "synthesis_cases.jsonl",
    "linking": "linking_cases.jsonl",
    "validation": "validation_cases.jsonl",
}


def build_eval_datasets(
    input_dir: Path,
    output_dir: Path,
    checkpoint_path: Path | None = None,
    max_cases_per_stage: int = 80,
) -> dict[str, int]:
    """Build JSONL datasets for all pipeline stages."""
    output_dir.mkdir(parents=True, exist_ok=True)

    conversations = parse_directory(input_dir)
    state = _load_state(checkpoint_path)

    segmentation_cases = _build_segmentation_cases(conversations, max_cases_per_stage)
    extraction_cases = _build_extraction_cases(state, max_cases_per_stage)
    synthesis_cases = _build_synthesis_cases(state, max_cases_per_stage)
    linking_cases = _build_linking_cases(state, max_cases_per_stage)
    validation_cases = _build_validation_cases(state, max_cases_per_stage)

    stage_cases: dict[str, list[EvalCase]] = {
        "segmentation": segmentation_cases,
        "extraction": extraction_cases,
        "synthesis": synthesis_cases,
        "linking": linking_cases,
        "validation": validation_cases,
    }

    counts: dict[str, int] = {}
    for stage_name, cases in stage_cases.items():
        path = output_dir / DEFAULT_STAGE_FILES[stage_name]
        _write_cases(path, cases)
        counts[stage_name] = len(cases)

    return counts


def _load_state(checkpoint_path: Path | None):
    if checkpoint_path is None:
        return None

    if checkpoint_path.is_file():
        manager = CheckpointManager(checkpoint_path.parent)
        return manager.load(checkpoint_path)

    manager = CheckpointManager(checkpoint_path)
    latest = manager.latest()
    return latest


def _build_segmentation_cases(conversations, limit: int) -> list[EvalCase]:
    cases: list[EvalCase] = []
    for conv in conversations[:limit]:
        messages = [
            {
                "role": msg.role,
                "content": msg.content[:600],
            }
            for msg in conv.messages
        ]
        cases.append(
            EvalCase(
                case_id=f"seg-{conv.id}",
                stage="segmentation",
                input_payload={
                    "conversation_id": conv.id,
                    "title": conv.title,
                    "messages": messages,
                },
                expected={
                    "min_segments": 1,
                    "message_count": len(conv.messages),
                },
                tags=[conv.source],
                source_ref=conv.id,
            )
        )
    return cases


def _build_extraction_cases(state, limit: int) -> list[EvalCase]:
    if state is None or not state.segments:
        return []

    extraction_map = {e.segment_id: e for e in state.extractions}
    cases: list[EvalCase] = []
    for seg in state.segments[:limit]:
        expected = extraction_map.get(seg.id)
        cases.append(
            EvalCase(
                case_id=f"ext-{seg.id}",
                stage="extraction",
                input_payload={
                    "segment_id": seg.id,
                    "topic_label": seg.topic_label,
                    "messages": [
                        {"role": msg.role, "content": msg.content[:800]}
                        for msg in seg.messages
                    ],
                },
                expected={
                    "summary": expected.summary if expected else "",
                    "concept_count": len(expected.concepts) if expected else 0,
                    "decision_count": len(expected.decisions) if expected else 0,
                    "insight_count": len(expected.insights) if expected else 0,
                },
                tags=["checkpoint-derived"],
                source_ref=seg.conversation_id,
            )
        )
    return cases


def _build_synthesis_cases(state, limit: int) -> list[EvalCase]:
    if state is None or not state.extractions:
        return []

    notes_by_segment: dict[str, int] = {}
    for note in state.draft_notes:
        for seg_id in note.source_segment_ids:
            notes_by_segment[seg_id] = notes_by_segment.get(seg_id, 0) + 1

    cases: list[EvalCase] = []
    for extraction in state.extractions[:limit]:
        cases.append(
            EvalCase(
                case_id=f"syn-{extraction.segment_id}",
                stage="synthesis",
                input_payload={
                    "segment_id": extraction.segment_id,
                    "topic_label": extraction.topic_label,
                    "summary": extraction.summary,
                    "concepts": [c.model_dump() for c in extraction.concepts],
                    "decisions": [d.model_dump() for d in extraction.decisions],
                    "insights": [i.model_dump() for i in extraction.insights],
                },
                expected={
                    "min_notes": 1 if extraction.concepts or extraction.insights else 0,
                    "observed_notes": notes_by_segment.get(extraction.segment_id, 0),
                },
                tags=["checkpoint-derived"],
                source_ref=extraction.conversation_id,
            )
        )
    return cases


def _build_linking_cases(state, limit: int) -> list[EvalCase]:
    if state is None:
        return []

    permanent_notes = [n for n in state.draft_notes if n.type == "permanent"]
    if not permanent_notes:
        return []

    # Build a small set of cluster-style linking cases from permanent note windows.
    cases: list[EvalCase] = []
    window_size = 8
    for idx in range(0, min(len(permanent_notes), limit * window_size), window_size):
        window = permanent_notes[idx : idx + window_size]
        if len(window) < 2:
            continue
        case_id = f"link-{idx // window_size:03d}"
        cases.append(
            EvalCase(
                case_id=case_id,
                stage="linking",
                input_payload={
                    "notes": [
                        {
                            "id": note.id,
                            "title": note.title,
                            "body": note.body[:700],
                            "tags": note.frontmatter.tags,
                        }
                        for note in window
                    ]
                },
                expected={
                    "min_links": 1,
                    "max_links": len(window) * 2,
                },
                tags=["checkpoint-derived"],
            )
        )
        if len(cases) >= limit:
            break
    return cases


def _build_validation_cases(state, limit: int) -> list[EvalCase]:
    if state is None:
        return []

    notes = state.final_notes or state.draft_notes
    cases: list[EvalCase] = []
    for note in notes[:limit]:
        cases.append(
            EvalCase(
                case_id=f"val-{note.id}",
                stage="validation",
                input_payload={
                    "note_id": note.id,
                    "title": note.title,
                    "body": note.body[:1200],
                    "note_type": note.type,
                },
                expected={
                    "should_have_expansion_prompts": note.type == "fleeting",
                },
                tags=[note.type],
            )
        )
    return cases


def _write_cases(path: Path, cases: list[EvalCase]) -> None:
    lines = [json.dumps(case.model_dump(mode="json"), ensure_ascii=False) for case in cases]
    if lines:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        path.write_text("", encoding="utf-8")
