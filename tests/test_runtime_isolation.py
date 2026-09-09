"""Exercise isolation through real persistence and local HTTP, without desktop UI."""

from __future__ import annotations

import builtins
import json
import os
import runpy
import shutil
import socket
import sys
import threading
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import dotenv
import httpx
import keyring
import pytest

from reweave import desktop
from reweave.extension_bridge import read_runtime_descriptor
from reweave.llm_profiles import KeyInput, LLMProfileStore, ProfileInput
from reweave.paths import get_app_paths


def test_native_launcher_enables_explicit_save_dialog_without_starting_real_ui(monkeypatch):
    observed = []
    fake_webview = SimpleNamespace(settings={"ALLOW_DOWNLOADS": False})

    def create_window(*args, **kwargs):
        assert fake_webview.settings["ALLOW_DOWNLOADS"] is True
        observed.append(args[1])

    fake_webview.create_window = create_window
    fake_webview.start = lambda: observed.append("started")

    @contextmanager
    def fake_runtime(*args, **kwargs):
        yield desktop.LocalRuntime("http://127.0.0.1:43210", Path("synthetic-descriptor"))

    monkeypatch.setitem(sys.modules, "webview", fake_webview)
    monkeypatch.setattr(desktop, "running_app", fake_runtime)
    desktop.main()
    assert observed == ["http://127.0.0.1:43210", "started"]


def _profile_input():
    return ProfileInput(
        name="Synthetic provider",
        provider="openai-compatible",
        keys=(KeyInput(label="Synthetic key", api_key="synthetic-test-secret"),),
    )


def test_volatile_credentials_never_touch_os_store_or_plaintext_files(tmp_path, monkeypatch):
    monkeypatch.setenv("REWEAVE_CREDENTIAL_BACKEND", "memory")

    def forbidden(*args, **kwargs):
        pytest.fail("The isolated backend accessed OS keyring.")

    for method in ("get_password", "set_password", "delete_password"):
        monkeypatch.setattr(keyring, method, forbidden)
    path = tmp_path / "library" / "llm_profiles.json"
    store = LLMProfileStore(path)
    profile = store.create(_profile_input())
    assert store.credentials_for(profile.id)[0].api_key == "synthetic-test-secret"
    assert "synthetic-test-secret" not in path.read_text(encoding="utf-8")
    assert [file.name for file in path.parent.iterdir()] == ["llm_profiles.json"]

    # Reopening this library in the process shares credentials, while a copied
    # profile file cannot expose credentials to a different isolated library.
    reopened = LLMProfileStore(path)
    assert reopened.has_secret(profile.id, profile.keys[0].id)
    copied_path = tmp_path / "other-library" / "llm_profiles.json"
    copied_path.parent.mkdir()
    shutil.copyfile(path, copied_path)
    assert LLMProfileStore(copied_path).credentials_for(profile.id) == ()
    reopened.clear_keys(profile.id)
    assert store.credentials_for(profile.id) == ()


def test_production_default_uses_os_keyring_contract(tmp_path, monkeypatch):
    monkeypatch.delenv("REWEAVE_CREDENTIAL_BACKEND", raising=False)
    writes = []
    monkeypatch.setattr(keyring, "set_password", lambda *args: writes.append(args))
    store = LLMProfileStore(tmp_path / "profiles.json")
    profile = store.create(_profile_input())
    assert store.credential_backend == "system"
    assert writes == [
        ("Reweave", f"llm-profile:{profile.id}:key:{profile.keys[0].id}", "synthetic-test-secret")
    ]


def test_invalid_backend_fails_before_creating_profile_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("REWEAVE_CREDENTIAL_BACKEND", "typo")
    path = tmp_path / "untouched" / "profiles.json"
    with pytest.raises(ValueError, match="system or memory"):
        LLMProfileStore(path)
    assert not path.parent.exists()


def test_ambient_paths_and_dotenv_are_isolated(isolated_test_environment, tmp_path):
    assert get_app_paths(ensure=False).data_dir == isolated_test_environment
    assert Path(os.environ["REWEAVE_DB"]).parent == isolated_test_environment
    env_file = tmp_path / ".env"
    env_file.write_text("REWEAVE_LLM_API_KEY=ambient-secret\n", encoding="utf-8")
    assert dotenv.load_dotenv(env_file) is False
    assert not os.getenv("REWEAVE_LLM_API_KEY")
    keyring.set_password("Reweave", "synthetic", "only-in-this-test")
    assert keyring.get_credential("Reweave", "synthetic").password == "only-in-this-test"


def test_network_guard_blocks_external_dns_and_sockets_without_calling_network():
    with pytest.raises(OSError, match="External network"):
        socket.getaddrinfo("example.com", 443)
    with pytest.raises(OSError, match="External network"):
        socket.gethostbyname("example.com")
    with socket.socket() as client:
        with pytest.raises(OSError, match="External network"):
            client.connect(("203.0.113.1", 443))
        with pytest.raises(OSError, match="External network"):
            client.connect_ex(("203.0.113.1", 443))
    with (
        socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client,
        pytest.raises(OSError, match="External network"),
    ):
        client.sendto(b"synthetic", ("203.0.113.1", 53))
    response = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"mock": True}))
    ).get("https://provider.invalid")
    assert response.json() == {"mock": True}


@pytest.mark.parametrize("run_for", [0, -1, float("inf"), float("nan"), 86401])
def test_headless_rejects_unbounded_or_invalid_lifetime(tmp_path, run_for):
    data_dir = tmp_path / "uncreated"
    with pytest.raises(ValueError, match="duration"):
        desktop.run_headless(data_dir=data_dir, run_for=run_for)
    assert not data_dir.exists()


def test_headless_rejects_default_user_data_and_external_stop_file(tmp_path, monkeypatch):
    default_dir = tmp_path / "pretend-production-library"
    monkeypatch.setattr(desktop, "user_data_dir", lambda *a, **k: str(default_dir))
    with pytest.raises(ValueError, match="separate data directory"):
        desktop.run_headless(data_dir=default_dir, run_for=1)
    with pytest.raises(ValueError, match="stop file"):
        desktop.run_headless(data_dir=tmp_path / "isolated", stop_file=tmp_path / "outside")
    assert not default_dir.exists()


def test_packaged_entrypoint_headless_uses_real_app_without_ui_and_cleans_up(tmp_path, monkeypatch):
    data_dir = tmp_path / "headless"
    stop_file = data_dir / "stop-request"
    previous_data_dir = os.environ["REWEAVE_DATA_DIR"]
    previous_db = os.environ["REWEAVE_DB"]
    imported = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "webview" or name.startswith("webview."):
            raise AssertionError("Headless launch imported native UI.")
        return imported(name, *args, **kwargs)

    def forbidden_keyring(*args, **kwargs):
        raise AssertionError("Headless launch accessed OS credentials.")

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    for method in ("get_password", "set_password", "delete_password"):
        monkeypatch.setattr(keyring, method, forbidden_keyring)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "Reweave.exe",
            "--headless",
            "--data-dir",
            str(data_dir),
            "--run-for",
            "10",
            "--stop-file",
            str(stop_file),
        ],
    )
    observations = {}
    errors = []

    def inspect_running_app():
        try:
            descriptor_path = data_dir / "extension-bridge.json"
            deadline = time.monotonic() + 8
            while not descriptor_path.exists() and time.monotonic() < deadline:
                time.sleep(0.025)
            descriptor = read_runtime_descriptor(descriptor_path)
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(f"http://127.0.0.1:{descriptor.port}/api/health") as response:
                observations["health"] = json.load(response)
            store = LLMProfileStore(data_dir / "llm_profiles.json")
            observations["backend"] = store.credential_backend
            assert all(not store.credentials_for(profile.id) for profile in store.list().profiles)
            profile = store.create(_profile_input())
            assert store.has_secret(profile.id, profile.keys[0].id)
            observations["profile_id"] = profile.id
        except BaseException as exc:
            errors.append(exc)
        finally:
            data_dir.mkdir(parents=True, exist_ok=True)
            stop_file.touch()

    observer = threading.Thread(target=inspect_running_app, name="isolated-runtime-observer")
    observer.start()
    started = time.monotonic()
    try:
        runpy.run_path(
            str(Path(__file__).parents[1] / "packaging" / "reweave_desktop.py"), run_name="__main__"
        )
    finally:
        observer.join(timeout=10)
    assert not observer.is_alive()
    assert not errors
    assert observations["health"]["status"] == "ok"
    assert observations["backend"] == "memory"
    assert time.monotonic() - started < 10
    assert (data_dir / "reweave.db").exists()
    assert not (data_dir / "extension-bridge.json").exists()
    assert os.environ["REWEAVE_DATA_DIR"] == previous_data_dir
    assert os.environ["REWEAVE_DB"] == previous_db
    assert "synthetic-test-secret" not in (data_dir / "llm_profiles.json").read_text()
    assert not any(thread.name == "reweave-server" for thread in threading.enumerate())
    # A second real lifespan reuses persisted data and expires without a stop file.
    desktop.run_headless(data_dir=data_dir, run_for=0.1)
    monkeypatch.setenv("REWEAVE_CREDENTIAL_BACKEND", "memory")
    assert LLMProfileStore(data_dir / "llm_profiles.json").get(observations["profile_id"])
    assert not (data_dir / "extension-bridge.json").exists()


def test_headless_cli_requires_explicit_data_directory():
    with pytest.raises(SystemExit) as error:
        desktop.cli_main(["--headless"])
    assert error.value.code == 2


def test_packaged_headless_failure_exits_without_an_unhandled_traceback(tmp_path, monkeypatch):
    def failed_start(argv=None):
        raise RuntimeError("Synthetic startup failure")

    monkeypatch.setattr(desktop, "cli_main", failed_start)
    monkeypatch.setattr(sys, "argv", ["Reweave.exe", "--headless", "--data-dir", str(tmp_path)])
    with pytest.raises(SystemExit) as error:
        runpy.run_path(
            str(Path(__file__).parents[1] / "packaging" / "reweave_desktop.py"),
            run_name="__main__",
        )
    assert error.value.code == 1
