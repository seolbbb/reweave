"""Synthetic encrypted backup round trips and adversarial fail-before-replace checks."""

import json
import os
import sqlite3
import stat
import struct
import zipfile
from contextlib import closing
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import keyring
import pytest

from reweave import encrypted_backup as backup
from reweave.analysis_policy import AnalysisLimitError, AnalysisPolicy, AnalysisPolicyStore
from reweave.archive import ArchiveStore
from reweave.context_chunking import ChunkStore, PartialAnalysisError
from reweave.context_library import ContextLibraryStore, EvidenceInput, ScopeInput
from reweave.context_review import ContextReviewStore
from reweave.context_trust import ContextTrustStore
from reweave.encrypted_backup import (
    BackupError,
    BackupLimits,
    EncryptedBackupService,
    RestoreRecoveryError,
)
from reweave.llm_profiles import KeyInput, LLMProfileStore, ProfileInput

PASSWORD = "synthetic library passphrase"


@pytest.fixture
def library(tmp_path, fixtures_dir):
    data = tmp_path / "source"
    data.mkdir()
    db = data / "library.db"
    profiles = data / "profiles.json"
    archive = ArchiveStore(db)
    archive.import_directory(fixtures_dir)
    context = ContextLibraryStore(db)
    conversation = archive.search("Obsidian", limit=1)[0].conversation_id
    message = archive.get_messages(conversation)[0]
    brief = context.save_brief(
        conversation_id=conversation,
        main_subject="Organizing notes",
        user_goal="Keep decisions",
        analysis_version="test-v1",
        prompt_version="test-v1",
        analysis_provider="synthetic",
        analysis_model="synthetic-model",
    )
    item = context.create_item(
        brief_id=brief.id,
        canonical_text="Keep a source-backed project library.",
        item_type="lesson",
        epistemic_kind="observed",
        confidence=0.9,
        evidence=[EvidenceInput(conversation, message.id)],
        scopes=[ScopeInput("project", "Notes")],
    )
    context.revise_item(
        item.id,
        canonical_text="Preserve original decisions and their sources.",
        change_reason="User correction",
        sensitivity="sensitive",
        epistemic_kind="inferred",
    )
    second = context.create_item(
        brief_id=brief.id,
        canonical_text="Notes can link across spaces.",
        item_type="concept",
        epistemic_kind="observed",
        confidence=0.85,
        evidence=[EvidenceInput(conversation, message.id)],
        scopes=[ScopeInput("topic", "Knowledge")],
    )
    context.link_items(item.id, second.id, "related_to")
    review = ContextReviewStore(context)
    row = review.inspect(context.get_item(item.id))
    review.dismiss(item.id, expected_version=2, review_key=row["review_key"])
    trust = ContextTrustStore(db)
    trust.save("chatgpt", "synthetic-conversation", "private", [], expected_revision=0)
    queued, _ = context.enqueue_analysis(
        conversation_id=conversation, source_fingerprint="synthetic-fingerprint"
    )
    context.start_analysis_queue_job(queued.id)
    policy = AnalysisPolicyStore(db)
    policy.save(AnalysisPolicy(daily_attempt_limit=7, analysis_mode="project"))
    policy.reserve(attempts=1, tokens=1000)
    profile_store = LLMProfileStore(profiles)
    profile = profile_store.create(
        ProfileInput(
            name="Synthetic provider",
            provider="openai-compatible",
            base_url="https://example.invalid/v1",
            default_model="synthetic-model",
            keys=(KeyInput(label="Primary", api_key="synthetic-secret-never-export"),),
        )
    )
    return EncryptedBackupService(db, profiles), context.get_item(item.id), profile, queued.id


def make_destination(tmp_path):
    destination = tmp_path / "destination"
    destination.mkdir()
    db = destination / "restored.db"
    profiles = destination / "profiles.json"
    ArchiveStore(db)
    ContextLibraryStore(db)
    store = LLMProfileStore(profiles)
    store.create(ProfileInput(name="Existing settings", provider="openai"))
    return EncryptedBackupService(db, profiles)


def test_restore_preserves_current_day_usage_high_water_mark(library, tmp_path):
    service, _, _, _ = library
    policy = AnalysisPolicyStore(service.db_path)
    policy.save(AnalysisPolicy(daily_attempt_limit=3))
    artifact = tmp_path / "earlier.reweave"
    service.backup_to(artifact, PASSWORD)
    policy.reserve(attempts=2, tokens=6000)
    before = policy.usage()
    service.restore_from(artifact, PASSWORD, jobs_idle=True)
    assert policy.usage()["reserved_attempts"] == before["reserved_attempts"]
    assert policy.usage()["reserved_tokens"] == before["reserved_tokens"]
    with pytest.raises(AnalysisLimitError):
        policy.reserve(attempts=1, tokens=1)


@pytest.mark.parametrize("backup_calls,live_calls", [(1, 256), (256, 1)])
def test_restore_preserves_same_run_call_maximum_and_new_generation(
    library, tmp_path, backup_calls, live_calls
):
    service, item, _, _ = library
    runner = ChunkStore(service.db_path)
    brief = {
        "main_subject": "Synthetic decision",
        "user_goal": "Retain source context",
        **{
            key: []
            for key in (
                "important_outcomes",
                "decisions",
                "lessons",
                "unresolved_questions",
                "actions",
            )
        },
    }
    args = dict(
        source_id=item.evidence[0].source_conversation_id,
        source_fingerprint="synthetic-restore-source",
        analysis_config_key="synthetic-restore-config",
        max_payload_chars=2000,
        messages=[
            SimpleNamespace(
                id="message", index=0, role="user", timestamp=None, content="Keep the decision."
            )
        ],
        call_chunk=lambda _: {
            "brief": brief,
            "items": [],
            "dropped_items": 0,
            "deduplicated_items": 0,
        },
        normalize_chunk=lambda value, _: value,
        call_synthesis=lambda _: pytest.fail("Single part needs no synthesis"),
        normalize_synthesis=lambda value, _: value,
    )
    first = runner.run(**args, explicit_generation=1).coverage.run_key
    second = runner.run(**args, explicit_generation=2).coverage.run_key
    with runner._connect() as conn:
        conn.execute(
            "UPDATE context_chunk_runs SET provider_calls=? WHERE run_key=?", (backup_calls, first)
        )
    artifact = tmp_path / "partial.reweave"
    service.backup_to(artifact, PASSWORD)
    before_checkpoints = table_rows(service.db_path, "context_chunk_checkpoints")
    with runner._connect() as conn:
        conn.execute(
            "UPDATE context_chunk_runs SET provider_calls=? WHERE run_key=?", (live_calls, first)
        )
    service.restore_from(artifact, PASSWORD, jobs_idle=True)
    restored = ChunkStore(service.db_path)
    assert restored.coverage(first).provider_calls == 256
    assert restored.coverage(second).provider_calls == 1
    assert table_rows(service.db_path, "context_chunk_checkpoints") == before_checkpoints
    with pytest.raises(PartialAnalysisError) as stopped:
        restored.run_followup(
            run_key=first,
            input_fingerprint="synthetic-pairs",
            call=lambda: pytest.fail("Attempt 257 must not be sent"),
            normalize=lambda value: value,
        )
    assert stopped.value.reason == "total_call_limit"
    assert restored.run_followup(
        run_key=second,
        input_fingerprint="synthetic-pairs",
        call=lambda: {"matches": []},
        normalize=lambda value: value,
    ) == {"matches": []}
    assert restored.coverage(second).provider_calls == 2


def artifact_for(service, tmp_path):
    path = tmp_path / "chosen-folder" / "library.reweave"
    result = service.backup_to(path, PASSWORD)
    return path, result


def table_rows(db, table):
    with closing(sqlite3.connect(db)) as conn:
        return conn.execute(f'SELECT * FROM "{table}" ORDER BY 1').fetchall()


def assert_clean(service):
    assert not list(service.db_path.parent.glob(".reweave-backup-*"))
    assert not service.journal_path.exists()


def test_complete_roundtrip_preserves_data_and_disconnects_profiles(library, tmp_path, monkeypatch):
    service, item, profile, queued_id = library
    source_stats = ArchiveStore(service.db_path).stats()

    def no_keyring(*args, **kwargs):
        raise AssertionError("Backup must never access credentials")

    monkeypatch.setattr(keyring, "get_password", no_keyring)
    monkeypatch.setattr(keyring, "set_password", no_keyring)
    monkeypatch.setattr(keyring, "delete_password", no_keyring)
    path, exported = artifact_for(service, tmp_path)
    assert path.read_bytes().startswith(backup.MAGIC)
    assert b"SQLite format" not in path.read_bytes()
    assert b"Preserve original decisions" not in path.read_bytes()
    assert b"synthetic-secret-never-export" not in path.read_bytes()
    assert exported.bytes_written == path.stat().st_size
    assert exported.sha256 == sha256(path.read_bytes()).hexdigest()
    destination = make_destination(tmp_path)
    previous_profiles = destination.profiles_path.read_bytes()
    preview = destination.preview_from(path, PASSWORD)
    assert preview.context_items == 2
    assert preview.versions == 3
    assert preview.profiles == 1
    assert destination.profiles_path.read_bytes() == previous_profiles
    assert ArchiveStore(destination.db_path).stats().total_conversations == 0

    restored = destination.restore_from(path, PASSWORD, jobs_idle=True)
    assert restored.requires_reconnect
    assert not restored.recovery_pending
    assert ArchiveStore(destination.db_path).stats() == source_stats
    assert ContextLibraryStore(destination.db_path).get_item(item.id) == item
    for table in (
        "context_review_events",
        "context_destination_preferences",
        "context_destination_events",
    ):
        assert table_rows(destination.db_path, table) == table_rows(service.db_path, table)
    for table in (
        "conversations",
        "messages",
        "conversation_briefs",
        "context_items",
        "context_item_versions",
        "context_item_links",
        "context_item_scopes",
        "context_evidence",
        "context_spaces",
        "context_space_aliases",
        "analysis_policy",
        "analysis_usage",
    ):
        assert table_rows(destination.db_path, table) == table_rows(service.db_path, table)
    restored_queue = ContextLibraryStore(destination.db_path).get_analysis_queue_job(queued_id)
    assert restored_queue.status == "pending"
    stored = LLMProfileStore(destination.profiles_path).list()
    assert stored.active_profile_id is None
    assert stored.profiles[0].id == profile.id
    assert stored.profiles[0].default_model == "synthetic-model"
    assert stored.profiles[0].keys[0].enabled is False
    assert LLMProfileStore(destination.profiles_path).credentials_for(profile.id) == ()
    assert_clean(service)
    assert_clean(destination)


@pytest.mark.parametrize(
    "fault", ["password", "ciphertext", "salt", "nonce", "tag", "trailing", "cut"]
)
def test_authentication_failure_keeps_current_library(library, tmp_path, fault):
    service, _, _, _ = library
    path, _ = artifact_for(service, tmp_path)
    raw = bytearray(path.read_bytes())
    password = PASSWORD
    if fault == "password":
        password = "wrong synthetic password"
    elif fault == "trailing":
        raw.extend(b"extra")
    elif fault == "cut":
        del raw[-8:]
    else:
        positions = {
            "ciphertext": backup.HEADER.size + 1,
            "salt": len(backup.MAGIC) + 1,
            "nonce": len(backup.MAGIC) + 17,
            "tag": len(raw) - 1,
        }
        raw[positions[fault]] ^= 1
    path.write_bytes(raw)
    destination = make_destination(tmp_path)
    before_db = destination.db_path.read_bytes()
    before_settings = destination.profiles_path.read_bytes()
    with pytest.raises(BackupError):
        destination.restore_from(path, password, jobs_idle=True)
    assert destination.db_path.read_bytes() == before_db
    assert destination.profiles_path.read_bytes() == before_settings
    assert_clean(destination)


def alter_artifact(service, path, tmp_path, mutation):
    """Make a correctly authenticated malicious file to exercise post-decryption checks."""
    work = tmp_path / "malicious-author-workspace"
    work.mkdir()
    original = work / "original.zip"
    service._decrypt(path, original, PASSWORD)
    with zipfile.ZipFile(original) as archive:
        contents = {info.filename: archive.read(info) for info in archive.infolist()}
    mutation(contents, work)
    changed = work / "changed.zip"
    with zipfile.ZipFile(changed, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in contents.items():
            archive.writestr(name, content)
    with path.open("wb") as output:
        service._encrypt(changed, output, PASSWORD)


@pytest.mark.parametrize(
    "fault",
    [
        "traversal",
        "extra",
        "manifest",
        "checksum",
        "sql",
        "future_schema",
        "foreign_key",
        "trigger",
        "view",
        "missing_column",
        "invalid_record_json",
        "profile_shape",
        "profile_size",
    ],
)
def test_authenticated_malformed_artifact_fails_before_replace(library, tmp_path, fault):
    service, _, _, _ = library
    path, _ = artifact_for(service, tmp_path)

    def mutation(contents, work):
        if fault == "traversal":
            contents["../escape.json"] = contents.pop("settings.json")
        elif fault == "extra":
            contents["extension-bridge.json"] = b"{}"
        elif fault == "manifest":
            manifest = json.loads(contents["manifest.json"])
            manifest["format_version"] = 999
            contents["manifest.json"] = json.dumps(manifest)
        elif fault == "checksum":
            contents["library.sqlite3"] += b"extra"
        elif fault == "profile_shape":
            contents["settings.json"] = b'{"profiles":"wrong"}'
        elif fault == "profile_size":
            contents["settings.json"] = b" " * (backup.BackupLimits().max_settings_bytes + 1)
        else:
            db = work / "malformed.db"
            db.write_bytes(contents["library.sqlite3"])
            if fault == "sql":
                db.write_bytes(b"not a SQLite database")
            else:
                with closing(sqlite3.connect(db)) as conn, conn:
                    if fault == "future_schema":
                        conn.execute(
                            "UPDATE schema_meta SET value='999' WHERE key='schema_version'"
                        )
                    elif fault == "foreign_key":
                        conn.execute(
                            "UPDATE context_evidence SET item_id='missing-item' "
                            "WHERE id=(SELECT id FROM context_evidence LIMIT 1)"
                        )
                    elif fault == "trigger":
                        conn.execute(
                            "CREATE TRIGGER hostile AFTER INSERT ON schema_meta "
                            "BEGIN DELETE FROM context_items; END"
                        )
                    elif fault == "view":
                        conn.execute("CREATE VIEW hostile AS SELECT * FROM context_items")
                    elif fault == "missing_column":
                        conn.execute(
                            "ALTER TABLE context_items RENAME COLUMN canonical_text TO nope"
                        )
                    elif fault == "invalid_record_json":
                        conn.execute("UPDATE context_item_versions SET scopes_json='not JSON'")
            contents["library.sqlite3"] = db.read_bytes()
            manifest = json.loads(contents["manifest.json"])
            manifest["database_sha256"] = sha256(contents["library.sqlite3"]).hexdigest()
            contents["manifest.json"] = json.dumps(manifest)

    alter_artifact(service, path, tmp_path, mutation)
    destination = make_destination(tmp_path)
    before_db = destination.db_path.read_bytes()
    before_settings = destination.profiles_path.read_bytes()
    with pytest.raises(BackupError):
        destination.restore_from(path, PASSWORD, jobs_idle=True)
    assert destination.db_path.read_bytes() == before_db
    assert destination.profiles_path.read_bytes() == before_settings
    assert not (tmp_path / "escape.json").exists()
    assert_clean(destination)


def test_limits_password_and_live_file_protection(library, tmp_path):
    service, _, _, _ = library
    for password in ("short", "x" * 1025):
        with pytest.raises(BackupError, match="password"):
            service.backup_to(tmp_path / "no.reweave", password)
    for path in (service.db_path, service.profiles_path, service.journal_path):
        with pytest.raises(BackupError, match="active library"):
            service.backup_to(path, PASSWORD)
    path, _ = artifact_for(service, tmp_path)
    tiny = EncryptedBackupService(
        service.db_path, service.profiles_path, limits=BackupLimits(max_artifact_bytes=100)
    )
    with pytest.raises(BackupError, match="size"):
        tiny.preview_from(path, PASSWORD)
    with pytest.raises(BackupError, match="Pause"):
        service.restore_from(path, PASSWORD)
    assert_clean(service)


def test_backup_failure_preserves_existing_artifact(library, tmp_path, monkeypatch):
    service, _, _, _ = library
    destination = tmp_path / "previous.reweave"
    destination.write_bytes(b"previous encrypted artifact")

    def failed_encryption(bundle, output, password):
        output.write(b"partial ciphertext")
        raise OSError("Synthetic full disk")

    monkeypatch.setattr(service, "_encrypt", failed_encryption)
    with pytest.raises(OSError):
        service.backup_to(destination, PASSWORD)
    assert destination.read_bytes() == b"previous encrypted artifact"
    assert not list(tmp_path.glob(".previous.reweave.*"))
    assert_clean(service)


def test_publish_failure_restores_profile_settings(library, tmp_path, monkeypatch):
    service, _, _, _ = library
    path, _ = artifact_for(service, tmp_path)
    destination = make_destination(tmp_path)
    before_db = destination.db_path.read_bytes()
    before_settings = json.loads(destination.profiles_path.read_bytes())
    original_replace = os.replace

    def fail_database(source, target):
        if Path(target) == destination.db_path:
            raise PermissionError("Synthetic open DB handle")
        original_replace(source, target)

    monkeypatch.setattr(os, "replace", fail_database)
    with pytest.raises(BackupError, match="not replaced"):
        destination.restore_from(path, PASSWORD, jobs_idle=True)
    assert destination.db_path.read_bytes() == before_db
    assert json.loads(destination.profiles_path.read_bytes()) == before_settings
    assert_clean(destination)


@pytest.mark.parametrize("committed", [False, True])
def test_interrupted_restore_recovers_without_password_or_keyring(
    library, tmp_path, monkeypatch, committed
):
    service, _, _, _ = library
    path, _ = artifact_for(service, tmp_path)
    destination = make_destination(tmp_path)
    before_settings = json.loads(destination.profiles_path.read_bytes())
    before_db = destination.db_path.read_bytes()
    original_replace = os.replace

    class SimulatedCrash(BaseException):
        pass

    def crash_at_commit(source, target):
        if Path(target) == destination.db_path:
            if committed:
                original_replace(source, target)
            raise SimulatedCrash()
        original_replace(source, target)

    monkeypatch.setattr(os, "replace", crash_at_commit)
    with pytest.raises(SimulatedCrash):
        destination.restore_from(path, PASSWORD, jobs_idle=True)
    assert destination.journal_path.exists()
    journal = destination.journal_path.read_bytes()
    assert PASSWORD.encode() not in journal
    assert b"synthetic-secret-never-export" not in journal
    assert b"Keep decisions" not in journal
    monkeypatch.setattr(os, "replace", original_replace)
    reopened = EncryptedBackupService(destination.db_path, destination.profiles_path)
    assert reopened.recover_interrupted_restore()
    assert not reopened.recover_interrupted_restore()
    if committed:
        assert ArchiveStore(destination.db_path).stats().total_conversations > 0
        assert json.loads(destination.profiles_path.read_bytes())["active_profile_id"] is None
    else:
        assert destination.db_path.read_bytes() == before_db
        assert json.loads(destination.profiles_path.read_bytes()) == before_settings
    assert_clean(destination)


def test_unknown_recovery_record_blocks_open(library):
    service, _, _, _ = library
    service.journal_path.write_text('{"version":999}', encoding="utf-8")
    with pytest.raises(RestoreRecoveryError):
        service.recover_interrupted_restore()
    assert service.journal_path.exists()


def test_settings_allowlist_and_endpoint_secrets_are_excluded(library, tmp_path):
    service, _, _, _ = library
    data = json.loads(service.profiles_path.read_bytes())
    data["api_key"] = "synthetic-secret-never-export"
    data["profiles"][0]["api_key"] = "synthetic-secret-never-export"
    data["profiles"][0]["base_url"] = "https://name:secret@example.invalid/v1?key=secret"
    data["profiles"][0]["keys"][0]["api_key"] = "synthetic-secret-never-export"
    service.profiles_path.write_text(json.dumps(data), encoding="utf-8")
    (service.db_path.parent / "extension-bridge.json").write_text("runtime-token", encoding="utf-8")
    path, _ = artifact_for(service, tmp_path)
    unpacked = tmp_path / "inspect.zip"
    service._decrypt(path, unpacked, PASSWORD)
    with zipfile.ZipFile(unpacked) as archive:
        assert set(archive.namelist()) == backup.MEMBERS
        settings = archive.read("settings.json")
        assert b"synthetic-secret" not in settings
        assert b"runtime-token" not in settings
        assert json.loads(settings)["profiles"][0]["base_url"] == ""


def test_symlink_zip_entry_rejected(library, tmp_path):
    service, _, _, _ = library
    path, _ = artifact_for(service, tmp_path)
    bundle = tmp_path / "symlink.zip"
    info = zipfile.ZipInfo("library.sqlite3")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr(info, "../../outside")
        archive.writestr("settings.json", "{}")
        archive.writestr("manifest.json", "{}")
    with path.open("wb") as output:
        service._encrypt(bundle, output, PASSWORD)
    with pytest.raises(BackupError, match="unsafe"):
        service.preview_from(path, PASSWORD)
    assert_clean(service)


def test_database_size_limit_leaves_destination_unchanged(library, tmp_path):
    service, _, _, _ = library
    limited = EncryptedBackupService(
        service.db_path,
        service.profiles_path,
        limits=replace(service.limits, max_database_bytes=1024),
    )
    path = tmp_path / "unchanged.reweave"
    path.write_bytes(b"older backup")
    with pytest.raises(BackupError, match="size"):
        limited.backup_to(path, PASSWORD)
    assert path.read_bytes() == b"older backup"
    assert_clean(service)


def test_pre_context_archive_migrates_only_in_staging(tmp_path, fixtures_dir):
    data = tmp_path / "legacy"
    data.mkdir()
    db = data / "legacy.db"
    original = ArchiveStore(db)
    original.import_directory(fixtures_dir)
    service = EncryptedBackupService(db, data / "profiles.json")
    path, _ = artifact_for(service, tmp_path)
    destination = make_destination(tmp_path)
    result = destination.restore_from(path, PASSWORD, jobs_idle=True)
    assert result.preview.context_items == 0
    assert result.preview.conversations == original.stats().total_conversations
    assert ArchiveStore(destination.db_path).stats() == original.stats()
    assert ContextLibraryStore(destination.db_path).list_items() == []
    with closing(sqlite3.connect(db)) as conn:
        assert (
            conn.execute(
                "SELECT value FROM schema_meta WHERE key='context_schema_version'"
            ).fetchone()
            is None
        )
    assert_clean(destination)


def test_busy_wal_library_is_not_replaced(library, tmp_path):
    service, _, _, _ = library
    path, _ = artifact_for(service, tmp_path)
    destination = make_destination(tmp_path)
    settings = destination.profiles_path.read_bytes()
    with closing(sqlite3.connect(destination.db_path)) as active:
        active.execute("PRAGMA journal_mode=WAL")
        active.execute("BEGIN")
        active.execute("SELECT * FROM conversations").fetchall()
        with pytest.raises(BackupError, match="busy|active"):
            destination.restore_from(path, PASSWORD, jobs_idle=True)
        assert active.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 0
        assert destination.profiles_path.read_bytes() == settings
    assert_clean(destination)


def test_startup_cleans_only_marked_owned_plaintext_workspaces(library):
    service, _, _, _ = library
    owned = service.db_path.parent / ".reweave-backup-interrupted"
    owned.mkdir()
    (owned / backup.WORKSPACE_MARKER).write_text(
        json.dumps(
            {
                "kind": "reweave-backup-workspace",
                "database": service.db_path.name,
            }
        ),
        encoding="utf-8",
    )
    (owned / "library.sqlite3").write_bytes(b"synthetic old staging data")
    unowned = service.db_path.parent / ".reweave-backup-user-folder"
    unowned.mkdir()
    note = unowned / "notes.txt"
    note.write_text("Preserve user material", encoding="utf-8")
    assert service.recover_interrupted_restore() is False
    assert not owned.exists()
    assert note.read_text(encoding="utf-8") == "Preserve user material"


def test_excessive_zip_directory_rejected_before_zipfile_parsing(library, tmp_path, monkeypatch):
    service, _, _, _ = library
    path, _ = artifact_for(service, tmp_path)
    bundle = tmp_path / "hostile-directory.zip"
    service._decrypt(path, bundle, PASSWORD)
    raw = bytearray(bundle.read_bytes())
    # Declare many entries in the end record, which zipfile otherwise starts parsing eagerly.
    struct.pack_into("<HH", raw, len(raw) - 14, 65000, 65000)
    bundle.write_bytes(raw)
    with path.open("wb") as output:
        service._encrypt(bundle, output, PASSWORD)

    def must_not_parse(*args, **kwargs):
        raise AssertionError("Directory bounds must be checked before ZipFile")

    monkeypatch.setattr(zipfile, "ZipFile", must_not_parse)
    with pytest.raises(BackupError, match="directory"):
        service.preview_from(path, PASSWORD)
    assert_clean(service)


def test_deleted_sqlite_pages_do_not_enter_artifact(library, tmp_path):
    service, _, _, _ = library
    marker = "synthetic-deleted-page-content" * 2000
    with closing(sqlite3.connect(service.db_path)) as conn, conn:
        conn.execute("PRAGMA secure_delete=OFF")
        conn.execute("CREATE TABLE temporary_deleted_content (body TEXT)")
        conn.execute("INSERT INTO temporary_deleted_content VALUES (?)", (marker,))
        conn.execute("DELETE FROM temporary_deleted_content")
    assert marker[:100].encode() in service.db_path.read_bytes()
    path, _ = artifact_for(service, tmp_path)
    bundle = tmp_path / "vacuumed.zip"
    service._decrypt(path, bundle, PASSWORD)
    with zipfile.ZipFile(bundle) as archive:
        assert marker[:100].encode() not in archive.read("library.sqlite3")
    assert_clean(service)


def test_cleanup_failure_after_commit_reports_restored_and_retains_owner_marker(
    library, tmp_path, monkeypatch
):
    service, item, _, _ = library
    path, _ = artifact_for(service, tmp_path)
    destination = make_destination(tmp_path)
    original_unlink = Path.unlink

    def locked_plaintext(target, *args, **kwargs):
        if target.name == "bundle.zip" and target.parent.parent == destination.db_path.parent:
            raise PermissionError("Synthetic antivirus lock")
        return original_unlink(target, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", locked_plaintext)
    result = destination.restore_from(path, PASSWORD, jobs_idle=True)
    assert result.recovery_pending is True
    assert ContextLibraryStore(destination.db_path).get_item(item.id) == item
    leftovers = list(destination.db_path.parent.glob(".reweave-backup-*"))
    assert len(leftovers) == 1
    assert (leftovers[0] / backup.WORKSPACE_MARKER).exists()
    monkeypatch.setattr(Path, "unlink", original_unlink)
    destination.recover_interrupted_restore()
    assert_clean(destination)
