"""Run safe fixed SQLite checks for a required explicit local file."""

import argparse
import json
import sys

from app.database_check import ERROR_DETAILS, DatabaseCheckError, DatabaseCheckResult, check_database


class _SafeParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        # argparse's default message may contain private paths or unknown arguments.
        raise DatabaseCheckError("invalid_arguments")


def build_parser() -> argparse.ArgumentParser:
    """Build a static, non-abbreviating parser without environment defaults."""
    parser = _SafeParser(
        prog="python -m app.cli.check_database",
        description="Check an explicit standalone local SQLite file; business schema is not verified.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--path", required=True, metavar="PATH", help="explicit local file; parent must exist"
    )
    parser.add_argument("--create", action="store_true", help="exclusively create a new empty file first")
    parser.add_argument("--json", action="store_true", help="emit one safe JSON result")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Print one safe result after cleanup and return a stable process exit code."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    json_output = "--json" in arguments
    mode = None
    try:
        parser = build_parser()
        # Help is a static-output exception, even when --json is also present.
        if "--help" in arguments or "-h" in arguments:
            parser.print_help()
            return 0
        options = parser.parse_args(arguments)
        json_output = options.json
        mode = "create" if options.create else "read_only"
        result = check_database(options.path, create=options.create)
    except DatabaseCheckError as exc:
        result = DatabaseCheckResult(mode, exc.target, exc.created, exc.code)
    except KeyboardInterrupt:
        result = DatabaseCheckResult(mode, None, code="interrupted")
    except Exception:  # noqa: BLE001 - CLI must not expose raw exceptions or private arguments
        result = DatabaseCheckResult(mode, None, code="internal_error")
    payload = result.to_dict()
    stream = sys.stdout if result.code == "ok" else sys.stderr
    if json_output:
        print(json.dumps(payload, separators=(",", ":")), file=stream)
    else:
        print(" ".join(f"{key}={json.dumps(value)}" for key, value in payload.items()), file=stream)
    return ERROR_DETAILS[result.code][0]


if __name__ == "__main__":
    raise SystemExit(main())
