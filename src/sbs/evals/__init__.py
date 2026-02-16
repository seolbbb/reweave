"""Evaluation helpers for prompt iteration workflows."""

from sbs.evals.dataset_builder import build_eval_datasets
from sbs.evals.promptfoo import parse_promptfoo_metrics, run_promptfoo_eval
from sbs.evals.tracker import EvalTracker, compute_dataset_hash
from sbs.evals.tuner import evaluate_promotion_gate, generate_candidate_bundles, persist_candidates

__all__ = [
    "EvalTracker",
    "build_eval_datasets",
    "compute_dataset_hash",
    "evaluate_promotion_gate",
    "generate_candidate_bundles",
    "parse_promptfoo_metrics",
    "persist_candidates",
    "run_promptfoo_eval",
]
