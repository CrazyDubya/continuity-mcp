from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from continuity_mcp.models import CanonicalConversation


def default_db_path() -> Path:
    configured = os.environ.get("CONTINUITY_DB")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".local" / "share" / "continuity-mcp" / "continuity.sqlite3"


def _canonical_conversation_id(provider: str, source_id: str) -> str:
    return f"{provider}:{source_id}"


def _canonical_message_id(provider: str, conversation_id: str, source_id: str) -> str:
    return f"{provider}:{conversation_id}:{source_id}"


def _fts_query(query: str) -> str:
    tokens = re.findall(r"[\w'-]+", query, flags=re.UNICODE)
    if not tokens:
        raise ValueError("Search query must contain at least one searchable token")
    return " ".join(f'"{token.replace(chr(34), chr(34) * 2)}"' for token in tokens)


class ArchiveStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS imports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT NOT NULL,
                    source_path TEXT,
                    source_sha256 TEXT,
                    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    source_conversation_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    created_at REAL,
                    updated_at REAL,
                    raw_json TEXT NOT NULL,
                    UNIQUE(provider, source_conversation_id)
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    provider TEXT NOT NULL,
                    source_message_id TEXT NOT NULL,
                    role TEXT,
                    content TEXT NOT NULL,
                    created_at REAL,
                    updated_at REAL,
                    parent_message_id TEXT,
                    children_json TEXT NOT NULL,
                    raw_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_messages_conversation
                    ON messages(conversation_id);
                CREATE INDEX IF NOT EXISTS idx_messages_created
                    ON messages(created_at);

                CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                    message_id UNINDEXED,
                    conversation_id UNINDEXED,
                    content,
                    tokenize='unicode61'
                );
                """
            )

    def import_conversations(
        self,
        conversations: Iterable[CanonicalConversation],
        *,
        source_path: str | Path | None = None,
        source_sha256: str | None = None,
    ) -> dict[str, int]:
        imported_conversations = 0
        imported_messages = 0
        provider_seen: str | None = None

        with self._connect() as conn:
            for conversation in conversations:
                provider_seen = provider_seen or conversation.provider
                if conversation.provider != provider_seen:
                    raise ValueError("One import transaction must contain a single provider")

                canonical_conversation_id = _canonical_conversation_id(
                    conversation.provider, conversation.conversation_id
                )

                conn.execute(
                    "DELETE FROM messages_fts WHERE conversation_id = ?",
                    (canonical_conversation_id,),
                )
                conn.execute(
                    "DELETE FROM messages WHERE conversation_id = ?",
                    (canonical_conversation_id,),
                )
                conn.execute(
                    """
                    INSERT INTO conversations(
                        id, provider, source_conversation_id, title,
                        created_at, updated_at, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        title=excluded.title,
                        created_at=excluded.created_at,
                        updated_at=excluded.updated_at,
                        raw_json=excluded.raw_json
                    """,
                    (
                        canonical_conversation_id,
                        conversation.provider,
                        conversation.conversation_id,
                        conversation.title,
                        conversation.created_at,
                        conversation.updated_at,
                        json.dumps(conversation.raw, ensure_ascii=False),
                    ),
                )

                for message in conversation.messages:
                    canonical_message_id = _canonical_message_id(
                        message.provider, message.conversation_id, message.message_id
                    )
                    parent_message_id = (
                        _canonical_message_id(
                            message.provider, message.conversation_id, message.parent_id
                        )
                        if message.parent_id
                        else None
                    )
                    conn.execute(
                        """
                        INSERT INTO messages(
                            id, conversation_id, provider, source_message_id,
                            role, content, created_at, updated_at,
                            parent_message_id, children_json, raw_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            canonical_message_id,
                            canonical_conversation_id,
                            message.provider,
                            message.message_id,
                            message.role,
                            message.content,
                            message.created_at,
                            message.updated_at,
                            parent_message_id,
                            json.dumps(message.children_ids),
                            json.dumps(message.raw, ensure_ascii=False),
                        ),
                    )
                    conn.execute(
                        "INSERT INTO messages_fts(message_id, conversation_id, content) VALUES (?, ?, ?)",
                        (canonical_message_id, canonical_conversation_id, message.content),
                    )
                    imported_messages += 1

                imported_conversations += 1

            if provider_seen:
                conn.execute(
                    """
                    INSERT INTO imports(provider, source_path, source_sha256)
                    VALUES (?, ?, ?)
                    """,
                    (
                        provider_seen,
                        str(source_path) if source_path is not None else None,
                        source_sha256,
                    ),
                )

        return {"conversations": imported_conversations, "messages": imported_messages}

    def status(self) -> dict[str, Any]:
        with self._connect() as conn:
            providers = {
                row["provider"]: row["count"]
                for row in conn.execute(
                    "SELECT provider, COUNT(*) AS count FROM conversations GROUP BY provider"
                )
            }
            conversation_count = conn.execute(
                "SELECT COUNT(*) FROM conversations"
            ).fetchone()[0]
            message_count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            import_count = conn.execute("SELECT COUNT(*) FROM imports").fetchone()[0]

        return {
            "database": str(self.path),
            "providers": providers,
            "conversations": conversation_count,
            "messages": message_count,
            "imports": import_count,
        }

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 50))
        match_query = _fts_query(query)

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    m.id AS message_id,
                    m.conversation_id,
                    c.provider,
                    c.title,
                    m.role,
                    m.content,
                    m.created_at,
                    bm25(messages_fts) AS score
                FROM messages_fts
                JOIN messages m ON m.id = messages_fts.message_id
                JOIN conversations c ON c.id = m.conversation_id
                WHERE messages_fts MATCH ?
                ORDER BY score
                LIMIT ?
                """,
                (match_query, limit),
            ).fetchall()

        return [dict(row) for row in rows]

    def conversation(self, conversation_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            conversation = conn.execute(
                """
                SELECT id, provider, source_conversation_id, title, created_at, updated_at
                FROM conversations
                WHERE id = ?
                """,
                (conversation_id,),
            ).fetchone()
            if conversation is None:
                return None

            messages = conn.execute(
                """
                SELECT id, source_message_id, role, content, created_at, updated_at,
                       parent_message_id, children_json
                FROM messages
                WHERE conversation_id = ?
                ORDER BY created_at IS NULL, created_at, id
                """,
                (conversation_id,),
            ).fetchall()

        result = dict(conversation)
        result["messages"] = [
            {
                **{k: row[k] for k in row.keys() if k != "children_json"},
                "children_ids": json.loads(row["children_json"]),
            }
            for row in messages
        ]
        return result


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
