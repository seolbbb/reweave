"""Obsidian vault file writer — writes notes, MOCs, and sources to disk."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console

from sbs.models.pipeline import PipelineState
from sbs.output.naming import sanitize_filename
from sbs.output.templates import render_moc, render_permanent_note, render_source_note

console = Console()


def write_vault(state: PipelineState) -> Path:
    """Write the complete vault to the output directory."""
    output = state.config.output_dir
    notes_dir = output / "notes"
    mocs_dir = output / "mocs"
    sources_dir = output / "sources"

    notes_dir.mkdir(parents=True, exist_ok=True)
    mocs_dir.mkdir(parents=True, exist_ok=True)
    sources_dir.mkdir(parents=True, exist_ok=True)

    note_map = {n.id: n for n in state.final_notes or state.draft_notes}

    # Write permanent notes
    written_notes = 0
    for note in state.final_notes or state.draft_notes:
        filename = sanitize_filename(note.filename)
        path = notes_dir / filename
        content = render_permanent_note(note)
        path.write_text(content, encoding="utf-8")
        written_notes += 1

    # Write source notes
    written_sources = 0
    for note in state.source_notes:
        filename = sanitize_filename(note.filename)
        path = sources_dir / filename
        content = render_source_note(note)
        path.write_text(content, encoding="utf-8")
        written_sources += 1

    # Write MOCs
    written_mocs = 0
    for moc in state.mocs:
        filename = sanitize_filename(moc.filename)
        path = mocs_dir / filename
        content = render_moc(moc, note_map)
        path.write_text(content, encoding="utf-8")
        written_mocs += 1

    console.print(
        f"  Vault written to [bold]{output}[/bold]: "
        f"{written_notes} notes, {written_sources} sources, {written_mocs} MOCs"
    )
    return output
