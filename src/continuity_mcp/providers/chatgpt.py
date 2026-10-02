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

def _message_parent(mapping: dict[str, Any], node: dict[str, Any]) -> str | None:
    """Return the nearest message-bearing ancestor, skipping structural nodes."""
    parent_id = node.get("parent")
    seen: set[str] = set()

    while parent_id is not None:
        parent_key = str(parent_id)
        if parent_key in seen:
            return None
        seen.add(parent_key)

        parent = mapping.get(parent_key)
        if not isinstance(parent, dict):
            return None
        if isinstance(parent.get("message"), dict):
            return parent_key
        parent_id = parent.get("parent")

    return None


def _message_children(mapping: dict[str, Any], node: dict[str, Any]) -> tuple[str, ...]:
    """Return nearest message-bearing descendants, skipping structural nodes."""
    pending = list(node.get("children") or [])
    resolved: list[str] = []
    seen: set[str] = set()

    while pending:
        child_key = str(pending.pop(0))
        if child_key in seen:
            continue
        seen.add(child_key)

        child = mapping.get(child_key)
        if not isinstance(child, dict):
            continue
        if isinstance(child.get("message"), dict):
            resolved.append(child_key)
            continue

        grandchildren = child.get("children") or []
        if isinstance(grandchildren, list):
            pending.extend(grandchildren)

    return tuple(resolved)


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
                    parent_id=_message_parent(mapping, node),
                    children_ids=_message_children(mapping, node),
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
    )

def parse_chatgpt_export(data: Any) -> list[CanonicalConversation]:
    """Parse an in-memory ChatGPT conversations.json value.

    This helper exists mainly for tests and callers that already hold JSON in
    memory. Full archive imports should use iter_chatgpt_export so processing is
    bounded by one conversation at a time.
    """
    if not isinstance(data, list):
        raise TypeError("ChatGPT export must be a JSON array of conversations")

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
