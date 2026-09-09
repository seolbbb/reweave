"""Synthetic installer ownership tests; never install into a Windows profile."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "packaging" / "installer" / "lifecycle.ps1"
spec = importlib.util.spec_from_file_location(
    "windows_installer_builder", ROOT / "scripts" / "build_windows_installer.py"
)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


@pytest.fixture()
def workspace():
    cache = ROOT / ".pytest_cache" / "installer-tests"
    cache.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix="synthetic-", dir=cache)).resolve()
    yield path
    assert path.is_relative_to(cache.resolve()) and path != cache.resolve()
    shutil.rmtree(path)


def payload(workspace, files=None):
    source = workspace / "source"
    source.mkdir(exist_ok=True)
    paths = {}
    for name, contents in (
        files or {"Reweave.exe": b"synthetic executable", "_internal/data.txt": b"packaged data"}
    ).items():
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
        paths[name] = path
    result = workspace / "payload"
    builder.stage_payload(paths, result, "0.1.0-test")
    (result / "Uninstall.exe").write_bytes(b"synthetic uninstaller - never executed")
    return result


def invoke(workspace, operation, target, stage=None, isolated="1"):
    if os.name != "nt":
        pytest.skip("Windows PowerShell lifecycle verification")
    arguments = [
        "powershell.exe",
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(SCRIPT),
        "-Operation",
        operation,
        "-InstallRoot",
        str(target),
        "-Isolated",
        isolated,
        "-WorkspaceRoot",
        str(workspace),
    ]
    if stage:
        arguments.extend(["-PayloadRoot", str(stage)])
    return subprocess.run(
        arguments,
        capture_output=True,
        text=True,
        timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


@pytest.mark.parametrize(
    "name",
    [
        "../escape",
        "/absolute",
        "C:/drive",
        "nested\\file",
        "nested//file",
        "a/./b",
        "file:stream",
        "file.",
        "file ",
        "NUL.txt",
        "a/*",
        "a/\nfile",
    ],
)
def test_builder_rejects_ambiguous_windows_paths(name):
    with pytest.raises(ValueError):
        builder.relative_path(name)


def test_manifest_has_exact_file_hashes_and_no_ambient_profile(workspace):
    stage = payload(workspace)
    manifest = json.loads((stage / ".reweave-files.json").read_text())
    assert {file["path"] for file in manifest["files"]} == {"Reweave.exe", "_internal/data.txt"}
    for file in manifest["files"]:
        assert file["sha256"] == builder.file_hash(stage / file["path"])
    assert "api_key" not in json.dumps(manifest)


def test_install_and_uninstall_preserve_unrelated_and_user_data(workspace):
    target = workspace / ".pytest_cache" / "installation"
    data = workspace / "user-data" / "archive.db"
    data.parent.mkdir()
    data.write_bytes(b"synthetic user data")
    result = invoke(workspace, "Install", target, payload(workspace))
    assert result.returncode == 0, result.stdout + result.stderr
    manifest = json.loads((target / ".reweave-files.json").read_text())
    assert {row["path"] for row in manifest["files"]} == {
        "Reweave.exe",
        "_internal/data.txt",
        "Uninstall.exe",
    }
    unrelated = target / "_internal" / "owner-note.txt"
    unrelated.write_text("keep this")
    result = invoke(workspace, "Uninstall", target)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not (target / "Reweave.exe").exists()
    assert unrelated.read_text() == "keep this"
    assert data.read_bytes() == b"synthetic user data"


def test_uninstall_preserves_modified_owned_file(workspace):
    target = workspace / ".pytest_cache" / "installation"
    assert invoke(workspace, "Install", target, payload(workspace)).returncode == 0
    (target / "Reweave.exe").write_bytes(b"modified owner file")
    result = invoke(workspace, "Uninstall", target)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (target / "Reweave.exe").read_bytes() == b"modified owner file"
    assert "retained: 1" in result.stdout


def test_unmarked_nonempty_target_is_rejected_without_mutation(workspace):
    target = workspace / ".pytest_cache" / "installation"
    target.mkdir(parents=True)
    (target / "owner.txt").write_text("preserve")
    result = invoke(workspace, "Install", target, payload(workspace))
    assert result.returncode == 1
    assert sorted(path.name for path in target.iterdir()) == ["owner.txt"]


@pytest.mark.parametrize(
    "relative",
    [
        "outside",
        ".pytest_cache",
        ".pytest_cache/../escape",
        ".pytest_cache/.. /escape",
        ".pytest_cache/install.",
    ],
)
def test_isolated_root_must_be_strict_cache_descendant(workspace, relative):
    target = workspace / relative
    result = invoke(workspace, "Install", target, payload(workspace))
    assert result.returncode == 1
    assert not (target / "Reweave.exe").exists()


def test_normal_mode_cannot_operate_on_isolated_target(workspace):
    target = workspace / ".pytest_cache" / "installation"
    assert invoke(workspace, "Install", target, payload(workspace)).returncode == 0
    result = invoke(workspace, "Uninstall", target, isolated="0")
    assert result.returncode == 1
    assert (target / "Reweave.exe").exists()


def test_modified_old_file_blocks_update_before_copying(workspace):
    target = workspace / ".pytest_cache" / "installation"
    stage = payload(workspace)
    assert invoke(workspace, "Install", target, stage).returncode == 0
    (target / "_internal/data.txt").write_bytes(b"owner modification")
    stage = payload(workspace, {"Reweave.exe": b"new version", "_internal/data.txt": b"new data"})
    result = invoke(workspace, "Install", target, stage)
    assert result.returncode == 1
    assert (target / "Reweave.exe").read_bytes() == b"synthetic executable"
    assert (target / "_internal/data.txt").read_bytes() == b"owner modification"


def test_update_deletes_only_obsolete_owned_files(workspace):
    target = workspace / ".pytest_cache" / "installation"
    assert invoke(workspace, "Install", target, payload(workspace)).returncode == 0
    (target / "keep.txt").write_text("unrelated")
    stage = payload(workspace, {"Reweave.exe": b"updated", "new.txt": b"new"})
    result = invoke(workspace, "Install", target, stage)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (target / "Reweave.exe").read_bytes() == b"updated"
    assert not (target / "_internal/data.txt").exists()
    assert (target / "keep.txt").read_text() == "unrelated"


def test_new_payload_collision_blocks_update_before_copying(workspace):
    target = workspace / ".pytest_cache" / "installation"
    assert invoke(workspace, "Install", target, payload(workspace)).returncode == 0
    (target / "new.txt").write_text("owner")
    stage = payload(workspace, {"Reweave.exe": b"updated", "new.txt": b"new"})
    result = invoke(workspace, "Install", target, stage)
    assert result.returncode == 1
    assert (target / "Reweave.exe").read_bytes() == b"synthetic executable"
    assert (target / "new.txt").read_text() == "owner"


def test_corrupt_payload_hash_fails_before_target_creation(workspace):
    stage = payload(workspace)
    (stage / "Reweave.exe").write_bytes(b"corrupted")
    target = workspace / ".pytest_cache" / "installation"
    assert invoke(workspace, "Install", target, stage).returncode == 1
    assert not target.exists()


@pytest.mark.parametrize(
    "bad_path", ["../outside.txt", "C:/outside.txt", "a:stream", "NUL", "a//b"]
)
def test_malformed_uninstall_manifest_fails_before_any_file_removal(workspace, bad_path):
    target = workspace / ".pytest_cache" / "installation"
    assert invoke(workspace, "Install", target, payload(workspace)).returncode == 0
    path = target / ".reweave-files.json"
    manifest = json.loads(path.read_text())
    manifest["files"][-1]["path"] = bad_path
    path.write_text(json.dumps(manifest))
    result = invoke(workspace, "Uninstall", target)
    assert result.returncode == 1
    assert (target / "Reweave.exe").exists()
    assert (target / "_internal/data.txt").exists()


def test_swapped_marker_root_blocks_uninstall(workspace):
    target = workspace / ".pytest_cache" / "installation"
    assert invoke(workspace, "Install", target, payload(workspace)).returncode == 0
    path = target / ".reweave-install.json"
    marker = json.loads(path.read_text())
    marker["root"] = str(workspace / ".pytest_cache" / "another-installation")
    path.write_text(json.dumps(marker))
    assert invoke(workspace, "Uninstall", target).returncode == 1
    assert (target / "Reweave.exe").exists()


def test_installer_source_has_no_launch_or_recursive_directory_removal():
    nsi = (ROOT / "packaging/installer/Reweave.nsi").read_text()
    lifecycle = SCRIPT.read_text()
    assert "RequestExecutionLevel user" in nsi
    assert "MUI_FINISHPAGE_RUN" not in nsi
    assert "ExecShell" not in nsi
    assert "RMDir /r" not in nsi
    assert "-Recurse" not in lifecycle
    assert "RunOnce" not in lifecycle
    assert lifecycle.count("if ($Isolated -ne '1')") == 2


def test_isolated_lifecycle_never_reaches_registry_or_shortcut_commands(workspace):
    if os.name != "nt":
        pytest.skip("Windows PowerShell lifecycle verification")
    stage = payload(workspace)
    target = workspace / ".pytest_cache" / "tripwire"
    wrapper = workspace / "tripwire.ps1"
    wrapper.write_text(
        "param([string]$Action,[string]$Lifecycle,[string]$Target,[string]$Payload,[string]$Workspace)\n"
        "function New-Item { throw 'Registry creation was attempted' }\n"
        "function New-ItemProperty { throw 'Registry mutation was attempted' }\n"
        "function Get-ItemProperty { throw 'Registry access was attempted' }\n"
        "function New-Object { throw 'Shortcut COM creation was attempted' }\n"
        "& $Lifecycle -Operation $Action -InstallRoot $Target -PayloadRoot $Payload "
        "-Isolated 1 -WorkspaceRoot $Workspace\n"
    )
    for action in ("Install", "Uninstall"):
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(wrapper),
                action,
                str(SCRIPT),
                str(target),
                str(stage),
                str(workspace),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        assert result.returncode == 0, result.stdout + result.stderr


def test_junction_target_is_rejected_before_writing_outside_target(workspace):
    if os.name != "nt":
        pytest.skip("Windows junction verification")
    outside = workspace / "unrelated"
    outside.mkdir()
    sentinel = outside / "owner.txt"
    sentinel.write_text("preserve")
    target = workspace / ".pytest_cache" / "junction"
    target.parent.mkdir()
    assert target.is_relative_to(workspace) and outside.is_relative_to(workspace)
    script = workspace / "make-junction.ps1"
    script.write_text(
        "param([string]$Link,[string]$Destination)\n"
        "New-Item -ItemType Junction -Path $Link -Value $Destination | Out-Null\n"
    )
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            str(target),
            str(outside),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    try:
        result = invoke(workspace, "Install", target, payload(workspace))
        assert result.returncode == 1
        assert list(outside.iterdir()) == [sentinel]
        with pytest.raises(ValueError, match="reparse"):
            builder.ensure_plain_path(target)
    finally:
        # Remove only the checked junction itself, never its target contents.
        assert target.parent.resolve().is_relative_to(workspace.resolve())
        os.rmdir(target)
