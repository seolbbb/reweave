"""Configuration loading from environment variables and CLI options."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field, model_validator

load_dotenv()

PROVIDER_DEFAULT_MODELS: dict[str, tuple[str, str]] = {
    "anthropic": ("claude-sonnet-4-5-20250929", "claude-haiku-4-5-20251001"),
    "openai": ("gpt-4o", "gpt-4o-mini"),
    "google": ("gemini-3-pro", "gemini-3-flash"),
}


class Config(BaseModel):
    """Global configuration for the SBS pipeline."""

    # Input / Output
    input_dir: Path = Field(default=Path("."))
    output_dir: Path = Field(default=Path("./vault"))
    checkpoint_dir: Path = Field(default=Path("./.sbs-checkpoints"))

    # LLM
    provider: Literal["anthropic", "openai", "google"] = Field(
        default_factory=lambda: os.getenv("SBS_PROVIDER", "anthropic")  # type: ignore[return-value]
    )
    model: str = Field(default_factory=lambda: os.getenv("SBS_MODEL", ""))
    cheap_model: str = Field(default_factory=lambda: os.getenv("SBS_CHEAP_MODEL", ""))
    concurrency: int = Field(default=3, ge=1, le=20)

    # API keys (resolved at runtime)
    anthropic_api_key: str = Field(
        default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", "")
    )
    openai_api_key: str = Field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY", "")
    )
    google_api_key: str = Field(
        default_factory=lambda: os.getenv("GOOGLE_API_KEY", "")
    )

    # Flags
    dry_run: bool = False
    verbose: bool = False

    @model_validator(mode="after")
    def apply_provider_defaults(self) -> Config:
        """Apply provider-specific defaults unless explicit model names were provided."""
        default_main, default_cheap = PROVIDER_DEFAULT_MODELS[self.provider]
        if not self.model:
            self.model = default_main
        if not self.cheap_model:
            self.cheap_model = default_cheap
        return self
