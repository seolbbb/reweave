"""Chrome and Edge native messaging host for the Reweave extension."""

from __future__ import annotations

import json
import os
import struct
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any, BinaryIO

from reweave.extension_bridge import BRIDGE_PROTOCOL_VERSION, read_runtime_descriptor
from reweave.paths import get_app_paths

MAX_REQUEST_BYTES = 64 * 1024 * 1024
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_CAPTURE_FORWARD_BYTES = 32 * 1024 * 1024
MAX_HTTP_RESPONSE_BYTES = 64 * 1024
HOST_NAME = "com.reweave.bridge"


def read_native_message(stream: BinaryIO) -> dict[str, Any]:
    """Read one length-prefixed native messaging JSON object."""
    header = _read_exact(stream, 4)
    if len(header) != 4:
        raise ValueError("A complete native messaging header was not received.")
    message_length = struct.unpack("=I", header)[0]
    if message_length < 2 or message_length > MAX_REQUEST_BYTES:
        raise ValueError("The native messaging request size is invalid.")
    payload = _read_exact(stream, message_length)
    if len(payload) != message_length:
        raise ValueError("The native messaging request ended before the declared size.")
    try:
        message = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("The native messaging request is not valid UTF-8 JSON.") from exc
    if not isinstance(message, dict):
        raise ValueError("The native messaging request must be a JSON object.")
    return message


def _read_exact(stream: BinaryIO, length: int) -> bytes:
    chunks: list[bytes] = []
    remaining = length
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def write_native_message(stream: BinaryIO, message: dict[str, Any]) -> None:
    """Write one length-prefixed native messaging JSON object."""
    payload = json.dumps(message, separators=(",", ":")).encode("utf-8")
    if len(payload) > MAX_RESPONSE_BYTES:
        raise ValueError("The native messaging response is too large.")
    stream.write(struct.pack("=I", len(payload)))
    stream.write(payload)
    stream.flush()


def check_app_availability(
    runtime_path: Path | None = None,
    *,
    urlopen: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    """Probe the authenticated loopback handshake without exposing connection metadata."""
    path = runtime_path or get_app_paths(ensure=False).extension_runtime_path
    try:
        descriptor = read_runtime_descriptor(path)
    except ValueError:
        return _status("unavailable", "app_not_running")
    if descriptor.protocol_version != BRIDGE_PROTOCOL_VERSION:
        return _status("incompatible", "protocol_mismatch")

    request = urllib.request.Request(
        f"http://127.0.0.1:{descriptor.port}/api/extension/handshake",
        method="POST",
        headers={"X-Reweave-Bridge-Token": descriptor.token},
    )
    try:
        with urlopen(request, timeout=1.5) as response:
            payload = _read_json_response(response)
    except (
        OSError,
        TimeoutError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        urllib.error.HTTPError,
        urllib.error.URLError,
        ValueError,
    ):
        return _status("unavailable", "connection_failed")

    if not isinstance(payload, dict) or payload.get("protocol_version") != BRIDGE_PROTOCOL_VERSION:
        return _status("incompatible", "protocol_mismatch")
    if payload.get("status") != "ready":
        return _status("unavailable", "connection_rejected")
    return _status("ready", "connected")


def handle_native_message(
    message: dict[str, Any],
    *,
    runtime_path: Path | None = None,
    urlopen: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    if message.get("protocol_version") != BRIDGE_PROTOCOL_VERSION:
        return _status("incompatible", "protocol_mismatch")
    if message.get("type") == "ping":
        return check_app_availability(runtime_path, urlopen=urlopen)
    if message.get("type") == "capture_conversation":
        return forward_conversation_capture(
            message.get("capture"),
            runtime_path=runtime_path,
            urlopen=urlopen,
        )
    return _status("error", "unsupported_message")


def forward_conversation_capture(
    capture: object,
    *,
    runtime_path: Path | None = None,
    urlopen: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    """Forward one bounded capture to the authenticated local app endpoint."""
    if not isinstance(capture, dict):
        return _capture_result("error", "invalid_capture")
    body = json.dumps(capture, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(body) > MAX_CAPTURE_FORWARD_BYTES:
        return _capture_result("error", "capture_too_large")

    path = runtime_path or get_app_paths(ensure=False).extension_runtime_path
    try:
        descriptor = read_runtime_descriptor(path)
    except ValueError:
        return _capture_result("unavailable", "app_not_running")
    if descriptor.protocol_version != BRIDGE_PROTOCOL_VERSION:
        return _capture_result("incompatible", "protocol_mismatch")

    request = urllib.request.Request(
        f"http://127.0.0.1:{descriptor.port}/api/capture/conversations",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Reweave-Bridge-Token": descriptor.token,
        },
    )
    try:
        with urlopen(request, timeout=10.0) as response:
            payload = _read_json_response(response)
    except urllib.error.HTTPError as exc:
        if exc.code in {400, 422}:
            return _capture_result("error", "invalid_capture")
        if exc.code in {403, 503}:
            return _capture_result("unavailable", "connection_rejected")
        return _capture_result("unavailable", "connection_failed")
    except (
        OSError,
        TimeoutError,
        urllib.error.URLError,
    ):
        return _capture_result("unavailable", "connection_failed")
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return _capture_result("incompatible", "malformed_response")

    if not isinstance(payload, dict):
        return _capture_result("incompatible", "malformed_response")
    outcome = payload.get("outcome")
    message_count = payload.get("message_count")
    if outcome not in {"created", "updated", "unchanged"} or not isinstance(
        message_count, int
    ):
        return _capture_result("incompatible", "malformed_response")
    return _capture_result(
        "saved",
        "stored",
        outcome=outcome,
        message_count=message_count,
    )


def _read_json_response(response: Any) -> Any:
    body = response.read(MAX_HTTP_RESPONSE_BYTES + 1)
    if len(body) > MAX_HTTP_RESPONSE_BYTES:
        raise ValueError("The local app response is too large.")
    return json.loads(body.decode("utf-8"))


def _status(status: str, reason: str) -> dict[str, Any]:
    return {
        "type": "status",
        "status": status,
        "reason": reason,
        "protocol_version": BRIDGE_PROTOCOL_VERSION,
    }


def _capture_result(
    status: str,
    reason: str,
    *,
    outcome: str | None = None,
    message_count: int | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "type": "capture_result",
        "status": status,
        "reason": reason,
        "protocol_version": BRIDGE_PROTOCOL_VERSION,
    }
    if outcome is not None:
        result["outcome"] = outcome
    if message_count is not None:
        result["message_count"] = message_count
    return result


def _set_binary_stdio() -> None:
    if os.name != "nt":
        return
    import msvcrt

    msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
    msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)


def main() -> None:
    """Read one browser request and return exactly one native messaging response."""
    _set_binary_stdio()
    try:
        message = read_native_message(sys.stdin.buffer)
        response = handle_native_message(message)
    except ValueError:
        response = _status("error", "malformed_request")
    write_native_message(sys.stdout.buffer, response)


if __name__ == "__main__":
    main()
