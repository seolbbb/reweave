"""Managed filesystem paths for Reweave."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_data_dir

APP_NAME = "Reweave"


@dataclass(frozen=True)
class AppPaths:
    data_dir: Path
    db_path: Path
    imports_dir: Path
    extracted_dir: Path
    llm_profiles_path: Path

    def ensure(self) -> AppPaths:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.imports_dir.mkdir(parents=True, exist_ok=True)
        self.extracted_dir.mkdir(parents=True, exist_ok=True)
        return self


def get_app_paths(data_dir: Path | None = None) -> AppPaths:
    root = data_dir or Path(user_data_dir(APP_NAME, appauthor=False))
    return AppPaths(
        data_dir=root,
        db_path=root / "reweave.db",
        imports_dir=root / "imports",
        extracted_dir=root / "extracted",
        llm_profiles_path=root / "llm_profiles.json",
    ).ensure()
