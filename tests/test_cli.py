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


def test_convert_google_quota_options_are_wired(monkeypatch, tmp_path: Path):
    captured: dict[str, int | float | bool] = {}

    async def fake_run_pipeline(config):
        captured["rpm"] = config.google_rpm_limit
        captured["tpm"] = config.google_tpm_limit
        captured["rpd"] = config.google_rpd_limit
        captured["headroom"] = config.google_quota_headroom
        captured["enforce"] = config.google_enforce_quota
        return None

    monkeypatch.setattr("sbs.pipeline.runner.run_pipeline", fake_run_pipeline)

    result = runner.invoke(
        app,
        [
            "convert",
            str(tmp_path),
            "--provider",
            "google",
            "--google-rpm-limit",
            "1200",
            "--google-tpm-limit",
            "900000",
            "--google-rpd-limit",
            "20000",
            "--google-quota-headroom",
            "0.75",
            "--no-google-enforce-quota",
        ],
    )

    assert result.exit_code == 0
    assert captured == {
        "rpm": 1200,
        "tpm": 900000,
        "rpd": 20000,
        "headroom": 0.75,
        "enforce": False,
    }
