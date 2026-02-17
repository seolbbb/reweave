"""Prompt bundle registry and YAML I/O."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from sbs.llm import prompts as prompt_module

DEFAULT_PROMPT_KEYS_BY_STAGE: dict[str, list[str]] = {
    "segmentation": [
        "SEGMENTATION_SYSTEM",
        "SEGMENTATION_USER",
        "SEGMENTATION_BATCH_SYSTEM",
        "SEGMENTATION_BATCH_USER",
    ],
    "extraction": ["EXTRACTION_SYSTEM", "EXTRACTION_USER"],
    "synthesis": ["SYNTHESIS_SYSTEM", "SYNTHESIS_USER"],
    "linking": [
        "LINKING_CLUSTER_SYSTEM",
        "LINKING_CLUSTER_USER",
        "LINKING_DISCOVER_SYSTEM",
        "LINKING_DISCOVER_USER",
    ],
    "validation": ["VALIDATION_ATOMICITY_SYSTEM", "VALIDATION_ATOMICITY_USER"],
}
REGISTRY_FILE = "registry.yaml"


class PromptBundle(BaseModel):
    """Versioned set of prompts used by the pipeline."""

    bundle_id: str = "default"
    created_at: str = Field(default_factory=lambda: datetime.now(tz=UTC).isoformat())
    prompts: dict[str, str] = Field(default_factory=dict)


def default_prompt_map() -> dict[str, str]:
    """Return the in-code default prompt map."""
    return {
        "SEGMENTATION_SYSTEM": prompt_module.SEGMENTATION_SYSTEM,
        "SEGMENTATION_USER": prompt_module.SEGMENTATION_USER,
        "SEGMENTATION_BATCH_SYSTEM": prompt_module.SEGMENTATION_BATCH_SYSTEM,
        "SEGMENTATION_BATCH_USER": prompt_module.SEGMENTATION_BATCH_USER,
        "EXTRACTION_SYSTEM": prompt_module.EXTRACTION_SYSTEM,
        "EXTRACTION_USER": prompt_module.EXTRACTION_USER,
        "SYNTHESIS_SYSTEM": prompt_module.SYNTHESIS_SYSTEM,
        "SYNTHESIS_USER": prompt_module.SYNTHESIS_USER,
        "LINKING_CLUSTER_SYSTEM": prompt_module.LINKING_CLUSTER_SYSTEM,
        "LINKING_CLUSTER_USER": prompt_module.LINKING_CLUSTER_USER,
        "LINKING_DISCOVER_SYSTEM": prompt_module.LINKING_DISCOVER_SYSTEM,
        "LINKING_DISCOVER_USER": prompt_module.LINKING_DISCOVER_USER,
        "VALIDATION_ATOMICITY_SYSTEM": prompt_module.VALIDATION_ATOMICITY_SYSTEM,
        "VALIDATION_ATOMICITY_USER": prompt_module.VALIDATION_ATOMICITY_USER,
    }


def detect_default_prompt_source(cwd: Path | None = None) -> Path | None:
    """Discover default prompt bundle source under the current working directory."""
    root = cwd or Path.cwd()
    prompts_root = root / "prompts"
    if not prompts_root.exists():
        return None

    registry_file = prompts_root / REGISTRY_FILE
    if registry_file.exists():
        registry_data = _read_yaml(registry_file)
        active_bundle = str(registry_data.get("active_bundle", "")).strip()
        if active_bundle:
            bundle_dir = prompts_root / "bundles" / active_bundle
            if bundle_dir.exists():
                return bundle_dir

    if (prompts_root / "bundle.yaml").exists() or (prompts_root / "stages").exists():
        return prompts_root

    # Fallback: default bundle path if registry was incomplete.
    default_bundle_dir = prompts_root / "bundles" / "default"
    if default_bundle_dir.exists():
        return default_bundle_dir

    return None


def load_prompt_registry(prompts_root: Path) -> dict[str, Any]:
    """Load prompts/registry.yaml or return default metadata."""
    registry_path = prompts_root / REGISTRY_FILE
    if not registry_path.exists():
        return {"active_bundle": "default"}
    return _read_yaml(registry_path)


def write_prompt_registry(prompts_root: Path, active_bundle: str) -> Path:
    """Write prompts/registry.yaml with active bundle metadata."""
    prompts_root.mkdir(parents=True, exist_ok=True)
    registry_path = prompts_root / REGISTRY_FILE
    payload = {
        "active_bundle": active_bundle,
        "updated_at": datetime.now(tz=UTC).isoformat(),
    }
    registry_path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return registry_path


def resolve_bundle_path(
    bundle_ref: str | Path | None,
    prompts_root: Path = Path("./prompts"),
) -> Path:
    """Resolve bundle reference to a concrete path."""
    if bundle_ref is None:
        source = detect_default_prompt_source()
        if source:
            return source
        raise FileNotFoundError("No prompt bundle source found.")

    if isinstance(bundle_ref, Path):
        return bundle_ref

    candidate_path = Path(bundle_ref)
    if candidate_path.exists():
        return candidate_path

    if bundle_ref == "active":
        registry = load_prompt_registry(prompts_root)
        bundle_ref = str(registry.get("active_bundle", "default"))

    bundle_dir = prompts_root / "bundles" / bundle_ref
    if bundle_dir.exists():
        return bundle_dir

    raise FileNotFoundError(f"Prompt bundle not found: {bundle_ref}")


def load_prompt_bundle(path: Path | None = None) -> PromptBundle:
    """Load prompt bundle from a YAML file or directory."""
    defaults = default_prompt_map()

    if path is None:
        return PromptBundle(bundle_id="default", prompts=defaults)

    if not path.exists():
        raise FileNotFoundError(f"Prompt bundle path not found: {path}")

    raw: dict[str, Any]
    bundle_id: str
    created_at: str

    if path.is_file():
        raw = _read_yaml(path)
        bundle_id = str(raw.get("bundle_id", path.stem))
        created_at = str(raw.get("created_at", datetime.now(tz=UTC).isoformat()))
        prompts = _normalize_prompts(raw)
    else:
        metadata = _read_bundle_metadata(path)
        bundle_id = str(metadata.get("bundle_id", path.name))
        created_at = str(metadata.get("created_at", datetime.now(tz=UTC).isoformat()))
        prompts = _load_prompts_from_dir(path)
        # Allow inline prompt overrides in bundle.yaml
        prompts.update(_normalize_prompts(metadata))

    unknown_keys = set(prompts) - set(defaults)
    if unknown_keys:
        keys = ", ".join(sorted(unknown_keys))
        raise ValueError(f"Unknown prompt keys in bundle: {keys}")

    merged = dict(defaults)
    merged.update(prompts)
    return PromptBundle(bundle_id=bundle_id, created_at=created_at, prompts=merged)


def write_prompt_bundle(
    bundle: PromptBundle,
    output_dir: Path,
    overwrite: bool = False,
) -> None:
    """Write prompt bundle to bundle.yaml + per-stage files."""
    if output_dir.exists() and any(output_dir.iterdir()) and not overwrite:
        raise FileExistsError(
            f"Output directory is not empty: {output_dir}. Use overwrite=True to replace."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    stages_dir = output_dir / "stages"
    stages_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "bundle_id": bundle.bundle_id,
        "created_at": bundle.created_at,
    }
    (output_dir / "bundle.yaml").write_text(
        yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    for stage_name, keys in DEFAULT_PROMPT_KEYS_BY_STAGE.items():
        payload = {
            "prompts": {
                key: bundle.prompts[key]
                for key in keys
                if key in bundle.prompts
            }
        }
        stage_file = stages_dir / f"{stage_name}.yaml"
        stage_file.write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )


def _read_bundle_metadata(path: Path) -> dict[str, Any]:
    bundle_file = path / "bundle.yaml"
    if bundle_file.exists():
        return _read_yaml(bundle_file)
    return {}


def _load_prompts_from_dir(path: Path) -> dict[str, str]:
    prompts: dict[str, str] = {}

    candidate_dirs = [path / "stages", path]
    for stage_name in DEFAULT_PROMPT_KEYS_BY_STAGE:
        for base_dir in candidate_dirs:
            yaml_path = base_dir / f"{stage_name}.yaml"
            yml_path = base_dir / f"{stage_name}.yml"
            if yaml_path.exists():
                prompts.update(_normalize_prompts(_read_yaml(yaml_path)))
            if yml_path.exists():
                prompts.update(_normalize_prompts(_read_yaml(yml_path)))

    # Optional flat prompt map in prompts.yaml
    for filename in ("prompts.yaml", "prompts.yml"):
        file_path = path / filename
        if file_path.exists():
            prompts.update(_normalize_prompts(_read_yaml(file_path)))

    return prompts


def _normalize_prompts(data: dict[str, Any]) -> dict[str, str]:
    raw_prompts = data.get("prompts")
    if raw_prompts is None:
        raw_prompts = {
            key: value
            for key, value in data.items()
            if isinstance(key, str) and key.upper() == key and "_" in key
        }
    if not isinstance(raw_prompts, dict):
        return {}

    prompts: dict[str, str] = {}
    for key, value in raw_prompts.items():
        if isinstance(value, str):
            prompts[key] = value
    return prompts


def _read_yaml(path: Path) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8")
    parsed = yaml.safe_load(content)
    if parsed is None:
        return {}
    if not isinstance(parsed, dict):
        raise ValueError(f"YAML content must be an object: {path}")
    return parsed
