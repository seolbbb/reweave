"""Markdown templates for different note types."""

from __future__ import annotations

import yaml

from sbs.models.note import DraftNote, MOC, NoteFrontmatter


def render_permanent_note(note: DraftNote) -> str:
    """Render a permanent note as Markdown with YAML frontmatter."""
    fm = _render_frontmatter(note.frontmatter)
    lines = [fm, "", f"# {note.title}", "", note.body]

    if note.source_segment_ids:
        lines.extend(["", "## Source"])
        lines.append(f"{note.frontmatter.source_ref} segment(s): {', '.join(note.source_segment_ids)}")

    return "\n".join(lines) + "\n"


def render_source_note(note: DraftNote) -> str:
    """Render a source note as Markdown with YAML frontmatter."""
    fm = _render_frontmatter(note.frontmatter)
    return f"{fm}\n\n{note.body}\n"


def render_moc(moc: MOC, note_map: dict[str, DraftNote] | None = None) -> str:
    """Render a MOC as Markdown with YAML frontmatter."""
    fm_data = {
        "type": "moc",
        "created": moc.id,
        "tags": ["moc"] + moc.tags,
    }
    fm = "---\n" + yaml.dump(fm_data, default_flow_style=False, allow_unicode=True).strip() + "\n---"

    lines = [fm, "", f"# {moc.title}", ""]

    if moc.body:
        lines.append(moc.body)
    else:
        lines.append("## Notes")
        for nid in moc.note_ids:
            if note_map and nid in note_map:
                note = note_map[nid]
                lines.append(f"- [[{note.id}-{_safe_slug(note.title)}]] -- {note.title}")
            else:
                lines.append(f"- [[{nid}]]")

    return "\n".join(lines) + "\n"


def _render_frontmatter(fm: NoteFrontmatter) -> str:
    """Render NoteFrontmatter as YAML frontmatter block."""
    data = fm.model_dump(exclude_none=True)
    yaml_str = yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    return f"---\n{yaml_str.strip()}\n---"


def _safe_slug(text: str) -> str:
    """Quick slug for inline references."""
    import re

    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text[:50].strip("-")
