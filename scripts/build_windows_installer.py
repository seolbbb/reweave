"""Build a per-user NSIS installer from an already verified PyInstaller bundle.

The portable compiler is pinned, verified, and extracted inside this workspace's
ignored cache. This script never installs the compiler or the resulting product.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import time
import tomllib
import urllib.request
import uuid
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "packaging" / "installer"
PRODUCT_ID = "reweave-local-desktop-8912a075-3c88-4ec1-a542-2a6a228bb592"
RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", re.I)
MAX_FILES = 30000


def relative_path(value: str) -> str:
    """Accept a portable, unambiguous Windows relative file path."""
    path = PurePosixPath(value)
    if not value or "\\" in value or path.is_absolute() or str(path) != value:
        raise ValueError("Invalid relative bundle path")
    for part in path.parts:
        if (
            part in {".", ".."}
            or part.endswith((" ", "."))
            or any(ord(char) < 32 or char in '<>:"|?*' for char in part)
            or RESERVED.match(part)
        ):
            raise ValueError("Invalid Windows bundle path")
    return value


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def ensure_plain_path(path: Path) -> None:
    """Reject links/junctions in a source or destination and its ancestors."""
    for entry in (path, *path.parents):
        if entry.exists() and (
            entry.is_symlink()
            or getattr(entry.stat(follow_symlinks=False), "st_file_attributes", 0)
            & stat.FILE_ATTRIBUTE_REPARSE_POINT
        ):
            raise ValueError("Links and reparse points are not allowed")


def prepare_toolchain(root: Path = ROOT) -> Path:
    config = json.loads((INSTALLER / "toolchain.json").read_text(encoding="utf-8"))
    cache = root.resolve() / ".pytest_cache" / "installer-toolchain"
    ensure_plain_path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / f"nsis-{config['version']}.zip"
    if not archive.exists():
        with urllib.request.urlopen(config["download_url"], timeout=60) as response:
            data = response.read(config["size"] + 1)
        if len(data) != config["size"] or hashlib.sha256(data).hexdigest() != config["sha256"]:
            raise ValueError("NSIS download size or SHA-256 does not match the pinned release")
        archive.write_bytes(data)
    if archive.stat().st_size != config["size"] or file_hash(archive) != config["sha256"]:
        raise ValueError("Cached NSIS archive does not match the pinned release")
    destination = cache / config["sha256"][:16]
    ensure_plain_path(destination)
    destination.mkdir(exist_ok=True)
    # Re-extract verified bytes, including include files/plugins, before execution.
    # No cached executable or configuration is trusted independently of the ZIP.
    with zipfile.ZipFile(archive) as package:
        if (
            len(package.infolist()) > 5000
            or sum(i.file_size for i in package.infolist()) > 100_000_000
        ):
            raise ValueError("Unexpected NSIS archive dimensions")
        entries: list[tuple[zipfile.ZipInfo, Path]] = []
        for info in package.infolist():
            name = relative_path(info.filename.rstrip("/"))
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError("NSIS archive contains a link")
            target = destination.joinpath(*PurePosixPath(name).parts)
            ensure_plain_path(target)
            entries.append((info, target))
        expected = {target for _, target in entries}
        expected.update(
            parent
            for _, target in entries
            for parent in target.parents
            if parent != destination and parent.is_relative_to(destination)
        )
        if any(path not in expected for path in destination.rglob("*")):
            raise ValueError("Unexpected files in the portable compiler cache")
        for info, target in entries:
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(package.read(info))
    compiler = destination / f"nsis-{config['version']}" / "makensis.exe"
    if not compiler.is_file():
        raise ValueError("Verified NSIS archive is missing makensis.exe")
    return compiler


def collect_payload(bundle_root: Path, root: Path = ROOT) -> dict[str, Path]:
    bundle_root = bundle_root.absolute()
    ensure_plain_path(bundle_root)
    for name in ("Reweave.exe", "ReweaveNativeHost.exe"):
        if not (bundle_root / name).is_file():
            raise ValueError(
                f"PyInstaller bundle is missing {name}; build packaging/Reweave.spec first"
            )
    result: dict[str, Path] = {}
    folded: set[str] = set()

    def add(path: Path, name: str) -> None:
        relative_path(name)
        ensure_plain_path(path)
        if name.casefold() in folded:
            raise ValueError("Case-insensitive duplicate bundle path")
        folded.add(name.casefold())
        result[name] = path

    for file in sorted(bundle_root.rglob("*")):
        ensure_plain_path(file)
        if file.is_file():
            add(file, file.relative_to(bundle_root).as_posix())
    extension = root / "extension"
    for file in sorted(extension.rglob("*")):
        ensure_plain_path(file)
        if file.is_file() and file.suffix.lower() in {
            ".json",
            ".js",
            ".css",
            ".html",
            ".png",
            ".svg",
            ".md",
        }:
            add(file, "extension/" + file.relative_to(extension).as_posix())
    for name in ("register_native_host.ps1", "unregister_native_host.ps1"):
        add(root / "scripts" / name, "scripts/" + name)
    add(root / "LICENSE", "LICENSE")
    add(INSTALLER / "README.md", "INSTALLATION.md")
    add(INSTALLER / "lifecycle.ps1", "installer/lifecycle.ps1")
    if len(result) > MAX_FILES:
        raise ValueError("Bundle has too many files")
    return result


def stage_payload(files: dict[str, Path], destination: Path, version: str) -> dict:
    ensure_plain_path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    entries = []
    for name, source in sorted(files.items()):
        relative_path(name)
        target = destination.joinpath(*PurePosixPath(name).parts)
        ensure_plain_path(source)
        ensure_plain_path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        entries.append({"path": name, "sha256": file_hash(target), "size": target.stat().st_size})
    manifest = {"schema": 1, "product": PRODUCT_ID, "version": version, "files": entries}
    (destination / ".reweave-files.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def nsis_string(value: str) -> str:
    if "\n" in value or "\r" in value:
        raise ValueError("Newlines are not valid in an NSIS definition")
    return value.replace("$", "$$").replace('"', '$\\"')


def build(bundle_root: Path, output: Path, version: str) -> dict:
    if os.name != "nt":
        raise RuntimeError("Windows is required for the installer build")
    if not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z.+_-]{0,63}", version):
        raise ValueError("Invalid installer version")
    output = output.absolute()
    ensure_plain_path(output)
    compiler = prepare_toolchain()
    files = collect_payload(bundle_root)
    cache = ROOT / ".pytest_cache" / "installer-build"
    ensure_plain_path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="build-", dir=cache) as temporary:
        workspace = Path(temporary)
        payload = workspace / "payload"
        manifest = stage_payload(files, payload, version)
        config = workspace / "build.nsh"
        config.write_text(
            "\n".join(
                f'!define {key} "{nsis_string(value)}"'
                for key, value in {
                    "PAYLOAD": str(payload),
                    "OUTPUT": str(output),
                    "VERSION": version,
                    "LIFECYCLE": str(INSTALLER / "lifecycle.ps1"),
                    "PRODUCT_LICENSE": str(ROOT / "LICENSE"),
                }.items()
            )
            + "\n",
            encoding="utf-8",
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        command = [
            str(compiler),
            "/NOCONFIG",
            "/V3",
            f"/DBUILD_CONFIG={config}",
            str(INSTALLER / "Reweave.nsi"),
        ]
        subprocess.run(command, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        if not output.is_file() or output.stat().st_size == 0:
            raise RuntimeError("NSIS did not create the installer")
        evidence = {
            "installer": output.name,
            "version": version,
            "sha256": file_hash(output),
            "size": output.stat().st_size,
            "compiler": "NSIS 3.12",
            "payload": manifest,
        }
        output.with_suffix(".manifest.json").write_text(
            json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
        )
    return evidence


def verify_isolated(installer: Path, workspace: Path = ROOT) -> dict:
    """Exercise the actual EXE without registry, shortcuts, UI or app execution."""
    if os.name != "nt":
        raise RuntimeError("Windows is required for installer verification")
    workspace = workspace.absolute()
    ensure_plain_path(workspace)
    target = workspace / ".pytest_cache" / ("installer-qa-" + uuid.uuid4().hex)
    ensure_plain_path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    assert target.is_relative_to(workspace / ".pytest_cache") and not target.exists()
    # NSIS documents /D= as the final, unquoted command-line tail, including
    # spaces. Other arguments use CreateProcess quoting and never a shell.
    command = (
        subprocess.list2cmdline(
            [str(installer.absolute()), "/S", "/ISOLATED", "/WORKSPACE=" + str(workspace)]
        )
        + " /D="
        + str(target)
    )
    result = subprocess.run(command, timeout=600, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode != 0:
        raise RuntimeError("Isolated installer exited unsuccessfully")
    marker = json.loads((target / ".reweave-install.json").read_text(encoding="utf-8"))
    if marker["isolated"] != "1" or marker["root"] != str(target):
        raise RuntimeError("Installer did not retain the isolated target contract")
    manifest = json.loads((target / ".reweave-files.json").read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        path = target / relative_path(entry["path"])
        ensure_plain_path(path)
        if file_hash(path) != entry["sha256"]:
            raise RuntimeError("Installed payload hash mismatch")
    sentinel = target / "unrelated-synthetic-sentinel.txt"
    sentinel.write_text("Preserve this unrelated synthetic file.\n", encoding="utf-8")
    result = subprocess.run(
        [str(target / "Uninstall.exe"), "/S", "/ISOLATED", "/WORKSPACE=" + str(workspace)],
        timeout=60,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if result.returncode != 0:
        raise RuntimeError("Isolated uninstaller launcher exited unsuccessfully")
    # NSIS copies the uninstaller to its private temporary directory and the
    # original launcher can return before that child finishes.
    deadline = time.monotonic() + 120
    while (target / ".reweave-install.json").exists() and time.monotonic() < deadline:
        time.sleep(0.2)
    remaining = sorted(
        path.relative_to(target).as_posix() for path in target.rglob("*") if path.is_file()
    )
    if (
        remaining != [sentinel.name]
        or sentinel.read_text(encoding="utf-8") != "Preserve this unrelated synthetic file.\n"
    ):
        raise RuntimeError("Uninstaller did not preserve exactly the unrelated sentinel")
    evidence = {
        "installer_sha256": file_hash(installer),
        "isolated": True,
        "workspace_target": target.relative_to(workspace).as_posix(),
        "installed_files_verified": len(manifest["files"]),
        "install_exit": 0,
        "uninstall_launcher_exit": 0,
        "owned_files_removed": True,
        "unrelated_file_preserved": True,
        "application_started": False,
    }
    installer.with_suffix(".verification.json").write_text(
        json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
    )
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-toolchain", action="store_true")
    parser.add_argument(
        "--verify-isolated",
        action="store_true",
        help="Verify the output EXE without building or touching Windows profile state",
    )
    parser.add_argument("--bundle-root", type=Path, default=ROOT / "dist" / "Reweave")
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "Reweave-Setup.exe")
    parser.add_argument(
        "--version",
        default=tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
            "version"
        ],
    )
    args = parser.parse_args()
    if args.verify_isolated:
        print(json.dumps(verify_isolated(args.output), indent=2))
    elif args.prepare_toolchain:
        compiler = prepare_toolchain()
        result = subprocess.run(
            [str(compiler), "/NOCONFIG", "/VERSION"],
            check=True,
            capture_output=True,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        print(json.dumps({"compiler": str(compiler), "version": result.stdout.strip()}))
    else:
        evidence = build(args.bundle_root, args.output, args.version)
        print(
            json.dumps(
                {key: value for key, value in evidence.items() if key != "payload"}, indent=2
            )
        )


if __name__ == "__main__":
    main()
