"""Claude JSON parser ??handles Claude's exported conversation format."""

from __future__ import annotations

import hashlib
from typing import Any

from reweave.models.conversation import NormalizedConversation, NormalizedMessage

# Claude export role mapping
_ROLE_MAP = {
    "human": "user",
    "assistant": "assistant",
}


class ClaudeParser:
    """Parse Claude exported conversation JSON files."""

    def can_parse(self, data: dict | list) -> bool:
        """Check if data looks like Claude export (list with 'chat_messages')."""
        if isinstance(data, list):
            if len(data) == 0:
                return False
            return isinstance(data[0], dict) and "chat_messages" in data[0]
        if isinstance(data, dict):
            return "chat_messages" in data
        return False

    def parse(self, data: dict | list, source_path: str = "") -> list[NormalizedConversation]:
        """Parse Claude conversation data into normalized conversations."""
        items = data if isinstance(data, list) else [data]
        conversations = []
        for raw_conv in items:
            conv = self._parse_conversation(raw_conv, source_path)
            if conv and len(conv.messages) > 0:
                conversations.append(conv)
        return conversations

    def _parse_conversation(
        self, raw: dict[str, Any], source_path: str
    ) -> NormalizedConversation | None:
        chat_messages = raw.get("chat_messages", [])
        if not chat_messages:
            return None

        title = raw.get("name", raw.get("title", "Untitled"))
        created_at = raw.get("created_at", "")
        updated_at = raw.get("updated_at")

        messages = []
        for msg in chat_messages:
            normalized = self._extract_message(msg)
            if normalized is not None:
                messages.append(normalized)

        conv_id = self._make_id("claude", title, created_at)
        return NormalizedConversation(
            id=conv_id,
            title=title,
            source="claude",
            created_at=created_at,
            updated_at=updated_at,
            messages=messages,
            raw_message_count=len(messages),
            metadata={"source_path": source_path},
        )

    @staticmethod
    def _extract_message(msg: dict[str, Any]) -> NormalizedMessage | None:
        sender = msg.get("sender", "")
        role = _ROLE_MAP.get(sender)
        if role is None:
            return None

        # Claude messages can have text directly or in content list
        text = msg.get("text", "")
        if not text:
            content = msg.get("content", [])
            if isinstance(content, list):
                text_parts = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
                    elif isinstance(item, str):
                        text_parts.append(item)
                text = "\n".join(text_parts)
            elif isinstance(content, str):
                text = content

        if not text.strip():
            return None

        timestamp = msg.get("created_at") or msg.get("timestamp")

        return NormalizedMessage(
            role=role,
            content=text,
            timestamp=timestamp,
        )

    @staticmethod
    def _make_id(source: str, title: str, created_at: str) -> str:
        raw = f"{source}:{title}:{created_at}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
