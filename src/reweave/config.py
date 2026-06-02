"""Configuration defaults for the local archive CLI."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()


class Config(BaseModel):
    """Global configuration for local archive operations."""

    input_dir: Path = Field(default=Path("."))
    db_path: Path = Field(
        default_factory=lambda: Path(os.getenv("REWEAVE_DB", "./reweave.db"))
    )
    output_dir: Path = Field(
        default_factory=lambda: Path(os.getenv("REWEAVE_EXPORT_DIR", "./exports"))
    )
    llm_provider: str = Field(
        default_factory=lambda: os.getenv("REWEAVE_LLM_PROVIDER", "openai")
    )
    llm_model: str = Field(
        default_factory=lambda: os.getenv("REWEAVE_LLM_MODEL", "gpt-4o-mini")
    )
    llm_base_url: str = Field(default_factory=lambda: os.getenv("REWEAVE_LLM_BASE_URL", ""))
    llm_api_key: str = Field(default_factory=lambda: os.getenv("REWEAVE_LLM_API_KEY", ""))
    llm_max_context_chars: int = Field(
        default_factory=lambda: int(os.getenv("REWEAVE_LLM_MAX_CONTEXT_CHARS", "80000"))
    )
    llm_temperature: float = Field(
        default_factory=lambda: float(os.getenv("REWEAVE_LLM_TEMPERATURE", "0.2"))
    )
    verbose: bool = False
