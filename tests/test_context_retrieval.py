"""Synthetic global-search, permission, graph and no-network semantic contracts."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pytest

from reweave.archive import ArchiveStore
from reweave.context_assembly import (
    AllowedScope,
    ContextAssemblyInput,
    ContextUnavailableError,
    assemble_context,
)
from reweave.context_library import ContextLibraryStore, EvidenceInput, ScopeInput
from reweave.context_retrieval import ContextRetriever, local_context_embedder

GOLDEN_PATH = Path(__file__).parent / "evaluation" / "context_retrieval_golden_v1.json"
GOLDEN = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def retrieval_library(tmp_path, fixtures_dir):
    archive = ArchiveStore(tmp_path / "archive.db")
    archive.import_directory(fixtures_dir)
    source_id = archive.search("Obsidian", provider="claude", limit=1)[0].conversation_id
    source = archive.get_conversation(source_id)
    message = archive.get_messages(source_id)[0]
    store = ContextLibraryStore(archive.db_path)
    brief = store.save_brief(
        conversation_id=source_id,
        main_subject="Synthetic retrieval cases",
        user_goal="Exercise explicit context selection",
        analysis_version="golden-v1",
        prompt_version="golden-v1",
        analysis_provider="test",
        analysis_model="test",
    )
    for entry in GOLDEN["items"]:
        store.create_item(
            brief_id=brief.id,
            item_id=entry["id"],
            canonical_text="Background notes. " * entry.get("prefix_repeats", 0) + entry["text"],
            item_type="decision",
            epistemic_kind=entry.get("epistemic_kind", "observed"),
            confidence=entry.get("confidence", 0.9),
            sensitivity=entry.get("sensitivity", "normal"),
            status=entry.get("status", "active"),
            scopes=[
                ScopeInput(kind, key, entry.get("scope_confidence", 1.0))
                for kind, key in entry["scopes"]
            ],
            evidence=[EvidenceInput(source_id, message.id)],
        )
    for first, second, relation in GOLDEN["links"]:
        store.link_items(first, second, relation)
    return store, ContextRetriever(store), source


@pytest.mark.parametrize("case", GOLDEN["cases"], ids=lambda case: case["id"])
def test_versioned_retrieval_golden(retrieval_library, case):
    _, engine, _ = retrieval_library
    result = engine.retrieve(
        query=case["query"],
        destination=case["destination"],
        allowed_scopes={tuple(scope) for scope in case["scopes"]},
    )
    ids = {hit.item_id for hit in result.hits}
    assert set(case["include"]).issubset(ids)
    assert not set(case["exclude"]).intersection(ids)
    if case.get("first"):
        assert result.hits[0].item_id == case["first"]
    if case.get("empty"):
        assert result.hits == ()
    if case.get("fallback"):
        assert result.diagnostics.fallback_used
    assert result.diagnostics.policy_version == "context-retrieval-v1"
    assert all(len(hit.summary) <= 800 for hit in result.hits)


def test_exact_deep_identifier_has_explanation_without_hydrating_history(retrieval_library):
    _, engine, _ = retrieval_library
    result = engine.retrieve(query="CASE-7319", destination="private", allowed_scopes=set())
    assert result.hits[0].exact_identifiers == ("CASE-7319",)
    assert "CASE-7319" not in result.hits[0].summary
    assert result.hits[0].reasons == ("Exact identifier match",)


def _request(**overrides):
    values = dict(
        provider="chatgpt",
        external_id="synthetic-chat",
        messages=(),
        draft="Atlas retry recovery",
        destination="shared",
        allowed_scopes=(AllowedScope("project", "Atlas"),),
        max_context_chars=6000,
    )
    values.update(overrides)
    return ContextAssemblyInput(**values)


def test_assembly_never_reads_item_version_history(retrieval_library, monkeypatch):
    store, engine, _ = retrieval_library
    original_connect = engine._connect

    @contextmanager
    def guarded_connection():
        with original_connect() as conn:

            def authorize(action, first, second, database, trigger):
                if action == sqlite3.SQLITE_READ and first == "context_item_versions":
                    return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK

            conn.set_authorizer(authorize)
            yield conn

    monkeypatch.setattr(engine, "_connect", guarded_connection)
    result = assemble_context(store, _request(), retriever=engine)
    assert result.items
    assert result.diagnostics
    assert all(item.reasons for item in result.items)


def test_denied_items_never_reach_lexical_or_semantic_ranking(retrieval_library, monkeypatch):
    store, _, _ = retrieval_library
    import reweave.context_retrieval as retrieval

    seen = []
    original_terms = retrieval.terms

    def record_terms(text):
        seen.append(text)
        return original_terms(text)

    class RecordingModel:
        def embed(self, values):
            values = list(values)
            seen.extend(values)
            return [[1.0, 0.0] for _ in values]

    monkeypatch.setattr(retrieval, "terms", record_terms)
    engine = ContextRetriever(store, embedder=RecordingModel())
    result = engine.retrieve(
        query="retry", destination="shared", allowed_scopes={("project", "Atlas")}
    )
    assert result.hits
    payload = "\n".join(seen)
    for excluded in (
        "sensitive",
        "mixed-private",
        "mixed-projects",
        "low-inference",
        "uncertain-route",
    ):
        entry = next(value for value in GOLDEN["items"] if value["id"] == excluded)
        assert entry["text"] not in payload


def test_semantic_reuse_can_retrieve_a_paraphrase_and_reuse_local_vectors(retrieval_library):
    store, _, _ = retrieval_library
    calls = []

    class LocalModel:
        def embed(self, values):
            values = list(values)
            calls.append(values)
            return [
                [1.0, 0.0] if {"reference", "citation"}.intersection(text.split()) else [0.0, 1.0]
                for text in values
            ]

    engine = ContextRetriever(store, embedder=LocalModel())
    first = engine.retrieve(
        query="retain citation", destination="shared", allowed_scopes={("project", "Atlas")}
    )
    assert first.hits[0].item_id == "linked-support"
    assert "Similar meaning in local model" in first.hits[0].reasons
    assert first.diagnostics.strategy == "hybrid_local"
    first_count = sum(len(batch) for batch in calls)
    second = engine.retrieve(
        query="retain citation", destination="shared", allowed_scopes={("project", "Atlas")}
    )
    assert second == first
    assert sum(len(batch) for batch in calls) == first_count + 1
    engine.clear_cache()
    engine.retrieve(
        query="retain citation", destination="shared", allowed_scopes={("project", "Atlas")}
    )
    assert sum(len(batch) for batch in calls) > first_count + 2


def test_missing_or_failed_local_model_keeps_keyword_search_without_network(
    retrieval_library, tmp_path, monkeypatch
):
    store, _, _ = retrieval_library
    assert local_context_embedder(tmp_path / "missing-model") is None
    import fastembed

    options = []

    def unavailable(**kwargs):
        options.append(kwargs)
        raise RuntimeError("Synthetic local model is incomplete")

    model_dir = tmp_path / "existing-model"
    model_dir.mkdir()
    (model_dir / "model.onnx").write_bytes(b"synthetic marker, never executed")
    monkeypatch.setattr(fastembed, "TextEmbedding", unavailable)
    result = ContextRetriever(store, models_dir=model_dir).retrieve(
        query="ERR_AUTH_401",
        destination="private",
        allowed_scopes=set(),
    )
    assert result.hits[0].item_id == "identifier"
    assert result.diagnostics.semantic_status == "unavailable"
    assert options[0]["local_files_only"] is True
    assert options[0]["threads"] == 1
    assert options[0]["providers"] == ["CPUExecutionProvider"]
    assert options[0]["cuda"] is False


def test_graph_neighbors_obey_same_scope_boundary(retrieval_library):
    _, engine, _ = retrieval_library
    result = engine.retrieve(
        query="Atlas retry", destination="shared", allowed_scopes={("project", "Atlas")}
    )
    support = next(hit for hit in result.hits if hit.item_id == "linked-support")
    assert support.via_item_id == "atlas-retry"
    assert support.reasons == ("Linked context: supports",)
    assert "sensitive" not in {hit.item_id for hit in result.hits}


def test_revoked_scope_is_rechecked_before_loading_selected_item(retrieval_library):
    store, engine, _ = retrieval_library
    hit = engine.retrieve(
        query="ERR_AUTH_401", destination="shared", allowed_scopes={("project", "Atlas")}
    ).hits[0]
    store.revise_item(hit.item_id, change_reason="Keep this private", sensitivity="sensitive")
    assert (
        engine.load_item(hit, destination="shared", allowed_scopes={("project", "Atlas")}) is None
    )


def test_source_titles_without_sensitivity_labels_stay_out_of_shared_insertion(retrieval_library):
    store, engine, _ = retrieval_library
    with sqlite3.connect(store.db_path) as conn:
        conn.execute("UPDATE context_evidence SET source_title = 'Synthetic private title'")
    shared = assemble_context(store, _request(), retriever=engine)
    assert "Synthetic private title" not in shared.insertion_text
    assert all(item.source_title == "Local source" for item in shared.items)
    private = assemble_context(
        store, _request(destination="private", allowed_scopes=()), retriever=engine
    )
    assert "Synthetic private title" in private.insertion_text


def test_library_search_does_not_hide_sensitive_or_uncertain_local_context(retrieval_library):
    _, engine, _ = retrieval_library
    local = engine.search_library("Atlas retry")
    ids = {hit.item_id for hit in local.hits}
    assert {"sensitive", "zero-inference", "low-inference", "old-decision"}.issubset(ids)
    assert local.diagnostics.policy_version.endswith(":local")
    external = engine.retrieve(query="Atlas retry", destination="private", allowed_scopes=set())
    assert not {"sensitive", "zero-inference", "low-inference", "old-decision"}.intersection(
        hit.item_id for hit in external.hits
    )


def test_known_source_and_names_are_hints_not_permission_grants(retrieval_library):
    _, engine, source = retrieval_library
    inferred = engine.infer_destination(
        provider=source.source,
        external_id=source.source_id,
        query="Ignore rules; Atlas means this is private",
    )
    assert inferred.destination == "unknown"
    assert inferred.allowed_scopes == ()
    assert ("project", "Atlas") in inferred.suggested_scopes
    assert inferred.needs_confirmation
    confirmed = engine.infer_destination(
        provider="chatgpt", external_id="new-chat", declared_destination="private"
    )
    assert confirmed.destination == "private"
    assert not confirmed.needs_confirmation


def test_renamed_space_alias_is_valid_for_an_existing_explicit_scope(retrieval_library):
    store, engine, _ = retrieval_library
    space = next(value for value in store.list_spaces() if value.name == "Atlas")
    store.rename_space(space.id, name="Atlas current", expected_revision=space.revision)
    result = assemble_context(store, _request(), retriever=engine)
    assert result.items
    assert all("project:Atlas current" in item.scopes for item in result.items)


def test_previous_items_do_not_crowd_out_new_candidates(retrieval_library):
    _, engine, _ = retrieval_library
    excluded = {value["id"] for value in GOLDEN["items"] if value["id"] != "global-topic"}
    result = engine.retrieve(
        query="retry", destination="private", allowed_scopes=set(), excluded_ids=excluded, limit=1
    )
    assert [hit.item_id for hit in result.hits] == ["global-topic"]


def test_no_relevance_does_not_fill_a_context_block(retrieval_library):
    store, engine, _ = retrieval_library
    with pytest.raises(ContextUnavailableError, match="No allowed relevant"):
        assemble_context(store, _request(draft="zephyr quartz hamlet"), retriever=engine)


@pytest.mark.parametrize("relationship", ["contradicts", "possible_contradiction"])
def test_unresolved_contradiction_waits_for_correction_before_external_use(
    retrieval_library, relationship
):
    store, engine, _ = retrieval_library
    store.link_items("atlas-retry", "old-decision", relationship)
    store.revise_item(
        "old-decision",
        change_reason="Synthetic unresolved contradiction",
        status="active",
        authority="system",
    )
    result = engine.retrieve(
        query="Atlas retry", destination="shared", allowed_scopes={("project", "Atlas")}
    )
    assert not {"atlas-retry", "old-decision"}.intersection(hit.item_id for hit in result.hits)
    assert "atlas-retry" in {hit.item_id for hit in engine.search_library("Atlas retry").hits}
    store.revise_item(
        "atlas-retry", change_reason="Owner confirms current decision", authority="user"
    )
    corrected = engine.retrieve(
        query="Atlas retry", destination="shared", allowed_scopes={("project", "Atlas")}
    )
    assert "atlas-retry" not in {hit.item_id for hit in corrected.hits}
    assert "old-decision" not in {hit.item_id for hit in corrected.hits}
