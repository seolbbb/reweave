"""Configuration loading from environment variables and CLI options."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()


class Config(BaseModel):
    """Global configuration for the SBS pipeline."""

    # Input / Output
    input_dir: Path = Field(default=Path("."))
    output_dir: Path = Field(default=Path("./vault"))
    checkpoint_dir: Path = Field(default=Path("./.sbs-checkpoints"))

    # LLM
    provider: Literal["anthropic", "openai"] = Field(
        default_factory=lambda: os.getenv("SBS_PROVIDER", "anthropic")  # type: ignore[return-value]
    )
    model: str = Field(
        default_factory=lambda: os.getenv("SBS_MODEL", "claude-sonnet-4-5-20250929")
    )
    cheap_model: str = Field(
        default_factory=lambda: os.getenv("SBS_CHEAP_MODEL", "claude-haiku-4-5-20251001")
    )
    concurrency: int = Field(default=3, ge=1, le=20)

    # API keys (resolved at runtime)
    anthropic_api_key: str = Field(
        default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", "")
    )
    openai_api_key: str = Field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY", "")
    )

    # Flags
    dry_run: bool = False
    verbose: bool = False
