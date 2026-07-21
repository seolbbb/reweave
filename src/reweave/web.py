"""FastAPI backend for the local search app."""

from __future__ import annotations

import json
import secrets
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any, Literal
from uuid import uuid4

import httpx
from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from reweave.archive import ArchiveStore, ImportSummary
from reweave.archive_answers import answer_archive
from reweave.archive_management import ArchiveManager
from reweave.context_assembly import (
    AllowedScope,
    ContextAssemblyInput,
    ContextAssemblyResult,
    ContextUnavailableError,
    CurrentChatMessage,
    assemble_context,
)
from reweave.context_extraction import (
    ContextExtractionResult,
    conversation_source_fingerprint,
    extract_context_from_conversation,
)
from reweave.context_library import (
    ContextAnalysisQueueJob,
    ContextItem,
    ContextLibraryStore,
    ConversationBrief,
)
from reweave.conversation_capture import ConversationCapture
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
from reweave.memory_audits import (
    AuditEvidence,
    AuditSession,
    MemoryAuditStore,
    classify_memory_claim,
    extract_memory_claims,
    suggest_audit_evidence,
)
from reweave.paths import get_app_paths
from reweave.semantic import SearchEngine, SemanticIndex, SemanticUnavailableError

UPLOAD_FILES = File(...)
UPLOAD_BACKUP = File(...)
BRIDGE_TOKEN_HEADER = Header(default=None, alias="X-Reweave-Bridge-Token")


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


class ContextAnalysisRequest(BaseModel):
    conversation_id: str = Field(min_length=1)
    analysis_mode: Literal["auto", "project", "learning", "research_writing", "context_handoff"] = (
        "auto"
    )
    settings: LLMSettingsRequest


class ContextAnalysisQueueRetryRequest(BaseModel):
    settings: LLMSettingsRequest = Field(default_factory=LLMSettingsRequest)


class CurrentChatMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=50_000)

    @field_validator("content")
    @classmethod
    def require_visible_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Current-chat message content cannot be blank.")
        return value


class AllowedContextScopeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope_type: Literal["core_self", "personal", "work", "project", "topic", "destination"]
    scope_key: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def normalize_scope(self) -> AllowedContextScopeRequest:
        self.scope_key = self.scope_key.strip()
        if self.scope_type in {"project", "topic", "destination"} and not self.scope_key:
            raise ValueError(f"{self.scope_type} scope requires a scope key.")
        if self.scope_type in {"core_self", "personal", "work"} and self.scope_key:
            raise ValueError(f"{self.scope_type} scope cannot have a scope key.")
        return self


class ContextAssemblyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["chatgpt", "claude"]
    external_id: str = Field(min_length=1, max_length=512)
    messages: list[CurrentChatMessageRequest] = Field(default_factory=list, max_length=500)
    draft: str = Field(min_length=1, max_length=20_000)
    destination: Literal["private", "work", "client", "shared"]
    allowed_scopes: list[AllowedContextScopeRequest] = Field(default_factory=list, max_length=25)
    max_context_chars: int = Field(default=6_000, ge=512, le=20_000)

    @field_validator("external_id", "draft")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Current-chat identity and draft cannot be blank.")
        return normalized

    @model_validator(mode="after")
    def validate_bounds_and_scope(self) -> ContextAssemblyRequest:
        if sum(len(message.content) for message in self.messages) > 200_000:
            raise ValueError("Current-chat content exceeds 200000 characters.")
        if self.messages and any(
            message.role != ("user" if index % 2 == 0 else "assistant")
            for index, message in enumerate(self.messages)
        ):
            raise ValueError("Current-chat messages must contain complete user-assistant turns.")
        if self.messages and self.messages[-1].role != "assistant":
            raise ValueError("Current-chat messages must end with a complete assistant response.")
        scope_keys = [(scope.scope_type, scope.scope_key) for scope in self.allowed_scopes]
        if len(scope_keys) != len(set(scope_keys)):
            raise ValueError("Allowed Context scopes must be unique.")
        if not self.allowed_scopes and self.destination != "private":
            raise ValueError("Non-private destinations require an explicit allowed Context scope.")
        destination_scope_types = {
            "private": {"core_self", "personal", "work", "project", "topic", "destination"},
            "work": {"core_self", "work", "project", "topic", "destination"},
            "client": {"core_self", "project", "topic", "destination"},
            "shared": {"core_self", "project", "topic", "destination"},
        }
        if any(
            scope.scope_type not in destination_scope_types[self.destination]
            for scope in self.allowed_scopes
        ):
            raise ValueError("An allowed Context scope is unsafe for this destination.")
        return self


class SemanticIndexRequest(BaseModel):
    rebuild: bool = False


class ArchiveAnswerRequest(BaseModel):
    question: str
    mode: str = "auto"
    provider: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    title: str | None = None
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


class MemoryAuditExtractRequest(BaseModel):
    assistant_source: Literal["chatgpt", "claude"] = "chatgpt"
    raw_text: str = Field(min_length=1, max_length=50_000)
    settings: LLMSettingsRequest


class MemoryAuditClaimInput(BaseModel):
    claim_text: str = Field(min_length=1, max_length=5_000)
    llm_statement_kind: str = ""
    llm_evidence_verdict: str = ""
    llm_issue_tags: list[str] = Field(default_factory=list)
    llm_severity: str = ""
    llm_rationale: str = ""
    search_queries: list[str] = Field(default_factory=list)


class MemoryAuditCreateRequest(BaseModel):
    assistant_source: Literal["chatgpt", "claude"] = "chatgpt"
    items: list[MemoryAuditClaimInput] = Field(min_length=1, max_length=100)


class MemoryAuditEvidenceInput(BaseModel):
    conversation_id: str
    message_id: str
    message_index: int
    relationship: Literal["supports", "contradicts", "context"]


class MemoryAuditItemUpdateRequest(BaseModel):
    statement_kind: Literal["direct_statement", "model_inference", "unclear"]
    evidence_verdict: Literal[
        "supported", "contradicted", "mixed", "not_found", "unclear"
    ]
    issue_tags: list[str] = Field(default_factory=list)
    severity: Literal["low", "medium", "high", "unclear"]
    redacted_example: str = Field(default="", max_length=2_000)
    notes: str = Field(default="", max_length=5_000)
    evidence: list[MemoryAuditEvidenceInput] = Field(default_factory=list, max_length=20)


class MemoryAuditEvidenceRequest(BaseModel):
    all_sources: bool = False
    settings: LLMSettingsRequest | None = None


class MemoryAuditSessionUpdateRequest(BaseModel):
    status: Literal["completed"]
    provenance_understood: bool = False


def create_app(
    db_path: Path,
    static_dir: Path | None = None,
    data_dir: Path | None = None,
    extension_bridge_token: str | None = None,
) -> FastAPI:
    """Create the FastAPI app."""
    app = FastAPI(title="Reweave")
    store = ArchiveStore(db_path)
    context_library = ContextLibraryStore(db_path)
    context_library.recover_interrupted_analysis_jobs()
    app.state.context_library = context_library
    archive_manager = ArchiveManager(db_path)
    app_paths = get_app_paths(data_dir)
    profile_store = LLMProfileStore(app_paths.llm_profiles_path)
    ensure_default_profiles(profile_store)
    semantic_index = SemanticIndex(db_path, app_paths.models_dir)
    search_engine = SearchEngine(store, semantic_index)
    memory_audit_store = MemoryAuditStore(app_paths.memory_audit_db_path)
    insight_jobs: dict[str, dict[str, Any]] = {}
    insight_jobs_lock = Lock()
    insight_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="reweave-job")
    semantic_jobs: dict[str, dict[str, Any]] = {}
    semantic_jobs_lock = Lock()
    semantic_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="reweave-index")
    answer_jobs: dict[str, dict[str, Any]] = {}
    answer_jobs_lock = Lock()
    answer_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="reweave-answer")
    context_jobs: dict[str, dict[str, Any]] = {}
    context_jobs_lock = Lock()
    context_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="reweave-context")

    def update_insight_job(job_id: str, **changes: Any) -> None:
        with insight_jobs_lock:
            insight_jobs[job_id].update(changes)

    def update_semantic_job(job_id: str, **changes: Any) -> None:
        with semantic_jobs_lock:
            semantic_jobs[job_id].update(changes)

    def update_answer_job(job_id: str, **changes: Any) -> None:
        with answer_jobs_lock:
            answer_jobs[job_id].update(changes)

    def update_context_job(job_id: str, **changes: Any) -> None:
        with context_jobs_lock:
            context_jobs[job_id].update(changes)

    def require_extension_bridge_token(provided_token: str | None) -> None:
        if extension_bridge_token is None:
            raise HTTPException(status_code=503, detail="The extension bridge is not active.")
        if provided_token is None or not secrets.compare_digest(
            provided_token.encode("utf-8"),
            extension_bridge_token.encode("utf-8"),
        ):
            raise HTTPException(status_code=403, detail="The extension bridge token is invalid.")

    def run_insight_job(
        job_id: str,
        request: InsightRequest,
        settings: LLMSettings,
        provider: Any,
    ) -> None:
        metrics: dict[str, Any] = {}

        def report_progress(stage: str, message: str, completed: int, total: int) -> None:
            update_insight_job(
                job_id,
                status="running",
                stage=stage,
                message=message,
                progress=_insight_job_progress(stage, completed, total),
            )

        try:
            report = generate_insight_report(
                store,
                conversation_ids=request.conversation_ids,
                title=request.title,
                settings=settings,
                provider=provider,
                progress=report_progress,
                metrics=metrics,
            )
        except (
            ProviderConfigurationError,
            ProviderRequestError,
            httpx.HTTPError,
            ValueError,
        ) as exc:
            update_insight_job(
                job_id,
                status="failed",
                stage="failed",
                message=_insight_job_error(exc),
                error=_insight_job_error(exc),
            )
            return

        result = _insight_report_to_dict(report)
        result["language"] = metrics.get("language", "en")
        result["performance"] = metrics
        update_insight_job(
            job_id,
            status="completed",
            stage="complete",
            message="Insight report ready",
            progress=100,
            result=result,
        )

    def run_semantic_job(job_id: str, rebuild: bool) -> None:
        def report_progress(stage: str, completed: int, total: int) -> None:
            progress = 100 if stage == "complete" else round(5 + 90 * completed / max(total, 1))
            update_semantic_job(
                job_id,
                status="completed" if stage == "complete" else "running",
                stage=stage,
                message=(
                    "Smart search is ready"
                    if stage == "complete"
                    else f"Indexed {completed} of {total} source chunks"
                ),
                progress=progress,
            )

        try:
            status = semantic_index.build(rebuild=rebuild, progress=report_progress)
        except Exception as exc:  # Background job must report model and network failures.
            update_semantic_job(
                job_id,
                status="failed",
                stage="failed",
                message=str(exc),
                error=str(exc),
            )
            return
        update_semantic_job(
            job_id,
            status="completed",
            stage="complete",
            message="Smart search is ready",
            progress=100,
            result=status.to_dict(),
        )

    def run_answer_job(
        job_id: str,
        request: ArchiveAnswerRequest,
        settings: LLMSettings,
        llm_provider: Any,
    ) -> None:
        def report_progress(stage: str, message: str, completed: int, total: int) -> None:
            stage_progress = {
                "searching": 10,
                "preparing": 30,
                "answering": 55,
                "validating": 85,
                "complete": 100,
            }
            update_answer_job(
                job_id,
                status="completed" if stage == "complete" else "running",
                stage=stage,
                message=message,
                progress=stage_progress.get(stage, 5),
            )

        try:
            answer = answer_archive(
                store,
                search_engine,
                question=request.question,
                settings=settings,
                mode=request.mode,
                provider_filter=request.provider,
                date_from=request.date_from,
                date_to=request.date_to,
                title=request.title,
                provider=llm_provider,
                progress=report_progress,
            )
        except (
            ProviderConfigurationError,
            ProviderRequestError,
            SemanticUnavailableError,
            httpx.HTTPError,
            ValueError,
        ) as exc:
            update_answer_job(
                job_id,
                status="failed",
                stage="failed",
                message=_insight_job_error(exc),
                error=_insight_job_error(exc),
            )
            return
        update_answer_job(
            job_id,
            status="completed",
            stage="complete",
            message="Archive answer ready",
            progress=100,
            result={
                "question": answer.question,
                "markdown": answer.markdown,
                "mode_used": answer.mode_used,
                "language": answer.language,
                "sources": [source.__dict__ for source in answer.sources],
            },
        )

    def run_context_job(
        job_id: str,
        request: ContextAnalysisRequest,
        settings: LLMSettings,
        provider: Any,
    ) -> None:
        update_context_job(
            job_id,
            status="running",
            stage="analyzing",
            message="Analyzing the selected conversation",
            progress=25,
        )
        try:
            result = extract_context_from_conversation(
                store,
                context_library,
                conversation_id=request.conversation_id,
                settings=settings,
                analysis_mode=request.analysis_mode,
                provider=provider,
            )
        except Exception as exc:  # Background failures must always reach a terminal state.
            error = _context_job_error(exc)
            update_context_job(
                job_id,
                status="failed",
                stage="failed",
                message=error,
                error=error,
            )
            return
        update_context_job(
            job_id,
            status="completed",
            stage="complete",
            message="Conversation context ready",
            progress=100,
            result=_context_extraction_result_to_dict(result),
        )

    def run_queued_context_analysis(
        job_id: str,
        settings: LLMSettings,
        provider: Any,
    ) -> None:
        job = context_library.get_analysis_queue_job(job_id)
        if job is None or job.status != "running":
            return
        try:
            current_fingerprint = conversation_source_fingerprint(store, job.source_record_id)
            if current_fingerprint != job.source_fingerprint:
                context_library.supersede_analysis_queue_job(job_id)
                return
            result = extract_context_from_conversation(
                store,
                context_library,
                conversation_id=job.source_record_id,
                settings=settings,
                analysis_mode=job.analysis_mode,
                provider=provider,
            )
            current_job = context_library.get_analysis_queue_job(job_id)
            if current_job is not None and current_job.status == "running":
                context_library.complete_analysis_queue_job(
                    job_id,
                    brief_id=result.brief.id,
                )
        except Exception as exc:  # Durable jobs must always reach a terminal retryable state.
            current_job = context_library.get_analysis_queue_job(job_id)
            if current_job is not None and current_job.status == "running":
                error_code, error_summary = _context_queue_error(exc)
                context_library.fail_analysis_queue_job(
                    job_id,
                    error_code=error_code,
                    error_summary=error_summary,
                )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/paths")
    def paths() -> dict[str, str]:
        return {
            "data_dir": str(app_paths.data_dir),
            "db_path": str(db_path),
            "memory_audit_db_path": str(app_paths.memory_audit_db_path),
            "imports_dir": str(app_paths.imports_dir),
            "extracted_dir": str(app_paths.extracted_dir),
            "models_dir": str(app_paths.models_dir),
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

    @app.get("/api/library")
    def library(
        source: str | None = None,
        title: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        sort: str = "newest",
        offset: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        try:
            page = archive_manager.list_conversations(
                source=source,
                title=title,
                date_from=date_from,
                date_to=date_to,
                sort=sort,
                offset=offset,
                limit=limit,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "results": [result.__dict__ for result in page.results],
            "total": page.total,
            "offset": page.offset,
            "limit": page.limit,
        }

    @app.get("/api/search")
    def search(
        q: str,
        mode: str = "auto",
        provider: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        title: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        try:
            results, mode_used = search_engine.search_conversations(
                q,
                mode=mode,
                provider=provider,
                date_from=date_from,
                date_to=date_to,
                title=title,
                limit=limit,
            )
        except SemanticUnavailableError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "query": q,
            "mode_used": mode_used,
            "semantic_status": semantic_index.status().to_dict(),
            "results": [_conversation_search_result_to_dict(result) for result in results],
        }

    @app.post("/api/memory-audits/extract")
    def extract_memory_audit_items(request: MemoryAuditExtractRequest) -> dict[str, Any]:
        try:
            settings, llm_provider = _resolve_llm_settings(request.settings, profile_store)
            claims = extract_memory_claims(
                request.raw_text,
                assistant_source=request.assistant_source,
                settings=settings,
                provider=llm_provider,
            )
        except (
            ProviderConfigurationError,
            ProviderRequestError,
            httpx.HTTPError,
            ValueError,
        ) as exc:
            raise HTTPException(status_code=400, detail=_insight_job_error(exc)) from exc
        return {"items": claims}

    @app.get("/api/memory-audits")
    def list_memory_audits() -> dict[str, Any]:
        return {"results": memory_audit_store.list_sessions()}

    @app.post("/api/memory-audits", status_code=201)
    def create_memory_audit(request: MemoryAuditCreateRequest) -> dict[str, Any]:
        try:
            session = memory_audit_store.create_session(
                request.assistant_source,
                [item.model_dump() for item in request.items],
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _memory_audit_session_to_dict(session, store)

    @app.get("/api/memory-audits/{session_id}")
    def get_memory_audit(session_id: str) -> dict[str, Any]:
        session = memory_audit_store.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Memory-audit session not found.")
        return _memory_audit_session_to_dict(session, store)

    @app.patch("/api/memory-audits/{session_id}")
    def update_memory_audit_session(
        session_id: str,
        request: MemoryAuditSessionUpdateRequest,
    ) -> dict[str, Any]:
        try:
            session = memory_audit_store.complete_session(
                session_id,
                provenance_understood=request.provenance_understood,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _memory_audit_session_to_dict(session, store)

    @app.patch("/api/memory-audits/{session_id}/items/{item_id}")
    def update_memory_audit_item(
        session_id: str,
        item_id: str,
        request: MemoryAuditItemUpdateRequest,
    ) -> dict[str, Any]:
        item = memory_audit_store.get_item(item_id)
        if item is None or item.session_id != session_id:
            raise HTTPException(status_code=404, detail="Memory-audit item not found.")
        try:
            session = memory_audit_store.update_item(
                item_id,
                statement_kind=request.statement_kind,
                evidence_verdict=request.evidence_verdict,
                issue_tags=request.issue_tags,
                severity=request.severity,
                redacted_example=request.redacted_example,
                notes=request.notes,
                evidence=[evidence.model_dump() for evidence in request.evidence],
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _memory_audit_session_to_dict(session, store)

    @app.post("/api/memory-audits/{session_id}/items/{item_id}/evidence-suggestions")
    def get_memory_audit_evidence_suggestions(
        session_id: str,
        item_id: str,
        request: MemoryAuditEvidenceRequest,
    ) -> dict[str, Any]:
        item = memory_audit_store.get_item(item_id)
        session = memory_audit_store.get_session(session_id)
        if item is None or session is None or item.session_id != session_id:
            raise HTTPException(status_code=404, detail="Memory-audit item not found.")
        try:
            candidates, mode_used = suggest_audit_evidence(
                search_engine,
                item=item,
                assistant_source=session.assistant_source,
                all_sources=request.all_sources,
            )
        except (SemanticUnavailableError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        suggestion = None
        suggestion_error = None
        if request.settings is not None:
            try:
                settings, llm_provider = _resolve_llm_settings(request.settings, profile_store)
                suggestion = classify_memory_claim(
                    item,
                    candidates,
                    settings=settings,
                    provider=llm_provider,
                )
            except (
                ProviderConfigurationError,
                ProviderRequestError,
                httpx.HTTPError,
                ValueError,
            ) as exc:
                suggestion_error = _insight_job_error(exc)
        return {
            "mode_used": mode_used,
            "candidates": [candidate.__dict__ for candidate in candidates],
            "suggestion": suggestion,
            "suggestion_error": suggestion_error,
        }

    @app.get("/api/memory-audits/{session_id}/export")
    def export_memory_audit(
        session_id: str,
        format: Literal["json", "csv"] = "json",
    ) -> Response:
        try:
            if format == "csv":
                content = memory_audit_store.redacted_csv(session_id)
                media_type = "text/csv; charset=utf-8"
            else:
                content = json.dumps(
                    memory_audit_store.redacted_export(session_id),
                    ensure_ascii=False,
                    indent=2,
                )
                media_type = "application/json"
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        filename = f"memory-audit-{session_id[:8]}.{format}"
        return Response(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.delete("/api/memory-audits/{session_id}", status_code=204)
    def delete_memory_audit(session_id: str) -> Response:
        try:
            memory_audit_store.delete_session(session_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return Response(status_code=204)

    @app.get("/api/semantic/status")
    def semantic_status() -> dict[str, object]:
        return semantic_index.status().to_dict()

    @app.post("/api/semantic/index/jobs", status_code=202)
    def create_semantic_index_job(request: SemanticIndexRequest) -> dict[str, Any]:
        with semantic_jobs_lock:
            active = next(
                (job for job in semantic_jobs.values() if job["status"] in {"queued", "running"}),
                None,
            )
            if active is not None:
                return dict(active)
            job_id = uuid4().hex
            job = {
                "id": job_id,
                "status": "queued",
                "stage": "preparing",
                "message": "Preparing the local semantic model",
                "progress": 2,
                "created_at": datetime.now(tz=UTC).isoformat(),
                "result": None,
                "error": None,
            }
            semantic_jobs[job_id] = job
        semantic_executor.submit(run_semantic_job, job_id, request.rebuild)
        return dict(job)

    @app.get("/api/semantic/index/jobs/{job_id}")
    def get_semantic_index_job(job_id: str) -> dict[str, Any]:
        with semantic_jobs_lock:
            job = semantic_jobs.get(job_id)
            if job is None:
                raise HTTPException(status_code=404, detail="Semantic index job not found.")
            return dict(job)

    @app.delete("/api/semantic/index")
    def delete_semantic_index() -> dict[str, object]:
        semantic_index.delete_index()
        return semantic_index.status().to_dict()

    @app.delete("/api/semantic/model")
    def delete_semantic_model() -> dict[str, object]:
        semantic_index.delete_model()
        return semantic_index.status().to_dict()

    @app.post("/api/archive-answers/jobs", status_code=202)
    def create_archive_answer_job(request: ArchiveAnswerRequest) -> dict[str, Any]:
        try:
            settings, llm_provider = _resolve_llm_settings(request.settings, profile_store)
        except ProviderConfigurationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        job_id = uuid4().hex
        job = {
            "id": job_id,
            "status": "queued",
            "stage": "searching",
            "message": "Searching your local archive",
            "progress": 2,
            "created_at": datetime.now(tz=UTC).isoformat(),
            "result": None,
            "error": None,
        }
        with answer_jobs_lock:
            answer_jobs[job_id] = job
        answer_executor.submit(run_answer_job, job_id, request, settings, llm_provider)
        return dict(job)

    @app.get("/api/archive-answers/jobs/{job_id}")
    def get_archive_answer_job(job_id: str) -> dict[str, Any]:
        with answer_jobs_lock:
            job = answer_jobs.get(job_id)
            if job is None:
                raise HTTPException(status_code=404, detail="Archive answer job not found.")
            return dict(job)

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

    @app.delete("/api/conversations/{conversation_id}")
    def delete_conversation(conversation_id: str) -> dict[str, int]:
        try:
            summary = archive_manager.delete_conversation(conversation_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return summary.__dict__

    @app.delete("/api/archive/sources/{source}")
    def delete_archive_source(source: str) -> dict[str, int]:
        try:
            summary = archive_manager.delete_source(source)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return summary.__dict__

    @app.get("/api/archive/backup")
    def backup_archive() -> StreamingResponse:
        stamp = datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S")
        filename = f"reweave-backup-{stamp}.sqlite3"
        temporary_path = app_paths.data_dir / "backup-downloads" / f"{uuid4().hex}.sqlite3"
        archive_manager.backup_to(temporary_path)
        return StreamingResponse(
            _stream_file_and_remove(temporary_path),
            media_type="application/vnd.sqlite3",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.post("/api/archive/restore")
    def restore_archive(file: UploadFile = UPLOAD_BACKUP) -> dict[str, Any]:
        filename = _safe_upload_name(file.filename)
        if Path(filename).suffix.lower() not in {".db", ".sqlite", ".sqlite3"}:
            raise HTTPException(status_code=400, detail="Choose a Reweave SQLite backup file.")
        temporary_path = app_paths.imports_dir / f"restore-{uuid4().hex}-{filename}"
        with open(temporary_path, "wb") as destination:
            shutil.copyfileobj(file.file, destination)
        try:
            summary = archive_manager.restore_from(
                temporary_path,
                safety_backup_dir=app_paths.data_dir / "backups",
            )
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            temporary_path.unlink(missing_ok=True)
        return summary.__dict__

    @app.post("/api/import")
    def import_directory(request: ImportRequest) -> dict[str, Any]:
        try:
            summary = store.import_path(Path(request.input_dir))
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _import_summary_to_dict(summary)

    @app.post("/api/import/path")
    def import_path(request: ImportPathRequest) -> dict[str, Any]:
        try:
            summary = store.import_path(Path(request.path))
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
                summaries.append(store.import_path(target_path))
            except (OSError, ValueError) as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            finally:
                target_path.unlink(missing_ok=True)

        return _import_summary_to_dict(_merge_import_summaries(summaries))

    @app.post("/api/capture/conversations")
    def capture_conversation(
        request: ConversationCapture,
        x_reweave_bridge_token: str | None = BRIDGE_TOKEN_HEADER,
    ) -> dict[str, Any]:
        if extension_bridge_token is not None:
            require_extension_bridge_token(x_reweave_bridge_token)
        try:
            summary = store.capture_conversation(request.to_normalized())
            source_fingerprint = conversation_source_fingerprint(store, summary.conversation_id)
            queue_job, _ = context_library.enqueue_analysis(
                conversation_id=summary.conversation_id,
                source_fingerprint=source_fingerprint,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "conversation_id": summary.conversation_id,
            "provider": request.provider,
            "external_id": request.external_id,
            "outcome": summary.outcome,
            "message_count": len(request.messages),
            "inserted_messages": summary.inserted_messages,
            "updated_messages": summary.updated_messages,
            "invalidated_embeddings": summary.invalidated_embeddings,
            "analysis_queue_job": _context_analysis_queue_job_to_dict(queue_job),
        }

    @app.post("/api/extension/handshake")
    def extension_handshake(
        x_reweave_bridge_token: str | None = BRIDGE_TOKEN_HEADER,
    ) -> dict[str, Any]:
        require_extension_bridge_token(x_reweave_bridge_token)
        return {
            "status": "ready",
            "protocol_version": 1,
        }

    @app.post("/api/context/assembly")
    def create_context_assembly(
        request: ContextAssemblyRequest,
        x_reweave_bridge_token: str | None = BRIDGE_TOKEN_HEADER,
    ) -> dict[str, Any]:
        require_extension_bridge_token(x_reweave_bridge_token)
        assembly_request = ContextAssemblyInput(
            provider=request.provider,
            external_id=request.external_id,
            messages=tuple(
                CurrentChatMessage(role=message.role, content=message.content)
                for message in request.messages
            ),
            draft=request.draft,
            destination=request.destination,
            allowed_scopes=tuple(
                AllowedScope(scope_type=scope.scope_type, scope_key=scope.scope_key)
                for scope in request.allowed_scopes
            ),
            max_context_chars=request.max_context_chars,
        )
        try:
            result = assemble_context(context_library, assembly_request)
        except ContextUnavailableError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return _context_assembly_result_to_dict(result)

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
        base_url = request.base_url.strip()
        settings = LLMSettings(
            provider=profile.provider,
            model=profile.default_model,
            api_key="",
            base_url=base_url,
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
                base_url=base_url,
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

    @app.post("/api/context/analysis/jobs", status_code=202)
    def create_context_analysis_job(request: ContextAnalysisRequest) -> dict[str, Any]:
        if store.get_conversation(request.conversation_id) is None:
            raise HTTPException(status_code=404, detail="Archived conversation not found.")
        try:
            settings, provider = _resolve_llm_settings(request.settings, profile_store)
        except ProviderConfigurationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        job_id = uuid4().hex
        job = {
            "id": job_id,
            "conversation_id": request.conversation_id,
            "analysis_mode": request.analysis_mode,
            "status": "queued",
            "stage": "queued",
            "message": "Queued for Context analysis",
            "progress": 2,
            "created_at": datetime.now(tz=UTC).isoformat(),
            "result": None,
            "error": None,
        }
        with context_jobs_lock:
            context_jobs[job_id] = job
        response = dict(job)
        context_executor.submit(run_context_job, job_id, request, settings, provider)
        return response

    @app.get("/api/context/analysis/jobs/{job_id}")
    def get_context_analysis_job(job_id: str) -> dict[str, Any]:
        with context_jobs_lock:
            job = context_jobs.get(job_id)
            if job is None:
                raise HTTPException(status_code=404, detail="Context analysis job not found.")
            return dict(job)

    @app.get("/api/context/analysis/queue")
    def list_context_analysis_queue(
        status: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        try:
            jobs = context_library.list_analysis_queue_jobs(status=status, limit=limit)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"results": [_context_analysis_queue_job_to_dict(job) for job in jobs]}

    @app.get("/api/context/analysis/queue/{job_id}")
    def get_context_analysis_queue_job(job_id: str) -> dict[str, Any]:
        job = context_library.get_analysis_queue_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Context analysis queue job not found.")
        return _context_analysis_queue_job_to_dict(job)

    @app.post("/api/context/analysis/queue/{job_id}/retry", status_code=202)
    def retry_context_analysis_queue_job(
        job_id: str,
        request: ContextAnalysisQueueRetryRequest,
    ) -> dict[str, Any]:
        job = context_library.get_analysis_queue_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Context analysis queue job not found.")
        if job.status not in {"pending", "failed"}:
            raise HTTPException(
                status_code=409,
                detail="Context analysis queue job is not retryable.",
            )
        try:
            current_fingerprint = conversation_source_fingerprint(store, job.source_record_id)
        except (LookupError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if current_fingerprint != job.source_fingerprint:
            running_job = context_library.start_analysis_queue_job(job_id)
            context_library.supersede_analysis_queue_job(running_job.id)
            raise HTTPException(status_code=409, detail="A newer source version is available.")
        try:
            settings, provider = _resolve_llm_settings(request.settings, profile_store)
            running_job = context_library.start_analysis_queue_job(job_id)
        except ProviderConfigurationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        context_executor.submit(run_queued_context_analysis, running_job.id, settings, provider)
        return _context_analysis_queue_job_to_dict(running_job)

    @app.get("/api/context/briefs")
    def list_context_briefs(limit: int = 100) -> dict[str, Any]:
        return {
            "results": [
                _context_brief_to_dict(brief) for brief in context_library.list_briefs(limit=limit)
            ]
        }

    @app.get("/api/context/briefs/{brief_id}")
    def get_context_brief(brief_id: str) -> dict[str, Any]:
        brief = context_library.get_brief(brief_id)
        if brief is None:
            raise HTTPException(status_code=404, detail="Conversation Brief not found.")
        result = _context_brief_to_dict(brief)
        result["items"] = [
            _context_item_to_dict(item)
            for item_id in brief.context_item_ids
            if (item := context_library.get_item(item_id)) is not None
        ]
        return result

    @app.get("/api/context/items")
    def list_context_items(limit: int = 200) -> dict[str, Any]:
        return {
            "results": [
                _context_item_to_dict(item) for item in context_library.list_items(limit=limit)
            ]
        }

    @app.get("/api/context/items/{item_id}")
    def get_context_item(item_id: str) -> dict[str, Any]:
        item = context_library.get_item(item_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Context Item not found.")
        return _context_item_to_dict(item)

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

    @app.post("/api/insights/jobs", status_code=202)
    def create_insight_job(request: InsightRequest) -> dict[str, Any]:
        try:
            settings, provider = _resolve_llm_settings(request.settings, profile_store)
        except ProviderConfigurationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        job_id = uuid4().hex
        job = {
            "id": job_id,
            "status": "queued",
            "stage": "loading",
            "message": "Preparing selected conversations",
            "progress": 2,
            "created_at": datetime.now(tz=UTC).isoformat(),
            "result": None,
            "error": None,
        }
        with insight_jobs_lock:
            insight_jobs[job_id] = job
        insight_executor.submit(run_insight_job, job_id, request, settings, provider)
        return dict(job)

    @app.get("/api/insights/jobs/{job_id}")
    def get_insight_job(job_id: str) -> dict[str, Any]:
        with insight_jobs_lock:
            job = insight_jobs.get(job_id)
            if job is None:
                raise HTTPException(status_code=404, detail="Insight job not found.")
            return dict(job)

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


def _memory_audit_session_to_dict(
    session: AuditSession,
    archive_store: ArchiveStore,
) -> dict[str, Any]:
    source_cache: dict[str, tuple[Any, dict[str, Any]]] = {}
    items = []
    for item in session.items:
        evidence = [
            _memory_audit_evidence_to_dict(reference, archive_store, source_cache)
            for reference in item.evidence
        ]
        items.append(
            {
                "id": item.id,
                "session_id": item.session_id,
                "claim_text": item.claim_text,
                "llm_statement_kind": item.llm_statement_kind,
                "llm_evidence_verdict": item.llm_evidence_verdict,
                "llm_issue_tags": list(item.llm_issue_tags),
                "llm_severity": item.llm_severity,
                "llm_rationale": item.llm_rationale,
                "search_queries": list(item.search_queries),
                "user_statement_kind": item.user_statement_kind,
                "user_evidence_verdict": item.user_evidence_verdict,
                "user_issue_tags": list(item.user_issue_tags),
                "user_severity": item.user_severity,
                "redacted_example": item.redacted_example,
                "notes": item.notes,
                "evidence": evidence,
                "created_at": item.created_at,
                "updated_at": item.updated_at,
            }
        )
    reviewed_count = sum(
        bool(
            item.user_statement_kind
            and item.user_evidence_verdict
            and item.user_severity
        )
        for item in session.items
    )
    return {
        "id": session.id,
        "assistant_source": session.assistant_source,
        "status": session.status,
        "provenance_understood": session.provenance_understood,
        "first_discrepancy_at": session.first_discrepancy_at,
        "started_at": session.started_at,
        "completed_at": session.completed_at,
        "updated_at": session.updated_at,
        "item_count": len(session.items),
        "reviewed_count": reviewed_count,
        "discrepancy_count": sum(bool(item.user_issue_tags) for item in session.items),
        "items": items,
    }


def _memory_audit_evidence_to_dict(
    reference: AuditEvidence,
    archive_store: ArchiveStore,
    source_cache: dict[str, tuple[Any, dict[str, Any]]],
) -> dict[str, Any]:
    if reference.conversation_id not in source_cache:
        conversation = archive_store.get_conversation(reference.conversation_id)
        messages = (
            {
                message.id: message
                for message in archive_store.get_messages(reference.conversation_id)
            }
            if conversation is not None
            else {}
        )
        source_cache[reference.conversation_id] = (conversation, messages)
    conversation, messages = source_cache[reference.conversation_id]
    message = messages.get(reference.message_id)
    base = {
        "id": reference.id,
        "conversation_id": reference.conversation_id,
        "message_id": reference.message_id,
        "message_index": reference.message_index,
        "relationship": reference.relationship,
    }
    if conversation is None or message is None:
        return {**base, "available": False, "title": "Source unavailable", "excerpt": ""}
    compact = " ".join(message.content.split())
    return {
        **base,
        "available": True,
        "source": conversation.source,
        "title": conversation.title,
        "role": message.role,
        "timestamp": message.timestamp,
        "excerpt": compact if len(compact) <= 480 else f"{compact[:480].rstrip()}...",
    }


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


def _context_assembly_result_to_dict(result: ContextAssemblyResult) -> dict[str, Any]:
    return {
        "insertion_text": result.insertion_text,
        "context_chars": result.context_chars,
        "context_budget_chars": result.context_budget_chars,
        "truncated": result.truncated,
        "items": [
            {
                "item_id": item.item_id,
                "canonical_text": item.canonical_text,
                "item_type": item.item_type,
                "epistemic_kind": item.epistemic_kind,
                "confidence": item.confidence,
                "scopes": list(item.scopes),
                "score": item.score,
                "provenance": {
                    "provider": item.source_provider,
                    "title": item.source_title,
                    "message_index": item.source_message_index,
                },
            }
            for item in result.items
        ],
    }


def _context_brief_to_dict(brief: ConversationBrief) -> dict[str, Any]:
    return {
        "id": brief.id,
        "source_conversation_id": brief.source_conversation_id,
        "source_record_id": brief.source_record_id,
        "source_external_id": brief.source_external_id,
        "source_provider": brief.source_provider,
        "source_title": brief.source_title,
        "source_created_at": brief.source_created_at,
        "main_subject": brief.main_subject,
        "user_goal": brief.user_goal,
        "important_outcomes": list(brief.important_outcomes),
        "decisions": list(brief.decisions),
        "lessons": list(brief.lessons),
        "unresolved_questions": list(brief.unresolved_questions),
        "actions": list(brief.actions),
        "analysis_mode": brief.analysis_mode,
        "analysis_version": brief.analysis_version,
        "prompt_version": brief.prompt_version,
        "analysis_provider": brief.analysis_provider,
        "analysis_model": brief.analysis_model,
        "analysis_status": brief.analysis_status,
        "created_at": brief.created_at,
        "updated_at": brief.updated_at,
        "context_item_ids": list(brief.context_item_ids),
        "item_count": len(brief.context_item_ids),
    }


def _context_analysis_queue_job_to_dict(job: ContextAnalysisQueueJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "source_conversation_id": job.source_conversation_id,
        "source_record_id": job.source_record_id,
        "source_fingerprint": job.source_fingerprint,
        "analysis_mode": job.analysis_mode,
        "status": job.status,
        "attempt_count": job.attempt_count,
        "last_error_code": job.last_error_code,
        "last_error_summary": job.last_error_summary,
        "result_brief_id": job.result_brief_id,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "last_attempt_at": job.last_attempt_at,
        "completed_at": job.completed_at,
    }


def _context_item_to_dict(item: ContextItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "canonical_text": item.canonical_text,
        "item_type": item.item_type,
        "epistemic_kind": item.epistemic_kind,
        "confidence": item.confidence,
        "sensitivity": item.sensitivity,
        "status": item.status,
        "current_version": item.current_version,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "last_confirmed_at": item.last_confirmed_at,
        "stale_at": item.stale_at,
        "scopes": [
            {
                "scope_type": scope.scope_type,
                "scope_key": scope.scope_key,
                "confidence": scope.confidence,
                "created_at": scope.created_at,
            }
            for scope in item.scopes
        ],
        "evidence": [
            {
                "id": evidence.id,
                "source_conversation_id": evidence.source_conversation_id,
                "source_message_id": evidence.source_message_id,
                "source_record_id": evidence.source_record_id,
                "source_external_id": evidence.source_external_id,
                "source_message_record_id": evidence.source_message_record_id,
                "source_provider": evidence.source_provider,
                "source_title": evidence.source_title,
                "source_message_index": evidence.source_message_index,
                "source_role": evidence.source_role,
                "source_timestamp": evidence.source_timestamp,
                "excerpt": evidence.excerpt,
                "relationship": evidence.relationship,
                "source_available": bool(
                    evidence.source_conversation_id and evidence.source_message_id
                ),
                "created_at": evidence.created_at,
            }
            for evidence in item.evidence
        ],
        "versions": [
            {
                "version": version.version,
                "canonical_text": version.canonical_text,
                "item_type": version.item_type,
                "epistemic_kind": version.epistemic_kind,
                "confidence": version.confidence,
                "sensitivity": version.sensitivity,
                "status": version.status,
                "last_confirmed_at": version.last_confirmed_at,
                "stale_at": version.stale_at,
                "change_reason": version.change_reason,
                "created_at": version.created_at,
            }
            for version in item.versions
        ],
        "links": [
            {
                "source_item_id": link.source_item_id,
                "target_item_id": link.target_item_id,
                "relationship": link.relationship,
                "created_at": link.created_at,
            }
            for link in item.links
        ],
    }


def _context_extraction_result_to_dict(result: ContextExtractionResult) -> dict[str, Any]:
    return {
        "brief": _context_brief_to_dict(result.brief),
        "items": [_context_item_to_dict(item) for item in result.items],
        "analysis_version": result.analysis_version,
        "prompt_version": result.prompt_version,
        "reused_existing": result.reused_existing,
        "dropped_items": result.dropped_items,
        "deduplicated_items": result.deduplicated_items,
    }


def _import_summary_to_dict(summary: ImportSummary) -> dict[str, Any]:
    return {
        "parsed_conversations": summary.parsed_conversations,
        "inserted_conversations": summary.inserted_conversations,
        "updated_conversations": summary.updated_conversations,
        "inserted_messages": summary.inserted_messages,
        "updated_messages": summary.updated_messages,
        "invalidated_embeddings": summary.invalidated_embeddings,
        "skipped_files": [str(path) for path in summary.skipped_files],
    }


def _merge_import_summaries(summaries: list[ImportSummary]) -> ImportSummary:
    return ImportSummary(
        parsed_conversations=sum(summary.parsed_conversations for summary in summaries),
        inserted_conversations=sum(summary.inserted_conversations for summary in summaries),
        updated_conversations=sum(summary.updated_conversations for summary in summaries),
        inserted_messages=sum(summary.inserted_messages for summary in summaries),
        updated_messages=sum(summary.updated_messages for summary in summaries),
        invalidated_embeddings=sum(summary.invalidated_embeddings for summary in summaries),
        skipped_files=tuple(
            path for summary in summaries for path in summary.skipped_files
        ),
    )


def _safe_upload_name(filename: str | None) -> str:
    name = Path(filename or "upload").name
    sanitized = "".join(char if char.isalnum() or char in "._-" else "_" for char in name)
    return sanitized or "upload"


def _stream_file_and_remove(path: Path):
    try:
        with open(path, "rb") as file:
            while chunk := file.read(1024 * 1024):
                yield chunk
    finally:
        path.unlink(missing_ok=True)


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


def _insight_job_progress(stage: str, completed: int, total: int) -> int:
    if stage == "loading":
        return 5
    if stage == "preparing":
        return 15
    if stage == "analyzing":
        return 20 + round(55 * completed / max(total, 1))
    if stage == "synthesizing":
        return 82
    if stage == "saving":
        return 95
    if stage == "complete":
        return 100
    return 2


def _insight_job_error(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPError):
        return f"The model request failed ({exc.__class__.__name__})."
    return str(exc)


def _context_job_error(exc: Exception) -> str:
    if isinstance(
        exc,
        (
            ProviderConfigurationError,
            ProviderRequestError,
            httpx.HTTPError,
            LookupError,
            ValueError,
        ),
    ):
        return _insight_job_error(exc)
    return "Context analysis failed unexpectedly."


def _context_queue_error(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, ProviderAuthenticationError):
        return "provider_authentication", "Provider authentication failed."
    if isinstance(exc, ProviderPermissionError):
        return "provider_permission", "The provider denied this analysis request."
    if isinstance(exc, ProviderRateLimitError):
        return "provider_rate_limit", "The provider rate limit interrupted analysis."
    if isinstance(exc, ProviderConfigurationError):
        return "provider_configuration", "A connected provider is required for analysis."
    if isinstance(exc, (ProviderRequestError, httpx.HTTPError)):
        return "provider_request", "The provider request failed."
    if isinstance(exc, LookupError):
        return "source_unavailable", "The captured source is no longer available."
    if isinstance(exc, ValueError):
        return "invalid_analysis_result", "The provider returned an invalid analysis result."
    return "analysis_failed", "Context analysis failed unexpectedly."
