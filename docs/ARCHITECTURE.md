# Architecture

## Purpose

Continuity is a user-hosted memory boundary between private AI interaction
archives and agents. It is deliberately not an agent itself.

The current foundation owns ingestion, provenance, indexing, and retrieval.
Local stdio access inherits the permissions of the process that launches the
server; remote authentication and scoped authorization are not implemented.

## Layers

### L0 — source truth

The exact imported provider export is copied into managed, content-addressed
local storage and identified by SHA-256. These bytes are never rewritten by
normalization or model interpretation.

### L1 — canonical archive

Provider-neutral conversations and messages live in SQLite. Provider message
identities are preserved. Provider structural nodes that do not contain a
message remain in L0; L1 projects message-to-message parent/child links across
those structural nodes so canonical links never point at missing messages.
Canonical records retain a source relationship back to L0.

### L2 — rebuildable indexes

SQLite FTS5 is the first index. It uses external-content mode so searchable
message text is not duplicated in the FTS table. Embeddings and other
retrieval indexes belong here later. Losing L2 must not lose archive truth.

### L3 — interpreted memory

Future entities, episodes, events, assertions, relations, supersession edges,
salience, sensitivity labels, and other model-assisted structures. Every record
must retain provenance to L0/L1.

### L4 — retrieval product

Temporary answers and context packs assembled for a connected caller and
bounded by the retrieval interface.

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
entire export in memory. Exact duplicate sources are skipped by default.
Changed cumulative exports compute a deterministic fingerprint of each
canonical conversation; unchanged conversations avoid message and FTS writes,
while changed conversations replace their canonical messages and rebuild their
FTS entries. A forced re-import path exists for deliberate adapter rebuilds.

## MCP baseline

The first retrieval surface is deliberately small:

- archive_status
- archive_search
- archive_conversation
- archive_message

All outputs are bounded. Higher-level memory tools should compose these
primitives or query the same store rather than bypassing provenance.
