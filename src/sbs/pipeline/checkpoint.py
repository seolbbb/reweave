"""Checkpoint manager — save and load pipeline state as JSON."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from sbs.models.pipeline import PipelineState


class CheckpointManager:
    """Save and load pipeline state checkpoints."""

    def __init__(self, checkpoint_dir: Path):
        self._dir = checkpoint_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def save(self, state: PipelineState, stage: int) -> Path:
        """Save state after completing a stage."""
        ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d%H%M%S")
        filename = f"checkpoint-stage-{stage}-{ts}.json"
        path = self._dir / filename
        path.write_text(state.model_dump_json(indent=2), encoding="utf-8")

        # Also write a "latest" symlink/copy
        latest = self._dir / "latest.json"
        latest.write_text(state.model_dump_json(indent=2), encoding="utf-8")

        return path

    def load(self, path: Path) -> PipelineState:
        """Load state from a checkpoint file."""
        if path.is_dir():
            path = path / "latest.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        return PipelineState.model_validate(data)

    def latest(self) -> PipelineState | None:
        """Load the latest checkpoint if it exists."""
        latest = self._dir / "latest.json"
        if latest.exists():
            return self.load(latest)
        return None

    @staticmethod
    def compute_input_hash(input_dir: Path) -> str:
        """Compute a hash of input files for resume validation."""
        h = hashlib.sha256()
        for f in sorted(input_dir.glob("*.json")):
            h.update(f.name.encode())
            h.update(str(f.stat().st_size).encode())
        return h.hexdigest()[:16]
