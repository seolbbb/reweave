"""Secure extension availability bridge tests."""

from __future__ import annotations

import io
import json
import struct
import urllib.error

import pytest
from fastapi.testclient import TestClient

import reweave.native_host as native_host
from reweave.extension_bridge import (
    BRIDGE_PROTOCOL_VERSION,
    read_runtime_descriptor,
    remove_runtime_descriptor,
    write_runtime_descriptor,
)
from reweave.native_host import (
    MAX_REQUEST_BYTES,
    check_app_availability,
    forward_conversation_capture,
    handle_native_message,
    read_native_message,
    write_native_message,
)
from reweave.paths import get_app_paths
from reweave.web import create_app


class _FakeResponse:
    def __init__(self, payload: object):
        self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size: int = -1) -> bytes:
        return self._payload if size < 0 else self._payload[:size]


class _PartialReadStream(io.BytesIO):
    def read(self, size: int = -1) -> bytes:
        return super().read(min(size, 2) if size >= 0 else 2)


def test_app_paths_honor_explicit_then_environment_data_dir(tmp_path, monkeypatch):
    configured = tmp_path / "configured"
    explicit = tmp_path / "explicit"
    monkeypatch.setenv("REWEAVE_DATA_DIR", str(configured))

    assert get_app_paths().data_dir == configured
    assert get_app_paths().extension_runtime_path == configured / "extension-bridge.json"
    assert get_app_paths(explicit).data_dir == explicit


def test_runtime_descriptor_round_trip_and_owner_safe_cleanup(tmp_path):
    path = tmp_path / "extension-bridge.json"
    descriptor = write_runtime_descriptor(path, port=43123, token="a" * 43, pid=8123)

    assert descriptor == read_runtime_descriptor(path)
    assert descriptor.protocol_version == BRIDGE_PROTOCOL_VERSION
    assert remove_runtime_descriptor(path, expected_token="b" * 43) is False
    assert path.exists()
    assert remove_runtime_descriptor(path, expected_token="a" * 43) is True
    assert not path.exists()


@pytest.mark.parametrize(
    "value",
    [
        "not-json",
        "[]",
        '{"protocol_version":1,"port":0,"token":"short","pid":1}',
    ],
)
def test_runtime_descriptor_rejects_malformed_or_unsafe_values(tmp_path, value):
    path = tmp_path / "extension-bridge.json"
    path.write_text(value, encoding="utf-8")

    with pytest.raises(ValueError):
        read_runtime_descriptor(path)


def test_handshake_requires_the_ephemeral_bridge_token(tmp_path):
    token = "bridge-token-for-tests-with-enough-entropy"
    client = TestClient(
        create_app(
            tmp_path / "archive.db",
            data_dir=tmp_path / "app-data",
            extension_bridge_token=token,
        )
    )

    assert client.post("/api/extension/handshake").status_code == 403
    assert (
        client.post(
            "/api/extension/handshake",
            headers={"X-Reweave-Bridge-Token": "wrong-token"},
        ).status_code
        == 403
    )
    response = client.post(
        "/api/extension/handshake",
        headers={"X-Reweave-Bridge-Token": token},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "protocol_version": 1}
    assert token not in response.text

    inactive = TestClient(create_app(tmp_path / "inactive.db", data_dir=tmp_path / "inactive"))
    assert inactive.post("/api/extension/handshake").status_code == 503


def test_native_message_framing_round_trips_one_json_object():
    stream = io.BytesIO()
    message = {"type": "ping", "protocol_version": 1}

    write_native_message(stream, message)
    stream.seek(0)

    assert read_native_message(stream) == message

    stream.seek(0)
    assert read_native_message(_PartialReadStream(stream.read())) == message


def test_native_message_framing_rejects_oversized_or_truncated_requests():
    with pytest.raises(ValueError, match="size"):
        read_native_message(io.BytesIO(struct.pack("=I", MAX_REQUEST_BYTES + 1)))
    with pytest.raises(ValueError, match="ended"):
        read_native_message(io.BytesIO(struct.pack("=I", 12) + b"{}"))


def test_native_host_reports_ready_without_leaking_connection_metadata(tmp_path):
    runtime_path = tmp_path / "extension-bridge.json"
    token = "private-runtime-token-with-enough-entropy"
    write_runtime_descriptor(runtime_path, port=45678, token=token, pid=991)

    def fake_urlopen(request, timeout):
        assert request.full_url == "http://127.0.0.1:45678/api/extension/handshake"
        assert request.get_header("X-reweave-bridge-token") == token
        assert timeout == 1.5
        return _FakeResponse({"status": "ready", "protocol_version": 1})

    result = handle_native_message(
        {"type": "ping", "protocol_version": 1},
        runtime_path=runtime_path,
        urlopen=fake_urlopen,
    )

    assert result == {
        "type": "status",
        "status": "ready",
        "reason": "connected",
        "protocol_version": 1,
    }
    assert token not in json.dumps(result)
    assert "45678" not in json.dumps(result)


def test_native_host_reports_actionable_unavailable_and_incompatible_states(tmp_path):
    runtime_path = tmp_path / "extension-bridge.json"
    assert check_app_availability(runtime_path)["reason"] == "app_not_running"

    runtime_path.write_text("not-json", encoding="utf-8")
    assert check_app_availability(runtime_path)["reason"] == "app_not_running"

    write_runtime_descriptor(runtime_path, port=45678, token="a" * 43, pid=991)

    def connection_failure(*_args, **_kwargs):
        raise urllib.error.URLError("not running")

    assert (
        check_app_availability(runtime_path, urlopen=connection_failure)["reason"]
        == "connection_failed"
    )

    def incompatible_response(*_args, **_kwargs):
        return _FakeResponse({"status": "ready", "protocol_version": 99})

    assert (
        check_app_availability(runtime_path, urlopen=incompatible_response)["status"]
        == "incompatible"
    )
    assert (
        handle_native_message({"type": "capture", "protocol_version": 1})["reason"]
        == "unsupported_message"
    )
    assert (
        handle_native_message({"type": "ping", "protocol_version": 99})["status"]
        == "incompatible"
    )


def _capture_payload() -> dict:
    return {
        "provider": "chatgpt",
        "external_id": "conversation-42",
        "title": "Captured from ChatGPT",
        "created_at": None,
        "updated_at": None,
        "messages": [
            {
                "external_id": "conversation-42:turn:0",
                "role": "user",
                "content": "Keep this exact question.",
                "timestamp": None,
            }
        ],
    }


def test_native_host_forwards_capture_with_token_and_returns_only_summary(tmp_path):
    runtime_path = tmp_path / "extension-bridge.json"
    token = "private-runtime-token-with-enough-entropy"
    write_runtime_descriptor(runtime_path, port=45678, token=token, pid=991)

    def fake_urlopen(request, timeout):
        assert request.full_url == "http://127.0.0.1:45678/api/capture/conversations"
        assert request.get_method() == "POST"
        assert request.get_header("Content-type") == "application/json"
        assert request.get_header("X-reweave-bridge-token") == token
        assert json.loads(request.data.decode("utf-8")) == _capture_payload()
        assert timeout == 10.0
        return _FakeResponse({"outcome": "created", "message_count": 1})

    result = handle_native_message(
        {
            "type": "capture_conversation",
            "protocol_version": 1,
            "capture": _capture_payload(),
        },
        runtime_path=runtime_path,
        urlopen=fake_urlopen,
    )

    assert result == {
        "type": "capture_result",
        "status": "saved",
        "reason": "stored",
        "protocol_version": 1,
        "outcome": "created",
        "message_count": 1,
    }
    serialized = json.dumps(result)
    assert token not in serialized
    assert "Keep this exact question" not in serialized
    assert "45678" not in serialized


def test_native_host_reports_invalid_unavailable_and_oversized_capture_states(
    tmp_path, monkeypatch
):
    runtime_path = tmp_path / "extension-bridge.json"
    assert (
        forward_conversation_capture(_capture_payload(), runtime_path=runtime_path)["reason"]
        == "app_not_running"
    )

    write_runtime_descriptor(runtime_path, port=45678, token="a" * 43, pid=991)

    def invalid_response(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url,
            422,
            "Unprocessable Entity",
            {},
            io.BytesIO(b"{}"),
        )

    assert (
        forward_conversation_capture(
            _capture_payload(), runtime_path=runtime_path, urlopen=invalid_response
        )["reason"]
        == "invalid_capture"
    )

    monkeypatch.setattr(native_host, "MAX_CAPTURE_FORWARD_BYTES", 10)

    def should_not_connect(*_args, **_kwargs):
        raise AssertionError("Oversized captures must not reach the app.")

    assert (
        forward_conversation_capture(
            _capture_payload(), runtime_path=runtime_path, urlopen=should_not_connect
        )["reason"]
        == "capture_too_large"
    )


def test_unavailable_native_host_probe_does_not_create_app_directories(tmp_path, monkeypatch):
    missing_data_dir = tmp_path / "missing-app-data"
    monkeypatch.setenv("REWEAVE_DATA_DIR", str(missing_data_dir))

    assert check_app_availability()["reason"] == "app_not_running"
    assert not missing_data_dir.exists()
