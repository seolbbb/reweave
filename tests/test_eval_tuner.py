"""Tests for prompt tuning and promptfoo metric parsing helpers."""

from __future__ import annotations

from pathlib import Path

from sbs.evals.promptfoo import parse_promptfoo_metrics
from sbs.evals.tuner import evaluate_promotion_gate, generate_candidate_bundles, persist_candidates
from sbs.models.evals import EvalRun, StageMetrics
from sbs.prompting.registry import PromptBundle


def _make_run(
    bundle_id: str,
    global_score: float,
    stage_score: float,
    cost: float = 1.0,
) -> EvalRun:
    return EvalRun(
        run_id=f"run-{bundle_id}",
        bundle_id=bundle_id,
        dataset_hash="hash1234567890ab",
        global_score=global_score,
        estimated_cost_usd=cost,
        metrics={
            "segmentation": StageMetrics(
                score=stage_score,
                pass_rate=stage_score / 100.0,
                total_cases=10,
                passed_cases=max(0, min(10, int(stage_score // 10))),
            )
        },
    )


def test_generate_candidate_bundles():
    baseline = PromptBundle(
        bundle_id="base",
        prompts={
            "SEGMENTATION_SYSTEM": "seg prompt",
            "SEGMENTATION_USER": "seg user",
        },
    )
    candidates = generate_candidate_bundles(baseline, count=3)
    assert len(candidates) == 3
    assert all(candidate.bundle_id.startswith("base-cand-") for candidate in candidates)
    assert candidates[0].prompts != baseline.prompts


def test_persist_candidates(tmp_path: Path):
    candidates = [
        PromptBundle(bundle_id="cand-a", prompts={"SEGMENTATION_SYSTEM": "x"}),
        PromptBundle(bundle_id="cand-b", prompts={"SEGMENTATION_SYSTEM": "y"}),
    ]
    paths = persist_candidates(candidates, prompts_root=tmp_path, overwrite=False)
    assert len(paths) == 2
    assert (tmp_path / "bundles" / "cand-a" / "bundle.yaml").exists()
    assert (tmp_path / "bundles" / "cand-b" / "stages").exists()


def test_evaluate_promotion_gate_passes():
    baseline = _make_run("base", global_score=80.0, stage_score=80.0, cost=1.0)
    candidate = _make_run("cand", global_score=83.5, stage_score=80.2, cost=1.12)
    decision = evaluate_promotion_gate(candidate, baseline)
    assert decision.passed is True


def test_evaluate_promotion_gate_blocks_regression():
    baseline = _make_run("base", global_score=80.0, stage_score=80.0, cost=1.0)
    candidate = _make_run("cand", global_score=83.0, stage_score=78.5, cost=1.05)
    decision = evaluate_promotion_gate(candidate, baseline, max_stage_drop=1.0)
    assert decision.passed is False
    assert any("regressed" in reason for reason in decision.reasons)


def test_evaluate_promotion_gate_blocks_cost():
    baseline = _make_run("base", global_score=80.0, stage_score=80.0, cost=1.0)
    candidate = _make_run("cand", global_score=85.0, stage_score=82.0, cost=1.25)
    decision = evaluate_promotion_gate(candidate, baseline, cost_cap_ratio=0.15)
    assert decision.passed is False
    assert any("Cost" in reason for reason in decision.reasons)


def test_parse_promptfoo_metrics_from_rows():
    payload = {
        "results": [
            {"pass": True, "score": 93},
            {"pass": False, "score": 70},
            {"success": True},
        ],
        "stats": {"cost": 0.45, "latencyMs": 2300},
    }
    metrics, cost, latency = parse_promptfoo_metrics(payload)
    assert metrics.total_cases == 3
    assert metrics.passed_cases == 2
    assert metrics.score > 0
    assert abs(cost - 0.45) < 1e-9
    assert abs(latency - 2.3) < 1e-9
