"""Auto-detect input format and route to the appropriate parser."""

from __future__ import annotations

import json
import zipfile
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


def _parse_zip(zip_path: Path) -> list[NormalizedConversation]:
    """Parse JSON files inside a zip archive without extracting to disk."""
    conversations: list[NormalizedConversation] = []
    with zipfile.ZipFile(zip_path) as zf:
        json_names = [n for n in zf.namelist() if n.lower().endswith(".json")]
        for name in json_names:
            try:
                with zf.open(name) as f:
                    data = json.loads(f.read().decode("utf-8"))
                source = f"{zip_path}/{name}"
                for parser in _PARSERS:
                    if parser.can_parse(data):
                        conversations.extend(parser.parse(data, source_path=source))
                        break
            except (json.JSONDecodeError, ValueError):
                continue
    return conversations


def parse_directory(input_dir: Path) -> list[NormalizedConversation]:
    """Parse all JSON files in a directory tree, auto-detecting format for each."""
    conversations: list[NormalizedConversation] = []

    for file_path in sorted(input_dir.rglob("*.json")):
        try:
            convs = detect_and_parse(file_path)
            conversations.extend(convs)
        except (json.JSONDecodeError, ValueError):
            continue

    for zip_path in sorted(input_dir.rglob("*.zip")):
        try:
            convs = _parse_zip(zip_path)
            conversations.extend(convs)
        except (zipfile.BadZipFile, OSError):
            continue

    return conversations
