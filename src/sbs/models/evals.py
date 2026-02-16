"""Models for prompt evaluation datasets and experiment runs."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

StageName = Literal["segmentation", "extraction", "synthesis", "linking", "validation", "all"]


class EvalCase(BaseModel):
    """Single evaluation case for a pipeline stage."""

    case_id: str
    stage: StageName
    input_payload: dict[str, Any] = Field(default_factory=dict)
    expected: dict[str, Any] = Field(default_factory=dict)
    weight: float = 1.0
    tags: list[str] = Field(default_factory=list)
    source_ref: str = ""


class StageMetrics(BaseModel):
    """Aggregated metrics for one stage."""

    score: float = 0.0
    pass_rate: float = 0.0
    total_cases: int = 0
    passed_cases: int = 0


class EvalRun(BaseModel):
    """Recorded evaluation run metadata and outcome."""

    run_id: str
    bundle_id: str
    dataset_hash: str
    stage: StageName = "all"
    metrics: dict[str, StageMetrics] = Field(default_factory=dict)
    global_score: float = 0.0
    estimated_cost_usd: float = 0.0
    latency_seconds: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class PromotionDecision(BaseModel):
    """Decision object for candidate prompt promotion."""

    candidate_bundle: str
    baseline_bundle: str
    passed: bool
    reasons: list[str] = Field(default_factory=list)
    approved_by: str = "manual"
