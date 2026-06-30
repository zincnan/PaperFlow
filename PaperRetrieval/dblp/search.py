#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Unified paper search CLI dispatcher.

Usage:
    python search.py <subcommand> [args...]

Each subcommand maps to a self-contained searcher module. The dispatcher
just routes — all business logic lives in the searcher module itself,
including argument parsing, config loading, and the search pipeline.

Adding a new subcommand:
    1. Write `<name>_search.py` with a `main(argv) -> int` function.
    2. Add `<name>: "<name>_search"` to `SEARCHERS` below.
"""

import importlib
import sys

# Map subcommand -> Python module name.
SEARCHERS: dict[str, str] = {
    "dblp": "dblp_search",
}


def _print_help() -> int:
    print(
        "Usage: python search.py <subcommand> [args...]\n"
        f"Available subcommands: {', '.join(sorted(SEARCHERS))}\n"
        "For help on a subcommand: python search.py <subcommand> --help",
        file=sys.stderr,
    )
    return 0


def _import_searcher(module_name: str):
    if __package__:
        return importlib.import_module(f".{module_name}", package=__package__)
    return importlib.import_module(module_name)


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    if not argv or argv[0] in ("-h", "--help"):
        return _print_help()

    source = argv[0]
    if source not in SEARCHERS:
        print(
            f"Unknown subcommand: '{source}'. "
            f"Available: {sorted(SEARCHERS)}",
            file=sys.stderr,
        )
        return 1

    module = _import_searcher(SEARCHERS[source])
    return module.main(argv[1:])


if __name__ == "__main__":
    sys.exit(main())
