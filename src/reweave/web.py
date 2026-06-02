"""FastAPI backend for the local search app."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from reweave.archive import ArchiveStore, ImportSummary
from reweave.insights import generate_insight_report
from reweave.llm import LLMSettings, ProviderConfigurationError
from reweave.paths import get_app_paths

UPLOAD_FILES = File(...)


class ImportRequest(BaseModel):
    input_dir: str


class ImportPathRequest(BaseModel):
    path: str


class LLMSettingsRequest(BaseModel):
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    api_key: str = ""
    base_url: str = ""
    max_context_chars: int = Field(default=80_000, ge=10_000)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)


class InsightRequest(BaseModel):
    conversation_ids: list[str]
    title: str = "Connected Insights"
    settings: LLMSettingsRequest


def create_app(
    db_path: Path,
    static_dir: Path | None = None,
    data_dir: Path | None = None,
) -> FastAPI:
    """Create the FastAPI app."""
    app = FastAPI(title="Reweave")
    store = ArchiveStore(db_path)
    app_paths = get_app_paths(data_dir)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

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

    @app.post("/api/insights")
    def create_insight(request: InsightRequest) -> dict[str, Any]:
        settings = LLMSettings(**request.settings.model_dump())
        try:
            report = generate_insight_report(
                store,
                conversation_ids=request.conversation_ids,
                title=request.title,
                settings=settings,
            )
        except ProviderConfigurationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
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
