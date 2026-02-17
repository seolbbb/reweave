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
    "google": ("gemini-3-pro-preview", "gemini-3-flash-preview"),
}

GOOGLE_MODEL_ALIASES: dict[str, str] = {
    "gemini-3-pro": "gemini-3-pro-preview",
    "gemini-3-flash": "gemini-3-flash-preview",
}

_PROVIDER_CONCURRENCY_DEFAULTS: dict[str, int] = {
    "anthropic": 10,
    "openai": 15,
    "google": 15,
}

# Sentinel indicating the user did NOT explicitly set --concurrency.
_DEFAULT_CONCURRENCY = 3


class Config(BaseModel):
    """Global configuration for the SBS pipeline."""

    # Input / Output
    input_dir: Path = Field(default=Path("."))
    output_dir: Path = Field(default=Path("./vault"))
    checkpoint_dir: Path = Field(default=Path("./.sbs-checkpoints"))
    prompt_bundle: Path | None = Field(
        default_factory=lambda: (
            Path(os.getenv("SBS_PROMPT_BUNDLE", ""))
            if os.getenv("SBS_PROMPT_BUNDLE", "")
            else None
        )
    )

    # LLM
    provider: Literal["anthropic", "openai", "google"] = Field(
        default_factory=lambda: os.getenv("SBS_PROVIDER", "anthropic")  # type: ignore[return-value]
    )
    model: str = Field(default_factory=lambda: os.getenv("SBS_MODEL", ""))
    cheap_model: str = Field(default_factory=lambda: os.getenv("SBS_CHEAP_MODEL", ""))
    concurrency: int | None = Field(default=None, ge=1, le=50)

    # Stage 1 micro-batching
    stage1_batch_enabled: bool = Field(default=True)
    stage1_batch_max_items: int = Field(default=4, ge=1, le=20)
    stage1_batch_input_token_budget: int = Field(default=12000, ge=1000, le=200000)
    stage1_batch_split_retries: int = Field(default=3, ge=0, le=10)

    # Per-stage concurrency overrides (None = use resolved default)
    stage2_concurrency: int | None = Field(default=None, ge=1, le=50)
    stage3_concurrency: int | None = Field(default=None, ge=1, le=50)

    # Stage 2 micro-batching
    stage2_batch_enabled: bool = Field(default=False)
    stage2_batch_max_items: int = Field(default=8, ge=1, le=20)
    stage2_batch_input_token_budget: int = Field(default=20000, ge=1000, le=200000)

    # Stage 3 micro-batching
    stage3_batch_enabled: bool = Field(default=False)
    stage3_batch_max_items: int = Field(default=6, ge=1, le=20)
    stage3_batch_input_token_budget: int = Field(default=24000, ge=1000, le=200000)

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

        # Backward compatibility for older Google model names stored in .env files.
        if self.provider == "google":
            self.model = GOOGLE_MODEL_ALIASES.get(self.model, self.model)
            self.cheap_model = GOOGLE_MODEL_ALIASES.get(self.cheap_model, self.cheap_model)

        # Apply provider-aware concurrency when caller did not provide an override.
        if self.concurrency is None:
            self.concurrency = _PROVIDER_CONCURRENCY_DEFAULTS.get(
                self.provider, _DEFAULT_CONCURRENCY
            )

        return self

    def resolve_stage2_concurrency(self) -> int:
        """Resolve effective concurrency for Stage 2."""
        if self.stage2_concurrency is not None:
            return self.stage2_concurrency
        assert self.concurrency is not None
        return self.concurrency

    def resolve_stage3_concurrency(self) -> int:
        """Resolve effective concurrency for Stage 3."""
        if self.stage3_concurrency is not None:
            return self.stage3_concurrency
        assert self.concurrency is not None
        return self.concurrency
