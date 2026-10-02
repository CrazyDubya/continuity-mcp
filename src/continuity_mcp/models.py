from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class CanonicalMessage:
    provider: str
    conversation_id: str
    message_id: str
    role: str | None
    content: str
    provider_message_id: str | None = None
    created_at: float | None = None
    updated_at: float | None = None
    parent_id: str | None = None
    children_ids: tuple[str, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CanonicalConversation:
    provider: str
    conversation_id: str
    title: str
    messages: tuple[CanonicalMessage, ...]
    created_at: float | None = None
    updated_at: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)
