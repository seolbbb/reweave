import sqlite3
from pathlib import Path

import pytest

from reweave.archive import ArchiveStore
from reweave.archive_management import ArchiveManager


def test_library_lists_and_filters_conversations(tmp_path, fixtures_dir):
    db = tmp_path / "archive.db"
    ArchiveStore(db).import_directory(fixtures_dir)
    manager = ArchiveManager(db)

    page = manager.list_conversations(source="claude", title="Vault", sort="title")

    assert page.total == 1
    assert page.results[0].title == "Obsidian Vault Setup"
    assert page.results[0].source == "claude"
    assert page.results[0].preview


def test_library_rejects_unknown_source_and_sort(tmp_path):
    manager = ArchiveManager(tmp_path / "archive.db")
    ArchiveStore(manager.db_path)

    with pytest.raises(ValueError, match="Source"):
        manager.list_conversations(source="other")
    with pytest.raises(ValueError, match="Sort"):
        manager.list_conversations(sort="random")


def test_delete_conversation_removes_search_data_and_related_reports(tmp_path, fixtures_dir):
    db = tmp_path / "archive.db"
    store = ArchiveStore(db)
    store.import_directory(fixtures_dir)
    conversation = store.search_conversations("Obsidian")[0]
    report = store.save_insight_report(
        title="Delete me",
        selected_conversation_ids=[conversation.id],
        provider="openai",
        model="test",
        markdown="Private derived content",
    )
    with sqlite3.connect(db) as conn:
        message_id = conn.execute(
            "SELECT id FROM messages WHERE conversation_id = ? LIMIT 1", (conversation.id,)
        ).fetchone()[0]
        chunk_id = f"{message_id}:0"
        conn.execute(
            """
            INSERT INTO search_chunks (
                id, message_id, conversation_id, message_index, chunk_index, content, content_hash
            ) VALUES (?, ?, ?, 0, 0, 'chunk', 'hash')
            """,
            (chunk_id, message_id, conversation.id),
        )
        conn.execute(
            """
            INSERT INTO chunk_embeddings (chunk_id, model_id, dimensions, embedding)
            VALUES (?, 'test-model', 1, ?)
            """,
            (chunk_id, b"1234"),
        )

    summary = ArchiveManager(db).delete_conversation(conversation.id)

    assert summary.conversations == 1
    assert summary.messages > 0
    assert summary.embeddings == 1
    assert summary.reports == 1
    assert store.get_conversation(conversation.id) is None
    assert store.get_insight_report(report.id) is None
    assert not any(result.conversation_id == conversation.id for result in store.search("Obsidian"))
    with sqlite3.connect(db) as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM messages_fts WHERE conversation_id = ?", (conversation.id,)
            ).fetchone()[0]
            == 0
        )
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM search_chunks WHERE conversation_id = ?", (conversation.id,)
            ).fetchone()[0]
            == 0
        )


def test_delete_source_keeps_other_provider(tmp_path, fixtures_dir):
    db = tmp_path / "archive.db"
    store = ArchiveStore(db)
    store.import_directory(fixtures_dir)

    summary = ArchiveManager(db).delete_source("chatgpt")

    assert summary.conversations == 2
    page = ArchiveManager(db).list_conversations()
    assert page.total == 2
    assert {item.source for item in page.results} == {"claude"}


def test_backup_and_restore_round_trip_with_safety_copy(tmp_path, fixtures_dir):
    db = tmp_path / "archive.db"
    store = ArchiveStore(db)
    store.import_directory(fixtures_dir)
    manager = ArchiveManager(db)
    backup = manager.backup_to(tmp_path / "backup.sqlite3")
    chatgpt_id = manager.list_conversations(source="chatgpt").results[0].id
    manager.delete_conversation(chatgpt_id)

    summary = manager.restore_from(backup, safety_backup_dir=tmp_path / "safety")

    assert summary.conversations == 4
    assert summary.messages == 12
    assert Path(summary.safety_backup_path).exists()
    assert manager.list_conversations().total == 4


def test_restore_rejects_non_reweave_database(tmp_path):
    db = tmp_path / "archive.db"
    ArchiveStore(db)
    invalid = tmp_path / "invalid.sqlite3"
    with sqlite3.connect(invalid) as conn:
        conn.execute("CREATE TABLE other (id INTEGER)")

    with pytest.raises(ValueError, match="not a Reweave"):
        ArchiveManager(db).restore_from(invalid, safety_backup_dir=tmp_path / "safety")
