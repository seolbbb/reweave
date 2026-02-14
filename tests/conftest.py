"""Shared test fixtures."""

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def fixtures_dir():
    """Return the path to test fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture()
def chatgpt_sample_path():
    """Return path to ChatGPT sample JSON."""
    return FIXTURES_DIR / "chatgpt_sample.json"


@pytest.fixture()
def claude_sample_path():
    """Return path to Claude sample JSON."""
    return FIXTURES_DIR / "claude_sample.json"
