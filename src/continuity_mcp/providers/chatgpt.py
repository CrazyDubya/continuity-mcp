from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from continuity_mcp.models import CanonicalConversation, CanonicalMessage


PROVIDER = "chatgpt"


def _content_to_text(content: Any) -> str:
    """Produce searchable text without discarding non-string content.

    The exact source object remains in raw; this field is only the canonical
    searchable representation.
    """
    if not isinstance(content, dict):
        return "" if content is None else str(content)

    parts = content.get("parts")
    if isinstance(parts, list):
        rendered: list[str] = []
        for part in parts:
            if isinstance(part, str):
                rendered.append(part)
            elif part is not None:
                rendered.append(json.dumps(part, ensure_ascii=False, sort_keys=True))
        return "\n".join(rendered)

    text = content.get("text")
    if isinstance(text, str):
        return text

    return json.dumps(content, ensure_ascii=False, sort_keys=True)


def parse_chatgpt_export(data: Any) -> list[CanonicalConversation]:
    """Parse ChatGPT conversations.json data into provider-neutral records.

    Parent/child identifiers are preserved so branched conversations remain a
    graph rather than being flattened into a single guessed transcript.
    """
    if not isinstance(data, list):
        raise ValueError("ChatGPT export must be a JSON array of conversations")

    conversations: list[CanonicalConversation] = []

    for raw_conversation in data:
        if not isinstance(raw_conversation, dict):
            continue

        conversation_id = raw_conversation.get("id")
        if not conversation_id:
            continue

        title = raw_conversation.get("title") or "Untitled conversation"
        mapping = raw_conversation.get("mapping") or {}
        messages: list[CanonicalMessage] = []

        if isinstance(mapping, dict):
            for node_id, node in mapping.items():
                if not isinstance(node, dict):
                    continue
                raw_message = node.get("message")
                if not isinstance(raw_message, dict):
                    continue

                # ChatGPT branch edges reference mapping node IDs, not the
                # nested message.id value. Use the node ID as canonical graph
                # identity and retain the complete nested message in raw.
                message_id = node_id
                author = raw_message.get("author") or {}
                role = author.get("role") if isinstance(author, dict) else None

                children = node.get("children") or []
                if not isinstance(children, list):
                    children = []

                messages.append(
                    CanonicalMessage(
                        provider=PROVIDER,
                        conversation_id=str(conversation_id),
                        message_id=str(message_id),
                        role=role,
                        content=_content_to_text(raw_message.get("content")),
                        created_at=raw_message.get("create_time"),
                        updated_at=raw_message.get("update_time"),
                        parent_id=node.get("parent"),
                        children_ids=tuple(str(x) for x in children),
                        raw={"node_id": node_id, "node": node},
                    )
                )

        messages.sort(
            key=lambda m: (
                m.created_at is None,
                m.created_at if m.created_at is not None else 0,
                m.message_id,
            )
        )

        conversations.append(
            CanonicalConversation(
                provider=PROVIDER,
                conversation_id=str(conversation_id),
                title=str(title),
                messages=tuple(messages),
                created_at=raw_conversation.get("create_time"),
                updated_at=raw_conversation.get("update_time"),
                raw=raw_conversation,
            )
        )

    return conversations


def load_chatgpt_export(path: str | Path) -> list[CanonicalConversation]:
    path = Path(path)
    with path.open("r", encoding="utf-8") as handle:
        return parse_chatgpt_export(json.load(handle))
