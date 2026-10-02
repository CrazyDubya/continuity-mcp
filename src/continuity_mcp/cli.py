from __future__ import annotations

import argparse
import json
from pathlib import Path

from continuity_mcp.providers.chatgpt import load_chatgpt_export
from continuity_mcp.store import ArchiveStore, sha256_file


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
        "import-chatgpt", help="Import a ChatGPT conversations.json export"
    )
    import_chatgpt.add_argument("path", type=Path)

    subcommands.add_parser("status", help="Show local archive status")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    store = ArchiveStore(args.db)

    if args.command == "import-chatgpt":
        path = args.path.expanduser().resolve()
        conversations = load_chatgpt_export(path)
        result = store.import_conversations(
            conversations,
            source_path=path,
            source_sha256=sha256_file(path),
        )
        print(json.dumps(result, indent=2))
        return

    if args.command == "status":
        print(json.dumps(store.status(), indent=2))
        return

    raise SystemExit(f"Unknown command: {args.command}")
