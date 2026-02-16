"""Tests for eval dataset builder and local tracker."""

from __future__ import annotations

import json
from pathlib import Path

from sbs.config import Config
from sbs.evals.dataset_builder import build_eval_datasets
from sbs.evals.tracker import EvalTracker, compute_dataset_hash
from sbs.models.evals import EvalRun, StageMetrics
from sbs.models.pipeline import PipelineState
from sbs.pipeline.checkpoint import CheckpointManager


def test_build_eval_datasets_from_input_only(tmp_path: Path, chatgpt_sample_path: Path):
    input_dir = tmp_path / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    (input_dir / "chatgpt_sample.json").write_text(
        chatgpt_sample_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    output_dir = tmp_path / "evals" / "datasets"
    counts = build_eval_datasets(input_dir=input_dir, output_dir=output_dir)

    assert counts["segmentation"] > 0
    assert (output_dir / "segmentation_cases.jsonl").exists()
    assert (output_dir / "extraction_cases.jsonl").exists()


def test_build_eval_datasets_with_checkpoint(tmp_path: Path, chatgpt_sample_path: Path):
    input_dir = tmp_path / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    (input_dir / "chatgpt_sample.json").write_text(
        chatgpt_sample_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    checkpoint_dir = tmp_path / "checkpoints"
    manager = CheckpointManager(checkpoint_dir)
    state = PipelineState(config=Config(input_dir=input_dir))
    manager.save(state, stage=0)

    output_dir = tmp_path / "evals" / "datasets"
    counts = build_eval_datasets(
        input_dir=input_dir,
        output_dir=output_dir,
        checkpoint_path=checkpoint_dir,
    )

    assert counts["segmentation"] > 0
    # Empty state still yields deterministic files.
    assert counts["extraction"] == 0


def test_compute_dataset_hash_changes_on_update(tmp_path: Path):
    dataset_dir = tmp_path / "datasets"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    file_path = dataset_dir / "segmentation_cases.jsonl"
    file_path.write_text('{"case_id":"1"}\n', encoding="utf-8")

    hash1 = compute_dataset_hash(dataset_dir)
    file_path.write_text('{"case_id":"2"}\n', encoding="utf-8")
    hash2 = compute_dataset_hash(dataset_dir)

    assert hash1 != hash2


def test_eval_tracker_save_and_load_latest(tmp_path: Path):
    tracker = EvalTracker(tmp_path / "runs")
    run = EvalRun(
        run_id=tracker.new_run_id(),
        bundle_id="default",
        dataset_hash="abcd1234efgh5678",
        stage="all",
        metrics={
            "segmentation": StageMetrics(score=90.0, pass_rate=0.9, total_cases=10, passed_cases=9)
        },
        global_score=90.0,
        estimated_cost_usd=1.23,
        latency_seconds=4.56,
        metadata={"source": "test"},
    )

    run_dir = tracker.save_run(run, decision={"passed": True})
    assert (run_dir / "metadata.json").exists()
    assert (run_dir / "scores.json").exists()
    assert (run_dir / "cost_latency.json").exists()
    assert (run_dir / "winner_decision.json").exists()

    latest = tracker.load_latest()
    assert latest is not None
    assert latest.run_id == run.run_id

    leaderboard = tracker.list_leaderboard(limit=5)
    assert len(leaderboard) == 1
    assert leaderboard[0].bundle_id == "default"


def test_eval_tracker_leaderboard_jsonl_format(tmp_path: Path):
    tracker = EvalTracker(tmp_path / "runs")
    run = EvalRun(run_id=tracker.new_run_id(), bundle_id="b1", dataset_hash="h1")
    tracker.save_run(run)

    lines = (tmp_path / "runs" / "leaderboard.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["bundle_id"] == "b1"
