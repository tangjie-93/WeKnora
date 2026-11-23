"""Explicitly initialize one new, isolated authentication database and secret."""

import argparse
import sqlite3
from pathlib import Path

from app.core.migrations import initialize_auth_database


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Initialize a NEW owned authentication database; never overwrite")
    parser.add_argument("--path", type=Path, required=True, help="Absolute path in an existing non-symlink directory")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        initialize_auth_database(args.path)
    except (OSError, ValueError, sqlite3.Error) as exc:
        # Do not print paths, SQL, secret values or exception details.
        print(f"Authentication initialization failed ({type(exc).__name__}); no existing files were overwritten.")
        return 1
    print("Authentication database initialized (SQLite prefix v7); private persistent secret created.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
