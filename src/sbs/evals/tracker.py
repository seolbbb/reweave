"""Local file-based tracking for prompt evaluation runs."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sbs.models.evals import EvalRun


def compute_dataset_hash(dataset_dir: Path) -> str:
    """Compute deterministic hash for dataset files."""
    h = hashlib.sha256()
    for file in sorted(dataset_dir.glob("*.jsonl")):
        h.update(file.name.encode("utf-8"))
        h.update(file.read_bytes())
    return h.hexdigest()[:16]


class EvalTracker:
    """Persist eval runs and a lightweight leaderboard under evals/runs/."""

    def __init__(self, runs_dir: Path):
        self._runs_dir = runs_dir
        self._runs_dir.mkdir(parents=True, exist_ok=True)
        self._leaderboard = self._runs_dir / "leaderboard.jsonl"

    def new_run_id(self) -> str:
        now = datetime.now(tz=UTC)
        return now.strftime("%Y%m%d-%H%M%S")

    def save_run(
        self,
        run: EvalRun,
        decision: dict[str, Any] | None = None,
    ) -> Path:
        """Save a run artifact set and append summary to leaderboard."""
        run_dir = self._runs_dir / run.run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        metadata = {
            "run_id": run.run_id,
            "bundle_id": run.bundle_id,
            "dataset_hash": run.dataset_hash,
            "stage": run.stage,
            "metadata": run.metadata,
        }
        (run_dir / "metadata.json").write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        scores = {
            "global_score": run.global_score,
            "metrics": {
                stage: metric.model_dump(mode="json")
                for stage, metric in run.metrics.items()
            },
        }
        (run_dir / "scores.json").write_text(
            json.dumps(scores, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        cost_latency = {
            "estimated_cost_usd": run.estimated_cost_usd,
            "latency_seconds": run.latency_seconds,
        }
        (run_dir / "cost_latency.json").write_text(
            json.dumps(cost_latency, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        if decision:
            (run_dir / "winner_decision.json").write_text(
                json.dumps(decision, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

        self._append_leaderboard(run)
        (self._runs_dir / "latest.json").write_text(
            run.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return run_dir

    def load_latest(self) -> EvalRun | None:
        """Load latest run snapshot if available."""
        latest = self._runs_dir / "latest.json"
        if not latest.exists():
            return None
        data = json.loads(latest.read_text(encoding="utf-8"))
        return EvalRun.model_validate(data)

    def list_leaderboard(self, limit: int = 20) -> list[EvalRun]:
        """Load most recent runs from leaderboard."""
        if not self._leaderboard.exists():
            return []

        lines = self._leaderboard.read_text(encoding="utf-8").splitlines()
        rows = []
        for line in lines[-limit:]:
            line = line.strip()
            if not line:
                continue
            rows.append(EvalRun.model_validate_json(line))
        return rows[::-1]

    def _append_leaderboard(self, run: EvalRun) -> None:
        with self._leaderboard.open("a", encoding="utf-8") as f:
            f.write(run.model_dump_json())
            f.write("\n")
