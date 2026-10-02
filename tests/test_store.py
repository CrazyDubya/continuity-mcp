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
                role="user",
                content="Mara needs selective episodic memory",
            ),
            CanonicalMessage(
                provider="chatgpt",
                conversation_id="c1",
                message_id="m2",
                role="assistant",
                content="Keep canon and episodic memory separate",
                parent_id="m1",
            ),
        ),
        raw={"id": "c1"},
    )


def test_import_search_and_reimport_are_idempotent(tmp_path):
    store = ArchiveStore(tmp_path / "archive.sqlite3")

    first = store.import_conversations([_conversation()])
    second = store.import_conversations([_conversation()])

    assert first == {"conversations": 1, "messages": 2}
    assert second == {"conversations": 1, "messages": 2}
    assert store.status()["conversations"] == 1
    assert store.status()["messages"] == 2

    hits = store.search("episodic memory")
    assert len(hits) == 2
    assert hits[0]["conversation_id"] == "chatgpt:c1"

    conversation = store.conversation("chatgpt:c1")
    assert conversation is not None
    assert len(conversation["messages"]) == 2
    assert conversation["messages"][1]["parent_message_id"] == "chatgpt:c1:m1"
