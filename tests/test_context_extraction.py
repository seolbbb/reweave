"""Source-grounded Context extraction and normalization tests."""

import json

import pytest

from reweave.archive import ArchiveStore
from reweave.context_extraction import (
    CONTEXT_EXTRACTION_PROMPT_VERSION,
    extract_context_from_conversation,
    normalize_context_extraction,
)
from reweave.context_library import ContextLibraryStore, EvidenceInput, ScopeInput
from reweave.llm import LLMSettings


class FakeJsonProvider:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def generate_json(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def _archive_fixture(tmp_path, fixtures_dir):
    db_path = tmp_path / "archive.db"
    archive = ArchiveStore(db_path)
    archive.import_directory(fixtures_dir)
    conversation_id = archive.search("Obsidian", provider="claude", limit=1)[0].conversation_id
    conversation = archive.get_conversation(conversation_id)
    messages = archive.get_messages(conversation_id)
    assert conversation is not None
    return db_path, archive, ContextLibraryStore(db_path), conversation, messages


def _settings():
    return LLMSettings(provider="openai", model="test-model", api_key="test-key")


def _brief():
    return {
        "main_subject": "Organizing an Obsidian vault",
        "user_goal": "Choose a maintainable structure for notes.",
        "important_outcomes": ["Links should carry specific relationships."],
        "decisions": [],
        "lessons": ["Folders and links serve different navigation needs."],
        "unresolved_questions": ["How much metadata should be required?"],
        "actions": ["Try the structure with one project."],
    }


def _valid_observed_item():
    return {
        "canonical_text": "The user is organizing an Obsidian vault.",
        "type": "project_fact",
        "epistemic_kind": "observed",
        "confidence": 0.96,
        "sensitivity": "normal",
        "scopes": [{"type": "project", "key": "Obsidian", "confidence": 0.95}],
        "evidence": [
            {
                "message_index": 0,
                "excerpt": "How should I organize my Obsidian vault?",
                "relationship": "supports",
            }
        ],
    }


def test_extracts_brief_and_items_with_untrusted_prompt_and_idempotent_reuse(
    tmp_path, fixtures_dir
):
    db_path, archive, context, conversation, messages = _archive_fixture(tmp_path, fixtures_dir)
    provider = FakeJsonProvider(
        {
            "brief": _brief(),
            "items": [
                _valid_observed_item(),
                {
                    "canonical_text": "A linked-note structure may stay easier to maintain.",
                    "type": "lesson",
                    "epistemic_kind": "observed",
                    "confidence": 0.72,
                    "scopes": [{"type": "topic", "key": "Knowledge management"}],
                    "evidence": [
                        {
                            "message_index": 1,
                            "excerpt": "Let links create the structure rather than folders.",
                            "relationship": "supports",
                        }
                    ],
                },
            ],
        }
    )

    result = extract_context_from_conversation(
        archive,
        context,
        conversation_id=conversation.id,
        settings=_settings(),
        analysis_mode="project",
        provider=provider,
    )

    assert result.brief.analysis_status == "complete"
    assert len(result.brief.source_fingerprint) == 64
    assert result.brief.main_subject == "Organizing an Obsidian vault"
    assert result.analysis_version == f"{CONTEXT_EXTRACTION_PROMPT_VERSION}:project"
    assert len(result.items) == 2
    assert result.items[0].epistemic_kind == "observed"
    assert result.items[0].last_confirmed_at == messages[0].timestamp
    assert result.items[1].epistemic_kind == "suggested"
    assert result.items[1].sensitivity == "sensitive"
    assert "untrusted data" in provider.calls[0]["system"].lower()
    assert "Do not turn an assistant recommendation" in provider.calls[0]["system"]
    assert "<untrusted_source_conversation_json>" in provider.calls[0]["user"]
    assert provider.calls[0]["temperature"] == 0.0

    reopened = ContextLibraryStore(db_path)
    stored = reopened.get_brief_for_analysis(conversation.id, result.analysis_version)
    assert stored is not None
    assert stored.context_item_ids == tuple(item.id for item in result.items)

    reused = extract_context_from_conversation(
        archive,
        reopened,
        conversation_id=conversation.id,
        settings=_settings(),
        analysis_mode="project",
        provider=provider,
    )
    assert reused.reused_existing is True
    assert tuple(item.id for item in reused.items) == tuple(item.id for item in result.items)
    assert len(provider.calls) == 1


def test_changed_source_replaces_stale_analysis_instead_of_reusing_it(tmp_path, fixtures_dir):
    db_path, archive, context, conversation, _ = _archive_fixture(tmp_path, fixtures_dir)
    first_provider = FakeJsonProvider({"brief": _brief(), "items": [_valid_observed_item()]})
    first = extract_context_from_conversation(
        archive,
        context,
        conversation_id=conversation.id,
        settings=_settings(),
        provider=first_provider,
    )
    first_item_id = first.items[0].id

    fixture = json.loads((fixtures_dir / "claude_sample.json").read_text(encoding="utf-8"))
    source = [fixture[0]]
    source[0]["updated_at"] = "2026-02-10T11:00:00Z"
    source[0]["chat_messages"][0]["text"] = "How should I organize my Obsidian vault for a team?"
    changed_path = tmp_path / "changed-claude-export.json"
    changed_path.write_text(json.dumps(source), encoding="utf-8")
    summary = archive.import_path(changed_path)
    assert summary.updated_conversations == 1
    assert summary.updated_messages == 1

    changed_item = _valid_observed_item()
    changed_item["canonical_text"] = "The user is organizing a team Obsidian vault."
    changed_item["evidence"] = [
        {
            "message_index": 0,
            "excerpt": "How should I organize my Obsidian vault for a team?",
            "relationship": "supports",
        }
    ]
    second_provider = FakeJsonProvider({"brief": _brief(), "items": [changed_item]})

    second = extract_context_from_conversation(
        archive,
        context,
        conversation_id=conversation.id,
        settings=_settings(),
        provider=second_provider,
    )

    assert second.reused_existing is False
    assert len(second_provider.calls) == 1
    assert second.brief.id == first.brief.id
    assert second.brief.source_fingerprint != first.brief.source_fingerprint
    assert context.get_item(first_item_id) is None
    assert second.items[0].canonical_text == "The user is organizing a team Obsidian vault."


def test_zero_context_items_still_saves_a_complete_brief(tmp_path, fixtures_dir):
    _, archive, context, conversation, _ = _archive_fixture(tmp_path, fixtures_dir)
    provider = FakeJsonProvider({"brief": _brief(), "items": []})

    result = extract_context_from_conversation(
        archive,
        context,
        conversation_id=conversation.id,
        settings=_settings(),
        provider=provider,
    )

    assert result.brief.analysis_status == "complete"
    assert result.brief.context_item_ids == ()
    assert result.items == ()
    assert context.list_briefs()[0].main_subject == "Organizing an Obsidian vault"


def test_invalid_items_are_dropped_without_discarding_the_brief(tmp_path, fixtures_dir):
    _, archive, context, conversation, _ = _archive_fixture(tmp_path, fixtures_dir)
    fabricated = _valid_observed_item()
    fabricated["canonical_text"] = "Fabricated evidence"
    fabricated["evidence"] = [
        {
            "message_index": 0,
            "excerpt": "This exact text is absent from the source.",
            "relationship": "supports",
        }
    ]
    missing_scope = _valid_observed_item()
    missing_scope["canonical_text"] = "Missing scope"
    missing_scope["scopes"] = []
    invalid_confidence = _valid_observed_item()
    invalid_confidence["canonical_text"] = "Invalid confidence"
    invalid_confidence["confidence"] = 1.5
    provider = FakeJsonProvider(
        {
            "brief": _brief(),
            "items": [
                _valid_observed_item(),
                fabricated,
                missing_scope,
                invalid_confidence,
            ],
        }
    )

    result = extract_context_from_conversation(
        archive,
        context,
        conversation_id=conversation.id,
        settings=_settings(),
        provider=provider,
    )

    assert result.dropped_items == 3
    assert len(result.items) == 1
    assert result.items[0].canonical_text == "The user is organizing an Obsidian vault."


def test_normalization_merges_exact_duplicate_items_and_evidence(tmp_path, fixtures_dir):
    _, archive, _, conversation, messages = _archive_fixture(tmp_path, fixtures_dir)
    duplicate = _valid_observed_item()
    duplicate["canonical_text"] = "  THE USER IS ORGANIZING AN OBSIDIAN VAULT.  "
    duplicate["confidence"] = 0.8
    duplicate["scopes"] = [{"type": "topic", "key": "Knowledge management"}]
    duplicate["evidence"] = [
        {
            "message_index": 2,
            "excerpt": "What about tags vs links?",
            "relationship": "context",
        }
    ]

    normalized = normalize_context_extraction(
        {"brief": _brief(), "items": [_valid_observed_item(), duplicate]},
        archive.get_messages(conversation.id),
    )

    assert normalized.deduplicated_items == 1
    assert len(normalized.items) == 1
    assert len(normalized.items[0].evidence) == 2
    assert {scope.scope_type for scope in normalized.items[0].scopes} == {"project", "topic"}
    assert normalized.items[0].last_confirmed_at == messages[2].timestamp


def test_invalid_brief_fails_before_any_context_is_saved(tmp_path, fixtures_dir):
    _, archive, context, conversation, _ = _archive_fixture(tmp_path, fixtures_dir)
    provider = FakeJsonProvider({"brief": {"main_subject": "Missing user goal"}, "items": []})

    with pytest.raises(ValueError, match="user goal"):
        extract_context_from_conversation(
            archive,
            context,
            conversation_id=conversation.id,
            settings=_settings(),
            provider=provider,
        )

    assert context.list_briefs() == []


def test_failed_pending_analysis_is_replaced_on_retry(tmp_path, fixtures_dir):
    _, archive, context, conversation, messages = _archive_fixture(tmp_path, fixtures_dir)
    analysis_version = f"{CONTEXT_EXTRACTION_PROMPT_VERSION}:auto"
    pending = context.save_brief(
        conversation_id=conversation.id,
        main_subject="Partial brief",
        user_goal="Recover from an interrupted save.",
        analysis_version=analysis_version,
        prompt_version=CONTEXT_EXTRACTION_PROMPT_VERSION,
        analysis_provider="openai",
        analysis_model="test-model",
        analysis_status="pending",
    )
    stale_item = context.create_item(
        brief_id=pending.id,
        canonical_text="Partial item that should be replaced.",
        item_type="insight",
        epistemic_kind="observed",
        confidence=0.5,
        scopes=[ScopeInput("project", "Obsidian")],
        evidence=[EvidenceInput(conversation.id, messages[0].id)],
    )
    provider = FakeJsonProvider({"brief": _brief(), "items": [_valid_observed_item()]})

    result = extract_context_from_conversation(
        archive,
        context,
        conversation_id=conversation.id,
        settings=_settings(),
        provider=provider,
    )

    assert result.brief.id == pending.id
    assert result.brief.analysis_status == "complete"
    assert context.get_item(stale_item.id) is None
    assert len(result.items) == 1
