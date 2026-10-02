# Architecture

## Purpose

Continuity is a user-hosted memory boundary between private AI interaction
archives and agents. It is deliberately not an agent itself.

The system owns ingestion, provenance, indexing, retrieval, and authorization.
Models may later classify or synthesize derived memory, but they do not become
the source of truth and do not grant themselves access.

## Layers

### L0 — source truth

The exact imported provider export is copied into managed, content-addressed
local storage and identified by SHA-256. These bytes are never rewritten by
normalization or model interpretation.

### L1 — canonical archive

Provider-neutral conversations and messages live in SQLite. Provider IDs and
graph links are preserved, but large provider-native raw trees are not copied
into every canonical row. Canonical records retain a source relationship back
to L0.

### L2 — rebuildable indexes

SQLite FTS5 is the first index. It uses external-content mode so searchable
message text is not duplicated in the FTS table. Embeddings and other
retrieval indexes belong here later. Losing L2 must not lose archive truth.

### L3 — interpreted memory

Future entities, episodes, events, assertions, relations, supersession edges,
salience, sensitivity labels, and other model-assisted structures. Every record
must retain provenance to L0/L1.

### L4 — retrieval product

Temporary answers and context packs assembled for an authorized caller and
bounded by policy and token budget.

## Trust boundaries

- Local import is a CLI operation, not an MCP tool.
- The MCP surface is read-only.
- Search returns bounded snippets, not arbitrary whole messages.
- Conversation retrieval is paginated and bounds per-message content.
- Exact message text can be read in bounded character slices.
- MCP status does not reveal host filesystem paths.
- Remote transport is intentionally deferred until authentication and grant
  policy exist.
- A future semantic model may classify sensitivity, but deterministic policy
  decides access.
- Derived memory can be deleted and rebuilt; source truth cannot be silently
  replaced by it.

## Canonical identifiers

Canonical IDs are provider-qualified:

    chatgpt:<conversation-id>
    chatgpt:<conversation-id>:<source-node-id>

For ChatGPT, the mapping node ID is the canonical source identity because
parent/child branch edges reference node IDs. The nested ChatGPT message ID is
preserved separately.

Child and parent links stored in L1 use fully qualified canonical IDs.

## Import behavior

A ChatGPT import follows this path:

    conversations.json
      -> exact byte copy + SHA-256
      -> managed sources/<sha256>.blob
      -> streaming ChatGPT adapter
      -> CanonicalConversation / CanonicalMessage
      -> SQLite
      -> external-content FTS5 index

The parser processes one conversation at a time rather than materializing the
entire export in memory. Re-importing a conversation replaces its canonical
messages and deterministically rebuilds the corresponding FTS entries.

## MCP baseline

The first retrieval surface is deliberately small:

- archive_status
- archive_search
- archive_conversation
- archive_message

All outputs are bounded. Higher-level memory tools should compose these
primitives or query the same store rather than bypassing provenance.

## Near-term evolution

1. Add explicit schema migrations before the first durable release.
2. Make canonical message content multimodal rather than a text projection.
3. Add provider adapter conformance fixtures.
4. Add embeddings as an optional L2 index.
5. Add episode/entity/assertion schemas as rebuildable L3 data.
6. Add a retrieval planner and task-specific archive_context.
7. Add capability grants and scoped remote MCP access.
8. Add Claude/Codex/Hermes/Grok adapters without changing L1 semantics.
