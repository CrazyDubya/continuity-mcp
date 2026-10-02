# Continuity MCP

Self-hosted, provenance-preserving personal AI memory infrastructure with scoped MCP access across conversation archives.

Continuity is not an analytics dashboard and it is not a replacement for the original archive experiments. It is a clean successor focused on one job: keep a user's AI interaction history under the user's control and make the right parts of that history available to authorized agents.

## Core contract

> The archive remembers. Models interpret. MCP mediates. The owner authorizes.

Continuity keeps four layers deliberately separate:

1. **Source truth** — immutable provider exports and exact source records.
2. **Canonical archive** — provider-neutral conversations, messages, branches, artifacts, and metadata.
3. **Derived memory** — rebuildable indexes and, later, episodes, entities, assertions, relationships, salience, and supersession.
4. **Retrieved context** — temporary, task-specific context returned to an authorized agent.

Derived memory never replaces source truth. Every synthesized memory must be traceable back to source records.

## Initial scope

The first complete path is intentionally small:

```
ChatGPT conversations.json
        ↓
ChatGPT provider adapter
        ↓
canonical conversations/messages
        ↓
SQLite + FTS5
        ↓
MCP tools
        ↓
authorized agent
```

The initial server exposes exact archive search and source retrieval. Learned semantic compilation, embeddings, temporal assertions, context-pack construction, provider ACLs, and additional provider adapters come next without changing the source layer.

## Local-first

Archive exports can contain highly sensitive personal information. Continuity is designed to run locally by default. Raw archives, imported data directories, and local databases are gitignored.

No model call is required for ingestion or baseline retrieval.

## Development

Requires Python 3.12+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Import a ChatGPT export:

```bash
continuity import-chatgpt /path/to/conversations.json
```

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

The bootstrap server starts with three bounded primitives:

- `archive_status()` — report archive/provider counts.
- `archive_search(query, limit)` — full-text search returning source-linked message hits.
- `archive_conversation(conversation_id)` — fetch an exact canonical conversation with messages.

Planned higher-level primitives include `archive_recall`, `archive_context`, `archive_timeline`, `archive_related`, and `archive_trace`.

## Provider model

Provider-specific formats stop at the adapter boundary. ChatGPT is only the first adapter. Claude, Codex, Grok, Hermes, and other archives should compile into the same canonical representation rather than leaking provider schemas into retrieval.

## Legacy projects

Earlier archive-analysis repositories remain independent legacy projects and are not modified by Continuity. Proven ideas and code may be ported selectively with attribution, but this repository has its own architecture and lifecycle.
