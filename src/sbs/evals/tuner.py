"""Prompt candidate generation and promotion gating."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

from sbs.models.evals import EvalRun, PromotionDecision
from sbs.prompting.registry import PromptBundle, write_prompt_bundle

IMPROVEMENT_TARGET = 2.0
MAX_STAGE_DROP = 1.0
COST_CAP_RATIO = 0.15

_PROMPT_MUTATION_SUFFIXES = [
    "\n\nAdditional rule: prefer explicit, verifiable statements over vague wording.",
    (
        "\n\nAdditional rule: if information is missing, "
        "return conservative output instead of guessing."
    ),
    "\n\nAdditional rule: keep outputs concise while preserving all required fields.",
    "\n\nAdditional rule: prioritize consistency with provided source context.",
]


def generate_candidate_bundles(
    baseline: PromptBundle,
    count: int = 8,
    bundle_prefix: str | None = None,
) -> list[PromptBundle]:
    """Generate deterministic prompt candidates from a baseline bundle."""
    if count < 1:
        return []

    keys = sorted(baseline.prompts)
    prefix = bundle_prefix or baseline.bundle_id
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%d%H%M%S")

    candidates: list[PromptBundle] = []
    for idx in range(count):
        key = keys[idx % len(keys)]
        suffix = _PROMPT_MUTATION_SUFFIXES[idx % len(_PROMPT_MUTATION_SUFFIXES)]
        prompts = deepcopy(baseline.prompts)
        prompts[key] = prompts[key].rstrip() + suffix
        candidates.append(
            PromptBundle(
                bundle_id=f"{prefix}-cand-{timestamp}-{idx + 1:02d}",
                prompts=prompts,
            )
        )
    return candidates


def persist_candidates(
    candidates: list[PromptBundle],
    prompts_root: Path,
    overwrite: bool = False,
) -> list[Path]:
    """Write candidate bundles under prompts/bundles/<bundle_id>."""
    written: list[Path] = []
    bundles_dir = prompts_root / "bundles"
    bundles_dir.mkdir(parents=True, exist_ok=True)

    for candidate in candidates:
        target = bundles_dir / candidate.bundle_id
        write_prompt_bundle(candidate, target, overwrite=overwrite)
        written.append(target)

    return written


def evaluate_promotion_gate(
    candidate: EvalRun,
    baseline: EvalRun,
    min_improvement: float = IMPROVEMENT_TARGET,
    max_stage_drop: float = MAX_STAGE_DROP,
    cost_cap_ratio: float = COST_CAP_RATIO,
) -> PromotionDecision:
    """Evaluate candidate run against baseline using quality-first gate."""
    reasons: list[str] = []
    passed = True

    global_delta = candidate.global_score - baseline.global_score
    if global_delta < min_improvement:
        passed = False
        reasons.append(
            f"Global score delta {global_delta:.2f} < required {min_improvement:.2f}."
        )

    common_stages = set(candidate.metrics) & set(baseline.metrics)
    for stage in sorted(common_stages):
        stage_delta = candidate.metrics[stage].score - baseline.metrics[stage].score
        if stage_delta < -max_stage_drop:
            passed = False
            reasons.append(
                f"Stage '{stage}' regressed by {abs(stage_delta):.2f} "
                f"(max allowed {max_stage_drop:.2f})."
            )

    if baseline.estimated_cost_usd > 0:
        max_allowed_cost = baseline.estimated_cost_usd * (1 + cost_cap_ratio)
        if candidate.estimated_cost_usd > max_allowed_cost:
            passed = False
            reasons.append(
                f"Cost ${candidate.estimated_cost_usd:.4f} exceeded cap ${max_allowed_cost:.4f}."
            )

    if passed:
        reasons.append("Candidate passed quality-first promotion gate.")

    return PromotionDecision(
        candidate_bundle=candidate.bundle_id,
        baseline_bundle=baseline.bundle_id,
        passed=passed,
        reasons=reasons,
    )
