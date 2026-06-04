"""CLI tests for local archive commands."""

from typer.testing import CliRunner

from reweave.cli import app

runner = CliRunner()


def test_cli_import_search_show_stats_export(tmp_path, fixtures_dir):
    db = tmp_path / "archive.db"
    exports = tmp_path / "exports"

    result = runner.invoke(app, ["import", str(fixtures_dir), "--db", str(db)])
    assert result.exit_code == 0
    assert "New conversations: 4" in result.output

    result = runner.invoke(app, ["search", "Zettelkasten", "--db", str(db)])
    assert result.exit_code == 0
    assert "Zettelkasten Discussion" in result.output

    conversation_id = _first_conversation_id(db, fixtures_dir)
    result = runner.invoke(app, ["show", conversation_id, "--db", str(db)])
    assert result.exit_code == 0
    assert "Zettelkasten Discussion" in result.output
    assert "0. user" in result.output

    result = runner.invoke(app, ["stats", "--db", str(db)])
    assert result.exit_code == 0
    assert "Conversations: 4" in result.output

    result = runner.invoke(
        app, ["export", conversation_id, "-o", str(exports), "--db", str(db)]
    )
    assert result.exit_code == 0
    assert "Exported:" in result.output
    assert list(exports.glob("*.md"))


def test_cli_search_no_results(tmp_path, fixtures_dir):
    db = tmp_path / "archive.db"
    runner.invoke(app, ["import", str(fixtures_dir), "--db", str(db)])

    result = runner.invoke(app, ["search", "notfoundtoken", "--db", str(db)])

    assert result.exit_code == 0
    assert "No results found" in result.output


def test_cli_show_missing_conversation(tmp_path):
    db = tmp_path / "archive.db"

    result = runner.invoke(app, ["show", "missing", "--db", str(db)])

    assert result.exit_code == 1
    assert "Conversation not found" in result.output


def test_cli_export_query(tmp_path, fixtures_dir):
    db = tmp_path / "archive.db"
    exports = tmp_path / "exports"
    runner.invoke(app, ["import", str(fixtures_dir), "--db", str(db)])

    result = runner.invoke(
        app, ["export", "--query", "Obsidian", "-o", str(exports), "--db", str(db)]
    )

    assert result.exit_code == 0
    assert "Exported:" in result.output
    content = next(exports.glob("*.md")).read_text(encoding="utf-8")
    assert "type: search-dossier" in content


def test_cli_export_requires_target(tmp_path):
    db = tmp_path / "archive.db"

    result = runner.invoke(app, ["export", "--db", str(db)])

    assert result.exit_code == 1
    assert "Provide a conversation_id or --query" in result.output


def _first_conversation_id(db, fixtures_dir):
    from reweave.archive import ArchiveStore

    store = ArchiveStore(db)
    store.import_directory(fixtures_dir)
    return store.search("Zettelkasten")[0].conversation_id
