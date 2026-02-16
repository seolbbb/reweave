"""Tests for conversation parsers."""

import json
import shutil
import zipfile
from pathlib import Path

import pytest

from sbs.parsers.chatgpt import ChatGPTParser
from sbs.parsers.claude import ClaudeParser
from sbs.parsers.detector import _parse_zip, detect_and_parse, parse_directory

FIXTURES = Path(__file__).parent / "fixtures"


class TestChatGPTParser:
    @pytest.fixture()
    def parser(self):
        return ChatGPTParser()

    @pytest.fixture()
    def sample_data(self):
        with open(FIXTURES / "chatgpt_sample.json") as f:
            return json.load(f)

    def test_can_parse_valid(self, parser, sample_data):
        assert parser.can_parse(sample_data) is True

    def test_can_parse_invalid(self, parser):
        assert parser.can_parse({"chat_messages": []}) is False
        assert parser.can_parse("not a list") is False

    def test_parse_conversations(self, parser, sample_data):
        convs = parser.parse(sample_data)
        assert len(convs) == 2

    def test_first_conversation(self, parser, sample_data):
        convs = parser.parse(sample_data)
        conv = convs[0]
        assert conv.title == "Zettelkasten Discussion"
        assert conv.source == "chatgpt"
        assert len(conv.messages) == 4

    def test_message_roles(self, parser, sample_data):
        convs = parser.parse(sample_data)
        roles = [m.role for m in convs[0].messages]
        assert roles == ["user", "assistant", "user", "assistant"]

    def test_message_content(self, parser, sample_data):
        convs = parser.parse(sample_data)
        assert "Zettelkasten method" in convs[0].messages[0].content

    def test_timestamps_converted(self, parser, sample_data):
        convs = parser.parse(sample_data)
        # All messages should have ISO timestamps
        for msg in convs[0].messages:
            assert msg.timestamp is not None
            assert "T" in msg.timestamp  # ISO format

    def test_second_conversation(self, parser, sample_data):
        convs = parser.parse(sample_data)
        conv = convs[1]
        assert conv.title == "Python Best Practices"
        assert len(conv.messages) == 2

    def test_deterministic_ids(self, parser, sample_data):
        convs1 = parser.parse(sample_data)
        convs2 = parser.parse(sample_data)
        assert convs1[0].id == convs2[0].id

    def test_skips_null_messages(self, parser):
        """Root nodes with message: null should be skipped."""
        data = [{
            "title": "Test",
            "create_time": 1700000000.0,
            "mapping": {
                "root": {
                    "id": "root", "message": None,
                    "parent": None, "children": ["m1"]
                },
                "m1": {
                    "id": "m1",
                    "message": {
                        "author": {"role": "user"},
                        "content": {"parts": ["hello"]},
                        "create_time": 1700000000.0
                    },
                    "parent": "root", "children": []
                }
            }
        }]
        convs = parser.parse(data)
        assert len(convs) == 1
        assert len(convs[0].messages) == 1


class TestClaudeParser:
    @pytest.fixture()
    def parser(self):
        return ClaudeParser()

    @pytest.fixture()
    def sample_data(self):
        with open(FIXTURES / "claude_sample.json") as f:
            return json.load(f)

    def test_can_parse_valid(self, parser, sample_data):
        assert parser.can_parse(sample_data) is True

    def test_can_parse_single_object(self, parser):
        assert parser.can_parse({"chat_messages": []}) is True

    def test_can_parse_invalid(self, parser):
        assert parser.can_parse([{"mapping": {}}]) is False
        assert parser.can_parse("string") is False

    def test_parse_conversations(self, parser, sample_data):
        convs = parser.parse(sample_data)
        assert len(convs) == 2

    def test_first_conversation(self, parser, sample_data):
        convs = parser.parse(sample_data)
        conv = convs[0]
        assert conv.title == "Obsidian Vault Setup"
        assert conv.source == "claude"
        assert len(conv.messages) == 4

    def test_role_mapping(self, parser, sample_data):
        convs = parser.parse(sample_data)
        roles = [m.role for m in convs[0].messages]
        assert roles == ["user", "assistant", "user", "assistant"]

    def test_timestamps_preserved(self, parser, sample_data):
        convs = parser.parse(sample_data)
        assert convs[0].messages[0].timestamp == "2026-02-10T09:15:00Z"

    def test_second_conversation(self, parser, sample_data):
        convs = parser.parse(sample_data)
        conv = convs[1]
        assert conv.title == "AI Agent Patterns"
        assert len(conv.messages) == 2


class TestDetector:
    def test_detect_chatgpt(self):
        convs = detect_and_parse(FIXTURES / "chatgpt_sample.json")
        assert len(convs) == 2
        assert all(c.source == "chatgpt" for c in convs)

    def test_detect_claude(self):
        convs = detect_and_parse(FIXTURES / "claude_sample.json")
        assert len(convs) == 2
        assert all(c.source == "claude" for c in convs)

    def test_parse_directory(self):
        convs = parse_directory(FIXTURES)
        # Should find both chatgpt and claude conversations
        assert len(convs) == 4
        sources = {c.source for c in convs}
        assert sources == {"chatgpt", "claude"}


class TestRecursiveDirectoryParsing:
    def test_finds_json_in_subdirectory(self, tmp_path):
        """parse_directory should find JSON files in nested subdirectories."""
        subdir = tmp_path / "export" / "nested"
        subdir.mkdir(parents=True)
        shutil.copy(FIXTURES / "chatgpt_sample.json", subdir / "conversations.json")

        convs = parse_directory(tmp_path)
        assert len(convs) == 2
        assert all(c.source == "chatgpt" for c in convs)

    def test_finds_json_at_multiple_levels(self, tmp_path):
        """parse_directory should find JSON at root and in subdirectories."""
        shutil.copy(FIXTURES / "chatgpt_sample.json", tmp_path / "root.json")
        subdir = tmp_path / "sub"
        subdir.mkdir()
        shutil.copy(FIXTURES / "claude_sample.json", subdir / "claude.json")

        convs = parse_directory(tmp_path)
        assert len(convs) == 4
        sources = {c.source for c in convs}
        assert sources == {"chatgpt", "claude"}


class TestZipParsing:
    @pytest.fixture()
    def chatgpt_zip(self, tmp_path):
        """Create a zip containing chatgpt_sample.json."""
        zip_path = tmp_path / "export.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.write(FIXTURES / "chatgpt_sample.json", "conversations.json")
        return zip_path

    @pytest.fixture()
    def mixed_zip(self, tmp_path):
        """Create a zip containing both ChatGPT and Claude JSON files."""
        zip_path = tmp_path / "mixed.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.write(FIXTURES / "chatgpt_sample.json", "chatgpt/conversations.json")
            zf.write(FIXTURES / "claude_sample.json", "claude/export.json")
        return zip_path

    def test_parse_zip_chatgpt(self, chatgpt_zip):
        convs = _parse_zip(chatgpt_zip)
        assert len(convs) == 2
        assert all(c.source == "chatgpt" for c in convs)

    def test_parse_zip_source_path_includes_zip_name(self, chatgpt_zip):
        convs = _parse_zip(chatgpt_zip)
        source_path = convs[0].metadata["source_path"]
        assert "export.zip" in source_path
        assert "conversations.json" in source_path

    def test_parse_zip_mixed_formats(self, mixed_zip):
        convs = _parse_zip(mixed_zip)
        assert len(convs) == 4
        sources = {c.source for c in convs}
        assert sources == {"chatgpt", "claude"}

    def test_parse_zip_skips_non_json(self, tmp_path):
        """Zip files containing non-JSON entries should be silently skipped."""
        zip_path = tmp_path / "nojson.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("readme.txt", "not json")
        convs = _parse_zip(zip_path)
        assert convs == []

    def test_parse_zip_skips_invalid_json(self, tmp_path):
        """Invalid JSON inside a zip should be silently skipped."""
        zip_path = tmp_path / "bad.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("broken.json", "{not valid json}")
        convs = _parse_zip(zip_path)
        assert convs == []

    def test_parse_directory_finds_zip(self, tmp_path, chatgpt_zip):
        """parse_directory should discover and parse zip files."""
        convs = parse_directory(tmp_path)
        assert len(convs) == 2
        assert all(c.source == "chatgpt" for c in convs)

    def test_parse_directory_zip_in_subdirectory(self, tmp_path):
        """parse_directory should find zip files in subdirectories."""
        subdir = tmp_path / "exports"
        subdir.mkdir()
        zip_path = subdir / "claude.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.write(FIXTURES / "claude_sample.json", "data.json")

        convs = parse_directory(tmp_path)
        assert len(convs) == 2
        assert all(c.source == "claude" for c in convs)
