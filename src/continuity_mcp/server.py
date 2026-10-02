from __future__ import annotations

from functools import cache
from typing import Any

from mcp.server import MCPServer

from continuity_mcp.store import ArchiveStore

mcp = MCPServer(
    "Continuity",
    description="Read-only access to a user-owned conversation archive.",
    instructions=(
        "Search before retrieving source text. Treat search results as pointers, "
        "not facts; use archive_message or archive_conversation when exact source "
        "context matters."
    ),
)

@cache
def _store() -> ArchiveStore:
    return ArchiveStore()

@mcp.tool()
def archive_status() -> dict[str, Any]:
    """Return provider and archive counts without exposing host filesystem paths."""
    return _store().status()

@mcp.tool()
def archive_search(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search archived messages and return bounded snippets with source IDs.

    Search never returns whole messages. Use archive_message or
    archive_conversation to retrieve bounded source text.
    """
    return _store().search(query, limit)

@mcp.tool()
def archive_conversation(
    conversation_id: str,
    offset: int = 0,
    limit: int = 50,
    max_chars_per_message: int = 8_000,
) -> dict[str, Any]:
    """Return a bounded page of canonical messages from one conversation."""
    result = _store().conversation(
        conversation_id,
        offset=offset,
        limit=limit,
        max_chars_per_message=max_chars_per_message,
    )
    if result is None:
        return {"found": False, "conversation_id": conversation_id}
    return {"found": True, **result}

@mcp.tool()
def archive_message(
    message_id: str,
    start_char: int = 0,
    max_chars: int = 8_000,
) -> dict[str, Any]:
    """Return a bounded exact character slice from one canonical message."""
    result = _store().message(
        message_id,
        start_char=start_char,
        max_chars=max_chars,
    )
    if result is None:
        return {"found": False, "message_id": message_id}
    return {"found": True, **result}

def main() -> None:
    # stdio is the local default. Remote serving stays out of scope until
    # capability grants and authentication are implemented.
    mcp.run()

if __name__ == "__main__":
    main()
