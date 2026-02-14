"""Stage 4: Linking agent — discover connections between notes and create MOCs."""

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
    """Discover links between notes and create MOCs."""
    if not draft_notes:
        return [], [], []

    note_map = {n.id: n for n in draft_notes}

    # Step 1: Cluster notes by topic
    clusters = await _cluster_notes(draft_notes, llm)

    # Step 2: Discover links within each cluster
    all_links: list[NoteLink] = []
    for cluster in clusters:
        # Filter to notes that exist
        valid_ids = [nid for nid in cluster.note_ids if nid in note_map]
        if len(valid_ids) < 2:
            continue
        cluster_notes = [note_map[nid] for nid in valid_ids]
        links = await _discover_links(cluster.cluster_label, cluster_notes, llm)
        all_links.extend(links)

    # Step 3: Create MOCs for clusters with 3+ notes
    mocs = _create_mocs(clusters, note_map)

    # Step 4: Insert links into notes as "related" frontmatter
    final_notes = _inject_links(draft_notes, all_links)

    # Step 5: Handle orphan notes
    linked_ids = set()
    for link in all_links:
        linked_ids.add(link.source_note_id)
        linked_ids.add(link.target_note_id)

    orphan_notes = [n for n in draft_notes if n.id not in linked_ids]
    if orphan_notes:
        # Add orphans to a "Misc" MOC if they exist
        misc_moc = MOC(
            id="moc-misc",
            title="Miscellaneous",
            filename="MOC-miscellaneous.md",
            tags=["misc"],
            note_ids=[n.id for n in orphan_notes],
        )
        mocs.append(misc_moc)

    return all_links, mocs, final_notes


async def _cluster_notes(
    notes: list[DraftNote], llm: LLMClient
) -> list[ClusterItem]:
    """Ask LLM to group notes into topical clusters."""
    notes_summary = "\n".join(
        f"- ID: {n.id} | Title: {n.title} | Tags: {', '.join(n.frontmatter.tags)}"
        for n in notes
    )
    user_prompt = LINKING_CLUSTER_USER.format(notes_summary=notes_summary)

    result, _usage = await llm.cheap_structured_call(
        system=LINKING_CLUSTER_SYSTEM,
        user=user_prompt,
        schema=ClusteringResult,
    )

    return result.clusters if result.clusters else [
        ClusterItem(cluster_label="General", note_ids=[n.id for n in notes])
    ]


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
    user_prompt = LINKING_DISCOVER_USER.format(
        cluster_label=cluster_label, notes_detail=notes_detail
    )

    result, _usage = await llm.main_structured_call(
        system=LINKING_DISCOVER_SYSTEM,
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
        if len(valid_ids) < 3:
            continue

        slug = re.sub(r"[^\w\s-]", "", cluster.cluster_label.lower())
        slug = re.sub(r"[\s_]+", "-", slug).strip("-")[:50]

        moc = MOC(
            id=f"moc-{slug}",
            title=cluster.cluster_label,
            filename=f"MOC-{slug}.md",
            tags=[slug],
            note_ids=valid_ids,
        )
        mocs.append(moc)

    return mocs


def _inject_links(
    notes: list[DraftNote], links: list[NoteLink]
) -> list[DraftNote]:
    """Add discovered links to notes' related frontmatter."""
    # Build adjacency map
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
