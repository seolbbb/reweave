"""Password-protected local backup downloads and confirmed replacement."""

from __future__ import annotations

import re
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, SecretStr
from starlette.background import BackgroundTask

from reweave.encrypted_backup import BackupError, EncryptedBackupService
from reweave.maintenance import MaintenanceBusyError, MaintenanceGate

BACKUP_UPLOAD = File(...)
BACKUP_PASSWORD = Form(...)
RESTORE_CONFIRMATION = Form(...)


class BackupRequest(BaseModel):
    password: SecretStr


def cleanup_backup_transfers(db_path: Path) -> int:
    """Remove only app-named encrypted transfers after a process interruption."""
    staging = db_path.resolve().parent / "backup-transfers"
    if (
        not staging.is_dir()
        or staging.is_symlink()
        or getattr(staging, "is_junction", lambda: False)()
    ):
        return 0
    remaining = 0
    for path in staging.iterdir():
        if not re.fullmatch(r"[a-f0-9]{32}\.reweave", path.name) or path.is_symlink():
            continue
        if path.is_file():
            try:
                path.unlink()
            except OSError:
                remaining += 1
    return remaining


def backup_router(service: EncryptedBackupService, gate: MaintenanceGate, *, on_restored):
    router = APIRouter(prefix="/api/archive")
    staging = service.db_path.parent / "backup-transfers"

    def remove_transfer(path):
        try:
            path.unlink(missing_ok=True)
            return True
        except OSError:
            return False

    def save_upload(upload: UploadFile) -> Path:
        if not upload.filename or Path(upload.filename).suffix.lower() != ".reweave":
            raise HTTPException(400, "Choose an encrypted .reweave backup.")
        staging.mkdir(parents=True, exist_ok=True)
        path = staging / f"{uuid4().hex}.reweave"
        total = 0
        try:
            with path.open("xb") as target:
                while chunk := upload.file.read(1024 * 1024):
                    total += len(chunk)
                    if total > service.limits.max_artifact_bytes:
                        raise HTTPException(413, "Backup upload exceeds the supported size.")
                    target.write(chunk)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return path

    @router.post("/encrypted-backup")
    def download(request: BackupRequest):
        staging.mkdir(parents=True, exist_ok=True)
        path = staging / f"{uuid4().hex}.reweave"
        try:
            with gate.exclusive():
                service.backup_to(path, request.password.get_secret_value())
        except MaintenanceBusyError as exc:
            raise HTTPException(409, str(exc)) from exc
        except (BackupError, OSError) as exc:
            path.unlink(missing_ok=True)
            raise HTTPException(
                400,
                "Could not create the encrypted backup. "
                "Check the password and available disk space.",
            ) from exc
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        return FileResponse(
            path,
            media_type="application/octet-stream",
            filename=f"reweave-{stamp}.reweave",
            background=BackgroundTask(remove_transfer, path),
            headers={"Cache-Control": "no-store"},
        )

    @router.post("/encrypted-restore/preview")
    def preview(file: UploadFile = BACKUP_UPLOAD, password: str = BACKUP_PASSWORD):
        path = save_upload(file)
        try:
            with gate.exclusive():
                result = service.preview_from(path, password)
            return {"preview": asdict(result)}
        except MaintenanceBusyError as exc:
            raise HTTPException(409, str(exc)) from exc
        except BackupError as exc:
            raise HTTPException(400, str(exc)) from exc
        except OSError as exc:
            raise HTTPException(
                400, "Could not read the backup. Check available disk space."
            ) from exc
        finally:
            remove_transfer(path)

    @router.post("/encrypted-restore")
    def restore(
        file: UploadFile = BACKUP_UPLOAD,
        password: str = BACKUP_PASSWORD,
        confirmation: str = RESTORE_CONFIRMATION,
    ):
        if confirmation != "RESTORE":
            raise HTTPException(400, "Preview the backup and confirm with RESTORE.")
        path = save_upload(file)
        result = None
        try:
            with gate.exclusive():
                result = service.restore_from(path, password, jobs_idle=True)
                try:
                    on_restored()
                except Exception:
                    result = replace(
                        result,
                        recovery_pending=True,
                        notice="The library was restored. Restart Reweave before continuing. "
                        "Reconnect your provider after restart.",
                    )
                if not remove_transfer(path):
                    result = replace(
                        result,
                        recovery_pending=True,
                        notice="The library was restored. "
                        "Restart Reweave to clean up the encrypted transfer. "
                        "Reconnect your provider after restart.",
                    )
                if result.recovery_pending:
                    gate.block_until_restart(
                        "The library was restored. Restart Reweave to finish recovery."
                    )
            return asdict(result)
        except MaintenanceBusyError as exc:
            raise HTTPException(409, str(exc)) from exc
        except BackupError as exc:
            raise HTTPException(400, str(exc)) from exc
        except OSError as exc:
            raise HTTPException(
                400, "Could not restore the backup. Check available disk space."
            ) from exc
        finally:
            remove_transfer(path)

    return router
