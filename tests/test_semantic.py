"""Tests for optional local semantic indexing and hybrid retrieval."""

from __future__ import annotations

import json

import numpy as np
import pytest

from reweave.archive import ArchiveStore
from reweave.context_library import ContextLibraryStore, EvidenceInput, ScopeInput
from reweave.semantic import (
    MAX_CHUNK_CHARS,
    SearchEngine,
    SemanticIndex,
    SemanticUnavailableError,
    split_message,
)


class TopicEmbedder:
    """Small deterministic embedder used without downloading a production model."""

    def embed(self, texts):
        for text in texts:
            lowered = text.lower()
            if any(term in lowered for term in ("vault", "flat folder", "second brain")):
                yield np.asarray([1.0, 0.0, 0.0], dtype=np.float32)
            elif any(term in lowered for term in ("agent", "orchestrator", "worker")):
                yield np.asarray([0.0, 1.0, 0.0], dtype=np.float32)
            else:
                yield np.asarray([0.0, 0.0, 1.0], dtype=np.float32)


def _prepared_index(tmp_path, fixtures_dir):
    store = ArchiveStore(tmp_path / "archive.db")
    store.import_directory(fixtures_dir)
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    (models_dir / "model.onnx").write_bytes(b"test model marker")
    index = SemanticIndex(store.db_path, models_dir, embedder_factory=TopicEmbedder)
    status = index.build(embedder=TopicEmbedder())
    return store, index, status


def test_chunking_respects_size_and_overlap():
    content = "a" * 2_000

    chunks = list(split_message(content))

    assert len(chunks) == 2
    assert all(len(chunk) <= MAX_CHUNK_CHARS for chunk in chunks)
    assert chunks[0][-200:] == chunks[1][:200]


def test_semantic_mode_requires_an_explicitly_built_index(tmp_path, fixtures_dir):
    store = ArchiveStore(tmp_path / "archive.db")
    store.import_directory(fixtures_dir)
    engine = SearchEngine(store, SemanticIndex(store.db_path, tmp_path / "models"))

    with pytest.raises(SemanticUnavailableError):
        engine.search_messages("second brain", mode="semantic")

    results, mode_used = engine.search_messages("Obsidian", mode="auto")
    assert results
    assert mode_used == "keyword"


def test_semantic_and_auto_modes_find_paraphrased_archive_content(tmp_path, fixtures_dir):
    store, index, status = _prepared_index(tmp_path, fixtures_dir)
    engine = SearchEngine(store, index)

    semantic, semantic_mode = engine.search_messages("second brain layout", mode="semantic")
    hybrid, hybrid_mode = engine.search_messages("second brain layout", mode="auto")

    assert status.ready
    assert semantic_mode == "semantic"
    assert semantic[0].title == "Obsidian Vault Setup"
    assert semantic[0].match_kind == "semantic"
    assert hybrid_mode == "hybrid"
    assert hybrid[0].title == "Obsidian Vault Setup"


def test_changed_message_invalidates_only_its_embeddings(tmp_path, claude_sample_path):
    export_path = tmp_path / "claude.json"
    payload = json.loads(claude_sample_path.read_text(encoding="utf-8"))
    export_path.write_text(json.dumps(payload), encoding="utf-8")
    store = ArchiveStore(tmp_path / "archive.db")
    store.import_path(export_path)
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    (models_dir / "model.onnx").write_bytes(b"test model marker")
    index = SemanticIndex(store.db_path, models_dir, embedder_factory=TopicEmbedder)
    initial = index.build(embedder=TopicEmbedder())

    payload[0]["chat_messages"][1]["text"] = "Use a linked second brain layout."
    export_path.write_text(json.dumps(payload), encoding="utf-8")
    summary = store.import_path(export_path)
    stale = index.status()
    refreshed = index.build(embedder=TopicEmbedder())

    assert initial.ready
    assert summary.updated_messages == 1
    assert summary.invalidated_embeddings == 1
    assert not stale.ready
    assert refreshed.ready
    assert refreshed.indexed_chunks == initial.indexed_chunks


@pytest.mark.parametrize("mode", ["keyword", "semantic", "auto"])
def test_source_context_filters_apply_before_ranking(tmp_path, fixtures_dir, mode):
    store, index, _ = _prepared_index(tmp_path, fixtures_dir)
    engine = SearchEngine(store, index)
    source = store.search("Obsidian", limit=1)[0].conversation_id
    message = store.get_messages(source)[0]
    library = ContextLibraryStore(store.db_path)
    brief = library.save_brief(
        conversation_id=source,
        main_subject="Vault",
        user_goal="Organize",
        analysis_version="test",
        prompt_version="test",
        analysis_provider="test",
        analysis_model="test",
    )
    library.create_item(
        brief_id=brief.id,
        canonical_text="Organize the vault",
        item_type="project_fact",
        epistemic_kind="observed",
        confidence=0.95,
        scopes=[ScopeInput("project", "Vault")],
        evidence=[EvidenceInput(source, message.id, excerpt=message.content)],
    )
    space = next(space for space in library.list_spaces() if space.name == "Vault")
    results, _ = engine.search_messages(
        "Obsidian",
        mode=mode,
        space_id=space.id,
        item_type="project_fact",
        limit=1,
    )
    assert len(results) == 1 and results[0].conversation_id == source
    assert (
        engine.search_messages(
            "Obsidian",
            mode=mode,
            space_id=space.id,
            item_type="decision",
            limit=1,
        )[0]
        == []
    )
    assert engine.search_messages("Obsidian", mode=mode, space_id="missing", limit=1)[0] == []
