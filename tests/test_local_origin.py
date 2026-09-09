"""Local browser trust boundary without real browser profiles, accounts, or credentials."""

import pytest
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.testclient import TestClient

from reweave.local_origin import LocalOriginMiddleware


@pytest.fixture
def guarded_app():
    app = FastAPI()
    calls = []
    app.add_middleware(LocalOriginMiddleware)

    @app.api_route("/", methods=["GET", "HEAD"])
    def home():
        return HTMLResponse("<html><body>Local library</body></html>")

    @app.api_route("/assets/main.js", methods=["GET", "HEAD"])
    def asset():
        return PlainTextResponse("console.log('local');", media_type="text/javascript")

    @app.get("/api/context/items")
    def items():
        calls.append("read")
        return {"items": []}

    upload = File(...)
    password_field = Form(...)
    confirmation_field = Form(...)

    @app.post("/api/archive/encrypted-restore")
    def restore(
        file: UploadFile = upload,
        password: str = password_field,
        confirmation: str = confirmation_field,
    ):
        calls.append("restore")
        return {"restored": confirmation == "RESTORE", "bytes": len(file.file.read())}

    token = Header(default=None, alias="X-Reweave-Test-Token")

    @app.get("/api/extension/status")
    def native(bridge_token: str | None = token):
        if bridge_token != "synthetic-local-token":
            raise HTTPException(401, "Native authentication required")
        calls.append("native")
        return {"available": True}

    return app, calls


@pytest.mark.parametrize(
    "host",
    [
        "evil.example",
        "evil.example:8765",
        "127.0.0.1.evil.example",
        "127.1",
        "2130706433",
        "0x7f000001",
        "127.0.0.2",
        "0.0.0.0",
        "localhost.",
        "localhost.evil.example",
        "[::ffff:127.0.0.1]",
        "[::]",
        "127.0.0.1:0",
        "127.0.0.1:65536",
        "localhost:",
        "localhost:abc",
        "user@localhost",
        "localhost/",
        " localhost",
        "localhost,evil.example",
    ],
)
def test_rebinding_and_invalid_host_rejected_on_all_routes(guarded_app, host):
    app, calls = guarded_app
    with TestClient(app) as client:
        for path in ("/api/context/items", "/", "/assets/main.js"):
            response = client.get(path, headers={"Host": host})
            assert response.status_code == 403
            assert host not in response.text
    assert calls == []


@pytest.mark.parametrize(
    "base_url",
    [
        "http://127.0.0.1",
        "http://127.0.0.1:8765",
        "http://localhost:8765",
        "http://[::1]:8765",
        "https://localhost:8765",
    ],
)
def test_exact_origin_accepts_normal_desktop_and_static_head(guarded_app, base_url):
    app, calls = guarded_app
    # The installed TestClient transport cannot split IPv6 URLs; exercise the actual
    # IPv6 Host and Origin through its in-process transport using an IPv4 base URL.
    transport_url = "http://127.0.0.1:8765" if "[::1]" in base_url else base_url
    with TestClient(app, base_url=transport_url) as client:
        headers = {"Origin": base_url, "Sec-Fetch-Site": "same-origin"}
        if "[::1]" in base_url:
            headers["Host"] = "[::1]:8765"
        response = client.get("/api/context/items", headers=headers)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["content-security-policy"] == "frame-ancestors 'none'"
        for path in ("/", "/assets/main.js"):
            assert client.get(path, headers=headers).status_code == 200
            head = client.head(path, headers=headers)
            assert head.status_code == 200
            assert head.content == b""
    assert calls == ["read"]


@pytest.mark.parametrize(
    "origin",
    [
        "https://evil.example",
        "null",
        "",
        "http://127.0.0.1:8766",
        "http://localhost:8765",
        "https://127.0.0.1:8765",
        "http://127.0.0.1:8765/",
        "http://127.0.0.1:8765/path",
        "http://127.0.0.1:8765?x=y",
        "http://user@127.0.0.1:8765",
        "http://127.0.0.1:8765 https://evil.example",
    ],
)
def test_cross_origin_multipart_restore_never_reaches_handler(guarded_app, origin):
    app, calls = guarded_app
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        response = client.post(
            "/api/archive/encrypted-restore",
            headers={"Origin": origin},
            files={"file": ("hostile.reweave", b"synthetic-ciphertext")},
            data={"password": "synthetic-password", "confirmation": "RESTORE"},
        )
        assert response.status_code == 403
        assert "synthetic-password" not in response.text
    assert calls == []


def test_matching_origin_multipart_restore_is_allowed(guarded_app):
    app, calls = guarded_app
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        response = client.post(
            "/api/archive/encrypted-restore",
            headers={"Origin": "http://127.0.0.1:8765", "Sec-Fetch-Site": "same-origin"},
            files={"file": ("library.reweave", b"synthetic-ciphertext")},
            data={"password": "synthetic-password", "confirmation": "RESTORE"},
        )
        assert response.status_code == 200
        assert response.json()["restored"] is True
    assert calls == ["restore"]


@pytest.mark.parametrize(
    "metadata,origin,expected",
    [
        ("cross-site", None, 403),
        ("cross-site", "http://127.0.0.1:8765", 403),
        ("same-site", None, 403),
        ("same-site", "http://127.0.0.1:8766", 403),
        ("same-site", "http://127.0.0.1:8765", 200),
        ("same-origin", None, 200),
        ("none", None, 200),
        ("garbage", None, 403),
    ],
)
def test_fetch_metadata_requires_provable_origin(guarded_app, metadata, origin, expected):
    app, _ = guarded_app
    headers = {"Sec-Fetch-Site": metadata}
    if origin is not None:
        headers["Origin"] = origin
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        assert client.get("/api/context/items", headers=headers).status_code == expected


def test_no_origin_native_client_still_requires_its_token(guarded_app):
    app, calls = guarded_app
    with TestClient(app) as client:
        assert client.get("/api/extension/status").status_code == 401
        assert (
            client.get(
                "/api/extension/status", headers={"X-Reweave-Test-Token": "synthetic-local-token"}
            ).status_code
            == 200
        )
    assert calls == ["native"]


def test_forwarded_headers_do_not_establish_trust(guarded_app):
    app, calls = guarded_app
    with TestClient(app) as client:
        response = client.get(
            "/api/context/items",
            headers={
                "Host": "rebound.evil.example",
                "X-Forwarded-Host": "127.0.0.1",
                "X-Forwarded-Proto": "http",
                "Forwarded": "host=127.0.0.1;proto=http",
            },
        )
        assert response.status_code == 403
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "headers",
    [
        [],
        [(b"host", b"127.0.0.1"), (b"host", b"localhost")],
        [(b"host", b"127.0.0.1"), (b"origin", b"http://127.0.0.1"), (b"origin", b"null")],
        [(b"host", b"127.0.0.1"), (b"sec-fetch-site", b"none"), (b"sec-fetch-site", b"cross-site")],
        [(b"host", b"127.0.0.1\r\nOrigin: evil")],
        [(b"host", b"127.0.0.1"), (b"origin", b"\xff")],
    ],
)
async def test_invalid_trust_headers_rejected_before_reading_upload(headers):
    async def unreachable(*args):
        raise AssertionError("Rejected requests must not reach the app or read their bodies")

    messages = []

    async def send(message):
        messages.append(message)

    middleware = LocalOriginMiddleware(unreachable)
    await middleware(
        {
            "type": "http",
            "scheme": "http",
            "path": "/api/archive/encrypted-restore",
            "method": "POST",
            "headers": headers,
        },
        unreachable,
        send,
    )
    assert messages[0]["status"] == 403


def test_shared_client_default_is_loopback_and_explicit_host_is_preserved(guarded_app):
    app, _ = guarded_app
    with TestClient(app) as client:
        assert str(client.base_url) == "http://127.0.0.1"
    with TestClient(app, base_url="http://hostile.example") as client:
        assert client.get("/").status_code == 403
