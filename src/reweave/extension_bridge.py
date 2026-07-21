"""Short-lived connection metadata for the browser extension bridge."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4

BRIDGE_PROTOCOL_VERSION = 1


@dataclass(frozen=True)
class ExtensionRuntimeDescriptor:
    """Private metadata needed by the native host to reach the running app."""

    protocol_version: int
    port: int
    token: str
    pid: int

    @classmethod
    def from_dict(cls, value: object) -> ExtensionRuntimeDescriptor:
        if not isinstance(value, dict):
            raise ValueError("The extension runtime descriptor must be a JSON object.")

        protocol_version = value.get("protocol_version")
        port = value.get("port")
        token = value.get("token")
        pid = value.get("pid")
        if not isinstance(protocol_version, int) or protocol_version < 1:
            raise ValueError("The extension runtime protocol version is invalid.")
        if not isinstance(port, int) or not 1 <= port <= 65_535:
            raise ValueError("The extension runtime port is invalid.")
        if not isinstance(token, str) or len(token) < 32:
            raise ValueError("The extension runtime token is invalid.")
        if not isinstance(pid, int) or pid < 1:
            raise ValueError("The extension runtime process ID is invalid.")
        return cls(
            protocol_version=protocol_version,
            port=port,
            token=token,
            pid=pid,
        )


def write_runtime_descriptor(
    path: Path,
    *,
    port: int,
    token: str,
    pid: int | None = None,
) -> ExtensionRuntimeDescriptor:
    """Atomically publish the running app's private extension connection metadata."""
    descriptor = ExtensionRuntimeDescriptor.from_dict(
        {
            "protocol_version": BRIDGE_PROTOCOL_VERSION,
            "port": port,
            "token": token,
            "pid": pid or os.getpid(),
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary_path.write_text(
            json.dumps(asdict(descriptor), sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return descriptor


def read_runtime_descriptor(path: Path) -> ExtensionRuntimeDescriptor:
    """Read and validate the running app's extension connection metadata."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("The extension runtime descriptor is unavailable or malformed.") from exc
    return ExtensionRuntimeDescriptor.from_dict(raw)


def remove_runtime_descriptor(path: Path, *, expected_token: str) -> bool:
    """Remove only the descriptor owned by the current app process."""
    try:
        descriptor = read_runtime_descriptor(path)
    except ValueError:
        return False
    if descriptor.token != expected_token:
        return False
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    return True
