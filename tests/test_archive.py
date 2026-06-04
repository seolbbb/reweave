"""Tests for SQLite archive import, search, retrieval, stats, and export."""

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
