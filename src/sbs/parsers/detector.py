"""Auto-detect input format and route to the appropriate parser."""

from __future__ import annotations

import json
from pathlib import Path

from sbs.models.conversation import NormalizedConversation
from sbs.parsers.chatgpt import ChatGPTParser
from sbs.parsers.claude import ClaudeParser

_PARSERS = [ChatGPTParser(), ClaudeParser()]


def detect_and_parse(file_path: Path) -> list[NormalizedConversation]:
    """Load a JSON file, detect its format, and parse it into normalized conversations."""
    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)

    for parser in _PARSERS:
        if parser.can_parse(data):
            return parser.parse(data, source_path=str(file_path))

    raise ValueError(f"Could not detect format of {file_path}")


def parse_directory(input_dir: Path) -> list[NormalizedConversation]:
    """Parse all JSON files in a directory, auto-detecting format for each."""
    conversations: list[NormalizedConversation] = []
    json_files = sorted(input_dir.glob("*.json"))

    for file_path in json_files:
        try:
            convs = detect_and_parse(file_path)
            conversations.extend(convs)
        except (json.JSONDecodeError, ValueError):
            # Skip files that can't be parsed
            continue

    return conversations
