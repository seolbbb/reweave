"""Actual encrypted transfer endpoints and exclusion against queued work."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from reweave.archive import ArchiveStore
from reweave.backup_api import backup_router, cleanup_backup_transfers
from reweave.context_library import ContextLibraryStore
from reweave.encrypted_backup import BackupLimits, BackupPreview, RestoreResult
from reweave.maintenance import MaintenanceBusyError, MaintenanceGate
from reweave.web import create_app


def test_gate_reserves_queued_work_and_releases_cancellation():
    gate = MaintenanceGate()
    stop = Event()
    with ThreadPoolExecutor(max_workers=1) as executor:
        first = gate.submit(executor, stop.wait, 5)
        queued = gate.submit(executor, lambda: None)
        assert queued.cancel()
        with pytest.raises(MaintenanceBusyError), gate.exclusive():
            pass
        stop.set()
        first.result()
    with gate.exclusive(), pytest.raises(MaintenanceBusyError), gate.operation():
        pass
    with gate.operation():
        pass


def test_encrypted_api_roundtrip_busy_wrong_password_and_restart(tmp_path, fixtures_dir):
    db = tmp_path / "library.db"
    ArchiveStore(db).import_directory(fixtures_dir)
    original_count = ArchiveStore(db).stats().total_conversations
    app = create_app(db, data_dir=tmp_path)
    password = "local synthetic backup password"
    with TestClient(app) as client:
        app.state.context_analysis_scheduler.stop()
        bad = client.post("/api/archive/encrypted-backup", json={"password": "short"})
        assert bad.status_code == 400
        assert "short" not in bad.text
        artifact = client.post("/api/archive/encrypted-backup", json={"password": password})
        assert artifact.status_code == 200, artifact.text[:500]
        assert artifact.content[:16] != b"SQLite format 3\x00"
        assert artifact.headers["cache-control"] == "no-store"
        upload = {"file": ("library.reweave", artifact.content, "application/octet-stream")}
        preview = client.post(
            "/api/archive/encrypted-restore/preview", files=upload, data={"password": password}
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["preview"]["conversations"] == original_count
        source = ArchiveStore(db).search_conversations("Obsidian")[0]
        client.delete(f"/api/conversations/{source.id}")
        before = ArchiveStore(db).stats().total_conversations
        assert before == original_count - 1
        wrong = client.post(
            "/api/archive/encrypted-restore",
            files=upload,
            data={"password": "wrong password provided", "confirmation": "RESTORE"},
        )
        assert wrong.status_code == 400
        assert ArchiveStore(db).stats().total_conversations == before
        with app.state.maintenance_gate.operation():
            busy = client.post(
                "/api/archive/encrypted-restore",
                files=upload,
                data={"password": password, "confirmation": "RESTORE"},
            )
        assert busy.status_code == 409
        assert ArchiveStore(db).stats().total_conversations == before
        missing_confirmation = client.post(
            "/api/archive/encrypted-restore",
            files=upload,
            data={"password": password, "confirmation": "no"},
        )
        assert missing_confirmation.status_code == 400
        restored = client.post(
            "/api/archive/encrypted-restore",
            files=upload,
            data={"password": password, "confirmation": "RESTORE"},
        )
        assert restored.status_code == 200, restored.text
        assert restored.json()["requires_reconnect"]
        assert ArchiveStore(db).stats().total_conversations == original_count
        assert client.get("/api/context/items").status_code == 200
        with app.state.maintenance_gate.exclusive():
            assert client.get("/api/context/items").status_code == 503
    with TestClient(create_app(db, data_dir=tmp_path)) as restarted:
        assert restarted.get("/api/context/analysis/policy").json()["provider_connected"] is False
        assert ContextLibraryStore(db).count_items() == 0
    assert not list((tmp_path / "backup-transfers").glob("*.reweave"))


@pytest.mark.parametrize("failure", ["reinitialize", "transfer_cleanup"])
def test_committed_restore_is_reported_as_success_with_restart_gate(tmp_path, monkeypatch, failure):
    gate = MaintenanceGate()
    committed = False
    preview = BackupPreview(1, "2026-09-09", 100, 1, 2, 1, 2, 2, 1, 0)

    def restore(*args, **kwargs):
        nonlocal committed
        committed = True
        return RestoreResult(preview)

    def after_restore():
        if failure == "reinitialize":
            raise OSError("Injected post-commit disk error")

    unlink = Path.unlink

    def maybe_fail_cleanup(path, *args, **kwargs):
        if committed and failure == "transfer_cleanup" and path.suffix == ".reweave":
            raise PermissionError("Injected Windows file lock")
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", maybe_fail_cleanup)
    service = SimpleNamespace(
        db_path=tmp_path / "library.db", limits=BackupLimits(), restore_from=restore
    )
    app = FastAPI()
    app.include_router(backup_router(service, gate, on_restored=after_restore))
    with TestClient(app) as client:
        result = client.post(
            "/api/archive/encrypted-restore",
            files={"file": ("local.reweave", b"synthetic encrypted artifact")},
            data={"password": "synthetic password", "confirmation": "RESTORE"},
        )
    assert committed
    assert result.status_code == 200
    assert result.json()["recovery_pending"] is True
    assert "restored" in result.json()["notice"]
    with pytest.raises(MaintenanceBusyError, match="Restart"), gate.operation():
        pass
    monkeypatch.setattr(Path, "unlink", unlink)
    assert cleanup_backup_transfers(service.db_path) == 0
    assert not list((tmp_path / "backup-transfers").glob("*.reweave"))
