"""Command-line entry point: ``gedcom-mcp --gedcom-path DIR``."""

from __future__ import annotations

import argparse
import logging
import os
import sys


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="gedcom-mcp",
        description="MCP server for reading, searching and editing GEDCOM (.ged) files",
    )
    parser.add_argument(
        "--gedcom-path",
        default=os.environ.get("GEDCOM_PATH"),
        help="Directory containing .ged files (or set GEDCOM_PATH)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging on stderr")
    args = parser.parse_args(argv)

    logging.basicConfig(
        stream=sys.stderr,
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    from .config import ConfigError, make_settings
    from .server import configure, mcp

    if not args.gedcom_path:
        parser.error("--gedcom-path is required (or set GEDCOM_PATH)")
    try:
        configure(make_settings(args.gedcom_path))
    except ConfigError as e:
        parser.error(str(e))
    mcp.run()


if __name__ == "__main__":
    main()
