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

MAX_MESSAGE_BYTES = 1024 * 1024
HOST_NAME = "com.reweave.bridge"


def read_native_message(stream: BinaryIO) -> dict[str, Any]:
    """Read one length-prefixed native messaging JSON object."""
    header = _read_exact(stream, 4)
    if len(header) != 4:
        raise ValueError("A complete native messaging header was not received.")
    message_length = struct.unpack("=I", header)[0]
    if message_length < 2 or message_length > MAX_MESSAGE_BYTES:
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
    if len(payload) > MAX_MESSAGE_BYTES:
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
            payload = json.loads(response.read().decode("utf-8"))
    except (
        OSError,
        TimeoutError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        urllib.error.HTTPError,
        urllib.error.URLError,
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
    """Handle the availability-only protocol supported by this scaffold."""
    if message.get("type") != "ping":
        return _status("error", "unsupported_message")
    if message.get("protocol_version") != BRIDGE_PROTOCOL_VERSION:
        return _status("incompatible", "protocol_mismatch")
    return check_app_availability(runtime_path, urlopen=urlopen)


def _status(status: str, reason: str) -> dict[str, Any]:
    return {
        "type": "status",
        "status": status,
        "reason": reason,
        "protocol_version": BRIDGE_PROTOCOL_VERSION,
    }


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
