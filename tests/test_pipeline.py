"""Tests for pipeline infrastructure — checkpoint and runner."""

import json
from pathlib import Path

import pytest

from sbs.config import Config
from sbs.models.pipeline import PipelineState
from sbs.pipeline.checkpoint import CheckpointManager


class TestCheckpointManager:
    @pytest.fixture()
    def tmp_checkpoint_dir(self, tmp_path):
        return tmp_path / "checkpoints"

    @pytest.fixture()
    def manager(self, tmp_checkpoint_dir):
        return CheckpointManager(tmp_checkpoint_dir)

    @pytest.fixture()
    def sample_state(self):
        config = Config(input_dir=Path("."), output_dir=Path("./vault"))
        state = PipelineState(config=config, started_at="2026-01-01T00:00:00Z")
        state.completed_stages = [0, 1]
        return state

    def test_save_creates_file(self, manager, sample_state, tmp_checkpoint_dir):
        path = manager.save(sample_state, stage=1)
        assert path.exists()
        assert "stage-1" in path.name

    def test_save_creates_latest(self, manager, sample_state, tmp_checkpoint_dir):
        manager.save(sample_state, stage=1)
        latest = tmp_checkpoint_dir / "latest.json"
        assert latest.exists()

    def test_load_roundtrip(self, manager, sample_state):
        path = manager.save(sample_state, stage=1)
        loaded = manager.load(path)
        assert loaded.completed_stages == [0, 1]
        assert loaded.started_at == "2026-01-01T00:00:00Z"

    def test_load_from_directory(self, manager, sample_state, tmp_checkpoint_dir):
        manager.save(sample_state, stage=1)
        loaded = manager.load(tmp_checkpoint_dir)
        assert loaded.completed_stages == [0, 1]

    def test_latest(self, manager, sample_state):
        assert manager.latest() is None
        manager.save(sample_state, stage=0)
        loaded = manager.latest()
        assert loaded is not None
        assert loaded.completed_stages == [0, 1]

    def test_input_hash(self, tmp_path):
        # Create fake input files
        (tmp_path / "a.json").write_text("{}", encoding="utf-8")
        (tmp_path / "b.json").write_text("{}", encoding="utf-8")

        hash1 = CheckpointManager.compute_input_hash(tmp_path)
        assert len(hash1) == 16

        # Same files → same hash
        hash2 = CheckpointManager.compute_input_hash(tmp_path)
        assert hash1 == hash2

    def test_checkpoint_json_valid(self, manager, sample_state, tmp_checkpoint_dir):
        path = manager.save(sample_state, stage=1)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "config" in data
        assert "completed_stages" in data
