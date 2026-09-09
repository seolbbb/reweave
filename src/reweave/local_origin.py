"""Reject DNS rebinding and cross-origin browser access to the local application."""

from __future__ import annotations

import re

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

_AUTHORITY = re.compile(r"(127\.0\.0\.1|localhost|\[::1\])(?::([0-9]{1,5}))?", re.IGNORECASE)
_ORIGIN = re.compile(r"(https?)://([^/\\?#]+)", re.IGNORECASE)
_DENIED = "Open Reweave from its local desktop window or local application address."


class LocalOriginMiddleware:
    """Guard every HTTP route before routing, parsing uploads, or accessing local data.

    Native Messaging and local tools omit browser Origin/Fetch-Metadata headers and
    still reach their own route authentication. This is a browser boundary, not local
    process authentication. Forwarded host/proto headers never establish trust here.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if not _allowed(scope):
            await JSONResponse(
                {"detail": _DENIED}, status_code=403, headers={"Cache-Control": "no-store"}
            )(scope, receive, send)
            return

        async def send_protected(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                names = {name.lower() for name, _ in headers}
                if b"x-content-type-options" not in names:
                    headers.append((b"x-content-type-options", b"nosniff"))
                if b"x-frame-options" not in names:
                    headers.append((b"x-frame-options", b"DENY"))
                if b"content-security-policy" not in names:
                    headers.append((b"content-security-policy", b"frame-ancestors 'none'"))
                if scope["path"].startswith("/api/"):
                    headers = [
                        (name, value) for name, value in headers if name.lower() != b"cache-control"
                    ]
                    headers.append((b"cache-control", b"no-store"))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_protected)


def _one_header(scope, wanted):
    values = [value for name, value in scope["headers"] if name.lower() == wanted]
    if len(values) > 1:
        raise ValueError("Duplicate trust header")
    return values[0].decode("ascii") if values else None


def _authority(value, scheme):
    if value is None or len(value) > 255:
        return None
    match = _AUTHORITY.fullmatch(value)
    if match is None:
        return None
    host, port = match.groups()
    port = int(port) if port is not None else (443 if scheme == "https" else 80)
    return (host.lower(), port) if 1 <= port <= 65535 else None


def _allowed(scope):
    try:
        scheme = scope.get("scheme", "http").lower()
        if scheme not in {"http", "https"}:
            return False
        host = _authority(_one_header(scope, b"host"), scheme)
        if host is None:
            return False
        origin = _one_header(scope, b"origin")
        if origin is not None:
            match = _ORIGIN.fullmatch(origin)
            if match is None:
                return False
            origin_scheme, origin_host = match.groups()
            if origin_scheme.lower() != scheme or _authority(origin_host, scheme) != host:
                return False
        fetch_site = _one_header(scope, b"sec-fetch-site")
        if fetch_site is not None:
            fetch_site = fetch_site.lower()
            if fetch_site not in {"none", "same-origin", "same-site"}:
                return False
            if fetch_site == "same-site" and origin is None:
                # Same-site does not prove the same loopback port. Require an exact Origin.
                return False
        return True
    except (ValueError, UnicodeError):
        return False
