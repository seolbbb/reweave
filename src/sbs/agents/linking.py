"""Stage 4 linking agent for note connections and MOC generation."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from sbs.config import Config
from sbs.llm.client import LLMClient
from sbs.llm.prompts import (
    LINKING_CLUSTER_SYSTEM,
    LINKING_CLUSTER_USER,
    LINKING_DISCOVER_SYSTEM,
    LINKING_DISCOVER_USER,
    get_prompt,
)
from sbs.models.note import MOC, DraftNote, NoteLink


class ClusterItem(BaseModel):
    cluster_label: str
    note_ids: list[str] = Field(default_factory=list)


class ClusteringResult(BaseModel):
    clusters: list[ClusterItem] = Field(default_factory=list)


class LinkItem(BaseModel):
    source_note_id: str
    target_note_id: str
    relationship: str
    description: str


class LinkDiscoveryResult(BaseModel):
    links: list[LinkItem] = Field(default_factory=list)


async def link_notes(
    draft_notes: list[DraftNote],
    llm: LLMClient,
    config: Config,
) -> tuple[list[NoteLink], list[MOC], list[DraftNote]]:
    """Discover links between permanent notes and create MOCs."""
    if not draft_notes:
        return [], [], []

    _ = config
    note_map = {n.id: n for n in draft_notes}
    permanent_notes = [n for n in draft_notes if n.type == "permanent"]
    fleeting_notes = [n for n in draft_notes if n.type == "fleeting"]

    all_links: list[NoteLink] = []
    clusters: list[ClusterItem] = []

    if permanent_notes:
        # Step 1: Cluster permanent notes by topic.
        clusters = await _cluster_notes(permanent_notes, llm)

        # Step 2: Discover links within each cluster.
        for cluster in clusters:
            valid_ids = [nid for nid in cluster.note_ids if nid in note_map]
            if len(valid_ids) < 2:
                continue
            cluster_notes = [note_map[nid] for nid in valid_ids]
            links = await _discover_links(cluster.cluster_label, cluster_notes, llm)
            all_links.extend(links)

    # Step 3: Create MOCs for clusters with 3+ permanent notes.
    mocs = _create_mocs(clusters, note_map)

    # Step 4: Insert links into all knowledge notes.
    final_notes = _inject_links(draft_notes, all_links)

    # Step 5: Handle orphan permanent notes.
    linked_ids = set()
    for link in all_links:
        linked_ids.add(link.source_note_id)
        linked_ids.add(link.target_note_id)

    orphan_permanent = [n for n in permanent_notes if n.id not in linked_ids]
    if orphan_permanent:
        mocs.append(
            MOC(
                id="moc-misc",
                title="Miscellaneous Permanent Notes",
                filename="MOC-miscellaneous.md",
                tags=["misc", "permanent"],
                note_ids=[n.id for n in orphan_permanent],
            )
        )

    # Step 6: Add fleeting triage MOC for inbox-style refinement.
    if fleeting_notes:
        mocs.append(_create_fleeting_triage_moc(fleeting_notes))

    return all_links, mocs, final_notes


async def _cluster_notes(
    notes: list[DraftNote], llm: LLMClient
) -> list[ClusterItem]:
    """Ask LLM to group notes into topical clusters."""
    notes_summary = "\n".join(
        f"- ID: {n.id} | Title: {n.title} | Tags: {', '.join(n.frontmatter.tags)}"
        for n in notes
    )
    user_prompt = get_prompt("LINKING_CLUSTER_USER", LINKING_CLUSTER_USER).format(
        notes_summary=notes_summary
    )

    result, _usage = await llm.cheap_structured_call(
        system=get_prompt("LINKING_CLUSTER_SYSTEM", LINKING_CLUSTER_SYSTEM),
        user=user_prompt,
        schema=ClusteringResult,
    )

    if result.clusters:
        return result.clusters
    return [ClusterItem(cluster_label="General", note_ids=[n.id for n in notes])]


async def _discover_links(
    cluster_label: str,
    notes: list[DraftNote],
    llm: LLMClient,
) -> list[NoteLink]:
    """Discover meaningful links between notes in a cluster."""
    notes_detail = "\n\n".join(
        f"### {n.id}: {n.title}\n{n.body[:300]}..." if len(n.body) > 300
        else f"### {n.id}: {n.title}\n{n.body}"
        for n in notes
    )
    user_prompt = get_prompt("LINKING_DISCOVER_USER", LINKING_DISCOVER_USER).format(
        cluster_label=cluster_label, notes_detail=notes_detail
    )

    result, _usage = await llm.main_structured_call(
        system=get_prompt("LINKING_DISCOVER_SYSTEM", LINKING_DISCOVER_SYSTEM),
        user=user_prompt,
        schema=LinkDiscoveryResult,
    )

    return [
        NoteLink(
            source_note_id=link.source_note_id,
            target_note_id=link.target_note_id,
            relationship=link.relationship,
            description=link.description,
        )
        for link in result.links
    ]


def _create_mocs(
    clusters: list[ClusterItem], note_map: dict[str, DraftNote]
) -> list[MOC]:
    """Create MOCs for clusters with 3+ notes."""
    mocs = []
    for cluster in clusters:
        valid_ids = [nid for nid in cluster.note_ids if nid in note_map]
        permanent_ids = [nid for nid in valid_ids if note_map[nid].type == "permanent"]
        if len(permanent_ids) < 3:
            continue

        slug = re.sub(r"[^\w\s-]", "", cluster.cluster_label.lower())
        slug = re.sub(r"[\s_]+", "-", slug).strip("-")[:50]

        moc = MOC(
            id=f"moc-{slug}",
            title=cluster.cluster_label,
            filename=f"MOC-{slug}.md",
            tags=[slug, "permanent"],
            note_ids=permanent_ids,
        )
        mocs.append(moc)

    return mocs


def _inject_links(
    notes: list[DraftNote], links: list[NoteLink]
) -> list[DraftNote]:
    """Add discovered links to notes' related frontmatter."""
    adjacency: dict[str, set[str]] = {}
    for link in links:
        adjacency.setdefault(link.source_note_id, set()).add(link.target_note_id)
        adjacency.setdefault(link.target_note_id, set()).add(link.source_note_id)

    updated = []
    for note in notes:
        related_ids = adjacency.get(note.id, set())
        if related_ids:
            note.frontmatter.related = [f"[[{rid}]]" for rid in sorted(related_ids)]
        updated.append(note)

    return updated


def _create_fleeting_triage_moc(fleeting_notes: list[DraftNote]) -> MOC:
    """Create a triage MOC to help users promote fleeting notes."""
    body_lines = [
        "## Triage Guidance",
        "- Promote notes with reusable claims into permanent notes.",
        "- Merge duplicate rough ideas.",
        "- Add evidence or examples before promoting.",
    ]

    return MOC(
        id="moc-inbox-triage",
        title="Inbox Triage",
        filename="MOC-inbox-triage.md",
        tags=["triage", "fleeting"],
        note_ids=[note.id for note in fleeting_notes],
        body="\n".join(body_lines),
    )
