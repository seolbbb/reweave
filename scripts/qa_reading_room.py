"""Seed only synthetic visual fixtures, then run the real isolated headless app.

This preserves the accepted design's baseline data for matched screenshots.
It proves rendering, not extraction quality or actual personal usefulness.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--run-for", type=int, default=1200)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    data = args.data_dir.resolve()
    if not data.is_relative_to(root / ".pytest_cache"):
        parser.error("Visual QA data must be inside this worktree's .pytest_cache.")
    os.environ.update(
        {
            "REWEAVE_DATA_DIR": str(data),
            "REWEAVE_CREDENTIAL_BACKEND": "memory",
            "PYTHON_DOTENV_DISABLED": "1",
        }
    )
    from reweave.archive import ArchiveStore
    from reweave.context_library import ContextLibraryStore, EvidenceInput, ScopeInput
    from reweave.desktop import run_headless

    data.mkdir(parents=True, exist_ok=True)
    archive = ArchiveStore(data / "reweave.db")
    archive.import_directory(root / "tests" / "fixtures")
    match = archive.search("Obsidian", provider="claude", limit=1)[0]
    conversation = archive.get_conversation(match.conversation_id)
    messages = archive.get_messages(match.conversation_id)
    context = ContextLibraryStore(data / "reweave.db")
    if not context.list_items():
        brief = context.save_brief(
            conversation_id=conversation.id,
            main_subject="A simpler system for connected project notes",
            user_goal="Keep useful ideas connected without maintaining a folder system.",
            important_outcomes=["Use links to connect related project notes."],
            decisions=["Start with a flat folder structure and add links as needed."],
            lessons=["Organization should help you return to an idea, not create more work."],
            unresolved_questions=["Which details should be shared across projects?"],
            actions=["Try the structure with one active project."],
            analysis_mode="project",
            analysis_version="design-preview-synthetic-v1",
            prompt_version="synthetic-preview",
            analysis_provider="synthetic",
            analysis_model="no-model-called",
        )
        entries = [
            (
                "Start with a flat folder structure and connect notes through links.",
                "decision",
                "observed",
                "Knowledge system",
            ),
            (
                "Organization should help you return to an idea, not create more work.",
                "lesson",
                "inferred",
                "Knowledge system",
            ),
            (
                "Try the structure with one active project before expanding it.",
                "action",
                "suggested",
                "Writing practice",
            ),
            (
                "Which details should be shared across projects?",
                "open_question",
                "observed",
                "Knowledge system",
            ),
        ]
        for content, kind, epistemic, project in entries:
            context.create_item(
                brief_id=brief.id,
                canonical_text=content,
                item_type=kind,
                epistemic_kind=epistemic,
                confidence=0.87,
                scopes=[ScopeInput("project", project), ScopeInput("topic", "Connected thinking")],
                evidence=[
                    EvidenceInput(
                        conversation_id=conversation.id,
                        message_id=messages[0].id,
                        excerpt=messages[0].content[:160],
                    )
                ],
            )
    run_headless(data_dir=data, run_for=args.run_for, stop_file=data / "stop-request")


if __name__ == "__main__":
    main()
