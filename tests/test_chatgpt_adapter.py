from continuity_mcp.providers.chatgpt import parse_chatgpt_export


def test_parser_preserves_branch_graph_and_content():
    data = [
        {
            "id": "conv-1",
            "title": "Branch test",
            "create_time": 1.0,
            "mapping": {
                "node-user": {
                    "parent": None,
                    "children": ["node-a", "node-b"],
                    "message": {
                        "id": "msg-user",
                        "author": {"role": "user"},
                        "create_time": 2.0,
                        "content": {"parts": ["Pick a path"]},
                    },
                },
                "node-a": {
                    "parent": "node-user",
                    "children": [],
                    "message": {
                        "id": "msg-a",
                        "author": {"role": "assistant"},
                        "create_time": 3.0,
                        "content": {"parts": ["Path A"]},
                    },
                },
            },
        }
    ]

    conversations = parse_chatgpt_export(data)

    assert len(conversations) == 1
    conversation = conversations[0]
    assert conversation.conversation_id == "conv-1"
    assert len(conversation.messages) == 2

    first = conversation.messages[0]
    assert first.message_id == "msg-user"
    assert first.content == "Pick a path"
    assert first.children_ids == ("node-a", "node-b")

    second = conversation.messages[1]
    assert second.parent_id == "node-user"


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
    assert message.raw
