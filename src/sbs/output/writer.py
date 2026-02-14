"""Obsidian vault file writer that persists generated notes to disk."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console

from sbs.models.pipeline import PipelineState
from sbs.output.naming import sanitize_filename
from sbs.output.templates import (
    render_literature_note,
    render_moc,
    render_permanent_note,
    render_source_note,
)

console = Console()

VAULT_LAYOUT = {
    "inbox": "100_inbox",
    "fleeting": "200_fleeting",
    "permanent": "300_permanent",
    "mocs": "400_mocs",
    "literature": "500_literature",
    "sources": "900_sources",
}


def write_vault(state: PipelineState) -> Path:
    """Write the complete vault to the output directory."""
    output = state.config.output_dir
    inbox_dir = output / VAULT_LAYOUT["inbox"]
    fleeting_dir = output / VAULT_LAYOUT["fleeting"]
    permanent_dir = output / VAULT_LAYOUT["permanent"]
    mocs_dir = output / VAULT_LAYOUT["mocs"]
    literature_dir = output / VAULT_LAYOUT["literature"]
    sources_dir = output / VAULT_LAYOUT["sources"]

    inbox_dir.mkdir(parents=True, exist_ok=True)
    fleeting_dir.mkdir(parents=True, exist_ok=True)
    permanent_dir.mkdir(parents=True, exist_ok=True)
    mocs_dir.mkdir(parents=True, exist_ok=True)
    literature_dir.mkdir(parents=True, exist_ok=True)
    sources_dir.mkdir(parents=True, exist_ok=True)

    note_map = {n.id: n for n in state.final_notes or state.draft_notes}

    # Write knowledge notes by type.
    written_fleeting = 0
    written_permanent = 0
    for note in state.final_notes or state.draft_notes:
        if note.type not in {"fleeting", "permanent"}:
            continue

        filename = sanitize_filename(note.filename)
        path = (fleeting_dir if note.type == "fleeting" else permanent_dir) / filename
        content = render_permanent_note(note)
        path.write_text(content, encoding="utf-8")

        if note.type == "fleeting":
            written_fleeting += 1
        else:
            written_permanent += 1

    # Write source notes.
    written_sources = 0
    for note in state.source_notes:
        filename = sanitize_filename(note.filename)
        path = sources_dir / filename
        content = render_source_note(note)
        path.write_text(content, encoding="utf-8")
        written_sources += 1

    # Write literature notes.
    written_literature = 0
    for note in state.literature_notes:
        filename = sanitize_filename(note.filename)
        path = literature_dir / filename
        content = render_literature_note(note)
        path.write_text(content, encoding="utf-8")
        written_literature += 1

    # Write MOCs.
    written_mocs = 0
    for moc in state.mocs:
        filename = sanitize_filename(moc.filename)
        path = mocs_dir / filename
        content = render_moc(moc, note_map)
        path.write_text(content, encoding="utf-8")
        written_mocs += 1

    _write_run_summary(
        inbox_dir=inbox_dir,
        state=state,
        fleeting_count=written_fleeting,
        permanent_count=written_permanent,
        source_count=written_sources,
        literature_count=written_literature,
        moc_count=written_mocs,
    )

    console.print(
        f"  Vault written to [bold]{output}[/bold]: "
        f"{written_permanent} permanent, {written_fleeting} fleeting, "
        f"{written_sources} sources, {written_literature} literature, {written_mocs} MOCs"
    )
    return output


def _write_run_summary(
    inbox_dir: Path,
    state: PipelineState,
    fleeting_count: int,
    permanent_count: int,
    source_count: int,
    literature_count: int,
    moc_count: int,
) -> None:
    """Write a deterministic run summary for inbox triage."""
    summary_path = inbox_dir / "Run-Summary.md"
    report = state.validation_report

    lines = ["# Run Summary", ""]
    lines.append(f"- Conversations: {len(state.conversations)}")
    lines.append(f"- Fleeting notes: {fleeting_count}")
    lines.append(f"- Permanent notes: {permanent_count}")
    lines.append(f"- Source notes: {source_count}")
    lines.append(f"- Literature notes: {literature_count}")
    lines.append(f"- MOCs: {moc_count}")
    lines.append("")

    if report:
        lines.append("## Validation")
        lines.append(f"- Score: {report.score:.1f}/100")
        lines.append(f"- Issues: {len(report.issues)}")
        lines.append(f"- Orphan notes: {report.orphan_notes}")
        lines.append("")

    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
