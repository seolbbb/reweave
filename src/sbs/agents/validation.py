"""Stage 5 validation agent with type-aware quality checks."""

from __future__ import annotations

import random

from pydantic import BaseModel

from sbs.llm.client import LLMClient
from sbs.llm.prompts import VALIDATION_ATOMICITY_SYSTEM, VALIDATION_ATOMICITY_USER
from sbs.models.note import DraftNote
from sbs.models.pipeline import PipelineState, ValidationIssue, ValidationReport

# Sample 10% of permanent notes for atomicity check (LLM)
ATOMICITY_SAMPLE_RATE = 0.10
MAX_LINKS_PER_NOTE = 15


class AtomicityResult(BaseModel):
    is_atomic: bool = True
    reason: str = ""


async def validate_vault(state: PipelineState, llm: LLMClient) -> ValidationReport:
    """Run all validation checks and produce a report."""
    issues: list[ValidationIssue] = []
    notes = state.final_notes or state.draft_notes
    permanent_notes = [n for n in notes if n.type == "permanent"]
    fleeting_notes = [n for n in notes if n.type == "fleeting"]

    # 1. Frontmatter consistency (deterministic).
    all_authored_notes = notes + state.source_notes + state.literature_notes
    issues.extend(_check_frontmatter(all_authored_notes))

    # 2. Link quality (deterministic, permanent notes only).
    link_issues, orphan_count = _check_links(permanent_notes, state.links)
    issues.extend(link_issues)

    # 3. Completeness (deterministic).
    issues.extend(_check_completeness(state))

    # 4. Atomicity check (LLM, permanent sample only).
    atomicity_pass_rate = await _check_atomicity(permanent_notes, llm)

    total_notes = len(notes)
    error_count = sum(1 for issue in issues if issue.severity == "error")
    warning_count = sum(1 for issue in issues if issue.severity == "warning")

    score = 100.0
    score -= error_count * 10
    score -= warning_count * 2
    score -= (1 - atomicity_pass_rate) * 20
    score = max(0.0, min(100.0, score))

    return ValidationReport(
        score=score,
        issues=issues,
        total_notes=total_notes,
        fleeting_notes=len(fleeting_notes),
        permanent_notes=len(permanent_notes),
        total_links=len(state.links),
        orphan_notes=orphan_count,
        literature_references=_count_literature_references(state),
        sampled_atomicity_pass_rate=atomicity_pass_rate,
    )


def _check_frontmatter(notes: list[DraftNote]) -> list[ValidationIssue]:
    """Validate frontmatter consistency across all note types."""
    issues: list[ValidationIssue] = []
    for note in notes:
        fm = note.frontmatter
        if not fm.created:
            issues.append(
                ValidationIssue(
                    severity="error",
                    category="frontmatter",
                    message="Missing 'created' date",
                    note_id=note.id,
                )
            )

        if note.type == "permanent" and not fm.tags:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    category="frontmatter",
                    message="Permanent note has no tags assigned",
                    note_id=note.id,
                )
            )

        if note.type == "fleeting" and "## Expansion Prompts" not in note.body:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    category="fleeting",
                    message="Fleeting note is missing expansion prompts section",
                    note_id=note.id,
                )
            )

        if note.type == "source" and not fm.source_ref:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    category="source",
                    message="Source note is missing source_ref",
                    note_id=note.id,
                )
            )

    return issues


def _check_links(notes: list[DraftNote], links: list) -> tuple[list[ValidationIssue], int]:
    """Check link quality for permanent notes only."""
    issues: list[ValidationIssue] = []
    note_ids = {note.id for note in notes}

    for link in links:
        if link.source_note_id not in note_ids:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    category="links",
                    message=f"Link source '{link.source_note_id}' not found in permanent notes",
                )
            )
        if link.target_note_id not in note_ids:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    category="links",
                    message=f"Link target '{link.target_note_id}' not found in permanent notes",
                )
            )

    link_count: dict[str, int] = {}
    for link in links:
        link_count[link.source_note_id] = link_count.get(link.source_note_id, 0) + 1
        link_count[link.target_note_id] = link_count.get(link.target_note_id, 0) + 1

    for note_id, count in link_count.items():
        if count > MAX_LINKS_PER_NOTE:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    category="links",
                    message=(
                        f"Permanent note has {count} links "
                        f"(max recommended: {MAX_LINKS_PER_NOTE})"
                    ),
                    note_id=note_id,
                )
            )

    linked_ids = set()
    for link in links:
        linked_ids.add(link.source_note_id)
        linked_ids.add(link.target_note_id)

    orphan_count = len(note_ids - linked_ids)
    if orphan_count > 0:
        issues.append(
            ValidationIssue(
                severity="warning",
                category="links",
                message=f"{orphan_count} permanent orphan note(s) with no links",
            )
        )

    return issues, orphan_count


def _check_completeness(state: PipelineState) -> list[ValidationIssue]:
    """Check that all source conversations have corresponding source notes."""
    issues = []
    conv_ids = {c.id for c in state.conversations}
    source_conv_ids = set()
    for note in state.source_notes:
        for seg_id in note.source_segment_ids:
            conv_id = seg_id.rsplit("-seg-", 1)[0] if "-seg-" in seg_id else seg_id
            source_conv_ids.add(conv_id)

    for note in state.source_notes:
        source_conv_ids.add(note.frontmatter.source_ref)

    missing = conv_ids - source_conv_ids
    if missing:
        issues.append(
            ValidationIssue(
                severity="warning",
                category="completeness",
                message=f"{len(missing)} conversation(s) have no corresponding source note",
            )
        )

    return issues


async def _check_atomicity(notes: list[DraftNote], llm: LLMClient) -> float:
    """Check atomicity of a sample of permanent notes using LLM."""
    if not notes:
        return 1.0

    sample_size = max(1, int(len(notes) * ATOMICITY_SAMPLE_RATE))
    sample = random.sample(notes, min(sample_size, len(notes)))

    passed = 0
    for note in sample:
        user_prompt = VALIDATION_ATOMICITY_USER.format(title=note.title, body=note.body)
        try:
            result, _usage = await llm.cheap_structured_call(
                system=VALIDATION_ATOMICITY_SYSTEM,
                user=user_prompt,
                schema=AtomicityResult,
            )
            if result.is_atomic:
                passed += 1
        except Exception:
            # If LLM call fails, do not penalize the user.
            passed += 1

    return passed / len(sample)


def _count_literature_references(state: PipelineState) -> int:
    """Count extracted literature references across all segments."""
    return sum(len(extraction.references) for extraction in state.extractions)
