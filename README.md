# Continuity MCP

Self-hosted, provenance-preserving personal AI memory infrastructure with bounded read-only MCP access across conversation archives.

Continuity is not an analytics dashboard and it is not a replacement for the original archive experiments. It is a clean successor focused on one job: keep a user's AI interaction history under the user's control and make the right parts of that history available to connected agents through MCP.

## Core contract

> The archive remembers. Models interpret. MCP mediates. The owner authorizes.

Continuity keeps four layers deliberately separate:

1. **Source truth** — exact imported provider exports, stored locally by content hash.
2. **Canonical archive** — provider-neutral conversations, messages, branches, and provenance.
3. **Derived memory** — rebuildable indexes and, later, episodes, entities, assertions, relationships, salience, and supersession.
4. **Retrieved context** — temporary, task-specific context returned to a connected caller.

Derived memory never replaces source truth. Every synthesized memory must ultimately be traceable back to imported source bytes.

## Initial scope

The first complete path is intentionally small:

```
ChatGPT conversations.json
        ↓
content-addressed source store
        ↓
streaming ChatGPT adapter
        ↓
canonical conversations/messages
        ↓
SQLite + external-content FTS5
        ↓
bounded MCP tools
        ↓
connected local agent
```

The initial server exposes source-linked archive search and bounded source retrieval. Learned semantic compilation, embeddings, temporal assertions, context-pack construction, provider ACLs, and additional provider adapters come later without changing the source layer.

## Local-first

Archive exports can contain highly sensitive personal information. Continuity runs locally by default. Raw archives, managed source copies, local databases, model caches, and indexes are gitignored.

No model call is required for ingestion or baseline retrieval. Import is deliberately a local CLI action rather than an MCP tool, so a connected agent cannot select arbitrary host filesystem paths.

## Development

Requires Python 3.12+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
ruff check src tests
pytest
```

Import a ChatGPT export:

```bash
continuity import-chatgpt /path/to/conversations.json
```

The file is copied byte-for-byte into Continuity's managed content-addressed source store before parsing. Large exports are then parsed one conversation at a time rather than loaded fully into memory. Re-importing the exact same source is skipped by default; changed cumulative exports fingerprint each canonical conversation and only rewrite conversations whose canonical content changed. Use `--force` when intentionally rebuilding canonical records after an adapter change.

Run the MCP server over stdio:

```bash
continuity-mcp
```

Or inspect it with the official MCP tooling:

```bash
mcp dev src/continuity_mcp/server.py
```

The project targets the current stable v2 line of the official Python MCP SDK.

## MCP surface

The bootstrap server exposes four read-only, bounded primitives:

- `archive_status()` — report provider/archive counts without exposing host paths.
- `archive_search(query, limit)` — FTS search returning source-linked snippets, never whole messages.
- `archive_conversation(conversation_id, offset, limit, max_chars_per_message)` — page through a conversation with bounded message content.
- `archive_message(message_id, start_char, max_chars)` — retrieve exact message text in bounded character slices.

The intended higher-level surface includes `archive_recall`, `archive_context`, `archive_timeline`, `archive_related`, and `archive_trace`.

## Provider model

Provider-specific formats stop at the adapter boundary. ChatGPT is only the first adapter. Claude, Codex, Grok, Hermes, and other archives should compile into the same canonical representation rather than leaking provider schemas into retrieval.

For ChatGPT specifically, message-bearing mapping node IDs are retained as canonical source identities because branch edges reference those IDs; nested provider message IDs are preserved separately. Structural mapping nodes that contain no message remain in the exact L0 source and are bridged when projecting canonical message-to-message links. Provider-native identifier components are percent-escaped before composition so canonical IDs remain collision-safe.

## Legacy projects

Earlier archive-analysis repositories remain independent legacy projects and are not modified by Continuity. Proven ideas and code may be ported selectively with attribution, but this repository has its own architecture and lifecycle.
