import json

from continuity_mcp.providers.chatgpt import (
    iter_chatgpt_export,
    parse_chatgpt_export,
)


def _sample_export():
    return [
        {
            "id": "conv-1",
            "title": "Branch test",
            "create_time": 1.0,
            "mapping": {
                "root": {
                    "parent": None,
                    "children": ["node-user"],
                    "message": None,
                },
                "node-user": {
                    "parent": "root",
                    "children": ["bridge", "node-b", "missing-node"],
                    "message": {
                        "id": "msg-user",
                        "author": {"role": "user"},
                        "create_time": 2.0,
                        "content": {"parts": ["Pick a path"]},
                    },
                },
                "bridge": {
                    "parent": "node-user",
                    "children": ["node-a"],
                    "message": None,
                },
                "node-a": {
                    "parent": "bridge",
                    "children": [],
                    "message": {
                        "id": "msg-a",
                        "author": {"role": "assistant"},
                        "create_time": 3.0,
                        "content": {"parts": ["Path A"]},
                    },
                },
                "node-b": {
                    "parent": "node-user",
                    "children": [],
                    "message": {
                        "id": "msg-b",
                        "author": {"role": "assistant"},
                        "create_time": 4.0,
                        "content": {"parts": ["Path B"]},
                    },
                },
            },
        }
    ]

def test_parser_preserves_branch_graph_and_provider_identity():
    conversations = parse_chatgpt_export(_sample_export())

    assert len(conversations) == 1
    conversation = conversations[0]
    assert conversation.conversation_id == "conv-1"
    assert len(conversation.messages) == 3

    first = conversation.messages[0]
    assert first.message_id == "node-user"
    assert first.provider_message_id == "msg-user"
    assert first.content == "Pick a path"
    assert first.parent_id is None
    assert first.children_ids == ("node-a", "node-b")

    second = conversation.messages[1]
    assert second.message_id == "node-a"
    assert second.provider_message_id == "msg-a"
    assert second.parent_id == "node-user"

    third = conversation.messages[2]
    assert third.message_id == "node-b"
    assert third.parent_id == "node-user"


def test_streaming_parser_matches_in_memory_parser(tmp_path):
    path = tmp_path / "conversations.json"
    path.write_text(json.dumps(_sample_export()), encoding="utf-8")

    streamed = list(iter_chatgpt_export(path))
    in_memory = parse_chatgpt_export(_sample_export())

    assert streamed == in_memory


def test_parser_retains_non_string_parts_as_searchable_json():
    data = [
        {
            "id": "conv-2",
            "mapping": {
                "n": {
                    "message": {
                        "id": "m",
                        "author": {"role": "assistant"},
                        "content": {"parts": [{"kind": "tool", "value": 42}]},
                    }
                }
            },
        }
    ]
    message = parse_chatgpt_export(data)[0].messages[0]
    assert '"kind": "tool"' in message.content
