"""ChatGPT conversations.json parser ??handles tree-structured mapping format."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from reweave.models.conversation import NormalizedConversation, NormalizedMessage


class ChatGPTParser:
    """Parse ChatGPT exported conversations.json files."""

    def can_parse(self, data: dict | list) -> bool:
        """Check if data looks like ChatGPT export (list of objects with 'mapping' key)."""
        if not isinstance(data, list):
            return False
        if len(data) == 0:
            return True
        return isinstance(data[0], dict) and "mapping" in data[0]

    def parse(self, data: dict | list, source_path: str = "") -> list[NormalizedConversation]:
        """Parse ChatGPT conversations.json into normalized conversations."""
        if not isinstance(data, list):
            return []
        conversations = []
        for raw_conv in data:
            conv = self._parse_conversation(raw_conv, source_path)
            if conv and len(conv.messages) > 0:
                conversations.append(conv)
        return conversations

    def _parse_conversation(
        self, raw: dict[str, Any], source_path: str
    ) -> NormalizedConversation | None:
        mapping = raw.get("mapping", {})
        if not mapping:
            return None

        title = raw.get("title", "Untitled")
        create_time = raw.get("create_time")
        update_time = raw.get("update_time")

        created_at = self._unix_to_iso(create_time) if create_time else ""
        updated_at = self._unix_to_iso(update_time) if update_time else None

        messages = self._linearize_mapping(mapping, raw.get("current_node"))

        source_id = str(raw.get("id") or raw.get("conversation_id") or "") or None
        conv_id = self._make_id("chatgpt", source_id or created_at)
        return NormalizedConversation(
            id=conv_id,
            source_id=source_id,
            title=title,
            source="chatgpt",
            created_at=created_at,
            updated_at=updated_at,
            messages=messages,
            raw_message_count=len(messages),
            metadata={"source_path": source_path},
        )

    def _linearize_mapping(
        self,
        mapping: dict[str, Any],
        current_node: str | None = None,
    ) -> list[NormalizedMessage]:
        """Return the active branch, preferring ChatGPT's explicit current node."""
        if current_node and current_node in mapping:
            path: list[str] = []
            seen: set[str] = set()
            node_id: str | None = current_node
            while node_id and node_id in mapping and node_id not in seen:
                seen.add(node_id)
                path.append(node_id)
                node_id = mapping[node_id].get("parent")

            messages: list[NormalizedMessage] = []
            for active_node_id in reversed(path):
                node = mapping[active_node_id]
                msg_data = node.get("message")
                if msg_data is None:
                    continue
                normalized = self._extract_message(msg_data, active_node_id)
                if normalized is not None:
                    messages.append(normalized)
            return messages

        # Find root node (parent is None or "")
        root_id = None
        for node_id, node in mapping.items():
            parent = node.get("parent")
            if parent is None or parent == "":
                root_id = node_id
                break

        if root_id is None:
            return []

        messages: list[NormalizedMessage] = []
        self._dfs(mapping, root_id, messages)
        return messages

    def _dfs(
        self, mapping: dict[str, Any], node_id: str, messages: list[NormalizedMessage]
    ) -> None:
        node = mapping.get(node_id)
        if node is None:
            return

        msg_data = node.get("message")
        if msg_data is not None:
            normalized = self._extract_message(msg_data, node_id)
            if normalized is not None:
                messages.append(normalized)

        # Follow first child path (linear conversation ??pick first child)
        children = node.get("children", [])
        if children:
            # Follow the last child (most recent branch in ChatGPT exports)
            self._dfs(mapping, children[-1], messages)

    def _extract_message(
        self,
        msg: dict[str, Any],
        node_id: str | None = None,
    ) -> NormalizedMessage | None:
        author_role = msg.get("author", {}).get("role", "")
        if author_role not in ("user", "assistant", "system", "tool"):
            return None

        content = msg.get("content", {})
        parts = content.get("parts", [])
        text = self._join_parts(parts)

        if not text.strip():
            return None

        create_time = msg.get("create_time")
        timestamp = self._unix_to_iso(create_time) if create_time else None

        return NormalizedMessage(
            role=author_role,
            content=text,
            timestamp=timestamp,
            source_id=str(msg.get("id") or node_id or "") or None,
        )

    @staticmethod
    def _join_parts(parts: list[Any]) -> str:
        """Join content parts, skipping non-string items (images, etc.)."""
        text_parts = []
        for part in parts:
            if isinstance(part, str):
                text_parts.append(part)
            elif isinstance(part, dict):
                # Some parts are dicts with text content
                text = part.get("text", "")
                if text:
                    text_parts.append(text)
        return "\n".join(text_parts)

    @staticmethod
    def _unix_to_iso(ts: float | int | None) -> str:
        if ts is None:
            return ""
        return datetime.fromtimestamp(ts, tz=UTC).isoformat()

    @staticmethod
    def _make_id(source: str, stable_source_value: str) -> str:
        raw = f"{source}:{stable_source_value}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
