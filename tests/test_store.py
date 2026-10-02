import os
import stat

from continuity_mcp.models import CanonicalConversation, CanonicalMessage
from continuity_mcp.store import ArchiveStore


def _conversation() -> CanonicalConversation:
    return CanonicalConversation(
        provider="chatgpt",
        conversation_id="c1",
        title="Memory architecture",
        messages=(
            CanonicalMessage(
                provider="chatgpt",
                conversation_id="c1",
                message_id="m1",
                provider_message_id="provider-m1",
                role="user",
                content="Mara needs selective episodic memory",
                children_ids=("m2",),
            ),
            CanonicalMessage(
                provider="chatgpt",
                conversation_id="c1",
                message_id="m2",
                provider_message_id="provider-m2",
                role="assistant",
                content="Keep canon and episodic memory separate",
                parent_id="m1",
            ),
        ),
    )


def test_source_ingest_is_exact_and_content_addressed(tmp_path):
    store = ArchiveStore(tmp_path / "archive.sqlite3")
    source_file = tmp_path / "conversations.json"
    source_bytes = b'[{"id":"c1","text":"exact bytes"}]\n'
    source_file.write_bytes(source_bytes)

    source = store.ingest_source(source_file, provider="chatgpt")
    duplicate = store.ingest_source(source_file, provider="chatgpt")

    assert source.sha256 == duplicate.sha256
    assert source.id == duplicate.id
    assert source.path.read_bytes() == source_bytes
    assert source.path.parent == tmp_path / "sources"

    if os.name != "nt":
        assert stat.S_IMODE(source.path.stat().st_mode) == 0o600
        assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
        assert stat.S_IMODE(source.path.parent.stat().st_mode) == 0o700


def test_import_search_pagination_and_reimport_are_idempotent(tmp_path):
    store = ArchiveStore(tmp_path / "archive.sqlite3")

    first = store.import_conversations([_conversation()])
    second = store.import_conversations([_conversation()])

    assert first == {
        "conversations": 1,
        "messages": 2,
        "duplicate_source": False,
    }
    assert second == {
        "conversations": 1,
        "messages": 2,
        "duplicate_source": False,
    }

    status = store.status()
    assert status["schema_version"] == 1
    assert status["conversations"] == 1
    assert status["messages"] == 2
    assert "database" not in status

    hits = store.search("episodic memory")
    assert len(hits) == 2
    assert hits[0]["conversation_id"] == "chatgpt:c1"
    assert "snippet" in hits[0]
    assert "content" not in hits[0]

    conversation = store.conversation(
        "chatgpt:c1",
        limit=1,
        max_chars_per_message=256,
    )
    assert conversation is not None
    assert conversation["message_count"] == 2
    assert conversation["has_more"] is True
    assert len(conversation["messages"]) == 1
    first_message = conversation["messages"][0]
    assert first_message["children_ids"] == ["chatgpt:c1:m2"]
    assert first_message["content_truncated"] is False

    second_page = store.conversation("chatgpt:c1", offset=1, limit=1)
    assert second_page is not None
    assert second_page["messages"][0]["parent_message_id"] == "chatgpt:c1:m1"


def test_message_slices_large_content_without_losing_exact_text(tmp_path):
    store = ArchiveStore(tmp_path / "archive.sqlite3")
    content = "abcdefghijklmnopqrstuvwxyz" * 30
    conversation = CanonicalConversation(
        provider="chatgpt",
        conversation_id="large",
        title="Large message",
        messages=(
            CanonicalMessage(
                provider="chatgpt",
                conversation_id="large",
                message_id="m1",
                role="assistant",
                content=content,
            ),
        ),
    )
    store.import_conversations([conversation])

    first = store.message("chatgpt:large:m1", max_chars=256)
    assert first is not None
    assert first["content"] == content[:256]
    assert first["next_start_char"] == 256

    second = store.message(
        "chatgpt:large:m1",
        start_char=first["next_start_char"],
        max_chars=256,
    )
    assert second is not None
    assert second["content"] == content[256:512]



def test_duplicate_managed_source_skips_parser_iteration(tmp_path):
    store = ArchiveStore(tmp_path / "archive.sqlite3")
    source_file = tmp_path / "conversations.json"
    source_file.write_text("[]", encoding="utf-8")
    source = store.ingest_source(source_file, provider="chatgpt")

    first = store.import_conversations([_conversation()], source_id=source.id)
    assert first["duplicate_source"] is False

    def must_not_iterate():
        raise AssertionError("duplicate source should not be reparsed")
        yield  # pragma: no cover

    duplicate = store.import_conversations(must_not_iterate(), source_id=source.id)
    assert duplicate == {
        "conversations": 0,
        "messages": 0,
        "duplicate_source": True,
    }


def test_canonical_ids_escape_provider_native_colons(tmp_path):
    store = ArchiveStore(tmp_path / "archive.sqlite3")
    conversation = CanonicalConversation(
        provider="chatgpt",
        conversation_id="conv:with:colons",
        title="Collision safety",
        messages=(
            CanonicalMessage(
                provider="chatgpt",
                conversation_id="conv:with:colons",
                message_id="node:1",
                role="user",
                content="safe id",
            ),
        ),
    )

    store.import_conversations([conversation])

    hits = store.search("safe id")
    assert hits[0]["conversation_id"] == "chatgpt:conv%3Awith%3Acolons"
    assert hits[0]["message_id"] == "chatgpt:conv%3Awith%3Acolons:node%3A1"
