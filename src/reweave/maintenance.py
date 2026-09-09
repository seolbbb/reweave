"""Coordinate local requests and background work with exclusive library replacement."""

from __future__ import annotations

from contextlib import contextmanager
from threading import Lock

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse


class MaintenanceBusyError(RuntimeError):
    """An active operation prevents exclusive maintenance."""


class MaintenanceGate:
    def __init__(self):
        self._lock = Lock()
        self._active = 0
        self._exclusive = False
        self._blocked = ""

    def block_until_restart(self, message):
        with self._lock:
            self._blocked = message

    def _acquire(self):
        with self._lock:
            if self._exclusive or self._blocked:
                raise MaintenanceBusyError(
                    self._blocked or "Library maintenance is in progress. Try again shortly."
                )
            self._active += 1

    def _release(self):
        with self._lock:
            self._active -= 1

    @contextmanager
    def operation(self):
        self._acquire()
        try:
            yield
        finally:
            self._release()

    @contextmanager
    def exclusive(self):
        with self._lock:
            if self._exclusive or self._active or self._blocked:
                raise MaintenanceBusyError(
                    self._blocked
                    or "The library is busy. Wait for analysis, imports, and downloads to finish."
                )
            self._exclusive = True
        try:
            yield
        finally:
            with self._lock:
                self._exclusive = False

    def submit(self, executor, function, *args, **kwargs):
        """Reserve before submission, including queued work and cancelled futures."""
        self._acquire()
        try:
            future = executor.submit(function, *args, **kwargs)
        except BaseException:
            self._release()
            raise
        future.add_done_callback(lambda _: self._release())
        return future


class MaintenanceMiddleware:
    """Keep the lease until the complete response body has been sent."""

    def __init__(self, app, *, gate, exclusive_paths, upload_limit):
        self.app = app
        self.gate = gate
        self.exclusive_paths = frozenset(exclusive_paths)
        self.upload_limit = upload_limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/"):
            return await self.app(scope, receive, send)
        if scope["path"] in self.exclusive_paths:
            size = 0

            async def bounded_receive():
                nonlocal size
                message = await receive()
                size += len(message.get("body", b""))
                if size > self.upload_limit:
                    raise HTTPException(413, "Backup upload exceeds the supported size.")
                return message

            return await self.app(scope, bounded_receive, send)
        try:
            with self.gate.operation():
                await self.app(scope, receive, send)
        except MaintenanceBusyError as exc:
            await JSONResponse({"detail": str(exc)}, status_code=503)(scope, receive, send)
