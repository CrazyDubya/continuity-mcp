from __future__ import annotations

import argparse
import json
from pathlib import Path

from continuity_mcp.providers.chatgpt import iter_chatgpt_export
from continuity_mcp.store import ArchiveStore


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="continuity")
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="SQLite database path",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    import_chatgpt = subcommands.add_parser(
        "import-chatgpt",
        help="Import a ChatGPT conversations.json export",
    )
    import_chatgpt.add_argument("path", type=Path)

    subcommands.add_parser("status", help="Show local archive status")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    store = ArchiveStore(args.db)

    if args.command == "import-chatgpt":
        source = store.ingest_source(args.path, provider="chatgpt")
        result = store.import_conversations(
            iter_chatgpt_export(source.path),
            source_id=source.id,
        )
        print(
            json.dumps(
                {
                    **result,
                    "source_sha256": source.sha256,
                    "source_bytes": source.size_bytes,
                },
                indent=2,
            )
        )
        return

    if args.command == "status":
        print(json.dumps(store.status(), indent=2))
        return

    raise SystemExit(f"Unknown command: {args.command}")
