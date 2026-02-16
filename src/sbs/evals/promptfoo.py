"""Promptfoo subprocess integration and result parsing."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from sbs.models.evals import StageMetrics


class PromptfooError(RuntimeError):
    """Error raised when promptfoo execution fails."""


def ensure_promptfoo_installed() -> None:
    """Raise when promptfoo CLI is not available in PATH."""
    if shutil.which("promptfoo") is None:
        raise PromptfooError(
            "promptfoo CLI was not found in PATH. Install it with: npm i -g promptfoo"
        )


def run_promptfoo_eval(
    config_path: Path,
    output_path: Path,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run promptfoo eval and return parsed JSON output."""
    ensure_promptfoo_installed()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "promptfoo",
        "eval",
        "-c",
        str(config_path),
        "--output",
        str(output_path),
    ]
    process = subprocess.run(  # noqa: S603
        command,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if process.returncode != 0:
        raise PromptfooError(
            f"promptfoo eval failed for {config_path}:\n{process.stderr.strip()}"
        )

    if output_path.exists():
        return json.loads(output_path.read_text(encoding="utf-8"))

    # Fallback when CLI prints JSON to stdout without writing output.
    stdout = process.stdout.strip()
    if stdout:
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            return {"stdout": stdout}

    return {}


def parse_promptfoo_metrics(payload: dict[str, Any]) -> tuple[StageMetrics, float, float]:
    """Extract score/pass-rate/cost/latency from promptfoo JSON payload."""
    results = _extract_result_rows(payload)
    total = len(results)

    passed = 0
    numeric_scores: list[float] = []
    for row in results:
        pass_value = row.get("pass")
        if pass_value is None:
            pass_value = row.get("success")
        if pass_value is True:
            passed += 1

        score_value = row.get("score")
        if isinstance(score_value, (int, float)):
            numeric_scores.append(float(score_value))

    pass_rate = (passed / total) if total else 0.0
    # Match quality score scale used in the rest of this project.
    score = sum(numeric_scores) / len(numeric_scores) if numeric_scores else pass_rate * 100.0

    cost = _extract_numeric(payload, ["cost", "stats.cost", "results.stats.cost"], 0.0)
    latency = _extract_numeric(
        payload,
        ["latency", "stats.latencyMs", "results.stats.latencyMs"],
        0.0,
    )
    # Convert ms to seconds when value is likely ms scale.
    if latency > 10:
        latency = latency / 1000.0

    return (
        StageMetrics(
            score=score,
            pass_rate=pass_rate,
            total_cases=total,
            passed_cases=passed,
        ),
        cost,
        latency,
    )


def _extract_result_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key_path in [
        "results",
        "data.results",
        "results.results",
    ]:
        value = _extract_path(payload, key_path)
        if isinstance(value, list):
            rows = [row for row in value if isinstance(row, dict)]
            if rows:
                return rows
    return []


def _extract_numeric(payload: dict[str, Any], paths: list[str], default: float) -> float:
    for key_path in paths:
        value = _extract_path(payload, key_path)
        if isinstance(value, (int, float)):
            return float(value)
    return default


def _extract_path(payload: dict[str, Any], key_path: str) -> Any:
    current: Any = payload
    for key in key_path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current
