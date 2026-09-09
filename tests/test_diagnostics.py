"""Support exports retain useful counts while excluding local identity and credential data."""

from fastapi.testclient import TestClient

from reweave.archive import ArchiveStore
from reweave.context_library import CONTEXT_SCHEMA_VERSION
from reweave.llm_profiles import KeyInput, LLMProfileStore, ProfileInput
from reweave.paths import get_app_paths
from reweave.web import create_app


def test_diagnostic_export_excludes_source_profile_keys_and_paths(tmp_path, fixtures_dir):
    db = tmp_path / "private-library.db"
    ArchiveStore(db).import_directory(fixtures_dir)
    profiles = LLMProfileStore(get_app_paths(tmp_path).llm_profiles_path)
    profile = profiles.create(
        ProfileInput(
            name="PRIVATE-PROFILE-NAME",
            provider="openai-compatible",
            base_url="https://private-provider.invalid/v1",
            default_model="PRIVATE-MODEL",
            keys=(KeyInput(label="PRIVATE-KEY-LABEL", api_key="SYNTHETIC-SECRET-KEY"),),
        )
    )
    with TestClient(create_app(db, data_dir=tmp_path)) as client:
        report = client.get("/api/diagnostics/export")
        assert report.status_code == 200
        assert report.json()["counts"]["conversations"] == 4
        assert report.json()["context_schema_version"] == CONTEXT_SCHEMA_VERSION
        assert "attachment" in report.headers["content-disposition"]
        for private in (
            profile.id,
            "PRIVATE-PROFILE-NAME",
            "private-provider.invalid",
            "PRIVATE-MODEL",
            "PRIVATE-KEY-LABEL",
            "SYNTHETIC-SECRET-KEY",
            str(tmp_path),
            db.name,
            "Obsidian",
        ):
            assert private not in report.text
