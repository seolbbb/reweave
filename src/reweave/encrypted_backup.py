"""Versioned, authenticated local backups and fail-before-replace restoration.

The caller must exclude all jobs and requests that can use the library while restoring,
and call ``recover_interrupted_restore`` before opening stores at application startup.
Only SQLite and explicitly allowed non-secret profile settings enter the artifact.
Temporary plaintext stays under the destination library directory and is removed on exit.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import stat
import struct
import tempfile
import time
import zipfile
import zlib
from contextlib import closing, contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from reweave.analysis_policy import AnalysisPolicyStore
from reweave.archive import ArchiveStore
from reweave.context_chunking import ChunkStore
from reweave.context_library import CONTEXT_SCHEMA_VERSION, ContextLibraryStore
from reweave.context_review import ContextReviewStore
from reweave.context_trust import ContextTrustStore

MAGIC = b"REWEAVE-BACKUP\n"
FORMAT_VERSION = 1
HEADER = struct.Struct(f">{len(MAGIC)}sB16s12sQ")
CHUNK_BYTES = 1024 * 1024
PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_BYTES = 1024
ARCHIVE_SCHEMA_VERSION = 2
MEMBERS = {"manifest.json", "library.sqlite3", "settings.json"}
RECONNECT_NOTICE = "Provider keys are excluded. Reconnect a provider to resume analysis."
WORKSPACE_MARKER = ".owner.json"


class BackupError(ValueError):
    """A safe, user-facing backup or restore failure without source or secret content."""


class RestoreRecoveryError(BackupError):
    """Application startup must stop until the pending settings recovery succeeds."""


class WorkspaceCleanupError(RestoreRecoveryError):
    """An owned staging workspace remains marked for cleanup at next startup."""


@dataclass(frozen=True)
class BackupLimits:
    max_database_bytes: int = 2 * 1024**3
    max_artifact_bytes: int = 2 * 1024**3 + 16 * 1024**2
    max_settings_bytes: int = 256 * 1024
    max_manifest_bytes: int = 64 * 1024
    max_compression_ratio: int = 1000
    validation_timeout_seconds: float = 120


@dataclass(frozen=True)
class BackupPreview:
    format_version: int
    created_at: str
    database_bytes: int
    conversations: int
    messages: int
    briefs: int
    context_items: int
    versions: int
    links: int
    profiles: int
    requires_reconnect: bool = True
    notice: str = RECONNECT_NOTICE


@dataclass(frozen=True)
class BackupResult:
    path: str
    bytes_written: int
    sha256: str
    preview: BackupPreview


@dataclass(frozen=True)
class RestoreResult:
    preview: BackupPreview
    recovery_pending: bool = False
    requires_reconnect: bool = True
    notice: str = RECONNECT_NOTICE


class EncryptedBackupService:
    """Perform local backup I/O without loading keyring or touching runtime registration."""

    def __init__(self, db_path: Path, profiles_path: Path, *, limits: BackupLimits | None = None):
        self.db_path = db_path.resolve()
        self.profiles_path = profiles_path.resolve()
        self.limits = limits or BackupLimits()
        if self.db_path == self.profiles_path:
            raise BackupError("Library and profile paths must differ.")
        self.journal_path = self.db_path.with_name(f".{self.db_path.name}.restore.json")

    def backup_to(self, destination: Path, password: str) -> BackupResult:
        """Write one encrypted artifact atomically; an existing destination is preserved."""
        _password_bytes(password)
        self._require_recovered()
        destination = destination.resolve()
        self._check_artifact_path(destination)
        if not self.db_path.is_file():
            raise BackupError("There is no local library to back up.")
        with self._workspace() as workspace:
            database = workspace / "library.sqlite3"
            try:
                with (
                    closing(_connect_readonly(self.db_path)) as source,
                    closing(sqlite3.connect(database)) as target,
                ):
                    deadline = time.monotonic() + self.limits.validation_timeout_seconds

                    def bounded_backup(status, remaining, total):
                        if total * source.execute("PRAGMA page_size").fetchone()[0] > (
                            self.limits.max_database_bytes
                        ):
                            raise BackupError("The library exceeds the supported backup size.")
                        if time.monotonic() > deadline:
                            raise BackupError("The library stayed busy too long to back up.")

                    source.backup(target, pages=256, progress=bounded_backup, sleep=0.05)
                # Reclaim deleted SQLite pages; the artifact should contain live records only.
                with closing(sqlite3.connect(database)) as conn:
                    conn.execute("VACUUM")
                self._validate_database(database)
            except sqlite3.Error as exc:
                raise BackupError("The local library could not be backed up safely.") from exc
            settings = self._read_profiles()
            created_at = datetime.now(UTC).isoformat()
            preview = self._preview(database, settings, created_at)
            bundle = workspace / "bundle.zip"
            manifest = {
                "format_version": FORMAT_VERSION,
                "created_at": created_at,
                "database_sha256": _file_digest(database),
                "settings_version": 1,
            }
            with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                archive.write(database, "library.sqlite3")
                archive.writestr("manifest.json", _json_bytes(manifest))
                archive.writestr("settings.json", _json_bytes(settings))
            destination.parent.mkdir(parents=True, exist_ok=True)
            with _atomic_output(destination) as output:
                self._encrypt(bundle, output, password)
                output.flush()
                os.fsync(output.fileno())
                bytes_written = output.tell()
                # Calculate before publication so no post-commit read error reports failure.
                output.seek(0)
                digest = _stream_digest(output)
            return BackupResult(str(destination), bytes_written, digest, preview)

    def preview_from(self, source_path: Path, password: str) -> BackupPreview:
        """Authenticate, inspect, and stage migrations without changing the working library."""
        with self._prepared(source_path, password) as (_, _, preview):
            return preview

    def restore_from(
        self, source_path: Path, password: str, *, jobs_idle: bool = False
    ) -> RestoreResult:
        """Replace validated SQLite atomically, with recoverable non-secret settings I/O.

        ``jobs_idle`` is an explicit caller assertion, not a concurrency lock. The caller
        must hold its maintenance lock through this method and re-create stores afterward.
        No credentials are read, deleted, or reactivated. Old key references are retained
        disabled, and the restored active profile is unset until an explicit reconnection.
        """
        if not jobs_idle:
            raise BackupError("Pause library jobs before restoring a backup.")
        self._require_recovered()
        result = None
        try:
            with self._prepared(source_path, password) as (database, settings, preview):
                result = self._commit_restore(database, settings, preview)
            return result
        except WorkspaceCleanupError:
            if result is not None:
                return replace(result, recovery_pending=True)
            raise

    def _commit_restore(self, database, settings, preview):
        next_settings = _profile_settings(settings, disconnect=True)
        previous_settings = self._read_profiles()
        operation_id = uuid4().hex
        current_day = datetime.now(UTC).date().isoformat()
        current_usage = None
        if self.db_path.is_file():
            with closing(_connect_readonly(self.db_path)) as current:
                if current.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='analysis_usage'"
                ).fetchone():
                    current_usage = current.execute(
                        "SELECT reserved_attempts, reserved_tokens FROM analysis_usage WHERE day=?",
                        (current_day,),
                    ).fetchone()
        with closing(sqlite3.connect(database)) as conn, conn:
            if self.db_path.is_file():
                with closing(_connect_readonly(self.db_path)) as current:
                    if current.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' "
                        "AND name='context_chunk_runs'"
                    ).fetchone():
                        # Preserve spent calls only for the exact restored run identity.
                        # Checkpoints and unrelated/new generations still come from the backup.
                        conn.executemany(
                            "UPDATE context_chunk_runs "
                            "SET provider_calls=MAX(provider_calls,?) WHERE run_key=?",
                            current.execute(
                                "SELECT provider_calls,run_key FROM context_chunk_runs"
                            ),
                        )
            if current_usage is not None:
                conn.execute(
                    "INSERT INTO analysis_usage(day,reserved_attempts,reserved_tokens) "
                    "VALUES(?,?,?) "
                    "ON CONFLICT(day) DO UPDATE SET "
                    "reserved_attempts=MAX(reserved_attempts,excluded.reserved_attempts), "
                    "reserved_tokens=MAX(reserved_tokens,excluded.reserved_tokens)",
                    (current_day, *current_usage),
                )
            conn.execute(
                "INSERT OR REPLACE INTO schema_meta(key, value) VALUES (?, ?)",
                ("restore_operation_id", operation_id),
            )
            # Imported in-flight claims must resume as pending, never be lost as running.
            conn.execute(
                "UPDATE context_analysis_queue SET status='pending', next_retry_at=NULL "
                "WHERE status='running'"
            )
        self._prepare_active_database()
        journal = {
            "version": 1,
            "operation_id": operation_id,
            "previous_profiles_exist": self.profiles_path.exists(),
            "previous_profiles": previous_settings,
            "next_profiles": next_settings,
        }
        _atomic_json(self.journal_path, journal)
        try:
            _atomic_json(self.profiles_path, next_settings)
            # SQLite is the commit point. Its operation marker decides startup recovery.
            os.replace(database, self.db_path)
        except OSError as exc:
            try:
                self.recover_interrupted_restore()
            except (OSError, BackupError) as recovery_exc:
                raise RestoreRecoveryError(
                    "The library was not replaced. Restart to recover provider settings."
                ) from recovery_exc
            raise BackupError("The library was not replaced; close active jobs and retry.") from exc
        # A cleanup failure does not undo a committed database. Startup finalizes it.
        try:
            self.journal_path.unlink()
        except OSError:
            return RestoreResult(preview=preview, recovery_pending=True)
        return RestoreResult(preview=preview)

    def recover_interrupted_restore(self) -> bool:
        """Idempotently finish/roll back settings before any app store or scheduler opens.

        The journal holds only allowlisted non-secret settings and a random operation ID.
        No password is needed; no previous source DB or raw conversation is journaled.
        Failure must prevent app startup rather than run with mixed settings and data.
        """
        if not self.journal_path.exists():
            self.cleanup_interrupted_workspaces()
            return False
        try:
            data = _read_json(self.journal_path, 2 * self.limits.max_settings_bytes + 4096)
            if (
                not isinstance(data, dict)
                or data.get("version") != 1
                or not re.fullmatch("[a-f0-9]{32}", str(data.get("operation_id", "")))
                or type(data.get("previous_profiles_exist")) is not bool
            ):
                raise BackupError("The restore recovery record is invalid.")
            previous = _profile_settings(data.get("previous_profiles"))
            next_settings = _profile_settings(data.get("next_profiles"), disconnect=True)
            committed = False
            if self.db_path.exists():
                with closing(_connect_readonly(self.db_path)) as conn:
                    has_meta = conn.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_meta'"
                    ).fetchone()
                    marker = (
                        conn.execute(
                            "SELECT value FROM schema_meta WHERE key='restore_operation_id'"
                        ).fetchone()
                        if has_meta
                        else None
                    )
                    committed = bool(marker and marker[0] == data["operation_id"])
            if committed:
                _atomic_json(self.profiles_path, next_settings)
            elif data["previous_profiles_exist"]:
                _atomic_json(self.profiles_path, previous)
            else:
                self.profiles_path.unlink(missing_ok=True)
            self.journal_path.unlink()
            self.cleanup_interrupted_workspaces()
            return True
        except (OSError, sqlite3.Error, ValueError) as exc:
            raise RestoreRecoveryError(
                "Restore settings recovery is incomplete. Keep the library closed and retry."
            ) from exc

    def cleanup_interrupted_workspaces(self) -> int:
        """Remove only marked app-owned temporary files at exclusive application startup.

        Do not call while any backup/preview/restore is running. No recursive deletion or
        paths from the journal are used, and a symlink or unexpected entry fails closed.
        """
        removed = 0
        for directory in self.db_path.parent.glob(".reweave-backup-*"):
            if directory.is_symlink() or not directory.is_dir():
                continue
            # Resolve once before any unlink; junctions must not escape the library directory.
            if directory.resolve().parent != self.db_path.parent:
                continue
            marker = directory / WORKSPACE_MARKER
            if not marker.is_file() or marker.is_symlink():
                continue
            value = _read_json(marker, 1024)
            if value != {"kind": "reweave-backup-workspace", "database": self.db_path.name}:
                continue
            self._remove_workspace(directory)
            removed += 1
        return removed

    @staticmethod
    def _remove_workspace(directory):
        if not directory.exists():
            return
        known_names = MEMBERS | {"bundle.zip", "schema.sqlite3", WORKSPACE_MARKER}
        known_names |= {
            f"{name}{suffix}"
            for name in ("library.sqlite3", "schema.sqlite3")
            for suffix in ("-wal", "-shm", "-journal")
        }
        try:
            entries = list(directory.iterdir())
            if any(
                entry.name not in known_names or not entry.is_file() or entry.is_symlink()
                for entry in entries
            ):
                raise WorkspaceCleanupError("An interrupted backup workspace needs local cleanup.")
            marker = directory / WORKSPACE_MARKER
            for entry in entries:
                if entry != marker:
                    entry.unlink()
            # Keep the ownership marker while any plaintext may still need startup cleanup.
            marker.unlink(missing_ok=True)
            directory.rmdir()
        except OSError as exc:
            raise WorkspaceCleanupError(
                "Restart Reweave to finish cleaning its temporary backup files."
            ) from exc

    def _require_recovered(self):
        if self.journal_path.exists():
            raise RestoreRecoveryError("Restart Reweave to finish the interrupted restore first.")

    def _check_artifact_path(self, path: Path):
        protected = {
            self.db_path,
            self.profiles_path,
            self.journal_path,
            Path(f"{self.db_path}-wal"),
            Path(f"{self.db_path}-shm"),
            Path(f"{self.db_path}-journal"),
        }
        if path in protected or (
            path.exists() and any(item.exists() and path.samefile(item) for item in protected)
        ):
            raise BackupError("Choose an artifact path outside the active library files.")

    @contextmanager
    def _workspace(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        directory = Path(tempfile.mkdtemp(prefix=".reweave-backup-", dir=self.db_path.parent))
        try:
            (directory / WORKSPACE_MARKER).write_bytes(
                _json_bytes(
                    {
                        "kind": "reweave-backup-workspace",
                        "database": self.db_path.name,
                    }
                )
            )
            yield directory
        finally:
            self._remove_workspace(directory)

    @contextmanager
    def _prepared(self, source_path: Path, password: str):
        _password_bytes(password)
        source_path = source_path.resolve()
        self._check_artifact_path(source_path)
        with self._workspace() as workspace:
            bundle = workspace / "bundle.zip"
            self._decrypt(source_path, bundle, password)
            database, settings, created_at = self._unpack(bundle, workspace)
            self._validate_database(database)
            try:
                ArchiveStore(database)
                ContextReviewStore(ContextLibraryStore(database))
                ContextTrustStore(database)
                ChunkStore(database)
                AnalysisPolicyStore(database)
                self._validate_database(database)
                self._validate_current_schema(database, workspace / "schema.sqlite3")
                # Validate the fields required by actual store readers, not table names alone.
                context = ContextLibraryStore(database)
                context.list_briefs(limit=1)
                context.list_items(limit=1)
                policy = AnalysisPolicyStore(database)
                policy.save(policy.get())
            except (sqlite3.Error, TypeError, ValueError, KeyError) as exc:
                raise BackupError(
                    "The backup schema cannot be safely restored by this version."
                ) from exc
            yield database, settings, self._preview(database, settings, created_at)

    def _read_profiles(self):
        if not self.profiles_path.exists():
            return {"active_profile_id": None, "profiles": []}
        return _profile_settings(_read_json(self.profiles_path, self.limits.max_settings_bytes))

    def _preview(self, database, settings, created_at):
        with closing(_connect_readonly(database)) as conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master")}

            def count(table):
                return (
                    conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                    if (table in tables)
                    else 0
                )

            return BackupPreview(
                FORMAT_VERSION,
                created_at,
                database.stat().st_size,
                count("conversations"),
                count("messages"),
                count("conversation_briefs"),
                count("context_items"),
                count("context_item_versions"),
                count("context_item_links"),
                len(settings["profiles"]),
            )

    def _validate_database(self, database):
        if database.stat().st_size > self.limits.max_database_bytes:
            raise BackupError("The backup library exceeds the supported size.")
        try:
            with closing(_connect_readonly(database)) as conn:
                deadline = time.monotonic() + self.limits.validation_timeout_seconds
                conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
                objects = conn.execute("SELECT name, type, sql FROM sqlite_master").fetchall()
                if any(row[1] in {"view", "trigger"} for row in objects):
                    raise BackupError(
                        "Backups containing executable views or triggers are unsupported."
                    )
                for name, _, sql in objects:
                    if (
                        sql
                        and "CREATE VIRTUAL TABLE" in sql.upper()
                        and (
                            name not in {"messages_fts", "messages_fts_trigram"}
                            or not re.search(r"\bUSING\s+fts5\s*\(", sql, re.IGNORECASE)
                        )
                    ):
                        raise BackupError("The backup uses an unsupported search extension.")
                tables = {row[0] for row in objects if row[1] == "table"}
                if not {"conversations", "messages", "insight_reports", "schema_meta"} <= tables:
                    raise BackupError("The backup does not contain a Reweave library.")
                versions = dict(conn.execute("SELECT key, value FROM schema_meta"))
                for name, minimum, maximum in (
                    ("schema_version", 1, ARCHIVE_SCHEMA_VERSION),
                    ("context_schema_version", 1, CONTEXT_SCHEMA_VERSION),
                ):
                    value = versions.get(name)
                    if value is None and name == "context_schema_version":
                        if "context_items" in tables:
                            raise BackupError(
                                "The Context Library has no supported schema version."
                            )
                        continue
                    if (
                        value is None
                        or not str(value).isdigit()
                        or not minimum <= int(value) <= maximum
                    ):
                        raise BackupError("The backup needs a different Reweave version.")
                if conn.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                    raise BackupError("The backup failed its database integrity check.")
                if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
                    raise BackupError("The backup contains broken source or Context links.")
        except sqlite3.Error as exc:
            raise BackupError(
                "The backup database is invalid or could not be validated safely."
            ) from exc

    def _prepare_active_database(self):
        if not self.db_path.exists():
            return
        try:
            with closing(sqlite3.connect(self.db_path, timeout=0)) as conn:
                # Refuse active WAL readers/writers rather than detach their live sidecar files.
                mode = conn.execute("PRAGMA journal_mode=DELETE").fetchone()[0]
                if mode != "delete":
                    raise BackupError("Close active library work before restoring.")
                conn.execute("BEGIN EXCLUSIVE")
                conn.rollback()
        except sqlite3.Error as exc:
            raise BackupError("The library is busy. Pause its jobs before restoring.") from exc

    def _validate_current_schema(self, database, reference):
        """Compare actual column/primary-key/foreign-key contracts after staged migration."""
        ArchiveStore(reference)
        ContextReviewStore(ContextLibraryStore(reference))
        ContextTrustStore(reference)
        ChunkStore(reference)
        AnalysisPolicyStore(reference)
        with (
            closing(_connect_readonly(database)) as candidate,
            closing(_connect_readonly(reference)) as expected,
        ):
            deadline = time.monotonic() + self.limits.validation_timeout_seconds
            candidate.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
            tables = [
                row[0]
                for row in expected.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            ]
            for table in tables:
                # Names come only from the fresh application-owned schema, never uploaded SQL.
                if candidate.execute(f'PRAGMA table_info("{table}")').fetchall() != (
                    expected.execute(f'PRAGMA table_info("{table}")').fetchall()
                ):
                    raise BackupError("The backup has an incompatible library table definition.")
                actual_keys = candidate.execute(f'PRAGMA foreign_key_list("{table}")').fetchall()
                expected_keys = expected.execute(f'PRAGMA foreign_key_list("{table}")').fetchall()
                if actual_keys != expected_keys:
                    raise BackupError("The backup has incompatible source or Context link rules.")
            json_columns = {
                "conversation_briefs": (
                    "important_outcomes",
                    "decisions",
                    "lessons",
                    "unresolved_questions",
                    "actions",
                ),
                "context_item_versions": ("scopes_json", "evidence_ids_json"),
                "insight_reports": ("selected_conversation_ids",),
                "analysis_policy": ("settings_json",),
                "context_review_events": ("reasons_json",),
                "context_chunk_checkpoints": ("result_json",),
                "context_destination_preferences": ("scope_bindings_json",),
                "context_destination_events": ("scope_bindings_json",),
            }
            for table, columns in json_columns.items():
                for column in columns:
                    if candidate.execute(
                        f'SELECT 1 FROM "{table}" WHERE NOT json_valid("{column}") LIMIT 1'
                    ).fetchone():
                        raise BackupError("The backup contains invalid structured library records.")
            if candidate.execute(
                "SELECT 1 FROM context_items i LEFT JOIN context_item_versions v "
                "ON v.item_id=i.id AND v.version=i.current_version "
                "WHERE v.item_id IS NULL LIMIT 1"
            ).fetchone():
                raise BackupError("The backup is missing current Context revision records.")

    def _encrypt(self, bundle, output, password):
        size = bundle.stat().st_size
        if size + HEADER.size + 16 > self.limits.max_artifact_bytes:
            raise BackupError("The encrypted backup exceeds the supported file size.")
        salt, nonce = os.urandom(16), os.urandom(12)
        header = HEADER.pack(MAGIC, FORMAT_VERSION, salt, nonce, size)
        encryptor = Cipher(
            algorithms.AES(_derive_key(password, salt)), modes.GCM(nonce)
        ).encryptor()
        encryptor.authenticate_additional_data(header)
        output.write(header)
        with bundle.open("rb") as source:
            while chunk := source.read(CHUNK_BYTES):
                output.write(encryptor.update(chunk))
        output.write(encryptor.finalize())
        output.write(encryptor.tag)

    def _decrypt(self, source_path, bundle, password):
        try:
            with source_path.open("rb") as source:
                size = os.fstat(source.fileno()).st_size
                if size > self.limits.max_artifact_bytes or size < HEADER.size + 16:
                    raise BackupError(
                        "The backup file is incomplete or exceeds the supported size."
                    )
                header = source.read(HEADER.size)
                magic, version, salt, nonce, ciphertext_bytes = HEADER.unpack(header)
                if magic != MAGIC or version != FORMAT_VERSION:
                    raise BackupError("Choose a supported encrypted Reweave backup (.reweave).")
                if ciphertext_bytes != size - HEADER.size - 16:
                    raise BackupError("The encrypted backup length is invalid.")
                decryptor = Cipher(
                    algorithms.AES(_derive_key(password, salt)), modes.GCM(nonce)
                ).decryptor()
                decryptor.authenticate_additional_data(header)
                with bundle.open("xb") as output:
                    remaining = ciphertext_bytes
                    while remaining:
                        chunk = source.read(min(CHUNK_BYTES, remaining))
                        if not chunk:
                            raise BackupError("The encrypted backup is incomplete.")
                        output.write(decryptor.update(chunk))
                        remaining -= len(chunk)
                    # No decompression, parsing, migration, or publication occurs before this.
                    output.write(decryptor.finalize_with_tag(source.read(16)))
                    if source.read(1):
                        raise BackupError("The encrypted backup has unexpected trailing data.")
        except InvalidTag as exc:
            raise BackupError("The password is incorrect or the backup has been damaged.") from exc
        except (OSError, struct.error) as exc:
            raise BackupError("The encrypted backup could not be read.") from exc

    def _unpack(self, bundle, workspace):
        bounds = {
            "library.sqlite3": self.limits.max_database_bytes,
            "settings.json": self.limits.max_settings_bytes,
            "manifest.json": self.limits.max_manifest_bytes,
        }
        try:
            _check_zip_directory(bundle, self.limits.max_manifest_bytes)
            with zipfile.ZipFile(bundle) as archive:
                entries = archive.infolist()
                if len(entries) != len(MEMBERS) or {entry.filename for entry in entries} != MEMBERS:
                    raise BackupError(
                        "The backup has unexpected, duplicate, or unsafe file entries."
                    )
                for entry in entries:
                    mode = entry.external_attr >> 16
                    if (
                        entry.is_dir()
                        or (mode and stat.S_IFMT(mode) not in {0, stat.S_IFREG})
                        or entry.flag_bits & 1
                        or entry.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                        or entry.file_size > bounds[entry.filename]
                        or entry.file_size
                        > max(1, entry.compress_size) * self.limits.max_compression_ratio
                    ):
                        raise BackupError(
                            "A backup entry is unsafe or exceeds supported size limits."
                        )
                    total = 0
                    # Exact member names above are the only paths used. Never use extractall.
                    with (
                        archive.open(entry) as source,
                        (workspace / entry.filename).open("xb") as target,
                    ):
                        while chunk := source.read(CHUNK_BYTES):
                            total += len(chunk)
                            if total > bounds[entry.filename] or total > entry.file_size:
                                raise BackupError("A backup entry exceeds its declared size.")
                            target.write(chunk)
                    if total != entry.file_size:
                        raise BackupError("A backup entry is incomplete.")
            manifest = _read_json(workspace / "manifest.json", self.limits.max_manifest_bytes)
            if (
                not isinstance(manifest, dict)
                or manifest.get("format_version") != FORMAT_VERSION
                or manifest.get("settings_version") != 1
                or not isinstance(manifest.get("created_at"), str)
            ):
                raise BackupError("The backup manifest is unsupported.")
            try:
                datetime.fromisoformat(manifest["created_at"])
            except ValueError as exc:
                raise BackupError("The backup timestamp is invalid.") from exc
            database = workspace / "library.sqlite3"
            if manifest.get("database_sha256") != _file_digest(database):
                raise BackupError("The backup database does not match its manifest.")
            settings = _profile_settings(
                _read_json(workspace / "settings.json", self.limits.max_settings_bytes)
            )
            return database, settings, manifest["created_at"]
        except (
            zipfile.BadZipFile,
            zlib.error,
            EOFError,
            struct.error,
            UnicodeError,
            RuntimeError,
            NotImplementedError,
            OSError,
        ) as exc:
            raise BackupError("The authenticated backup contents are invalid.") from exc


def _password_bytes(password: str) -> bytes:
    if not isinstance(password, str) or len(password) < PASSWORD_MIN_LENGTH:
        raise BackupError(f"Use a backup password of at least {PASSWORD_MIN_LENGTH} characters.")
    encoded = password.encode("utf-8")
    if len(encoded) > PASSWORD_MAX_BYTES:
        raise BackupError("The backup password is too long.")
    return encoded


def _check_zip_directory(path, maximum_directory_bytes):
    """Bound central-directory allocation before zipfile builds its entry list.

    Reweave writes three entries, a single disk and no archive comment. Support the fixed
    ZIP64 end records produced for large databases, without trusting unbounded offsets.
    """
    with path.open("rb") as source:
        size = os.fstat(source.fileno()).st_size
        if size < 22:
            raise BackupError("The authenticated backup archive is incomplete.")
        source.seek(-22, os.SEEK_END)
        magic, disk, cd_disk, disk_entries, entries, cd_size, cd_offset, comment = struct.unpack(
            "<4s4H2LH", source.read(22)
        )
        if magic != b"PK\x05\x06" or disk or cd_disk or comment:
            raise BackupError("The backup archive has unsupported directory records.")
        directory_end = size - 22
        if size >= 42:
            source.seek(-42, os.SEEK_END)
            locator = source.read(20)
            if locator[:4] == b"PK\x06\x07":
                _, locator_disk, record_offset, disks = struct.unpack("<4sLQL", locator)
                if locator_disk or disks != 1 or record_offset + 56 != size - 42:
                    raise BackupError("The backup ZIP64 directory is invalid.")
                source.seek(record_offset)
                record = struct.unpack("<4sQHHLLQQQQ", source.read(56))
                (
                    magic,
                    record_size,
                    _,
                    _,
                    disk,
                    cd_disk,
                    disk_entries,
                    entries,
                    cd_size,
                    cd_offset,
                ) = record
                if magic != b"PK\x06\x06" or record_size != 44 or disk or cd_disk:
                    raise BackupError("The backup ZIP64 directory is unsupported.")
                directory_end = record_offset
        if (
            disk_entries != len(MEMBERS)
            or entries != len(MEMBERS)
            or cd_size > maximum_directory_bytes
            or cd_offset + cd_size != directory_end
        ):
            raise BackupError("The backup archive has unsafe or excessive directory entries.")


def _derive_key(password: str, salt: bytes) -> bytes:
    # Version 1 fixes these parameters, so untrusted headers cannot raise the KDF cost.
    return Scrypt(salt=salt, length=32, n=2**17, r=8, p=1).derive(_password_bytes(password))


def _connect_readonly(path):
    conn = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=5)
    conn.execute("PRAGMA trusted_schema=OFF")
    conn.execute("PRAGMA query_only=ON")
    return conn


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode(
        "utf-8"
    )


def _read_json(path, limit):
    try:
        with path.open("rb") as source:
            raw = source.read(limit + 1)
        if len(raw) > limit:
            raise BackupError("A backup settings file exceeds its size limit.")
        return json.loads(raw)
    except (UnicodeError, ValueError, RecursionError, OSError) as exc:
        raise BackupError("A backup settings file is invalid or unavailable.") from exc


def _profile_settings(value, *, disconnect=False):
    """Allowlist metadata; never instantiate a store or ask keyring for any credentials."""
    if not isinstance(value, dict) or not isinstance(value.get("profiles"), list):
        raise BackupError("Provider profile settings are invalid.")
    if len(value["profiles"]) > 100:
        raise BackupError("The backup contains too many provider profiles.")
    profiles, ids = [], set()

    def text(record, name, maximum=1024, default=""):
        field = record.get(name, default)
        if not isinstance(field, str) or len(field) > maximum:
            raise BackupError("A provider profile setting is invalid.")
        return field

    for record in value["profiles"]:
        if not isinstance(record, dict):
            raise BackupError("A provider profile is invalid.")
        profile_id = text(record, "id", 128)
        if not profile_id or profile_id in ids:
            raise BackupError("Provider profile identities are invalid.")
        ids.add(profile_id)
        url = text(record, "base_url", 4096)
        if url:
            try:
                parts = urlsplit(url)
                # Credential-bearing endpoints are not non-secret settings.
                if parts.username or parts.password or parts.query or parts.fragment:
                    url = ""
            except ValueError as exc:
                raise BackupError("A provider endpoint is invalid.") from exc
        custom_models = record.get("custom_models", [])
        keys = record.get("keys", [])
        if (
            not isinstance(custom_models, list)
            or len(custom_models) > 200
            or any(not isinstance(item, str) or len(item) > 512 for item in custom_models)
            or not isinstance(keys, list)
            or len(keys) > 100
        ):
            raise BackupError("Provider models or key references are invalid.")
        references, key_ids = [], set()
        for key in keys:
            if not isinstance(key, dict):
                raise BackupError("A provider key reference is invalid.")
            key_id = text(key, "id", 128)
            if not key_id or key_id in key_ids or type(key.get("enabled", True)) is not bool:
                raise BackupError("A provider key reference is invalid.")
            priority = key.get("priority", 0)
            if type(priority) is not int or not -10000 <= priority <= 10000:
                raise BackupError("A provider key priority is invalid.")
            key_ids.add(key_id)
            references.append(
                {
                    "id": key_id,
                    "label": text(key, "label"),
                    "enabled": False if disconnect else key.get("enabled", True),
                    "priority": priority,
                }
            )
        profiles.append(
            {
                "id": profile_id,
                "name": text(record, "name"),
                "provider": text(record, "provider", 128),
                "base_url": url,
                "default_model": text(record, "default_model", 512),
                "custom_models": custom_models,
                "keys": references,
            }
        )
    active = value.get("active_profile_id")
    if active is not None and (not isinstance(active, str) or active not in ids):
        raise BackupError("The active provider profile is invalid.")
    return {"active_profile_id": None if disconnect else active, "profiles": profiles}


@contextmanager
def _atomic_output(destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    temporary = Path(temporary)
    try:
        with os.fdopen(descriptor, "w+b") as output:
            yield output
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_json(destination, value):
    with _atomic_output(destination) as output:
        output.write(_json_bytes(value))
        output.flush()
        os.fsync(output.fileno())


def _stream_digest(source):
    digest = sha256()
    while chunk := source.read(CHUNK_BYTES):
        digest.update(chunk)
    return digest.hexdigest()


def _file_digest(path):
    with path.open("rb") as source:
        return _stream_digest(source)
