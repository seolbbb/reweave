"""Parser protocol — interface for conversation file parsers."""

from __future__ import annotations

from typing import Protocol

from sbs.models.conversation import NormalizedConversation


class ConversationParser(Protocol):
    """Protocol for parsing exported conversation files."""

    def can_parse(self, data: dict | list) -> bool:
        """Return True if this parser can handle the given data structure."""
        ...

    def parse(self, data: dict | list, source_path: str = "") -> list[NormalizedConversation]:
        """Parse raw JSON data into normalized conversations."""
        ...
