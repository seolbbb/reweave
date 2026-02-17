"""CLI tests for option wiring and configuration behavior."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from sbs.cli import app

runner = CliRunner()


def test_convert_uses_provider_default_concurrency_when_omitted(monkeypatch, tmp_path: Path):
    captured: dict[str, int] = {}

    async def fake_run_pipeline(config):
        captured["concurrency"] = config.concurrency
        return None

    monkeypatch.setattr("sbs.pipeline.runner.run_pipeline", fake_run_pipeline)

    result = runner.invoke(
        app,
        ["convert", str(tmp_path), "--provider", "openai"],
    )

    assert result.exit_code == 0
    assert captured["concurrency"] == 15


def test_convert_preserves_explicit_concurrency_even_at_sentinel_value(
    monkeypatch, tmp_path: Path
):
    captured: dict[str, int] = {}

    async def fake_run_pipeline(config):
        captured["concurrency"] = config.concurrency
        return None

    monkeypatch.setattr("sbs.pipeline.runner.run_pipeline", fake_run_pipeline)

    result = runner.invoke(
        app,
        ["convert", str(tmp_path), "--provider", "openai", "--concurrency", "3"],
    )

    assert result.exit_code == 0
    assert captured["concurrency"] == 3
