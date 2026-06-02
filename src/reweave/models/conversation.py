"""Normalized conversation models for unified representation of ChatGPT/Claude data."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class NormalizedMessage(BaseModel):
    """A single message in a conversation, normalized across providers."""

    role: Literal["user", "assistant", "system", "tool"]
    content: str
    timestamp: str | None = None  # ISO 8601
    metadata: dict[str, Any] = Field(default_factory=dict)


class NormalizedConversation(BaseModel):
    """A full conversation, normalized from ChatGPT or Claude export format."""

    id: str  # Deterministic hash from source + title + created_at
    title: str
    source: Literal["chatgpt", "claude"]
    created_at: str  # ISO 8601
    updated_at: str | None = None
    messages: list[NormalizedMessage]
    raw_message_count: int
    metadata: dict[str, Any] = Field(default_factory=dict)
