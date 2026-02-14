"""Segment model — a topically coherent slice of a conversation."""

from __future__ import annotations

from pydantic import BaseModel

from sbs.models.conversation import NormalizedMessage


class Segment(BaseModel):
    """A topically coherent segment of a conversation."""

    id: str  # "{conversation_id}-seg-{index}"
    conversation_id: str
    topic_label: str
    messages: list[NormalizedMessage]
    start_index: int  # Index within original conversation
    end_index: int
