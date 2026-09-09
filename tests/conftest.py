"""Shared fixtures: isolated libraries, volatile credentials, and loopback-only I/O."""

import ipaddress
import os
import socket
from pathlib import Path

import dotenv
import keyring
import keyring.backend
import keyring.core
import pytest
from fastapi.testclient import TestClient

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _clear_ambient_environment(monkeypatch):
    prefixes = ("REWEAVE_", "OPENAI_", "ANTHROPIC_", "GEMINI_", "OPENROUTER_", "AZURE_OPENAI_")
    names = {
        "GOOGLE_API_KEY",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "HF_TOKEN",
        "HUGGING_FACE_HUB_TOKEN",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
    }
    for name in tuple(os.environ):
        if name.upper().startswith(prefixes) or name.upper() in names:
            monkeypatch.delenv(name, raising=False)


def pytest_configure(config):
    # Collection imports config.py, so disabling dotenv in a fixture is too late.
    patch = pytest.MonkeyPatch()
    config._reweave_environment_patch = patch
    _clear_ambient_environment(patch)
    patch.setenv("PYTHON_DOTENV_DISABLED", "1")
    patch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: False)


def pytest_unconfigure(config):
    patch = getattr(config, "_reweave_environment_patch", None)
    if patch is not None:
        patch.undo()


@pytest.fixture(autouse=True)
def isolated_test_environment(monkeypatch, tmp_path):
    """Make accidental defaults safe while leaving explicit provider mocks usable."""
    from reweave import llm_profiles

    _clear_ambient_environment(monkeypatch)
    monkeypatch.setattr(llm_profiles, "_MEMORY_SECRETS", {})
    original_client_init = TestClient.__init__

    def local_client_init(self, app, *args, **kwargs):
        # Test clients use a real permitted origin without weakening production Host checks.
        if not args and "base_url" not in kwargs:
            kwargs["base_url"] = "http://127.0.0.1"
        original_client_init(self, app, *args, **kwargs)

    monkeypatch.setattr(TestClient, "__init__", local_client_init)
    data_dir = tmp_path / "default-app-data"
    monkeypatch.setenv("REWEAVE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("REWEAVE_DB", str(data_dir / "reweave.db"))
    monkeypatch.setenv("REWEAVE_EXPORT_DIR", str(data_dir / "exports"))
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    monkeypatch.setenv("HF_HOME", str(tmp_path / "model-cache"))

    secrets = {}

    class MemoryKeyring(keyring.backend.KeyringBackend):
        priority = 1

        def get_password(self, service, username):
            return secrets.get((service, username))

        def set_password(self, service, username, password):
            secrets[(service, username)] = password

        def delete_password(self, service, username):
            secrets.pop((service, username), None)

    backend = MemoryKeyring()
    monkeypatch.setattr(keyring, "get_keyring", lambda: backend)
    monkeypatch.setattr(keyring.core, "get_keyring", lambda: backend)
    monkeypatch.setattr(keyring, "set_password", lambda s, n, v: secrets.__setitem__((s, n), v))
    monkeypatch.setattr(keyring, "get_password", lambda s, n: secrets.get((s, n)))
    monkeypatch.setattr(keyring, "delete_password", lambda s, n: secrets.pop((s, n), None))

    def require_loopback(host):
        if isinstance(host, bytes):
            host = host.decode("ascii")
        if host in {None, "", "localhost"}:
            return
        try:
            if ipaddress.ip_address(host).is_loopback:
                return
        except ValueError:
            pass
        raise OSError("External network access is disabled in Reweave tests.")

    original_getaddrinfo = socket.getaddrinfo
    original_gethostbyname = socket.gethostbyname
    original_gethostbyname_ex = socket.gethostbyname_ex
    original_getnameinfo = socket.getnameinfo
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_sendto = socket.socket.sendto

    def getaddrinfo(host, *args, **kwargs):
        require_loopback(host)
        return original_getaddrinfo(host, *args, **kwargs)

    def connect(sock, address):
        if sock.family in {socket.AF_INET, socket.AF_INET6}:
            require_loopback(address[0])
        return original_connect(sock, address)

    def gethostbyname(host):
        require_loopback(host)
        return original_gethostbyname(host)

    def gethostbyname_ex(host):
        require_loopback(host)
        return original_gethostbyname_ex(host)

    def getnameinfo(address, flags):
        require_loopback(address[0])
        return original_getnameinfo(address, flags)

    def connect_ex(sock, address):
        if sock.family in {socket.AF_INET, socket.AF_INET6}:
            require_loopback(address[0])
        return original_connect_ex(sock, address)

    def sendto(sock, data, *args):
        if sock.family in {socket.AF_INET, socket.AF_INET6}:
            require_loopback(args[-1][0])
        return original_sendto(sock, data, *args)

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(socket, "gethostbyname", gethostbyname)
    monkeypatch.setattr(socket, "gethostbyname_ex", gethostbyname_ex)
    monkeypatch.setattr(socket, "getnameinfo", getnameinfo)
    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket.socket, "sendto", sendto)
    yield data_dir
    secrets.clear()


@pytest.fixture()
def fixtures_dir():
    """Return the path to test fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture()
def chatgpt_sample_path():
    """Return path to ChatGPT sample JSON."""
    return FIXTURES_DIR / "chatgpt_sample.json"


@pytest.fixture()
def claude_sample_path():
    """Return path to Claude sample JSON."""
    return FIXTURES_DIR / "claude_sample.json"
