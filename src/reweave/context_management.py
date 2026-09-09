"""Explicit local correction and canonical-space management API."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from reweave.context_library import (
    ContextItem,
    ContextLibraryStore,
    ContextRevisionConflictError,
    ScopeInput,
)


class ScopeEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope_type: Literal["core_self", "personal", "work", "project", "topic", "destination"]
    scope_key: str = Field(default="", max_length=500)
    confidence: float = Field(default=1, ge=0, le=1)


class ItemCorrection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    change_reason: str = Field(min_length=1, max_length=2000)
    canonical_text: str | None = Field(default=None, min_length=1, max_length=12_000)
    item_type: str | None = None
    epistemic_kind: Literal["observed", "inferred", "suggested"] | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    sensitivity: Literal["normal", "sensitive"] | None = None
    status: Literal["active", "superseded", "stale", "archived"] | None = None
    scopes: list[ScopeEdit] | None = Field(default=None, min_length=1, max_length=25)
    inference_rationale: str | None = Field(default=None, max_length=4000)


class ItemUndo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)
    expected_version: int = Field(ge=1)


class SpaceRename(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=500)
    expected_revision: int = Field(ge=1)


class SpaceMerge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_id: str = Field(min_length=1, max_length=128)
    expected_source_revision: int = Field(ge=1)
    expected_target_revision: int = Field(ge=1)


def management_router(
    store: ContextLibraryStore,
    serialize_item: Callable[[ContextItem], dict[str, Any]],
) -> APIRouter:
    router = APIRouter(prefix="/api/context")

    def mutate(operation: Callable):
        try:
            return operation()
        except ContextRevisionConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.patch("/items/{item_id}")
    def correct_item(item_id: str, request: ItemCorrection):
        fields = request.model_dump(exclude_none=True, exclude={"scopes"})
        if request.scopes is not None:
            fields["scopes"] = tuple(ScopeInput(**scope.model_dump()) for scope in request.scopes)
        return mutate(
            lambda: serialize_item(store.revise_item(item_id, authority="user", **fields))
        )

    @router.post("/items/{item_id}/undo")
    def undo_item(item_id: str, request: ItemUndo):
        return mutate(lambda: serialize_item(store.undo_item(item_id, **request.model_dump())))

    @router.get("/spaces")
    def list_spaces():
        return {"results": [asdict(space) for space in store.list_spaces()]}

    @router.patch("/spaces/{space_id}")
    def rename_space(space_id: str, request: SpaceRename):
        return mutate(lambda: asdict(store.rename_space(space_id, **request.model_dump())))

    @router.post("/spaces/{space_id}/merge")
    def merge_space(space_id: str, request: SpaceMerge):
        return mutate(lambda: asdict(store.merge_spaces(space_id, **request.model_dump())))

    return router
