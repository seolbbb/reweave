"""Extraction models — structured knowledge extracted from conversation segments."""

from __future__ import annotations

from pydantic import BaseModel


class ConceptItem(BaseModel):
    """A single concept extracted from a segment."""

    name: str
    description: str
    importance: int = 1  # 1-5 scale


class DecisionItem(BaseModel):
    """A decision or conclusion made during the conversation."""

    decision: str
    rationale: str


class InsightItem(BaseModel):
    """An insight or learning from the conversation."""

    insight: str
    context: str


class TodoItem(BaseModel):
    """An action item or task mentioned in the conversation."""

    task: str
    status: str = "open"  # open, done


class OpenQuestion(BaseModel):
    """An unresolved question from the conversation."""

    question: str
    context: str


class ExtractedKnowledge(BaseModel):
    """Structured knowledge extracted from a single segment."""

    segment_id: str
    conversation_id: str
    topic_label: str
    concepts: list[ConceptItem] = []
    decisions: list[DecisionItem] = []
    insights: list[InsightItem] = []
    todos: list[TodoItem] = []
    open_questions: list[OpenQuestion] = []
    summary: str = ""
