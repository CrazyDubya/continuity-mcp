# Architecture

## Purpose

Continuity is a user-hosted memory boundary between private AI interaction
archives and agents. It is deliberately not an agent itself.

The system owns ingestion, provenance, indexing, retrieval, and authorization.
Models may later classify or synthesize derived memory, but they do not become
the source of truth and do not grant themselves access.

## Layers

### L0 — source truth

Original provider exports and exact imported source objects. Source data is
never rewritten to match a newer interpretation.

### L1 — canonical archive

Provider-neutral conversations and messages. Provider IDs and graph links are
preserved. The first adapter is ChatGPT.

### L2 — rebuildable indexes

SQLite indexes and FTS5 initially. Embeddings and other retrieval indexes belong
here later. Losing L2 must not lose archive truth.

### L3 — interpreted memory

Future entities, episodes, events, assertions, relations, supersession edges,
salience, sensitivity labels, and other model-assisted structures. Every record
must retain provenance to L0/L1.

### L4 — retrieval product

Temporary answers and context packs assembled for an authorized caller and
bounded by policy and token budget.

## Trust boundaries

- Local import is a CLI operation, not an MCP tool.
- The bootstrap MCP surface is read-only.
- Remote transport is intentionally deferred until authentication and grant
  policy exist.
- A future semantic model may classify sensitivity, but deterministic policy
  decides access.
- Derived memory can be deleted and rebuilt; source truth cannot be silently
  replaced by it.

## Canonical identifiers

Canonical IDs are provider-qualified:

    chatgpt:<conversation-id>
    chatgpt:<conversation-id>:<message-id>

This prevents collisions when additional provider adapters are added.

## First vertical slice

    conversations.json
      -> providers/chatgpt.py
      -> CanonicalConversation / CanonicalMessage
      -> ArchiveStore
      -> SQLite + FTS5
      -> archive_search / archive_conversation

The slice intentionally proves provenance-preserving retrieval before semantic
compilation is introduced.

## Near-term evolution

1. Add immutable import manifests and stronger source/version tracking.
2. Make message content multimodal rather than text-only canonical projection.
3. Add provider adapter conformance tests.
4. Add embeddings as an optional L2 index.
5. Add episode/entity/assertion schemas as rebuildable L3 data.
6. Add a retrieval planner and task-specific archive_context.
7. Add capability grants and scoped remote MCP access.
8. Add Claude/Codex/Hermes/Grok adapters without changing L1 semantics.
