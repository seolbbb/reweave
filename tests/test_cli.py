"""CLI tests for local archive commands."""

from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

import reweave.cli as cli
from reweave.cli import app
from reweave.library_lock import library_lock

runner = CliRunner()


@pytest.mark.parametrize("command", ["import", "search", "index", "ask", "show", "stats", "export"])
def test_cli_commands_reject_an_open_library_before_any_store_or_output_write(
    tmp_path, fixtures_dir, monkeypatch, command
):
    db = tmp_path / "unopened.db"
    exports = tmp_path / "exports"
    arguments = {
        "import": [str(fixtures_dir)],
        "search": ["synthetic"],
        "index": [],
        "ask": ["Synthetic question"],
        "show": ["synthetic-id"],
        "stats": [],
        "export": ["synthetic-id", "-o", str(exports)],
    }
    constructed = []

    def forbidden_store(*args, **kwargs):
        constructed.append(True)
        raise AssertionError("A blocked command must not initialize its database.")

    monkeypatch.setattr(cli, "ArchiveStore", forbidden_store)
    with library_lock(db):
        result = runner.invoke(app, [command, *arguments[command], "--db", str(db)])

    assert result.exit_code == 1
    assert "Library unavailable" in result.output
    assert "already open" in result.output
    assert not constructed
    assert not db.exists()
    assert not exports.exists()


@pytest.mark.parametrize("command", ["index", "ask"])
def test_cli_keeps_library_owned_through_long_work(tmp_path, monkeypatch, command):
    db = tmp_path / "archive.db"
    observations = []

    def observe_owner():
        with pytest.raises(RuntimeError, match="already open"), library_lock(db):
            pass
        observations.append("owned during work")

    class SyntheticIndex:
        def __init__(self, *args):
            pass

        def build(self, **kwargs):
            observe_owner()
            return SimpleNamespace(indexed_chunks=0)

    def synthetic_answer(*args, **kwargs):
        observe_owner()
        return SimpleNamespace(markdown="Synthetic answer")

    monkeypatch.setattr(cli, "SemanticIndex", SyntheticIndex)
    monkeypatch.setattr(cli, "SearchEngine", lambda *args: object())
    monkeypatch.setattr(cli, "answer_archive", synthetic_answer)
    arguments = ["Synthetic question"] if command == "ask" else []
    result = runner.invoke(app, [command, *arguments, "--db", str(db)])

    assert result.exit_code == 0, result.output
    assert observations == ["owned during work"]
    with library_lock(db):
        assert db.exists()


def test_cli_releases_library_when_command_fails(tmp_path):
    db = tmp_path / "archive.db"
    result = runner.invoke(app, ["show", "missing", "--db", str(db)])
    assert result.exit_code == 1
    with library_lock(db):
        assert db.exists()


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

    result = runner.invoke(app, ["export", conversation_id, "-o", str(exports), "--db", str(db)])
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
