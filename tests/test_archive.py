"""Tests for SQLite archive import, search, retrieval, stats, and export."""

import json
import sqlite3
import zipfile

from reweave.archive import ArchiveStore, export_conversation_markdown, export_search_markdown


def test_import_fixtures_idempotent(tmp_path, fixtures_dir):
    store = ArchiveStore(tmp_path / "archive.db")

    first = store.import_directory(fixtures_dir)
    second = store.import_directory(fixtures_dir)

    assert first.parsed_conversations == 4
    assert first.inserted_conversations == 4
    assert first.inserted_messages == 12
    assert first.skipped_files == ()
    assert second.parsed_conversations == 4
    assert second.inserted_conversations == 0
    assert second.inserted_messages == 0


def test_import_path_single_json(tmp_path, chatgpt_sample_path):
    store = ArchiveStore(tmp_path / "archive.db")

    summary = store.import_path(chatgpt_sample_path)

    assert summary.parsed_conversations == 2
    assert summary.inserted_conversations == 2
    assert summary.inserted_messages == 6


def test_import_directory_recurses(tmp_path, fixtures_dir, chatgpt_sample_path):
    nested = tmp_path / "exports" / "nested"
    nested.mkdir(parents=True)
    target = nested / "chatgpt_sample.json"
    target.write_text(chatgpt_sample_path.read_text(encoding="utf-8"), encoding="utf-8")
    store = ArchiveStore(tmp_path / "archive.db")

    summary = store.import_directory(tmp_path / "exports")

    assert summary.parsed_conversations == 2
    assert store.stats().total_conversations == 2


def test_import_path_zip_idempotent(tmp_path, fixtures_dir):
    zip_path = tmp_path / "chat_export.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        for json_path in fixtures_dir.glob("*.json"):
            archive.write(json_path, arcname=f"nested/{json_path.name}")
    store = ArchiveStore(tmp_path / "archive.db")

    first = store.import_path(zip_path, extraction_root=tmp_path / "extracted")
    second = store.import_path(zip_path, extraction_root=tmp_path / "extracted")

    assert first.parsed_conversations == 4
    assert first.inserted_conversations == 4
    assert second.parsed_conversations == 4
    assert second.inserted_conversations == 0


def test_import_path_zip_extracts_only_json_files(tmp_path, fixtures_dir):
    zip_path = tmp_path / "chat_export.zip"
    long_asset_name = "assets/" + ("nested/" * 30) + "ignored.png"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.write(fixtures_dir / "chatgpt_sample.json", arcname="conversations.json")
        archive.writestr(long_asset_name, b"image bytes")
    extraction_root = tmp_path / "extracted"
    store = ArchiveStore(tmp_path / "archive.db")

    summary = store.import_path(zip_path, extraction_root=extraction_root)

    assert summary.parsed_conversations == 2
    assert not list(extraction_root.rglob("*.png"))


def test_import_path_rejects_zip_slip(tmp_path, chatgpt_sample_path):
    zip_path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.write(chatgpt_sample_path, arcname="../escape.json")
    store = ArchiveStore(tmp_path / "archive.db")

    try:
        store.import_path(zip_path, extraction_root=tmp_path / "extracted")
    except ValueError as exc:
        assert "Unsafe zip entry" in str(exc)
    else:
        raise AssertionError("Expected unsafe zip to be rejected.")


def test_search_message_content(tmp_path, fixtures_dir):
    store = ArchiveStore(tmp_path / "archive.db")
    store.import_directory(fixtures_dir)

    results = store.search("Zettelkasten")

    assert results
    assert results[0].conversation_id
    assert results[0].message_id
    assert results[0].message_index >= 0
    assert "Zettelkasten" in results[0].excerpt


def test_search_title_and_provider_filter(tmp_path, fixtures_dir):
    store = ArchiveStore(tmp_path / "archive.db")
    store.import_directory(fixtures_dir)

    results = store.search("Obsidian", provider="claude", title="Vault")

    assert results
    assert all(result.source == "claude" for result in results)
    assert all(result.title == "Obsidian Vault Setup" for result in results)


def test_search_date_filter(tmp_path, fixtures_dir):
    store = ArchiveStore(tmp_path / "archive.db")
    store.import_directory(fixtures_dir)

    results = store.search("agent", date_from="2026-02-11", date_to="2026-02-12")

    assert results
    assert all(result.title == "AI Agent Patterns" for result in results)


def test_search_conversations_groups_excerpts(tmp_path, fixtures_dir):
    store = ArchiveStore(tmp_path / "archive.db")
    store.import_directory(fixtures_dir)

    results = store.search_conversations("Obsidian")

    assert results
    assert results[0].id
    assert results[0].match_count >= 1
    assert results[0].excerpts


def test_search_supports_phrase_substring_special_characters_and_empty_query(
    tmp_path, fixtures_dir
):
    store = ArchiveStore(tmp_path / "archive.db")
    store.import_directory(fixtures_dir)

    phrase = store.search('"flat folder structure"')
    substring = store.search("sidian")
    punctuation = store.search('"tags vs links?"')

    assert phrase and "flat folder structure" in phrase[0].excerpt
    assert substring and any(result.title == "Obsidian Vault Setup" for result in substring)
    assert punctuation and punctuation[0].title == "Obsidian Vault Setup"
    assert store.search("   ") == []


def test_search_finds_korean_partial_word(tmp_path):
    export_path = tmp_path / "korean.json"
    export_path.write_text(
        json.dumps(
            [
                {
                    "uuid": "korean-partial-conversation",
                    "name": "Korean substring",
                    "created_at": "2026-07-01T00:00:00Z",
                    "updated_at": "2026-07-01T00:00:00Z",
                    "chat_messages": [
                        {
                            "uuid": "korean-partial-message",
                            "sender": "human",
                            "text": "파란호수검색어를 나중에 다시 찾아보자.",
                            "created_at": "2026-07-01T00:00:00Z",
                        }
                    ],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    store = ArchiveStore(tmp_path / "archive.db")
    store.import_path(export_path)

    results = store.search("호수검색")

    assert results
    assert results[0].match_kind == "substring"


def test_reimport_updates_native_conversation_without_changing_archive_id(
    tmp_path, claude_sample_path
):
    export_path = tmp_path / "claude.json"
    payload = json.loads(claude_sample_path.read_text(encoding="utf-8"))
    export_path.write_text(json.dumps(payload), encoding="utf-8")
    store = ArchiveStore(tmp_path / "archive.db")
    first = store.import_path(export_path)
    original = store.search("Obsidian")[0]

    payload[0]["name"] = "My Updated Vault Plan"
    payload[0]["updated_at"] = "2026-02-12T10:00:00Z"
    payload[0]["chat_messages"][1]["text"] = "Use a calm flat structure with linked notes."
    payload[0]["chat_messages"].append(
        {
            "uuid": "msg-005",
            "sender": "human",
            "text": "Keep this durable archive reference.",
            "created_at": "2026-02-12T10:00:00Z",
        }
    )
    export_path.write_text(json.dumps(payload), encoding="utf-8")
    second = store.import_path(export_path)
    updated = store.search("durable archive reference")[0]

    assert first.inserted_conversations == 2
    assert second.inserted_conversations == 0
    assert second.updated_conversations == 1
    assert second.updated_messages == 1
    assert second.inserted_messages == 1
    assert updated.conversation_id == original.conversation_id
    assert store.get_conversation(original.conversation_id).title == "My Updated Vault Plan"


def test_reimport_never_deletes_messages_missing_from_new_export(tmp_path, claude_sample_path):
    export_path = tmp_path / "claude.json"
    payload = json.loads(claude_sample_path.read_text(encoding="utf-8"))
    export_path.write_text(json.dumps(payload), encoding="utf-8")
    store = ArchiveStore(tmp_path / "archive.db")
    store.import_path(export_path)
    conversation_id = store.search("Obsidian")[0].conversation_id

    payload[0]["chat_messages"] = payload[0]["chat_messages"][:2]
    export_path.write_text(json.dumps(payload), encoding="utf-8")
    store.import_path(export_path)

    assert len(store.get_messages(conversation_id)) == 4


def test_existing_v1_database_is_migrated_and_remains_searchable(tmp_path):
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE conversations (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT,
                raw_message_count INTEGER NOT NULL,
                source_path TEXT NOT NULL
            );
            CREATE TABLE messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                message_index INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT,
                UNIQUE(conversation_id, message_index)
            );
            CREATE VIRTUAL TABLE messages_fts USING fts5(
                message_id UNINDEXED,
                conversation_id UNINDEXED,
                message_index UNINDEXED,
                role UNINDEXED,
                timestamp UNINDEXED,
                title,
                content
            );
            INSERT INTO conversations VALUES (
                'legacy-conversation', 'chatgpt', 'Legacy Archive',
                '2025-01-01T00:00:00Z', NULL, 1, 'legacy.json'
            );
            INSERT INTO messages VALUES (
                'legacy-message', 'legacy-conversation', 0, 'user',
                'A durable searchable memory', '2025-01-01T00:00:00Z'
            );
            INSERT INTO messages_fts VALUES (
                'legacy-message', 'legacy-conversation', 0, 'user',
                '2025-01-01T00:00:00Z', 'Legacy Archive',
                'A durable searchable memory'
            );
            """
        )

    store = ArchiveStore(db_path)
    results = store.search("searchable")
    with sqlite3.connect(db_path) as conn:
        conversation_columns = {row[1] for row in conn.execute("PRAGMA table_info(conversations)")}
        message_columns = {row[1] for row in conn.execute("PRAGMA table_info(messages)")}
        schema_version = conn.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        ).fetchone()[0]

    assert results[0].conversation_id == "legacy-conversation"
    assert "source_id" in conversation_columns
    assert {"source_id", "content_hash"}.issubset(message_columns)
    assert schema_version == "2"


def test_get_conversation_and_messages_preserve_source_metadata(tmp_path, fixtures_dir):
    store = ArchiveStore(tmp_path / "archive.db")
    store.import_directory(fixtures_dir)
    result = store.search("Python", provider="chatgpt")[0]

    conversation = store.get_conversation(result.conversation_id)
    messages = store.get_messages(result.conversation_id)

    assert conversation is not None
    assert conversation.source == "chatgpt"
    assert conversation.source_path.endswith("chatgpt_sample.json")
    assert messages[0].index == 0
    assert messages[0].timestamp is not None


def test_stats(tmp_path, fixtures_dir):
    store = ArchiveStore(tmp_path / "archive.db")
    store.import_directory(fixtures_dir)

    stats = store.stats()

    assert stats.total_conversations == 4
    assert stats.total_messages == 12
    assert {row.source for row in stats.by_source} == {"chatgpt", "claude"}
    assert stats.longest_conversations[0].messages == 4


def test_insight_report_storage(tmp_path):
    store = ArchiveStore(tmp_path / "archive.db")

    report = store.save_insight_report(
        title="Insight",
        selected_conversation_ids=["c1", "c2"],
        provider="openai",
        model="gpt-4o-mini",
        markdown="## Overview\n\nText",
    )

    assert store.get_insight_report(report.id) == report
    assert store.list_insight_reports()[0] == report


def test_export_conversation_markdown(tmp_path, fixtures_dir):
    store = ArchiveStore(tmp_path / "archive.db")
    store.import_directory(fixtures_dir)
    result = store.search("Zettelkasten")[0]
    conversation = store.get_conversation(result.conversation_id)
    assert conversation is not None

    path = export_conversation_markdown(
        tmp_path / "exports", conversation, store.get_messages(conversation.id)
    )

    content = path.read_text(encoding="utf-8")
    assert "type: source-conversation" in content
    assert f"conversation_id: {conversation.id}" in content
    assert "## Messages" in content
    assert "Source:" in content
    assert "message `0`" in content


def test_export_search_markdown(tmp_path, fixtures_dir):
    store = ArchiveStore(tmp_path / "archive.db")
    store.import_directory(fixtures_dir)
    results = store.search("Obsidian")

    path = export_search_markdown(tmp_path / "exports", "Obsidian", results)

    content = path.read_text(encoding="utf-8")
    assert "type: search-dossier" in content
    assert "Search Dossier: Obsidian" in content
    assert "Conversation ID:" in content
    assert "Message index:" in content
