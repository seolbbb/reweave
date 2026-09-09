"""Process lifetime ownership of one SQLite Library before startup recovery."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def library_lock(db_path: Path):
    """Hold an OS lock; a process exit releases it without deleting another owner's file."""
    database = db_path.expanduser().resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    path = database.with_name(database.name + ".owner-lock")
    if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
        raise RuntimeError("The Library ownership file must be a regular local file.")
    with path.open("a+b") as handle:
        if handle.seek(0, 2) == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError(
                "This Reweave Library is already open. Close its existing app before reopening it."
            ) from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
