"""Whole-conversation capture contract tests."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from reweave.archive import ArchiveStore
from reweave.conversation_capture import ConversationCapture
from reweave.web import create_app


def _payload(provider: str = "chatgpt") -> dict:
    return {
        "provider": provider,
        "external_id": f"{provider}-conversation-42",
        "title": f"{provider.title()} capture",
        "created_at": "2026-07-21T09:00:00Z",
        "updated_at": "2026-07-21T09:05:00+00:00",
        "messages": [
            {
                "external_id": f"{provider}-message-1",
                "role": "user",
                "content": "Keep this exact captured question.\n",
                "timestamp": "2026-07-21T09:00:00Z",
            },
            {
                "external_id": f"{provider}-message-2",
                "role": "assistant",
                "content": "This answer is stored locally before analysis.",
                "timestamp": "2026-07-21T09:00:30Z",
            },
        ],
    }


@pytest.mark.parametrize("provider", ["chatgpt", "claude"])
def test_capture_api_persists_supported_provider_without_llm_key(tmp_path, provider):
    db_path = tmp_path / "archive.db"
    client = TestClient(create_app(db_path, data_dir=tmp_path / "app-data"))

    response = client.post("/api/capture/conversations", json=_payload(provider))

    assert response.status_code == 200
    result = response.json()
    assert result["provider"] == provider
    assert result["outcome"] == "created"
    assert result["message_count"] == 2
    assert result["inserted_messages"] == 2

    reopened = ArchiveStore(db_path)
    conversation = reopened.get_conversation(result["conversation_id"])
    messages = reopened.get_messages(result["conversation_id"])
    assert conversation is not None
    assert conversation.source == provider
    assert conversation.source_id == f"{provider}-conversation-42"
    assert conversation.title == f"{provider.title()} capture"
    assert conversation.created_at == "2026-07-21T09:00:00Z"
    assert conversation.updated_at == "2026-07-21T09:05:00+00:00"
    assert conversation.source_path.startswith(f"capture://{provider}/")
    assert [message.index for message in messages] == [0, 1]
    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[0].content == "Keep this exact captured question.\n"
    assert messages[0].source_id == f"{provider}-message-1"


def test_repeated_capture_updates_in_place_then_becomes_unchanged(tmp_path):
    db_path = tmp_path / "archive.db"
    client = TestClient(create_app(db_path, data_dir=tmp_path / "app-data"))
    payload = _payload("claude")
    created = client.post("/api/capture/conversations", json=payload).json()

    payload["title"] = "Updated Claude capture"
    payload["updated_at"] = "2026-07-21T09:10:00Z"
    payload["messages"][1]["content"] = "Updated locally with the same message identity."
    payload["messages"].append(
        {
            "external_id": "claude-message-3",
            "role": "user",
            "content": "Append one more ordered message.",
            "timestamp": "2026-07-21T09:10:00Z",
        }
    )
    updated = client.post("/api/capture/conversations", json=payload)
    unchanged = client.post("/api/capture/conversations", json=payload)

    assert updated.status_code == 200
    assert unchanged.status_code == 200
    assert updated.json()["conversation_id"] == created["conversation_id"]
    assert updated.json()["outcome"] == "updated"
    assert updated.json()["inserted_messages"] == 1
    assert updated.json()["updated_messages"] == 1
    assert unchanged.json()["outcome"] == "unchanged"
    assert unchanged.json()["inserted_messages"] == 0
    assert unchanged.json()["updated_messages"] == 0

    reopened = ArchiveStore(db_path)
    conversation = reopened.get_conversation(created["conversation_id"])
    messages = reopened.get_messages(created["conversation_id"])
    assert conversation is not None
    assert conversation.title == "Updated Claude capture"
    assert len(messages) == 3
    assert messages[1].content == "Updated locally with the same message identity."
    assert reopened.search("Append one more ordered message")[0].conversation_id == conversation.id


def test_invalid_capture_is_rejected_without_partial_archive_writes(tmp_path):
    db_path = tmp_path / "archive.db"
    client = TestClient(create_app(db_path, data_dir=tmp_path / "app-data"))
    payload = _payload()
    payload["messages"][1]["content"] = "   "

    response = client.post("/api/capture/conversations", json=payload)

    assert response.status_code == 422
    stats = ArchiveStore(db_path).stats()
    assert stats.total_conversations == 0
    assert stats.total_messages == 0

    payload["messages"] = []
    empty_response = client.post("/api/capture/conversations", json=payload)
    assert empty_response.status_code == 422
    assert ArchiveStore(db_path).stats().total_conversations == 0


def test_capture_model_rejects_duplicate_message_identity_and_naive_time():
    duplicate = _payload()
    duplicate["messages"][1]["external_id"] = duplicate["messages"][0]["external_id"]
    with pytest.raises(ValidationError, match="must be unique"):
        ConversationCapture.model_validate(duplicate)

    naive_time = _payload()
    naive_time["created_at"] = "2026-07-21T09:00:00"
    with pytest.raises(ValidationError, match="timezone offset"):
        ConversationCapture.model_validate(naive_time)
