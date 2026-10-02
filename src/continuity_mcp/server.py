from __future__ import annotations

from typing import Any

from mcp.server import MCPServer

from continuity_mcp.store import ArchiveStore


mcp = MCPServer("Continuity")


@mcp.tool()
def archive_status() -> dict[str, Any]:
    """Return counts and providers available in the local Continuity archive."""
    return ArchiveStore().status()


@mcp.tool()
def archive_search(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search exact archived message text.

    Results include canonical conversation and message identifiers so callers
    can fetch source context rather than treating search hits as memory truth.
    """
    return ArchiveStore().search(query, limit)


@mcp.tool()
def archive_conversation(conversation_id: str) -> dict[str, Any]:
    """Return one canonical conversation and its exact imported messages."""
    result = ArchiveStore().conversation(conversation_id)
    if result is None:
        return {"found": False, "conversation_id": conversation_id}
    return {"found": True, **result}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
