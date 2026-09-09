"""Synthetic full coverage, exact evidence, and durable sequential checkpoint reuse."""

import json
from types import SimpleNamespace

import pytest

from reweave.analysis_policy import AnalysisLimitError
from reweave.archive import ArchiveStore
from reweave.context_chunking import ChunkStore, PartialAnalysisError, partition_messages
from reweave.context_library import ContextLibraryStore
from reweave.context_review import ContextReviewStore
from reweave.llm import ProviderConnectionChangedError


def messages(count=6, length=700):
    return [
        SimpleNamespace(
            id=f"message-{i}",
            index=i,
            role="user" if i % 2 == 0 else "assistant",
            timestamp="2026-09-09T00:00:00Z",
            content=f"Original turn {i}: " + ('ab\n"한글😀 ' * length),
        )
        for i in range(count)
    ]


def brief(decisions=()):
    return {
        "main_subject": "Synthetic complete source",
        "user_goal": "Retain all decisions",
        "important_outcomes": [],
        "decisions": list(decisions),
        "lessons": [],
        "unresolved_questions": [],
        "actions": [],
    }


def normalized(segment):
    piece = segment.pieces[0]
    return {
        "brief": brief([f"Segment {segment.index}"]),
        "items": [
            {
                "canonical_text": f"Keep segment {segment.index}.",
                "item_type": "decision",
                "epistemic_kind": "observed" if piece.role == "user" else "suggested",
                "confidence": 0.9,
                "sensitivity": "normal",
                "scopes": [{"scope_type": "project", "scope_key": "Synthetic", "confidence": 1}],
                "evidence": [
                    {
                        "message_id": piece.message_id,
                        "message_index": piece.message_index,
                        "message_role": piece.role,
                        "message_timestamp": piece.timestamp,
                        "excerpt": piece.content[: min(20, len(piece.content))],
                        "relationship": "supports",
                    }
                ],
                "last_confirmed_at": None,
                "inference_rationale": "",
            }
        ],
        "dropped_items": 0,
        "deduplicated_items": 0,
    }


@pytest.fixture
def runtime(tmp_path, fixtures_dir):
    archive = ArchiveStore(tmp_path / "library.db")
    archive.import_directory(fixtures_dir)
    source_id = archive.search("Obsidian", limit=1)[0].conversation_id
    runner = ChunkStore(archive.db_path)
    calls = []

    def call_chunk(segment):
        calls.append(("chunk", segment.index))
        return {"raw_model_trace": "Never checkpoint this private model trace"}

    def call_synthesis(values):
        calls.append(("synthesis", len(values)))
        decisions = [decision for value in values for decision in value.get("decisions", [])]
        return brief(decisions)

    args = dict(
        source_id=source_id,
        source_fingerprint="source-v1",
        analysis_config_key="model-v1",
        explicit_generation=1,
        messages=messages(3, 160),
        max_payload_chars=2500,
        call_chunk=call_chunk,
        normalize_chunk=lambda raw, segment: normalized(segment),
        call_synthesis=call_synthesis,
        normalize_synthesis=lambda raw, values: raw,
        max_calls_per_invocation=64,
    )
    return runner, args, calls


def test_partition_covers_every_original_character_and_message_once():
    original = messages(40, 900)
    segments = partition_messages(original, max_payload_chars=80000)
    assert len(segments) > 1
    restored = {message.id: [] for message in original}
    positions = {message.id: 0 for message in original}
    for segment in segments:
        assert len(segment.json_text) <= 80000
        for piece in segment.pieces:
            assert piece.start == positions[piece.message_id]
            assert piece.end - piece.start == len(piece.content)
            positions[piece.message_id] = piece.end
            restored[piece.message_id].append(piece.content)
    assert ["".join(restored[m.id]) for m in original] == [m.content for m in original]
    assert sum(s.covered_characters for s in segments) == sum(len(m.content) for m in original)


def test_one_huge_turn_has_contiguous_offsets_and_real_boundary_excerpts():
    original = messages(1, 1000)
    segments = partition_messages(original, max_payload_chars=700)
    assert len(segments) > 10
    for segment in segments:
        for piece in segment.pieces:
            assert piece.content == original[0].content[piece.start : piece.end]
            assert piece.content[-5:] in original[0].content
    assert "".join(p.content for s in segments for p in s.pieces) == original[0].content


def test_complete_run_retains_all_chunk_items_and_only_synthesizes_briefs(runtime):
    runner, args, calls = runtime
    result = runner.run(**args)
    assert result.complete and result.coverage.complete
    assert (
        result.coverage.completed_segments == result.coverage.total_segments == len(result.chunks)
    )
    assert (
        result.coverage.completed_messages
        == result.coverage.total_messages
        == len(args["messages"])
    )
    assert result.coverage.covered_characters == result.coverage.total_characters
    assert result.synthesis["decisions"] == [f"Segment {i}" for i in range(len(result.chunks))]
    assert len(calls) == result.coverage.provider_calls
    assert len([call for call in calls if call[0] == "chunk"]) == len(result.chunks)
    with runner._connect() as conn:
        outputs = " ".join(
            row[0] for row in conn.execute("SELECT result_json FROM context_chunk_checkpoints")
        )
        assert "Never checkpoint" not in outputs and "raw_model_trace" not in outputs
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_single_segment_does_not_require_a_synthesis_call(runtime):
    runner, args, calls = runtime
    result = runner.run(**(args | {"messages": messages(1, 3)}))
    assert result.coverage.total_segments == 1
    assert calls == [("chunk", 0)]
    assert result.synthesis == result.chunks[0]["brief"]


def test_invocation_pause_and_process_restart_reuse_committed_chunks(runtime):
    runner, args, calls = runtime
    with pytest.raises(PartialAnalysisError) as paused:
        runner.run(**(args | {"max_calls_per_invocation": 1}))
    assert paused.value.reason == "invocation_limit"
    assert paused.value.coverage.completed_segments == 1 and not paused.value.coverage.complete
    result = ChunkStore(runner.db_path).run(**args)
    assert result.complete
    assert calls.count(("chunk", 0)) == 1
    again = ChunkStore(runner.db_path).run(**args)
    assert again == result and len(calls) == result.coverage.provider_calls


def test_allowance_pause_is_pending_without_counting_an_unmade_call(runtime):
    runner, args, calls = runtime
    original = args["call_chunk"]

    def limited(segment):
        if segment.index == 1:
            raise AnalysisLimitError("Synthetic daily allowance reached")
        return original(segment)

    with pytest.raises(PartialAnalysisError) as paused:
        runner.run(**(args | {"call_chunk": limited}))
    assert paused.value.reason == "allowance"
    assert paused.value.coverage.provider_calls == 1
    assert paused.value.coverage.completed_segments == 1
    assert runner.run(**args).complete and calls.count(("chunk", 0)) == 1


def test_interruption_preserves_completed_checkpoints_and_never_commits_a_brief(runtime):
    runner, args, calls = runtime
    library = ContextLibraryStore(runner.db_path)
    original = args["call_chunk"]

    def interrupted(segment):
        if segment.index == 1:
            raise RuntimeError("Synthetic process interruption")
        return original(segment)

    with pytest.raises(RuntimeError, match="Synthetic process"):
        runner.run(**(args | {"call_chunk": interrupted}))
    assert library.count_briefs() == 0 and library.count_items() == 0
    saved = runner.progress_for_source(args["source_id"], args["source_fingerprint"], 1)
    assert saved["completed_segments"] == 1 and saved["state"] == "interrupted"
    assert runner.run(**args).complete and calls.count(("chunk", 0)) == 1
    assert library.count_briefs() == 0


@pytest.mark.parametrize("change", ["source", "model", "generation", "content"])
def test_changed_source_config_generation_or_content_never_reuses_old_checkpoints(runtime, change):
    runner, args, calls = runtime
    first = runner.run(**args)
    updated = dict(args)
    if change == "source":
        updated["source_fingerprint"] = "source-v2"
    if change == "model":
        updated["analysis_config_key"] = "model-v2"
    if change == "generation":
        updated["explicit_generation"] = 2
    if change == "content":
        updated["messages"] = [SimpleNamespace(**vars(m)) for m in args["messages"]]
        updated["messages"][0].content += "A new fact."
    second = runner.run(**updated)
    assert first.coverage.run_key != second.coverage.run_key
    assert calls.count(("chunk", 0)) == 2


def test_synthesis_checkpoint_resume_avoids_repeating_finished_reductions(runtime):
    runner, args, calls = runtime
    args = args | {"messages": messages(8, 120), "max_payload_chars": 1200}
    segments = partition_messages(args["messages"], max_payload_chars=1200)
    with pytest.raises(PartialAnalysisError) as paused:
        runner.run(**(args | {"max_calls_per_invocation": len(segments) + 1}))
    assert paused.value.coverage.completed_segments == len(segments)
    assert paused.value.coverage.completed_synthesis_steps == 1
    before = len(calls)
    result = ChunkStore(runner.db_path).run(**args)
    assert result.complete
    assert (
        len(calls) - before == result.coverage.provider_calls - paused.value.coverage.provider_calls
    )
    assert len([call for call in calls if call[0] == "chunk"]) == len(segments)


def test_total_call_cap_preserves_checkpoint_for_explicit_higher_limit(runtime):
    runner, args, calls = runtime
    with pytest.raises(PartialAnalysisError) as paused:
        runner.run(**(args | {"max_total_calls": 1}))
    assert paused.value.reason == "total_call_limit" and len(calls) == 1
    with pytest.raises(PartialAnalysisError):
        runner.run(**(args | {"max_total_calls": 1}))
    assert len(calls) == 1
    assert runner.run(**(args | {"max_total_calls": 64})).complete


def test_fabricated_or_unseen_evidence_is_rejected_before_checkpoint(runtime):
    runner, args, _ = runtime

    def invalid(raw, segment):
        value = normalized(segment)
        value["items"][0]["evidence"][0]["excerpt"] = "This is absent from the actual piece."
        return value

    with pytest.raises(ValueError, match="actually analyzed"):
        runner.run(**(args | {"normalize_chunk": invalid}))
    saved = runner.progress_for_source(args["source_id"], args["source_fingerprint"], 1)
    assert saved["completed_segments"] == 0


def test_progress_query_does_not_deserialize_private_outputs_and_delete_clears_checkpoints(
    runtime, monkeypatch
):
    runner, args, _ = runtime
    runner.run(**args)
    with monkeypatch.context() as patch:
        patch.setattr(
            json,
            "loads",
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("No output hydration")),
        )
        assert runner.progress_for_source(args["source_id"], args["source_fingerprint"], 1)[
            "complete"
        ]
    library = ContextLibraryStore(runner.db_path)
    deleted = ContextReviewStore(library).delete_library(confirmation="DELETE LIBRARY")
    assert deleted["deleted"]["analysis_checkpoints"] > 0
    assert runner.progress_for_source(args["source_id"], args["source_fingerprint"], 1) is None
    assert ArchiveStore(runner.db_path).get_conversation(args["source_id"]) is not None


def test_tuple_based_dataclass_normalization_is_serializable(runtime):
    runner, args, _ = runtime

    def immutable(raw, segment):
        value = normalized(segment)
        value["items"] = tuple(value["items"])
        value["brief"]["decisions"] = tuple(value["brief"]["decisions"])
        return value

    assert runner.run(**(args | {"normalize_chunk": immutable})).complete


def test_encrypted_roundtrip_preserves_partial_checkpoint_resume(runtime, tmp_path):
    from reweave.encrypted_backup import EncryptedBackupService

    runner, args, calls = runtime
    ContextLibraryStore(runner.db_path)
    with pytest.raises(PartialAnalysisError):
        runner.run(**(args | {"max_calls_per_invocation": 1}))
    artifact = tmp_path / "partial.reweave"
    service = EncryptedBackupService(runner.db_path, tmp_path / "profiles.json")
    service.backup_to(artifact, "synthetic checkpoint passphrase")
    restored_dir = tmp_path / "restored"
    restored_dir.mkdir()
    target = EncryptedBackupService(restored_dir / "library.db", restored_dir / "profiles.json")
    target.restore_from(artifact, "synthetic checkpoint passphrase", jobs_idle=True)
    restored = ChunkStore(target.db_path)
    progress = restored.progress_for_source(args["source_id"], args["source_fingerprint"], 1)
    assert progress["completed_segments"] == 1 and not progress["complete"]
    assert restored.run(**args).complete
    assert calls.count(("chunk", 0)) == 1


@pytest.mark.parametrize(
    "relationship", ["possible_duplicate", "possible_expansion", "possible_contradiction"]
)
def test_uncertain_semantic_relationships_are_reviewable_without_deleting_either_item(
    runtime, relationship
):
    from reweave.context_library import EvidenceInput, ScopeInput

    runner, args, _ = runtime
    archive = ArchiveStore(runner.db_path)
    source_message = archive.get_messages(args["source_id"])[0]
    library = ContextLibraryStore(runner.db_path)
    saved_brief = library.save_brief(
        conversation_id=args["source_id"],
        main_subject="Synthetic",
        user_goal="Resolve a relation",
        analysis_version="test",
        prompt_version="test",
        analysis_provider="synthetic",
        analysis_model="synthetic",
    )

    def item(text):
        return library.create_item(
            brief_id=saved_brief.id,
            canonical_text=text,
            item_type="decision",
            epistemic_kind="observed",
            confidence=0.99,
            scopes=[ScopeInput("project", "Synthetic")],
            evidence=[EvidenceInput(args["source_id"], source_message.id)],
        )

    first, second = item("One record."), item("A related record.")
    library.link_items(first.id, second.id, relationship)
    review = ContextReviewStore(library)
    row = review.inspect(library.get_item(first.id))
    assert row["state"] == "open" and row["related_items"][0]["relationship"] == relationship
    confirmed = review.confirm(first.id, expected_version=1, review_key=row["review_key"])
    assert confirmed["state"] == "open"
    resolved = review.resolve_link(
        first.id,
        expected_version=2,
        review_key=confirmed["review_key"],
        related_item_id=second.id,
        related_version=1,
        relationship=relationship,
        resolution="keep_both",
    )
    assert resolved["reasons"] == [] and library.count_items() == 2


def test_followup_is_checkpointed_and_counts_toward_source_cap(runtime):
    runner, args, calls = runtime
    completed = runner.run(**args)
    count = completed.coverage.provider_calls
    kwargs = dict(
        run_key=completed.coverage.run_key,
        input_fingerprint="valid-pairs-v1",
        call=lambda: {"matches": []},
        normalize=lambda value: value,
        max_total_calls=count + 1,
    )
    assert runner.run_followup(**kwargs) == {"matches": []}
    assert runner.coverage(completed.coverage.run_key).provider_calls == count + 1
    kwargs["call"] = lambda: pytest.fail("Completed follow-up must never be repeated")
    assert ChunkStore(runner.db_path).run_followup(**kwargs) == {"matches": []}
    with pytest.raises(ValueError, match="candidates changed"):
        runner.run_followup(**{**kwargs, "input_fingerprint": "different-pairs"})


def test_cached_brief_coverage_is_bound_to_its_analysis_configuration(runtime):
    runner, args, _ = runtime
    first = runner.run(**args)
    second = runner.run(**{**args, "analysis_config_key": "other-model"})
    selected = runner.progress_for_source(
        args["source_id"],
        args["source_fingerprint"],
        args["explicit_generation"],
        analysis_config_key=args["analysis_config_key"],
    )
    assert selected["run_key"] == first.coverage.run_key
    assert selected["run_key"] != second.coverage.run_key


@pytest.mark.parametrize(
    "error,reason",
    [(AnalysisLimitError, "allowance"), (ProviderConnectionChangedError, "connection_changed")],
)
def test_unsent_followup_does_not_consume_source_call_and_resumes(runtime, error, reason):
    runner, args, _ = runtime
    completed = runner.run(**args)
    count = completed.coverage.provider_calls

    def denied():
        raise error("Synthetic pre-send denial")

    kwargs = dict(
        run_key=completed.coverage.run_key,
        input_fingerprint="pairs",
        call=denied,
        normalize=lambda value: value,
        max_total_calls=count + 1,
    )
    with pytest.raises(PartialAnalysisError) as paused:
        runner.run_followup(**kwargs)
    assert paused.value.reason == reason and paused.value.coverage.provider_calls == count
    runner.run(**{**args, "call_chunk": lambda _: pytest.fail("Source must be reused")})
    assert runner.run_followup(**{**kwargs, "call": lambda: {"matches": []}}) == {"matches": []}
    assert runner.coverage(completed.coverage.run_key).provider_calls == count + 1


def test_failed_followup_attempt_still_consumes_source_cap(runtime):
    runner, args, _ = runtime
    completed = runner.run(**args)
    count = completed.coverage.provider_calls

    def interrupted():
        raise RuntimeError("Unknown provider response")

    kwargs = dict(
        run_key=completed.coverage.run_key,
        input_fingerprint="pairs",
        call=interrupted,
        normalize=lambda value: value,
        max_total_calls=count + 1,
    )
    with pytest.raises(RuntimeError, match="Unknown"):
        runner.run_followup(**kwargs)
    with pytest.raises(PartialAnalysisError) as paused:
        runner.run_followup(**{**kwargs, "call": lambda: pytest.fail("Cap must stop another call")})
    assert paused.value.reason == "total_call_limit"
    assert paused.value.coverage.provider_calls == count + 1


def test_unsent_chunk_connection_change_preserves_previous_checkpoint(runtime):
    runner, args, calls = runtime
    original = args["call_chunk"]

    def guarded(segment):
        if segment.index == 1:
            raise ProviderConnectionChangedError("Synthetic provider change")
        return original(segment)

    with pytest.raises(PartialAnalysisError) as paused:
        runner.run(**{**args, "call_chunk": guarded})
    assert paused.value.reason == "connection_changed"
    assert paused.value.coverage.provider_calls == 1
    result = runner.run(**args)
    assert result.complete and calls.count(("chunk", 0)) == 1
