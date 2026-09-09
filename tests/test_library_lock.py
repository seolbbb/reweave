"""Library ownership prevents a second runtime from reaching startup recovery."""

import threading

import pytest

import reweave.web
from reweave.desktop import running_app
from reweave.library_lock import library_lock


def test_second_owner_fails_before_runtime_writes_and_releases_on_error(tmp_path):
    database = tmp_path / "library.db"
    with library_lock(database):
        with (
            pytest.raises(RuntimeError, match="already open"),
            running_app(database, data_dir=tmp_path / "second"),
        ):
            pytest.fail("A second runtime acquired the same Library.")
        assert not database.exists()
        assert not (tmp_path / "second").exists()
    with pytest.raises(ValueError, match="synthetic"), library_lock(database):
        raise ValueError("synthetic")
    with library_lock(database):
        assert not database.exists()


def test_runtime_keeps_owner_until_shutdown_worker_finishes(tmp_path, monkeypatch):
    original = reweave.web.create_app
    active = []
    release = threading.Event()
    started = threading.Event()
    wrote = threading.Event()
    observations = []
    database = tmp_path / "library.db"

    def create(*args, **kwargs):
        app = original(*args, **kwargs)
        active.append(app)
        return app

    def worker():
        started.set()
        assert release.wait(5)
        (tmp_path / "finished.txt").write_text("synthetic", encoding="utf-8")
        wrote.set()

    def check_while_closing():
        try:
            assert active[0].state.stopping.wait(5)
            with pytest.raises(RuntimeError, match="already open"), library_lock(database):
                pass
            observations.append("locked during worker")
        finally:
            release.set()

    monkeypatch.setattr(reweave.web, "create_app", create)
    with running_app(database, data_dir=tmp_path):
        active[0].state.context_executor.submit(worker)
        assert started.wait(5)
        observer = threading.Thread(target=check_while_closing)
        observer.start()
    observer.join(timeout=5)
    assert not observer.is_alive()
    assert observations == ["locked during worker"]
    assert wrote.is_set()
    with library_lock(database):
        assert (tmp_path / "finished.txt").exists()
