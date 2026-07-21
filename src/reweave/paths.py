"""Managed filesystem paths for Reweave."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_data_dir

APP_NAME = "Reweave"


@dataclass(frozen=True)
class AppPaths:
    data_dir: Path
    db_path: Path
    memory_audit_db_path: Path
    imports_dir: Path
    extracted_dir: Path
    llm_profiles_path: Path
    models_dir: Path
    extension_runtime_path: Path

    def ensure(self) -> AppPaths:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.imports_dir.mkdir(parents=True, exist_ok=True)
        self.extracted_dir.mkdir(parents=True, exist_ok=True)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        return self


def get_app_paths(data_dir: Path | None = None, *, ensure: bool = True) -> AppPaths:
    configured_data_dir = os.getenv("REWEAVE_DATA_DIR")
    root = data_dir or (
        Path(configured_data_dir)
        if configured_data_dir
        else Path(user_data_dir(APP_NAME, appauthor=False))
    )
    paths = AppPaths(
        data_dir=root,
        db_path=root / "reweave.db",
        memory_audit_db_path=root / "memory-audit-p0.db",
        imports_dir=root / "imports",
        extracted_dir=root / "extracted",
        llm_profiles_path=root / "llm_profiles.json",
        models_dir=root / "models",
        extension_runtime_path=root / "extension-bridge.json",
    )
    return paths.ensure() if ensure else paths
