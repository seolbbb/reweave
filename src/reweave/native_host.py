"""Chrome and Edge native messaging host for the Reweave extension."""

from __future__ import annotations

import json
import os
import re
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
MAX_CONTEXT_FORWARD_BYTES = 512 * 1024
MAX_HTTP_RESPONSE_BYTES = 64 * 1024
HOST_NAME = "com.reweave.bridge"
CONTEXT_ITEM_PATTERN = re.compile(r"^\[Reweave:([A-Za-z0-9_-]+)\]\s", re.MULTILINE)


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
    if message.get("type") == "assemble_context":
        return forward_context_assembly(
            message.get("context_request"),
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
    if outcome not in {"created", "updated", "unchanged"} or not isinstance(message_count, int):
        return _capture_result("incompatible", "malformed_response")
    return _capture_result(
        "saved",
        "stored",
        outcome=outcome,
        message_count=message_count,
    )


def forward_context_assembly(
    context_request: object,
    *,
    runtime_path: Path | None = None,
    urlopen: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    """Forward a bounded explicit Use or local review action without retaining chat text."""
    if not isinstance(context_request, dict):
        return _context_result("error", "invalid_context")
    body = json.dumps(context_request, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(body) > MAX_CONTEXT_FORWARD_BYTES:
        return _context_result("error", "context_request_too_large")

    path = runtime_path or get_app_paths(ensure=False).extension_runtime_path
    try:
        descriptor = read_runtime_descriptor(path)
    except ValueError:
        return _context_result("unavailable", "app_not_running")
    if descriptor.protocol_version != BRIDGE_PROTOCOL_VERSION:
        return _context_result("incompatible", "protocol_mismatch")

    request = urllib.request.Request(
        f"http://127.0.0.1:{descriptor.port}/api/context/assembly",
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
        if exc.code == 409:
            return _context_result("error", "destination_changed")
        if exc.code in {400, 422}:
            return _context_result("error", "invalid_context")
        if exc.code in {403, 503}:
            return _context_result("unavailable", "connection_rejected")
        return _context_result("unavailable", "connection_failed")
    except (OSError, TimeoutError, urllib.error.URLError):
        return _context_result("unavailable", "connection_failed")
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return _context_result("incompatible", "malformed_response")

    if not isinstance(payload, dict):
        return _context_result("incompatible", "malformed_response")
    if payload.get("status") in {
        "destination_confirmation_required",
        "destination_saved",
        "sensitive_preview",
        "sensitive_confirmed",
        "error",
    }:
        return _trust_response(payload)
    insertion_text = payload.get("insertion_text")
    context_chars = payload.get("context_chars")
    items = payload.get("items")
    if (
        not isinstance(insertion_text, str)
        or not insertion_text.startswith("<reweave_context>\n")
        or not insertion_text.endswith("</reweave_context>")
        or len(insertion_text) > 20_000
        or context_chars != len(insertion_text)
        or not isinstance(items, list)
        or not items
        or not all(
            isinstance(item, dict) and isinstance(item.get("item_id"), str) for item in items
        )
    ):
        return _context_result("incompatible", "malformed_response")
    item_ids = [item["item_id"] for item in items]
    marker_ids = CONTEXT_ITEM_PATTERN.findall(insertion_text)
    if len(item_ids) != len(set(item_ids)) or marker_ids != item_ids:
        return _context_result("incompatible", "malformed_response")
    result = _context_result(
        "ready",
        "context_ready",
        insertion_text=insertion_text,
        item_count=len(items),
        context_chars=context_chars,
    )
    for field in (
        "destination",
        "destination_revision",
        "sensitive_available",
        "used",
        "excluded_reasons",
    ):
        if field in payload:
            result[field] = payload[field]
    return result


def _trust_response(payload: dict) -> dict:
    """Pass bounded local preview data only for a recognized service response."""
    status = payload["status"]
    if status == "destination_confirmation_required":
        spaces = payload.get("spaces")
        valid = (
            type(payload.get("destination_revision")) is int
            and isinstance(spaces, list)
            and len(spaces) <= 200
            and all(
                isinstance(s, dict)
                and all(isinstance(s.get(k), str) for k in ("space_id", "scope_type", "name"))
                for s in spaces
            )
        )
        fields = (
            "destination",
            "destination_revision",
            "allowed_space_ids",
            "suggested_destination",
            "reasons",
            "spaces",
        )
    elif status == "destination_saved":
        valid = (
            payload.get("destination") in {"private", "work", "client", "shared"}
            and type(payload.get("destination_revision")) is int
        )
        fields = ("destination", "destination_revision")
    elif status == "sensitive_preview":
        items = payload.get("items")
        valid = (
            isinstance(payload.get("preview_token"), str)
            and len(payload["preview_token"]) <= 200
            and isinstance(items, list)
            and len(items) <= 5
            and all(
                isinstance(i, dict)
                and isinstance(i.get("item_id"), str)
                and type(i.get("version")) is int
                and isinstance(i.get("text"), str)
                and isinstance(i.get("sources"), list)
                for i in items
            )
        )
        fields = ("destination", "preview_token", "expires_in_seconds", "items")
    elif status == "sensitive_confirmed":
        valid = (
            isinstance(payload.get("confirmation_token"), str)
            and len(payload["confirmation_token"]) <= 200
        )
        fields = ("confirmation_token", "expires_in_seconds")
    else:
        valid = payload.get("reason") in {"context_unavailable", "confirmation_expired"}
        fields = ("destination", "destination_revision", "sensitive_available", "excluded_reasons")
    if not valid:
        return _context_result("incompatible", "malformed_response")
    response = _context_result(status, payload.get("reason", status))
    response.update({key: payload[key] for key in fields if key in payload})
    return response


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


def _context_result(
    status: str,
    reason: str,
    *,
    insertion_text: str | None = None,
    item_count: int | None = None,
    context_chars: int | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "type": "context_result",
        "status": status,
        "reason": reason,
        "protocol_version": BRIDGE_PROTOCOL_VERSION,
    }
    if insertion_text is not None:
        result["insertion_text"] = insertion_text
    if item_count is not None:
        result["item_count"] = item_count
    if context_chars is not None:
        result["context_chars"] = context_chars
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
