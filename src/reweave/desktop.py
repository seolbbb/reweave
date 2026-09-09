"""Shared native-window and isolated background launchers for the local app."""

from __future__ import annotations

import argparse
import math
import os
import secrets
import signal
import socket
import threading
import time
import urllib.request
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import uvicorn
from platformdirs import user_data_dir

from reweave.extension_bridge import remove_runtime_descriptor, write_runtime_descriptor
from reweave.library_lock import library_lock
from reweave.paths import APP_NAME, get_app_paths


@dataclass(frozen=True)
class LocalRuntime:
    url: str
    descriptor_path: Path


@contextmanager
def running_app(db_path: Path, *, data_dir: Path) -> Iterator[LocalRuntime]:
    """Reserve this Library before restore recovery, runtime publication or worker startup."""
    with library_lock(db_path):
        yield from _running_app_owned(db_path, data_dir=data_dir)


def _running_app_owned(db_path: Path, *, data_dir: Path) -> Iterator[LocalRuntime]:
    """Run the actual app lifespan on an exclusively reserved loopback port."""
    from reweave.web import create_app

    app_paths = get_app_paths(data_dir)
    static_dir = Path(__file__).parent / "web" / "dist"
    bridge_token = secrets.token_urlsafe(32)
    host = "127.0.0.1"
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind((host, 0))
        port = int(listener.getsockname()[1])
        listener.listen(128)
        url = f"http://{host}:{port}"
        server = uvicorn.Server(
            uvicorn.Config(
                create_app(
                    db_path,
                    static_dir=static_dir if static_dir.exists() else None,
                    data_dir=app_paths.data_dir,
                    extension_bridge_token=bridge_token,
                ),
                host=host,
                port=port,
                log_level="warning",
                # Windowed PyInstaller executables have no stderr stream.
                log_config=None,
                timeout_graceful_shutdown=5,
            )
        )
        thread = threading.Thread(
            target=server.run,
            kwargs={"sockets": [listener]},
            name="reweave-server",
            daemon=True,
        )
        thread.start()
        try:
            _wait_for_server(f"{url}/api/health", server_thread=thread)
            write_runtime_descriptor(
                app_paths.extension_runtime_path, port=port, token=bridge_token
            )
            yield LocalRuntime(url=url, descriptor_path=app_paths.extension_runtime_path)
        finally:
            remove_runtime_descriptor(app_paths.extension_runtime_path, expected_token=bridge_token)
            server.should_exit = True
            # Lifespan stops future transmissions and drains running workers before
            # this owner can release its OS Library lock. Never outlive a DB writer.
            thread.join()


def main(db_path: Path | None = None) -> None:
    """Start Reweave in a native desktop window."""
    try:
        import webview
    except ImportError as exc:
        raise RuntimeError("pywebview is required to run the Reweave desktop app.") from exc

    app_paths = get_app_paths()
    resolved_db_path = db_path or Path(os.getenv("REWEAVE_DB", app_paths.db_path))
    with running_app(resolved_db_path, data_dir=app_paths.data_dir) as runtime:
        # WebView2 opens a Save File dialog only for explicit attachment/download actions.
        webview.settings["ALLOW_DOWNLOADS"] = True
        webview.create_window("Reweave", runtime.url, width=1280, height=820, min_size=(960, 640))
        webview.start()


def run_headless(*, data_dir: Path, run_for: float = 300, stop_file: Path | None = None) -> None:
    """Run a bounded isolated instance without UI, OS credentials, or registration.

    The stop file belongs inside the explicitly selected data directory. A caller
    can create it to request normal lifespan shutdown, or let the deadline expire.
    Memory-only credentials survive store instances, but never process restart.
    """
    isolated_dir = data_dir.expanduser().resolve()
    default_dir = Path(user_data_dir(APP_NAME, appauthor=False)).resolve()
    if isolated_dir == default_dir:
        raise ValueError("Headless verification requires a separate data directory.")
    if not math.isfinite(run_for) or not 0 < run_for <= 86_400:
        raise ValueError(
            "Headless run duration must be greater than zero and at most 86400 seconds."
        )
    if stop_file is not None:
        stop_file = stop_file.expanduser().resolve()
        if not stop_file.is_relative_to(isolated_dir) or stop_file == isolated_dir:
            raise ValueError("The headless stop file must be inside its isolated data directory.")

    stop_event = threading.Event()
    previous_handlers = {}
    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[sig] = signal.signal(sig, lambda *_: stop_event.set())
    environment = {
        "REWEAVE_DATA_DIR": str(isolated_dir),
        "REWEAVE_DB": str(isolated_dir / "reweave.db"),
        "REWEAVE_CREDENTIAL_BACKEND": "memory",
        "PYTHON_DOTENV_DISABLED": "1",
    }
    previous_environment = {key: os.environ.get(key) for key in environment}
    os.environ.update(environment)
    try:
        with running_app(isolated_dir / "reweave.db", data_dir=isolated_dir):
            deadline = time.monotonic() + run_for
            while not stop_event.is_set():
                if stop_file is not None and stop_file.exists():
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                stop_event.wait(min(0.1, remaining))
    finally:
        for key, value in previous_environment.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)


def cli_main(argv: Sequence[str] | None = None) -> None:
    """Parse packaged launch options before importing any native UI module."""
    parser = argparse.ArgumentParser(description="Reweave local Context Library")
    parser.add_argument(
        "--headless", action="store_true", help="Run isolated background verification"
    )
    parser.add_argument(
        "--data-dir", type=Path, help="Separate headless library directory (required)"
    )
    parser.add_argument("--run-for", type=float, default=300, help="Headless lifetime in seconds")
    parser.add_argument("--stop-file", type=Path, help="Create this isolated file to stop normally")
    arguments = parser.parse_args(argv)
    if arguments.headless:
        if arguments.data_dir is None:
            parser.error("--headless requires an explicit --data-dir")
        run_headless(
            data_dir=arguments.data_dir, run_for=arguments.run_for, stop_file=arguments.stop_file
        )
    elif (
        arguments.data_dir is not None
        or arguments.stop_file is not None
        or arguments.run_for != 300
    ):
        parser.error("--data-dir, --run-for, and --stop-file require --headless")
    else:
        main()


def _wait_for_server(
    url: str, timeout: float = 10.0, *, server_thread: threading.Thread | None = None
) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    # Health checks always remain loopback even when the shell has proxy settings.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    while time.monotonic() < deadline:
        if server_thread is not None and not server_thread.is_alive():
            break
        try:
            with opener.open(url, timeout=0.5) as response:
                if response.status == 200:
                    return
        except Exception as exc:  # pragma: no cover - depends on startup timing
            last_error = exc
        time.sleep(0.1)
    raise RuntimeError("Reweave server did not start in time.") from last_error


if __name__ == "__main__":
    cli_main()
