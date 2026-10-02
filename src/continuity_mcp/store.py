from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from platformdirs import user_data_path

from continuity_mcp.models import CanonicalConversation

_SEARCH_LIMIT_MAX = 50
_CONVERSATION_LIMIT_MAX = 200
_MESSAGE_CHARS_MAX = 20_000
_SCHEMA_VERSION = 2

@dataclass(frozen=True, slots=True)
class SourceRecord:
    id: int
    provider: str
    sha256: str
    original_name: str
    size_bytes: int
    path: Path

def default_db_path() -> Path:
    configured = os.environ.get("CONTINUITY_DB")
    if configured:
        return Path(configured).expanduser()
    return user_data_path("continuity-mcp", appauthor=False) / "continuity.sqlite3"

def _id_component(value: str) -> str:
    return quote(str(value), safe="")


def _canonical_conversation_id(provider: str, source_id: str) -> str:
    return f"{_id_component(provider)}:{_id_component(source_id)}"


def _canonical_message_id(provider: str, conversation_id: str, source_id: str) -> str:
    return (
        f"{_id_component(provider)}:{_id_component(conversation_id)}:"
        f"{_id_component(source_id)}"
    )

def _conversation_fingerprint(conversation: CanonicalConversation) -> str:
    payload = {
        "provider": conversation.provider,
        "conversation_id": conversation.conversation_id,
        "title": conversation.title,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
        "messages": [
            {
                "message_id": message.message_id,
                "provider_message_id": message.provider_message_id,
                "role": message.role,
                "content": message.content,
                "created_at": message.created_at,
                "updated_at": message.updated_at,
                "parent_id": message.parent_id,
                "children_ids": message.children_ids,
            }
            for message in conversation.messages
        ],
    }
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _fts_query(query: str) -> str:
    # Quoting the whitespace-delimited terms keeps user input out of FTS query
    # operators while retaining precise AND semantics for baseline retrieval.
    terms = [term.strip() for term in query.split() if term.strip()]
    if not terms:
        raise ValueError("Search query must contain at least one searchable term")
    return " ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms)

class ArchiveStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path).expanduser() if path else default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.sources_dir = self.path.parent / "sources"
        self._initialize()
        if os.name != "nt":
            self.path.chmod(0o600)
            if self.sources_dir.exists():
                self.sources_dir.chmod(0o700)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            if version > _SCHEMA_VERSION:
                raise RuntimeError(
                    f"Database schema version {version} is newer than this build "
                    f"(supports {_SCHEMA_VERSION})."
                )

            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    original_name TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    stored_relpath TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(provider, sha256)
                );

                CREATE TABLE IF NOT EXISTS imports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT NOT NULL,
                    source_id INTEGER REFERENCES sources(id),
                    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    source_conversation_id TEXT NOT NULL,
                    source_id INTEGER REFERENCES sources(id),
                    canonical_sha256 TEXT,
                    title TEXT NOT NULL,
                    created_at REAL,
                    updated_at REAL,
                    UNIQUE(provider, source_conversation_id)
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL
                        REFERENCES conversations(id) ON DELETE CASCADE,
                    provider TEXT NOT NULL,
                    source_message_id TEXT NOT NULL,
                    provider_message_id TEXT,
                    source_id INTEGER REFERENCES sources(id),
                    role TEXT,
                    content TEXT NOT NULL,
                    created_at REAL,
                    updated_at REAL,
                    parent_message_id TEXT,
                    children_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_messages_conversation
                    ON messages(conversation_id);
                CREATE INDEX IF NOT EXISTS idx_messages_created
                    ON messages(created_at);
                CREATE INDEX IF NOT EXISTS idx_messages_provider_message
                    ON messages(provider, provider_message_id);

                CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                    content,
                    content='messages',
                    content_rowid='rowid',
                    tokenize='unicode61'
                );

                CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
                    INSERT INTO messages_fts(rowid, content)
                    VALUES (new.rowid, new.content);
                END;

                CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
                    INSERT INTO messages_fts(messages_fts, rowid, content)
                    VALUES ('delete', old.rowid, old.content);
                END;

                CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
                    INSERT INTO messages_fts(messages_fts, rowid, content)
                    VALUES ('delete', old.rowid, old.content);
                    INSERT INTO messages_fts(rowid, content)
                    VALUES (new.rowid, new.content);
                END;
                """
            )

            conversation_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(conversations)")
            }
            if "canonical_sha256" not in conversation_columns:
                conn.execute(
                    "ALTER TABLE conversations ADD COLUMN canonical_sha256 TEXT"
                )

            if version < _SCHEMA_VERSION:
                conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")

    def ingest_source(self, source_path: str | Path, provider: str) -> SourceRecord:
        """Copy exact source bytes into content-addressed local storage."""
        source = Path(source_path).expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(source)

        self.sources_dir.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            self.sources_dir.chmod(0o700)

        digest = hashlib.sha256()
        size_bytes = 0

        fd, temporary_name = tempfile.mkstemp(
            prefix=".ingest-", dir=self.sources_dir
        )
        temporary = Path(temporary_name)

        try:
            with source.open("rb") as input_file, os.fdopen(fd, "wb") as output_file:
                for block in iter(lambda: input_file.read(1024 * 1024), b""):
                    digest.update(block)
                    size_bytes += len(block)
                    output_file.write(block)
                output_file.flush()
                os.fsync(output_file.fileno())

            sha256 = digest.hexdigest()
            stored = self.sources_dir / f"{sha256}.blob"
            # Replace atomically even when the content-addressed path exists.
            # This repairs a locally corrupted blob instead of trusting it only
            # because its filename matches the expected digest.
            os.replace(temporary, stored)
            if os.name != "nt":
                stored.chmod(0o600)
        except BaseException:
            if temporary.exists():
                temporary.unlink()
            raise

        stored_relpath = str(stored.relative_to(self.path.parent))
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sources(
                    provider, sha256, original_name, size_bytes, stored_relpath
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(provider, sha256) DO UPDATE SET
                    original_name=excluded.original_name,
                    size_bytes=excluded.size_bytes,
                    stored_relpath=excluded.stored_relpath
                """,
                (
                    provider,
                    sha256,
                    source.name,
                    size_bytes,
                    stored_relpath,
                ),
            )
            row = conn.execute(
                """
                SELECT id, provider, sha256, original_name, size_bytes, stored_relpath
                FROM sources
                WHERE provider = ? AND sha256 = ?
                """,
                (provider, sha256),
            ).fetchone()

        assert row is not None
        return SourceRecord(
            id=row["id"],
            provider=row["provider"],
            sha256=row["sha256"],
            original_name=row["original_name"],
            size_bytes=row["size_bytes"],
            path=self.path.parent / row["stored_relpath"],
        )

    def import_conversations(
        self,
        conversations: Iterable[CanonicalConversation],
        *,
        source_id: int | None = None,
        force_reimport: bool = False,
    ) -> dict[str, int | bool]:
        imported_conversations = 0
        imported_messages = 0
        unchanged_conversations = 0
        provider_seen: str | None = None

        with self._connect() as conn:
            source_provider: str | None = None
            if source_id is not None:
                source_row = conn.execute(
                    "SELECT provider FROM sources WHERE id = ?", (source_id,)
                ).fetchone()
                if source_row is None:
                    raise ValueError(f"Unknown source id: {source_id}")
                source_provider = source_row["provider"]

                already_imported = conn.execute(
                    "SELECT 1 FROM imports WHERE source_id = ? LIMIT 1",
                    (source_id,),
                ).fetchone()
                if already_imported is not None and not force_reimport:
                    return {
                        "conversations": 0,
                        "messages": 0,
                        "unchanged_conversations": 0,
                        "duplicate_source": True,
                    }

            for conversation in conversations:
                provider_seen = provider_seen or conversation.provider
                if conversation.provider != provider_seen:
                    raise ValueError(
                        "One import transaction must contain a single provider"
                    )
                if source_provider and conversation.provider != source_provider:
                    raise ValueError(
                        "Imported conversation provider does not match source provider"
                    )

                canonical_conversation_id = _canonical_conversation_id(
                    conversation.provider, conversation.conversation_id
                )
                canonical_sha256 = _conversation_fingerprint(conversation)

                existing = conn.execute(
                    "SELECT canonical_sha256 FROM conversations WHERE id = ?",
                    (canonical_conversation_id,),
                ).fetchone()
                if (
                    existing is not None
                    and existing["canonical_sha256"] == canonical_sha256
                    and not force_reimport
                ):
                    imported_conversations += 1
                    unchanged_conversations += 1
                    continue

                conn.execute(
                    "DELETE FROM messages WHERE conversation_id = ?",
                    (canonical_conversation_id,),
                )
                conn.execute(
                    """
                    INSERT INTO conversations(
                        id, provider, source_conversation_id, source_id,
                        canonical_sha256, title, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        source_id=excluded.source_id,
                        canonical_sha256=excluded.canonical_sha256,
                        title=excluded.title,
                        created_at=excluded.created_at,
                        updated_at=excluded.updated_at
                    """,
                    (
                        canonical_conversation_id,
                        conversation.provider,
                        conversation.conversation_id,
                        source_id,
                        canonical_sha256,
                        conversation.title,
                        conversation.created_at,
                        conversation.updated_at,
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
                    children_ids = [
                        _canonical_message_id(
                            message.provider, message.conversation_id, child_id
                        )
                        for child_id in message.children_ids
                    ]
                    conn.execute(
                        """
                        INSERT INTO messages(
                            id, conversation_id, provider, source_message_id,
                            provider_message_id, source_id, role, content,
                            created_at, updated_at, parent_message_id, children_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            canonical_message_id,
                            canonical_conversation_id,
                            message.provider,
                            message.message_id,
                            message.provider_message_id,
                            source_id,
                            message.role,
                            message.content,
                            message.created_at,
                            message.updated_at,
                            parent_message_id,
                            json.dumps(children_ids),
                        ),
                    )
                    imported_messages += 1

                imported_conversations += 1

            if provider_seen:
                conn.execute(
                    """
                    INSERT INTO imports(provider, source_id)
                    VALUES (?, ?)
                    """,
                    (provider_seen, source_id),
                )

        return {
            "conversations": imported_conversations,
            "messages": imported_messages,
            "unchanged_conversations": unchanged_conversations,
            "duplicate_source": False,
        }

    def status(self) -> dict[str, Any]:
        with self._connect() as conn:
            providers = {
                row["provider"]: row["count"]
                for row in conn.execute(
                    """
                    SELECT provider, COUNT(*) AS count
                    FROM conversations
                    GROUP BY provider
                    """
                )
            }
            conversation_count = conn.execute(
                "SELECT COUNT(*) FROM conversations"
            ).fetchone()[0]
            message_count = conn.execute(
                "SELECT COUNT(*) FROM messages"
            ).fetchone()[0]
            source_count = conn.execute(
                "SELECT COUNT(*) FROM sources"
            ).fetchone()[0]
            import_count = conn.execute(
                "SELECT COUNT(*) FROM imports"
            ).fetchone()[0]

        return {
            "schema_version": int(
                conn.execute("PRAGMA user_version").fetchone()[0]
            ),
            "providers": providers,
            "conversations": conversation_count,
            "messages": message_count,
            "sources": source_count,
            "imports": import_count,
        }

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), _SEARCH_LIMIT_MAX))
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
                    snippet(messages_fts, 0, '', '', ' … ', 32) AS snippet,
                    length(m.content) AS content_length,
                    m.created_at,
                    s.sha256 AS source_sha256,
                    bm25(messages_fts) AS bm25_rank
                FROM messages_fts
                JOIN messages m ON m.rowid = messages_fts.rowid
                JOIN conversations c ON c.id = m.conversation_id
                LEFT JOIN sources s ON s.id = m.source_id
                WHERE messages_fts MATCH ?
                ORDER BY bm25_rank
                LIMIT ?
                """,
                (match_query, limit),
            ).fetchall()

        return [dict(row) for row in rows]

    def conversation(
        self,
        conversation_id: str,
        *,
        offset: int = 0,
        limit: int = 50,
        max_chars_per_message: int = 8_000,
    ) -> dict[str, Any] | None:
        offset = max(0, int(offset))
        limit = max(1, min(int(limit), _CONVERSATION_LIMIT_MAX))
        max_chars_per_message = max(
            256, min(int(max_chars_per_message), _MESSAGE_CHARS_MAX)
        )

        with self._connect() as conn:
            conversation = conn.execute(
                """
                SELECT
                    c.id, c.provider, c.source_conversation_id, c.title,
                    c.created_at, c.updated_at, s.sha256 AS source_sha256
                FROM conversations c
                LEFT JOIN sources s ON s.id = c.source_id
                WHERE c.id = ?
                """,
                (conversation_id,),
            ).fetchone()
            if conversation is None:
                return None

            message_count = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()[0]

            messages = conn.execute(
                """
                SELECT
                    id, source_message_id, provider_message_id, role,
                    substr(content, 1, ?) AS content,
                    length(content) AS content_length,
                    created_at, updated_at, parent_message_id, children_json
                FROM messages
                WHERE conversation_id = ?
                ORDER BY created_at IS NULL, created_at, id
                LIMIT ? OFFSET ?
                """,
                (max_chars_per_message, conversation_id, limit, offset),
            ).fetchall()

        result = dict(conversation)
        result.update(
            {
                "message_count": message_count,
                "offset": offset,
                "limit": limit,
                "has_more": offset + len(messages) < message_count,
            }
        )
        result["messages"] = []
        for row in messages:
            item = dict(row)
            children_json = item.pop("children_json")
            item["content_truncated"] = (
                item["content_length"] > max_chars_per_message
            )
            item["children_ids"] = json.loads(children_json)
            result["messages"].append(item)
        return result

    def message(
        self,
        message_id: str,
        *,
        start_char: int = 0,
        max_chars: int = 8_000,
    ) -> dict[str, Any] | None:
        start_char = max(0, int(start_char))
        max_chars = max(256, min(int(max_chars), _MESSAGE_CHARS_MAX))

        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    m.id, m.conversation_id, c.provider, c.title,
                    m.source_message_id, m.provider_message_id, m.role,
                    substr(m.content, ?, ?) AS content,
                    length(m.content) AS content_length,
                    m.created_at, m.updated_at,
                    m.parent_message_id, m.children_json,
                    s.sha256 AS source_sha256
                FROM messages m
                JOIN conversations c ON c.id = m.conversation_id
                LEFT JOIN sources s ON s.id = m.source_id
                WHERE m.id = ?
                """,
                (start_char + 1, max_chars, message_id),
            ).fetchone()

        if row is None:
            return None

        content = row["content"]
        content_length = row["content_length"]
        next_start = start_char + len(content)
        if next_start >= content_length:
            next_start = None

        result = dict(row)
        children_json = result.pop("children_json")
        result["start_char"] = start_char
        result["next_start_char"] = next_start
        result["children_ids"] = json.loads(children_json)
        return result
