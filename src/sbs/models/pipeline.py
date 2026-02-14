"""Pipeline state — the shared state object passed between stages."""

from __future__ import annotations

from pydantic import BaseModel, Field

from sbs.config import Config
from sbs.models.conversation import NormalizedConversation
from sbs.models.extraction import ExtractedKnowledge
from sbs.models.note import MOC, DraftNote, NoteLink
from sbs.models.segment import Segment


class TokenUsage(BaseModel):
    """Token usage for a single LLM call."""

    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""


class CostSummary(BaseModel):
    """Accumulated cost tracking across all LLM calls."""

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    calls: list[TokenUsage] = Field(default_factory=list)
    estimated_cost_usd: float = 0.0


class ValidationIssue(BaseModel):
    """A single issue found during validation."""

    severity: str  # "warning" or "error"
    category: str
    message: str
    note_id: str | None = None


class ValidationReport(BaseModel):
    """Quality validation report for the generated vault."""

    score: float = 0.0  # 0-100
    issues: list[ValidationIssue] = Field(default_factory=list)
    total_notes: int = 0
    fleeting_notes: int = 0
    permanent_notes: int = 0
    total_links: int = 0
    orphan_notes: int = 0
    literature_references: int = 0
    sampled_atomicity_pass_rate: float = 0.0


class PipelineState(BaseModel):
    """The complete shared state for the conversion pipeline."""

    config: Config
    started_at: str = ""
    completed_stages: list[int] = Field(default_factory=list)
    conversations: list[NormalizedConversation] = Field(default_factory=list)
    segments: list[Segment] = Field(default_factory=list)
    extractions: list[ExtractedKnowledge] = Field(default_factory=list)
    draft_notes: list[DraftNote] = Field(default_factory=list)
    source_notes: list[DraftNote] = Field(default_factory=list)
    literature_notes: list[DraftNote] = Field(default_factory=list)
    links: list[NoteLink] = Field(default_factory=list)
    mocs: list[MOC] = Field(default_factory=list)
    final_notes: list[DraftNote] = Field(default_factory=list)
    validation_report: ValidationReport | None = None
    cost: CostSummary = Field(default_factory=CostSummary)
    input_hash: str = ""  # Hash of input files for resume validation
