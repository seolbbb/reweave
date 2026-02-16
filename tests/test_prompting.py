"""Tests for prompt bundle loading and registry helpers."""

from __future__ import annotations

from pathlib import Path

import yaml

from sbs.prompting.registry import (
    DEFAULT_PROMPT_KEYS_BY_STAGE,
    PromptBundle,
    default_prompt_map,
    detect_default_prompt_source,
    load_prompt_bundle,
    write_prompt_bundle,
)


def test_default_prompt_map_has_all_expected_keys():
    defaults = default_prompt_map()
    expected = {
        key
        for keys in DEFAULT_PROMPT_KEYS_BY_STAGE.values()
        for key in keys
    }
    assert set(defaults) == expected


def test_load_prompt_bundle_with_partial_override_file(tmp_path: Path):
    bundle_file = tmp_path / "bundle.yaml"
    bundle_file.write_text(
        yaml.safe_dump(
            {
                "bundle_id": "partial",
                "prompts": {
                    "SEGMENTATION_SYSTEM": "custom segmentation system prompt",
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    bundle = load_prompt_bundle(bundle_file)
    defaults = default_prompt_map()

    assert bundle.bundle_id == "partial"
    assert bundle.prompts["SEGMENTATION_SYSTEM"] == "custom segmentation system prompt"
    assert bundle.prompts["EXTRACTION_SYSTEM"] == defaults["EXTRACTION_SYSTEM"]


def test_write_and_load_prompt_bundle_roundtrip(tmp_path: Path):
    defaults = default_prompt_map()
    defaults["VALIDATION_ATOMICITY_SYSTEM"] = "custom validator"
    bundle = PromptBundle(bundle_id="roundtrip", prompts=defaults)
    out_dir = tmp_path / "bundle"

    write_prompt_bundle(bundle, out_dir, overwrite=False)
    loaded = load_prompt_bundle(out_dir)

    assert loaded.bundle_id == "roundtrip"
    assert loaded.prompts["VALIDATION_ATOMICITY_SYSTEM"] == "custom validator"


def test_detect_default_prompt_source_uses_registry(tmp_path: Path):
    prompts_root = tmp_path / "prompts"
    bundle_dir = prompts_root / "bundles" / "default"
    write_prompt_bundle(PromptBundle(prompts=default_prompt_map()), bundle_dir, overwrite=False)
    (prompts_root / "registry.yaml").write_text(
        yaml.safe_dump({"active_bundle": "default"}, sort_keys=False),
        encoding="utf-8",
    )

    detected = detect_default_prompt_source(tmp_path)
    assert detected == bundle_dir
