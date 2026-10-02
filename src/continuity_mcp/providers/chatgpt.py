from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import ijson

from continuity_mcp.models import CanonicalConversation, CanonicalMessage


PROVIDER = "chatgpt"


def _timestamp(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _content_to_text(content: Any) -> str:
    """Produce searchable text without discarding non-string content.

    The exact source bytes live in the managed source store. This projection is
    rebuildable and exists only for canonical retrieval/indexing.
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


def _parse_conversation(raw_conversation: Any) -> CanonicalConversation | None:
    if not isinstance(raw_conversation, dict):
        return None

    conversation_id = raw_conversation.get("id")
    if not conversation_id:
        return None

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

            author = raw_message.get("author") or {}
            role = author.get("role") if isinstance(author, dict) else None

            children = node.get("children") or []
            if not isinstance(children, list):
                children = []

            provider_message_id = raw_message.get("id")

            messages.append(
                CanonicalMessage(
                    provider=PROVIDER,
                    conversation_id=str(conversation_id),
                    # ChatGPT branch edges reference mapping node IDs, not the
                    # nested message.id value. The node ID is therefore the
                    # canonical source identity for graph traversal.
                    message_id=str(node_id),
                    provider_message_id=(
                        str(provider_message_id) if provider_message_id else None
                    ),
                    role=role,
                    content=_content_to_text(raw_message.get("content")),
                    created_at=_timestamp(raw_message.get("create_time")),
                    updated_at=_timestamp(raw_message.get("update_time")),
                    parent_id=(
                        str(node.get("parent")) if node.get("parent") is not None else None
                    ),
                    children_ids=tuple(str(item) for item in children),
                    raw={"node_id": node_id, "node": node},
                )
            )

    messages.sort(
        key=lambda message: (
            message.created_at is None,
            message.created_at if message.created_at is not None else 0,
            message.message_id,
        )
    )

    return CanonicalConversation(
        provider=PROVIDER,
        conversation_id=str(conversation_id),
        title=str(title),
        messages=tuple(messages),
        created_at=_timestamp(raw_conversation.get("create_time")),
        updated_at=_timestamp(raw_conversation.get("update_time")),
        raw=raw_conversation,
    )


def parse_chatgpt_export(data: Any) -> list[CanonicalConversation]:
    """Parse an in-memory ChatGPT conversations.json value.

    This helper exists mainly for tests and callers that already hold JSON in
    memory. Full archive imports should use iter_chatgpt_export so processing is
    bounded by one conversation at a time.
    """
    if not isinstance(data, list):
        raise ValueError("ChatGPT export must be a JSON array of conversations")

    parsed: list[CanonicalConversation] = []
    for raw_conversation in data:
        conversation = _parse_conversation(raw_conversation)
        if conversation is not None:
            parsed.append(conversation)
    return parsed


def iter_chatgpt_export(path: str | Path) -> Iterator[CanonicalConversation]:
    """Stream a ChatGPT conversations.json file one conversation at a time."""
    source = Path(path)
    with source.open("rb") as handle:
        for raw_conversation in ijson.items(handle, "item", use_float=True):
            conversation = _parse_conversation(raw_conversation)
            if conversation is not None:
                yield conversation
