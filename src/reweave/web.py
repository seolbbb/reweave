"""FastAPI backend for the local search app."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, SecretStr

from reweave.archive import ArchiveStore, ImportSummary
from reweave.insights import generate_insight_report
from reweave.llm import (
    LLMSettings,
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderPermissionError,
    ProviderRateLimitError,
    ProviderRequestError,
    create_failover_provider,
    discover_available_models,
)
from reweave.llm_profiles import (
    KeyInput,
    LLMKeyCredential,
    LLMKeyRef,
    LLMProfile,
    LLMProfileStore,
    ProfileInput,
    ensure_default_profiles,
)
from reweave.paths import get_app_paths

UPLOAD_FILES = File(...)


class ImportRequest(BaseModel):
    input_dir: str


class ImportPathRequest(BaseModel):
    path: str


class LLMSettingsRequest(BaseModel):
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    api_key: SecretStr = SecretStr("")
    base_url: str = ""
    profile_id: str | None = None
    max_context_chars: int = Field(default=80_000, ge=10_000)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)


class InsightRequest(BaseModel):
    conversation_ids: list[str]
    title: str = "Connected Insights"
    settings: LLMSettingsRequest


class LLMKeyRequest(BaseModel):
    label: str
    api_key: SecretStr | None = None
    enabled: bool = True
    priority: int = 0


class LLMProfileRequest(BaseModel):
    name: str
    provider: str
    base_url: str = ""
    default_model: str = ""
    custom_models: list[str] = Field(default_factory=list)


class ActiveProfileRequest(BaseModel):
    profile_id: str | None = None


class LLMConnectRequest(BaseModel):
    api_key: SecretStr
    base_url: str = ""
    custom_models: list[str] = Field(default_factory=list)


class LLMModelRequest(BaseModel):
    model: str


def create_app(
    db_path: Path,
    static_dir: Path | None = None,
    data_dir: Path | None = None,
) -> FastAPI:
    """Create the FastAPI app."""
    app = FastAPI(title="Reweave")
    store = ArchiveStore(db_path)
    app_paths = get_app_paths(data_dir)
    profile_store = LLMProfileStore(app_paths.llm_profiles_path)
    ensure_default_profiles(profile_store)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/paths")
    def paths() -> dict[str, str]:
        return {
            "data_dir": str(app_paths.data_dir),
            "db_path": str(db_path),
            "imports_dir": str(app_paths.imports_dir),
            "extracted_dir": str(app_paths.extracted_dir),
        }

    @app.get("/api/facets")
    def facets() -> dict[str, Any]:
        stats = store.stats()
        return {
            "sources": [
                {
                    "source": row.source,
                    "conversations": row.conversations,
                    "messages": row.messages,
                }
                for row in stats.by_source
            ]
        }

    @app.get("/api/search")
    def search(
        q: str,
        provider: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        title: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        results = store.search_conversations(
            q,
            provider=provider,
            date_from=date_from,
            date_to=date_to,
            title=title,
            limit=limit,
        )
        return {"results": [_conversation_search_result_to_dict(result) for result in results]}

    @app.get("/api/conversations/{conversation_id}")
    def conversation_detail(conversation_id: str) -> dict[str, Any]:
        conversation = store.get_conversation(conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        messages = store.get_messages(conversation_id)
        return {
            "conversation": conversation.__dict__,
            "messages": [message.__dict__ for message in messages],
        }

    @app.post("/api/import")
    def import_directory(request: ImportRequest) -> dict[str, Any]:
        try:
            summary = store.import_path(
                Path(request.input_dir),
                extraction_root=app_paths.extracted_dir,
            )
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _import_summary_to_dict(summary)

    @app.post("/api/import/path")
    def import_path(request: ImportPathRequest) -> dict[str, Any]:
        try:
            summary = store.import_path(
                Path(request.path),
                extraction_root=app_paths.extracted_dir,
            )
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _import_summary_to_dict(summary)

    @app.post("/api/import/upload")
    def import_upload(files: list[UploadFile] = UPLOAD_FILES) -> dict[str, Any]:
        if not files:
            raise HTTPException(status_code=400, detail="No files uploaded.")

        summaries: list[ImportSummary] = []
        for upload in files:
            filename = _safe_upload_name(upload.filename)
            target_path = app_paths.imports_dir / f"{uuid4().hex}-{filename}"
            with open(target_path, "wb") as destination:
                shutil.copyfileobj(upload.file, destination)
            try:
                summaries.append(
                    store.import_path(target_path, extraction_root=app_paths.extracted_dir)
                )
            except (OSError, ValueError) as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        return _import_summary_to_dict(_merge_import_summaries(summaries))

    @app.get("/api/llm/profiles")
    def list_llm_profiles() -> dict[str, Any]:
        stored = profile_store.list()
        return {
            "active_profile_id": stored.active_profile_id,
            "profiles": [
                _llm_profile_to_dict(profile, profile_store)
                for profile in stored.profiles
            ],
        }

    @app.post("/api/llm/profiles")
    def create_llm_profile(request: LLMProfileRequest) -> dict[str, Any]:
        profile = profile_store.create(
            ProfileInput(
                name=request.name,
                provider=request.provider,
                base_url=request.base_url,
                default_model=request.default_model,
                custom_models=tuple(request.custom_models),
            )
        )
        return _llm_profile_to_dict(profile, profile_store)

    @app.put("/api/llm/profiles/{profile_id}")
    def update_llm_profile(profile_id: str, request: LLMProfileRequest) -> dict[str, Any]:
        try:
            profile = profile_store.update(
                profile_id,
                ProfileInput(
                    name=request.name,
                    provider=request.provider,
                    base_url=request.base_url,
                    default_model=request.default_model,
                    custom_models=tuple(request.custom_models),
                ),
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _llm_profile_to_dict(profile, profile_store)

    @app.delete("/api/llm/profiles/{profile_id}")
    def delete_llm_profile(profile_id: str) -> dict[str, str]:
        try:
            profile_store.delete(profile_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"status": "deleted"}

    @app.post("/api/llm/profiles/active")
    def set_active_llm_profile(request: ActiveProfileRequest) -> dict[str, Any]:
        try:
            profile_store.set_active(request.profile_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        stored = profile_store.list()
        return {"active_profile_id": stored.active_profile_id}

    @app.get("/api/llm/profiles/{profile_id}/models")
    def list_llm_profile_models(profile_id: str) -> dict[str, Any]:
        profile = profile_store.get(profile_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="LLM profile not found.")
        settings = LLMSettings(
            provider=profile.provider,
            model=profile.default_model,
            api_key="",
            base_url=profile.base_url,
        )
        try:
            result = discover_available_models(
                settings,
                profile_store.credentials_for(profile.id),
            )
        except ProviderAuthenticationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except ProviderPermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ProviderRateLimitError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        except ProviderConfigurationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ProviderRequestError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {
            "models": _merge_models(result.models, profile.custom_models),
            "validated_key_label": result.credential_label,
        }

    @app.post("/api/llm/profiles/{profile_id}/connect")
    def connect_llm_profile(profile_id: str, request: LLMConnectRequest) -> dict[str, Any]:
        profile = profile_store.get(profile_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="LLM profile not found.")
        api_key = request.api_key.get_secret_value().strip()
        if not api_key:
            raise HTTPException(status_code=400, detail="Enter an API key to connect.")

        custom_models = tuple(
            dict.fromkeys(model.strip() for model in request.custom_models if model.strip())
        )
        settings = LLMSettings(
            provider=profile.provider,
            model=profile.default_model,
            api_key="",
            base_url=request.base_url.strip(),
        )
        pending_key = LLMKeyCredential(
            key_id="pending",
            label="Primary key",
            api_key=api_key,
        )
        try:
            result = discover_available_models(settings, (pending_key,))
        except ProviderAuthenticationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except ProviderPermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ProviderRateLimitError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        except ProviderConfigurationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ProviderRequestError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        models = _merge_models(result.models, custom_models)
        selected_model = _select_default_model(profile.provider, profile.default_model, models)
        updated_profile = profile_store.update(
            profile_id,
            ProfileInput(
                name=profile.name,
                provider=profile.provider,
                base_url=request.base_url,
                default_model=selected_model,
                custom_models=custom_models,
            ),
        )
        profile_store.replace_keys(
            profile_id,
            KeyInput(label="Primary key", api_key=api_key, enabled=True, priority=0),
        )
        profile_store.set_active(profile_id)
        connected_profile = profile_store.get(profile_id) or updated_profile
        return {
            "profile": _llm_profile_to_dict(connected_profile, profile_store),
            "models": models,
            "selected_model": selected_model,
        }

    @app.delete("/api/llm/profiles/{profile_id}/connection")
    def disconnect_llm_profile(profile_id: str) -> dict[str, str]:
        try:
            profile_store.clear_keys(profile_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"status": "disconnected"}

    @app.put("/api/llm/profiles/{profile_id}/model")
    def select_llm_profile_model(profile_id: str, request: LLMModelRequest) -> dict[str, Any]:
        profile = profile_store.get(profile_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="LLM profile not found.")
        model = request.model.strip()
        if not model:
            raise HTTPException(status_code=400, detail="Choose a model.")
        updated = profile_store.update(
            profile_id,
            ProfileInput(
                name=profile.name,
                provider=profile.provider,
                base_url=profile.base_url,
                default_model=model,
                custom_models=profile.custom_models,
            ),
        )
        return _llm_profile_to_dict(updated, profile_store)

    @app.post("/api/llm/profiles/{profile_id}/keys")
    def add_llm_profile_key(profile_id: str, request: LLMKeyRequest) -> dict[str, Any]:
        try:
            key_ref = profile_store.add_key(
                profile_id,
                KeyInput(
                    label=request.label,
                    api_key=(
                        request.api_key.get_secret_value()
                        if request.api_key is not None
                        else None
                    ),
                    enabled=request.enabled,
                    priority=request.priority,
                ),
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _llm_key_to_dict(key_ref, profile_id, profile_store)

    @app.put("/api/llm/profiles/{profile_id}/keys/{key_id}")
    def update_llm_profile_key(
        profile_id: str,
        key_id: str,
        request: LLMKeyRequest,
    ) -> dict[str, Any]:
        try:
            key_ref = profile_store.update_key(
                profile_id,
                key_id,
                KeyInput(
                    label=request.label,
                    api_key=(
                        request.api_key.get_secret_value()
                        if request.api_key is not None
                        else None
                    ),
                    enabled=request.enabled,
                    priority=request.priority,
                ),
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _llm_key_to_dict(key_ref, profile_id, profile_store)

    @app.delete("/api/llm/profiles/{profile_id}/keys/{key_id}")
    def delete_llm_profile_key(profile_id: str, key_id: str) -> dict[str, str]:
        try:
            profile_store.delete_key(profile_id, key_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"status": "deleted"}

    @app.post("/api/insights")
    def create_insight(request: InsightRequest) -> dict[str, Any]:
        try:
            settings, provider = _resolve_llm_settings(request.settings, profile_store)
            report = generate_insight_report(
                store,
                conversation_ids=request.conversation_ids,
                title=request.title,
                settings=settings,
                provider=provider,
            )
        except ProviderConfigurationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ProviderRequestError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=exc.__class__.__name__) from exc
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _insight_report_to_dict(report)

    @app.get("/api/insights")
    def list_insights() -> dict[str, Any]:
        return {
            "results": [
                _insight_report_summary_to_dict(report) for report in store.list_insight_reports()
            ]
        }

    @app.get("/api/insights/{report_id}")
    def get_insight(report_id: str) -> dict[str, Any]:
        report = store.get_insight_report(report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="Insight report not found.")
        return _insight_report_to_dict(report)

    if static_dir and static_dir.exists():
        assets_dir = static_dir / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(static_dir / "index.html")

        @app.get("/{path:path}")
        def spa_fallback(path: str) -> FileResponse:
            target = static_dir / path
            if target.exists() and target.is_file():
                return FileResponse(target)
            return FileResponse(static_dir / "index.html")

    return app


def _conversation_search_result_to_dict(result) -> dict[str, Any]:
    return {
        "id": result.id,
        "source": result.source,
        "title": result.title,
        "created_at": result.created_at,
        "updated_at": result.updated_at,
        "raw_message_count": result.raw_message_count,
        "match_count": result.match_count,
        "excerpts": [excerpt.__dict__ for excerpt in result.excerpts],
    }


def _import_summary_to_dict(summary: ImportSummary) -> dict[str, Any]:
    return {
        "parsed_conversations": summary.parsed_conversations,
        "inserted_conversations": summary.inserted_conversations,
        "inserted_messages": summary.inserted_messages,
        "skipped_files": [str(path) for path in summary.skipped_files],
    }


def _merge_import_summaries(summaries: list[ImportSummary]) -> ImportSummary:
    return ImportSummary(
        parsed_conversations=sum(summary.parsed_conversations for summary in summaries),
        inserted_conversations=sum(summary.inserted_conversations for summary in summaries),
        inserted_messages=sum(summary.inserted_messages for summary in summaries),
        skipped_files=tuple(
            path for summary in summaries for path in summary.skipped_files
        ),
    )


def _safe_upload_name(filename: str | None) -> str:
    name = Path(filename or "upload").name
    sanitized = "".join(char if char.isalnum() or char in "._-" else "_" for char in name)
    return sanitized or "upload"


def _resolve_llm_settings(
    request: LLMSettingsRequest,
    profile_store: LLMProfileStore,
) -> tuple[LLMSettings, Any]:
    if not request.profile_id:
        return (
            LLMSettings(
                provider=request.provider,
                model=request.model,
                api_key=request.api_key.get_secret_value(),
                base_url=request.base_url,
                max_context_chars=request.max_context_chars,
                temperature=request.temperature,
            ),
            None,
        )

    profile = profile_store.get(request.profile_id)
    if profile is None:
        raise ProviderConfigurationError("LLM profile not found.")

    model = request.model or profile.default_model
    if not model:
        raise ProviderConfigurationError("Model is required.")
    settings = LLMSettings(
        provider=profile.provider,
        model=model,
        api_key="",
        base_url=profile.base_url,
        max_context_chars=request.max_context_chars,
        temperature=request.temperature,
    )
    credentials = profile_store.credentials_for(profile.id)
    return settings, create_failover_provider(settings, credentials)


def _llm_profile_to_dict(profile: LLMProfile, store: LLMProfileStore) -> dict[str, Any]:
    connected = any(store.has_secret(profile.id, key.id) for key in profile.keys if key.enabled)
    return {
        "id": profile.id,
        "name": profile.name,
        "provider": profile.provider,
        "base_url": profile.base_url,
        "default_model": profile.default_model,
        "custom_models": list(profile.custom_models),
        "keys": [_llm_key_to_dict(key, profile.id, store) for key in profile.keys],
        "connected": connected,
        "masked_key": "************" if connected else "",
    }


def _llm_key_to_dict(
    key_ref: LLMKeyRef,
    profile_id: str,
    store: LLMProfileStore,
) -> dict[str, Any]:
    return {
        "id": key_ref.id,
        "label": key_ref.label,
        "enabled": key_ref.enabled,
        "priority": key_ref.priority,
        "has_secret": store.has_secret(profile_id, key_ref.id),
    }


def _merge_models(provider_models, custom_models) -> list[str]:
    return list(dict.fromkeys([*provider_models, *custom_models]))


def _select_default_model(provider: str, current: str, models: list[str]) -> str:
    if current in models:
        return current
    preferences = {
        "openai": ("mini",),
        "anthropic": ("sonnet",),
        "gemini": ("flash",),
    }
    excluded = ("audio", "embedding", "image", "realtime", "transcribe", "tts")
    usable = [model for model in models if not any(term in model.casefold() for term in excluded)]
    for preference in preferences.get(provider, ()):
        if match := next(
            (model for model in usable if preference in model.casefold()),
            None,
        ):
            return match
    return usable[0] if usable else (models[0] if models else "")


def _insight_report_summary_to_dict(report) -> dict[str, Any]:
    return {
        "id": report.id,
        "title": report.title,
        "selected_conversation_ids": list(report.selected_conversation_ids),
        "provider": report.provider,
        "model": report.model,
        "created_at": report.created_at,
    }


def _insight_report_to_dict(report) -> dict[str, Any]:
    data = _insight_report_summary_to_dict(report)
    data["markdown"] = report.markdown
    return data
