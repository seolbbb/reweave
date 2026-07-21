"""Provider-neutral whole-conversation capture models."""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from reweave.models.conversation import NormalizedConversation, NormalizedMessage

MAX_CAPTURE_CONTENT_CHARS = 20_000_000


class CapturedMessage(BaseModel):
    """One ordered message supplied by a supported web-chat adapter."""

    model_config = ConfigDict(extra="forbid")

    external_id: str | None = Field(default=None, max_length=512)
    role: Literal["user", "assistant", "system", "tool"]
    content: str = Field(min_length=1, max_length=1_000_000)
    timestamp: str | None = Field(default=None, max_length=64)

    @field_validator("external_id")
    @classmethod
    def normalize_optional_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Message external ID cannot be blank when provided.")
        return normalized

    @field_validator("content")
    @classmethod
    def require_visible_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Captured message content cannot be blank.")
        return value

    @field_validator("timestamp")
    @classmethod
    def validate_optional_timestamp(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _require_aware_iso_timestamp(value, "Message timestamp")


class ConversationCapture(BaseModel):
    """A complete current ChatGPT or Claude conversation captured after explicit Save."""

    model_config = ConfigDict(extra="forbid")

    provider: Literal["chatgpt", "claude"]
    external_id: str = Field(min_length=1, max_length=512)
    title: str = Field(min_length=1, max_length=4_000)
    created_at: str = Field(min_length=1, max_length=64)
    updated_at: str | None = Field(default=None, max_length=64)
    messages: list[CapturedMessage] = Field(min_length=1, max_length=5_000)

    @field_validator("external_id", "title")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Capture identity and title cannot be blank.")
        return normalized

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: str) -> str:
        return _require_aware_iso_timestamp(value, "Conversation created_at")

    @field_validator("updated_at")
    @classmethod
    def validate_updated_at(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _require_aware_iso_timestamp(value, "Conversation updated_at")

    @model_validator(mode="after")
    def validate_message_set(self) -> Self:
        external_ids = [message.external_id for message in self.messages if message.external_id]
        if len(external_ids) != len(set(external_ids)):
            raise ValueError("Captured message external IDs must be unique within a conversation.")
        if sum(len(message.content) for message in self.messages) > MAX_CAPTURE_CONTENT_CHARS:
            raise ValueError(
                f"Captured conversation content exceeds {MAX_CAPTURE_CONTENT_CHARS} characters."
            )
        return self

    def to_normalized(self) -> NormalizedConversation:
        """Convert the validated boundary payload to the archive's shared model."""
        archive_id = sha256(f"{self.provider}:{self.external_id}".encode()).hexdigest()[:16]
        return NormalizedConversation(
            id=archive_id,
            source_id=self.external_id,
            title=self.title,
            source=self.provider,
            created_at=self.created_at,
            updated_at=self.updated_at,
            messages=[
                NormalizedMessage(
                    role=message.role,
                    content=message.content,
                    timestamp=message.timestamp,
                    source_id=message.external_id,
                )
                for message in self.messages
            ],
            raw_message_count=len(self.messages),
            metadata={"capture": "explicit-web-save"},
        )


def _require_aware_iso_timestamp(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be blank.")
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO 8601 timestamp.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone offset.")
    return normalized
