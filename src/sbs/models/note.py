"""Note models — draft notes, frontmatter, links, and MOCs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class NoteFrontmatter(BaseModel):
    """YAML frontmatter for an Obsidian note."""

    type: Literal["fleeting", "permanent", "moc", "source", "literature"]
    status: Literal["seedling", "budding", "evergreen"] = "seedling"
    created: str  # ISO 8601
    tags: list[str] = Field(default_factory=list)
    source_type: Literal["chatgpt", "claude"] | None = None
    source_ref: str = ""
    conversation_date: str = ""
    participants: list[str] = Field(default_factory=list)
    related: list[str] = Field(default_factory=list)


class DraftNote(BaseModel):
    """A draft note ready to be written to the vault."""

    id: str  # YYYYMMDDHHMMSS-based ID
    filename: str  # {id}-{slug}.md
    type: Literal["fleeting", "permanent", "source", "literature"]
    title: str
    frontmatter: NoteFrontmatter
    body: str  # Markdown content
    link_candidates: list[str] = Field(default_factory=list)
    source_segment_ids: list[str] = Field(default_factory=list)


class NoteLink(BaseModel):
    """A discovered link between two notes."""

    source_note_id: str
    target_note_id: str
    relationship: str  # e.g. "supports", "contradicts", "extends", etc.
    description: str


class MOC(BaseModel):
    """A Map of Content grouping related notes."""

    id: str
    title: str
    filename: str
    tags: list[str] = Field(default_factory=list)
    note_ids: list[str] = Field(default_factory=list)
    body: str = ""
