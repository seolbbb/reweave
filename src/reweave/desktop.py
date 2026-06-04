"""Desktop launcher for the Reweave local app."""

from __future__ import annotations

import os
import socket
import threading
import time
import urllib.request
from pathlib import Path

import uvicorn

from reweave.paths import get_app_paths
from reweave.web import create_app


def main(db_path: Path | None = None) -> None:
    """Start Reweave in a native desktop window."""
    try:
        import webview
    except ImportError as exc:
        raise RuntimeError("pywebview is required to run the Reweave desktop app.") from exc

    app_paths = get_app_paths()
    resolved_db_path = db_path or Path(os.getenv("REWEAVE_DB", app_paths.db_path))
    static_dir = Path(__file__).parent / "web" / "dist"
    if not static_dir.exists():
        static_dir = None

    host = "127.0.0.1"
    port = _available_port(host)
    url = f"http://{host}:{port}"
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(resolved_db_path, static_dir=static_dir, data_dir=app_paths.data_dir),
            host=host,
            port=port,
            log_level="warning",
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    _wait_for_server(f"{url}/api/health")

    try:
        webview.create_window("Reweave", url, width=1280, height=820, min_size=(960, 640))
        webview.start()
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def _available_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def _wait_for_server(url: str, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.5) as response:
                if response.status == 200:
                    return
        except Exception as exc:  # pragma: no cover - depends on startup timing
            last_error = exc
        time.sleep(0.1)
    raise RuntimeError("Reweave server did not start in time.") from last_error
